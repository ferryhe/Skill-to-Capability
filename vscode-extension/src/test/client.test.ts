import assert from "node:assert/strict";
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
