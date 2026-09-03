"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { ApiError } from "@/lib/api/client";
import { IconAlertTriangle } from "@/components/ui/icons";
import { cn } from "@/lib/utils/cn";

interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleIdServices {
  initialize: (config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdServices } };
  }
}

const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

// Module-level so every GoogleButton instance (Login + Register can both be
// visited in one session) shares a single script load instead of injecting
// the tag twice.
let gisScriptPromise: Promise<void> | null = null;

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (gisScriptPromise) return gisScriptPromise;

  gisScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GIS_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      gisScriptPromise = null;
      reject(new Error("Failed to load Google Sign-In."));
    };
    document.head.appendChild(script);
  });
  return gisScriptPromise;
}

type Status = "loading" | "ready" | "exchanging" | "unavailable";

/**
 * Renders Google's own "Continue with Google" button via Google Identity
 * Services -- the official widget (real G logo, Google-hosted popup), not a
 * custom lookalike. On success, hands the ID token it returns to
 * AuthProvider.loginWithGoogle, which exchanges it for a StudyGraph session
 * through the exact same token-storage/user-state path `login`/`register`
 * use, then redirects to /dashboard. Fully self-contained (owns its own
 * loading/error UI) so Login/Register only need to render it -- no changes
 * to their existing form/state.
 */
export function GoogleButton() {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (!clientId || !containerRef.current) {
      setStatus("unavailable");
      return;
    }
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => {
            setError(null);
            setStatus("exchanging");
            loginWithGoogle(response.credential)
              .then(() => router.push("/dashboard"))
              .catch((err) => {
                setStatus("ready");
                setError(
                  err instanceof ApiError ? err.message : "Couldn't sign in with Google. Try again."
                );
              });
          },
        });
        window.google.accounts.id.renderButton(containerRef.current, {
          type: "standard",
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: "continue_with",
          logo_alignment: "left",
          width: Math.min(400, Math.max(220, containerRef.current.offsetWidth || 320)),
        });
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("unavailable");
          setError("Couldn't load Google Sign-In right now.");
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  // No client ID configured -- omit the option entirely rather than show a
  // broken/dead button (see backend/.env.example, frontend/.env.local.example).
  if (status === "unavailable" && !error) return null;

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className={cn(
          "flex w-full justify-center",
          status === "loading" && "h-11 animate-pulse rounded-full bg-base-elevated",
          status === "exchanging" && "pointer-events-none opacity-60 transition-opacity"
        )}
      />
      {status === "exchanging" && (
        <p className="text-center text-xs text-content-muted">Signing in with Google...</p>
      )}
      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 text-xs text-danger">
          <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}
