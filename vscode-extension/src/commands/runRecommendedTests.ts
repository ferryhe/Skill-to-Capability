import type * as vscode from "vscode";
import path from "node:path";

import type { CapabilityRunResponse } from "../api/client";

interface RememberedRecommendedTests {
  commands: string[];
  workspaceFolder?: vscode.WorkspaceFolder;
}

type RecommendedTestQuickPickItem = vscode.QuickPickItem & {
  command: string;
};

let lastRecommendedTests: RememberedRecommendedTests | undefined;

export function registerRecommendedTestsCommand(context: vscode.ExtensionContext): void {
  const vscodeApi = require("vscode") as typeof vscode;
  context.subscriptions.push(
    vscodeApi.commands.registerCommand(
      "skillCapability.runRecommendedTests",
      () => runRecommendedTests(),
    ),
  );
}

export function rememberRunRecommendedTests(
  report: CapabilityRunResponse | unknown,
  workspaceFolder?: vscode.WorkspaceFolder,
): void {
  lastRecommendedTests = undefined;
  if (!isCompletedRunReport(report)) {
    return;
  }

  const commands = extractRecommendedTests(report.result);
  if (commands.length === 0) {
    return;
  }

  lastRecommendedTests = {
    commands,
    workspaceFolder,
  };
}

export function clearRememberedRecommendedTests(): void {
  lastRecommendedTests = undefined;
}

export async function runRecommendedTests(): Promise<void> {
  const vscodeApi = require("vscode") as typeof vscode;
  if (!lastRecommendedTests) {
    await vscodeApi.window.showInformationMessage("No completed capability recommended tests are available to run.");
    return;
  }

  const workspaceFolder = await resolveRecommendedTestsWorkspaceFolder(lastRecommendedTests.workspaceFolder);
  if (!workspaceFolder) {
    return;
  }

  const selectedTests = await vscodeApi.window.showQuickPick(
    lastRecommendedTests.commands.map((command) => ({
      label: command,
      command,
    })),
    {
      title: "Run Recommended Tests",
      placeHolder: "Select recommended test commands to run",
      canPickMany: true,
      ignoreFocusOut: true,
    },
  ) as RecommendedTestQuickPickItem[] | undefined;
  if (!selectedTests || selectedTests.length === 0) {
    return;
  }

  const selectedCommands = selectedTests.map((test) => test.command);
  const choice = await vscodeApi.window.showWarningMessage(
    confirmationMessage(selectedCommands, workspaceFolder),
    { modal: true },
    "Run tests",
  );
  if (choice !== "Run tests") {
    return;
  }

  const terminal = vscodeApi.window.createTerminal({
    name: "Skill Capability Tests",
    cwd: workspaceFolder.uri.fsPath,
  });
  terminal.show();
  for (const command of selectedCommands) {
    terminal.sendText(command, true);
  }
}

async function resolveRecommendedTestsWorkspaceFolder(
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
        `The workspace for the remembered recommended tests (${rememberedWorkspaceFolder.name}) is no longer open.`,
      );
      return undefined;
    }
    return matchingWorkspaceFolder;
  }

  if (workspaceFolders.length === 0) {
    await vscodeApi.window.showErrorMessage("Open a workspace folder before running recommended tests.");
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
      title: "Run Recommended Tests",
      placeHolder: "Select workspace for recommended tests",
      ignoreFocusOut: true,
    },
  );
  return selected?.workspaceFolder;
}

function confirmationMessage(
  commands: string[],
  workspaceFolder: vscode.WorkspaceFolder,
): string {
  const count = commands.length;
  const noun = count === 1 ? "command" : "commands";
  return [
    `Run ${count} recommended test ${noun} in workspace ${workspaceFolder.name}?`,
    "",
    ...commands,
  ].join("\n");
}

function extractRecommendedTests(result: unknown): string[] {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    return [];
  }

  const recommendedTests = (result as { recommended_tests?: unknown }).recommended_tests;
  if (!Array.isArray(recommendedTests)) {
    return [];
  }

  return recommendedTests
    .filter((command): command is string => typeof command === "string")
    .map((command) => command.trim())
    .filter((command) => !/[\r\n]/.test(command))
    .filter((command) => command.length > 0);
}

function sameFsPath(left: string, right: string): boolean {
  return pathForCompare(left) === pathForCompare(right);
}

function pathForCompare(value: string): string {
  const normalized = path.resolve(value);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function isCompletedRunReport(value: unknown): value is CapabilityRunResponse {
  return Boolean(value)
    && typeof value === "object"
    && (value as { status?: unknown }).status === "completed";
}
