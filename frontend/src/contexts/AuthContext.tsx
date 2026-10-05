/**
 * AuthContext — thin bridge between Neon Auth and the rest of the app.
 *
 * The `useAuth()` hook surface (token, user, login, logout) is unchanged so
 * Dashboard, Reports, Upload, etc. need no edits.
 *
 * Auth state is driven by authClient.useSession() (nanostores — no provider
 * needed).  Whenever the session changes (sign-in, sign-out, token refresh),
 * we pull a fresh JWT and push it into apiService so subsequent API calls
 * carry the updated Bearer header automatically.
 */
import React, { createContext, useContext, useEffect, ReactNode } from 'react';
import { authClient } from '@/lib/neon';
import { apiService } from '@/services/api';

interface User {
  id: string;
  email: string;
  full_name: string | null;
}

interface AuthContextType {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const neonSession = authClient.useSession();
  const isLoading = neonSession.isPending;

  // Derived directly from neonSession on every render — not copied into
  // separate useState — so `user`/`token` are never one render behind
  // `isLoading` flipping. That lag previously let a consumer see
  // `isLoading === false` together with a stale `user === null` (or vice
  // versa) for one frame, which caused incorrect redirect decisions.
  const sessionData = neonSession.data;
  const user: User | null = sessionData
    ? {
        id: sessionData.user.id,
        email: sessionData.user.email,
        full_name: (sessionData.user as any).name ?? null,
      }
    : null;
  const token: string | null = sessionData?.session?.token ?? null;

  // Register a per-request token getter so apiService always sends a fresh JWT
  // even if the in-memory token has expired. This also means we don't need to
  // push the token into apiService eagerly — the getter fetches it on demand.
  // This remains a useEffect because it's an imperative side effect on a
  // singleton, not a value this component renders.
  useEffect(() => {
    if (sessionData) {
      apiService.setTokenGetter(async () => {
        try {
          const { data } = await authClient.token();
          return data?.token ?? sessionData.session?.token ?? null;
        } catch {
          return sessionData.session?.token ?? null;
        }
      });
    } else if (!isLoading) {
      apiService.setTokenGetter(null);
      apiService.setToken(null);
    }
  }, [sessionData, isLoading]);

  // No longer called anywhere (Login now goes through authClient directly,
  // and user/token are derived from the Neon session above) — kept only so
  // the AuthContextType surface doesn't change for any other caller.
  const login = (newToken: string, _newUser: User) => {
    apiService.setToken(newToken);
  };

  const logout = () => {
    authClient.signOut();
    apiService.setTokenGetter(null);
    apiService.setToken(null);
    try {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
    } catch {
      // localStorage may be unavailable
    }
  };

  return (
    <AuthContext.Provider value={{ token, user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
