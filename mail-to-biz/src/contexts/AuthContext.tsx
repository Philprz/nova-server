/**
 * NOVA Auth Context
 * Expose : useAuth() → { user, isAuthenticated, login, logout, isLoading }
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { clearTokens, getAccessToken, setTokens } from '@/lib/fetchWithAuth';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface NovaUser {
  user_id:      number;
  sap_username: string;
  society_id:   number;
  sap_company:  string;
  role:         'ADMIN' | 'MANAGER' | 'ADV';
  mailboxes:    { mailbox_id: number; address: string; can_write: boolean }[];
}

interface LoginCredentials {
  sap_company_db: string;
  sap_username:   string;
  sap_password:   string;
}

interface AuthContextValue {
  user:            NovaUser | null;
  isAuthenticated: boolean;
  isLoading:       boolean;
  login:           (credentials: LoginCredentials) => Promise<{ success: boolean; error?: string }>;
  logout:          () => void;
}

// ── Context ────────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]       = useState<NovaUser | null>(null);
  const [isLoading, setLoading] = useState(true);

  // Charger le profil si un token existe déjà (rechargement de page)
  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setLoading(false);
      return;
    }
    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setUser(data ?? null))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const err = await response.json();
        return { success: false, error: err.detail ?? 'Erreur de connexion' };
      }

      const data = await response.json();
      setTokens(data.access_token, data.refresh_token);

      // Charger le profil utilisateur
      const meResp = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (meResp.ok) {
        setUser(await meResp.json());
      }

      return { success: true };
    } catch (e) {
      return { success: false, error: 'Erreur réseau' };
    }
  }, []);

  const logout = useCallback(() => {
    const refreshToken = localStorage.getItem('nova_refresh_token');
    const token = getAccessToken();
    if (refreshToken && token) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => {});
    }
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth doit être utilisé dans un <AuthProvider>');
  return ctx;
}
