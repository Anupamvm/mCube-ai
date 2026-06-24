export function formatINR(value: number | string): string {
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(n)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatPct(value: number | string | undefined): string {
  if (value === undefined || value === null) return '—';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export function gainClass(value: number | string): string {
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (n > 0) return 'text-green-600';
  if (n < 0) return 'text-red-600';
  return 'text-slate-500';
}

export const ASSET_COLORS: Record<string, string> = {
  EQUITY: '#3b82f6',
  MUTUAL_FUND: '#8b5cf6',
  SGB: '#f59e0b',
  FD: '#10b981',
  REAL_ESTATE: '#ef4444',
  PPF: '#06b6d4',
  EPF: '#0ea5e9',
  NPS: '#6366f1',
  PHYSICAL_GOLD: '#d97706',
  BOND: '#64748b',
  SAVINGS: '#84cc16',
  OTHER: '#94a3b8',
};

export const PRODUCT_TYPE_LABELS: Record<string, string> = {
  MUTUAL_FUND: 'Mutual Fund',
  EQUITY: 'Equity',
  FD: 'Fixed Deposit',
  RD: 'Recurring Deposit',
  SGB: 'Sovereign Gold Bond',
  BOND: 'Bond',
  PPF: 'PPF',
  EPF: 'EPF',
  NPS: 'NPS',
  REAL_ESTATE: 'Real Estate',
  PHYSICAL_GOLD: 'Physical Gold',
  CRYPTO: 'Crypto',
  CASH: 'Cash',
  SAVINGS: 'Savings',
  OTHER: 'Other',
};
