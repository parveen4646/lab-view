import React, { createContext, useContext, useState, ReactNode } from 'react';
import { apiService } from '@/services/api';

interface User {
  id: string;
  email: string;
  full_name: string | null;
}

interface AuthContextType {
  token: string | null;
  user: User | null;
  login: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function readStoredUser(): User | null {
  try {
    const raw = localStorage.getItem('auth_user');
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

function readStoredToken(): string | null {
  try {
    const stored = localStorage.getItem('auth_token');
    if (stored) {
      // Sync the api service token on initial load — runs synchronously
      // before any component renders, so API calls made at mount have the token.
      apiService.setToken(stored);
    }
    return stored;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(readStoredToken);
  const [user, setUser] = useState<User | null>(readStoredUser);

  const login = (newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    apiService.setToken(newToken);
    try {
      localStorage.setItem('auth_token', newToken);
      localStorage.setItem('auth_user', JSON.stringify(newUser));
    } catch {
      // localStorage may be unavailable in some private-browsing environments
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    apiService.setToken(null);
    try {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
    } catch {
      // localStorage may be unavailable
    }
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
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
