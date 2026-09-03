import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ComponentType, SVGProps } from "react";

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  loading?: boolean;
  accent?: "indigo" | "teal" | "neutral";
}

const ACCENT_CLASSES: Record<NonNullable<StatCardProps["accent"]>, string> = {
  indigo: "bg-accent-indigo/10 text-accent-indigo",
  teal: "bg-accent-teal/10 text-accent-teal",
  neutral: "bg-base-elevated text-content-secondary",
};

export function StatCard({ label, value, icon: Icon, loading = false, accent = "neutral" }: StatCardProps) {
  return (
    <Card className="flex items-center gap-4">
      {Icon && (
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${ACCENT_CLASSES[accent]}`}>
          <Icon className="h-[18px] w-[18px]" />
        </div>
      )}
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-content-muted">{label}</p>
        {loading ? (
          <Skeleton className="mt-2 h-7 w-12 rounded" />
        ) : (
          <p className="mt-1 text-2xl font-semibold tracking-tight text-content-primary">{value}</p>
        )}
      </div>
    </Card>
  );
}
