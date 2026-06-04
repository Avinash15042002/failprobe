"use client";

import { useParams } from "next/navigation";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import useSWR from "swr";

import { FailureTypeBadge, StatusBadge } from "@/components/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { fetcher, type RunDetailResponse } from "@/lib/api";
import { truncate } from "@/lib/utils";

/** A single labelled detail field in the run header. */
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </p>
      <div className="text-sm">{value}</div>
    </div>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const { data, error } = useSWR<RunDetailResponse>(
    params.id ? `/runs/${params.id}` : null,
    fetcher,
    { refreshInterval: 5000 },
  );

  if (error) {
    return (
      <p className="text-sm text-destructive">
        Failed to load run {params.id}.
      </p>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Loading run…</p>;
  }

  const { run, tool_calls, eval_result } = data;
  const timeline = tool_calls.map((tc) => ({
    name: tc.tool_name,
    duration_ms: Math.round(tc.duration_ms),
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {run.agent_name}
        </h1>
        <StatusBadge success={run.success} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Input" value={truncate(run.input_text, 200)} />
          <Field
            label="Output"
            value={truncate(run.output_text, 200) || "—"}
          />
          <Field
            label="Duration"
            value={`${Math.round(run.duration_ms)} ms`}
          />
          <Field label="Model" value={run.model ?? "—"} />
          <Field
            label="Tags"
            value={
              Object.keys(run.tags).length
                ? JSON.stringify(run.tags)
                : "—"
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trace timeline</CardTitle>
          <CardDescription>Tool call durations (ms)</CardDescription>
        </CardHeader>
        <CardContent>
          {timeline.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No tool calls recorded.
            </p>
          ) : (
            <ResponsiveContainer
              width="100%"
              height={Math.max(120, timeline.length * 44)}
            >
              <BarChart
                data={timeline}
                layout="vertical"
                margin={{ left: 24, right: 24, top: 8, bottom: 8 }}
              >
                <XAxis type="number" unit="ms" tick={{ fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={140}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value: number) => [`${value} ms`, "duration"]}
                />
                <Bar
                  dataKey="duration_ms"
                  fill="hsl(var(--primary))"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {!run.success && (
        <Card>
          <CardHeader>
            <CardTitle>Failure</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FailureTypeBadge failureType={run.failure_type} />
            {run.failure_msg && (
              <p className="text-sm">{run.failure_msg}</p>
            )}
            {run.exception && (
              <details className="rounded-md border bg-muted/40 p-3">
                <summary className="cursor-pointer text-sm font-medium">
                  Raw exception
                </summary>
                <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">
                  {run.exception}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {eval_result && (
        <Card>
          <CardHeader>
            <CardTitle>Evaluation</CardTitle>
            <CardDescription>
              Judge: {eval_result.judge_model}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-3">
              <Progress value={eval_result.score * 100} className="max-w-xs" />
              <span className="text-sm font-medium tabular-nums">
                {(eval_result.score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              {eval_result.reasoning}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
