import { execFile } from "node:child_process";
import type { Stats } from "node:fs";
import { lstat, readFile } from "node:fs/promises";
import {
  acceptWorkspaceRelativePath,
  byteLength,
  isBinaryContent,
  isWithinFileLimit,
  resolveWorkspacePath,
  toWorkspacePath,
  type WorkspaceContextSettings,
} from "./policy";

export interface WorkspaceDocument {
  uri: WorkspaceUri;
  text: string;
}

export type WorkspaceUri = string | { fsPath: string };

export interface WorkspaceSelection {
  startLine: number;
  endLine: number;
  text: string;
}

export interface WorkspaceFilePayload {
  path: string;
  content: string;
}

export interface WorkspaceSelectionPayload {
  path: string;
  start_line: number;
  end_line: number;
  content: string;
}

export interface PublicWorkspaceContext {
  name?: string;
  root_uri?: string;
  git_branch?: string;
  git_diff?: string;
  files?: WorkspaceFilePayload[];
  selection?: WorkspaceSelectionPayload;
}

export interface WorkspaceContextResult {
  workspace: PublicWorkspaceContext;
  errors: string[];
}

export interface CollectFileOptions {
  workspaceRoot: string;
  settings: WorkspaceContextSettings;
}

export interface CollectCurrentFileOptions extends CollectFileOptions {
  document: WorkspaceDocument;
}

export interface CollectSelectionOptions extends CollectCurrentFileOptions {
  selection: WorkspaceSelection;
}

export interface CollectSelectedFilesOptions extends CollectFileOptions {
  fileUris: WorkspaceUri[];
}

export type CommandRunner = (
  command: string,
  args: string[],
  options: { cwd: string },
) => Promise<{ stdout: string }>;

export interface CollectGitDiffOptions {
  workspaceRoot: string;
  settings: WorkspaceContextSettings;
  paths?: string[];
  commandRunner?: CommandRunner;
}

export interface RunRequestPayload {
  instruction: string;
  workspace?: PublicWorkspaceContext;
  client: {
    type: "vscode";
    version?: string;
  };
}

export async function collectCurrentFileContext(
  options: CollectCurrentFileOptions,
): Promise<WorkspaceContextResult> {
  const resolved = resolveWorkspacePath(options.workspaceRoot, fsPath(options.document.uri));
  if ("error" in resolved) {
    return { workspace: { files: [] }, errors: [resolved.error] };
  }

  const uploadableFile = await validateUploadableFile(resolved);
  if ("error" in uploadableFile) {
    return { workspace: { files: [] }, errors: [uploadableFile.error] };
  }

  return collectTextFile(
    resolved.relativePath,
    options.document.text,
    { files: [] },
    [],
    options.settings,
  );
}

export async function collectSelectionContext(
  options: CollectSelectionOptions,
): Promise<WorkspaceContextResult> {
  if (!options.selection.text) {
    return {
      workspace: {},
      errors: ["Selection is empty; no selection context was collected."],
    };
  }

  const resolved = resolveWorkspacePath(options.workspaceRoot, fsPath(options.document.uri));
  if ("error" in resolved) {
    return { workspace: {}, errors: [resolved.error] };
  }

  if (options.selection.startLine < 0 || options.selection.endLine < options.selection.startLine) {
    return {
      workspace: {},
      errors: ["Selection line range is invalid."],
    };
  }

  const uploadableFile = await validateUploadableFile(resolved);
  if ("error" in uploadableFile) {
    return { workspace: {}, errors: [uploadableFile.error] };
  }

  if (isBinaryContent(options.selection.text)) {
    return {
      workspace: {},
      errors: [`${resolved.relativePath} selection appears to be binary and cannot be uploaded.`],
    };
  }

  if (byteLength(options.selection.text) > options.settings.maxTotalBytes) {
    return {
      workspace: {},
      errors: [`${resolved.relativePath} selection exceeds maxTotalBytes ${options.settings.maxTotalBytes}.`],
    };
  }

  return {
    workspace: {
      selection: {
        path: resolved.relativePath,
        start_line: options.selection.startLine + 1,
        end_line: options.selection.endLine + 1,
        content: options.selection.text,
      },
    },
    errors: [],
  };
}

export async function collectSelectedFilesContext(
  options: CollectSelectedFilesOptions,
): Promise<WorkspaceContextResult> {
  const workspace: PublicWorkspaceContext = { files: [] };
  const errors: string[] = [];
  let totalBytes = 0;

  for (const fileUri of options.fileUris) {
    const resolved = resolveWorkspacePath(options.workspaceRoot, fsPath(fileUri));
    if ("error" in resolved) {
      errors.push(resolved.error);
      continue;
    }

    if (!isWithinFileLimit(workspace.files?.length ?? 0, options.settings)) {
      errors.push(`Skipping ${resolved.relativePath}: maxFiles ${options.settings.maxFiles} reached.`);
      continue;
    }

    try {
      const uploadableFile = await validateUploadableFile(resolved);
      if ("error" in uploadableFile) {
        errors.push(uploadableFile.error);
        continue;
      }

      if (totalBytes + uploadableFile.stats.size > options.settings.maxTotalBytes) {
        errors.push(`${resolved.relativePath} exceeds maxTotalBytes ${options.settings.maxTotalBytes}.`);
        continue;
      }

      const contentBuffer = await readFile(resolved.absolutePath);
      if (isBinaryContent(contentBuffer)) {
        errors.push(`${resolved.relativePath} appears to be binary and cannot be uploaded.`);
        continue;
      }

      const contentBytes = contentBuffer.length;
      const content = contentBuffer.toString("utf8");
      workspace.files?.push({ path: resolved.relativePath, content });
      totalBytes += contentBytes;
    } catch {
      errors.push(`${resolved.relativePath} could not be read for workspace context.`);
    }
  }

  return { workspace, errors };
}

async function validateUploadableFile(
  resolved: { absolutePath: string; relativePath: string },
): Promise<{ stats: Stats } | { error: string }> {
  try {
    const fileStats = await lstat(resolved.absolutePath);
    if (fileStats.isSymbolicLink()) {
      return { error: `${resolved.relativePath} is a symbolic link and cannot be uploaded.` };
    }

    if (!fileStats.isFile()) {
      return { error: `${resolved.relativePath} is not a regular file and cannot be uploaded.` };
    }

    return { stats: fileStats };
  } catch {
    return { error: `${resolved.relativePath} could not be read for workspace context.` };
  }
}

export async function collectGitDiffContext(
  options: CollectGitDiffOptions,
): Promise<WorkspaceContextResult> {
  const runner = options.commandRunner ?? defaultCommandRunner;
  const errors: string[] = [];
  let paths = options.paths ?? [];

  if (paths.length === 0) {
    try {
      const changedFiles = await runner("git", ["diff", "--name-only"], {
        cwd: options.workspaceRoot,
      });
      paths = parseGitPathList(changedFiles.stdout);
    } catch {
      return { workspace: {}, errors: ["Unable to read git diff."] };
    }
  }

  if (paths.length > options.settings.maxFiles) {
    return {
      workspace: {},
      errors: [`git diff paths exceed maxFiles ${options.settings.maxFiles}.`],
    };
  }

  const allowedPaths: string[] = [];
  for (const diffPath of paths) {
    const accepted = acceptWorkspaceRelativePath(diffPath);
    if ("error" in accepted) {
      errors.push(accepted.error);
      continue;
    }
    allowedPaths.push(accepted.relativePath);
  }

  if (allowedPaths.length === 0) {
    return { workspace: { git_diff: "" }, errors };
  }

  try {
    const result = await runner(
      "git",
      ["diff", "--", ...allowedPaths],
      { cwd: options.workspaceRoot },
    );
    if (byteLength(result.stdout) > options.settings.maxTotalBytes) {
      return {
        workspace: {},
        errors: [`git diff exceeds maxTotalBytes ${options.settings.maxTotalBytes}.`],
      };
    }
    return { workspace: { git_diff: result.stdout }, errors };
  } catch {
    return { workspace: {}, errors: ["Unable to read git diff."] };
  }
}

export function createRunRequestPayload(options: {
  instruction: string;
  workspace?: PublicWorkspaceContext;
  clientVersion?: string;
}): RunRequestPayload {
  return {
    instruction: options.instruction,
    workspace: options.workspace,
    client: {
      type: "vscode",
      version: options.clientVersion,
    },
  };
}

function collectTextFile(
  relativePath: string,
  content: string,
  workspace: PublicWorkspaceContext,
  errors: string[],
  settings: WorkspaceContextSettings,
): WorkspaceContextResult {
  const normalizedPath = toWorkspacePath(relativePath);
  const accepted = acceptWorkspaceRelativePath(normalizedPath);
  if ("error" in accepted) {
    return { workspace: { files: [] }, errors: [accepted.error] };
  }

  if (isBinaryContent(content)) {
    return {
      workspace,
      errors: [...errors, `${accepted.relativePath} appears to be binary and cannot be uploaded.`],
    };
  }

  if (!isWithinFileLimit(workspace.files?.length ?? 0, settings)) {
    return {
      workspace,
      errors: [...errors, `Skipping ${accepted.relativePath}: maxFiles ${settings.maxFiles} reached.`],
    };
  }

  if (byteLength(content) > settings.maxTotalBytes) {
    return {
      workspace,
      errors: [...errors, `${accepted.relativePath} exceeds maxTotalBytes ${settings.maxTotalBytes}.`],
    };
  }

  return {
    workspace: {
      ...workspace,
      files: [
        ...(workspace.files ?? []),
        { path: accepted.relativePath, content },
      ],
    },
    errors,
  };
}

function defaultCommandRunner(
  command: string,
  args: string[],
  options: { cwd: string },
): Promise<{ stdout: string }> {
  return new Promise((resolve, reject) => {
    execFile(command, args, { cwd: options.cwd }, (error, stdout) => {
      if (error) {
        reject(error);
        return;
      }
      resolve({ stdout });
    });
  });
}

function parseGitPathList(stdout: string): string[] {
  return stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function fsPath(uri: WorkspaceUri): string {
  return typeof uri === "string" ? uri : uri.fsPath;
}
