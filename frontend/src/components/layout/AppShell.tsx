/**
 * components/layout/AppShell.tsx
 * --------------------------------
 * Responsive enterprise application shell:
 * - Persistent desktop sidebar / slide-over mobile drawer
 * - Fixed academic topbar with page context and profile menu
 * - Structured main content canvas with standard padding
 */

import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export function AppShell({ title }: { title?: string }) {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-[#F4F7FB] text-[#111D35] antialiased selection:bg-primary-100 selection:text-primary-900">
      <Sidebar
        role={user.role}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar
          title={title}
          onToggleMobile={() => setMobileOpen((prev) => !prev)}
        />
        <main className="flex-1 p-4 sm:p-6 lg:p-6 w-full max-w-[1600px] mx-auto overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
