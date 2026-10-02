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
import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
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
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);

  const neonSession = authClient.useSession();
  const isLoading = neonSession.isPending;

  // Register a per-request token getter so apiService always sends a fresh JWT
  // even if the in-memory token has expired. This also means we don't need to
  // push the token into apiService eagerly — the getter fetches it on demand.
  useEffect(() => {
    if (neonSession.data) {
      apiService.setTokenGetter(async () => {
        try {
          return (await authClient.getJWTToken?.()) ?? neonSession.data?.session?.token ?? null;
        } catch {
          return neonSession.data?.session?.token ?? null;
        }
      });
      const neonUser = neonSession.data.user;
      setUser({ id: neonUser.id, email: neonUser.email, full_name: (neonUser as any).name ?? null });
      // Keep a cached token in state for callers that read it synchronously (e.g. Reports).
      const sessionToken = neonSession.data.session?.token ?? null;
      setToken(sessionToken);
    } else if (!neonSession.isPending) {
      apiService.setTokenGetter(null);
      apiService.setToken(null);
      setToken(null);
      setUser(null);
    }
  }, [neonSession.data, neonSession.isPending]);

  const login = (newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    apiService.setToken(newToken);
  };

  const logout = () => {
    authClient.signOut();
    apiService.setTokenGetter(null);
    apiService.setToken(null);
    setToken(null);
    setUser(null);
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
