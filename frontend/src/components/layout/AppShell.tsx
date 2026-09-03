"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";

const NO_CHROME_ROUTES = ["/login", "/register"];

/** Hides the app sidebar on unauthenticated routes (login/register) -- those
 * pages own their own full-bleed, centered layout instead of the app shell. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (NO_CHROME_ROUTES.includes(pathname ?? "")) {
    return <div className="flex min-h-screen min-w-0 flex-1 flex-col">{children}</div>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
