import * as vscode from "vscode";

import type { JsonObject, PublicCapability } from "../api/client";
import { stripServerOnlyFields } from "../security/publicFields";

export const capabilityTreeViewId = "skillCapability.capabilities";

const uncategorizedLabel = "Uncategorized";

export interface CapabilityCategoryNode {
  readonly type: "category";
  readonly label: string;
  readonly capabilities: readonly PublicCapability[];
}

export interface CapabilityLeafNode {
  readonly type: "capability";
  readonly label: string;
  readonly capability: PublicCapability;
}

export type CapabilityTreeNode = CapabilityCategoryNode | CapabilityLeafNode;

export class CapabilityTreeProvider implements vscode.TreeDataProvider<CapabilityTreeNode>, vscode.Disposable {
  private capabilities: PublicCapability[] = [];
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<
    CapabilityTreeNode | undefined | null | void
  >();

  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  setCapabilities(capabilities: readonly PublicCapability[]): void {
    this.capabilities = sortCapabilities(capabilities);
    this.onDidChangeTreeDataEmitter.fire(undefined);
  }

  getCapabilities(): PublicCapability[] {
    return [...this.capabilities];
  }

  getCapability(id: string): PublicCapability | undefined {
    return this.capabilities.find((capability) => capability.id === id);
  }

  getTreeItem(element: CapabilityTreeNode): vscode.TreeItem {
    if (element.type === "category") {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.Collapsed,
      );
      item.description = String(element.capabilities.length);
      item.contextValue = "skillCapability.category";
      item.iconPath = new vscode.ThemeIcon("folder");
      return item;
    }

    const item = new vscode.TreeItem(
      element.capability.name,
      vscode.TreeItemCollapsibleState.None,
    );
    item.id = element.capability.id;
    item.description = capabilityTreeDescription(element.capability);
    item.tooltip = capabilityTooltip(element.capability);
    item.contextValue = "skillCapability.capability";
    item.iconPath = new vscode.ThemeIcon("symbol-method");
    item.command = {
      command: "skillCapability.showCapabilityDetail",
      title: "Show Capability Detail",
      arguments: [element.capability.id],
    };
    return item;
  }

  async getChildren(element?: CapabilityTreeNode): Promise<CapabilityTreeNode[]> {
    if (!element) {
      return buildCapabilityGroups(this.capabilities);
    }
    if (element.type === "category") {
      return element.capabilities.map(toCapabilityNode);
    }
    return [];
  }

  dispose(): void {
    this.onDidChangeTreeDataEmitter.dispose();
  }
}

export function buildCapabilityGroups(
  capabilities: readonly PublicCapability[],
): CapabilityCategoryNode[] {
  const groupedCapabilities = new Map<string, PublicCapability[]>();
  for (const capability of capabilities) {
    const category = capability.category?.trim() || uncategorizedLabel;
    const group = groupedCapabilities.get(category) ?? [];
    group.push(capability);
    groupedCapabilities.set(category, group);
  }

  return [...groupedCapabilities.entries()].map(([label, groupCapabilities]) => ({
    type: "category" as const,
    label,
    capabilities: groupCapabilities,
  }));
}

export function formatCapabilityDetail(capability: PublicCapability): string {
  const sections = [
    "Skill Capability",
    "================",
    `Name: ${capability.name}`,
    `ID: ${capability.id}`,
    `Version: ${capability.version}`,
  ];

  if (capability.category) {
    sections.push(`Category: ${capability.category}`);
  }

  sections.push(
    "",
    "Description:",
    capability.visible_description,
    "",
    `Input modes: ${capability.input_modes.join(", ") || "None"}`,
    "",
    "Input schema:",
    stringifyPublicJson(capability.input_schema),
    "",
    "Output schema:",
    stringifyPublicJson(capability.output_schema),
    "",
    "Client permissions:",
    stringifyPublicJson(capability.client_permissions),
    "",
    "Approval policy:",
    stringifyPublicJson(capability.approval_policy),
  );

  if (capability.security) {
    sections.push("", "Security:", stringifyPublicJson(capability.security));
  }

  return `${sections.join("\n")}\n`;
}

function sortCapabilities(capabilities: readonly PublicCapability[]): PublicCapability[] {
  return [...capabilities].sort((left, right) => {
    const categoryComparison = compareLabels(
      left.category?.trim() || uncategorizedLabel,
      right.category?.trim() || uncategorizedLabel,
    );
    if (categoryComparison !== 0) {
      return categoryComparison;
    }
    return compareLabels(left.name, right.name);
  });
}

function toCapabilityNode(capability: PublicCapability): CapabilityLeafNode {
  return {
    type: "capability",
    label: capability.name,
    capability,
  };
}

function capabilityTreeDescription(capability: PublicCapability): string {
  const modes = capability.input_modes.length > 0
    ? ` - ${capability.input_modes.join(", ")}`
    : "";
  return `${capability.version}${modes}`;
}

function capabilityTooltip(capability: PublicCapability): string {
  return [
    capability.name,
    `${capability.id} @ ${capability.version}`,
    capability.visible_description,
  ].join("\n");
}

function compareLabels(left: string, right: string): number {
  return left.localeCompare(right, undefined, { sensitivity: "base" });
}

function stringifyPublicJson(value: JsonObject): string {
  return JSON.stringify(stripServerOnlyFields(value), null, 2);
}
