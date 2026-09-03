"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ToastStack } from "@/components/ui/Toast";
import { useToast } from "@/lib/hooks/useToast";
import { useAuth } from "@/components/auth/AuthProvider";
import { EditProfileDialog } from "@/components/settings/EditProfileDialog";
import { ApiError } from "@/lib/api/client";
import type { UserUpdateInput } from "@/lib/types/auth";
import { IconCalendar, IconEdit, IconLogout, IconSun, IconUser } from "@/components/ui/icons";

function getInitials(name: string | null, email: string): string {
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/);
    const first = parts[0]?.[0] ?? "";
    const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
    return (first + last).toUpperCase();
  }
  return email[0]?.toUpperCase() ?? "?";
}

function formatJoinDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

export default function SettingsPage() {
  const router = useRouter();
  const { user, isLoading, logout, updateProfile } = useAuth();
  const { toasts, push, dismiss } = useToast();
  const [editOpen, setEditOpen] = useState(false);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  async function handleProfileSave(payload: UserUpdateInput) {
    try {
      await updateProfile(payload);
      setEditOpen(false);
      push("Profile updated.");
    } catch (err) {
      // Re-throw so EditProfileDialog can show the inline field/form error
      // and keep the modal open -- only surface a toast for success.
      if (err instanceof ApiError) throw err;
      push("Couldn't update your profile. Try again.", "error");
      throw err;
    }
  }

  const displayName = user?.name?.trim() || null;

  return (
    <>
      <Topbar title="Settings" />
      <main className="mx-auto flex w-full max-w-2xl animate-fade-in flex-col gap-8 p-6 sm:p-8 lg:p-10">
        <PageHeader
          title="Settings"
          description="Manage your profile, appearance, and account for StudyGraph."
        />

        {/* Profile */}
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Profile</h2>
            <p className="text-xs text-content-muted">How you appear across StudyGraph.</p>
          </div>

          <Card>
            {isLoading ? (
              <div className="flex items-center gap-4">
                <Skeleton className="h-12 w-12 rounded-full" />
                <div className="flex flex-1 flex-col gap-2">
                  <Skeleton className="h-3.5 w-32" />
                  <Skeleton className="h-3 w-44" />
                </div>
              </div>
            ) : user ? (
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent-teal to-accent-indigo text-base font-semibold text-white">
                    {getInitials(user.name, user.email)}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-content-primary">
                      {displayName ?? "Add your name"}
                    </p>
                    <p className="truncate text-xs text-content-muted">{user.email}</p>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  onClick={() => setEditOpen(true)}
                  className="shrink-0 self-start sm:self-auto"
                >
                  <IconEdit className="h-3.5 w-3.5" />
                  Edit profile
                </Button>
              </div>
            ) : (
              <p className="text-sm text-content-muted">
                We couldn&apos;t load your profile. Try refreshing the page.
              </p>
            )}
          </Card>
        </section>

        {/* Appearance */}
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Appearance</h2>
            <p className="text-xs text-content-muted">Choose how StudyGraph looks on this device.</p>
          </div>

          <Card className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-base-elevated text-content-secondary">
                <IconSun className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-content-primary">Theme</p>
                <p className="text-xs text-content-muted">Switch between light and dark mode.</p>
              </div>
            </div>
            <ThemeToggle />
          </Card>
        </section>

        {/* Account */}
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Account</h2>
            <p className="text-xs text-content-muted">Details tied to your StudyGraph account.</p>
          </div>

          <Card className="flex flex-col divide-y divide-base-border p-0">
            <div className="flex items-center justify-between gap-4 px-5 py-3.5">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-base-elevated text-content-secondary">
                  <IconUser className="h-3.5 w-3.5" />
                </div>
                <span className="text-sm text-content-secondary">Email</span>
              </div>
              {isLoading ? (
                <Skeleton className="h-3.5 w-40" />
              ) : (
                <span className="truncate text-sm font-medium text-content-primary">
                  {user?.email ?? "—"}
                </span>
              )}
            </div>
            <div className="flex items-center justify-between gap-4 px-5 py-3.5">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-base-elevated text-content-secondary">
                  <IconCalendar className="h-3.5 w-3.5" />
                </div>
                <span className="text-sm text-content-secondary">Member since</span>
              </div>
              {isLoading ? (
                <Skeleton className="h-3.5 w-28" />
              ) : (
                <span className="text-sm font-medium text-content-primary">
                  {user ? formatJoinDate(user.createdAt) : "—"}
                </span>
              )}
            </div>
          </Card>
        </section>

        {/* Logout */}
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Log out</h2>
            <p className="text-xs text-content-muted">Sign out of StudyGraph on this device.</p>
          </div>

          <Card className="flex items-center justify-between gap-4 border-danger/20">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger/10 text-danger">
                <IconLogout className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-content-primary">End your session</p>
                <p className="text-xs text-content-muted">
                  You&apos;ll need to sign in again to access your account.
                </p>
              </div>
            </div>
            <Button variant="danger" onClick={handleLogout}>
              Log out
            </Button>
          </Card>
        </section>
      </main>

      {editOpen && user && (
        <EditProfileDialog
          user={user}
          onClose={() => setEditOpen(false)}
          onSubmit={handleProfileSave}
        />
      )}

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </>
  );
}
