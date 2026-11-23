import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { OtpStep } from "@/components/OtpStep";
import { useAuth, type OtpChallenge } from "@/lib/auth";

export function Login() {
  const { status, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState(() => {
    try { return localStorage.getItem("tms_remembered_email") || ""; } catch { return ""; }
  });
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [otp, setOtp] = useState<OtpChallenge | null>(null);

  if (status === "authed") return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (rememberMe) {
        try { localStorage.setItem("tms_remembered_email", email.trim().toLowerCase()); } catch { /* ignore */ }
      } else {
        try { localStorage.removeItem("tms_remembered_email"); } catch { /* ignore */ }
      }
      const ch = await login(email, password);
      if (ch) setOtp(ch);
      else nav("/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title={otp ? "Check your email" : "Welcome back"} subtitle={otp ? "One more step to keep your account safe." : "Sign in to the SeaWind Task Management System."}>
      {otp ? <OtpStep first={otp} onBack={() => { setOtp(null); setPassword(""); }} onDone={() => nav("/", { replace: true })} /> : <form onSubmit={submit} className="space-y-4">
        <Field label="Work email">
          <Input id="email" name="email" type="email" autoComplete="username" required autoFocus={!email} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@seawindsolution.com" />
        </Field>
        <Field label="Password">
          <Input id="password" name="password" type="password" autoComplete="current-password" required autoFocus={!!email} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span>Remember me on this device</span>
          </label>
        </div>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full py-2.5" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <div className="text-center text-sm">
          <Link to="/forgot-password" className="font-medium text-indigo-600 hover:underline">Forgot password?</Link>
        </div>
        <div className="border-t border-slate-100 pt-4 text-center text-sm text-slate-600">
          New to SeaWind? <Link to="/signup" className="font-medium text-indigo-600 hover:underline">Create your account</Link>
        </div>
      </form>}
    </AuthLayout>
  );
}
