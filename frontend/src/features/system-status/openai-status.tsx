import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink } from "lucide-react";

import { getSystemStatus } from "@/features/system-status/api";
import { CRITICAL_INDICATORS } from "@/features/system-status/schemas";
import { cn } from "@/lib/utils";

export function OpenAIStatusWidget() {
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: getSystemStatus,
    refetchInterval: 60_000,
    staleTime: 60_000,
    retry: false,
  });

  const status = query.data;
  // Nothing trustworthy to show: no snapshot yet or a stale snapshot. Stay
  // invisible rather than assert a state we don't know.
  if (!status || status.stale) {
    return null;
  }

  // Key on API/Codex-scoped degradation, not the overall rollup: a
  // ChatGPT-web-only incident does not affect codex-lb, so show the clear state.
  if (!status.apiAffected) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
        title={`OpenAI API: ${status.description || "All Systems Operational"}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
        OpenAI
      </span>
    );
  }

  const incident = status.apiIncident ?? null;
  const critical = CRITICAL_INDICATORS.has(status.apiIndicator);
  const title = incident?.name || "OpenAI API service degradation";
  const component = status.apiComponent?.name ?? incident?.affectedComponents[0] ?? null;

  return (
    <a
      href={status.statusPageUrl}
      target="_blank"
      rel="noreferrer"
      role="status"
      title={`Open OpenAI status page — ${title}`}
      className={cn(
        "inline-flex max-w-md items-start gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
        critical
          ? "border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/15"
          : "border-amber-500/20 bg-amber-500/10 text-amber-700 hover:bg-amber-500/15 dark:text-amber-300",
      )}
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0">
        <span className="font-semibold">OpenAI API incident: </span>
        <span>{title}</span>
        {component ? <span className="opacity-80"> · {component}</span> : null}
        <span className="ml-1 inline-flex items-center gap-0.5 whitespace-nowrap underline underline-offset-2">
          status.openai.com
          <ExternalLink className="h-3 w-3" aria-hidden />
        </span>
      </span>
    </a>
  );
}
