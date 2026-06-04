/**
 * Typed API client for the FailProbe REST API.
 *
 * The TypeScript interfaces below mirror the Pydantic response schemas in
 * `api/schemas.py` exactly. This module is the single source of the base URL
 * and the SWR `fetcher`; pages never construct URLs or parse responses inline.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** SWR fetcher: GETs `${API_BASE}${path}` and returns parsed JSON. */
export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API request failed (${res.status}) for ${path}`);
  }
  return (await res.json()) as T;
}

// --- Response shapes (mirror api/schemas.py) -----------------------------

/** A single agent run (`RunSchema`). */
export interface Run {
  id: string;
  agent_name: string;
  input_text: string;
  output_text: string | null;
  duration_ms: number;
  tokens_used: number | null;
  model: string | null;
  success: boolean;
  failure_type: string | null;
  failure_msg: string | null;
  exception: string | null;
  tags: Record<string, unknown>;
  created_at: string;
}

/** A single tool invocation (`ToolCallSchema`). */
export interface ToolCall {
  id: string;
  run_id: string;
  tool_name: string;
  params: Record<string, unknown>;
  result: string | null;
  duration_ms: number;
  error: string | null;
  timestamp: string;
}

/** An LLM-judge / human evaluation (`EvalResultSchema`). */
export interface EvalResult {
  id: string;
  run_id: string;
  judge_model: string;
  score: number;
  reasoning: string;
  confidence: number;
  human_label: boolean | null;
  human_notes: string | null;
  created_at: string;
}

/** `GET /runs` response (`RunListResponse`). */
export interface RunListResponse {
  total: number;
  runs: Run[];
}

/** `GET /runs/{id}` response (`RunDetailResponse`). */
export interface RunDetailResponse {
  run: Run;
  tool_calls: ToolCall[];
  eval_result: EvalResult | null;
}

/** Per-failure-type aggregate (`FailureBreakdownSchema`). */
export interface FailureBreakdown {
  count: number;
  description: string;
  pct: number;
}

/** `GET /failures/taxonomy` response (`TaxonomyResponse`). */
export interface TaxonomyResponse {
  breakdown: Record<string, FailureBreakdown>;
  total_failures: number;
  total_runs: number;
  failure_rate: number;
}

/** `GET /health` response. */
export interface Health {
  status: string;
  version: string;
}
