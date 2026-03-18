/**
 * fetchWithAuth — wrapper fetch avec injection du Bearer token NOVA.
 * - Injecte automatiquement Authorization: Bearer <access_token>
 * - Sur 401 : tente un refresh puis relance la requête
 * - Si le refresh échoue : efface les tokens et recharge la page (logout forcé)
 */

const TOKEN_KEY   = 'nova_access_token';
const REFRESH_KEY = 'nova_refresh_token';

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;

  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearTokens();
      return false;
    }

    const data = await response.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

function buildHeaders(options?: RequestInit): HeadersInit {
  const token = getAccessToken();
  return {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function fetchWithAuth(
  url: string,
  options?: RequestInit
): Promise<Response> {
  const init: RequestInit = { ...options, headers: buildHeaders(options) };
  let response = await fetch(url, init);

  if (response.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Relancer avec le nouveau token
      const retryInit: RequestInit = { ...options, headers: buildHeaders(options) };
      response = await fetch(url, retryInit);
    } else {
      // Session expirée — forcer le rechargement (l'AuthContext détectera l'absence de token)
      clearTokens();
      window.location.reload();
    }
  }

  return response;
}
