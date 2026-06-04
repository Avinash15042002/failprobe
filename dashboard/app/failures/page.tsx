"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import useSWR from "swr";

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
import { fetcher, type TaxonomyResponse } from "@/lib/api";

export default function FailuresPage() {
  const { data } = useSWR<TaxonomyResponse>("/failures/taxonomy", fetcher, {
    refreshInterval: 5000,
  });

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">Loading failure analytics…</p>
    );
  }

  // Sorted, descending, only types that have actually occurred — for the chart.
  const ranked = Object.entries(data.breakdown)
    .map(([type, info]) => ({ type, ...info }))
    .sort((a, b) => b.count - a.count);
  const occurred = ranked.filter((row) => row.count > 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Failure analytics
      </h1>

      <Card>
        <CardHeader>
          <CardTitle>Failure type distribution</CardTitle>
          <CardDescription>
            {data.total_failures} failures across {data.total_runs} runs
          </CardDescription>
        </CardHeader>
        <CardContent>
          {occurred.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No failures recorded yet.
            </p>
          ) : (
            <ResponsiveContainer
              width="100%"
              height={Math.max(160, occurred.length * 40)}
            >
              <BarChart
                data={occurred}
                layout="vertical"
                margin={{ left: 24, right: 56, top: 8, bottom: 8 }}
              >
                <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="type"
                  width={180}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value: number, _name, item) => [
                    `${value} (${item.payload.pct}%)`,
                    "count",
                  ]}
                />
                <Bar dataKey="count" fill="hsl(var(--destructive))" radius={[0, 4, 4, 0]}>
                  <LabelList
                    dataKey="count"
                    position="right"
                    formatter={(value: number) => `${value}`}
                    style={{ fontSize: 12 }}
                  />
                  {occurred.map((row) => (
                    <Cell key={row.type} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Taxonomy</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Failure type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Count</TableHead>
                <TableHead className="text-right">% of runs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranked.map((row) => {
                const pctOfRuns = data.total_runs
                  ? ((row.count / data.total_runs) * 100).toFixed(1)
                  : "0.0";
                return (
                  <TableRow key={row.type}>
                    <TableCell className="font-medium">{row.type}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.description}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.count}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {pctOfRuns}%
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
