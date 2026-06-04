import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names and de-conflict Tailwind utilities. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Render an ISO timestamp as a coarse "x ago" string (e.g. "3m ago"). */
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Truncate a string to `n` characters, appending an ellipsis when clipped. */
export function truncate(value: string | null | undefined, n = 200): string {
  if (!value) return "";
  return value.length > n ? `${value.slice(0, n)}…` : value;
}
