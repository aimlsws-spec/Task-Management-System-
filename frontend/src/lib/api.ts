// HTTP client. The access token lives in memory only (never localStorage); the refresh token is an
// httpOnly cookie managed by the server. On 401 we refresh once (single-flight) and retry.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

// Absolute API origin from VITE_API_BASE_URL (see .env.production); empty = same origin (dev uses the Vite proxy).
// A deployer can change /config.js after the build; the build-time VITE_API_BASE_URL is the fallback.
const runtimeBase = (window as unknown as { __TMS_CONFIG__?: { apiBase?: string } }).__TMS_CONFIG__?.apiBase;
// `npm run dev` always uses the Vite proxy to the local API (http://localhost:8000): config.js is for deployed builds only.
const ORIGIN = import.meta.env.DEV ? "" : (runtimeBase ?? (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/+$/, "");
const BASE = `${ORIGIN}/api/v1`;
/** Shown on the sign-in page so anyone can see which build is running and where it talks to. */
export const BUILD_LABEL = `Build ${__BUILD_ID__} · API ${ORIGIN ? ORIGIN.replace(/^https?:\/\//, "") : "same address"}`;
let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;

export const setAccessToken = (t: string | null) => {
  accessToken = t;
};

// DEV multi-session: when the API runs with TMS_DEV_MULTI_SESSION it returns the refresh token in the body
// instead of a shared cookie, and we keep it in sessionStorage, which is PER TAB. That is what lets several
// roles be signed in at once. In normal (cookie) mode the API never returns it, so this stays unused.
const RT_KEY = "tms_rt";
const readRt = () => {
  try { return sessionStorage.getItem(RT_KEY); } catch { return null; }
};
export const setRefreshToken = (t: string | null) => {
  try { if (t) sessionStorage.setItem(RT_KEY, t); else sessionStorage.removeItem(RT_KEY); } catch { /* storage blocked */ }
};
export const getRefreshToken = readRt;
export const setSessionLostHandler = (fn: () => void) => {
  onSessionLost = fn;
};

async function parse(res: Response) {
  if (res.status === 204) return undefined;
  const text = await res.text();
  let data: { code?: string; message?: string; details?: Record<string, unknown> } | undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    // A web page (or nothing useful) came back instead of the API's JSON: the API address is wrong or the API is down.
    if (res.status === 500) throw new ApiError(500, "SERVER_ERROR", "The server hit an error (500). If you just updated the app, ask your administrator to run the database upgrade (alembic upgrade head).");
    throw new ApiError(res.status || 502, "BAD_RESPONSE", "Cannot reach the API server. Check the API address in config.js or try again in a moment.");
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.code ?? "ERROR", data?.message ?? res.statusText, data?.details ?? {});
  }
  return data;
}

export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const rt = readRt();
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest", ...(rt ? { "Content-Type": "application/json" } : {}) },
        body: rt ? JSON.stringify({ refresh_token: rt }) : undefined,
      });
      if (!res.ok) {
        if (rt) setRefreshToken(null);
        return false;
      }
      const data = await res.json();
      accessToken = data.access_token;
      if (data.refresh_token) setRefreshToken(data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

/** fetch with the bearer token; on 401 refresh once and retry (used for uploads/downloads). */
async function authedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const send = () => fetch(url, { ...init, credentials: "include", headers: { ...(init.headers ?? {}), ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) } });
  let res = await send();
  if (res.status === 401 && (await refreshSession())) res = await send();
  return res;
}

export async function apiUpload<T = unknown>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return parse(await authedFetch(BASE + path, { method: "POST", body: form })) as Promise<T>;
}

/** Downloads a protected file (needs the Authorization header, so a plain link cannot be used). */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await authedFetch(BASE + path);
  if (!res.ok) await parse(res);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; params?: Record<string, string | number | undefined | null> } = {},
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.params ?? {})) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  const send = () =>
    fetch(url, {
      method: opts.method ?? (opts.body ? "POST" : "GET"),
      credentials: "include",
      headers: {
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  let res: Response;
  try {
    res = await send();
  } catch {
    // fetch itself failed: no network, wrong API address, or the server does not allow this website's address (CORS).
    throw new ApiError(0, "NETWORK", "Cannot reach the API server (no connection, wrong address, or this website address is not allowed by the server). Check config.js and TMS_CORS_ORIGINS.");
  }
  if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/refresh")) {
    if (await refreshSession()) res = await send();
    else {
      accessToken = null;
      onSessionLost?.();
    }
  }
  return parse(res) as Promise<T>;
}
