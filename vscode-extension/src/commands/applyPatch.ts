import type * as vscode from "vscode";
import path from "node:path";

import type { CapabilityRunResponse } from "../api/client";
import { planUnifiedDiffApply } from "../patch/applyPatch";
import { showPatchPreview } from "../patch/diffPreview";

interface RememberedPatch {
  patch: string;
  workspaceFolder?: vscode.WorkspaceFolder;
}

let lastPatch: RememberedPatch | undefined;

export function registerApplyPatchCommand(context: vscode.ExtensionContext): void {
  const vscodeApi = require("vscode") as typeof vscode;
  context.subscriptions.push(
    vscodeApi.commands.registerCommand(
      "skillCapability.applyLastPatch",
      () => applyLastPatch(),
    ),
  );
}

export function rememberRunPatch(
  report: CapabilityRunResponse | unknown,
  workspaceFolder?: vscode.WorkspaceFolder,
): void {
  if (!isCompletedRunReport(report)) {
    return;
  }
  lastPatch = undefined;
  const patch = extractPatch(report.result);
  if (!patch) {
    return;
  }
  lastPatch = {
    patch,
    workspaceFolder,
  };
}

export function clearRememberedPatch(): void {
  lastPatch = undefined;
}

export async function applyLastPatch(): Promise<void> {
  const vscodeApi = require("vscode") as typeof vscode;
  if (!lastPatch) {
    await vscodeApi.window.showInformationMessage("No completed capability patch is available to apply.");
    return;
  }

  const workspaceFolder = await resolveApplyWorkspaceFolder(lastPatch.workspaceFolder);
  if (!workspaceFolder) {
    return;
  }

  await showPatchPreview(lastPatch.patch);
  const choice = await vscodeApi.window.showWarningMessage(
    `Apply last capability patch to workspace ${workspaceFolder.name}?`,
    { modal: true },
    "Apply patch",
  );
  if (choice !== "Apply patch") {
    return;
  }

  try {
    const plan = await planUnifiedDiffApply(workspaceFolder.uri.fsPath, lastPatch.patch);
    const edit = new vscodeApi.WorkspaceEdit();
    for (const plannedEdit of plan.edits) {
      const uri = vscodeApi.Uri.file(plannedEdit.absolutePath);
      const document = await vscodeApi.workspace.openTextDocument(uri);
      if (document.isDirty) {
        throw new Error(`${plannedEdit.relativePath} has unsaved changes. Save or discard them before applying the patch.`);
      }
      if (document.getText() !== plannedEdit.oldText) {
        throw new Error(`${plannedEdit.relativePath} changed since the patch was planned. Re-run the capability before applying.`);
      }
      edit.replace(uri, fullDocumentRange(vscodeApi, document), plannedEdit.newText);
    }
    const applied = await vscodeApi.workspace.applyEdit(edit);
    if (!applied) {
      await vscodeApi.window.showErrorMessage("VSCode did not apply the capability patch.");
      return;
    }
    await vscodeApi.window.showInformationMessage(`Applied capability patch to ${plan.edits.length} file(s).`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to apply capability patch.";
    await vscodeApi.window.showErrorMessage(message);
  }
}

async function resolveApplyWorkspaceFolder(
  rememberedWorkspaceFolder?: vscode.WorkspaceFolder,
): Promise<vscode.WorkspaceFolder | undefined> {
  const vscodeApi = require("vscode") as typeof vscode;
  const workspaceFolders = vscodeApi.workspace.workspaceFolders ?? [];
  if (rememberedWorkspaceFolder) {
    const matchingWorkspaceFolder = workspaceFolders.find((workspaceFolder) =>
      sameFsPath(workspaceFolder.uri.fsPath, rememberedWorkspaceFolder.uri.fsPath),
    );
    if (!matchingWorkspaceFolder) {
      await vscodeApi.window.showErrorMessage(
        `The workspace for the remembered capability patch (${rememberedWorkspaceFolder.name}) is no longer open.`,
      );
      return undefined;
    }
    return matchingWorkspaceFolder;
  }

  if (workspaceFolders.length === 0) {
    await vscodeApi.window.showErrorMessage("Open a workspace folder before applying a capability patch.");
    return undefined;
  }
  if (workspaceFolders.length === 1) {
    return workspaceFolders[0];
  }

  const selected = await vscodeApi.window.showQuickPick(
    workspaceFolders.map((workspaceFolder) => ({
      label: workspaceFolder.name,
      description: workspaceFolder.uri.fsPath,
      workspaceFolder,
    })),
    {
      title: "Apply Capability Patch",
      placeHolder: "Select workspace for patch apply",
      ignoreFocusOut: true,
    },
  );
  return selected?.workspaceFolder;
}

function sameFsPath(left: string, right: string): boolean {
  return pathForCompare(left) === pathForCompare(right);
}

function pathForCompare(value: string): string {
  const normalized = path.resolve(value);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function fullDocumentRange(
  vscodeApi: typeof vscode,
  document: vscode.TextDocument,
): vscode.Range {
  if (document.lineCount === 0) {
    return new vscodeApi.Range(0, 0, 0, 0);
  }
  const lastLine = document.lineAt(document.lineCount - 1);
  return new vscodeApi.Range(0, 0, document.lineCount - 1, lastLine.range.end.character);
}

function extractPatch(result: unknown): string | undefined {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    return undefined;
  }
  const patch = (result as { patch?: unknown }).patch;
  return typeof patch === "string" && patch.trim() ? patch : undefined;
}

function isCompletedRunReport(value: unknown): value is CapabilityRunResponse {
  return Boolean(value)
    && typeof value === "object"
    && (value as { status?: unknown }).status === "completed";
}
