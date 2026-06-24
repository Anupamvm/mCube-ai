'use client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { familyMemberApi, analyticsApi, FamilyMember } from '../lib/api';
import { formatINR, formatPct, gainClass, ASSET_COLORS } from '../lib/utils';
import Link from 'next/link';
import { useState } from 'react';
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

function MemberCard({ member }: { member: FamilyMember }) {
  const { data: nw } = useQuery({
    queryKey: ['net-worth', member.id],
    queryFn: () => familyMemberApi.netWorth(member.id).then((r) => r.data as NetWorth),
  });

  return (
    <Link href={`/member/${member.id}`}
      className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md transition-shadow cursor-pointer block">
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-semibold text-slate-800 text-base">{member.name}</p>
          <p className="text-xs text-slate-400 uppercase tracking-wide">{member.relationship}</p>
        </div>
        {member.pan_masked && (
          <span className="text-xs bg-slate-100 text-slate-500 px-2 py-1 rounded font-mono">
            {member.pan_masked}
          </span>
        )}
      </div>
      {nw ? (
        <>
          <p className="text-2xl font-bold text-slate-900">{formatINR(nw.total_current_value)}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-sm text-slate-500">Invested: {formatINR(nw.total_invested_value)}</span>
            <span className={`text-sm font-medium ${gainClass(nw.gain_loss_pct)}`}>
              {formatPct(nw.gain_loss_pct)}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            {nw.products_count} holdings · {nw.accounts_count} accounts
          </p>
        </>
      ) : (
        <p className="text-slate-400 text-sm mt-2">Loading…</p>
      )}
    </Link>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
  const [updating, setUpdating] = useState(false);

  const { data: members, isLoading } = useQuery({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const { data: consolidated } = useQuery({
    queryKey: ['consolidated', members?.map((m) => m.id)],
    queryFn: () =>
      members && members.length > 0
        ? analyticsApi.consolidated(members.map((m) => m.id)).then((r) => r.data as NetWorth)
        : Promise.resolve(null),
    enabled: !!members && members.length > 0,
  });

  const updatePricesMutation = useMutation({
    mutationFn: () => analyticsApi.updatePrices(),
    onSuccess: () => {
      setUpdating(false);
      qc.invalidateQueries({ queryKey: ['net-worth'] });
      qc.invalidateQueries({ queryKey: ['consolidated'] });
    },
  });

  const pieData = consolidated?.asset_allocation
    ? Object.entries(consolidated.asset_allocation)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: k, value: v }))
    : [];

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Family Net Worth</h1>
          {consolidated && (
            <p className="text-slate-500 mt-1">
              Total portfolio across all family members
            </p>
          )}
        </div>
        <button
          onClick={() => { setUpdating(true); updatePricesMutation.mutate(); }}
          disabled={updating}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium
                     hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {updating ? 'Updating…' : '⟳ Update Prices'}
        </button>
      </div>

      {/* Total net worth banner */}
      {consolidated && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-6 text-white mb-8 shadow-lg">
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-blue-200 text-sm">Total Portfolio Value</p>
              <p className="text-4xl font-bold mt-1">{formatINR(consolidated.total_current_value)}</p>
            </div>
            <div>
              <p className="text-blue-200 text-sm">Total Invested</p>
              <p className="text-2xl font-semibold mt-1">{formatINR(consolidated.total_invested_value)}</p>
            </div>
            <div>
              <p className="text-blue-200 text-sm">Overall Gain/Loss</p>
              <p className="text-2xl font-semibold mt-1">
                {formatINR(consolidated.total_gain_loss)}
                <span className="text-lg ml-2 opacity-80">
                  ({formatPct(consolidated.gain_loss_pct)})
                </span>
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-6 mb-8">
        {/* Asset allocation pie */}
        {pieData.length > 0 && (
          <div className="col-span-1 bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-3">Asset Allocation</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={ASSET_COLORS[entry.name] ?? '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => (typeof v === 'number' ? formatINR(v) : String(v))} />
                <Legend iconSize={10} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Quick actions */}
        <div className="col-span-2 bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { href: '/upload', label: '📤 Upload CAS PDF', desc: 'Import NSDL/CAMS statement' },
              { href: '/portfolio/consolidated', label: '📊 Consolidated View', desc: 'Full family portfolio' },
              { href: '/reports', label: '📄 Generate Report', desc: 'PDF or Excel download' },
              { href: '/settings/family', label: '👨‍👩‍👧 Manage Family', desc: 'Add / edit members' },
            ].map((a) => (
              <Link key={a.href} href={a.href}
                className="border border-slate-200 rounded-lg p-4 hover:bg-slate-50 transition-colors">
                <p className="font-medium text-slate-800 text-sm">{a.label}</p>
                <p className="text-xs text-slate-400 mt-1">{a.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Family members */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-slate-800">Family Members</h2>
          <Link href="/settings/family"
            className="text-sm text-blue-600 hover:text-blue-700 font-medium">
            + Add Member
          </Link>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-32 mb-3" />
                <div className="h-8 bg-slate-100 rounded w-48" />
              </div>
            ))}
          </div>
        ) : members && members.length > 0 ? (
          <div className="grid grid-cols-3 gap-4">
            {members.map((m) => <MemberCard key={m.id} member={m} />)}
          </div>
        ) : (
          <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
            <p className="text-slate-400 mb-4">No family members yet.</p>
            <Link href="/settings/family"
              className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700">
              Add Your First Member
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
