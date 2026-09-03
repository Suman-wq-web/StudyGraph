import type { ReactNode } from "react";

interface AuthShellProps {
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}

/**
 * Shared chrome for the login/register pages: brand lockup, an ambient
 * background glow, and a centered glass card. Only used by those two pages,
 * so it's free to diverge from the standard `Card`/`PageHeader` treatment
 * used inside the authenticated app shell.
 */
export function AuthShell({ title, description, children, footer }: AuthShellProps) {
  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden px-4 py-12 sm:px-6">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-40 left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-accent-teal/10 blur-[110px] dark:bg-accent-teal/20"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-48 right-1/2 h-[26rem] w-[26rem] translate-x-1/2 rounded-full bg-accent-indigo/10 blur-[110px] dark:bg-accent-indigo/20"
      />

      <div className="relative w-full max-w-[26rem] animate-fade-in">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-teal to-accent-indigo text-base font-bold text-white shadow-lg shadow-accent-indigo/25">
            SG
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-sm font-semibold tracking-tight text-content-primary">
              StudyGraph
            </span>
            <span className="text-xs text-content-muted">
              Your personal learning knowledge graph
            </span>
          </div>
        </div>

        <div className="animate-scale-in rounded-3xl border border-base-border/80 bg-base-surface/70 p-7 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/40 sm:p-9">
          <div className="mb-7 flex flex-col gap-1.5 text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-content-primary">{title}</h1>
            <p className="text-sm leading-relaxed text-content-secondary">{description}</p>
          </div>
          {children}
        </div>

        <p className="mt-6 text-center text-sm text-content-secondary">{footer}</p>
      </div>
    </main>
  );
}
