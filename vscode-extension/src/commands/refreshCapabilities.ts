import * as vscode from "vscode";

import { GatewayClient, GatewayClientError, type PublicCapability } from "../api/client";
import type { GatewaySession } from "../auth/session";
import {
  CapabilityTreeProvider,
  formatCapabilityDetail,
  type CapabilityTreeNode,
} from "../capabilities/treeProvider";

const configurationSection = "skillCapability";

export function registerCapabilityCommands(
  context: vscode.ExtensionContext,
  session: GatewaySession,
  treeProvider: CapabilityTreeProvider,
): void {
  const outputChannel = vscode.window.createOutputChannel("Skill Capability");

  context.subscriptions.push(
    outputChannel,
    vscode.commands.registerCommand(
      "skillCapability.refreshCapabilities",
      () => refreshCapabilities(session, treeProvider),
    ),
    vscode.commands.registerCommand(
      "skillCapability.showCapabilityDetail",
      (capability?: CapabilityCommandArgument) =>
        showCapabilityDetail(treeProvider, outputChannel, capability),
    ),
  );
}

export async function refreshCapabilities(
  session: GatewaySession,
  treeProvider: CapabilityTreeProvider,
): Promise<void> {
  try {
    const client = createGatewayClient(session);
    const capabilities = await client.listCapabilities();
    treeProvider.setCapabilities(capabilities);
    vscode.window.showInformationMessage(
      `Loaded ${capabilities.length} Skill Gateway capabilities.`,
    );
  } catch (error) {
    vscode.window.showErrorMessage(gatewayErrorMessage(error));
  }
}

export async function showCapabilityDetail(
  treeProvider: CapabilityTreeProvider,
  outputChannel: vscode.OutputChannel,
  capability?: CapabilityCommandArgument,
): Promise<void> {
  const selectedCapability = await resolveCapability(treeProvider, capability);
  if (!selectedCapability) {
    return;
  }

  outputChannel.clear();
  outputChannel.append(formatCapabilityDetail(selectedCapability));
  outputChannel.show(true);
}

export function createGatewayClient(session: GatewaySession): GatewayClient {
  const configuration = vscode.workspace.getConfiguration(configurationSection);
  return new GatewayClient({
    gatewayUrl: configuration.get<string>("gatewayUrl", "http://localhost:8000"),
    tenantId: configuration.get<string>("tenantId", "default"),
    tokenProvider: () => session.getToken(),
  });
}

export function gatewayErrorMessage(error: unknown): string {
  if (error instanceof GatewayClientError) {
    return `Skill Gateway request failed: ${error.message}`;
  }
  return "Skill Gateway request failed.";
}

async function resolveCapability(
  treeProvider: CapabilityTreeProvider,
  capability?: CapabilityCommandArgument,
): Promise<PublicCapability | undefined> {
  if (typeof capability === "string") {
    const cachedCapability = treeProvider.getCapability(capability);
    if (!cachedCapability) {
      vscode.window.showWarningMessage(
        "Capability details are unavailable. Refresh Skill Gateway capabilities.",
      );
    }
    return cachedCapability;
  }

  if (isCapabilityLeafNode(capability)) {
    return capability.capability;
  }

  if (isPublicCapability(capability)) {
    return capability;
  }

  const capabilities = treeProvider.getCapabilities();
  if (capabilities.length === 0) {
    vscode.window.showInformationMessage(
      "No Skill Gateway capabilities loaded. Run refresh first.",
    );
    return undefined;
  }

  const selected = await vscode.window.showQuickPick(
    capabilities.map((cachedCapability) => ({
      label: cachedCapability.name,
      description: `${cachedCapability.id} @ ${cachedCapability.version}`,
      capability: cachedCapability,
    })),
    {
      title: "Show Skill Capability Detail",
      placeHolder: "Select a Gateway capability",
      ignoreFocusOut: true,
    },
  );

  return selected?.capability;
}

type CapabilityCommandArgument = PublicCapability | CapabilityTreeNode | string | undefined;

function isCapabilityLeafNode(value: unknown): value is Extract<
  CapabilityTreeNode,
  { type: "capability" }
> {
  return Boolean(value)
    && typeof value === "object"
    && (value as { type?: unknown }).type === "capability"
    && isPublicCapability((value as { capability?: unknown }).capability);
}

function isPublicCapability(value: unknown): value is PublicCapability {
  if (!value || typeof value !== "object") {
    return false;
  }

  const capability = value as Partial<PublicCapability>;
  return typeof capability.id === "string"
    && typeof capability.name === "string"
    && typeof capability.version === "string"
    && typeof capability.visible_description === "string"
    && Array.isArray(capability.input_modes)
    && capability.input_modes.every((mode) => typeof mode === "string")
    && isRecord(capability.input_schema)
    && isRecord(capability.output_schema)
    && isRecord(capability.client_permissions)
    && isRecord(capability.approval_policy);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
