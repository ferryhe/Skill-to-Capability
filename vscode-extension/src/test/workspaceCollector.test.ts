import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  collectCurrentFileContext,
  collectGitDiffContext,
  collectSelectedFilesContext,
  collectSelectionContext,
  createRunRequestPayload,
  type CommandRunner,
  type WorkspaceDocument,
} from "../context/workspaceCollector";

const defaultSettings = {
  maxFiles: 3,
  maxTotalBytes: 100,
};

test("selected files deny sensitive paths without uploading their contents", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    await writeFile(path.join(workspaceRoot, ".env"), "SECRET_TOKEN=leak-me");
    await writeFile(path.join(workspaceRoot, "cert.pem"), "PEM_SECRET=leak-me");
    await writeFile(path.join(workspaceRoot, "app.key"), "KEY_SECRET=leak-me");
    await writeFile(path.join(workspaceRoot, "id_rsa"), "RSA_SECRET=leak-me");
    await writeFile(path.join(workspaceRoot, "credentials.json"), "{\"secret\":\"leak-me\"}");
    await writeFile(path.join(workspaceRoot, "src.ts"), "export const safe = true;\n");

    const result = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: [
        { fsPath: path.join(workspaceRoot, ".env") },
        { fsPath: path.join(workspaceRoot, "cert.pem") },
        { fsPath: path.join(workspaceRoot, "app.key") },
        { fsPath: path.join(workspaceRoot, "id_rsa") },
        { fsPath: path.join(workspaceRoot, "credentials.json") },
        { fsPath: path.join(workspaceRoot, "src.ts") },
      ],
      settings: defaultSettings,
    });

    assert.deepEqual(result.workspace.files, [
      { path: "src.ts", content: "export const safe = true;\n" },
    ]);
    assert.match(result.errors.join("\n"), /\.env is denied by workspace context policy/);
    assert.match(result.errors.join("\n"), /cert\.pem is denied by workspace context policy/);
    assert.match(result.errors.join("\n"), /app\.key is denied by workspace context policy/);
    assert.match(result.errors.join("\n"), /id_rsa is denied by workspace context policy/);
    assert.match(result.errors.join("\n"), /credentials\.json is denied by workspace context policy/);
    assert.equal(JSON.stringify(result).includes("leak-me"), false);
  });
});

test("current file denies sensitive filenames without uploading content", () => {
  const result = collectCurrentFileContext({
    workspaceRoot: path.join("C:", "workspace"),
    document: {
      uri: { fsPath: path.join("C:", "workspace", "nested", "private.pem") },
      text: "PRIVATE_PEM_CONTENT",
    },
    settings: defaultSettings,
  });

  assert.deepEqual(result.workspace.files, []);
  assert.deepEqual(result.errors, ["nested/private.pem is denied by workspace context policy."]);
  assert.equal(JSON.stringify(result).includes("PRIVATE_PEM_CONTENT"), false);
});

test("binary selected and current files are denied without uploading bytes", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    await writeFile(path.join(workspaceRoot, "image.bin"), Buffer.from([0, 1, 2, 3, 4]));

    const selected = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: [path.join(workspaceRoot, "image.bin")],
      settings: defaultSettings,
    });
    const current = collectCurrentFileContext({
      workspaceRoot,
      document: {
        uri: path.join(workspaceRoot, "current.txt"),
        text: "safe-prefix\u0000binary-suffix",
      },
      settings: defaultSettings,
    });

    assert.deepEqual(selected.workspace.files, []);
    assert.deepEqual(selected.errors, ["image.bin appears to be binary and cannot be uploaded."]);
    assert.deepEqual(current.workspace.files, []);
    assert.deepEqual(current.errors, ["current.txt appears to be binary and cannot be uploaded."]);
    assert.equal(JSON.stringify(selected).includes("\u0000"), false);
    assert.equal(JSON.stringify(current).includes("binary-suffix"), false);
  });
});

test("selected files skip oversized content and report a policy error", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    await writeFile(path.join(workspaceRoot, "huge.txt"), "x".repeat(101));

    const result = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: [path.join(workspaceRoot, "huge.txt")],
      settings: defaultSettings,
    });

    assert.deepEqual(result.workspace.files, []);
    assert.match(result.errors.join("\n"), /huge\.txt exceeds maxTotalBytes/);
    assert.equal(JSON.stringify(result).includes("x".repeat(20)), false);
  });
});

test("selected files enforce max file count before upload", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const filePaths = ["a.ts", "b.ts", "c.ts", "d.ts"];
    for (const filePath of filePaths) {
      await writeFile(path.join(workspaceRoot, filePath), `${filePath}\n`);
    }

    const result = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: filePaths.map((filePath) => path.join(workspaceRoot, filePath)),
      settings: defaultSettings,
    });

    assert.equal(result.workspace.files?.length, 3);
    assert.match(result.errors.join("\n"), /maxFiles 3/);
    assert.equal(JSON.stringify(result).includes("d.ts\\n"), false);
  });
});

test("selected files reject paths outside the workspace", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const escapedPath = path.join(path.dirname(workspaceRoot), "escape.txt");
    await writeFile(escapedPath, "outside workspace");

    const result = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: [escapedPath],
      settings: defaultSettings,
    });

    assert.deepEqual(result.workspace.files, []);
    assert.match(result.errors.join("\n"), /outside the workspace/);
    assert.equal(JSON.stringify(result).includes("outside workspace"), false);
  });
});

test("selected files sanitize read failures and continue collecting safe files", async () => {
  await withTempWorkspace(async (workspaceRoot) => {
    const missingPath = path.join(workspaceRoot, "missing.txt");
    const safePath = path.join(workspaceRoot, "safe.ts");
    await writeFile(safePath, "export const safe = true;\n");

    const result = await collectSelectedFilesContext({
      workspaceRoot,
      fileUris: [missingPath, safePath],
      settings: defaultSettings,
    });

    assert.deepEqual(result.workspace.files, [
      { path: "safe.ts", content: "export const safe = true;\n" },
    ]);
    assert.deepEqual(result.errors, ["missing.txt could not be read for workspace context."]);
    assert.equal(JSON.stringify(result).includes(workspaceRoot), false);
    assert.equal(JSON.stringify(result).includes("ENOENT"), false);
  });
});

test("current file and selection collect workspace-relative public context", () => {
  const document: WorkspaceDocument = {
    uri: { fsPath: path.join("C:", "workspace", "src", "feature.ts") },
    text: "const first = 1;\nconst second = 2;\n",
  };
  const workspaceRoot = path.join("C:", "workspace");

  const currentFile = collectCurrentFileContext({
    workspaceRoot,
    document,
    settings: defaultSettings,
  });
  const selection = collectSelectionContext({
    workspaceRoot,
    document,
    selection: {
      startLine: 2,
      endLine: 2,
      text: "const second = 2;",
    },
    settings: defaultSettings,
  });
  const payload = createRunRequestPayload({
    instruction: "Review this file.",
    workspace: {
      ...currentFile.workspace,
      selection: selection.workspace.selection,
    },
    clientVersion: "0.1.0",
  });

  assert.deepEqual(currentFile.workspace.files, [
    { path: "src/feature.ts", content: document.text },
  ]);
  assert.deepEqual(selection.workspace.selection, {
    path: "src/feature.ts",
    start_line: 2,
    end_line: 2,
    content: "const second = 2;",
  });
  assert.deepEqual(payload, {
    instruction: "Review this file.",
    workspace: {
      files: [{ path: "src/feature.ts", content: document.text }],
      selection: {
        path: "src/feature.ts",
        start_line: 2,
        end_line: 2,
        content: "const second = 2;",
      },
    },
    client: {
      type: "vscode",
      version: "0.1.0",
    },
  });
});

test("empty selections return a clear no-content error", () => {
  const document: WorkspaceDocument = {
    uri: path.join("C:", "workspace", "src", "feature.ts"),
    text: "const first = 1;\n",
  };

  const result = collectSelectionContext({
    workspaceRoot: path.join("C:", "workspace"),
    document,
    selection: {
      startLine: 1,
      endLine: 1,
      text: "",
    },
    settings: defaultSettings,
  });

  assert.equal(result.workspace.selection, undefined);
  assert.deepEqual(result.errors, ["Selection is empty; no selection context was collected."]);
});

test("selection rejects binary-like text without uploading content", () => {
  const result = collectSelectionContext({
    workspaceRoot: path.join("C:", "workspace"),
    document: {
      uri: path.join("C:", "workspace", "src", "feature.ts"),
      text: "safe-prefix\u0000binary-suffix",
    },
    selection: {
      startLine: 1,
      endLine: 1,
      text: "safe-prefix\u0000binary-suffix",
    },
    settings: defaultSettings,
  });

  assert.equal(result.workspace.selection, undefined);
  assert.deepEqual(result.errors, ["src/feature.ts selection appears to be binary and cannot be uploaded."]);
  assert.equal(JSON.stringify(result).includes("binary-suffix"), false);
});

test("selected files reject symlinks before reading target content", async (t) => {
  await withTempWorkspace(async (workspaceRoot) => {
    const outsidePath = path.join(path.dirname(workspaceRoot), "outside-secret.txt");
    const linkPath = path.join(workspaceRoot, "linked-secret.txt");
    try {
      await writeFile(outsidePath, "OUTSIDE_SECRET_CONTENT");

      try {
        await symlink(outsidePath, linkPath);
      } catch (error) {
        t.skip(`symlink creation is unsupported in this environment: ${String(error)}`);
        return;
      }

      const result = await collectSelectedFilesContext({
        workspaceRoot,
        fileUris: [linkPath],
        settings: defaultSettings,
      });

      assert.deepEqual(result.workspace.files, []);
      assert.deepEqual(result.errors, ["linked-secret.txt is a symbolic link and cannot be uploaded."]);
      assert.equal(JSON.stringify(result).includes("OUTSIDE_SECRET_CONTENT"), false);
    } finally {
      await rm(outsidePath, { force: true });
    }
  });
});

test("git diff returns diff text from the injected command runner", async () => {
  const commands: Array<{ command: string; args: string[]; cwd: string }> = [];
  const runner: CommandRunner = async (
    command: string,
    args: string[],
    options: { cwd: string },
  ) => {
    commands.push({ command, args, cwd: options.cwd });
    return { stdout: "diff --git a/src/a.ts b/src/a.ts\n+change\n" };
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    paths: ["src/a.ts"],
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.deepEqual(commands, [
    {
      command: "git",
      args: ["diff", "--", "src/a.ts"],
      cwd: path.join("C:", "workspace"),
    },
  ]);
  assert.equal(result.workspace.git_diff, "diff --git a/src/a.ts b/src/a.ts\n+change\n");
  assert.deepEqual(result.errors, []);
});

test("git diff failures return sanitized errors instead of throwing raw exceptions", async () => {
  const runner: CommandRunner = async () => {
    throw new Error("fatal: private-token-123 failed at C:\\Users\\ferry\\secret");
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.equal(result.workspace.git_diff, undefined);
  assert.deepEqual(result.errors, ["Unable to read git diff."]);
  assert.equal(JSON.stringify(result).includes("private-token-123"), false);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("git diff skips oversized stdout and does not leak diff content", async () => {
  const privateDiff = `diff --git a/secret.ts b/secret.ts\n+${"x".repeat(101)}\n`;
  const runner: CommandRunner = async () => ({ stdout: privateDiff });

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    paths: ["secret.ts"],
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.equal(result.workspace.git_diff, undefined);
  assert.deepEqual(result.errors, ["git diff exceeds maxTotalBytes 100."]);
  assert.equal(JSON.stringify(result).includes(privateDiff), false);
  assert.equal(JSON.stringify(result).includes("secret.ts"), false);
});

test("git diff rejects too many paths before running the command", async () => {
  let commandRan = false;
  const runner: CommandRunner = async () => {
    commandRan = true;
    return { stdout: "diff should not run" };
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    paths: ["a.ts", "b.ts", "c.ts", "d.ts"],
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.equal(commandRan, false);
  assert.equal(result.workspace.git_diff, undefined);
  assert.deepEqual(result.errors, ["git diff paths exceed maxFiles 3."]);
});

test("git diff without paths discovers changed files and filters denied paths before diffing", async () => {
  const commands: string[][] = [];
  const runner: CommandRunner = async (_command, args) => {
    commands.push(args);
    if (args.join(" ") === "diff --name-only") {
      return { stdout: "src/a.ts\n.env\ncert.pem\n" };
    }
    assert.deepEqual(args, ["diff", "--", "src/a.ts"]);
    return { stdout: "diff --git a/src/a.ts b/src/a.ts\n+allowed\n" };
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.deepEqual(commands, [
    ["diff", "--name-only"],
    ["diff", "--", "src/a.ts"],
  ]);
  assert.equal(result.workspace.git_diff, "diff --git a/src/a.ts b/src/a.ts\n+allowed\n");
  assert.match(result.errors.join("\n"), /\.env is denied by workspace context policy/);
  assert.match(result.errors.join("\n"), /cert\.pem is denied by workspace context policy/);
  assert.equal(JSON.stringify(result).includes("DENIED_SECRET"), false);
});

test("git diff without paths rejects too many changed files before diffing content", async () => {
  const commands: string[][] = [];
  const runner: CommandRunner = async (_command, args) => {
    commands.push(args);
    return { stdout: "a.ts\nb.ts\nc.ts\nd.ts\n" };
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.deepEqual(commands, [["diff", "--name-only"]]);
  assert.equal(result.workspace.git_diff, undefined);
  assert.deepEqual(result.errors, ["git diff paths exceed maxFiles 3."]);
});

test("git diff without paths returns empty diff when no allowed files changed", async () => {
  const commands: string[][] = [];
  const runner: CommandRunner = async (_command, args) => {
    commands.push(args);
    return { stdout: ".env\ncredentials.json\n" };
  };

  const result = await collectGitDiffContext({
    workspaceRoot: path.join("C:", "workspace"),
    settings: defaultSettings,
    commandRunner: runner,
  });

  assert.deepEqual(commands, [["diff", "--name-only"]]);
  assert.equal(result.workspace.git_diff, "");
  assert.match(result.errors.join("\n"), /\.env is denied by workspace context policy/);
  assert.match(result.errors.join("\n"), /credentials\.json is denied by workspace context policy/);
});

async function withTempWorkspace(run: (workspaceRoot: string) => Promise<void>): Promise<void> {
  const workspaceRoot = await mkdtemp(path.join(tmpdir(), "skill-capability-"));
  try {
    await mkdir(path.join(workspaceRoot, "nested"), { recursive: true });
    await run(workspaceRoot);
  } finally {
    await rm(workspaceRoot, { recursive: true, force: true });
    const escapedPath = path.join(path.dirname(workspaceRoot), "escape.txt");
    await rm(escapedPath, { force: true });
  }
}
