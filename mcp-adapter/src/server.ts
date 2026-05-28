#!/usr/bin/env node
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import * as z from "zod/v4";

import { type AdapterConfig, loadAdapterConfig } from "./config.js";
import { GatewayClient, GatewayClientError, type FetchLike, type JsonObject } from "./gatewayClient.js";
import { redactSensitiveText, redactSensitiveValue, stripServerOnlyFields } from "./security.js";

export const MCP_ADAPTER_SERVER_INFO = {
  name: "skill-capability-mcp-adapter",
  version: "0.1.0",
} as const;

export const PLANNED_F2_TOOL_NAMES = [
  "list_capabilities",
  "run_capability",
  "get_task_status",
  "get_task_result",
  "cancel_task",
] as const;

export interface CreateSkillMcpServerOptions {
  config: AdapterConfig;
  fetch?: FetchLike;
}

export interface CreatedSkillMcpServer {
  server: McpServer;
  gatewayClient: GatewayClient;
  registeredTools: readonly string[];
  plannedTools: readonly string[];
}

export function createSkillMcpServer(
  options: CreateSkillMcpServerOptions,
): CreatedSkillMcpServer {
  const gatewayClient = new GatewayClient({
    gatewayUrl: options.config.gatewayUrl,
    token: options.config.token,
    tenantId: options.config.tenantId,
    fetch: options.fetch,
  });
  const server = new McpServer(MCP_ADAPTER_SERVER_INFO, {
    instructions:
      "Skill Gateway MCP adapter. Use the registered tools to list approved capabilities, start tasks, inspect task state, fetch task results, or cancel tasks.",
  });
  registerSkillGatewayTools(server, gatewayClient);

  return {
    server,
    gatewayClient,
    registeredTools: PLANNED_F2_TOOL_NAMES,
    plannedTools: PLANNED_F2_TOOL_NAMES,
  };
}

function registerSkillGatewayTools(server: McpServer, gatewayClient: GatewayClient): void {
  server.registerTool(
    "list_capabilities",
    {
      description: "Lists approved company capabilities available through the Skill Gateway.",
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async () => safeToolCall(async () => ({
      capabilities: await gatewayClient.listCapabilities(),
    })),
  );

  server.registerTool(
    "run_capability",
    {
      description:
        "Runs an approved company capability on provided workspace context and returns task metadata or a public report.",
      inputSchema: {
        capability_id: z.string().min(1).describe("Capability identifier."),
        request: z.record(z.string(), z.unknown()).describe("Gateway run request body."),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async ({ capability_id, request }) =>
      safeToolCall(async () => gatewayClient.runCapability(capability_id, request)),
  );

  server.registerTool(
    "get_task_status",
    {
      description: "Gets public status metadata for a Skill Gateway task.",
      inputSchema: {
        task_id: z.string().min(1).describe("Task identifier."),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ task_id }) => safeToolCall(async () => gatewayClient.getTaskStatus(task_id)),
  );

  server.registerTool(
    "get_task_result",
    {
      description: "Gets the public result for a completed Skill Gateway task.",
      inputSchema: {
        task_id: z.string().min(1).describe("Task identifier."),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ task_id }) => safeToolCall(async () => gatewayClient.getTaskResult(task_id)),
  );

  server.registerTool(
    "cancel_task",
    {
      description: "Requests cancellation for a Skill Gateway task and returns public task metadata.",
      inputSchema: {
        task_id: z.string().min(1).describe("Task identifier."),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ task_id }) => safeToolCall(async () => gatewayClient.cancelTask(task_id)),
  );
}

async function safeToolCall(callback: () => Promise<unknown>): Promise<CallToolResult> {
  try {
    return publicToolResult(await callback());
  } catch (error) {
    return publicToolError(error);
  }
}

function publicToolResult(value: unknown): CallToolResult {
  const structuredContent = toStructuredContent(value);
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(structuredContent, null, 2),
      },
    ],
    structuredContent,
  };
}

function publicToolError(error: unknown): CallToolResult {
  const publicError = toPublicError(error);
  return {
    isError: true,
    content: [
      {
        type: "text",
        text: JSON.stringify(publicError, null, 2),
      },
    ],
    structuredContent: publicError,
  };
}

function toStructuredContent(value: unknown): JsonObject {
  const publicValue = redactSensitiveValue(stripServerOnlyFields(value));
  if (isJsonObject(publicValue)) {
    return publicValue;
  }
  return { value: publicValue };
}

function toPublicError(error: unknown): JsonObject {
  if (error instanceof GatewayClientError) {
    return toStructuredContent({
      error: {
        status: error.status,
        code: error.code,
        message: "Gateway request failed.",
        details: error.details,
      },
    });
  }

  const message = error instanceof Error
    ? redactSensitiveText(error.message)
    : "MCP tool request failed.";
  return toStructuredContent({
    error: {
      code: "mcp_tool_error",
      message,
    },
  });
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export async function runStdioServer(
  config: AdapterConfig = loadAdapterConfig(),
): Promise<void> {
  const { server } = createSkillMcpServer({ config });
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

export function isEntrypointModule(moduleUrl: string, entrypoint: string | undefined): boolean {
  if (!entrypoint) {
    return false;
  }
  return moduleUrl === pathToFileURL(resolve(entrypoint)).href;
}

function isMainModule(): boolean {
  const entrypoint = process.argv[1];
  return isEntrypointModule(import.meta.url, entrypoint);
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return redactSensitiveText(error.message);
  }
  return "Skill Gateway MCP adapter failed to start.";
}

if (isMainModule()) {
  runStdioServer().catch((error: unknown) => {
    process.stderr.write(`${safeErrorMessage(error)}\n`);
    process.exitCode = 1;
  });
}
