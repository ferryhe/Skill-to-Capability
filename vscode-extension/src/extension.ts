import * as vscode from "vscode";

import { GatewayClient, GatewayClientError } from "./api/client";
import { createGatewaySession, GatewaySession } from "./auth/session";

const configurationSection = "skillCapability";

const placeholderCommands = [
  ["skillCapability.runCapability", "Run capability"],
  ["skillCapability.runCurrentFile", "Run current file"],
  ["skillCapability.runCurrentGitDiff", "Run current git diff"],
  ["skillCapability.applyLastPatch", "Apply last patch"],
  ["skillCapability.runRecommendedTests", "Run recommended tests"],
] as const;

export function activate(context: vscode.ExtensionContext): void {
  const session = createGatewaySession(context);

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "skillCapability.configureGateway",
      () => configureGateway(session),
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "skillCapability.refreshCapabilities",
      () => refreshCapabilities(session),
    ),
  );

  for (const [command, label] of placeholderCommands) {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, () => showPlaceholder(label)),
    );
  }
}

export function deactivate(): void {
  // VSCode disposes command registrations through context subscriptions.
}

async function configureGateway(session: GatewaySession): Promise<void> {
  const configuration = vscode.workspace.getConfiguration(configurationSection);

  const gatewayUrl = await vscode.window.showInputBox({
    title: "Configure Skill Gateway",
    prompt: "Gateway URL",
    value: configuration.get<string>("gatewayUrl", "http://localhost:8000"),
    ignoreFocusOut: true,
  });
  if (gatewayUrl === undefined) {
    return;
  }
  const trimmedGatewayUrl = gatewayUrl.trim();
  if (!trimmedGatewayUrl) {
    vscode.window.showErrorMessage("Skill Gateway URL is required.");
    return;
  }

  await configuration.update(
    "gatewayUrl",
    trimmedGatewayUrl,
    vscode.ConfigurationTarget.Global,
  );

  const tenantId = await vscode.window.showInputBox({
    title: "Configure Skill Gateway",
    prompt: "Tenant ID",
    value: configuration.get<string>("tenantId", "default"),
    ignoreFocusOut: true,
  });
  if (tenantId === undefined) {
    return;
  }

  await configuration.update(
    "tenantId",
    tenantId.trim(),
    vscode.ConfigurationTarget.Global,
  );

  const tokenAction = await vscode.window.showQuickPick(
    [
      { label: "Keep existing token", action: "keep" as const },
      { label: "Set or replace token", action: "set" as const },
      { label: "Delete token", action: "delete" as const },
    ],
    {
      title: "Configure Skill Gateway",
      placeHolder: "Gateway token storage",
      ignoreFocusOut: true,
    },
  );

  if (!tokenAction || tokenAction.action === "keep") {
    vscode.window.showInformationMessage("Skill Gateway settings updated.");
    return;
  }

  if (tokenAction.action === "delete") {
    await session.deleteToken();
    vscode.window.showInformationMessage("Skill Gateway token deleted.");
    return;
  }

  const token = await vscode.window.showInputBox({
    title: "Configure Skill Gateway",
    prompt: "Gateway token",
    password: true,
    ignoreFocusOut: true,
  });
  if (token === undefined) {
    return;
  }

  await session.setToken(token);
  vscode.window.showInformationMessage("Skill Gateway token saved.");
}

async function refreshCapabilities(session: GatewaySession): Promise<void> {
  try {
    const client = createGatewayClient(session);
    const capabilities = await client.listCapabilities();
    vscode.window.showInformationMessage(
      `Loaded ${capabilities.length} Skill Gateway capabilities.`,
    );
  } catch (error) {
    vscode.window.showErrorMessage(gatewayErrorMessage(error));
  }
}

function createGatewayClient(session: GatewaySession): GatewayClient {
  const configuration = vscode.workspace.getConfiguration(configurationSection);
  return new GatewayClient({
    gatewayUrl: configuration.get<string>("gatewayUrl", "http://localhost:8000"),
    tenantId: configuration.get<string>("tenantId", "default"),
    tokenProvider: () => session.getToken(),
  });
}

function gatewayErrorMessage(error: unknown): string {
  if (error instanceof GatewayClientError) {
    return `Skill Gateway request failed: ${error.message}`;
  }
  return "Skill Gateway request failed.";
}

function showPlaceholder(label: string): Thenable<string | undefined> {
  return vscode.window.showInformationMessage(`${label} will be added in a later PR.`);
}
