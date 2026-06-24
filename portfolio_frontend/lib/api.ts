import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/investments/api';

const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

// Reads the CSRF token from the csrftoken cookie (set by Django on any GET).
// Falls back to window.INVESTMENTS_CONFIG.csrfToken when embedded in the Django template.
function getCsrfToken(): string {
  if (typeof document === 'undefined') return '';
  const cookieMatch = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (cookieMatch) return cookieMatch[1];
  return (window as unknown as { INVESTMENTS_CONFIG?: { csrfToken?: string } })
    .INVESTMENTS_CONFIG?.csrfToken ?? '';
}

api.interceptors.request.use((config) => {
  const method = (config.method ?? '').toLowerCase();
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const token = getCsrfToken();
    if (token) config.headers['X-CSRFToken'] = token;
  }
  return config;
});

export default api;

// ── Types ──────────────────────────────────────────────────────────────────────

export interface FamilyMember {
  id: number;
  name: string;
  relationship: string;
  pan_masked: string;
  date_of_birth?: string;
}

export interface InvestmentAccount {
  id: number;
  account_name: string;
  account_type: string;
  institution_name: string;
  is_active: boolean;
  family_member: number;
}

export interface InvestmentProduct {
  id: number;
  name: string;
  isin: string;
  product_type: string;
  invested_value: string;
  current_value: string;
  gain_loss: string;
  xirr?: string;
  as_of_date?: string;
  investment_account: number;
  extra_data: Record<string, unknown>;
}

export interface CASUpload {
  id: number;
  family_member: number;
  cas_type: string;
  original_filename: string;
  parse_status: string;
  parse_error: string;
  statement_month?: number;
  statement_year?: number;
  accounts_created: number;
  products_created: number;
  transactions_created: number;
  created_at: string;
}

export interface PortfolioSnapshot {
  id: number;
  snapshot_date: string;
  total_invested: string;
  current_value: string;
  gain_loss: string;
  gain_loss_pct: string;
  xirr?: string;
  asset_allocation: Record<string, number>;
  net_worth_breakdown: Record<string, number>;
}

// ── API helpers ────────────────────────────────────────────────────────────────

export const familyMemberApi = {
  list: () => api.get<FamilyMember[]>('/family-members/'),
  create: (data: Partial<FamilyMember>) => api.post<FamilyMember>('/family-members/', data),
  get: (id: number) => api.get<FamilyMember>(`/family-members/${id}/`),
  update: (id: number, data: Partial<FamilyMember>) =>
    api.put<FamilyMember>(`/family-members/${id}/`, data),
  delete: (id: number) => api.delete(`/family-members/${id}/`),
  netWorth: (id: number) => api.get(`/family-members/${id}/net-worth/`),
};

export const accountApi = {
  list: (memberId?: number) =>
    api.get<InvestmentAccount[]>('/accounts/', {
      params: memberId ? { member_id: memberId } : {},
    }),
  create: (data: Partial<InvestmentAccount>) =>
    api.post<InvestmentAccount>('/accounts/', data),
  get: (id: number) => api.get<InvestmentAccount>(`/accounts/${id}/`),
};

export const productApi = {
  list: (params?: Record<string, string | number>) =>
    api.get<InvestmentProduct[]>('/products/', { params }),
  create: (accountId: number, data: Record<string, unknown>) =>
    api.post<InvestmentProduct>(`/accounts/${accountId}/products/add/`, data),
};

export const uploadApi = {
  uploadCAS: (formData: FormData) =>
    api.post<CASUpload>('/uploads/cas/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  listCAS: (memberId?: number) =>
    api.get<CASUpload[]>('/uploads/cas/', {
      params: memberId ? { member_id: memberId } : {},
    }),
  getCAS: (id: number) => api.get<CASUpload>(`/uploads/cas/${id}/`),
};

export const analyticsApi = {
  updatePrices: (memberIds?: number[]) =>
    api.post('/analytics/update-prices/', memberIds ? { member_ids: memberIds } : {}),
  consolidated: (memberIds: number[]) =>
    api.get('/portfolio/consolidated/', {
      params: { member_ids: memberIds.join(',') },
    }),
};
