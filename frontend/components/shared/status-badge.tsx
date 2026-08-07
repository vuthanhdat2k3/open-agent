import { Badge, type BadgeProps } from "@/components/ui/badge";

const variants: Record<string, BadgeProps["variant"]> = {
  active: "success",
  connected: "success",
  complete: "success",
  completed: "success",
  success: "success",
  pending: "warning",
  queued: "warning",
  running: "info",
  failed: "destructive",
  error: "destructive",
  rejected: "destructive",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const normalized = status.toLowerCase();
  return <Badge variant={variants[normalized] ?? "outline"} className={className}>{status}</Badge>;
}
