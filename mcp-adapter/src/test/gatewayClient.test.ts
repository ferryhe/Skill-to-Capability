import assert from "node:assert/strict";
import test from "node:test";

import {
  GatewayClient,
  GatewayClientError,
  type FetchLike,
  type GatewayFetchResponse,
} from "../gatewayClient.js";
import { redactSensitiveValue } from "../security.js";

test("listCapabilities calls the public Gateway endpoint with normalized URL and headers", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url, init) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, {
      capabilities: [
        {
          id: "backend-rbac-review",
          name: "Backend RBAC Review",
          version: "0.1.0",
          visible_description: "Review backend RBAC and public API payload boundaries.",
          input_modes: ["current_file"],
          input_schema: { type: "object" },
          output_schema: { type: "object" },
          client_permissions: { reads_workspace: true },
          approval_policy: { upload_context: "user_confirm_large" },
          internal: { skill_ref: "private" },
          prompt: "private prompt",
          trace: ["private trace"],
          skill_text: "private skill body",
        },
      ],
    });
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com/",
    token: "gateway-token",
    tenantId: "tenant-a",
    fetch,
  });

  const capabilities = await client.listCapabilities();

  assert.equal(requests[0].url, "https://gateway.example.com/v1/capabilities");
  assert.equal(headerValue(requests[0].init, "Accept"), "application/json");
  assert.equal(headerValue(requests[0].init, "Authorization"), "Bearer gateway-token");
  assert.equal(headerValue(requests[0].init, "X-Tenant-Id"), "tenant-a");
  assert.equal(JSON.stringify(capabilities).includes("private"), false);
  assert.equal(hasForbiddenKey(capabilities), false);
});

test("GatewayClient F2 methods call expected Gateway endpoints and bodies", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url, init) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, {
      task_id: "task-1",
      status: "completed",
      summary: "Public summary.",
    });
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  await client.runCapability("backend-rbac-review", {
    instruction: "Review this.",
    options: { strictness: "high" },
  });
  await client.getTaskStatus("task-1");
  await client.getTaskResult("task-1");
  await client.cancelTask("task-1");

  assertRequest(requests[0], "POST", "https://gateway.example.com/v1/capabilities/backend-rbac-review/run", {
    instruction: "Review this.",
    options: { strictness: "high" },
  });
  assertRequest(requests[1], "GET", "https://gateway.example.com/v1/tasks/task-1");
  assertRequest(requests[2], "GET", "https://gateway.example.com/v1/tasks/task-1/result");
  assertRequest(requests[3], "POST", "https://gateway.example.com/v1/tasks/task-1/cancel");
});

test("GatewayClient encodes capability and task IDs as path segments", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const fetch: FetchLike = async (url, init) => {
    requests.push({ url: String(url), init });
    return jsonResponse(200, {
      task_id: "task/a b",
      status: "completed",
    });
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  await client.runCapability("team/a b", { instruction: "Review this." });
  await client.getTaskStatus("task/a b");
  await client.getTaskResult("task/a b");
  await client.cancelTask("task/a b");

  assertRequest(requests[0], "POST", "https://gateway.example.com/v1/capabilities/team%2Fa%20b/run", {
    instruction: "Review this.",
  });
  assertRequest(requests[1], "GET", "https://gateway.example.com/v1/tasks/task%2Fa%20b");
  assertRequest(requests[2], "GET", "https://gateway.example.com/v1/tasks/task%2Fa%20b/result");
  assertRequest(requests[3], "POST", "https://gateway.example.com/v1/tasks/task%2Fa%20b/cancel");
});

test("GatewayClient F2 methods strip server-only fields from public responses", async () => {
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
          raw_runner_output: "private runner output",
        },
      ],
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  const result = await client.getTaskResult("task-1");

  assert.deepEqual(result, {
    task_id: "task-1",
    status: "completed",
    summary: "Public summary.",
    nested: { safe: true },
    findings: [{ title: "Public finding" }],
  });
  assert.equal(hasForbiddenKey(result), false);
  assert.equal(JSON.stringify(result).includes("private"), false);
});

test("GatewayClient validates Gateway URL schemes", () => {
  assert.throws(
    () =>
      new GatewayClient({
        gatewayUrl: "file:///tmp/gateway",
      }),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      assert.equal((error as GatewayClientError).code, "invalid_configuration");
      return true;
    },
  );
});

test("GatewayClient rejects Gateway URLs with query parameters or fragments", () => {
  for (const gatewayUrl of [
    "https://gateway.example.com?token=secret-token",
    "https://gateway.example.com#secret-token",
  ]) {
    assert.throws(
      () =>
        new GatewayClient({
          gatewayUrl,
        }),
      (error) => {
        assert.equal(error instanceof GatewayClientError, true);
        assert.equal((error as GatewayClientError).code, "invalid_configuration");
        assert.equal(
          (error as Error).message,
          "Gateway URL must not include query parameters or fragments.",
        );
        assert.equal(String(error).includes("secret-token"), false);
        return true;
      },
    );
  }
});

test("GatewayClient redacts tokens from Gateway error messages and details", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(500, {
      error: {
        code: "internal_server_error",
        message: "Failed while using Bearer secret-token against https://gateway.example.com/private?token=secret-token",
        details: {
          raw: "secret-token",
          nested: {
            message: "Authorization: Bearer secret-token",
          },
        },
      },
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    token: "secret-token",
    fetch,
  });

  await assert.rejects(
    () => client.listCapabilities(),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      assert.equal(String(error).includes("secret-token"), false);
      assert.equal(JSON.stringify((error as GatewayClientError).details).includes("secret-token"), false);
      assert.match((error as Error).message, /\[REDACTED\]/);
      return true;
    },
  );
});

test("GatewayClient strips server-only fields from Gateway error details before returning errors", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(500, {
      error: {
        code: "internal_server_error",
        message: "Gateway failed safely.",
        details: {
          safe: "public detail",
          internal: { skill_ref: "private-skill" },
          prompt: "private prompt",
          trace: ["private trace"],
          skill_text: "private skill body",
          skill_ref: "private-skill",
          raw_runner_output: "private runner output",
          nested: {
            safe: true,
            systemPrompt: "private system prompt",
            debugTrace: ["private trace"],
          },
        },
      },
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    fetch,
  });

  await assert.rejects(
    () => client.listCapabilities(),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      const details = (error as GatewayClientError).details;
      assert.deepEqual(details, {
        safe: "public detail",
        nested: {
          safe: true,
        },
      });
      assert.equal(hasForbiddenKey(details), false);
      assert.equal(JSON.stringify(details).includes("private"), false);
      return true;
    },
  );
});

test("GatewayClient redacts bearer-stripped token values from Gateway error details", async () => {
  const fetch: FetchLike = async () =>
    jsonResponse(500, {
      error: {
        code: "internal_server_error",
        message: "Failed with raw token secret-token.",
        details: {
          raw_token_echo: "secret-token",
          auth_header: "Bearer secret-token",
        },
      },
    });
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    token: "Bearer secret-token",
    fetch,
  });

  await assert.rejects(
    () => client.listCapabilities(),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      assert.equal(String(error).includes("secret-token"), false);
      assert.equal(JSON.stringify((error as GatewayClientError).details).includes("secret-token"), false);
      return true;
    },
  );
});

test("redactSensitiveValue redacts values stored under sensitive object keys", () => {
  const redacted = redactSensitiveValue({
    safe: "public",
    api_key: "unrelated-api-key",
    token: "unrelated-token",
    authorization: "Basic unrelated-credential",
    nested: {
      clientSecret: "unrelated-secret",
      credentials: {
        username: "service-user",
        password: "unrelated-password",
      },
    },
  });

  assert.deepEqual(redacted, {
    safe: "public",
    api_key: "[REDACTED]",
    token: "[REDACTED]",
    authorization: "[REDACTED]",
    nested: {
      clientSecret: "[REDACTED]",
      credentials: "[REDACTED]",
    },
  });
});

test("GatewayClient maps fetch failures to sanitized network errors", async () => {
  const fetch: FetchLike = async () => {
    throw new Error("network failed with secret-token");
  };
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    token: "secret-token",
    fetch,
  });

  await assert.rejects(
    () => client.listCapabilities(),
    (error) => {
      assert.equal(error instanceof GatewayClientError, true);
      assert.equal((error as GatewayClientError).status, 0);
      assert.equal((error as GatewayClientError).code, "network_error");
      assert.equal(String(error).includes("secret-token"), false);
      return true;
    },
  );
});

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
    assert.equal(headerValue(request.init, "Content-Type"), "application/json");
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
      ].includes(key)
        || hasForbiddenKey(nested);
    });
  }
  return false;
}
