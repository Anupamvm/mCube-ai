'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { familyMemberApi, analyticsApi, productApi, FamilyMember, InvestmentProduct } from '../../../lib/api';
import { formatINR, formatPct, gainClass, PRODUCT_TYPE_LABELS, ASSET_COLORS } from '../../../lib/utils';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

interface NetWorth {
  total_current_value: number;
  total_invested_value: number;
  total_gain_loss: number;
  gain_loss_pct: number;
  asset_allocation: Record<string, number>;
  accounts_count: number;
  products_count: number;
}

export default function ConsolidatedPage() {
  const { data: members } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const [selectedMembers, setSelectedMembers] = useState<Set<number>>(new Set());

  const memberIds = selectedMembers.size > 0
    ? [...selectedMembers]
    : (members?.map((m) => m.id) ?? []);

  const { data: consolidated } = useQuery<NetWorth>({
    queryKey: ['consolidated', memberIds],
    queryFn: () => analyticsApi.consolidated(memberIds).then((r) => r.data as NetWorth),
    enabled: memberIds.length > 0,
  });

  const { data: products } = useQuery<InvestmentProduct[]>({
    queryKey: ['products-all'],
    queryFn: () => productApi.list().then((r) => r.data),
  });

  const toggleMember = (id: number) => {
    setSelectedMembers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const pieData = consolidated?.asset_allocation
    ? Object.entries(consolidated.asset_allocation).filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: k, value: v }))
        .sort((a, b) => b.value - a.value)
    : [];

  const memberBarData = members?.map((m) => ({
    name: m.name.split(' ')[0],
    id: m.id,
  }));

  const [sortBy, setSortBy] = useState<'current_value' | 'gain_loss'>('current_value');

  const sortedProducts = products
    ? [...products].sort((a, b) =>
        parseFloat(b[sortBy]) - parseFloat(a[sortBy])
      )
    : [];

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Consolidated Portfolio</h1>

      {/* Member filter */}
      {members && members.length > 1 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          <span className="text-sm text-slate-500 self-center">Filter:</span>
          {members.map((m) => (
            <button
              key={m.id}
              onClick={() => toggleMember(m.id)}
              className={`text-sm px-3 py-1 rounded-full font-medium border transition-colors ${
                selectedMembers.size === 0 || selectedMembers.has(m.id)
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-300 hover:border-blue-400'
              }`}
            >
              {m.name}
            </button>
          ))}
        </div>
      )}

      {/* Summary banner */}
      {consolidated && (
        <div className="bg-gradient-to-r from-slate-800 to-slate-900 rounded-2xl p-6 text-white mb-8">
          <div className="grid grid-cols-4 gap-6">
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wide">Total Value</p>
              <p className="text-3xl font-bold mt-1">{formatINR(consolidated.total_current_value)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wide">Invested</p>
              <p className="text-xl font-semibold mt-1">{formatINR(consolidated.total_invested_value)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wide">Gain / Loss</p>
              <p className={`text-xl font-semibold mt-1 ${consolidated.total_gain_loss >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatINR(consolidated.total_gain_loss)}
                <span className="text-sm ml-2 opacity-80">({formatPct(consolidated.gain_loss_pct)})</span>
              </p>
            </div>
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wide">Holdings</p>
              <p className="text-xl font-semibold mt-1">{consolidated.products_count}</p>
              <p className="text-xs text-slate-500 mt-0.5">{consolidated.accounts_count} accounts</p>
            </div>
          </div>
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-6 mb-8">
        {pieData.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-3">Asset Allocation</h2>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100}
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false}>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={ASSET_COLORS[entry.name] ?? '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => (typeof v === 'number' ? formatINR(v) : String(v))} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {pieData.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-3">By Asset Class (₹)</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={pieData} layout="vertical" margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => `${(v / 1e5).toFixed(0)}L`} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
                <Tooltip formatter={(v) => (typeof v === 'number' ? formatINR(v) : String(v))} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={ASSET_COLORS[entry.name] ?? '#94a3b8'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Holdings table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-slate-700">All Holdings</h2>
          <div className="flex gap-2 text-xs">
            {(['current_value', 'gain_loss'] as const).map((k) => (
              <button key={k} onClick={() => setSortBy(k)}
                className={`px-3 py-1 rounded-full border font-medium transition-colors ${
                  sortBy === k ? 'bg-blue-600 text-white border-blue-600' : 'text-slate-600 border-slate-300'
                }`}>
                Sort by {k === 'current_value' ? 'Value' : 'Gain'}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                <th className="text-left py-3 px-4 font-medium">Security</th>
                <th className="text-left py-3 px-4 font-medium">Type</th>
                <th className="text-right py-3 px-4 font-medium">Invested</th>
                <th className="text-right py-3 px-4 font-medium">Current Value</th>
                <th className="text-right py-3 px-4 font-medium">Gain/Loss</th>
                <th className="text-right py-3 px-4 font-medium">% Return</th>
              </tr>
            </thead>
            <tbody>
              {sortedProducts.map((p) => {
                const iv = parseFloat(p.invested_value);
                const cv = parseFloat(p.current_value);
                const gain = parseFloat(p.gain_loss);
                const gainPct = iv > 0 ? (gain / iv) * 100 : 0;
                return (
                  <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50 text-sm">
                    <td className="py-3 px-4">
                      <p className="font-medium text-slate-800 truncate max-w-sm">{p.name}</p>
                      <p className="text-xs text-slate-400">{p.isin || '—'}</p>
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                        {PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-slate-700">{formatINR(iv)}</td>
                    <td className="py-3 px-4 text-right tabular-nums font-medium text-slate-900">{formatINR(cv)}</td>
                    <td className={`py-3 px-4 text-right tabular-nums ${gainClass(gainPct)}`}>
                      {formatINR(gain)}
                    </td>
                    <td className={`py-3 px-4 text-right tabular-nums ${gainClass(gainPct)}`}>
                      {formatPct(gainPct)}
                    </td>
                  </tr>
                );
              })}
              {!sortedProducts.length && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400 text-sm">
                    No holdings found. Upload a CAS statement to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
