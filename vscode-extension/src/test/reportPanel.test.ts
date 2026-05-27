import assert from "node:assert/strict";
import test from "node:test";

import { GatewayClient, type FetchLike, type GatewayFetchResponse } from "../api/client";
import { renderReportHtml, type CapabilityRunReport } from "../webview/reportPanel";

test("renderReportHtml escapes public report content and omits server-only fields", () => {
  const report: CapabilityRunReport & Record<string, unknown> = {
    task_id: "task-<123>",
    status: "completed",
    capability_id: "backend-rbac-review",
    created_at: "2026-05-27T15:00:00Z",
    updated_at: "2026-05-27T15:01:00Z",
    result: {
      summary: "Review <script>alert('x')</script>",
      safe_rationale: "Only public fields & escaped HTML.",
      confidence: "medium",
      findings: [
        {
          severity: "high",
          path: "src/<app>.ts",
          message: "Use escaping before rendering <html>.",
          prompt: "private finding prompt",
          internal: "private finding internal",
          trace: ["private finding trace"],
        },
      ],
      patch: "diff --git a/src/app.ts b/src/app.ts\n+escape(value)\n",
      recommended_tests: ["npm test -- --grep '<report>'"],
      artifacts: [
        "NON_OBJECT_ARTIFACT_SHOULD_NOT_RENDER",
        {
          name: "report.json",
          uri: "artifact://report",
          mime_type: "application/json",
          size: 123,
          sha256: "abc123",
          content: "ARTIFACT_CONTENT_SHOULD_NOT_RENDER",
          body: "ARTIFACT_BODY_SHOULD_NOT_RENDER",
          payload: { value: "ARTIFACT_PAYLOAD_SHOULD_NOT_RENDER" },
          data: "ARTIFACT_DATA_SHOULD_NOT_RENDER",
          internal: "private artifact internal",
          skill_text: "private artifact skill body",
        },
      ],
      internal: "private result internal",
      prompt: "private result prompt",
      skill_text: "private result skill body",
      raw_runner_output: "private raw runner output",
    },
  };

  const html = renderReportHtml(report);

  assert.match(html, /task-&lt;123&gt;/);
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /backend-rbac-review/);
  assert.match(html, /2026-05-27T15:00:00Z/);
  assert.match(html, /2026-05-27T15:01:00Z/);
  assert.match(html, /Review &lt;script&gt;alert\(&#39;x&#39;\)&lt;\/script&gt;/);
  assert.match(html, /src\/&lt;app&gt;\.ts/);
  assert.match(html, /Patch available/);
  assert.match(html, /Preview patch/);
  assert.match(html, /<details>/);
  assert.match(html, /npm test -- --grep &#39;&lt;report&gt;&#39;/);
  assert.match(html, /report\.json/);
  assert.match(html, /artifact:\/\/report/);
  assert.match(html, /application\/json/);
  assert.match(html, /size: 123/);
  assert.match(html, /sha256: abc123/);

  for (const forbidden of [
    "<script>",
    "private",
    "internal",
    "prompt",
    "trace",
    "skill_text",
    "raw_runner_output",
    "ARTIFACT_CONTENT_SHOULD_NOT_RENDER",
    "ARTIFACT_BODY_SHOULD_NOT_RENDER",
    "ARTIFACT_PAYLOAD_SHOULD_NOT_RENDER",
    "ARTIFACT_DATA_SHOULD_NOT_RENDER",
    "NON_OBJECT_ARTIFACT_SHOULD_NOT_RENDER",
  ]) {
    assert.equal(
      html.toLowerCase().includes(forbidden.toLowerCase()),
      false,
      `report html should not include ${forbidden}`,
    );
  }
});

test("renderReportHtml shows queued task metadata without completed result", () => {
  const html = renderReportHtml({
    task_id: "task-queued",
    status: "queued",
  });

  assert.match(html, /task-queued/);
  assert.match(html, /queued/);
  assert.match(html, /No completed result yet/);
});

test("GatewayClient run response can render completed report without private fields", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(200, {
      task_id: "task-client-report",
      status: "completed",
      capability_id: "backend-rbac-review",
      result: {
        summary: "Client result summary",
        findings: [
          {
            severity: "medium",
            path: "src/app.ts",
            message: "Finding from client response",
            internal: "private finding",
          },
        ],
        recommended_tests: ["npm test"],
        artifacts: [
          {
            name: "public-report.json",
            uri: "artifact://public-report",
            content: "ARTIFACT_CONTENT_SHOULD_NOT_RENDER",
          },
        ],
        internal: "private result",
        prompt: "private prompt",
      },
      trace: ["private trace"],
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  const run = await client.runCapability("backend-rbac-review", {
    instruction: "Review",
    client: { type: "vscode" },
  });
  const html = renderReportHtml(run);

  assert.match(html, /task-client-report/);
  assert.match(html, /backend-rbac-review/);
  assert.match(html, /Client result summary/);
  assert.match(html, /Finding from client response/);
  assert.match(html, /npm test/);
  assert.match(html, /public-report\.json/);
  assert.equal(html.includes("private"), false);
  assert.equal(html.includes("ARTIFACT_CONTENT_SHOULD_NOT_RENDER"), false);
});

function jsonResponse(status: number, body: unknown): GatewayFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  };
}
