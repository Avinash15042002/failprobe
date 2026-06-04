"use client";

import useSWR from "swr";

import { fetcher, type Health } from "@/lib/api";

/** Top bar showing the product name and the live API version from /health. */
export function Topbar() {
  const { data } = useSWR<Health>("/health", fetcher, {
    refreshInterval: 30000,
  });

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-6">
      <span className="text-lg font-semibold tracking-tight">FailProbe</span>
      <span className="text-xs text-muted-foreground">
        {data ? `v${data.version}` : "connecting…"}
      </span>
    </header>
  );
}
