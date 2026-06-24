'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { familyMemberApi, FamilyMember } from '../../lib/api';
import api from '../../lib/api';
import { formatINR, formatPct } from '../../lib/utils';

interface PortfolioGroup {
  id: number;
  name: string;
  description: string;
  group_type: string;
  members: number[];
}

const GROUP_TYPES = ['FAMILY', 'RETIREMENT', 'TAX_SAVING', 'CUSTOM'];

export default function GroupsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [groupType, setGroupType] = useState('FAMILY');
  const [memberIds, setMemberIds] = useState<number[]>([]);

  const { data: members } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const { data: groups, isLoading } = useQuery<PortfolioGroup[]>({
    queryKey: ['groups'],
    queryFn: () => api.get<PortfolioGroup[]>('/portfolio/groups/').then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post('/portfolio/groups/', { name, description, group_type: groupType, member_ids: memberIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['groups'] });
      setShowForm(false);
      setName(''); setDescription(''); setMemberIds([]);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/portfolio/groups/${id}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }),
  });

  const toggleMember = (id: number) =>
    setMemberIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const INPUT = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500';

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Portfolio Groups</h1>
          <p className="text-slate-400 text-sm mt-1">Group family members for consolidated reporting.</p>
        </div>
        {!showForm && (
          <button onClick={() => setShowForm(true)}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
            + New Group
          </button>
        )}
      </div>

      {showForm && (
        <div className="bg-white rounded-xl border border-blue-200 p-6 mb-6 shadow-sm">
          <h3 className="font-semibold text-slate-800 mb-4">Create Group</h3>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Group Name *</label>
                <input value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Retirement Corpus" className={INPUT} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                <select value={groupType} onChange={(e) => setGroupType(e.target.value)} className={INPUT}>
                  {GROUP_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)}
                className={INPUT} placeholder="Optional description" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-2">Members</label>
              <div className="flex gap-2 flex-wrap">
                {members?.map((m) => (
                  <button key={m.id} onClick={() => toggleMember(m.id)}
                    className={`text-sm px-3 py-1 rounded-full border font-medium transition-colors ${
                      memberIds.includes(m.id)
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'text-slate-600 border-slate-300'
                    }`}>
                    {m.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => name && createMutation.mutate()} disabled={!name || createMutation.isPending}
                className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                {createMutation.isPending ? 'Creating…' : 'Create Group'}
              </button>
              <button onClick={() => setShowForm(false)}
                className="border border-slate-300 text-slate-600 px-5 py-2 rounded-lg text-sm hover:bg-slate-50">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-40 mb-2" /><div className="h-3 bg-slate-100 rounded w-24" />
            </div>
          ))}
        </div>
      ) : groups?.length ? (
        <div className="space-y-4">
          {groups.map((g) => (
            <div key={g.id} className="bg-white rounded-xl border border-slate-200 p-5 flex justify-between items-start">
              <div>
                <p className="font-semibold text-slate-800">{g.name}</p>
                <div className="flex gap-2 mt-1 items-center">
                  <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">{g.group_type}</span>
                  <span className="text-xs text-slate-400">
                    {g.members.length} member{g.members.length !== 1 ? 's' : ''}
                  </span>
                </div>
                {g.description && <p className="text-xs text-slate-400 mt-1">{g.description}</p>}
              </div>
              <button onClick={() => deleteMutation.mutate(g.id)}
                className="text-xs text-slate-400 hover:text-red-600 px-2 py-1 rounded">
                Delete
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
          <p className="text-slate-400 mb-4">No groups yet.</p>
          <button onClick={() => setShowForm(true)}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700">
            Create First Group
          </button>
        </div>
      )}
    </div>
  );
}
