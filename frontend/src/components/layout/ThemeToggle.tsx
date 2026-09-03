"use client";

import { useTheme } from "@/components/layout/ThemeProvider";
import { IconMoon, IconSun } from "@/components/ui/icons";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-base-border text-content-secondary transition-colors hover:border-accent-teal/50 hover:text-content-primary"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {isDark ? <IconSun className="h-4 w-4" /> : <IconMoon className="h-4 w-4" />}
    </button>
  );
}
