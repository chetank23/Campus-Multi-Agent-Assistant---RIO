/**
 * auth/RoleRoute.tsx
 * ------------------
 * Renders children only if the current user has one of the allowed roles.
 * Otherwise renders the Unauthorized page inline (no extra redirect).
 *
 * Usage:
 *   <RoleRoute roles={['ADMIN']}>
 *     <Outlet />
 *   </RoleRoute>
 */

import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import type { UserRole } from './auth.types';

interface RoleRouteProps {
  roles: UserRole[];
  children: React.ReactNode;
}

export function RoleRoute({ roles, children }: RoleRouteProps) {
  const { user } = useAuth();

  if (!user) return <Navigate to="/login" replace />;

  if (!roles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
}
