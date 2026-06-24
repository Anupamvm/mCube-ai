'use client';
import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
  familyMemberApi, accountApi, productApi,
  FamilyMember, InvestmentAccount, InvestmentProduct,
} from '../../../lib/api';
import { formatINR, formatPct, gainClass, PRODUCT_TYPE_LABELS, ASSET_COLORS } from '../../../lib/utils';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface NetWorth {
  total_current_value: number;
  total_invested_value: number;
  total_gain_loss: number;
  gain_loss_pct: number;
  asset_allocation: Record<string, number>;
  accounts_count: number;
  products_count: number;
}

function ProductRow({ p }: { p: InvestmentProduct }) {
  const gain = parseFloat(p.gain_loss);
  const cv = parseFloat(p.current_value);
  const iv = parseFloat(p.invested_value);
  const gainPct = iv > 0 ? (gain / iv) * 100 : 0;

  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 text-sm">
      <td className="py-3 px-4">
        <p className="font-medium text-slate-800 truncate max-w-xs">{p.name}</p>
        <p className="text-xs text-slate-400 mt-0.5">{p.isin || '—'}</p>
      </td>
      <td className="py-3 px-4">
        <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium">
          {PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type}
        </span>
      </td>
      <td className="py-3 px-4 text-right tabular-nums">{formatINR(iv)}</td>
      <td className="py-3 px-4 text-right tabular-nums">{formatINR(cv)}</td>
      <td className={`py-3 px-4 text-right tabular-nums ${gainClass(gainPct)}`}>
        {formatINR(gain)}
        <span className="text-xs ml-1">({formatPct(gainPct)})</span>
      </td>
      <td className="py-3 px-4 text-right text-slate-400 text-xs">
        {p.xirr ? `${parseFloat(p.xirr).toFixed(1)}%` : '—'}
      </td>
      <td className="py-3 px-4 text-right text-xs text-slate-400">
        {p.as_of_date ?? '—'}
      </td>
    </tr>
  );
}

export default function MemberDetailPage() {
  const { id } = useParams<{ id: string }>();
  const memberId = Number(id);

  const { data: member } = useQuery<FamilyMember>({
    queryKey: ['member', memberId],
    queryFn: () => familyMemberApi.get(memberId).then((r) => r.data),
  });

  const { data: nw } = useQuery<NetWorth>({
    queryKey: ['net-worth', memberId],
    queryFn: () => familyMemberApi.netWorth(memberId).then((r) => r.data as NetWorth),
  });

  const { data: accounts } = useQuery<InvestmentAccount[]>({
    queryKey: ['accounts', memberId],
    queryFn: () => accountApi.list(memberId).then((r) => r.data),
  });

  const { data: products } = useQuery<InvestmentProduct[]>({
    queryKey: ['products', memberId],
    queryFn: () => productApi.list({ member_id: memberId }).then((r) => r.data),
  });

  const [filterType, setFilterType] = useState<string>('ALL');

  const pieData = nw?.asset_allocation
    ? Object.entries(nw.asset_allocation).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k, value: v }))
    : [];

  const productTypes = products ? [...new Set(products.map((p) => p.product_type))] : [];
  const filteredProducts = products?.filter(
    (p) => filterType === 'ALL' || p.product_type === filterType
  );

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <Link href="/" className="text-slate-400 hover:text-slate-600 text-sm">← Dashboard</Link>
      </div>
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{member?.name ?? 'Loading…'}</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {member?.relationship} · {member?.pan_masked}
          </p>
        </div>
        <div className="flex gap-2">
          <Link href={`/member/${memberId}/analytics`}
            className="border border-slate-300 text-slate-600 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-50">
            Analytics
          </Link>
          <Link href="/upload"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
            + Upload CAS
          </Link>
        </div>
      </div>

      {/* Net worth summary */}
      {nw && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Portfolio Value', value: formatINR(nw.total_current_value), sub: null },
            { label: 'Invested', value: formatINR(nw.total_invested_value), sub: null },
            {
              label: 'Gain / Loss',
              value: formatINR(nw.total_gain_loss),
              sub: formatPct(nw.gain_loss_pct),
            },
            { label: 'Holdings', value: String(nw.products_count), sub: `${nw.accounts_count} accounts` },
          ].map((c) => (
            <div key={c.label} className="bg-white rounded-xl border border-slate-200 p-5">
              <p className="text-xs text-slate-400 uppercase tracking-wide">{c.label}</p>
              <p className={`text-xl font-bold mt-1 ${
                c.label === 'Gain / Loss' ? gainClass(nw.gain_loss_pct) : 'text-slate-900'
              }`}>
                {c.value}
              </p>
              {c.sub && <p className="text-xs text-slate-400 mt-0.5">{c.sub}</p>}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-3 gap-6 mb-8">
        {/* Accounts */}
        <div className="col-span-2">
          <h2 className="text-base font-semibold text-slate-700 mb-3">Accounts</h2>
          <div className="space-y-2">
            {accounts?.map((a) => (
              <Link key={a.id} href={`/account/${a.id}`}
                className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center gap-3 hover:shadow-sm transition-shadow">
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-800">{a.account_name}</p>
                  <p className="text-xs text-slate-400">{a.institution_name} · {a.account_type}</p>
                </div>
                <span className={`w-2 h-2 rounded-full ${a.is_active ? 'bg-green-500' : 'bg-slate-300'}`} />
              </Link>
            ))}
            {!accounts?.length && (
              <p className="text-slate-400 text-sm">No accounts found. Upload a CAS to get started.</p>
            )}
          </div>
        </div>

        {/* Allocation pie */}
        {pieData.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-2">Allocation</h2>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={65}>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={ASSET_COLORS[entry.name] ?? '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => (typeof v === 'number' ? formatINR(v) : String(v))} />
                <Legend iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Holdings table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-slate-700">Holdings</h2>
          <div className="flex gap-2">
            {['ALL', ...productTypes].map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                  filterType === t
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {t === 'ALL' ? 'All' : (PRODUCT_TYPE_LABELS[t] ?? t)}
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
                <th className="text-right py-3 px-4 font-medium">Current</th>
                <th className="text-right py-3 px-4 font-medium">Gain/Loss</th>
                <th className="text-right py-3 px-4 font-medium">XIRR</th>
                <th className="text-right py-3 px-4 font-medium">As of</th>
              </tr>
            </thead>
            <tbody>
              {filteredProducts?.map((p) => <ProductRow key={p.id} p={p} />)}
              {!filteredProducts?.length && (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-400 text-sm">
                    No holdings found.
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
