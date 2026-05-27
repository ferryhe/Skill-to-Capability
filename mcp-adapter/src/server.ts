#!/usr/bin/env node
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { type AdapterConfig, loadAdapterConfig } from "./config.js";
import { GatewayClient, type FetchLike } from "./gatewayClient.js";
import { redactSensitiveText } from "./security.js";

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
      "Skill Gateway MCP adapter skeleton. Capability tools are planned for the next implementation scope.",
  });

  return {
    server,
    gatewayClient,
    plannedTools: PLANNED_F2_TOOL_NAMES,
  };
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
