import assert from "node:assert/strict";
import test from "node:test";

import { ConfigError, loadAdapterConfig } from "../config.js";

test("loadAdapterConfig uses env values when CLI flags are absent", () => {
  const config = loadAdapterConfig({
    argv: [],
    env: {
      SKILL_GATEWAY_URL: "https://gateway.example.com/",
      SKILL_GATEWAY_TOKEN: "env-token",
      SKILL_GATEWAY_TENANT_ID: "tenant-a",
    },
  });

  assert.deepEqual(config, {
    gatewayUrl: "https://gateway.example.com",
    token: "env-token",
    tenantId: "tenant-a",
  });
});

test("loadAdapterConfig gives CLI flags precedence over env values", () => {
  const config = loadAdapterConfig({
    argv: [
      "--gateway-url",
      "https://cli.example.com/",
      "--gateway-token=cli-token",
      "--tenant-id",
      "tenant-cli",
    ],
    env: {
      SKILL_GATEWAY_URL: "https://env.example.com",
      SKILL_GATEWAY_TOKEN: "env-token",
      SKILL_GATEWAY_TENANT_ID: "tenant-env",
    },
  });

  assert.equal(config.gatewayUrl, "https://cli.example.com");
  assert.equal(config.token, "cli-token");
  assert.equal(config.tenantId, "tenant-cli");
});

test("loadAdapterConfig supports generic Gateway env aliases", () => {
  const config = loadAdapterConfig({
    argv: [],
    env: {
      GATEWAY_URL: "http://localhost:8000",
      GATEWAY_TOKEN: "alias-token",
    },
  });

  assert.equal(config.gatewayUrl, "http://localhost:8000");
  assert.equal(config.token, "alias-token");
});

test("loadAdapterConfig reports missing gateway URL without leaking token env values", () => {
  assert.throws(
    () =>
      loadAdapterConfig({
        argv: [],
        env: {
          SKILL_GATEWAY_TOKEN: "secret-token",
        },
      }),
    (error) => {
      assert.equal(error instanceof ConfigError, true);
      assert.equal(String(error).includes("secret-token"), false);
      assert.match((error as Error).message, /Gateway URL is required/);
      return true;
    },
  );
});

test("loadAdapterConfig reports missing CLI values without echoing nearby secrets", () => {
  assert.throws(
    () =>
      loadAdapterConfig({
        argv: ["--gateway-token", "--gateway-url", "https://gateway.example.com"],
        env: {
          SKILL_GATEWAY_TOKEN: "env-secret",
        },
      }),
    (error) => {
      assert.equal(error instanceof ConfigError, true);
      assert.equal(String(error).includes("env-secret"), false);
      assert.match((error as Error).message, /Missing value for --gateway-token/);
      return true;
    },
  );
});
