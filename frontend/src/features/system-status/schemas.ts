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
  indicator: z.string(),
  description: z.string(),
  components: z.array(SystemStatusComponentSchema),
  incidents: z.array(SystemStatusIncidentSchema),
  updatedAt: z.string().nullable().optional(),
  stale: z.boolean(),
  statusPageUrl: z.string(),
});

export type SystemStatus = z.infer<typeof SystemStatusSchema>;
export type SystemStatusIncident = z.infer<typeof SystemStatusIncidentSchema>;

export const DEGRADED_INDICATORS = new Set(["minor", "major", "critical"]);
