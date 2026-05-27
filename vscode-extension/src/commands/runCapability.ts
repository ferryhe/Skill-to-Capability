import * as vscode from "vscode";

import type { CapabilityRunRequest, CapabilityRunResponse, PublicCapability } from "../api/client";
import type { GatewaySession } from "../auth/session";
import type { CapabilityTreeNode, CapabilityTreeProvider } from "../capabilities/treeProvider";
import {
  collectCurrentFileContext,
  collectGitDiffContext,
  collectSelectionContext,
  createRunRequestPayload,
  type PublicWorkspaceContext,
  type WorkspaceContextResult,
} from "../context/workspaceCollector";
import { showCapabilityReportPanel } from "../webview/reportPanel";
import { createGatewayClient, gatewayErrorMessage } from "./refreshCapabilities";

const configurationSection = "skillCapability";

type ContextMode = "current_file" | "git_diff" | "none";

type CollectedContextResult = WorkspaceContextResult & {
  workspaceFolder?: vscode.WorkspaceFolder;
};

export interface RunCommandDependencies {
  createClient(): {
    runCapability(id: string, request: CapabilityRunRequest): Promise<CapabilityRunResponse | unknown>;
  };
  renderReport(report: CapabilityRunResponse | unknown): void;
  rememberPatch?(report: CapabilityRunResponse | unknown, workspaceFolder?: vscode.WorkspaceFolder): void;
  rememberRecommendedTests?(report: CapabilityRunResponse | unknown, workspaceFolder?: vscode.WorkspaceFolder): void;
  clientVersion?: string;
}

export function registerRunCapabilityCommands(
  context: vscode.ExtensionContext,
  session: GatewaySession,
  treeProvider: CapabilityTreeProvider,
): void {
  const deps: RunCommandDependencies = {
    createClient: () => createGatewayClient(session),
    renderReport: (report) => showCapabilityReportPanel(report as CapabilityRunResponse),
    rememberPatch: (report, workspaceFolder) => {
      const { rememberRunPatch } = require("./applyPatch") as typeof import("./applyPatch");
      rememberRunPatch(report, workspaceFolder);
    },
    rememberRecommendedTests: (report, workspaceFolder) => {
      const { rememberRunRecommendedTests } = require("./runRecommendedTests") as typeof import("./runRecommendedTests");
      rememberRunRecommendedTests(report, workspaceFolder);
    },
    clientVersion: vscode.version,
  };

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "skillCapability.runCapability",
      (capability?: CapabilityCommandArgument) => runCapability(treeProvider, deps, capability),
    ),
    vscode.commands.registerCommand(
      "skillCapability.runCurrentFile",
      (capability?: CapabilityCommandArgument) => runCurrentFile(treeProvider, deps, capability),
    ),
    vscode.commands.registerCommand(
      "skillCapability.runCurrentGitDiff",
      (capability?: CapabilityCommandArgument) => runCurrentGitDiff(treeProvider, deps, capability),
    ),
  );
}

export async function runCapability(
  treeProvider: TreeProviderLike,
  deps: RunCommandDependencies,
  capability?: CapabilityCommandArgument,
): Promise<void> {
  const contextMode = await chooseContextMode();
  if (!contextMode) {
    return;
  }
  await runCapabilityWithMode(treeProvider, deps, contextMode, capability);
}

export async function runCurrentFile(
  treeProvider: TreeProviderLike,
  deps: RunCommandDependencies,
  capability?: CapabilityCommandArgument,
): Promise<void> {
  await runCapabilityWithMode(treeProvider, deps, "current_file", capability);
}

export async function runCurrentGitDiff(
  treeProvider: TreeProviderLike,
  deps: RunCommandDependencies,
  capability?: CapabilityCommandArgument,
): Promise<void> {
  await runCapabilityWithMode(treeProvider, deps, "git_diff", capability);
}

async function runCapabilityWithMode(
  treeProvider: TreeProviderLike,
  deps: RunCommandDependencies,
  contextMode: ContextMode,
  capability?: CapabilityCommandArgument,
): Promise<void> {
  const selectedCapability = await resolveCapability(treeProvider, capability);
  if (!selectedCapability) {
    return;
  }

  const instruction = await vscode.window.showInputBox({
    title: "Run Skill Capability",
    prompt: "Instruction",
    placeHolder: "What should this capability do?",
    ignoreFocusOut: true,
  });
  if (instruction === undefined) {
    return;
  }
  const trimmedInstruction = instruction.trim();
  if (!trimmedInstruction) {
    vscode.window.showErrorMessage("Instruction is required.");
    return;
  }

  const contextResult = await collectContext(contextMode);
  if (!contextResult) {
    return;
  }
  const hasContext = hasWorkspaceContext(contextResult.workspace);
  if (contextResult.errors.length > 0 && !hasContext && contextMode !== "none") {
    vscode.window.showErrorMessage(
      `No workspace context could be collected; ${contextResult.errors.length} issue(s) must be resolved before running.`,
    );
    return;
  }
  if (contextResult.errors.length > 0) {
    vscode.window.showWarningMessage(
      `Some workspace context was skipped: ${contextResult.errors.length} issue(s).`,
    );
  }

  const request = createRunRequestPayload({
    instruction: trimmedInstruction,
    workspace: hasContext
      ? contextResult.workspace
      : undefined,
    clientVersion: deps.clientVersion,
  });
  if (
    hasContext
      && shouldConfirmWorkspaceUpload(selectedCapability)
      && !await confirmWorkspaceUpload(contextResult.workspace, contextResult.workspaceFolder)
  ) {
    return;
  }

  try {
    const report = await deps.createClient().runCapability(selectedCapability.id, request);
    deps.rememberPatch?.(report, contextResult.workspaceFolder);
    deps.rememberRecommendedTests?.(report, contextResult.workspaceFolder);
    deps.renderReport(report);
  } catch (error) {
    vscode.window.showErrorMessage(gatewayErrorMessage(error));
  }
}

async function chooseContextMode(): Promise<ContextMode | undefined> {
  const selected = await vscode.window.showQuickPick(
    [
      { label: "Current file", mode: "current_file" as const },
      { label: "Git diff", mode: "git_diff" as const },
      { label: "No workspace context", mode: "none" as const },
    ],
    {
      title: "Run Skill Capability",
      placeHolder: "Choose workspace context",
      ignoreFocusOut: true,
    },
  );
  return selected?.mode;
}

async function collectContext(contextMode: ContextMode): Promise<CollectedContextResult | undefined> {
  if (contextMode === "none") {
    return { workspace: {}, errors: [] };
  }

  const settings = getWorkspaceContextSettings();
  if (contextMode === "git_diff") {
    const workspaceFolder = await resolveGitDiffWorkspaceFolder();
    if (!workspaceFolder) {
      return undefined;
    }
    const result = await collectGitDiffContext({
      workspaceRoot: workspaceFolder.uri.fsPath,
      settings,
    });
    return {
      ...result,
      workspaceFolder,
    };
  }

  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage("Open a file before running with current file context.");
    return undefined;
  }
  const workspaceFolder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  if (!workspaceFolder) {
    vscode.window.showErrorMessage("Open a file inside a workspace folder before running current file context.");
    return undefined;
  }

  const document = {
    uri: editor.document.uri,
    text: editor.document.getText(),
  };
  const currentFile = await collectCurrentFileContext({
    workspaceRoot: workspaceFolder.uri.fsPath,
    document,
    settings,
  });

  if (editor.selection.isEmpty) {
    return {
      ...currentFile,
      workspaceFolder,
    };
  }

  const selection = await collectSelectionContext({
    workspaceRoot: workspaceFolder.uri.fsPath,
    document,
    selection: {
      startLine: editor.selection.start.line,
      endLine: editor.selection.end.line,
      text: editor.document.getText(editor.selection),
    },
    settings,
  });

  return {
    workspace: {
      ...currentFile.workspace,
      selection: selection.workspace.selection,
    },
    errors: [...currentFile.errors, ...selection.errors],
    workspaceFolder,
  };
}

function activeEditorWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return undefined;
  }
  return vscode.workspace.getWorkspaceFolder(editor.document.uri);
}

async function resolveGitDiffWorkspaceFolder(): Promise<vscode.WorkspaceFolder | undefined> {
  const activeWorkspaceFolder = activeEditorWorkspaceFolder();
  if (activeWorkspaceFolder) {
    return activeWorkspaceFolder;
  }

  const workspaceFolders = vscode.workspace.workspaceFolders ?? [];
  if (workspaceFolders.length === 0) {
    vscode.window.showErrorMessage("Open a workspace folder before running with workspace context.");
    return undefined;
  }
  if (workspaceFolders.length === 1) {
    return workspaceFolders[0];
  }

  const selected = await vscode.window.showQuickPick(
    workspaceFolders.map((workspaceFolder) => ({
      label: workspaceFolder.name,
      description: workspaceFolder.uri.fsPath,
      workspaceFolder,
    })),
    {
      title: "Run Skill Capability",
      placeHolder: "Select workspace for git diff context",
      ignoreFocusOut: true,
    },
  );
  return selected?.workspaceFolder;
}

function getWorkspaceContextSettings(): {
  confirmLargeUploads: boolean;
  maxFiles: number;
  maxTotalBytes: number;
} {
  const configuration = vscode.workspace.getConfiguration(configurationSection);
  return {
    confirmLargeUploads: configuration.get<boolean>("confirmLargeUploads", true),
    maxFiles: configuration.get<number>("maxFiles", 20),
    maxTotalBytes: configuration.get<number>("maxTotalBytes", 300000),
  };
}

function shouldConfirmWorkspaceUpload(capability: PublicCapability): boolean {
  const settings = getWorkspaceContextSettings();
  return settings.confirmLargeUploads
    || capability.approval_policy.upload_context === "user_confirm_large";
}

async function confirmWorkspaceUpload(
  workspace: PublicWorkspaceContext,
  workspaceFolder?: vscode.WorkspaceFolder,
): Promise<boolean> {
  const summary = summarizeWorkspaceContext(workspace, workspaceFolder);
  const choice = await vscode.window.showWarningMessage(
    `Send workspace context to Skill Gateway? ${summary}.`,
    { modal: true },
    "Send context",
  );
  return choice === "Send context";
}

function summarizeWorkspaceContext(
  workspace: PublicWorkspaceContext,
  workspaceFolder?: vscode.WorkspaceFolder,
): string {
  const fileCount = workspace.files?.length ?? 0;
  const fileBytes = (workspace.files ?? [])
    .reduce((total, file) => total + byteLength(file.content), 0);
  const selectionBytes = workspace.selection ? byteLength(workspace.selection.content) : 0;
  const diffBytes = workspace.git_diff ? byteLength(workspace.git_diff) : 0;
  const totalBytes = fileBytes + selectionBytes + diffBytes;
  const parts: string[] = [];
  if (workspaceFolder) {
    parts.push(`workspace ${workspaceFolder.name}`);
  } else if (workspace.name) {
    parts.push(`workspace ${workspace.name}`);
  } else if (workspace.root_uri) {
    parts.push(`workspace ${workspace.root_uri}`);
  }
  if (fileCount > 0) {
    parts.push(`${fileCount} ${fileCount === 1 ? "file" : "files"}`);
  }
  if (workspace.selection) {
    parts.push("selection");
  }
  if (workspace.git_diff !== undefined) {
    parts.push("git diff");
  }
  parts.push(`${totalBytes} bytes`);
  return parts.join(", ");
}

function byteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

async function resolveCapability(
  treeProvider: TreeProviderLike,
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
      title: "Run Skill Capability",
      placeHolder: "Select a Gateway capability",
      ignoreFocusOut: true,
    },
  );

  return selected?.capability;
}

function hasWorkspaceContext(workspace: PublicWorkspaceContext): boolean {
  return Boolean(
    workspace.git_diff
      || workspace.selection
      || (workspace.files && workspace.files.length > 0)
      || workspace.name
      || workspace.root_uri
      || workspace.git_branch,
  );
}

type CapabilityCommandArgument = PublicCapability | CapabilityTreeNode | string | undefined;

interface TreeProviderLike {
  getCapabilities(): PublicCapability[];
  getCapability(id: string): PublicCapability | undefined;
}

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
    && Array.isArray(capability.input_modes);
}
