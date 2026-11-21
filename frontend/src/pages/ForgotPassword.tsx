import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/forgot-password", { body: { email } });
      setSent(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthLayout title="Reset your password" subtitle="We'll email you a link if the account exists.">
      {sent ? (
        <p className="text-sm text-slate-600">If that account exists, a reset link has been sent. Check your email.</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Work email">
            <Input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" className="w-full py-2.5">Send reset link</Button>
        </form>
      )}
      <div className="mt-5 text-center text-sm">
        <Link to="/login" className="font-medium text-indigo-600 hover:underline">Back to sign in</Link>
      </div>
    </AuthLayout>
  );
}
