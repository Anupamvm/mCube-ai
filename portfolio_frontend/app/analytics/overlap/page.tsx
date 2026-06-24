'use client';
import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { familyMemberApi, FamilyMember } from '../../../lib/api';
import api from '../../../lib/api';
import { formatPct } from '../../../lib/utils';

interface OverlapResult {
  amc_concentration: Record<string, number>;
  category_breakdown: Record<string, number>;
  weighted_expense_ratio: number;
  overlap_pairs: Array<{
    fund_a: string;
    fund_b: string;
    overlap_pct: number;
  }>;
  warnings: string[];
}

export default function OverlapPage() {
  const [selectedMembers, setSelectedMembers] = useState<number[]>([]);

  const { data: members } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const overlapMutation = useMutation({
    mutationFn: () =>
      api.post<OverlapResult>('/analytics/overlap/', {
        member_ids: selectedMembers.length ? selectedMembers : members?.map((m) => m.id),
      }),
  });

  const result = overlapMutation.data?.data;

  const toggleMember = (id: number) =>
    setSelectedMembers((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Fund Overlap Analysis</h1>
      <p className="text-slate-400 text-sm mb-6">
        Identify concentration risks and duplicate exposure across your mutual fund holdings.
      </p>

      {/* Member filter */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6">
        <p className="text-sm font-medium text-slate-700 mb-3">Analyse for</p>
        <div className="flex gap-2 flex-wrap mb-4">
          {members?.map((m) => (
            <button
              key={m.id}
              onClick={() => toggleMember(m.id)}
              className={`text-sm px-3 py-1 rounded-full border font-medium transition-colors ${
                !selectedMembers.length || selectedMembers.includes(m.id)
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-300'
              }`}
            >
              {m.name}
            </button>
          ))}
        </div>
        <button
          onClick={() => overlapMutation.mutate()}
          disabled={overlapMutation.isPending}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {overlapMutation.isPending ? 'Analysing…' : 'Run Analysis'}
        </button>
      </div>

      {result && (
        <div className="space-y-6">
          {/* Warnings */}
          {result.warnings?.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-amber-800 mb-2">Warnings</p>
              <ul className="space-y-1">
                {result.warnings.map((w, i) => (
                  <li key={i} className="text-sm text-amber-700">⚠ {w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-2 gap-6">
            {/* AMC Concentration */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">AMC Concentration</h2>
              <div className="space-y-2">
                {Object.entries(result.amc_concentration)
                  .sort(([, a], [, b]) => b - a)
                  .map(([amc, pct]) => (
                    <div key={amc}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-700">{amc}</span>
                        <span className={`font-medium ${pct > 35 ? 'text-red-600' : 'text-slate-600'}`}>
                          {pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full">
                        <div
                          className={`h-full rounded-full ${pct > 35 ? 'bg-red-400' : 'bg-blue-400'}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Category Breakdown */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Category Breakdown</h2>
              <div className="space-y-2">
                {Object.entries(result.category_breakdown)
                  .sort(([, a], [, b]) => b - a)
                  .map(([cat, pct]) => (
                    <div key={cat}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-700">{cat}</span>
                        <span className="font-medium text-slate-600">{pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full">
                        <div className="h-full rounded-full bg-purple-400"
                          style={{ width: `${Math.min(pct, 100)}%` }} />
                      </div>
                    </div>
                  ))}
              </div>
              {result.weighted_expense_ratio > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <p className="text-xs text-slate-500">
                    Weighted Expense Ratio:{' '}
                    <span className={`font-medium ${result.weighted_expense_ratio > 1 ? 'text-red-600' : 'text-green-600'}`}>
                      {result.weighted_expense_ratio.toFixed(2)}%
                    </span>
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Stock overlap pairs */}
          {result.overlap_pairs?.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Fund Overlap Pairs</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-400 uppercase border-b border-slate-100">
                    <th className="text-left pb-2">Fund A</th>
                    <th className="text-left pb-2">Fund B</th>
                    <th className="text-right pb-2">Overlap</th>
                  </tr>
                </thead>
                <tbody>
                  {result.overlap_pairs
                    .sort((a, b) => b.overlap_pct - a.overlap_pct)
                    .map((pair, i) => (
                      <tr key={i} className="border-t border-slate-50">
                        <td className="py-2 text-slate-700 truncate max-w-xs">{pair.fund_a}</td>
                        <td className="py-2 text-slate-700 truncate max-w-xs">{pair.fund_b}</td>
                        <td className={`py-2 text-right font-medium ${pair.overlap_pct > 60 ? 'text-red-600' : pair.overlap_pct > 40 ? 'text-amber-600' : 'text-green-600'}`}>
                          {pair.overlap_pct.toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {overlapMutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mt-4">
          <p className="text-red-700 text-sm">Analysis failed: {(overlapMutation.error as Error).message}</p>
        </div>
      )}
    </div>
  );
}
