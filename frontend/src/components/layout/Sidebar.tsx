"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils/cn";
import { useSidebar } from "@/components/layout/SidebarContext";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  IconChat,
  IconDashboard,
  IconGraph,
  IconLibrary,
  IconLogout,
  IconPath,
  IconSettings,
} from "@/components/ui/icons";
import type { ComponentType, SVGProps } from "react";

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: IconDashboard },
  { href: "/library", label: "Resource Library", icon: IconLibrary },
  { href: "/graph", label: "Knowledge Graph", icon: IconGraph },
  { href: "/chat", label: "AI Assistant", icon: IconChat },
  { href: "/recommendations", label: "Learning Path", icon: IconPath },
];

const SECONDARY_NAV_ITEMS: NavItem[] = [{ href: "/settings", label: "Settings", icon: IconSettings }];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { mobileOpen, closeMobile } = useSidebar();
  const { logout } = useAuth();

  const handleLogout = () => {
    closeMobile();
    logout();
    router.push("/login");
  };

  const navLink = (item: NavItem) => {
    const active = pathname?.startsWith(item.href);
    const ItemIcon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={closeMobile}
        aria-current={active ? "page" : undefined}
        className={cn(
          "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
          active
            ? "bg-accent-indigo/10 text-accent-indigo"
            : "text-content-secondary hover:bg-base-elevated hover:text-content-primary"
        )}
      >
        {active && (
          <span className="absolute left-0 top-1/2 h-5 -translate-y-1/2 rounded-r-full bg-accent-indigo" style={{ width: 3 }} />
        )}
        <ItemIcon
          className={cn(
            "h-[18px] w-[18px] shrink-0 transition-colors",
            active ? "text-accent-indigo" : "text-content-muted group-hover:text-content-primary"
          )}
        />
        <span className="truncate">{item.label}</span>
      </Link>
    );
  };

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 animate-fade-in-backdrop bg-black/40 md:hidden"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-base-border bg-base-surface px-3 py-5 transition-transform duration-200 ease-out",
          "md:static md:z-auto md:w-60 md:translate-x-0 md:bg-base-surface/60 md:backdrop-blur-sm",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-6 flex items-center gap-2.5 px-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-accent-teal to-accent-indigo text-xs font-bold text-white">
            SG
          </div>
          <span className="text-sm font-semibold tracking-tight text-content-primary">
            StudyGraph
          </span>
        </div>

        <nav className="flex flex-1 flex-col gap-1">{NAV_ITEMS.map(navLink)}</nav>

        <div className="flex flex-col gap-1 border-t border-base-border pt-3">
          {SECONDARY_NAV_ITEMS.map(navLink)}
          <button
            type="button"
            onClick={handleLogout}
            className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-content-secondary transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <IconLogout className="h-[18px] w-[18px] shrink-0 text-content-muted transition-colors group-hover:text-danger" />
            <span className="truncate">Log out</span>
          </button>
        </div>
      </aside>
    </>
  );
}
