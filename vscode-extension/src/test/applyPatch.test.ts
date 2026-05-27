import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import Module from "node:module";
import path from "node:path";
import test from "node:test";

import type { CapabilityRunResponse } from "../api/client";
import type { RunCommandDependencies } from "../commands/runCapability";
import { applyUnifiedDiffToWorkspace, planUnifiedDiffApply } from "../patch/applyPatch";

test("unified diff patch plans and applies to a workspace file", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "export const value = 'old';\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1 @@",
      "-export const value = 'old';",
      "+export const value = 'new';",
      "",
    ].join("\n");

    const plan = await planUnifiedDiffApply(workspaceRoot, patch);
    assert.deepEqual(plan.edits.map((edit) => edit.relativePath), ["src/app.ts"]);
    assert.equal(plan.edits[0].newText, "export const value = 'new';\n");

    await applyUnifiedDiffToWorkspace(workspaceRoot, patch);

    assert.equal(await readFile(filePath, "utf8"), "export const value = 'new';\n");
  });
});

test("plain unified diff without git header plans and applies", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const patch = [
      "--- src/app.ts",
      "+++ src/app.ts",
      "@@ -1 +1 @@",
      "-old",
      "+new",
      "",
    ].join("\n");

    await applyUnifiedDiffToWorkspace(workspaceRoot, patch);

    assert.equal(await readFile(filePath, "utf8"), "new\n");
  });
});

test("zero-context insertion hunk applies after the declared old line", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "a\nb\nc\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -2,0 +3 @@",
      "+inserted",
      "",
    ].join("\n");

    await applyUnifiedDiffToWorkspace(workspaceRoot, patch);

    assert.equal(await readFile(filePath, "utf8"), "a\nb\ninserted\nc\n");
  });
});

test("hunk old count mismatch rejects and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\nkeep\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1,2 +1 @@",
      "-old",
      "+new",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /hunk line count does not match header/,
    );

    assert.equal(await readFile(filePath, "utf8"), "old\nkeep\n");
  });
});

test("hunk new count mismatch rejects and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1,2 @@",
      "-old",
      "+new",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /hunk line count does not match header/,
    );

    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("EOF no-newline marker rejects and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1 @@",
      "-old",
      "\\ No newline at end of file",
      "+new",
      "\\ No newline at end of file",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /No newline at end of file marker is not supported/,
    );

    assert.equal(await readFile(filePath, "utf8"), "old");
  });
});

test("duplicate file sections reject and do not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1 @@",
      "-old",
      "+middle",
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1 @@",
      "-old",
      "+new",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /Duplicate patch target/,
    );

    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("path traversal patch is rejected and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const insidePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(insidePath, "inside\n");
    const escapeName = `${path.basename(workspaceRoot)}-escape.txt`;
    const escapePath = path.join(path.dirname(workspaceRoot), escapeName);
    await writeFile(escapePath, "outside\n");
    const patch = [
      `diff --git a/../${escapeName} b/../${escapeName}`,
      `--- a/../${escapeName}`,
      `+++ b/../${escapeName}`,
      "@@ -1 +1 @@",
      "-outside",
      "+changed",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /outside the workspace/,
    );

    assert.equal(await readFile(insidePath, "utf8"), "inside\n");
    assert.equal(await readFile(escapePath, "utf8"), "outside\n");
    await rm(escapePath, { force: true });
  });
});

test("denylisted patch path is rejected and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const envPath = path.join(workspaceRoot, ".env");
    await writeFile(envPath, "TOKEN=old\n");
    const patch = [
      "diff --git a/.env b/.env",
      "--- a/.env",
      "+++ b/.env",
      "@@ -1 +1 @@",
      "-TOKEN=old",
      "+TOKEN=new",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /denied by workspace context policy/,
    );

    assert.equal(await readFile(envPath, "utf8"), "TOKEN=old\n");
  });
});

test("denylisted patch paths are rejected case-insensitively", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    for (const relativePath of [".ENV", "PRIVATE.KEY", ".GIT/config"]) {
      const patch = changePatch(relativePath, "old", "new");

      await assert.rejects(
        () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
        /denied by workspace context policy/,
        `${relativePath} should be denied`,
      );
    }
  });
});

test("hunk context mismatch is rejected and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "export const value = 'current';\n");
    const patch = [
      "diff --git a/src/app.ts b/src/app.ts",
      "--- a/src/app.ts",
      "+++ b/src/app.ts",
      "@@ -1 +1 @@",
      "-export const value = 'old';",
      "+export const value = 'new';",
      "",
    ].join("\n");

    await assert.rejects(
      () => applyUnifiedDiffToWorkspace(workspaceRoot, patch),
      /does not match/,
    );

    assert.equal(await readFile(filePath, "utf8"), "export const value = 'current';\n");
  });
});

test("remembered workspace folder removed from current workspace does not preview or apply", async () => {
  await withTempWorkspace(async (rememberedRoot) => {
    await withTempWorkspace(async (currentRoot) => {
      const filePath = path.join(rememberedRoot, "src", "app.ts");
      await writeTextFile(filePath, "old\n");
      const harness = createApplyHarness({
        workspaceFolders: [{ name: "current", root: currentRoot }],
        confirmResponse: "Apply patch",
      });
      harness.rememberPatch(
        completedReportWithPatch(changePatch("src/app.ts", "old", "new")),
        toWorkspaceFolder("remembered", rememberedRoot),
      );

      await harness.applyLastPatch();

      assert.equal(harness.applyEditCalls, 0);
      assert.deepEqual(harness.previews, []);
      assert.match(harness.errors.join("\n"), /no longer open/i);
      assert.equal(await readFile(filePath, "utf8"), "old\n");
    });
  });
});

test("apply command cancel confirmation does not call applyEdit", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      confirmResponse: undefined,
    });
    harness.rememberPatch(completedReportWithPatch(changePatch("src/app.ts", "old", "new")), toWorkspaceFolder("workspace", workspaceRoot));

    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 0);
    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("apply command rejects dirty open documents without applying", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      confirmResponse: "Apply patch",
      openDocuments: {
        [filePath]: { text: "unsaved\n", isDirty: true },
      },
    });
    harness.rememberPatch(completedReportWithPatch(changePatch("src/app.ts", "old", "new")), toWorkspaceFolder("workspace", workspaceRoot));

    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 0);
    assert.match(harness.errors.join("\n"), /unsaved changes/i);
    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("apply command rejects open document text that differs from planned disk text", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      confirmResponse: "Apply patch",
      openDocuments: {
        [filePath]: { text: "buffer changed\n", isDirty: false },
      },
    });
    harness.rememberPatch(completedReportWithPatch(changePatch("src/app.ts", "old", "new")), toWorkspaceFolder("workspace", workspaceRoot));

    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 0);
    assert.match(harness.errors.join("\n"), /changed since the patch was planned/i);
    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("no last patch shows information and does not write", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      confirmResponse: "Apply patch",
    });

    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 0);
    assert.deepEqual(harness.infos, ["No completed capability patch is available to apply."]);
    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("completed run without patch clears the remembered patch", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      confirmResponse: "Apply patch",
    });
    harness.rememberPatch(completedReportWithPatch(changePatch("src/app.ts", "old", "new")), toWorkspaceFolder("workspace", workspaceRoot));
    harness.rememberPatch(completedReportWithoutPatch(), toWorkspaceFolder("workspace", workspaceRoot));

    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 0);
    assert.deepEqual(harness.infos, ["No completed capability patch is available to apply."]);
    assert.equal(await readFile(filePath, "utf8"), "old\n");
  });
});

test("patch from run report is remembered after successful run and apply command can use it", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(filePath, "old\n");
    const patch = changePatch("src/app.ts", "old", "new");
    const harness = createApplyHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath: filePath,
        documentText: "old\n",
        selectionEmpty: true,
      },
      runReport: completedReportWithPatch(patch),
      confirmResponse: "Apply patch",
      confirmLargeUploads: false,
    });

    await harness.runCurrentFileAndRememberPatch();
    await harness.applyLastPatch();

    assert.equal(harness.applyEditCalls, 1);
    assert.equal(await readFile(filePath, "utf8"), "new\n");
    assert.deepEqual(harness.renderedReports, [completedReportWithPatch(patch)]);
  });
});

type ModuleLoader = (request: string, parent: unknown, isMain: boolean) => unknown;

async function withMockedVscode<T>(
  vscodeMock: unknown,
  modulePaths: string[],
  run: () => Promise<T>,
): Promise<T> {
  const moduleWithLoad = Module as unknown as { _load: ModuleLoader };
  const originalLoad = moduleWithLoad._load;
  for (const modulePath of modulePaths) {
    delete require.cache[require.resolve(modulePath)];
  }
  moduleWithLoad._load = (request: string, parent: unknown, isMain: boolean) => {
    if (request === "vscode") {
      return vscodeMock;
    }
    return originalLoad(request, parent, isMain);
  };

  try {
    return await run();
  } finally {
    moduleWithLoad._load = originalLoad;
    for (const modulePath of modulePaths) {
      delete require.cache[require.resolve(modulePath)];
    }
  }
}

function createApplyHarness(options: ApplyHarnessOptions): ApplyHarness {
  const infos: string[] = [];
  const errors: string[] = [];
  const previews: string[] = [];
  const renderedReports: unknown[] = [];
  let applyEditCalls = 0;
  const vscodeMock = createVscodeMock(options, {
    infos,
    errors,
    previews,
    applyEditCalled: () => {
      applyEditCalls += 1;
    },
  });
  const applyCommandModule = require("../commands/applyPatch") as ApplyCommandModule;
  applyCommandModule.clearRememberedPatch();

  return {
    infos,
    errors,
    previews,
    renderedReports,
    get applyEditCalls(): number {
      return applyEditCalls;
    },
    rememberPatch(report: CapabilityRunResponse, workspaceFolder: WorkspaceFolderMock): void {
      applyCommandModule.rememberRunPatch(report, workspaceFolder);
    },
    async applyLastPatch(): Promise<void> {
      await withVscodeMock(vscodeMock, async () => {
        await applyCommandModule.applyLastPatch();
      });
    },
    async runCurrentFileAndRememberPatch(): Promise<void> {
      await withMockedVscode(vscodeMock, [
        "../commands/runCapability",
        "../patch/diffPreview",
      ], async () => {
        const { runCurrentFile } = require("../commands/runCapability") as RunCommandModule;
        const workspaceFolder = toWorkspaceFolder("workspace", options.workspaceFolders[0].root);
        const deps: RunCommandDependencies = {
          createClient: () => ({
            async runCapability(): Promise<unknown> {
              return options.runReport;
            },
          }),
          renderReport(report: unknown): void {
            renderedReports.push(report);
          },
          rememberPatch: (report: unknown, runWorkspaceFolder) => applyCommandModule.rememberRunPatch(
            report as CapabilityRunResponse,
            runWorkspaceFolder ?? workspaceFolder,
          ),
          clientVersion: "0.1.0",
        };
        await runCurrentFile(createTreeProvider(), deps, publicCapability());
      });
    },
  };
}

async function withVscodeMock<T>(
  vscodeMock: unknown,
  run: () => Promise<T>,
): Promise<T> {
  const moduleWithLoad = Module as unknown as { _load: ModuleLoader };
  const originalLoad = moduleWithLoad._load;
  moduleWithLoad._load = (request: string, parent: unknown, isMain: boolean) => {
    if (request === "vscode") {
      return vscodeMock;
    }
    return originalLoad(request, parent, isMain);
  };
  try {
    return await run();
  } finally {
    moduleWithLoad._load = originalLoad;
  }
}

function createVscodeMock(
  options: ApplyHarnessOptions,
  calls: {
    infos: string[];
    errors: string[];
    previews: string[];
    applyEditCalled(): void;
  },
): unknown {
  return {
    Uri: {
      file(filePath: string): UriMock {
        return { fsPath: filePath };
      },
    },
    Range: class RangeMock {
      constructor(
        readonly startLine: number,
        readonly startCharacter: number,
        readonly endLine: number,
        readonly endCharacter: number,
      ) {}
    },
    WorkspaceEdit: class WorkspaceEditMock {
      readonly replacements: Array<{ uri: UriMock; text: string }> = [];
      replace(uri: UriMock, _range: unknown, text: string): void {
        this.replacements.push({ uri, text });
      }
    },
    workspace: {
      workspaceFolders: options.workspaceFolders.map((folder) => toWorkspaceFolder(folder.name, folder.root)),
      async openTextDocument(arg: UriMock | { content: string; language: string }): Promise<TextDocumentMock> {
        if ("content" in arg) {
          calls.previews.push(arg.content);
          return {
            uri: { fsPath: "preview.patch" },
            getText: () => arg.content,
            lineAt: () => ({ range: {} }),
            lineCount: 1,
          };
        }
        const text = await readFile(arg.fsPath, "utf8");
        const openDocument = options.openDocuments?.[arg.fsPath];
        return {
          uri: arg,
          getText: () => openDocument?.text ?? text,
          isDirty: openDocument?.isDirty ?? false,
          lineAt: (line: number) => ({ range: { end: { line, character: line === 0 ? text.length : 0 } } }),
          lineCount: text.split(/\r?\n/).length,
        };
      },
      async applyEdit(edit: { replacements: Array<{ uri: UriMock; text: string }> }): Promise<boolean> {
        calls.applyEditCalled();
        for (const replacement of edit.replacements) {
          await writeFile(replacement.uri.fsPath, replacement.text);
        }
        return true;
      },
      getWorkspaceFolder(uri: UriMock): WorkspaceFolderMock | undefined {
        const fsPath = path.resolve(uri.fsPath);
        return options.workspaceFolders
          .map((folder) => toWorkspaceFolder(folder.name, folder.root))
          .find((folder) => isWithin(fsPath, folder.uri.fsPath));
      },
      getConfiguration(): MockConfiguration {
        return {
          get<T>(key: string, defaultValue: T): T {
            if (key === "confirmLargeUploads") {
              return (options.confirmLargeUploads ?? false) as T;
            }
            return defaultValue;
          },
        };
      },
    },
    window: {
      activeTextEditor: options.activeEditor
        ? {
          document: {
            uri: { fsPath: options.activeEditor.documentPath },
            getText: () => options.activeEditor?.documentText ?? "",
          },
          selection: {
            isEmpty: options.activeEditor.selectionEmpty,
            start: { line: 0 },
            end: { line: 0 },
          },
        }
        : undefined,
      async showTextDocument(): Promise<void> {},
      async showWarningMessage(_message: string, _options: unknown, action: string): Promise<string | undefined> {
        assert.equal(action, "Apply patch");
        return options.confirmResponse;
      },
      async showInformationMessage(message: string): Promise<undefined> {
        calls.infos.push(message);
        return undefined;
      },
      async showErrorMessage(message: string): Promise<undefined> {
        calls.errors.push(message);
        return undefined;
      },
      async showInputBox(): Promise<string> {
        return "Patch this file";
      },
      async showQuickPick<T>(items: readonly T[]): Promise<T | undefined> {
        return items[0];
      },
    },
    ViewColumn: {
      Beside: 2,
    },
    version: "1.90.0",
  };
}

function completedReportWithPatch(patch: string): CapabilityRunResponse {
  return {
    task_id: "task-patch",
    status: "completed",
    result: {
      summary: "Done",
      patch,
    },
  };
}

function completedReportWithoutPatch(): CapabilityRunResponse {
  return {
    task_id: "task-no-patch",
    status: "completed",
    result: {
      summary: "Done",
    },
  };
}

function changePatch(relativePath: string, oldText: string, newText: string): string {
  return [
    `diff --git a/${relativePath} b/${relativePath}`,
    `--- a/${relativePath}`,
    `+++ b/${relativePath}`,
    "@@ -1 +1 @@",
    `-${oldText}`,
    `+${newText}`,
    "",
  ].join("\n");
}

async function withTempWorkspace(run: (workspaceRoot: string) => Promise<void>): Promise<void> {
  const workspaceRoot = await mkdtemp(path.join(tmpdir(), "skill-capability-patch-"));
  try {
    await run(workspaceRoot);
  } finally {
    await rm(workspaceRoot, { recursive: true, force: true });
  }
}

async function writeTextFile(filePath: string, content: string): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content);
}

function toWorkspaceFolder(name: string, root: string): WorkspaceFolderMock {
  return {
    name,
    uri: {
      fsPath: root,
      toString: () => `file://${root}`,
    },
  };
}

function isWithin(child: string, parent: string): boolean {
  const relative = path.relative(path.resolve(parent), child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function createTreeProvider(): TreeProviderLike {
  const capability = publicCapability();
  return {
    getCapabilities: () => [capability],
    getCapability: () => capability,
  };
}

function publicCapability(): PublicCapabilityLike {
  return {
    id: "backend-rbac-review",
    name: "Backend RBAC Review",
    version: "0.1.0",
    visible_description: "Review backend RBAC and public API payload boundaries.",
    input_modes: ["current_file"],
    input_schema: { type: "object" },
    output_schema: { type: "object" },
    client_permissions: {},
    approval_policy: { upload_context: "always" },
  };
}

interface ApplyHarness {
  infos: string[];
  errors: string[];
  previews: string[];
  renderedReports: unknown[];
  applyEditCalls: number;
  rememberPatch(report: CapabilityRunResponse, workspaceFolder: WorkspaceFolderMock): void;
  applyLastPatch(): Promise<void>;
  runCurrentFileAndRememberPatch(): Promise<void>;
}

interface ApplyHarnessOptions {
  workspaceFolders: Array<{ name: string; root: string }>;
  activeEditor?: {
    documentPath: string;
    documentText: string;
    selectionEmpty: boolean;
  };
  runReport?: CapabilityRunResponse;
  confirmResponse?: string;
  confirmLargeUploads?: boolean;
  openDocuments?: Record<string, { text: string; isDirty: boolean }>;
}

interface ApplyCommandModule {
  rememberRunPatch(report: CapabilityRunResponse, workspaceFolder?: WorkspaceFolderMock): void;
  clearRememberedPatch(): void;
  applyLastPatch(): Promise<void>;
}

interface RunCommandModule {
  runCurrentFile(
    treeProvider: TreeProviderLike,
    deps: RunCommandDependencies,
    capability?: PublicCapabilityLike,
  ): Promise<void>;
}

interface TreeProviderLike {
  getCapabilities(): PublicCapabilityLike[];
  getCapability(id: string): PublicCapabilityLike | undefined;
}

interface PublicCapabilityLike {
  id: string;
  name: string;
  version: string;
  visible_description: string;
  input_modes: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  client_permissions: Record<string, unknown>;
  approval_policy: Record<string, unknown>;
}

interface WorkspaceFolderMock {
  name: string;
  uri: {
    fsPath: string;
    toString(): string;
  };
}

interface UriMock {
  fsPath: string;
}

interface TextDocumentMock {
  uri: UriMock;
  getText(): string;
  isDirty?: boolean;
  lineAt(line: number): { range: unknown };
  lineCount: number;
}

interface MockConfiguration {
  get<T>(key: string, defaultValue: T): T;
}
