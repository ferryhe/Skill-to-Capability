import assert from "node:assert/strict";
import { resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import {
  MCP_ADAPTER_SERVER_INFO,
  PLANNED_F2_TOOL_NAMES,
  createSkillMcpServer,
  isEntrypointModule,
} from "../server.js";
import { type FetchLike, type GatewayFetchResponse } from "../gatewayClient.js";

test("server module exports stable metadata for the MCP adapter", () => {
  assert.deepEqual(MCP_ADAPTER_SERVER_INFO, {
    name: "skill-capability-mcp-adapter",
    version: "0.1.0",
  });
  assert.deepEqual(PLANNED_F2_TOOL_NAMES, [
    "list_capabilities",
    "run_capability",
    "get_task_status",
    "get_task_result",
    "cancel_task",
  ]);
});

test("createSkillMcpServer constructs without connecting or calling Gateway", () => {
  let fetchCalled = false;
  const created = createSkillMcpServer({
    config: {
      gatewayUrl: "https://gateway.example.com",
      token: "secret-token",
    },
    fetch: async () => {
      fetchCalled = true;
      throw new Error("should not fetch during construction");
    },
  });

  assert.ok(created.server);
  assert.equal(created.gatewayClient.gatewayUrl, "https://gateway.example.com");
  assert.equal(fetchCalled, false);
  assert.deepEqual(created.plannedTools, PLANNED_F2_TOOL_NAMES);
  assert.equal(JSON.stringify(created.gatewayClient).includes("secret-token"), false);
});

test("server registers exactly the five public F2 tools with safe descriptions", async () => {
  await withMcpClient(async ({ client }) => {
    const tools = await client.listTools();

    assert.deepEqual(
      tools.tools.map((tool) => tool.name),
      PLANNED_F2_TOOL_NAMES,
    );
    for (const tool of tools.tools) {
      assert.equal(typeof tool.description, "string");
      assert.doesNotMatch(tool.description ?? "", /workflow|prompt|rubric|runner|skill body|skill_text|trace/i);
    }
  });
});

test("MCP tools call the expected Gateway paths, methods, and request bodies", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url, init) => {
    requests.push({ url: String(url), init });
    if (String(url).endsWith("/v1/capabilities")) {
      return jsonResponse(200, { capabilities: [publicCapability()] });
    }
    if (String(url).endsWith("/v1/capabilities/backend-rbac-review/run")) {
      return jsonResponse(200, {
        task_id: "task-1",
        status: "queued",
        internal: { prompt: "private" },
      });
    }
    if (String(url).endsWith("/v1/tasks/task-1")) {
      return jsonResponse(200, {
        task_id: "task-1",
        status: "running",
        trace: ["private"],
      });
    }
    if (String(url).endsWith("/v1/tasks/task-1/result")) {
      return jsonResponse(200, {
        task_id: "task-1",
        status: "completed",
        summary: "Public summary.",
        raw_runner_output: "private",
      });
    }
    if (String(url).endsWith("/v1/tasks/task-1/cancel")) {
      return jsonResponse(200, {
        task_id: "task-1",
        status: "cancelled",
        skill_text: "private",
      });
    }
    throw new Error(`unexpected URL: ${url}`);
  };

  await withMcpClient(async ({ client }) => {
    await client.callTool({ name: "list_capabilities", arguments: {} });
    await client.callTool({
      name: "run_capability",
      arguments: {
        capability_id: "backend-rbac-review",
        request: { instruction: "Review this.", options: { strictness: "high" } },
        ignored: "must not be forwarded",
      },
    });
    await client.callTool({ name: "get_task_status", arguments: { task_id: "task-1" } });
    await client.callTool({ name: "get_task_result", arguments: { task_id: "task-1" } });
    await client.callTool({ name: "cancel_task", arguments: { task_id: "task-1" } });
  }, fetch);

  assert.equal(requests.length, 5);
  assertRequest(requests[0], "GET", "https://gateway.example.com/v1/capabilities");
  assertRequest(requests[1], "POST", "https://gateway.example.com/v1/capabilities/backend-rbac-review/run", {
    instruction: "Review this.",
    options: { strictness: "high" },
  });
  assertRequest(requests[2], "GET", "https://gateway.example.com/v1/tasks/task-1");
  assertRequest(requests[3], "GET", "https://gateway.example.com/v1/tasks/task-1/result");
  assertRequest(requests[4], "POST", "https://gateway.example.com/v1/tasks/task-1/cancel");
});

test("MCP tool outputs strip server-only fields recursively", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(200, {
      task_id: "task-1",
      status: "completed",
      summary: "Public summary.",
      nested: {
        safe: true,
        internal: { skill_ref: "private" },
        provider: "private-provider",
        modelName: "private-model",
      },
      findings: [
        {
          title: "Public finding",
          prompt: "private prompt",
          trace: ["private trace"],
        },
      ],
    });

  await withMcpClient(async ({ client }) => {
    const result = await client.callTool({
      name: "get_task_result",
      arguments: { task_id: "task-1" },
    });

    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(hasForbiddenKey(result), false);
    assert.deepEqual(result.structuredContent, {
      task_id: "task-1",
      status: "completed",
      summary: "Public summary.",
      nested: { safe: true },
      findings: [{ title: "Public finding" }],
    });
  }, fetch);
});

test("Gateway errors become sanitized MCP tool error results", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(500, {
      error: {
        code: "internal_server_error",
        message: "Failed with Bearer secret-token and private prompt.",
        details: {
          safe: "public detail",
          token: "secret-token",
          internal: { skill_ref: "private skill" },
          raw_runner_output: "private runner output",
        },
      },
    });

  await withMcpClient(async ({ client }) => {
    const result = await client.callTool({
      name: "get_task_status",
      arguments: { task_id: "task-1" },
    });

    assert.equal(result.isError, true);
    assert.equal(JSON.stringify(result).includes("secret-token"), false);
    assert.equal(JSON.stringify(result).includes("private skill"), false);
    assert.equal(JSON.stringify(result).includes("private runner output"), false);
    assert.match(JSON.stringify(result), /\[REDACTED\]/);
    assert.equal(hasForbiddenKey(result), false);
  }, fetch);
});

test("isEntrypointModule matches relative entrypoint paths", () => {
  const entrypointUrl = pathToFileURL(resolve("dist/server.js")).href;

  assert.equal(isEntrypointModule(entrypointUrl, "dist/server.js"), true);
});

async function withMcpClient(
  callback: (context: { client: Client }) => Promise<void>,
  fetch?: FetchLike,
): Promise<void> {
  const created = createSkillMcpServer({
    config: {
      gatewayUrl: "https://gateway.example.com",
      token: "secret-token",
    },
    fetch: fetch ?? (async () => jsonResponse(200, { capabilities: [] })),
  });
  const client = new Client({ name: "test-client", version: "0.1.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await created.server.connect(serverTransport);
  await client.connect(clientTransport);

  try {
    await callback({ client });
  } finally {
    await client.close();
    await created.server.close();
  }
}

function jsonResponse(status: number, body: unknown): GatewayFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  };
}

function publicCapability(): Record<string, unknown> {
  return {
    id: "backend-rbac-review",
    name: "Backend RBAC Review",
    version: "0.1.0",
    visible_description: "Review backend RBAC and public API payload boundaries.",
    input_modes: ["current_file"],
    input_schema: { type: "object" },
    output_schema: { type: "object" },
    client_permissions: { reads_workspace: true },
    approval_policy: { upload_context: "user_confirm_large" },
  };
}

function assertRequest(
  request: { url: string; init?: RequestInit },
  method: string,
  url: string,
  body?: unknown,
): void {
  assert.equal(request.url, url);
  assert.equal(request.init?.method, method);
  if (body === undefined) {
    assert.equal(request.init?.body, undefined);
  } else {
    assert.deepEqual(JSON.parse(String(request.init?.body)), body);
  }
}

function hasForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasForbiddenKey);
  }
  if (value && typeof value === "object") {
    return Object.entries(value).some(([key, nested]) => {
      return [
        "internal",
        "prompt",
        "trace",
        "skill_text",
        "skill_ref",
        "raw_runner_output",
        "provider",
        "modelName",
      ].includes(key) || hasForbiddenKey(nested);
    });
  }
  return false;
}
