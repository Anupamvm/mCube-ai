'use client';
import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import { productApi } from '../../../../lib/api';

type ProductType = 'FD' | 'RD' | 'PPF' | 'EPF' | 'NPS' | 'REAL_ESTATE' | 'PHYSICAL_GOLD' | 'BOND' | 'SAVINGS' | 'OTHER';

const PRODUCT_TYPES: { value: ProductType; label: string; icon: string }[] = [
  { value: 'FD', label: 'Fixed Deposit', icon: '🏦' },
  { value: 'RD', label: 'Recurring Deposit', icon: '📅' },
  { value: 'PPF', label: 'PPF', icon: '🏛️' },
  { value: 'EPF', label: 'EPF / PF', icon: '👷' },
  { value: 'NPS', label: 'NPS', icon: '🎯' },
  { value: 'REAL_ESTATE', label: 'Real Estate', icon: '🏠' },
  { value: 'PHYSICAL_GOLD', label: 'Physical Gold', icon: '🪙' },
  { value: 'BOND', label: 'Bond', icon: '📜' },
  { value: 'SAVINGS', label: 'Savings / Cash', icon: '💰' },
  { value: 'OTHER', label: 'Other', icon: '📦' },
];

// ── Shared helpers ────────────────────────────────────────────────────────────
const INPUT = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent';

type OnChange = (patch: Record<string, string>) => void;

function Field({ label, type = 'text', step, name, onChange }: {
  label: string; type?: string; step?: string; name: string;
  onChange: OnChange;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <input
        type={type}
        step={step}
        className={INPUT}
        onChange={(e) => onChange({ [name]: e.target.value })}
      />
    </div>
  );
}

function SelectField({ label, name, options, onChange }: {
  label: string; name: string;
  options: { value: string; label: string }[];
  onChange: OnChange;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <select className={INPUT} onChange={(e) => onChange({ [name]: e.target.value })}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

// ── Sub-forms ────────────────────────────────────────────────────────────────

function FDForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Principal Amount (₹) *" type="number" name="principal" onChange={onChange} />
      <Field label="Interest Rate (% p.a.) *" type="number" step="0.01" name="interest_rate" onChange={onChange} />
      <SelectField label="Compounding" name="compounding" onChange={onChange}
        options={[
          { value: 'quarterly', label: 'Quarterly' },
          { value: 'monthly', label: 'Monthly' },
          { value: 'annually', label: 'Annually' },
          { value: 'simple', label: 'Simple Interest' },
        ]} />
      <Field label="Bank / Institution" name="bank_name" onChange={onChange} />
      <Field label="Start Date" type="date" name="start_date" onChange={onChange} />
      <Field label="Maturity Date" type="date" name="maturity_date" onChange={onChange} />
      <Field label="FD Number (optional)" name="fd_number" onChange={onChange} />
    </div>
  );
}

function RDForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Monthly Instalment (₹) *" type="number" name="monthly_amount" onChange={onChange} />
      <Field label="Interest Rate (% p.a.) *" type="number" step="0.01" name="interest_rate" onChange={onChange} />
      <Field label="Tenure (months) *" type="number" name="tenure_months" onChange={onChange} />
      <Field label="Bank Name" name="bank_name" onChange={onChange} />
      <Field label="Start Date" type="date" name="start_date" onChange={onChange} />
    </div>
  );
}

function PPFForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Current Balance (₹) *" type="number" name="balance" onChange={onChange} />
      <Field label="Annual Contribution (₹)" type="number" name="annual_contribution" onChange={onChange} />
      <Field label="Account Number" name="account_number" onChange={onChange} />
      <Field label="Financial Year (e.g. 2024-25)" name="financial_year" onChange={onChange} />
    </div>
  );
}

function EPFForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Current Balance (₹) *" type="number" name="balance" onChange={onChange} />
      <Field label="UAN" name="uan" onChange={onChange} />
      <Field label="Employer Name" name="employer_name" onChange={onChange} />
      <Field label="Employee Contribution (₹)" type="number" name="employee_contribution" onChange={onChange} />
      <Field label="Employer Contribution (₹)" type="number" name="employer_contribution" onChange={onChange} />
      <Field label="VPF Contribution (₹)" type="number" name="vpf_contribution" onChange={onChange} />
    </div>
  );
}

function NPSForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Current Corpus (₹) *" type="number" name="corpus" onChange={onChange} />
      <Field label="PRAN" name="pran" onChange={onChange} />
      <SelectField label="Tier" name="tier" onChange={onChange}
        options={[{ value: '1', label: 'Tier 1' }, { value: '2', label: 'Tier 2' }]} />
      <Field label="Scheme Preference (e.g. LC50)" name="scheme_preference" onChange={onChange} />
    </div>
  );
}

function RealEstateForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <SelectField label="Property Type" name="property_type" onChange={onChange}
        options={[
          { value: 'FLAT', label: 'Flat / Apartment' },
          { value: 'VILLA', label: 'Villa / Independent House' },
          { value: 'PLOT', label: 'Plot / Land' },
          { value: 'COMMERCIAL', label: 'Commercial' },
        ]} />
      <Field label="Location / Address" name="location" onChange={onChange} />
      <Field label="Area (sq ft)" type="number" name="area_sqft" onChange={onChange} />
      <Field label="Purchase Price (₹)" type="number" name="purchase_price" onChange={onChange} />
      <Field label="Purchase Date" type="date" name="purchase_date" onChange={onChange} />
      <Field label="Current Estimated Value (₹) *" type="number" name="estimated_value" onChange={onChange} />
      <Field label="Loan Outstanding (₹)" type="number" name="loan_outstanding" onChange={onChange} />
      <Field label="Monthly Rental Income (₹)" type="number" name="monthly_rental" onChange={onChange} />
    </div>
  );
}

function GoldForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Quantity (grams) *" type="number" step="0.01" name="quantity_grams" onChange={onChange} />
      <SelectField label="Purity" name="purity" onChange={onChange}
        options={[
          { value: '24K', label: '24K (999)' },
          { value: '22K', label: '22K (916)' },
          { value: '18K', label: '18K (750)' },
        ]} />
      <Field label="Purchase Price / gram (₹)" type="number" name="purchase_price_per_gram" onChange={onChange} />
      <SelectField label="Form" name="form" onChange={onChange}
        options={[
          { value: 'JEWELLERY', label: 'Jewellery' },
          { value: 'COIN', label: 'Coin' },
          { value: 'BAR', label: 'Bar' },
        ]} />
    </div>
  );
}

function BondForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Units / Bonds held *" type="number" name="units" onChange={onChange} />
      <Field label="Face Value per bond (₹)" type="number" name="face_value" onChange={onChange} />
      <Field label="Purchase Price per bond (₹)" type="number" name="purchase_price" onChange={onChange} />
      <Field label="Coupon Rate (% p.a.)" type="number" step="0.01" name="coupon_rate" onChange={onChange} />
      <SelectField label="Coupon Frequency" name="coupon_frequency" onChange={onChange}
        options={[
          { value: 'annual', label: 'Annual' },
          { value: 'semi-annual', label: 'Semi-annual' },
          { value: 'quarterly', label: 'Quarterly' },
          { value: 'monthly', label: 'Monthly' },
        ]} />
      <Field label="Maturity Date" type="date" name="maturity_date" onChange={onChange} />
    </div>
  );
}

function SavingsForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Balance (₹) *" type="number" name="balance" onChange={onChange} />
      <Field label="Account Number (last 4 digits)" name="account_number" onChange={onChange} />
    </div>
  );
}

function OtherForm({ onChange }: { onChange: OnChange }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Field label="Current Value (₹) *" type="number" name="balance" onChange={onChange} />
      <Field label="Invested Amount (₹)" type="number" name="invested" onChange={onChange} />
    </div>
  );
}

const FORM_MAP: Record<ProductType, React.FC<{ onChange: OnChange }>> = {
  FD: FDForm, RD: RDForm, PPF: PPFForm, EPF: EPFForm, NPS: NPSForm,
  REAL_ESTATE: RealEstateForm, PHYSICAL_GOLD: GoldForm, BOND: BondForm,
  SAVINGS: SavingsForm, OTHER: OtherForm,
};

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AddProductPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const router = useRouter();

  const [productType, setProductType] = useState<ProductType>('FD');
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [extraData, setExtraData] = useState<Record<string, string>>({});

  const updateExtra = (patch: Record<string, string>) =>
    setExtraData((prev) => ({ ...prev, ...patch }));

  const saveMutation = useMutation({
    mutationFn: () =>
      productApi.create(accountId, {
        product_type: productType,
        name: name || productType,
        notes,
        extra_data: extraData,
        data_source: 'MANUAL',
      }),
    onSuccess: () => router.push(`/account/${accountId}`),
  });

  const SubForm = FORM_MAP[productType];

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <button onClick={() => router.back()} className="text-slate-400 hover:text-slate-600 text-sm mb-4">
        ← Back
      </button>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Add Holding Manually</h1>

      {/* Type selector */}
      <div className="mb-6">
        <p className="text-sm font-medium text-slate-700 mb-2">Holding Type</p>
        <div className="grid grid-cols-5 gap-2">
          {PRODUCT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => { setProductType(t.value); setExtraData({}); }}
              className={`flex flex-col items-center gap-1 p-3 rounded-xl border text-xs font-medium transition-colors ${
                productType === t.value
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300'
              }`}
            >
              <span className="text-xl">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Name / Label</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. SBI FD — 7% 2yr, Flat in Pune"
            className={INPUT}
          />
        </div>

        <div>
          <p className="text-sm font-medium text-slate-700 mb-3">Details</p>
          <SubForm onChange={updateExtra} />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Notes (optional)</label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className={INPUT}
            placeholder="Any additional information"
          />
        </div>

        {saveMutation.isError && (
          <p className="text-red-600 text-sm">Error: {(saveMutation.error as Error).message}</p>
        )}

        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium text-sm
                     hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saveMutation.isPending ? 'Saving…' : 'Save Holding'}
        </button>
      </div>
    </div>
  );
}
