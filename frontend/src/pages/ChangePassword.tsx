import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api, setAccessToken, setRefreshToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Shown instead of the app while `must_change_password` is true (the API also enforces this). */
export function ChangePassword() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/change-password", { body: { current_password: current, new_password: next } });
      // All sessions were revoked server-side; sign in again with the new password.
      setAccessToken(null);
      setRefreshToken(null);
      await logout();
      nav("/login", { replace: true });
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthLayout
      title="Set a new password"
      subtitle={me?.user.must_change_password ? "You must change your temporary password before continuing." : "Choose a new password."}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Current password">
          <Input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password (10+ chars, upper, lower, digit)">
          <Input type="password" autoComplete="new-password" required minLength={10} value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full py-2.5">Change password</Button>
      </form>
    </AuthLayout>
  );
}
