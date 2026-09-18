/**
 * auth.types.ts
 * -------------
 * TypeScript types that mirror the actual backend schemas from:
 *   backend/schemas/auth.py  — LoginRequest, TokenResponse, UserResponse
 *   backend/models/identity.py — role constraint: 'ADMIN' | 'FACULTY' | 'STUDENT'
 */

/** The three roles enforced by the database CHECK constraint. */
export type UserRole = 'ADMIN' | 'FACULTY' | 'STUDENT';

/** POST /auth/login request body */
export interface LoginRequest {
  email: string;
  password: string;
}

/** POST /auth/login response body */
export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
}

/**
 * GET /auth/me response body.
 * Matches UserResponse pydantic schema exactly.
 */
export interface UserResponse {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  department_id: number | null;
}

/** Shape of auth context exposed to the rest of the application. */
export interface AuthContextValue {
  user: UserResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
}

/** Generic API error shape from FastAPI / our error handler. */
export interface ApiError {
  detail: string | { msg: string; type: string }[];
}
