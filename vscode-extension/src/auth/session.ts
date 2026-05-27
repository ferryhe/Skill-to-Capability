import * as vscode from "vscode";

const gatewayTokenSecretKey = "skillCapability.gatewayToken";

export class GatewaySession {
  constructor(private readonly secrets: vscode.SecretStorage) {}

  async getToken(): Promise<string | undefined> {
    const token = await this.secrets.get(gatewayTokenSecretKey);
    return token?.trim() || undefined;
  }

  async setToken(token: string): Promise<void> {
    const trimmedToken = token.trim();
    if (!trimmedToken) {
      await this.deleteToken();
      return;
    }
    await this.secrets.store(gatewayTokenSecretKey, trimmedToken);
  }

  async deleteToken(): Promise<void> {
    await this.secrets.delete(gatewayTokenSecretKey);
  }

  async getAuthorizationHeader(): Promise<Record<string, string>> {
    const token = await this.getToken();
    if (!token) {
      return {};
    }
    return {
      Authorization: token.startsWith("Bearer ") ? token : `Bearer ${token}`,
    };
  }
}

export function createGatewaySession(context: vscode.ExtensionContext): GatewaySession {
  return new GatewaySession(context.secrets);
}
