'use client';
import './globals.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_LINKS = [
  { href: '/', label: 'Dashboard', exact: true },
  { href: '/upload', label: 'Upload CAS' },
  { href: '/portfolio/consolidated', label: 'Consolidated' },
  { href: '/analytics', label: 'Overlap' },
  { href: '/groups', label: 'Groups' },
  { href: '/reports', label: 'Reports' },
  { href: '/settings/family', label: 'Family' },
];

function NavBar() {
  const path = usePathname();
  const isActive = (href: string, exact?: boolean) =>
    exact ? path === href : path === href || path.startsWith(href + '/');
  return (
    <nav className="bg-slate-900 text-white px-6 py-3 flex items-center gap-6 shadow-md">
      <span className="font-bold text-lg text-blue-400">Family Portfolio</span>
      <div className="flex gap-4 ml-4">
        {NAV_LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`text-sm px-3 py-1 rounded transition-colors ${
              isActive(l.href, l.exact)
                ? 'bg-blue-600 text-white'
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/investments/api';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient());

  // Bootstrap the CSRF cookie from Django on first mount.
  useEffect(() => {
    fetch(`${BASE}/csrf/`, { credentials: 'include' }).catch(() => {});
  }, []);

  return (
    <html lang="en">
      <body>
        <QueryClientProvider client={qc}>
          <NavBar />
          <main className="min-h-screen bg-slate-50">{children}</main>
        </QueryClientProvider>
      </body>
    </html>
  );
}
