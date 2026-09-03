"use client";

import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { useSidebar } from "@/components/layout/SidebarContext";
import { IconChevronRight, IconMenu } from "@/components/ui/icons";

interface TopbarProps {
  title: string;
}

/** Slim sticky utility bar: mobile nav toggle, breadcrumb, theme switch. The
 * page's own heading lives in `PageHeader` within `<main>`. */
export function Topbar({ title }: TopbarProps) {
  const { openMobile } = useSidebar();

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-base-border bg-base/80 px-4 py-4 backdrop-blur-md sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={openMobile}
          aria-label="Open navigation"
          className="-ml-1 flex h-9 w-9 items-center justify-center rounded-lg text-content-secondary hover:bg-base-elevated hover:text-content-primary md:hidden"
        >
          <IconMenu className="h-5 w-5" />
        </button>
        <div className="hidden items-center gap-1.5 text-sm md:flex">
          <span className="text-content-muted">StudyGraph</span>
          <IconChevronRight className="h-3.5 w-3.5 text-content-muted" />
          <span className="font-medium text-content-primary">{title}</span>
        </div>
        <span className="text-sm font-medium text-content-primary md:hidden">{title}</span>
      </div>
      <ThemeToggle />
    </header>
  );
}
