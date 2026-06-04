import { Badge } from "@/components/ui/badge";

/** Render a run's success/failure state as a coloured badge. */
export function StatusBadge({ success }: { success: boolean }) {
  return success ? (
    <Badge variant="success">✓ success</Badge>
  ) : (
    <Badge variant="destructive">✗ failure</Badge>
  );
}

/** Render a failure type as an outline badge, or an em dash when absent. */
export function FailureTypeBadge({ failureType }: { failureType: string | null }) {
  if (!failureType) {
    return <span className="text-muted-foreground">—</span>;
  }
  return <Badge variant="outline">{failureType}</Badge>;
}
