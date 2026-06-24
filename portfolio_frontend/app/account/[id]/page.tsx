'use client';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { accountApi, productApi, InvestmentAccount, InvestmentProduct } from '../../../lib/api';
import { formatINR, formatPct, gainClass, PRODUCT_TYPE_LABELS } from '../../../lib/utils';

export default function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);

  const { data: account } = useQuery<InvestmentAccount>({
    queryKey: ['account', accountId],
    queryFn: () => accountApi.get(accountId).then((r) => r.data),
  });

  const { data: products } = useQuery<InvestmentProduct[]>({
    queryKey: ['account-products', accountId],
    queryFn: () =>
      productApi.list({ account_id: accountId }).then((r) => r.data),
  });

  const totalInvested = products?.reduce((s, p) => s + parseFloat(p.invested_value), 0) ?? 0;
  const totalCurrent = products?.reduce((s, p) => s + parseFloat(p.current_value), 0) ?? 0;
  const gainPct = totalInvested > 0 ? ((totalCurrent - totalInvested) / totalInvested) * 100 : 0;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <Link href="/" className="text-slate-400 hover:text-slate-600 text-sm">← Dashboard</Link>

      <div className="flex justify-between items-start mt-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{account?.account_name ?? 'Loading…'}</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {account?.institution_name} · {account?.account_type}
          </p>
        </div>
        <Link
          href={`/account/${accountId}/add-product`}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          + Add Holding
        </Link>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: 'Current Value', value: formatINR(totalCurrent) },
          { label: 'Invested', value: formatINR(totalInvested) },
          { label: 'Gain / Loss', value: `${formatINR(totalCurrent - totalInvested)} (${formatPct(gainPct)})`, color: gainClass(gainPct) },
        ].map((c) => (
          <div key={c.label} className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-xs text-slate-400 uppercase tracking-wide">{c.label}</p>
            <p className={`text-xl font-bold mt-1 ${c.color ?? 'text-slate-900'}`}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* Products table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <th className="text-left py-3 px-4 font-medium">Security</th>
              <th className="text-left py-3 px-4 font-medium">Type</th>
              <th className="text-right py-3 px-4 font-medium">Invested</th>
              <th className="text-right py-3 px-4 font-medium">Current</th>
              <th className="text-right py-3 px-4 font-medium">Gain/Loss</th>
              <th className="text-right py-3 px-4 font-medium">As of</th>
            </tr>
          </thead>
          <tbody>
            {products?.map((p) => {
              const iv = parseFloat(p.invested_value);
              const cv = parseFloat(p.current_value);
              const gl = parseFloat(p.gain_loss);
              const gp = iv > 0 ? (gl / iv) * 100 : 0;
              return (
                <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50 text-sm">
                  <td className="py-3 px-4">
                    <p className="font-medium text-slate-800 truncate max-w-xs">{p.name}</p>
                    <p className="text-xs text-slate-400">{p.isin || '—'}</p>
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                      {PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right tabular-nums">{formatINR(iv)}</td>
                  <td className="py-3 px-4 text-right tabular-nums font-medium">{formatINR(cv)}</td>
                  <td className={`py-3 px-4 text-right tabular-nums ${gainClass(gp)}`}>
                    {formatINR(gl)} <span className="text-xs">({formatPct(gp)})</span>
                  </td>
                  <td className="py-3 px-4 text-right text-xs text-slate-400">{p.as_of_date ?? '—'}</td>
                </tr>
              );
            })}
            {!products?.length && (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-400 text-sm">
                  No holdings yet.{' '}
                  <Link href={`/account/${accountId}/add-product`} className="text-blue-600 hover:underline">
                    Add one manually
                  </Link>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
