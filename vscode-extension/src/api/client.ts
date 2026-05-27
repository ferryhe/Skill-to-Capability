export type JsonObject = Record<string, unknown>;

export interface GatewayFetchResponse {
  ok: boolean;
  status: number;
  statusText?: string;
  json(): Promise<unknown>;
}

export type FetchLike = (
  url: string,
  init?: RequestInit,
) => Promise<GatewayFetchResponse>;

export type TokenProvider = () => string | undefined | Promise<string | undefined>;

export interface GatewayClientOptions {
  gatewayUrl: string;
  tenantId?: string;
  tokenProvider?: TokenProvider;
  fetch?: FetchLike;
}

export interface PublicCapability {
  id: string;
  name: string;
  version: string;
  category?: string;
  visible_description: string;
  input_modes: string[];
  input_schema: JsonObject;
  output_schema: JsonObject;
  client_permissions: JsonObject;
  approval_policy: JsonObject;
  security?: JsonObject;
}

export class GatewayClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: JsonObject;

  constructor(status: number, code: string, message: string, details: JsonObject = {}) {
    super(message);
    this.name = "GatewayClientError";
    this.status = status;
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, GatewayClientError.prototype);
  }
}

const prohibitedOutputKeys = new Set([
  "chain_of_thought",
  "chainofthought",
  "developerprompt",
  "internal",
  "internalstate",
  "model_policy",
  "modelpolicy",
  "modelprovider",
  "prompt",
  "prompttext",
  "provider",
  "providerinfo",
  "raw_runner_output",
  "rawrunneroutput",
  "skill_body",
  "skill_ref",
  "skill_text",
  "skillbody",
  "skillref",
  "skilltext",
  "systemprompt",
  "tooltrace",
  "trace",
]);

const prohibitedOutputKeyPatterns = [
  /^(?:[a-z0-9]+_)*prompt(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*trace(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*internal(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*provider(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*skill_(?:body|text|ref)(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*chain_of_thought(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*raw_runner_output(?:_[a-z0-9]+)*$/,
];

export class GatewayClient {
  private readonly gatewayUrl: string;
  private readonly tenantId?: string;
  private readonly tokenProvider?: TokenProvider;
  private readonly fetchImpl: FetchLike;

  constructor(options: GatewayClientOptions) {
    const gatewayUrl = options.gatewayUrl.trim().replace(/\/+$/, "");
    if (!gatewayUrl) {
      throw new GatewayClientError(
        0,
        "invalid_configuration",
        "Skill Gateway URL is required.",
      );
    }

    this.gatewayUrl = gatewayUrl;
    this.tenantId = options.tenantId?.trim() || undefined;
    this.tokenProvider = options.tokenProvider;
    this.fetchImpl = options.fetch ?? defaultFetch;
  }

  async listCapabilities(): Promise<PublicCapability[]> {
    const body = await this.requestJson("/v1/capabilities");
    if (!isJsonObject(body) || !Array.isArray(body.capabilities)) {
      throw invalidResponse("Gateway capabilities response must include a capabilities array.");
    }

    return body.capabilities.map(toPublicCapability);
  }

  async getCapability(id: string): Promise<PublicCapability> {
    const capabilityId = id.trim();
    if (!capabilityId) {
      throw new GatewayClientError(
        0,
        "invalid_request",
        "Capability id is required.",
      );
    }

    const body = await this.requestJson(
      `/v1/capabilities/${encodeURIComponent(capabilityId)}`,
    );
    return toPublicCapability(body);
  }

  private async requestJson(path: string): Promise<unknown> {
    let response: GatewayFetchResponse;
    try {
      response = await this.fetchImpl(`${this.gatewayUrl}${path}`, {
        method: "GET",
        headers: await this.buildHeaders(),
      });
    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw error;
      }
      throw new GatewayClientError(
        0,
        "network_error",
        "Unable to reach Skill Gateway.",
      );
    }

    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw mapGatewayError(response, body);
    }
    return body;
  }

  private async buildHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };

    if (this.tenantId) {
      headers["X-Tenant-Id"] = this.tenantId;
    }

    const token = (await this.tokenProvider?.())?.trim();
    if (token) {
      headers.Authorization = token.startsWith("Bearer ") ? token : `Bearer ${token}`;
    }

    return headers;
  }
}

function toPublicCapability(value: unknown): PublicCapability {
  const sanitized = stripServerOnlyFields(value);
  if (!isJsonObject(sanitized)) {
    throw invalidResponse("Gateway capability response must be an object.");
  }

  const capability: PublicCapability = {
    id: stringField(sanitized, "id"),
    name: stringField(sanitized, "name"),
    version: stringField(sanitized, "version"),
    visible_description: stringField(sanitized, "visible_description"),
    input_modes: stringArrayField(sanitized, "input_modes"),
    input_schema: objectField(sanitized, "input_schema"),
    output_schema: objectField(sanitized, "output_schema"),
    client_permissions: objectField(sanitized, "client_permissions"),
    approval_policy: objectField(sanitized, "approval_policy"),
  };

  if (typeof sanitized.category === "string") {
    capability.category = sanitized.category;
  }
  if (isJsonObject(sanitized.security)) {
    capability.security = sanitized.security;
  }

  return capability;
}

function stripServerOnlyFields(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripServerOnlyFields);
  }
  if (!isJsonObject(value)) {
    return value;
  }

  const result: JsonObject = {};
  for (const [key, nested] of Object.entries(value)) {
    if (isProhibitedOutputKey(key)) {
      continue;
    }
    result[key] = stripServerOnlyFields(nested);
  }
  return result;
}

function stringField(value: JsonObject, field: string): string {
  const rawValue = value[field];
  if (typeof rawValue !== "string") {
    throw invalidResponse(`Gateway capability response is missing string field: ${field}.`);
  }
  return rawValue;
}

function stringArrayField(value: JsonObject, field: string): string[] {
  const rawValue = value[field];
  if (!Array.isArray(rawValue) || rawValue.some((item) => typeof item !== "string")) {
    throw invalidResponse(`Gateway capability response is missing string array field: ${field}.`);
  }
  return rawValue;
}

function objectField(value: JsonObject, field: string): JsonObject {
  const rawValue = value[field];
  if (!isJsonObject(rawValue)) {
    throw invalidResponse(`Gateway capability response is missing object field: ${field}.`);
  }
  return rawValue;
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeKey(key: string): string {
  return key
    .trim()
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function isProhibitedOutputKey(key: string): boolean {
  const normalizedKey = normalizeKey(key);
  return prohibitedOutputKeys.has(normalizedKey)
    || prohibitedOutputKeyPatterns.some((pattern) => pattern.test(normalizedKey));
}

async function parseJsonResponse(response: GatewayFetchResponse): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function mapGatewayError(
  response: GatewayFetchResponse,
  body: unknown,
): GatewayClientError {
  if (isJsonObject(body) && isJsonObject(body.error)) {
    const code = typeof body.error.code === "string"
      ? body.error.code
      : defaultErrorCode(response.status);
    const message = typeof body.error.message === "string"
      ? body.error.message
      : defaultErrorMessage(response);
    const details = isJsonObject(body.error.details) ? body.error.details : {};
    return new GatewayClientError(response.status, code, message, details);
  }

  return new GatewayClientError(
    response.status,
    defaultErrorCode(response.status),
    defaultErrorMessage(response),
  );
}

function defaultErrorCode(status: number): string {
  return {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    422: "request_validation_error",
    500: "internal_server_error",
  }[status] ?? "http_error";
}

function defaultErrorMessage(response: GatewayFetchResponse): string {
  return response.statusText || "Gateway request failed.";
}

function invalidResponse(message: string): GatewayClientError {
  return new GatewayClientError(0, "invalid_response", message);
}

async function defaultFetch(
  url: string,
  init?: RequestInit,
): Promise<GatewayFetchResponse> {
  if (typeof fetch !== "function") {
    throw new GatewayClientError(
      0,
      "network_error",
      "Fetch is not available in this extension host.",
    );
  }
  return fetch(url, init);
}
