'use client';
import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { familyMemberApi, FamilyMember } from '../../lib/api';
import api from '../../lib/api';

type ReportFormat = 'PDF' | 'EXCEL';
type ReportType = 'NET_WORTH' | 'HOLDINGS' | 'TRANSACTIONS' | 'FAMILY';

const REPORT_TYPES: { value: ReportType; label: string; desc: string }[] = [
  { value: 'NET_WORTH', label: 'Net Worth Summary', desc: 'Portfolio value, gains, asset allocation' },
  { value: 'HOLDINGS', label: 'Full Holdings', desc: 'All securities with cost, value, and XIRR' },
  { value: 'TRANSACTIONS', label: 'Transaction History', desc: 'All buy/sell/SIP transactions' },
  { value: 'FAMILY', label: 'Family Report', desc: 'Consolidated view across all members' },
];

interface GenerateResponse {
  token: string;
  status: string;
  download_url: string;
}

export default function ReportsPage() {
  const [memberId, setMemberId] = useState<number | ''>('');
  const [reportType, setReportType] = useState<ReportType>('NET_WORTH');
  const [format, setFormat] = useState<ReportFormat>('PDF');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [reportReady, setReportReady] = useState(false);

  const { data: members } = useQuery<FamilyMember[]>({
    queryKey: ['family-members'],
    queryFn: () => familyMemberApi.list().then((r) => r.data),
  });

  // Poll every 3s until report is ready in cache (HEAD request returns 200 when ready)
  useQuery({
    queryKey: ['report-ready', pendingToken],
    queryFn: async () => {
      const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/investments/api';
      const res = await fetch(`${BASE}${downloadUrl}`, { method: 'HEAD', credentials: 'include' });
      if (res.ok) setReportReady(true);
      return res.ok;
    },
    enabled: !!pendingToken && !!downloadUrl && !reportReady,
    refetchInterval: reportReady ? false : 3000,
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      api.post<GenerateResponse>('/reports/generate/', {
        type: format.toLowerCase(),
        report_type: reportType,
        member_id: memberId || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
      }),
    onSuccess: (res) => {
      setPendingToken(res.data.token);
      setDownloadUrl(res.data.download_url);
    },
  });

  const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/investments/api';
  const fullDownloadUrl = downloadUrl ? `${BASE}${downloadUrl}` : null;

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Generate Report</h1>
      <p className="text-slate-400 text-sm mb-8">Download your portfolio as PDF or Excel.</p>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-5">
        {/* Report type */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Report Type</label>
          <div className="grid grid-cols-2 gap-3">
            {REPORT_TYPES.map((rt) => (
              <button
                key={rt.value}
                onClick={() => { setReportType(rt.value); setPendingToken(null); setDownloadUrl(null); }}
                className={`text-left p-3 rounded-lg border transition-colors ${
                  reportType === rt.value
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <p className={`text-sm font-medium ${reportType === rt.value ? 'text-blue-700' : 'text-slate-800'}`}>
                  {rt.label}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{rt.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Format */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Format</label>
          <div className="flex gap-3">
            {(['PDF', 'EXCEL'] as ReportFormat[]).map((f) => (
              <button
                key={f}
                onClick={() => setFormat(f)}
                className={`flex-1 py-2 rounded-lg border text-sm font-medium transition-colors ${
                  format === f
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300'
                }`}
              >
                {f === 'PDF' ? '📄 PDF' : '📊 Excel'}
              </button>
            ))}
          </div>
        </div>

        {/* Member (skip for FAMILY report) */}
        {reportType !== 'FAMILY' && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Family Member <span className="text-slate-400 font-normal">(leave blank for all)</span>
            </label>
            <select
              value={memberId}
              onChange={(e) => setMemberId(Number(e.target.value) || '')}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All members</option>
              {members?.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Date range for transactions */}
        {reportType === 'TRANSACTIONS' && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">From Date</label>
              <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">To Date</label>
              <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
        )}

        {generateMutation.isError && (
          <p className="text-red-600 text-sm">
            Error: {(generateMutation.error as Error).message}
          </p>
        )}

        <button
          onClick={() => { setPendingToken(null); setDownloadUrl(null); setReportReady(false); generateMutation.mutate(); }}
          disabled={generateMutation.isPending}
          className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium text-sm
                     hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {generateMutation.isPending ? 'Queuing…' : `Generate ${format} Report`}
        </button>

        {/* Status / download */}
        {pendingToken && (
          <div className={`rounded-lg p-4 text-center border ${
            reportReady ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'
          }`}>
            {reportReady ? (
              <>
                <p className="text-green-700 text-sm font-medium mb-2">Report ready!</p>
                <a href={fullDownloadUrl!} target="_blank" rel="noreferrer"
                  className="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 inline-block">
                  Download {format}
                </a>
              </>
            ) : (
              <div className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-amber-700 text-sm">Generating report… checking every few seconds</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tips */}
      <div className="mt-6 bg-slate-50 rounded-xl border border-slate-200 p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Report Contents</h2>
        <ul className="space-y-2 text-xs text-slate-500">
          <li><span className="font-medium text-slate-600">Net Worth Summary</span> — Portfolio value, invested value, gains, asset allocation</li>
          <li><span className="font-medium text-slate-600">Full Holdings</span> — All securities, units, NAV/price, cost, current value, XIRR</li>
          <li><span className="font-medium text-slate-600">Transactions</span> — Buy/sell/SIP history, amounts, NAV at transaction</li>
          <li><span className="font-medium text-slate-600">Family Report</span> — Multi-sheet: each member + consolidated summary</li>
        </ul>
      </div>
    </div>
  );
}
