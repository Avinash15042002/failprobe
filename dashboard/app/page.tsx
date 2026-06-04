"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";

import {
  FailureTypeBadge,
  StatusBadge,
} from "@/components/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetcher,
  type RunListResponse,
  type TaxonomyResponse,
} from "@/lib/api";
import { timeAgo } from "@/lib/utils";

/** Pick the failure type with the highest count, or null when there are none. */
function mostCommonFailure(taxonomy: TaxonomyResponse | undefined): string | null {
  if (!taxonomy) return null;
  let best: string | null = null;
  let bestCount = 0;
  for (const [type, info] of Object.entries(taxonomy.breakdown)) {
    if (info.count > bestCount) {
      best = type;
      bestCount = info.count;
    }
  }
  return bestCount > 0 ? best : null;
}

export default function OverviewPage() {
  const router = useRouter();
  const { data: runList } = useSWR<RunListResponse>("/runs?limit=50", fetcher, {
    refreshInterval: 5000,
  });
  const { data: taxonomy } = useSWR<TaxonomyResponse>(
    "/failures/taxonomy",
    fetcher,
    { refreshInterval: 5000 },
  );

  const totalRuns = taxonomy?.total_runs ?? runList?.total ?? 0;
  const failureRatePct = taxonomy
    ? (taxonomy.failure_rate * 100).toFixed(1)
    : "—";
  const topFailure = mostCommonFailure(taxonomy);
  const runs = runList?.runs ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total runs</CardDescription>
            <CardTitle className="text-3xl">{totalRuns}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Failure rate</CardDescription>
            <CardTitle className="text-3xl">{failureRatePct}%</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Most common failure</CardDescription>
            <CardTitle className="text-2xl">{topFailure ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Run history</CardTitle>
        </CardHeader>
        <CardContent>
          {totalRuns === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No runs yet. Add <code className="font-mono">@probe</code> to your
              agent to get started.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Failure type</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/runs/${run.id}`)}
                  >
                    <TableCell className="font-medium">
                      {run.agent_name}
                    </TableCell>
                    <TableCell>
                      <StatusBadge success={run.success} />
                    </TableCell>
                    <TableCell>
                      <FailureTypeBadge failureType={run.failure_type} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Math.round(run.duration_ms)} ms
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {timeAgo(run.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
