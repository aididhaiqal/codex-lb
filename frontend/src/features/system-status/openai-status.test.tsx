import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { OpenAIStatusWidget } from "@/features/system-status/openai-status";
import type { SystemStatus } from "@/features/system-status/schemas";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

const CLEAR_STATUS: SystemStatus = {
  indicator: "none",
  description: "All Systems Operational",
  apiAffected: false,
  apiIndicator: "none",
  apiIncident: null,
  apiComponent: null,
  components: [],
  incidents: [],
  updatedAt: "2026-07-13T12:00:00Z",
  stale: false,
  statusPageUrl: "https://status.openai.com",
};

const CODEX_API_STATUS: SystemStatus = {
  indicator: "major",
  description: "Partial Outage",
  apiAffected: true,
  apiIndicator: "major",
  apiIncident: {
    name: "Elevated errors on the Responses API",
    impact: "major",
    status: "investigating",
    startedAt: "2026-07-13T10:00:00Z",
    shortlink: "https://stspg.io/x",
    affectedComponents: ["Codex API"],
  },
  apiComponent: { name: "Codex API", status: "partial_outage" },
  components: [{ name: "Codex API", status: "partial_outage" }],
  incidents: [
    {
      name: "Elevated errors on the Responses API",
      impact: "major",
      status: "investigating",
      startedAt: "2026-07-13T10:00:00Z",
      shortlink: "https://stspg.io/x",
      affectedComponents: ["Codex API"],
    },
  ],
  updatedAt: "2026-07-13T12:00:00Z",
  stale: false,
  statusPageUrl: "https://status.openai.com",
};

// Overall rollup is degraded, but only ChatGPT-web is affected — codex-lb is fine.
const CHATGPT_ONLY_STATUS: SystemStatus = {
  indicator: "minor",
  description: "Degraded Performance",
  apiAffected: false,
  apiIndicator: "none",
  apiIncident: null,
  apiComponent: null,
  components: [{ name: "Conversations", status: "degraded_performance" }],
  incidents: [
    {
      name: "ChatGPT web is slow",
      impact: "minor",
      status: "investigating",
      startedAt: "2026-07-13T10:00:00Z",
      shortlink: "https://stspg.io/y",
      affectedComponents: ["Conversations"],
    },
  ],
  updatedAt: "2026-07-13T12:00:00Z",
  stale: false,
  statusPageUrl: "https://status.openai.com",
};

function mockSystemStatus(body: SystemStatus): void {
  server.use(http.get("/api/system-status", () => HttpResponse.json(body)));
}

describe("OpenAIStatusWidget", () => {
  it("renders a clear dot when all systems are operational", async () => {
    mockSystemStatus(CLEAR_STATUS);

    renderWithProviders(<OpenAIStatusWidget />);

    const pill = await screen.findByTitle(/All Systems Operational/i);
    expect(pill).toBeInTheDocument();
    expect(pill.querySelector("a")).toBeNull();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders an incident banner when the Codex/API surface is degraded", async () => {
    mockSystemStatus(CODEX_API_STATUS);

    renderWithProviders(<OpenAIStatusWidget />);

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Elevated errors on the Responses API");
    expect(banner).toHaveTextContent("Codex API");
    expect(banner).toHaveTextContent("status.openai.com");
    expect(banner).toHaveAttribute("href", "https://status.openai.com");
  });

  it("shows the clear state (no banner) when only ChatGPT-web is degraded", async () => {
    mockSystemStatus(CHATGPT_ONLY_STATUS);

    renderWithProviders(<OpenAIStatusWidget />);

    const pill = await screen.findByTitle(/OpenAI API:/i);
    expect(pill).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing when the snapshot is stale", async () => {
    mockSystemStatus({ ...CODEX_API_STATUS, stale: true });

    const { container } = renderWithProviders(<OpenAIStatusWidget />);
    await waitFor(() => {
      expect(container.querySelector("a")).not.toBeInTheDocument();
      expect(container.querySelector("span")).not.toBeInTheDocument();
    });
  });
});
