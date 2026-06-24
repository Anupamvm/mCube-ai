'use client';
import { useState, useRef } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { familyMemberApi, uploadApi, FamilyMember, CASUpload } from '../../lib/api';

const CAS_TYPES = ['NSDL', 'CAMS', 'KFINTECH'] as const;

export default function UploadPage() {
  const [memberId, setMemberId] = useState<number | ''>('');
  const [casType, setCasType] = useState<'NSDL' | 'CAMS' | 'KFINTECH'>('NSDL');
  const [password, setPassword] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploads, setUploads] = useState<CASUpload[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: members } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  const { data: existingUploads, refetch } = useQuery<CASUpload[]>({
    queryKey: ['cas-uploads'],
    queryFn: () => uploadApi.listCAS().then((r) => r.data),
    refetchInterval: 5000,
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file || !memberId) throw new Error('Missing file or member');
      const fd = new FormData();
      fd.append('file', file);
      fd.append('member_id', String(memberId));
      fd.append('cas_type', casType);
      fd.append('password', password);
      return uploadApi.uploadCAS(fd).then((r) => r.data);
    },
    onSuccess: (data) => {
      setFile(null);
      setPassword('');
      if (fileRef.current) fileRef.current.value = '';
      refetch();
    },
  });

  const statusColor = (s: string) => {
    if (s === 'DONE') return 'text-green-600 bg-green-50';
    if (s === 'ERROR') return 'text-red-600 bg-red-50';
    if (s === 'PROCESSING') return 'text-yellow-600 bg-yellow-50';
    return 'text-slate-500 bg-slate-100';
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Upload CAS Statement</h1>

      <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Family Member *</label>
            <select
              value={memberId}
              onChange={(e) => setMemberId(Number(e.target.value) || '')}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">Select member…</option>
              {members?.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">CAS Type</label>
            <select
              value={casType}
              onChange={(e) => setCasType(e.target.value as typeof casType)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {CAS_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-slate-700 mb-1">PDF Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="e.g. AAQHA1835B"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="text-xs text-slate-400 mt-1">
            Usually your PAN or date of birth. Never stored.
          </p>
        </div>

        <div className="mb-5">
          <label className="block text-sm font-medium text-slate-700 mb-1">CAS PDF File *</label>
          <div
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              file ? 'border-blue-400 bg-blue-50' : 'border-slate-300 hover:border-slate-400'
            }`}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <p className="text-sm font-medium text-blue-700">{file.name} ({(file.size / 1024).toFixed(0)} KB)</p>
            ) : (
              <p className="text-sm text-slate-400">Click to select PDF, or drop here</p>
            )}
          </div>
        </div>

        {uploadMutation.isError && (
          <p className="text-red-600 text-sm mb-3">
            Error: {(uploadMutation.error as Error).message}
          </p>
        )}

        <button
          onClick={() => uploadMutation.mutate()}
          disabled={!file || !memberId || uploadMutation.isPending}
          className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium text-sm
                     hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {uploadMutation.isPending ? 'Uploading…' : 'Upload & Parse'}
        </button>
      </div>

      {/* Upload history */}
      <h2 className="text-lg font-semibold text-slate-800 mb-3">Upload History</h2>
      {existingUploads && existingUploads.length > 0 ? (
        <div className="space-y-3">
          {existingUploads.map((u) => (
            <div key={u.id} className="bg-white rounded-lg border border-slate-200 p-4 flex items-center gap-4">
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-800">{u.original_filename}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {u.cas_type} · {u.statement_month && u.statement_year ? `${u.statement_month}/${u.statement_year}` : 'Unknown period'}
                </p>
              </div>
              <div className="text-right">
                <span className={`text-xs px-2 py-1 rounded font-medium ${statusColor(u.parse_status)}`}>
                  {u.parse_status}
                </span>
                {u.parse_status === 'DONE' && (
                  <p className="text-xs text-slate-400 mt-1">
                    {u.products_created} holdings · {u.transactions_created} txns
                  </p>
                )}
                {u.parse_status === 'ERROR' && (
                  <p className="text-xs text-red-500 mt-1 max-w-xs truncate">{u.parse_error}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-400 text-sm">No uploads yet.</p>
      )}
    </div>
  );
}
