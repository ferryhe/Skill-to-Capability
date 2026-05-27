import assert from "node:assert/strict";
import Module from "node:module";
import test from "node:test";

import type { PublicCapability } from "../api/client";

test("CapabilityTreeProvider groups capabilities and keeps an id lookup", async () => {
  const { CapabilityTreeProvider } = await loadTreeProviderModule();
  const provider = new CapabilityTreeProvider();

  provider.setCapabilities([
    capability({ id: "z-file", name: "Z File", category: undefined }),
    capability({ id: "beta-review", name: "Beta Review", category: "code-review" }),
    capability({ id: "alpha-review", name: "Alpha Review", category: "code-review" }),
    capability({ id: "deploy", name: "Deploy", category: "automation" }),
  ]);

  const roots = await provider.getChildren();

  assert.deepEqual(roots.map((root: TreeNode) => root.label), [
    "automation",
    "code-review",
    "Uncategorized",
  ]);
  assert.equal(provider.getCapability("alpha-review")?.name, "Alpha Review");

  const codeReviewChildren = await provider.getChildren(roots[1]);
  assert.deepEqual(
    codeReviewChildren.map((node: TreeNode) => node.capability?.id),
    ["alpha-review", "beta-review"],
  );
});

test("formatCapabilityDetail renders only public fields and strips server-only keys", async () => {
  const { formatCapabilityDetail } = await loadTreeProviderModule();
  const detail = formatCapabilityDetail({
    ...capability({ id: "backend-rbac-review", name: "Backend RBAC Review" }),
    input_schema: {
      type: "object",
      properties: {
        instruction: { type: "string" },
        prompt: { const: "private prompt" },
        nested: {
          trace_id: "private trace",
          safe: true,
        },
      },
      internal: { validator: "server-only" },
      model_policy: "private policy",
    },
    output_schema: {
      type: "object",
      properties: {
        summary: { type: "string" },
        skill_text: { type: "string", const: "private skill body" },
        raw_runner_output: { type: "object" },
      },
      chain_of_thought: "private reasoning",
    },
    client_permissions: {
      reads_workspace: true,
      provider: "private provider",
    },
    approval_policy: {
      upload_context: "user_confirm_large",
      skill_ref: "private skill ref",
    },
    security: {
      max_files: 20,
      internalState: "private internal state",
    },
    internal: { secret: "private top-level internal" },
    prompt: "private top-level prompt",
    trace: "private top-level trace",
  } as PublicCapability & Record<string, unknown>);

  assert.match(detail, /Backend RBAC Review/);
  assert.match(detail, /Review backend RBAC and public API payload boundaries\./);
  assert.match(detail, /"instruction"/);
  assert.match(detail, /"safe": true/);
  assert.match(detail, /"max_files": 20/);

  for (const forbidden of [
    "internal",
    "prompt",
    "trace",
    "skill_text",
    "skill_ref",
    "model_policy",
    "provider",
    "chain_of_thought",
    "raw_runner_output",
    "private",
    "server-only",
  ]) {
    assert.equal(
      detail.toLowerCase().includes(forbidden),
      false,
      `detail should not include ${forbidden}`,
    );
  }
});

test("showCapabilityDetail accepts capability tree nodes from view context menus", async () => {
  const { showCapabilityDetail } = await loadCommandModule();
  const output = createOutputChannel();

  await showCapabilityDetail(
    {
      getCapabilities: () => [],
      getCapability: () => undefined,
    },
    output,
    {
      type: "capability",
      label: "Backend RBAC Review",
      capability: capability({ id: "backend-rbac-review" }),
    },
  );

  assert.match(output.value, /Name: Backend RBAC Review/);
  assert.doesNotMatch(output.value, /undefined/);
});

function capability(overrides: Partial<PublicCapability> = {}): PublicCapability {
  return {
    id: "backend-rbac-review",
    name: "Backend RBAC Review",
    version: "0.1.0",
    category: "code-review",
    visible_description: "Review backend RBAC and public API payload boundaries.",
    input_modes: ["current_file", "git_diff"],
    input_schema: { type: "object" },
    output_schema: { type: "object" },
    client_permissions: {
      reads_workspace: true,
      writes_workspace: "optional",
      runs_commands: "optional",
      sends_code_to_server: true,
    },
    approval_policy: {
      upload_context: "user_confirm_large",
      apply_patch: "user_confirm",
      run_commands: "user_confirm",
    },
    security: {
      max_files: 20,
      max_total_input_bytes: 300000,
    },
    ...overrides,
  };
}

interface TreeNode {
  label: string;
  capability?: PublicCapability;
}

type ModuleLoader = (request: string, parent: unknown, isMain: boolean) => unknown;

async function loadTreeProviderModule(): Promise<{
  CapabilityTreeProvider: new () => {
    setCapabilities(capabilities: PublicCapability[]): void;
    getCapability(id: string): PublicCapability | undefined;
    getChildren(element?: TreeNode): Promise<TreeNode[]>;
  };
  formatCapabilityDetail(capability: PublicCapability): string;
}> {
  return withMockedVscode(async () => {
    const treeProviderPath = require.resolve("../capabilities/treeProvider");
    delete require.cache[treeProviderPath];
    return require("../capabilities/treeProvider");
  });
}

async function loadCommandModule(): Promise<{
  showCapabilityDetail(
    treeProvider: {
      getCapabilities(): PublicCapability[];
      getCapability(id: string): PublicCapability | undefined;
    },
    outputChannel: OutputChannel,
    capability?: unknown,
  ): Promise<void>;
}> {
  return withMockedVscode(async () => {
    const commandPath = require.resolve("../commands/refreshCapabilities");
    const treeProviderPath = require.resolve("../capabilities/treeProvider");
    delete require.cache[commandPath];
    delete require.cache[treeProviderPath];
    return require("../commands/refreshCapabilities");
  });
}

async function withMockedVscode<T>(run: () => Promise<T> | T): Promise<T> {
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

const vscodeMock = {
  EventEmitter: class EventEmitter<T> {
    readonly event = (_listener: (value: T) => void): Disposable => ({ dispose() {} });

    fire(_value?: T): void {}
  },
  TreeItem: class TreeItem {
    constructor(
      readonly label: string,
      readonly collapsibleState: number,
    ) {}
  },
  TreeItemCollapsibleState: {
    None: 0,
    Collapsed: 1,
  },
  ThemeIcon: class ThemeIcon {
    constructor(readonly id: string) {}
  },
};

interface Disposable {
  dispose(): void;
}

interface OutputChannel extends Disposable {
  value: string;
  append(value: string): void;
  clear(): void;
  show(preserveFocus?: boolean): void;
}

function createOutputChannel(): OutputChannel {
  return {
    value: "",
    append(value: string): void {
      this.value += value;
    },
    clear(): void {
      this.value = "";
    },
    show(): void {},
    dispose(): void {},
  };
}
