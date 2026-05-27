import * as vscode from "vscode";

import { capabilityTreeViewId, CapabilityTreeProvider } from "./capabilities/treeProvider";
import { registerCapabilityCommands } from "./commands/refreshCapabilities";
import { registerRunCapabilityCommands } from "./commands/runCapability";
import { createGatewaySession, GatewaySession } from "./auth/session";

const configurationSection = "skillCapability";

const placeholderCommands = [
  ["skillCapability.applyLastPatch", "Apply last patch"],
  ["skillCapability.runRecommendedTests", "Run recommended tests"],
] as const;

export function activate(context: vscode.ExtensionContext): void {
  const session = createGatewaySession(context);
  const capabilityTreeProvider = new CapabilityTreeProvider();

  context.subscriptions.push(
    capabilityTreeProvider,
    vscode.window.registerTreeDataProvider(
      capabilityTreeViewId,
      capabilityTreeProvider,
    ),
    vscode.commands.registerCommand(
      "skillCapability.configureGateway",
      () => configureGateway(session),
    ),
  );

  registerCapabilityCommands(context, session, capabilityTreeProvider);
  registerRunCapabilityCommands(context, session, capabilityTreeProvider);

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

  const trimmedToken = token.trim();
  if (!trimmedToken) {
    vscode.window.showErrorMessage("Skill Gateway token is required.");
    return;
  }

  await session.setToken(trimmedToken);
  vscode.window.showInformationMessage("Skill Gateway token saved.");
}

function showPlaceholder(label: string): Thenable<string | undefined> {
  return vscode.window.showInformationMessage(`${label} will be added in a later PR.`);
}
