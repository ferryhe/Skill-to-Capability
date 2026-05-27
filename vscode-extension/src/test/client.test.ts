import assert from "node:assert/strict";
import Module from "node:module";
import test from "node:test";

import {
  GatewayClient,
  GatewayClientError,
  type FetchLike,
  type GatewayFetchResponse,
} from "../api/client";

const publicKeys = new Set([
  "id",
  "name",
  "version",
  "category",
  "visible_description",
  "input_modes",
  "input_schema",
  "output_schema",
  "client_permissions",
  "approval_policy",
  "security",
]);

const serverOnlyKeys = new Set([
  "internal",
  "model_policy",
  "prompt",
  "skill_ref",
  "trace",
  "skill_text",
]);

test("listCapabilities returns public fields and strips leakage fields", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url: string | URL, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, {
      capabilities: [
        {
          id: "backend-rbac-review",
          name: "Backend RBAC Review",
          version: "0.1.0",
          category: "code-review",
          visible_description: "Review backend RBAC and public API payload boundaries.",
          input_modes: ["current_file", "git_diff"],
          input_schema: {
            type: "object",
            properties: {
              instruction: { type: "string" },
              prompt: { type: "string" },
              skill_ref: { type: "string" },
            },
            internal: { validator: "server-only" },
            model_policy: "server-only",
          },
          output_schema: {
            type: "object",
            properties: {
              summary: { type: "string" },
              skill_text: { type: "string" },
              model_policy: { type: "string" },
            },
          },
          client_permissions: {
            reads_workspace: true,
            writes_workspace: "optional",
            runs_commands: "optional",
            sends_code_to_server: true,
          },
          approval_policy: {
            upload_context: "user_confirm_large",
            apply_patch: "user_confirm",
            run_commands: "user_confirm",
          },
          security: {
            max_files: 20,
            max_total_input_bytes: 300000,
          },
          internal: { skill_ref: "private-skill" },
          skill_ref: "private-skill",
          model_policy: "high_reasoning",
          prompt: "private prompt",
          trace: ["private trace"],
          skill_text: "private skill body",
          extra_server_field: "not public",
        },
      ],
    });
  };

  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com/",
    fetch,
  });

  const capabilities = await client.listCapabilities();

  assert.equal(requests[0].url, "https://gateway.example.com/v1/capabilities");
  assert.equal(capabilities.length, 1);
  assert.equal(hasForbiddenKey(capabilities[0]), false);
  for (const key of Object.keys(capabilities[0])) {
    assert.equal(publicKeys.has(key), true, `${key} should not be returned`);
  }
});

test("listCapabilities strips normalized and pattern-based server-only fields recursively", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(200, {
      capabilities: [
        {
          ...minimalCapability(),
          input_schema: {
            type: "object",
            provider: "private-provider",
            modelProvider: "private-model-provider",
            promptText: "private prompt",
            user_prompt: "private user prompt",
            properties: {
              instruction: {
                type: "string",
                systemPrompt: "private system prompt",
                rawRunnerOutput: { content: "private" },
                nested: {
                  debugTrace: ["private trace"],
                  value: true,
                },
              },
            },
          },
          output_schema: {
            type: "object",
            chainOfThought: "private reasoning",
            skill_body: "private skill body",
            variants: [
              {
                type: "text",
                providerInfo: "private provider details",
                visible: true,
              },
              {
                model_policy: "private policy",
                safe: "yes",
              },
            ],
          },
          security: {
            max_files: 20,
            trace_id: "private trace",
            internalState: { cache: "private" },
            provider_info: "private provider info",
            allowed: {
              mode: "safe",
            },
          },
        },
      ],
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  const capabilities = await client.listCapabilities();

  assert.deepEqual(capabilities[0].input_schema, {
    type: "object",
    properties: {
      instruction: {
        type: "string",
        nested: {
          value: true,
        },
      },
    },
  });
  assert.deepEqual(capabilities[0].output_schema, {
    type: "object",
    variants: [
      {
        type: "text",
        visible: true,
      },
      {
        safe: "yes",
      },
    ],
  });
  assert.deepEqual(capabilities[0].security, {
    max_files: 20,
    allowed: {
      mode: "safe",
    },
  });
});

test("getCapability sends tenant and authorization headers", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url: string | URL, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, minimalCapability());
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    tenantId: "tenant-a",
    tokenProvider: async () => "gateway-token",
    fetch,
  });

  const capability = await client.getCapability("backend-rbac-review");

  assert.equal(capability.id, "backend-rbac-review");
  assert.equal(requests[0].url, "https://gateway.example.com/v1/capabilities/backend-rbac-review");
  assert.equal(headerValue(requests[0].init, "Authorization"), "Bearer gateway-token");
  assert.equal(headerValue(requests[0].init, "X-Tenant-Id"), "tenant-a");
});

test("runCapability posts request body with tenant and authorization headers", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url: string | URL, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, {
      task_id: "task-123",
      status: "completed",
      result: {
        summary: "Reviewed safely.",
        findings: [
          {
            severity: "high",
            path: "src/app.ts",
            message: "Escaped output is missing.",
            internal: "private finding",
          },
        ],
        recommended_tests: ["npm test"],
        internal: "private result",
        prompt: "private prompt",
        trace: ["private trace"],
        skill_text: "private skill body",
        raw_runner_output: "private raw output",
      },
    });
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    tenantId: "tenant-a",
    tokenProvider: async () => "gateway-token",
    fetch,
  });

  const run = await client.runCapability("backend-rbac-review", {
    instruction: "Review current file",
    workspace: {
      files: [{ path: "src/app.ts", content: "const value = 1;\n" }],
    },
    client: { type: "vscode", version: "0.1.0" },
  });

  assert.equal(requests[0].url, "https://gateway.example.com/v1/capabilities/backend-rbac-review/run");
  assert.equal(requests[0].init?.method, "POST");
  assert.equal(headerValue(requests[0].init, "Accept"), "application/json");
  assert.equal(headerValue(requests[0].init, "Content-Type"), "application/json");
  assert.equal(headerValue(requests[0].init, "Authorization"), "Bearer gateway-token");
  assert.equal(headerValue(requests[0].init, "X-Tenant-Id"), "tenant-a");
  assert.deepEqual(JSON.parse(String(requests[0].init?.body)), {
    instruction: "Review current file",
    workspace: {
      files: [{ path: "src/app.ts", content: "const value = 1;\n" }],
    },
    client: { type: "vscode", version: "0.1.0" },
  });
  assert.equal(run.task_id, "task-123");
  assert.equal(run.status, "completed");
  assert.equal(hasForbiddenKey(run), false);
  assert.equal(JSON.stringify(run).includes("private"), false);
});

test("runCapability returns queued task metadata without requiring a result", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(202, {
      task_id: "task-queued",
      status: "queued",
      internal: "private queue metadata",
      trace: ["private trace"],
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  const run = await client.runCapability("backend-rbac-review", {
    instruction: "Review later",
    client: { type: "vscode" },
  });

  assert.deepEqual(run, {
    task_id: "task-queued",
    status: "queued",
  });
});

test("maps Gateway error responses", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(404, {
      error: {
        code: "not_found",
        message: "Capability not found",
        details: { capability_id: "missing" },
      },
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  await assert.rejects(
    () => client.getCapability("missing"),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      const clientError = error as GatewayClientError;
      assert.equal(clientError.status, 404);
      assert.equal(clientError.code, "not_found");
      assert.equal(clientError.message, "Capability not found");
      assert.deepEqual(clientError.details, { capability_id: "missing" });
      return true;
    },
  );
});

test("maps fetch failures to network errors", async () => {
  const fetch: FetchLike = async () => {
    throw new TypeError("fetch failed");
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  await assert.rejects(
    () => client.listCapabilities(),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      const clientError = error as GatewayClientError;
      assert.equal(clientError.status, 0);
      assert.equal(clientError.code, "network_error");
      return true;
    },
  );
});

test("rejects blank Gateway URLs as invalid configuration", () => {
  assert.throws(
    () => new GatewayClient({ gatewayUrl: "   " }),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      const clientError = error as GatewayClientError;
      assert.equal(clientError.status, 0);
      assert.equal(clientError.code, "invalid_configuration");
      return true;
    },
  );
});

test("configureGateway rejects blank replacement tokens without deleting the existing secret", async () => {
  const inputValues = [
    "https://gateway.example.com",
    "tenant-a",
    "   ",
  ];
  const commands = new Map<string, CommandCallback>();
  const deletedSecrets: string[] = [];
  const storedSecrets: Array<{ key: string; value: string }> = [];
  const errorMessages: string[] = [];
  const informationMessages: string[] = [];
  const configurationUpdates: Array<{ key: string; value: string }> = [];

  const vscodeMock = {
    commands: {
      registerCommand(command: string, callback: CommandCallback): Disposable {
        commands.set(command, callback);
        return { dispose() {} };
      },
    },
    workspace: {
      getConfiguration(section: string): MockConfiguration {
        assert.equal(section, "skillCapability");
        return {
          get<T>(_key: string, defaultValue: T): T {
            return defaultValue;
          },
          async update(key: string, value: string): Promise<void> {
            configurationUpdates.push({ key, value });
          },
        };
      },
    },
    window: {
      createOutputChannel(): Disposable & {
        append(value: string): void;
        clear(): void;
        show(preserveFocus?: boolean): void;
      } {
        return {
          append() {},
          clear() {},
          show() {},
          dispose() {},
        };
      },
      registerTreeDataProvider(): Disposable {
        return { dispose() {} };
      },
      async showInputBox(): Promise<string | undefined> {
        return inputValues.shift();
      },
      async showQuickPick(items: Array<{ action: string }>): Promise<{ action: string } | undefined> {
        return items.find((item) => item.action === "set");
      },
      showErrorMessage(message: string): Promise<undefined> {
        errorMessages.push(message);
        return Promise.resolve(undefined);
      },
      showInformationMessage(message: string): Promise<undefined> {
        informationMessages.push(message);
        return Promise.resolve(undefined);
      },
    },
    ConfigurationTarget: {
      Global: 1,
    },
    EventEmitter: class EventEmitter<T> {
      readonly event = (_listener: (value: T) => void): Disposable => ({ dispose() {} });

      fire(_value?: T): void {}
    },
    TreeItem: class TreeItem {
      constructor(
        readonly label: string,
        readonly collapsibleState: number,
      ) {}
    },
    TreeItemCollapsibleState: {
      None: 0,
      Collapsed: 1,
    },
    ThemeIcon: class ThemeIcon {
      constructor(readonly id: string) {}
    },
  };

  await withMockedVscode(vscodeMock, async () => {
    const extension = require("../extension") as {
      activate(context: MockExtensionContext): void;
    };
    extension.activate({
      secrets: {
        async get(): Promise<string | undefined> {
          return "old-token";
        },
        async store(key: string, value: string): Promise<void> {
          storedSecrets.push({ key, value });
        },
        async delete(key: string): Promise<void> {
          deletedSecrets.push(key);
        },
      },
      subscriptions: [],
    });

    const configureGateway = commands.get("skillCapability.configureGateway");
    assert.ok(configureGateway);
    await configureGateway();
  });

  assert.deepEqual(configurationUpdates, [
    { key: "gatewayUrl", value: "https://gateway.example.com" },
    { key: "tenantId", value: "tenant-a" },
  ]);
  assert.deepEqual(storedSecrets, []);
  assert.deepEqual(deletedSecrets, []);
  assert.deepEqual(errorMessages, ["Skill Gateway token is required."]);
  assert.deepEqual(informationMessages, []);
});

function minimalCapability(): Record<string, unknown> {
  return {
    id: "backend-rbac-review",
    name: "Backend RBAC Review",
    version: "0.1.0",
    visible_description: "Review backend RBAC and public API payload boundaries.",
    input_modes: ["current_file"],
    input_schema: { type: "object" },
    output_schema: { type: "object" },
    client_permissions: {
      reads_workspace: true,
      writes_workspace: "optional",
      runs_commands: "optional",
      sends_code_to_server: true,
    },
    approval_policy: {
      upload_context: "user_confirm_large",
    },
  };
}

function jsonResponse(status: number, body: unknown): GatewayFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  };
}

function headerValue(init: RequestInit | undefined, name: string): string | undefined {
  const headers = init?.headers as Record<string, string> | undefined;
  return headers?.[name];
}

function hasForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasForbiddenKey);
  }
  if (value && typeof value === "object") {
    return Object.entries(value).some(([key, nested]) => {
      return serverOnlyKeys.has(key) || hasForbiddenKey(nested);
    });
  }
  return false;
}

type CommandCallback = () => unknown | Promise<unknown>;

interface Disposable {
  dispose(): void;
}

interface MockConfiguration {
  get<T>(key: string, defaultValue: T): T;
  update(key: string, value: string, target: unknown): Promise<void>;
}

interface MockExtensionContext {
  secrets: {
    get(key: string): Promise<string | undefined>;
    store(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
  subscriptions: Disposable[];
}

type ModuleLoader = (request: string, parent: unknown, isMain: boolean) => unknown;

async function withMockedVscode<T>(
  vscodeMock: unknown,
  run: () => Promise<T>,
): Promise<T> {
  const moduleWithLoad = Module as unknown as { _load: ModuleLoader };
  const originalLoad = moduleWithLoad._load;
  const extensionPath = require.resolve("../extension");
  const sessionPath = require.resolve("../auth/session");

  delete require.cache[extensionPath];
  delete require.cache[sessionPath];
  moduleWithLoad._load = (request: string, parent: unknown, isMain: boolean) => {
    if (request === "vscode") {
      return vscodeMock;
    }
    return originalLoad(request, parent, isMain);
  };

  try {
    return await run();
  } finally {
    moduleWithLoad._load = originalLoad;
    delete require.cache[extensionPath];
    delete require.cache[sessionPath];
  }
}
