import { stripServerOnlyFields } from "../security/publicFields";

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

export interface CapabilityRunRequest {
  instruction: string;
  workspace?: unknown;
  client: {
    type: "vscode";
    version?: string;
  };
}

export interface CapabilityRunResponse {
  task_id: string;
  status: "completed" | "queued" | string;
  capability_id?: string;
  created_at?: string;
  updated_at?: string;
  result?: unknown;
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

  async runCapability(
    id: string,
    request: CapabilityRunRequest,
  ): Promise<CapabilityRunResponse> {
    const capabilityId = id.trim();
    if (!capabilityId) {
      throw new GatewayClientError(
        0,
        "invalid_request",
        "Capability id is required.",
      );
    }

    const body = await this.requestJson(
      `/v1/capabilities/${encodeURIComponent(capabilityId)}/run`,
      {
        method: "POST",
        body: JSON.stringify(request),
      },
    );
    return toCapabilityRunResponse(body);
  }

  private async requestJson(
    path: string,
    init: Pick<RequestInit, "method" | "body"> = {},
  ): Promise<unknown> {
    let response: GatewayFetchResponse;
    try {
      response = await this.fetchImpl(`${this.gatewayUrl}${path}`, {
        method: init.method ?? "GET",
        headers: await this.buildHeaders(init.body !== undefined),
        body: init.body,
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

  private async buildHeaders(includeJsonContentType = false): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (includeJsonContentType) {
      headers["Content-Type"] = "application/json";
    }

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

function toCapabilityRunResponse(value: unknown): CapabilityRunResponse {
  const sanitized = stripServerOnlyFields(value);
  if (!isJsonObject(sanitized)) {
    throw invalidResponse("Gateway run response must be an object.");
  }

  const taskId = sanitized.task_id;
  const status = sanitized.status;
  if (typeof taskId !== "string" || typeof status !== "string") {
    throw invalidResponse("Gateway run response must include task_id and status.");
  }

  const response: CapabilityRunResponse = {
    task_id: taskId,
    status,
  };
  for (const metadataField of ["capability_id", "created_at", "updated_at"] as const) {
    const metadataValue = sanitized[metadataField];
    if (typeof metadataValue === "string") {
      response[metadataField] = metadataValue;
    }
  }
  if ("result" in sanitized) {
    response.result = sanitized.result;
  }
  return response;
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
