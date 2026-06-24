'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { familyMemberApi, FamilyMember } from '../../../lib/api';

const RELATIONSHIPS = [
  'SELF', 'SPOUSE', 'FATHER', 'MOTHER', 'CHILD', 'HUF', 'TRUST', 'OTHER',
];

function MemberForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<FamilyMember>;
  onSave: (data: Partial<FamilyMember>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? '');
  const [relationship, setRelationship] = useState(initial?.relationship ?? 'SELF');
  const [dob, setDob] = useState(initial?.date_of_birth ?? '');

  return (
    <div className="bg-white border border-blue-200 rounded-xl p-5 shadow-sm">
      <h3 className="font-semibold text-slate-800 mb-4">
        {initial ? 'Edit Member' : 'Add Family Member'}
      </h3>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Full Name *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="e.g. Anupam Mangudkar"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Relationship</label>
          <select
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          >
            {RELATIONSHIPS.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Date of Birth</label>
          <input
            type="date"
            value={dob}
            onChange={(e) => setDob(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
      <p className="text-xs text-slate-400 mb-4">
        PAN will be auto-detected from the CAS statement upon upload.
      </p>
      <div className="flex gap-3">
        <button
          onClick={() => name && onSave({ name, relationship, date_of_birth: dob || undefined })}
          disabled={!name}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {initial ? 'Update' : 'Add Member'}
        </button>
        <button
          onClick={onCancel}
          className="border border-slate-300 text-slate-600 px-5 py-2 rounded-lg text-sm hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function FamilySettingsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const { data: members, isLoading } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (data: Partial<FamilyMember>) => familyMemberApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['family-members'] });
      setShowForm(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<FamilyMember> }) =>
      familyMemberApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['family-members'] });
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => familyMemberApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['family-members'] });
      setDeleteConfirm(null);
    },
  });

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Family Members</h1>
          <p className="text-slate-400 text-sm mt-1">
            Manage family members whose investments you track.
          </p>
        </div>
        {!showForm && (
          <button
            onClick={() => { setShowForm(true); setEditingId(null); }}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            + Add Member
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-6">
          <MemberForm
            onSave={(data) => createMutation.mutate(data)}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-40 mb-2" />
              <div className="h-3 bg-slate-100 rounded w-24" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {members?.map((m) => (
            <div key={m.id}>
              {editingId === m.id ? (
                <MemberForm
                  initial={m}
                  onSave={(data) => updateMutation.mutate({ id: m.id, data })}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div className="bg-white rounded-xl border border-slate-200 p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-semibold text-slate-800">{m.name}</p>
                      <div className="flex gap-3 mt-1">
                        <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                          {m.relationship}
                        </span>
                        {m.pan_masked && (
                          <span className="text-xs font-mono text-slate-400">{m.pan_masked}</span>
                        )}
                        {m.date_of_birth && (
                          <span className="text-xs text-slate-400">DOB: {m.date_of_birth}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => { setEditingId(m.id); setShowForm(false); }}
                        className="text-xs text-slate-500 hover:text-blue-600 px-3 py-1 border border-slate-200 rounded-lg"
                      >
                        Edit
                      </button>
                      {deleteConfirm === m.id ? (
                        <div className="flex gap-2 items-center">
                          <span className="text-xs text-red-600 font-medium">Delete all data?</span>
                          <button
                            onClick={() => deleteMutation.mutate(m.id)}
                            className="text-xs bg-red-600 text-white px-3 py-1 rounded-lg hover:bg-red-700"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            className="text-xs text-slate-500 px-2 py-1"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirm(m.id)}
                          className="text-xs text-slate-500 hover:text-red-600 px-3 py-1 border border-slate-200 rounded-lg"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {!members?.length && !showForm && (
            <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
              <p className="text-slate-400 mb-4">No family members added yet.</p>
              <button
                onClick={() => setShowForm(true)}
                className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700"
              >
                Add Your First Member
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
