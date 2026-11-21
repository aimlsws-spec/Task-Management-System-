import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { OtpStep } from "@/components/OtpStep";
import { useAuth, type OtpChallenge } from "@/lib/auth";

export function Login() {
  const { status, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [otp, setOtp] = useState<OtpChallenge | null>(null);

  if (status === "authed") return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
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
          <Input type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@seawindsolution.com" />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
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
