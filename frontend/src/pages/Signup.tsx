import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input, PasswordInput, Select } from "@/components/ui";
import { OtpStep } from "@/components/OtpStep";
import { useAuth, type OtpChallenge } from "@/lib/auth";
import { api } from "@/lib/api";

type PublicCompany = { id: number; name: string; code: string; logo_url: string | null };

/** New employees create their own account, selecting their company. Leadership (CEO/Owner) must approve before access is granted. */
export function Signup() {
  const { status, signup } = useAuth();
  const nav = useNavigate();
  const [otp, setOtp] = useState<OtpChallenge | null>(null);
  const [companies, setCompanies] = useState<PublicCompany[]>([]);
  const [f, setF] = useState({ full_name: "", email: "", password: "", company_id: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let ignore = false;
    api<PublicCompany[]>("/companies/public")
      .then((data) => {
        if (!ignore && data && data.length > 0) {
          setCompanies(data);
          setF((prev) => (prev.company_id ? prev : { ...prev, company_id: String(data[0].id) }));
        }
      })
      .catch((e) => console.error("Failed to load companies for signup:", e));
    return () => {
      ignore = true;
    };
  }, []);

  if (status === "authed") return <Navigate to="/" replace />;

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ch = await signup({
        full_name: f.full_name,
        email: f.email,
        password: f.password,
        company_id: f.company_id ? Number(f.company_id) : undefined,
      });
      if (ch) {
        setOtp(ch);
        setBusy(false);
      } else {
        nav("/", { replace: true });
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title={otp ? "Check your email" : "Create your account"}
      subtitle={
        otp
          ? "Enter the code we emailed to confirm it is you."
          : "Select your company to request access. Leadership will review and approve your account."
      }
    >
      {otp ? (
        <OtpStep first={otp} onBack={() => setOtp(null)} onDone={() => nav("/", { replace: true })} />
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Company to join">
            <Select
              required
              value={f.company_id}
              onChange={set("company_id")}
              className="w-full"
            >
              <option value="" disabled>Select your company…</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.code.toUpperCase()})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Full name">
            <Input required autoFocus autoComplete="name" value={f.full_name} onChange={set("full_name")} />
          </Field>
          <Field label="Work email">
            <Input type="email" required autoComplete="username" value={f.email} onChange={set("email")} />
          </Field>
          <Field label="Password (10+ chars, upper, lower, digit)">
            <PasswordInput required minLength={10} autoComplete="new-password" value={f.password} onChange={set("password")} />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" className="w-full py-2.5" disabled={busy}>
            {busy ? "Submitting join request…" : "Request to Join Team"}
          </Button>
          <div className="text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-indigo-600 hover:underline">
              Sign in
            </Link>
          </div>
        </form>
      )}
    </AuthLayout>
  );
}
