import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import Module from "node:module";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";

import { GatewayClientError, type PublicCapability } from "../api/client";
import type { CapabilityTreeNode } from "../capabilities/treeProvider";
import type { RunCommandDependencies } from "../commands/runCapability";

const execFileAsync = promisify(execFile);

test("runCurrentFile collects current editor context, calls Gateway, and renders report", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const documentPath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(documentPath, "const unsafe = '<html>';\n");

    const harness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "const unsafe = '<html>';\n",
        selectionText: "const unsafe = '<html>';",
        selectionEmpty: false,
      },
      confirmResponse: "Send context",
      confirmLargeUploads: false,
    });

    await harness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

    assert.deepEqual(harness.warnings, []);
    assert.equal(harness.calls.length, 1);
    assert.equal(harness.calls[0].capabilityId, "backend-rbac-review");
    assert.deepEqual(harness.calls[0].request, {
      instruction: "Review escaping",
      workspace: {
        files: [{ path: "src/app.ts", content: "const unsafe = '<html>';\n" }],
        selection: {
          path: "src/app.ts",
          start_line: 1,
          end_line: 1,
          content: "const unsafe = '<html>';",
        },
      },
      client: {
        type: "vscode",
        version: "0.1.0",
      },
    });
    assert.deepEqual(harness.rendered, [
      {
        task_id: "task-123",
        status: "completed",
        result: { summary: "Done", internal: "private" },
      },
    ]);
  });
});

test("runCurrentFile uses the document workspace folder in a multi-root workspace", async () => {
  await withTempWorkspace(async (firstRoot) => {
    await withTempWorkspace(async (secondRoot) => {
      const documentPath = path.join(secondRoot, "src", "app.ts");
      await writeTextFile(documentPath, "export const selectedRoot = true;\n");

      const harness = createRunHarness({
        workspaceFolders: [
          { name: "first", root: firstRoot },
          { name: "second", root: secondRoot },
        ],
        activeEditor: {
          documentPath,
          documentText: "export const selectedRoot = true;\n",
          selectionEmpty: true,
        },
        confirmResponse: "Send context",
        confirmLargeUploads: false,
      });

      await harness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

      assert.equal(harness.calls.length, 1);
      assert.deepEqual(requestWorkspace(harness.calls[0]).files, [
        { path: "src/app.ts", content: "export const selectedRoot = true;\n" },
      ]);
      assert.deepEqual(harness.errors, []);
    });
  });
});

test("runCurrentFile blocks Gateway call when collector errors leave empty workspace", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const documentPath = path.join(workspaceRoot, "private.pem");
    await writeTextFile(documentPath, "PRIVATE_KEY_SHOULD_NOT_UPLOAD");
    const harness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "PRIVATE_KEY_SHOULD_NOT_UPLOAD",
        selectionEmpty: true,
      },
      confirmLargeUploads: false,
    });

    await harness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

    assert.deepEqual(harness.calls, []);
    assert.deepEqual(harness.rendered, []);
    assert.match(harness.errors.join("\n"), /No workspace context could be collected/);
    assert.equal(JSON.stringify(harness.errors).includes("PRIVATE_KEY_SHOULD_NOT_UPLOAD"), false);
  });
});

test("context confirmation accept sends request and cancel does not send", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const documentPath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(documentPath, "abc\n");

    const acceptHarness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "abc\n",
        selectionEmpty: true,
      },
      confirmLargeUploads: true,
      confirmResponse: "Send context",
    });
    await acceptHarness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

    assert.equal(acceptHarness.calls.length, 1);
    assert.match(acceptHarness.confirmations[0], /1 file/);
    assert.match(acceptHarness.confirmations[0], /4 bytes/);

    const cancelHarness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "abc\n",
        selectionEmpty: true,
      },
      confirmLargeUploads: true,
      confirmResponse: undefined,
    });
    await cancelHarness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

    assert.deepEqual(cancelHarness.calls, []);
    assert.deepEqual(cancelHarness.rendered, []);
    assert.match(cancelHarness.confirmations[0], /1 file/);
    assert.match(cancelHarness.confirmations[0], /4 bytes/);
  });
});

test("runCurrentGitDiff uses the active editor workspace folder when present", async () => {
  await withTempWorkspace(async (firstRoot) => {
    await withTempWorkspace(async (secondRoot) => {
      await initializeGitWorkspace(secondRoot);
      const documentPath = path.join(secondRoot, "src", "app.ts");
      await writeTextFile(documentPath, "const changed = true;\n");

      const harness = createRunHarness({
        workspaceFolders: [
          { name: "first", root: firstRoot },
          { name: "second", root: secondRoot },
        ],
        activeEditor: {
          documentPath,
          documentText: "const changed = true;\n",
          selectionEmpty: true,
        },
        confirmResponse: "Send context",
        confirmLargeUploads: false,
      });

      await harness.runCurrentGitDiff(publicCapability({ approval_policy: { upload_context: "always" } }));

      assert.equal(harness.calls.length, 1);
      assert.match(requestWorkspace(harness.calls[0]).git_diff ?? "", /const changed = true/);
      assert.deepEqual(harness.errors, []);
    });
  });
});

test("runCurrentGitDiff asks for a workspace when multi-root has no active editor", async () => {
  await withTempWorkspace(async (firstRoot) => {
    await withTempWorkspace(async (secondRoot) => {
      await initializeGitWorkspace(firstRoot);
      await initializeGitWorkspace(secondRoot);
      await writeTextFile(path.join(firstRoot, "src", "app.ts"), "const firstRoot = true;\n");
      await writeTextFile(path.join(secondRoot, "src", "app.ts"), "const secondRoot = true;\n");

      const harness = createRunHarness({
        workspaceFolders: [
          { name: "first", root: firstRoot },
          { name: "second", root: secondRoot },
        ],
        workspacePickIndex: 1,
        confirmResponse: "Send context",
        confirmLargeUploads: false,
      });

      await harness.runCurrentGitDiff(publicCapability({ approval_policy: { upload_context: "always" } }));

      assert.equal(harness.calls.length, 1);
      assert.match(requestWorkspace(harness.calls[0]).git_diff ?? "", /const secondRoot = true/);
      assert.doesNotMatch(requestWorkspace(harness.calls[0]).git_diff ?? "", /const firstRoot = true/);
    });
  });
});

test("runCurrentGitDiff cancels when multi-root workspace selection is dismissed", async () => {
  await withTempWorkspace(async (firstRoot) => {
    await withTempWorkspace(async (secondRoot) => {
      const harness = createRunHarness({
        workspaceFolders: [
          { name: "first", root: firstRoot },
          { name: "second", root: secondRoot },
        ],
        workspacePickIndex: undefined,
        confirmLargeUploads: false,
      });

      await harness.runCurrentGitDiff(publicCapability({ approval_policy: { upload_context: "always" } }));

      assert.deepEqual(harness.calls, []);
      assert.deepEqual(harness.rendered, []);
    });
  });
});

test("upload_context user_confirm_large confirms even when confirmLargeUploads is false", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const documentPath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(documentPath, "abc\n");

    const harness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "abc\n",
        selectionEmpty: true,
      },
      confirmLargeUploads: false,
      confirmResponse: undefined,
    });

    await harness.runCurrentFile(publicCapability());

    assert.deepEqual(harness.calls, []);
    assert.deepEqual(harness.rendered, []);
    assert.match(harness.confirmations[0], /workspace/);
    assert.match(harness.confirmations[0], /1 file/);
    assert.match(harness.confirmations[0], /4 bytes/);
  });
});

test("Gateway errors do not render a report and show an error message", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const documentPath = path.join(workspaceRoot, "src", "app.ts");
    await writeTextFile(documentPath, "abc\n");
    const harness = createRunHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      activeEditor: {
        documentPath,
        documentText: "abc\n",
        selectionEmpty: true,
      },
      confirmResponse: "Send context",
      confirmLargeUploads: false,
      gatewayError: new GatewayClientError(500, "internal_server_error", "Runner failed."),
    });

    await harness.runCurrentFile(publicCapability({ approval_policy: { upload_context: "always" } }));

    assert.equal(harness.calls.length, 1);
    assert.deepEqual(harness.rendered, []);
    assert.deepEqual(harness.errors, ["Skill Gateway request failed: Runner failed."]);
  });
});

type ModuleLoader = (request: string, parent: unknown, isMain: boolean) => unknown;

async function withMockedVscode<T>(
  vscodeMock: unknown,
  run: () => Promise<T>,
): Promise<T> {
  const moduleWithLoad = Module as unknown as { _load: ModuleLoader };
  const originalLoad = moduleWithLoad._load;
  const commandPath = require.resolve("../commands/runCapability");

  delete require.cache[commandPath];
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
    delete require.cache[commandPath];
  }
}

function createRunHarness(options: VscodeMockOptions): RunHarness {
  const calls: Array<{ capabilityId: string; request: unknown }> = [];
  const rendered: unknown[] = [];
  const warnings = options.warnings ?? [];
  const errors = options.errors ?? [];
  const confirmations = options.confirmations ?? [];
  const normalizedOptions = {
    ...options,
    warnings,
    errors,
    confirmations,
  };
  const vscodeMock = createVscodeMock(normalizedOptions);

  return {
    calls,
    rendered,
    warnings,
    errors,
    confirmations,
    async runCurrentFile(capability: PublicCapability): Promise<void> {
      await withMockedVscode(vscodeMock, async () => {
        const { runCurrentFile } = require("../commands/runCapability") as RunCommandModule;
        await runCurrentFile(createTreeProvider([capability]), createDeps(normalizedOptions, calls, rendered), capability);
      });
    },
    async runCurrentGitDiff(capability: PublicCapability): Promise<void> {
      await withMockedVscode(vscodeMock, async () => {
        const { runCurrentGitDiff } = require("../commands/runCapability") as RunCommandModule;
        await runCurrentGitDiff(createTreeProvider([capability]), createDeps(normalizedOptions, calls, rendered), capability);
      });
    },
  };
}

function createDeps(
  options: VscodeMockOptions,
  calls: Array<{ capabilityId: string; request: unknown }>,
  rendered: unknown[],
): RunCommandDependencies {
  return {
    createClient: () => ({
      async runCapability(capabilityId: string, request: unknown): Promise<unknown> {
        calls.push({ capabilityId, request });
        if (options.gatewayError) {
          throw options.gatewayError;
        }
        return {
          task_id: "task-123",
          status: "completed",
          result: { summary: "Done", internal: "private" },
        };
      },
    }),
    renderReport(report: unknown): void {
      rendered.push(report);
    },
    clientVersion: "0.1.0",
  };
}

function createVscodeMock(options: VscodeMockOptions): unknown {
  const warnings = options.warnings ?? [];
  const errors = options.errors ?? [];
  const confirmations = options.confirmations ?? [];
  return {
    workspace: {
      workspaceFolders: options.workspaceFolders.map((folder) => toWorkspaceFolder(folder.name, folder.root)),
      getWorkspaceFolder(uri: { fsPath: string }): WorkspaceFolderMock | undefined {
        const fsPath = path.resolve(uri.fsPath);
        return options.workspaceFolders
          .map((folder) => toWorkspaceFolder(folder.name, folder.root))
          .find((folder) => isWithin(fsPath, folder.uri.fsPath));
      },
      getConfiguration(section: string): MockConfiguration {
        assert.equal(section, "skillCapability");
        return {
          get<T>(key: string, defaultValue: T): T {
            if (key === "maxFiles") {
              return (options.maxFiles ?? 20) as T;
            }
            if (key === "maxTotalBytes") {
              return (options.maxTotalBytes ?? 300000) as T;
            }
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
            getText(range?: unknown): string {
              return range
                ? options.activeEditor?.selectionText ?? ""
                : options.activeEditor?.documentText ?? "";
            },
          },
          selection: {
            isEmpty: options.activeEditor.selectionEmpty,
            start: { line: 0 },
            end: { line: 0 },
          },
        }
        : undefined,
      async showInputBox(): Promise<string> {
        return options.input ?? "Review escaping";
      },
      showWarningMessage(message: string, ...items: unknown[]): Promise<unknown> {
        if (items.length > 0) {
          confirmations.push(message);
          return Promise.resolve(options.confirmResponse);
        }
        warnings.push(message);
        return Promise.resolve(undefined);
      },
      showErrorMessage(message: string): Promise<undefined> {
        errors.push(message);
        return Promise.resolve(undefined);
      },
      showInformationMessage(): Promise<undefined> {
        return Promise.resolve(undefined);
      },
      async showQuickPick<T>(items: readonly T[]): Promise<T | undefined> {
        if (items.every((item) => isWorkspaceQuickPickItem(item))) {
          if (options.workspacePickIndex === undefined) {
            return undefined;
          }
          return items[options.workspacePickIndex];
        }
        return items[0];
      },
      createWebviewPanel(): never {
        throw new Error("renderReport should be injected in this test");
      },
      createOutputChannel(): Disposable {
        return { dispose() {} };
      },
    },
    version: "1.90.0",
    ViewColumn: {
      Beside: 2,
    },
  };
}

function createTreeProvider(capabilities: PublicCapability[]): TreeProviderLike {
  return {
    getCapabilities(): PublicCapability[] {
      return capabilities;
    },
    getCapability(id: string): PublicCapability | undefined {
      return capabilities.find((capability) => capability.id === id);
    },
  };
}

function publicCapability(overrides: Partial<PublicCapability> = {}): PublicCapability {
  return {
    id: "backend-rbac-review",
    name: "Backend RBAC Review",
    version: "0.1.0",
    visible_description: "Review backend RBAC and public API payload boundaries.",
    input_modes: ["current_file", "git_diff"],
    input_schema: { type: "object" },
    output_schema: { type: "object" },
    client_permissions: {
      reads_workspace: true,
      sends_code_to_server: true,
    },
    approval_policy: {
      upload_context: "user_confirm_large",
    },
    ...overrides,
  };
}

function requestWorkspace(call: { request: unknown }): {
  files?: Array<{ path: string; content: string }>;
  git_diff?: string;
} {
  assert.equal(typeof call.request, "object");
  assert.notEqual(call.request, null);
  const request = call.request as { workspace?: unknown };
  assert.equal(typeof request.workspace, "object");
  assert.notEqual(request.workspace, null);
  return request.workspace as {
    files?: Array<{ path: string; content: string }>;
    git_diff?: string;
  };
}

async function withTempWorkspace(run: (workspaceRoot: string) => Promise<void>): Promise<void> {
  const workspaceRoot = await mkdtemp(path.join(tmpdir(), "skill-capability-command-"));
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

async function initializeGitWorkspace(workspaceRoot: string): Promise<void> {
  const filePath = path.join(workspaceRoot, "src", "app.ts");
  await writeTextFile(filePath, "const changed = false;\n");
  await execFileAsync("git", ["init"], { cwd: workspaceRoot });
  await execFileAsync("git", ["add", "src/app.ts"], { cwd: workspaceRoot });
  await execFileAsync(
    "git",
    ["-c", "user.email=test@example.com", "-c", "user.name=Test User", "commit", "-m", "initial"],
    { cwd: workspaceRoot },
  );
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

interface RunHarness {
  calls: Array<{ capabilityId: string; request: unknown }>;
  rendered: unknown[];
  warnings: string[];
  errors: string[];
  confirmations: string[];
  runCurrentFile(capability: PublicCapability): Promise<void>;
  runCurrentGitDiff(capability: PublicCapability): Promise<void>;
}

interface VscodeMockOptions {
  workspaceFolders: Array<{ name: string; root: string }>;
  activeEditor?: {
    documentPath: string;
    documentText: string;
    selectionText?: string;
    selectionEmpty: boolean;
  };
  input?: string;
  warnings?: string[];
  errors?: string[];
  confirmations?: string[];
  confirmResponse?: string;
  confirmLargeUploads?: boolean;
  maxFiles?: number;
  maxTotalBytes?: number;
  gatewayError?: unknown;
  workspacePickIndex?: number;
}

interface RunCommandModule {
  runCurrentFile(
    treeProvider: TreeProviderLike,
    deps: RunCommandDependencies,
    capability?: PublicCapability | CapabilityTreeNode | string,
  ): Promise<void>;
  runCurrentGitDiff(
    treeProvider: TreeProviderLike,
    deps: RunCommandDependencies,
    capability?: PublicCapability | CapabilityTreeNode | string,
  ): Promise<void>;
}

interface WorkspaceFolderMock {
  name: string;
  uri: {
    fsPath: string;
    toString(): string;
  };
}

interface TreeProviderLike {
  getCapabilities(): PublicCapability[];
  getCapability(id: string): PublicCapability | undefined;
}

interface Disposable {
  dispose(): void;
}

interface MockConfiguration {
  get<T>(key: string, defaultValue: T): T;
}

function isWorkspaceQuickPickItem(value: unknown): value is { workspaceFolder: WorkspaceFolderMock } {
  return Boolean(value)
    && typeof value === "object"
    && Boolean((value as { workspaceFolder?: unknown }).workspaceFolder);
}
