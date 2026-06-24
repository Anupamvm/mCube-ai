'use client';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { familyMemberApi, FamilyMember } from '../../../../lib/api';
import api from '../../../../lib/api';
import { formatINR, formatPct } from '../../../../lib/utils';

interface Analytics {
  snapshot: {
    total_invested: string;
    current_value: string;
    gain_loss: string;
    gain_loss_pct: string;
    xirr?: string;
    asset_allocation: Record<string, number>;
  } | null;
  health_score: {
    total_score: number;
    diversification_score: number;
    concentration_score: number;
    expense_score: number;
    risk_adjusted_score: number;
    allocation_score: number;
    tax_efficiency_score: number;
    insights: string[];
  } | null;
}

function ScoreBar({ label, score, max = 20 }: { label: string; score: number; max?: number }) {
  const pct = Math.min((score / max) * 100, 100);
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium text-slate-800">{score.toFixed(0)}/{max}</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function MemberAnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const memberId = Number(id);

  const { data: member } = useQuery<FamilyMember>({
    queryKey: ['member', memberId],
    queryFn: () => familyMemberApi.get(memberId).then((r) => r.data),
  });

  const { data: analytics, isLoading } = useQuery<Analytics>({
    queryKey: ['analytics', memberId],
    queryFn: () => api.get<Analytics>(`/family-members/${memberId}/analytics/`).then((r) => r.data),
  });

  const { data: insights } = useQuery<{ insights: string[] }>({
    queryKey: ['insights', memberId],
    queryFn: () => api.get(`/family-members/${memberId}/insights/`).then((r) => r.data),
  });

  const snap = analytics?.snapshot;
  const score = analytics?.health_score;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <Link href={`/member/${memberId}`} className="text-slate-400 hover:text-slate-600 text-sm">
          ← {member?.name ?? 'Member'}
        </Link>
      </div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Portfolio Analytics</h1>

      {isLoading && <p className="text-slate-400 text-sm">Loading analytics…</p>}

      {snap && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Current Value', value: formatINR(parseFloat(snap.current_value)) },
            { label: 'Invested', value: formatINR(parseFloat(snap.total_invested)) },
            { label: 'Overall Return', value: formatPct(parseFloat(snap.gain_loss_pct)) },
            { label: 'XIRR', value: snap.xirr ? `${parseFloat(snap.xirr).toFixed(2)}%` : '—' },
          ].map((c) => (
            <div key={c.label} className="bg-white rounded-xl border border-slate-200 p-5">
              <p className="text-xs text-slate-400 uppercase tracking-wide">{c.label}</p>
              <p className="text-xl font-bold text-slate-900 mt-1">{c.value}</p>
            </div>
          ))}
        </div>
      )}

      {score && (
        <div className="grid grid-cols-2 gap-6 mb-8">
          {/* Overall score */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Portfolio Health Score</h2>
            <div className="flex items-center gap-4 mb-6">
              <div className={`w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold text-white ${
                score.total_score >= 70 ? 'bg-green-500' : score.total_score >= 50 ? 'bg-amber-400' : 'bg-red-400'
              }`}>
                {score.total_score}
              </div>
              <div>
                <p className="text-slate-800 font-semibold">
                  {score.total_score >= 70 ? 'Healthy' : score.total_score >= 50 ? 'Moderate' : 'Needs Work'}
                </p>
                <p className="text-xs text-slate-400">out of 100</p>
              </div>
            </div>
            <div className="space-y-3">
              <ScoreBar label="Diversification" score={score.diversification_score} max={20} />
              <ScoreBar label="Concentration" score={score.concentration_score} max={20} />
              <ScoreBar label="Expense Efficiency" score={score.expense_score} max={15} />
              <ScoreBar label="Risk-adjusted Return" score={score.risk_adjusted_score} max={20} />
              <ScoreBar label="Asset Allocation" score={score.allocation_score} max={15} />
              <ScoreBar label="Tax Efficiency" score={score.tax_efficiency_score} max={10} />
            </div>
          </div>

          {/* Insights */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Insights</h2>
            {(insights?.insights ?? score.insights)?.length ? (
              <ul className="space-y-3">
                {(insights?.insights ?? score.insights).map((ins, i) => (
                  <li key={i} className="flex gap-3 text-sm text-slate-700">
                    <span className="text-amber-500 shrink-0 mt-0.5">⚡</span>
                    {ins}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-400 text-sm">No insights generated yet. Update prices and run analytics.</p>
            )}
          </div>
        </div>
      )}

      {!snap && !isLoading && (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-slate-400 mb-3">No analytics data yet.</p>
          <p className="text-xs text-slate-300">Upload a CAS statement and click "Update Prices" on the dashboard.</p>
        </div>
      )}
    </div>
  );
}
