export interface AdapterConfig {
  gatewayUrl: string;
  token?: string;
  tenantId?: string;
}

export interface LoadAdapterConfigOptions {
  argv?: readonly string[];
  env?: Record<string, string | undefined>;
}

interface CliConfig {
  gatewayUrl?: string;
  token?: string;
  tenantId?: string;
}

export class ConfigError extends Error {
  readonly code = "invalid_configuration";

  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
    Object.setPrototypeOf(this, ConfigError.prototype);
  }
}

export function loadAdapterConfig(options: LoadAdapterConfigOptions = {}): AdapterConfig {
  const argv = options.argv ?? process.argv.slice(2);
  const env = options.env ?? process.env;
  const cli = parseCliConfig(argv);

  const rawGatewayUrl = firstPresent(
    cli.gatewayUrl,
    env.SKILL_GATEWAY_URL,
    env.GATEWAY_URL,
  );
  if (!rawGatewayUrl) {
    throw new ConfigError(
      "Gateway URL is required. Set --gateway-url or SKILL_GATEWAY_URL.",
    );
  }

  return {
    gatewayUrl: normalizeGatewayUrl(rawGatewayUrl),
    token: firstPresent(cli.token, env.SKILL_GATEWAY_TOKEN, env.GATEWAY_TOKEN),
    tenantId: firstPresent(
      cli.tenantId,
      env.SKILL_GATEWAY_TENANT_ID,
      env.GATEWAY_TENANT_ID,
      env.TENANT_ID,
    ),
  };
}

function parseCliConfig(argv: readonly string[]): CliConfig {
  const config: CliConfig = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--gateway-url") {
      config.gatewayUrl = requiredFlagValue(arg, argv[index + 1]);
      index += 1;
    } else if (arg.startsWith("--gateway-url=")) {
      config.gatewayUrl = requiredInlineValue("--gateway-url", arg);
    } else if (arg === "--gateway-token" || arg === "--token") {
      config.token = requiredFlagValue(arg, argv[index + 1]);
      index += 1;
    } else if (arg.startsWith("--gateway-token=")) {
      config.token = requiredInlineValue("--gateway-token", arg);
    } else if (arg.startsWith("--token=")) {
      config.token = requiredInlineValue("--token", arg);
    } else if (arg === "--tenant-id") {
      config.tenantId = requiredFlagValue(arg, argv[index + 1]);
      index += 1;
    } else if (arg.startsWith("--tenant-id=")) {
      config.tenantId = requiredInlineValue("--tenant-id", arg);
    }
  }
  return config;
}

function requiredFlagValue(flag: string, value: string | undefined): string {
  if (!value || value.startsWith("--") || !value.trim()) {
    throw new ConfigError(`Missing value for ${flag}.`);
  }
  return value.trim();
}

function requiredInlineValue(flag: string, arg: string): string {
  const value = arg.slice(flag.length + 1).trim();
  if (!value) {
    throw new ConfigError(`Missing value for ${flag}.`);
  }
  return value;
}

function normalizeGatewayUrl(value: string): string {
  const trimmed = value.trim();
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new ConfigError("Gateway URL must be an absolute http(s) URL.");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ConfigError("Gateway URL must use http or https.");
  }

  return trimmed.replace(/\/+$/, "");
}

function firstPresent(...values: Array<string | undefined>): string | undefined {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return undefined;
}
