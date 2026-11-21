import { useEffect, useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { useAuth, type OtpChallenge } from "@/lib/auth";

/** Second sign-in step: the 6-digit code that was emailed. Works for sign-in and sign-up (ADR 008). */
export function OtpStep({ first, onBack, onDone }: { first: OtpChallenge; onBack: () => void; onDone: () => void }) {
  const { verifyOtp, resendOtp } = useAuth();
  const [ch, setCh] = useState(first);
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(first.resend_after);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await verifyOtp(ch.challenge, code);
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setNote("");
    try {
      const next = await resendOtp(ch.challenge);
      setCh(next);
      setWait(next.resend_after);
      setCode("");
      setNote("A new code was sent.");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-slate-600">We emailed a 6-digit code to <b className="text-slate-900">{ch.email_hint}</b>. It works for {Math.round(ch.expires_in / 60)} minutes.</p>
      <Field label="Sign-in code">
        <Input
          inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" autoFocus required
          className="text-center text-2xl font-semibold tracking-[0.5em]" placeholder="······"
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        />
      </Field>
      <ErrorNote error={error} />
      {note && <p role="status" className="text-sm text-green-700">{note}</p>}
      <Button type="submit" className="w-full py-2.5" disabled={busy || code.length !== 6}>{busy ? "Checking…" : "Verify and sign in"}</Button>
      <div className="flex items-center justify-between text-sm">
        <button type="button" onClick={onBack} className="font-medium text-slate-600 hover:underline">Back</button>
        <button type="button" onClick={resend} disabled={wait > 0} className="font-medium text-indigo-600 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline">
          {wait > 0 ? `Resend code in ${wait}s` : "Resend code"}
        </button>
      </div>
    </form>
  );
}
