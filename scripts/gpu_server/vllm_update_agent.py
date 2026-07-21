#!/usr/bin/env python3
"""
vLLM model management agent.

Runs ON THE GPU SERVER (not in the Django app). Exposes a tiny, token-
authenticated HTTP API that the Django "Model Manager" UI calls to list,
download, activate, and delete models for the vllm-70b container - without
needing SSH access from Django.

    GET  /models
        -> every model known to the HF cache (ground truth - scanned from
           disk each call) plus any in-flight downloads, with the currently
           active one flagged.

    POST /models/download {"model": "org/repo-name"}
        -> pre-fetches a model's weights into the shared HF cache in the
           background WITHOUT touching the live container. Returns
           immediately; poll GET /models to see progress.

    POST /models/activate {"model": "org/repo-name"}  (model optional)
        -> rewrites the --model argument in docker-compose.yml (if a model
           is given), runs `docker compose pull` + `docker compose up -d
           --force-recreate`, then polls the vLLM API until it responds
           before declaring success. Runs in the background.

    POST /models/delete {"model": "org/repo-name"}
        -> removes a model's weights from the HF cache to free disk space.
           Refuses to delete the currently active model.

    GET  /status
        -> status of the last/current activate operation (unchanged from
           the original single-model update agent), including a tail of
           the update log.

Dependencies: stdlib + huggingface_hub (for cache scanning/downloading).
Auth via a shared bearer token (UPDATE_AGENT_TOKEN env var) so the endpoint
can't be triggered by anyone else on the LAN.
"""

import http.server
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone

from huggingface_hub import scan_cache_dir, snapshot_download

COMPOSE_DIR = os.path.expanduser('~/vllm')
COMPOSE_FILE = os.path.join(COMPOSE_DIR, 'docker-compose.yml')
LOG_FILE = os.path.join(COMPOSE_DIR, 'update_agent.log')
# NOTE: this must be the "hub" cache dir (where models--org--repo/ folders live),
# not its parent. docker-compose.yml mounts ~/hf_cache -> /root/.cache/huggingface
# inside the container, so the container's HF_HOME resolves there and it looks for
# models at $HF_HOME/hub - i.e. ~/hf_cache/hub on the host. Downloading anywhere
# else here would silently be invisible to the container, defeating pre-downloads.
HF_CACHE_DIR = os.path.expanduser(os.environ.get('HF_CACHE_DIR', '~/hf_cache/hub'))
TOKEN = os.environ.get('UPDATE_AGENT_TOKEN', '')
PORT = int(os.environ.get('UPDATE_AGENT_PORT', '8090'))
CONTAINER_NAME = os.environ.get('VLLM_CONTAINER_NAME', 'vllm-70b')
HEALTH_URL = os.environ.get('VLLM_HEALTH_URL', 'http://localhost:8000/v1/models')
HEALTH_TIMEOUT_SECONDS = int(os.environ.get('VLLM_HEALTH_TIMEOUT_SECONDS', '600'))

MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.\-]*/[A-Za-z0-9][A-Za-z0-9_.\-]*$')

activate_lock = threading.Lock()
activate_state = {'status': 'idle', 'started_at': None, 'finished_at': None, 'log': '', 'target_model': None}

downloads_lock = threading.Lock()
downloads = {}  # repo_id -> {'status', 'started_at', 'finished_at', 'error'}


def _human_size(num_bytes):
    if not num_bytes:
        return None
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024:
            return f'{size:.1f}{unit}'
        size /= 1024
    return f'{size:.1f}PB'


# ---------------------------------------------------------------------------
# Model registry (ground truth = HF cache on disk, plus in-flight downloads)
# ---------------------------------------------------------------------------

def _scan_downloaded_models():
    """Return {repo_id: size_bytes} for models actually present in the HF cache."""
    try:
        cache_info = scan_cache_dir(cache_dir=HF_CACHE_DIR)
        return {
            repo.repo_id: repo.size_on_disk
            for repo in cache_info.repos
            if repo.repo_type == 'model'
        }
    except Exception:
        return {}


def list_models():
    disk_models = _scan_downloaded_models()
    current = _current_model()

    result = {}
    for repo_id, size in disk_models.items():
        result[repo_id] = {'repo_id': repo_id, 'status': 'downloaded', 'size_bytes': size, 'size': _human_size(size)}

    with downloads_lock:
        for repo_id, info in downloads.items():
            if repo_id not in result or info['status'] in ('downloading', 'failed'):
                entry = result.get(repo_id, {'repo_id': repo_id, 'size_bytes': None, 'size': None})
                entry.update(info)
                result[repo_id] = entry

    if current:
        if current not in result:
            result[current] = {'repo_id': current, 'status': 'active', 'size_bytes': None, 'size': None}
        else:
            result[current]['status'] = 'active'

    return sorted(result.values(), key=lambda m: m['repo_id'])


def do_download(model_repo):
    with downloads_lock:
        downloads[model_repo] = {
            'status': 'downloading',
            'started_at': datetime.now(timezone.utc).isoformat(),
            'finished_at': None,
            'error': None,
        }
    try:
        snapshot_download(repo_id=model_repo, cache_dir=HF_CACHE_DIR)
        with downloads_lock:
            downloads[model_repo]['status'] = 'downloaded'
            downloads[model_repo]['finished_at'] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        with downloads_lock:
            downloads[model_repo]['status'] = 'failed'
            downloads[model_repo]['finished_at'] = datetime.now(timezone.utc).isoformat()
            downloads[model_repo]['error'] = str(e)


def do_delete(model_repo):
    try:
        cache_info = scan_cache_dir(cache_dir=HF_CACHE_DIR)
        for repo in cache_info.repos:
            if repo.repo_id == model_repo and repo.repo_type == 'model':
                revisions = [rev.commit_hash for rev in repo.revisions]
                cache_info.delete_revisions(*revisions).execute()
                with downloads_lock:
                    downloads.pop(model_repo, None)
                return True, None
        return False, 'Model not found in cache'
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Activate (switch the live container to a given model)
# ---------------------------------------------------------------------------

def _append_log(text):
    with activate_lock:
        activate_state['log'] += text


def _run(cmd):
    _append_log(f'\n$ {cmd}\n')
    proc = subprocess.run(
        cmd, shell=True, cwd=COMPOSE_DIR,
        capture_output=True, text=True, timeout=1800,
    )
    _append_log(proc.stdout + proc.stderr)
    return proc.returncode == 0


def _current_model():
    try:
        with open(COMPOSE_FILE) as f:
            content = f.read()
        m = re.search(r'--model\s+(\S+)', content)
        return m.group(1) if m else None
    except OSError:
        return None


def _set_model_in_compose(new_model):
    with open(COMPOSE_FILE) as f:
        content = f.read()
    new_content, n = re.subn(r'(--model\s+)\S+', r'\g<1>' + new_model, content, count=1)
    if n == 0:
        raise ValueError('Could not find --model argument in docker-compose.yml')
    with open(COMPOSE_FILE, 'w') as f:
        f.write(new_content)


def _strip_legacy_nvidia_runtime():
    """Remove any `runtime: nvidia` line from docker-compose.yml, if present.

    On this host that legacy runtime path (vs. the modern `deploy.resources.
    reservations.devices` GPU block, which is sufficient on its own) makes
    the container fail with "Error 803: unsupported display driver / cuda
    driver combination" even though the host driver, GPU, and image are all
    fine (diagnosed 2026-07-21 - see memory). It was removed by hand once;
    this makes every future activate self-heal if it ever comes back
    (restored backup, manual edit, etc.) instead of silently reintroducing
    the same failure.
    """
    try:
        with open(COMPOSE_FILE) as f:
            lines = f.readlines()
    except OSError:
        return
    filtered = [ln for ln in lines if ln.strip() != 'runtime: nvidia']
    if len(filtered) != len(lines):
        with open(COMPOSE_FILE, 'w') as f:
            f.writelines(filtered)
        _append_log('\nRemoved legacy `runtime: nvidia` line from docker-compose.yml (breaks GPU init on this host).\n')


def _wait_for_health(timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def _container_info():
    try:
        out = subprocess.run(
            ['docker', 'inspect', CONTAINER_NAME, '--format',
             '{{.Config.Image}}|{{.Image}}|{{.Created}}|{{.State.Status}}'],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split('|')
            if len(parts) == 4:
                image, image_id, created, status = parts
                return {
                    'image': image,
                    'image_id': image_id.replace('sha256:', '')[:19],
                    'container_created': created,
                    'container_status': status,
                }
    except Exception:
        pass
    return {}


def _bring_up_and_wait():
    """Pull + force-recreate the container per whatever's currently in
    docker-compose.yml, then wait for it to report healthy. Returns bool."""
    ok = _run('docker compose pull')
    ok = _run('docker compose up -d --force-recreate') and ok
    if not ok:
        return False
    _append_log('\nWaiting for vLLM API to become healthy...\n')
    healthy = _wait_for_health(HEALTH_TIMEOUT_SECONDS)
    if not healthy:
        _append_log(f'\nTimed out waiting for {HEALTH_URL} after {HEALTH_TIMEOUT_SECONDS}s\n')
        _run(f'docker logs --tail 100 {CONTAINER_NAME}')
        return False
    _append_log('\nvLLM API is responding - update successful.\n')
    return True


def do_activate(target_model):
    with activate_lock:
        activate_state['status'] = 'running'
        activate_state['started_at'] = datetime.now(timezone.utc).isoformat()
        activate_state['finished_at'] = None
        activate_state['log'] = ''
        activate_state['target_model'] = target_model

    previous_model = _current_model()

    ok = True
    if target_model:
        try:
            _set_model_in_compose(target_model)
            _append_log(f'\nSwitching model to: {target_model}\n')
        except Exception as e:
            ok = False
            _append_log(f'\nFailed to update docker-compose.yml: {e}\n')

    if ok:
        _strip_legacy_nvidia_runtime()

    if ok:
        # Explicit unload before loading the new model, rather than relying
        # solely on `--force-recreate`'s implicit stop - makes the swap
        # atomic-ish and guarantees the old model's GPU memory is freed
        # before the new one tries to load. Harmless no-op if nothing was
        # running (e.g. first-ever activation).
        _append_log('\nUnloading current model (if running)...\n')
        _run('docker compose stop')
        ok = _bring_up_and_wait()

    if not ok:
        # Don't leave a broken/unsupported model crash-looping forever via
        # restart: unless-stopped - stop it, and if something was working
        # before this attempt, roll back to it so the system isn't left
        # with no LLM at all.
        _append_log('\nActivation failed - stopping the failed container.\n')
        _run('docker compose stop')

        if target_model and previous_model and previous_model != target_model:
            _append_log(f'\nRolling back to previously active model: {previous_model}\n')
            try:
                _set_model_in_compose(previous_model)
                if _bring_up_and_wait():
                    _append_log(f'\nRolled back successfully - {previous_model} is running again.\n')
                else:
                    _append_log(f'\nRollback to {previous_model} also failed to come up healthy - manual intervention needed.\n')
            except Exception as e:
                _append_log(f'\nRollback failed: {e}\n')

    with activate_lock:
        activate_state['status'] = 'success' if ok else 'failed'
        activate_state['finished_at'] = datetime.now(timezone.utc).isoformat()
        snapshot = dict(activate_state)

    try:
        with open(LOG_FILE, 'a') as f:
            f.write(
                f"\n=== Activate {snapshot['finished_at']} status={snapshot['status']} "
                f"target_model={snapshot['target_model']} ===\n{snapshot['log']}\n"
            )
    except OSError:
        pass


def do_stop():
    """Stop the vLLM container without starting another model, to free GPU
    memory (e.g. when mCube has switched to OpenAI and isn't using it)."""
    with activate_lock:
        activate_state['status'] = 'running'
        activate_state['started_at'] = datetime.now(timezone.utc).isoformat()
        activate_state['finished_at'] = None
        activate_state['log'] = ''
        activate_state['target_model'] = None

    _append_log('\nStopping vLLM container...\n')
    ok = _run('docker compose stop')
    if ok:
        _append_log('\nvLLM container stopped.\n')

    with activate_lock:
        activate_state['status'] = 'success' if ok else 'failed'
        activate_state['finished_at'] = datetime.now(timezone.utc).isoformat()
        snapshot = dict(activate_state)

    try:
        with open(LOG_FILE, 'a') as f:
            f.write(
                f"\n=== Stop {snapshot['finished_at']} status={snapshot['status']} ===\n{snapshot['log']}\n"
            )
    except OSError:
        pass


def _log_tail(max_bytes=20000):
    try:
        with open(LOG_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode('utf-8', errors='replace')
    except OSError:
        return ''


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def _authed(self):
        return bool(TOKEN) and self.headers.get('Authorization') == f'Bearer {TOKEN}'

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _validated_model(self, body):
        model = (body.get('model') or '').strip() or None
        if model and not MODEL_RE.match(model):
            return None, 'invalid model repo format - expected org/model-name'
        return model, None

    def do_POST(self):
        if not self._authed():
            return self._send(401, {'error': 'unauthorized'})

        if self.path == '/models/download':
            body = self._read_json_body()
            model, err = self._validated_model(body)
            if err or not model:
                return self._send(400, {'error': err or 'model is required'})
            with downloads_lock:
                already = downloads.get(model, {}).get('status') == 'downloading'
            if already:
                return self._send(409, {'error': 'already downloading'})
            threading.Thread(target=do_download, args=(model,), daemon=True).start()
            return self._send(202, {'status': 'started', 'model': model})

        if self.path == '/models/activate':
            body = self._read_json_body()
            model, err = self._validated_model(body)
            if err:
                return self._send(400, {'error': err})
            if model and model not in _scan_downloaded_models():
                return self._send(400, {'error': f'{model} is not downloaded yet - download it first'})
            with activate_lock:
                already_running = activate_state['status'] == 'running'
            if already_running:
                return self._send(409, {'error': 'an activate is already in progress'})
            threading.Thread(target=do_activate, args=(model,), daemon=True).start()
            return self._send(202, {'status': 'started', 'target_model': model})

        if self.path == '/models/delete':
            body = self._read_json_body()
            model, err = self._validated_model(body)
            if err or not model:
                return self._send(400, {'error': err or 'model is required'})
            if model == _current_model():
                return self._send(400, {'error': 'cannot delete the currently active model'})
            ok, error = do_delete(model)
            if ok:
                return self._send(200, {'status': 'deleted', 'model': model})
            return self._send(500, {'error': error})

        if self.path == '/models/stop':
            with activate_lock:
                already_running = activate_state['status'] == 'running'
            if already_running:
                return self._send(409, {'error': 'an activate/stop is already in progress'})
            threading.Thread(target=do_stop, daemon=True).start()
            return self._send(202, {'status': 'started'})

        # Backward-compatible alias for the old single-model UI
        if self.path == '/update':
            body = self._read_json_body()
            model, err = self._validated_model(body)
            if err:
                return self._send(400, {'error': err})
            with activate_lock:
                already_running = activate_state['status'] == 'running'
            if already_running:
                return self._send(409, {'error': 'update already in progress'})
            threading.Thread(target=do_activate, args=(model,), daemon=True).start()
            return self._send(202, {'status': 'started', 'target_model': model})

        self._send(404, {'error': 'not found'})

    def do_GET(self):
        if not self._authed():
            return self._send(401, {'error': 'unauthorized'})

        if self.path == '/models':
            return self._send(200, {'models': list_models()})

        if self.path == '/status':
            with activate_lock:
                payload = dict(activate_state)
            payload['current_model'] = _current_model()
            payload.update(_container_info())
            payload['log_tail'] = payload['log'] if payload.get('status') == 'running' else _log_tail()
            return self._send(200, payload)

        self._send(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        pass  # quiet; details go to LOG_FILE instead


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('UPDATE_AGENT_TOKEN env var is required')
    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'vLLM update agent listening on :{PORT}')
    server.serve_forever()
