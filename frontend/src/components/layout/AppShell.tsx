/**
 * components/layout/AppShell.tsx
 * --------------------------------
 * Responsive application shell: sidebar + topbar + scrollable content area.
 * The sidebar is hidden on mobile (hamburger menu can be added in Stage 6B+).
 */

import { Outlet } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export function AppShell({ title }: { title?: string }) {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar role={user.role} />
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar title={title} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
