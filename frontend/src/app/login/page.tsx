"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle } from "@/components/ui/icons";
import { AuthShell } from "@/components/auth/AuthShell";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { useAuth } from "@/components/auth/AuthProvider";
import { ApiError } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    const nextFieldErrors: Record<string, string> = {};
    if (!email.trim()) nextFieldErrors.email = "Email is required.";
    if (!password) nextFieldErrors.password = "Password is required.";
    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length) return;

    setSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        setFormError(err.fieldErrors ? null : err.message);
      } else {
        setFormError("Something went wrong. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      description="Log in to continue building your knowledge graph."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-accent-indigo hover:underline">
            Register
          </Link>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <GoogleButton />

        <div className="flex items-center gap-3" aria-hidden="true">
          <div className="h-px flex-1 bg-base-border" />
          <span className="text-xs font-medium uppercase tracking-wide text-content-muted">
            Or
          </span>
          <div className="h-px flex-1 bg-base-border" />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-5" noValidate>
        <Input
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          error={fieldErrors.email}
        />
        <PasswordInput
          label="Password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          error={fieldErrors.password}
        />

        {formError && (
          <p className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 text-xs text-danger">
            <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {formError}
          </p>
        )}

        <Button
          type="submit"
          loading={submitting}
          className="mt-1 w-full shadow-lg shadow-accent-indigo/20 transition-shadow hover:shadow-accent-indigo/30"
        >
          Log in
        </Button>
      </form>
    </AuthShell>
  );
}
