import { get } from "@/lib/api-client";

import { SystemStatusSchema } from "@/features/system-status/schemas";

const SYSTEM_STATUS_PATH = "/api/system-status";

export function getSystemStatus() {
  return get(SYSTEM_STATUS_PATH, SystemStatusSchema);
}
