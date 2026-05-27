import { redactSensitiveText, redactSensitiveValue, stripServerOnlyFields } from "./security.js";

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

export interface GatewayClientOptions {
  gatewayUrl: string;
  token?: string;
  tenantId?: string;
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

export type PublicGatewayObject = JsonObject;

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
  readonly gatewayUrl: string;
  readonly tenantId?: string;
  readonly fetchImpl: FetchLike;
  #token?: string;

  constructor(options: GatewayClientOptions) {
    this.gatewayUrl = normalizeGatewayUrl(options.gatewayUrl);
    this.#token = options.token?.trim() || undefined;
    this.tenantId = options.tenantId?.trim() || undefined;
    this.fetchImpl = options.fetch ?? defaultFetch;
  }

  async listCapabilities(): Promise<PublicCapability[]> {
    const body = await this.requestJson("/v1/capabilities");
    if (!isJsonObject(body) || !Array.isArray(body.capabilities)) {
      throw this.invalidResponse("Gateway capabilities response must include a capabilities array.");
    }

    return body.capabilities.map((capability) => this.toPublicCapability(capability));
  }

  async runCapability(capabilityId: string, request: JsonObject): Promise<PublicGatewayObject> {
    return this.requestPublicObject(
      `/v1/capabilities/${encodePathSegment(capabilityId)}/run`,
      "POST",
      request,
      "Gateway run response must be an object.",
    );
  }

  async getTaskStatus(taskId: string): Promise<PublicGatewayObject> {
    return this.requestPublicObject(
      `/v1/tasks/${encodePathSegment(taskId)}`,
      "GET",
      undefined,
      "Gateway task status response must be an object.",
    );
  }

  async getTaskResult(taskId: string): Promise<PublicGatewayObject> {
    return this.requestPublicObject(
      `/v1/tasks/${encodePathSegment(taskId)}/result`,
      "GET",
      undefined,
      "Gateway task result response must be an object.",
    );
  }

  async cancelTask(taskId: string): Promise<PublicGatewayObject> {
    return this.requestPublicObject(
      `/v1/tasks/${encodePathSegment(taskId)}/cancel`,
      "POST",
      undefined,
      "Gateway cancel response must be an object.",
    );
  }

  toJSON(): JsonObject {
    return {
      gatewayUrl: this.gatewayUrl,
      tenantId: this.tenantId,
    };
  }

  private async requestJson(path: string, method = "GET", body?: JsonObject): Promise<unknown> {
    let response: GatewayFetchResponse;
    try {
      const init: RequestInit = {
        method,
        headers: this.buildHeaders(body !== undefined),
      };
      if (body !== undefined) {
        init.body = JSON.stringify(body);
      }
      response = await this.fetchImpl(`${this.gatewayUrl}${path}`, {
        ...init,
      });
    } catch {
      throw new GatewayClientError(
        0,
        "network_error",
        "Unable to reach Skill Gateway.",
      );
    }

    const responseBody = await parseJsonResponse(response);
    if (!response.ok) {
      throw this.mapGatewayError(response, responseBody);
    }
    return responseBody;
  }

  private async requestPublicObject(
    path: string,
    method: "GET" | "POST",
    body: JsonObject | undefined,
    invalidMessage: string,
  ): Promise<PublicGatewayObject> {
    const responseBody = await this.requestJson(path, method, body);
    const sanitized = this.publicValue(responseBody);
    if (!isJsonObject(sanitized)) {
      throw this.invalidResponse(invalidMessage);
    }
    return sanitized;
  }

  private buildHeaders(hasBody = false): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };

    if (hasBody) {
      headers["Content-Type"] = "application/json";
    }

    if (this.tenantId) {
      headers["X-Tenant-Id"] = this.tenantId;
    }

    if (this.#token) {
      headers.Authorization = this.#token.startsWith("Bearer ")
        ? this.#token
        : `Bearer ${this.#token}`;
    }

    return headers;
  }

  private toPublicCapability(value: unknown): PublicCapability {
    const sanitized = this.publicValue(value);
    if (!isJsonObject(sanitized)) {
      throw this.invalidResponse("Gateway capability response must be an object.");
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

  private mapGatewayError(response: GatewayFetchResponse, body: unknown): GatewayClientError {
    if (isJsonObject(body) && isJsonObject(body.error)) {
      const code = typeof body.error.code === "string"
        ? body.error.code
        : defaultErrorCode(response.status);
      const message = typeof body.error.message === "string"
        ? body.error.message
        : defaultErrorMessage(response);
      const details = isJsonObject(body.error.details)
        ? stripServerOnlyFields(body.error.details)
        : {};
      return new GatewayClientError(
        response.status,
        code,
        this.redact(message),
        this.redactValue(details) as JsonObject,
      );
    }

    return new GatewayClientError(
      response.status,
      defaultErrorCode(response.status),
      this.redact(defaultErrorMessage(response)),
    );
  }

  private invalidResponse(message: string): GatewayClientError {
    return new GatewayClientError(0, "invalid_response", this.redact(message));
  }

  private redact(value: string): string {
    return redactSensitiveText(value, this.secretCandidates());
  }

  private redactValue(value: unknown): unknown {
    return redactSensitiveValue(value, this.secretCandidates());
  }

  private publicValue(value: unknown): unknown {
    return this.redactValue(stripServerOnlyFields(value));
  }

  private secretCandidates(): string[] {
    if (!this.#token) {
      return [];
    }

    const candidates = [this.#token];
    const bearerMatch = /^Bearer\s+(.+)$/i.exec(this.#token);
    if (bearerMatch?.[1]) {
      candidates.push(bearerMatch[1]);
    }
    return candidates;
  }
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}

function normalizeGatewayUrl(value: string): string {
  const trimmed = value.trim();
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new GatewayClientError(
      0,
      "invalid_configuration",
      "Gateway URL must be an absolute http(s) URL.",
    );
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new GatewayClientError(
      0,
      "invalid_configuration",
      "Gateway URL must use http or https.",
    );
  }

  if (parsed.search || parsed.hash) {
    throw new GatewayClientError(
      0,
      "invalid_configuration",
      "Gateway URL must not include query parameters or fragments.",
    );
  }

  return trimmed.replace(/\/+$/, "");
}

function stringField(value: JsonObject, field: string): string {
  const rawValue = value[field];
  if (typeof rawValue !== "string") {
    throw new GatewayClientError(
      0,
      "invalid_response",
      `Gateway capability response is missing string field: ${field}.`,
    );
  }
  return rawValue;
}

function stringArrayField(value: JsonObject, field: string): string[] {
  const rawValue = value[field];
  if (!Array.isArray(rawValue) || rawValue.some((item) => typeof item !== "string")) {
    throw new GatewayClientError(
      0,
      "invalid_response",
      `Gateway capability response is missing string array field: ${field}.`,
    );
  }
  return rawValue;
}

function objectField(value: JsonObject, field: string): JsonObject {
  const rawValue = value[field];
  if (!isJsonObject(rawValue)) {
    throw new GatewayClientError(
      0,
      "invalid_response",
      `Gateway capability response is missing object field: ${field}.`,
    );
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

async function defaultFetch(
  url: string,
  init?: RequestInit,
): Promise<GatewayFetchResponse> {
  if (typeof fetch !== "function") {
    throw new GatewayClientError(
      0,
      "network_error",
      "Fetch is not available in this Node.js runtime.",
    );
  }
  return fetch(url, init);
}
