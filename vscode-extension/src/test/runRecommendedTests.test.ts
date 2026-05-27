import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import Module from "node:module";
import path from "node:path";
import test from "node:test";

import type { CapabilityRunResponse } from "../api/client";

test("completed report with recommended tests is remembered and selected commands run in workspace terminal", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0, 1],
      confirmResponse: "Run tests",
    });

    harness.rememberTests(
      completedReportWithRecommendedTests(["npm.cmd run test:recommendedTests", "python scripts\\validate-contracts.py"]),
      toWorkspaceFolder("workspace", workspaceRoot),
    );
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, [
      {
        name: "Skill Capability Tests",
        cwd: workspaceRoot,
        shown: true,
        sentText: ["npm.cmd run test:recommendedTests", "python scripts\\validate-contracts.py"],
      },
    ]);
    assert.match(harness.confirmations[0], /workspace/);
    assert.match(harness.confirmations[0], /2 recommended test command/);
    assert.match(harness.confirmations[0], /npm\.cmd run test:recommendedTests/);
  });
});

test("cancel recommended test QuickPick does not create a terminal", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: undefined,
      confirmResponse: "Run tests",
    });

    harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("workspace", workspaceRoot));
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.deepEqual(harness.confirmations, []);
  });
});

test("empty recommended test QuickPick selection does not create a terminal", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [],
      confirmResponse: "Run tests",
    });

    harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("workspace", workspaceRoot));
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.deepEqual(harness.confirmations, []);
  });
});

test("cancel recommended test confirmation does not create a terminal", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0],
      confirmResponse: undefined,
    });

    harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("workspace", workspaceRoot));
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.match(harness.confirmations[0], /npm test/);
  });
});

test("completed run without recommended tests clears stale remembered tests", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0],
      confirmResponse: "Run tests",
    });

    harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("workspace", workspaceRoot));
    harness.rememberTests(completedReportWithoutRecommendedTests(), toWorkspaceFolder("workspace", workspaceRoot));
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.deepEqual(harness.infos, ["No completed capability recommended tests are available to run."]);
  });
});

test("non-completed run report clears stale remembered tests", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    for (const report of [queuedReport(), failedReport()]) {
      const harness = createRecommendedTestsHarness({
        workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
        testPickIndexes: [0],
        confirmResponse: "Run tests",
      });

      harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("workspace", workspaceRoot));
      harness.rememberTests(report, toWorkspaceFolder("workspace", workspaceRoot));
      await harness.runRecommendedTests();

      assert.deepEqual(harness.terminals, []);
      assert.deepEqual(harness.infos, ["No completed capability recommended tests are available to run."]);
    }
  });
});

test("stale remembered workspace errors and does not run", async () => {
  await withTempWorkspace(async (rememberedRoot) => {
    await withTempWorkspace(async (currentRoot) => {
      const harness = createRecommendedTestsHarness({
        workspaceFolders: [{ name: "current", root: currentRoot }],
        testPickIndexes: [0],
        confirmResponse: "Run tests",
      });

      harness.rememberTests(completedReportWithRecommendedTests(["npm test"]), toWorkspaceFolder("remembered", rememberedRoot));
      await harness.runRecommendedTests();

      assert.deepEqual(harness.terminals, []);
      assert.match(harness.errors.join("\n"), /no longer open/i);
    });
  });
});

test("multi-root without remembered workspace prompts workspace selection before running", async () => {
  await withTempWorkspace(async (firstRoot) => {
    await withTempWorkspace(async (secondRoot) => {
      const harness = createRecommendedTestsHarness({
        workspaceFolders: [
          { name: "first", root: firstRoot },
          { name: "second", root: secondRoot },
        ],
        workspacePickIndex: 1,
        testPickIndexes: [0],
        confirmResponse: "Run tests",
      });

      harness.rememberTests(completedReportWithRecommendedTests(["npm test"]));
      await harness.runRecommendedTests();

      assert.deepEqual(harness.workspacePickLabels, ["first", "second"]);
      assert.equal(harness.terminals.length, 1);
      assert.equal(harness.terminals[0].cwd, secondRoot);
      assert.deepEqual(harness.terminals[0].sentText, ["npm test"]);
    });
  });
});

test("blank recommended test strings are ignored and commands are trimmed", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0, 1],
      confirmResponse: "Run tests",
    });

    harness.rememberTests(
      completedReportWithRecommendedTests(["  npm test  ", "", "   ", "\tpython scripts\\validate-contracts.py\t"]),
      toWorkspaceFolder("workspace", workspaceRoot),
    );
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals[0].sentText, ["npm test", "python scripts\\validate-contracts.py"]);
  });
});

test("recommended tests containing CR or LF are ignored", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0],
      confirmResponse: "Run tests",
    });

    harness.rememberTests(
      completedReportWithRecommendedTests(["npm test\nrm -rf x", "python -m pytest\r\nwhoami", "   "]),
      toWorkspaceFolder("workspace", workspaceRoot),
    );
    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.deepEqual(harness.infos, ["No completed capability recommended tests are available to run."]);
  });
});

test("no remembered recommended tests shows information and does not run", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const harness = createRecommendedTestsHarness({
      workspaceFolders: [{ name: "workspace", root: workspaceRoot }],
      testPickIndexes: [0],
      confirmResponse: "Run tests",
    });

    await harness.runRecommendedTests();

    assert.deepEqual(harness.terminals, []);
    assert.deepEqual(harness.infos, ["No completed capability recommended tests are available to run."]);
  });
});

type ModuleLoader = (request: string, parent: unknown, isMain: boolean) => unknown;

async function withMockedVscode<T>(
  vscodeMock: unknown,
  run: () => Promise<T>,
): Promise<T> {
  const moduleWithLoad = Module as unknown as { _load: ModuleLoader };
  const originalLoad = moduleWithLoad._load;
  const commandPath = require.resolve("../commands/runRecommendedTests");

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

function createRecommendedTestsHarness(options: RecommendedTestsHarnessOptions): RecommendedTestsHarness {
  const infos: string[] = [];
  const errors: string[] = [];
  const confirmations: string[] = [];
  const workspacePickLabels: string[] = [];
  const terminals: TerminalRecord[] = [];
  const vscodeMock = createVscodeMock(options, {
    infos,
    errors,
    confirmations,
    workspacePickLabels,
    terminals,
  });
  const commandModule = require("../commands/runRecommendedTests") as RecommendedTestsCommandModule;
  commandModule.clearRememberedRecommendedTests();

  return {
    infos,
    errors,
    confirmations,
    workspacePickLabels,
    terminals,
    rememberTests(report: CapabilityRunResponse, workspaceFolder?: WorkspaceFolderMock): void {
      commandModule.rememberRunRecommendedTests(report, workspaceFolder);
    },
    async runRecommendedTests(): Promise<void> {
      await withMockedVscode(vscodeMock, async () => {
        await commandModule.runRecommendedTests();
      });
    },
  };
}

function createVscodeMock(
  options: RecommendedTestsHarnessOptions,
  calls: {
    infos: string[];
    errors: string[];
    confirmations: string[];
    workspacePickLabels: string[];
    terminals: TerminalRecord[];
  },
): unknown {
  return {
    workspace: {
      workspaceFolders: options.workspaceFolders.map((folder) => toWorkspaceFolder(folder.name, folder.root)),
    },
    window: {
      async showQuickPick<T>(items: readonly T[], quickPickOptions?: { canPickMany?: boolean }): Promise<T | T[] | undefined> {
        if (items.every((item) => isWorkspaceQuickPickItem(item))) {
          const workspaceItems = items as readonly { label: string; workspaceFolder: WorkspaceFolderMock }[];
          calls.workspacePickLabels.push(...workspaceItems.map((item) => item.label));
          if (options.workspacePickIndex === undefined) {
            return undefined;
          }
          return workspaceItems[options.workspacePickIndex] as T;
        }
        if (quickPickOptions?.canPickMany) {
          if (options.testPickIndexes === undefined) {
            return undefined;
          }
          return options.testPickIndexes.map((index) => items[index]);
        }
        return items[0];
      },
      async showWarningMessage(message: string, _options: unknown, action: string): Promise<string | undefined> {
        assert.equal(action, "Run tests");
        calls.confirmations.push(message);
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
      createTerminal(options: { name?: string; cwd?: string }): TerminalMock {
        const terminal: TerminalRecord = {
          name: options.name ?? "",
          cwd: options.cwd ?? "",
          shown: false,
          sentText: [],
        };
        calls.terminals.push(terminal);
        return {
          show(): void {
            terminal.shown = true;
          },
          sendText(text: string, addNewLine?: boolean): void {
            assert.equal(addNewLine, true);
            terminal.sentText.push(text);
          },
        };
      },
    },
  };
}

function completedReportWithRecommendedTests(recommendedTests: unknown[]): CapabilityRunResponse {
  return {
    task_id: "task-tests",
    status: "completed",
    result: {
      summary: "Done",
      recommended_tests: recommendedTests,
    },
  };
}

function completedReportWithoutRecommendedTests(): CapabilityRunResponse {
  return {
    task_id: "task-no-tests",
    status: "completed",
    result: {
      summary: "Done",
    },
  };
}

function queuedReport(): CapabilityRunResponse {
  return {
    task_id: "task-queued",
    status: "queued",
  };
}

function failedReport(): CapabilityRunResponse {
  return {
    task_id: "task-failed",
    status: "failed",
    result: {
      recommended_tests: ["npm test"],
    },
  };
}

async function withTempWorkspace(run: (workspaceRoot: string) => Promise<void>): Promise<void> {
  const workspaceRoot = await mkdtemp(path.join(tmpdir(), "skill-capability-tests-"));
  try {
    await run(workspaceRoot);
  } finally {
    await rm(workspaceRoot, { recursive: true, force: true });
  }
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

interface RecommendedTestsHarness {
  infos: string[];
  errors: string[];
  confirmations: string[];
  workspacePickLabels: string[];
  terminals: TerminalRecord[];
  rememberTests(report: CapabilityRunResponse, workspaceFolder?: WorkspaceFolderMock): void;
  runRecommendedTests(): Promise<void>;
}

interface RecommendedTestsHarnessOptions {
  workspaceFolders: Array<{ name: string; root: string }>;
  workspacePickIndex?: number;
  testPickIndexes?: number[];
  confirmResponse?: string;
}

interface RecommendedTestsCommandModule {
  rememberRunRecommendedTests(report: CapabilityRunResponse, workspaceFolder?: WorkspaceFolderMock): void;
  clearRememberedRecommendedTests(): void;
  runRecommendedTests(): Promise<void>;
}

interface WorkspaceFolderMock {
  name: string;
  uri: {
    fsPath: string;
    toString(): string;
  };
}

interface TerminalRecord {
  name: string;
  cwd: string;
  shown: boolean;
  sentText: string[];
}

interface TerminalMock {
  show(): void;
  sendText(text: string, addNewLine?: boolean): void;
}

function isWorkspaceQuickPickItem(value: unknown): value is { label: string; workspaceFolder: WorkspaceFolderMock } {
  return Boolean(value)
    && typeof value === "object"
    && Boolean((value as { workspaceFolder?: unknown }).workspaceFolder)
    && typeof (value as { label?: unknown }).label === "string";
}
