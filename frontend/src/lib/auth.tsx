import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getRefreshToken, refreshSession, setAccessToken, setRefreshToken, setSessionLostHandler } from "./api";

export type Me = {
  user: { id: number; email: string; timezone: string; must_change_password: boolean };
  employee: { id: number; employee_code: string; full_name: string; job_title: string | null; department_id: number; status: string;
    company_id?: number; company_name?: string | null;
    department?: string | null; head?: { id: number; full_name: string } | null; reports_to?: { id: number; full_name: string } | null; qa?: { id: number; full_name: string } | null } | null;
  roles: string[];
  rank: number;
  permissions: Record<string, "self" | "team" | "department" | "organization">;
};

/** Step 1 of an OTP sign-in: the password was right and a 6-digit code was emailed (ADR 008). */
export type OtpChallenge = { otp_required: true; challenge: string; email_hint: string; expires_in: number; resend_after: number };
type Session = { access_token: string; refresh_token?: string };

type AuthState = {
  status: "loading" | "anon" | "authed";
  me: Me | null;
  /** Resolves to null when signed in (code switched off), or to the challenge when a code must be entered. */
  login: (email: string, password: string) => Promise<OtpChallenge | null>;
  signup: (body: { full_name: string; email: string; password: string; company_id?: number; department_id?: number }) => Promise<OtpChallenge | null>;
  verifyOtp: (challenge: string, code: string) => Promise<void>;
  resendOtp: (challenge: string) => Promise<OtpChallenge>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  can: (permission: string) => boolean;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const queryClient = useQueryClient();

  const reload = useCallback(async () => {
    const data = await api<Me>("/auth/me");
    setMe(data);
    setStatus("authed");
  }, []);

  useEffect(() => {
    setSessionLostHandler(() => {
      setMe(null);
      setStatus("anon");
      queryClient.clear(); // session expired for good: stop every poll
    });
    (async () => {
      if (await refreshSession()) {
        try {
          await reload();
          return;
        } catch {
          /* fall through */
        }
      }
      setStatus("anon");
    })();
  }, [reload, queryClient]);

  const start = useCallback(
    async (res: Session | OtpChallenge): Promise<OtpChallenge | null> => {
      if ("otp_required" in res) return res;
      setAccessToken(res.access_token);
      setRefreshToken(res.refresh_token ?? null); // only present in dev multi-session mode
      await reload();
      return null;
    },
    [reload],
  );
  const login = useCallback(
    async (email: string, password: string) => start(await api<Session | OtpChallenge>("/auth/login", { body: { email, password } })),
    [start],
  );
  const signup = useCallback(
    async (body: { full_name: string; email: string; password: string; company_id?: number }) => {
      const r = await api<Session | OtpChallenge | { message: string }>("/auth/signup", { body });
      // Code switched off: the account exists, sign in with the password as before.
      if ("message" in r) return start(await api<Session | OtpChallenge>("/auth/login", { body: { email: body.email, password: body.password } }));
      return start(r);
    },
    [start],
  );
  const verifyOtp = useCallback(async (challenge: string, code: string) => {
    await start(await api<Session>("/auth/verify-otp", { body: { challenge, code } }));
  }, [start]);
  const resendOtp = useCallback((challenge: string) => api<OtpChallenge>("/auth/resend-otp", { body: { challenge } }), []);

  const logout = useCallback(async () => {
    try {
      const rt = getRefreshToken();
      await api("/auth/logout", { method: "POST", body: rt ? { refresh_token: rt } : undefined });
    } finally {
      setRefreshToken(null);
      setAccessToken(null);
      setMe(null);
      setStatus("anon");
      queryClient.clear(); // cancels every poll and forgets the previous user's data
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({ status, me, login, signup, verifyOtp, resendOtp, logout, reload, can: (p) => !!me && p in me.permissions }),
    [status, me, login, signup, verifyOtp, resendOtp, logout, reload],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

/** UI convenience only: the backend is the authority on every action. */
export function Can({ permission, children }: { permission: string; children: ReactNode }) {
  return useAuth().can(permission) ? <>{children}</> : null;
}
