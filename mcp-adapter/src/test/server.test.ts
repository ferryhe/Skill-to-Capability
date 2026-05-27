import assert from "node:assert/strict";
import { resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  MCP_ADAPTER_SERVER_INFO,
  PLANNED_F2_TOOL_NAMES,
  createSkillMcpServer,
  isEntrypointModule,
} from "../server.js";

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

test("isEntrypointModule matches relative entrypoint paths", () => {
  const entrypointUrl = pathToFileURL(resolve("dist/server.js")).href;

  assert.equal(isEntrypointModule(entrypointUrl, "dist/server.js"), true);
});
