import { z } from "zod";

export const SystemStatusComponentSchema = z.object({
  name: z.string(),
  status: z.string(),
});

export const SystemStatusIncidentSchema = z.object({
  name: z.string(),
  impact: z.string(),
  status: z.string(),
  startedAt: z.string().nullable().optional(),
  shortlink: z.string().nullable().optional(),
  affectedComponents: z.array(z.string()),
});

export const SystemStatusSchema = z.object({
  // Overall Statuspage rollup across all OpenAI surfaces — informational only.
  indicator: z.string(),
  description: z.string(),
  // API/Codex-scoped signal (excludes ChatGPT-web surfaces). The dashboard keys
  // its banner on these, not on the overall rollup.
  apiAffected: z.boolean(),
  apiIndicator: z.string(),
  apiIncident: SystemStatusIncidentSchema.nullable().optional(),
  apiComponent: SystemStatusComponentSchema.nullable().optional(),
  components: z.array(SystemStatusComponentSchema),
  incidents: z.array(SystemStatusIncidentSchema),
  updatedAt: z.string().nullable().optional(),
  stale: z.boolean(),
  statusPageUrl: z.string(),
});

export type SystemStatus = z.infer<typeof SystemStatusSchema>;
export type SystemStatusIncident = z.infer<typeof SystemStatusIncidentSchema>;
export type SystemStatusComponent = z.infer<typeof SystemStatusComponentSchema>;

export const CRITICAL_INDICATORS = new Set(["major", "critical"]);
