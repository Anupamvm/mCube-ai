"""
Compare LLM output quality across models on real production content (analyst
reports + news) before committing to a model switch.

Usage:
    # Step 1: capture what the CURRENTLY running model produces
    python manage.py compare_llm_models --capture-baseline

    # Step 2: switch to a candidate model, wait for it to come up, capture its
    # output on the exact same content, and build a side-by-side HTML report
    python manage.py compare_llm_models --model "Qwen/Qwen3.6-27B" --compare

    # Step 3 (optional): switch back to whatever model was running before step 2
    python manage.py compare_llm_models --revert
"""
import json
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.html import escape

LOGS_DIR = os.path.join(settings.BASE_DIR, 'logs')
BASELINE_FILE = os.path.join(LOGS_DIR, 'llm_compare_baseline.json')
REVERT_FILE = os.path.join(LOGS_DIR, 'llm_compare_previous_model.txt')
REPORT_FILE = os.path.join(LOGS_DIR, 'llm_compare_report.html')


def build_test_cases():
    from apps.data.models import AnalystReport, NewsArticle

    cases = []

    for r in AnalystReport.objects.exclude(pdf_content_text='').order_by('-report_date')[:2]:
        cases.append({
            'label': f'Analyst report: {r.symbol} ({r.report_date})',
            'kind': 'report',
            'text': r.pdf_content_text[:6000],
        })

    for a in NewsArticle.objects.exclude(content='').order_by('-id')[:2]:
        cases.append({
            'label': f'News: {a.title[:70]}',
            'kind': 'news',
            'text': a.content,
        })

    return cases


def run_case(client, case):
    result = {'label': case['label'], 'kind': case['kind']}

    ok, summary, meta = client.summarize(case['text'], max_length=120)
    result['summary'] = summary if ok else f"ERROR: {meta.get('error')}"
    result['summary_ms'] = meta.get('processing_time_ms')

    ok, insights, meta = client.extract_insights(case['text'], num_insights=5)
    result['insights'] = insights if ok else f"ERROR: {meta.get('error')}"
    result['insights_ms'] = meta.get('processing_time_ms')

    if case['kind'] == 'news':
        ok, sentiment, meta = client.analyze_sentiment(case['text'])
        result['sentiment'] = sentiment if ok else f"ERROR: {meta.get('error')}"

    return result


class Command(BaseCommand):
    help = 'Compare LLM output quality across models using real production content'

    def add_arguments(self, parser):
        parser.add_argument('--capture-baseline', action='store_true',
                             help='Run test cases against the currently running model and save as baseline')
        parser.add_argument('--model', type=str, default=None,
                             help='HF model repo to switch to before comparing (e.g. Qwen/Qwen3.6-27B)')
        parser.add_argument('--compare', action='store_true',
                             help='Switch to --model, run the same test cases, and build a side-by-side report')
        parser.add_argument('--revert', action='store_true',
                             help='Switch back to the model that was running before --compare')
        parser.add_argument('--health-timeout', type=int, default=900,
                             help='Seconds to wait for the new model to become healthy (default 900)')
        parser.add_argument('--download-timeout', type=int, default=1800,
                             help='Seconds to wait for the model to finish downloading before activating (default 1800)')

    def handle(self, *args, **options):
        os.makedirs(LOGS_DIR, exist_ok=True)

        if options['revert']:
            return self._revert()
        if options['capture_baseline']:
            return self._capture_baseline()
        if options['compare']:
            if not options['model']:
                self.stderr.write(self.style.ERROR('--compare requires --model <hf-repo-id>'))
                return
            return self._compare(options['model'], options['health_timeout'], options['download_timeout'])

        self.stderr.write(self.style.ERROR('Specify one of --capture-baseline, --compare, or --revert'))

    def _capture_baseline(self):
        from apps.llm.services.vllm_client import get_vllm_client

        client = get_vllm_client()
        if not client.is_enabled():
            self.stderr.write(self.style.ERROR('vLLM is not reachable - cannot capture baseline'))
            return

        self.stdout.write(f'Capturing baseline from: {client.model}')
        cases = build_test_cases()
        if not cases:
            self.stderr.write(self.style.ERROR('No analyst reports / news articles with content found in the DB'))
            return

        results = []
        for case in cases:
            self.stdout.write(f'  Running: {case["label"]}')
            results.append(run_case(client, case))

        with open(BASELINE_FILE, 'w') as f:
            json.dump({'model': client.model, 'results': results}, f, indent=2)
        with open(REVERT_FILE, 'w') as f:
            f.write(client.model)

        self.stdout.write(self.style.SUCCESS(f'Baseline saved to {BASELINE_FILE} ({len(results)} cases)'))

    def _compare(self, target_model, health_timeout, download_timeout):
        from apps.llm.services.vllm_updater import trigger_update, get_status, download_model, list_models

        if not os.path.exists(BASELINE_FILE):
            self.stderr.write(self.style.ERROR('No baseline found - run --capture-baseline first'))
            return
        with open(BASELINE_FILE) as f:
            baseline = json.load(f)

        # The agent only allows activating models it has already downloaded -
        # make sure that's true before asking it to switch.
        ok, models = list_models()
        already_downloaded = ok and any(
            m['repo_id'] == target_model and m['status'] in ('downloaded', 'active') for m in models
        )
        if not already_downloaded:
            self.stdout.write(f'Downloading {target_model} (not yet cached on the server)...')
            ok, msg = download_model(target_model)
            if not ok:
                self.stderr.write(self.style.ERROR(f'Could not start download: {msg}'))
                return

            deadline = time.time() + download_timeout
            downloaded = False
            while time.time() < deadline:
                ok, models = list_models()
                if ok:
                    entry = next((m for m in models if m['repo_id'] == target_model), None)
                    if entry and entry['status'] in ('downloaded', 'active'):
                        downloaded = True
                        break
                    if entry and entry['status'] == 'failed':
                        self.stderr.write(self.style.ERROR(f"Download failed: {entry.get('error')}"))
                        return
                time.sleep(10)
            if not downloaded:
                self.stderr.write(self.style.ERROR(f'Timed out waiting for {target_model} to download'))
                return
            self.stdout.write(self.style.SUCCESS(f'{target_model} downloaded.'))

        self.stdout.write(f'Switching to: {target_model}')
        ok, msg = trigger_update(model=target_model)
        if not ok:
            self.stderr.write(self.style.ERROR(f'Could not start update: {msg}'))
            return

        self.stdout.write('Waiting for new model to become healthy (this can take several minutes)...')
        deadline = time.time() + health_timeout
        final_status = None
        while time.time() < deadline:
            reachable, status = get_status(timeout=10)
            if reachable and status.get('status') in ('success', 'failed'):
                final_status = status
                break
            time.sleep(10)

        if not final_status or final_status.get('status') != 'success':
            self.stderr.write(self.style.ERROR(f'Update did not succeed: {final_status}'))
            return
        self.stdout.write(self.style.SUCCESS('New model is healthy.'))

        # Fresh process each invocation, so the client singleton will connect
        # from scratch and auto-discover whatever model is now being served.
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()
        if not client.is_enabled():
            self.stderr.write(self.style.ERROR('New model came up but the client could not reconnect'))
            return

        cases = build_test_cases()
        new_results = []
        for case in cases:
            self.stdout.write(f'  Running: {case["label"]}')
            new_results.append(run_case(client, case))

        candidate = {'model': client.model, 'results': new_results}
        self._write_report(baseline, candidate)
        self.stdout.write(self.style.SUCCESS(f'Comparison report written to {REPORT_FILE}'))
        self.stdout.write('Run with --revert to switch back to the original model.')

    def _revert(self):
        from apps.llm.services.vllm_updater import trigger_update

        if not os.path.exists(REVERT_FILE):
            self.stderr.write(self.style.ERROR('No previous model recorded - nothing to revert to'))
            return
        with open(REVERT_FILE) as f:
            previous_model = f.read().strip()

        self.stdout.write(f'Reverting to: {previous_model}')
        ok, msg = trigger_update(model=previous_model)
        self.stdout.write(self.style.SUCCESS(msg) if ok else self.style.ERROR(msg))

    def _write_report(self, baseline, candidate):
        def fmt(value):
            if isinstance(value, list):
                return '<ul>' + ''.join(f'<li>{escape(str(v))}</li>' for v in value) + '</ul>'
            if isinstance(value, dict):
                return '<pre>' + escape(json.dumps(value, indent=2)) + '</pre>'
            return escape(str(value)).replace('\n', '<br>')

        rows = ''
        baseline_results = {r['label']: r for r in baseline['results']}
        candidate_results = {r['label']: r for r in candidate['results']}

        for label in baseline_results:
            b = baseline_results.get(label, {})
            c = candidate_results.get(label, {})
            rows += f'<h3>{escape(label)}</h3><table class="cmp"><tr><th>{escape(baseline["model"])}</th><th>{escape(candidate["model"])}</th></tr>'
            rows += f'<tr><td><b>Summary</b> ({b.get("summary_ms", "?")}ms)<br>{fmt(b.get("summary"))}</td>'
            rows += f'<td><b>Summary</b> ({c.get("summary_ms", "?")}ms)<br>{fmt(c.get("summary"))}</td></tr>'
            rows += f'<tr><td><b>Insights</b> ({b.get("insights_ms", "?")}ms)<br>{fmt(b.get("insights"))}</td>'
            rows += f'<td><b>Insights</b> ({c.get("insights_ms", "?")}ms)<br>{fmt(c.get("insights"))}</td></tr>'
            if 'sentiment' in b or 'sentiment' in c:
                rows += f'<tr><td><b>Sentiment</b><br>{fmt(b.get("sentiment"))}</td>'
                rows += f'<td><b>Sentiment</b><br>{fmt(c.get("sentiment"))}</td></tr>'
            rows += '</table>'

        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>LLM Model Comparison</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 30px auto; padding: 0 20px; color: #1a202c; }}
table.cmp {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; table-layout: fixed; }}
table.cmp th, table.cmp td {{ border: 1px solid #cbd5e0; padding: 12px; vertical-align: top; width: 50%; word-wrap: break-word; }}
table.cmp th {{ background: #edf2f7; }}
pre {{ white-space: pre-wrap; font-size: 12px; }}
h1 {{ border-bottom: 2px solid #4299e1; padding-bottom: 10px; }}
</style></head><body>
<h1>LLM Model Comparison</h1>
<p><b>Baseline:</b> {escape(baseline['model'])} &nbsp;|&nbsp; <b>Candidate:</b> {escape(candidate['model'])}</p>
{rows}
</body></html>"""

        with open(REPORT_FILE, 'w') as f:
            f.write(html)
