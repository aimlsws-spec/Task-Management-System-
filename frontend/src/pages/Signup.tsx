import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input, PasswordInput } from "@/components/ui";
import { OtpStep } from "@/components/OtpStep";
import { useAuth, type OtpChallenge } from "@/lib/auth";

/** New employees create their own account (company email only), then choose department + designation at first login. */
export function Signup() {
  const { status, signup } = useAuth();
  const nav = useNavigate();
  const [otp, setOtp] = useState<OtpChallenge | null>(null);
  const [f, setF] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (status === "authed") return <Navigate to="/" replace />;

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ch = await signup(f); // mails a code; after it, the person lands on the "finish your profile" step
      if (ch) { setOtp(ch); setBusy(false); } else nav("/", { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <AuthLayout title={otp ? "Check your email" : "Create your account"} subtitle={otp ? "Enter the code we emailed to confirm it is you." : "Use your company email. You will choose your department next."}>
      {otp ? <OtpStep first={otp} onBack={() => setOtp(null)} onDone={() => nav("/", { replace: true })} /> : <form onSubmit={submit} className="space-y-4">
        <Field label="Full name"><Input required autoFocus autoComplete="name" value={f.full_name} onChange={set("full_name")} /></Field>
        <Field label="Work email"><Input type="email" required autoComplete="username" value={f.email} onChange={set("email")} /></Field>
        <Field label="Password (10+ chars, upper, lower, digit)">
          <PasswordInput required minLength={10} autoComplete="new-password" value={f.password} onChange={set("password")} />
        </Field>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full py-2.5" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
        <div className="text-center text-sm">
          Already have an account? <Link to="/login" className="font-medium text-indigo-600 hover:underline">Sign in</Link>
        </div>
      </form>}
    </AuthLayout>
  );
}
