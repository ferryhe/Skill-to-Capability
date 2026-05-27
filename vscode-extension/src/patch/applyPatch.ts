import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { acceptWorkspaceRelativePath } from "../context/policy";

export interface PatchEdit {
  relativePath: string;
  absolutePath: string;
  oldText: string;
  newText: string;
}

export interface PatchApplyPlan {
  edits: PatchEdit[];
}

interface ParsedFilePatch {
  oldPath: string;
  newPath: string;
  hunks: ParsedHunk[];
}

interface ParsedHunk {
  oldStart: number;
  oldCount: number;
  newStart: number;
  newCount: number;
  lines: HunkLine[];
}

interface HunkLine {
  kind: "context" | "remove" | "add";
  text: string;
}

export async function planUnifiedDiffApply(
  workspaceRoot: string,
  patch: string,
): Promise<PatchApplyPlan> {
  const parsedFiles = parseUnifiedDiff(patch);
  const edits: PatchEdit[] = [];
  const targetPaths = new Set<string>();

  for (const filePatch of parsedFiles) {
    const relativePath = validateFilePatchPath(filePatch);
    if (targetPaths.has(relativePath)) {
      throw new Error(`Duplicate patch target ${relativePath} is not supported.`);
    }
    targetPaths.add(relativePath);
    const absolutePath = path.join(path.resolve(workspaceRoot), relativePath);
    const oldText = await readFile(absolutePath, "utf8");
    const newText = applyHunks(oldText, filePatch, relativePath);
    edits.push({
      relativePath,
      absolutePath,
      oldText,
      newText,
    });
  }

  return { edits };
}

export async function applyUnifiedDiffToWorkspace(
  workspaceRoot: string,
  patch: string,
): Promise<PatchApplyPlan> {
  const plan = await planUnifiedDiffApply(workspaceRoot, patch);
  for (const edit of plan.edits) {
    await writeFile(edit.absolutePath, edit.newText, "utf8");
  }
  return plan;
}

function parseUnifiedDiff(patch: string): ParsedFilePatch[] {
  const lines = patch.replace(/\r\n/g, "\n").split("\n");
  const files: ParsedFilePatch[] = [];
  let current: ParsedFilePatch | undefined;
  let currentHunk: ParsedHunk | undefined;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("diff --git ")) {
      if (current) {
        files.push(current);
      }
      current = { oldPath: "", newPath: "", hunks: [] };
      currentHunk = undefined;
      continue;
    }

    if (line.startsWith("--- ") && lines[index + 1]?.startsWith("+++ ")) {
      if (current?.hunks.length) {
        files.push(current);
        current = { oldPath: "", newPath: "", hunks: [] };
      } else if (!current) {
        current = { oldPath: "", newPath: "", hunks: [] };
      }
      current.oldPath = parseHeaderPath(line.slice(4));
      currentHunk = undefined;
      continue;
    }

    if (!current) {
      continue;
    }

    if (line.startsWith("+++ ")) {
      current.newPath = parseHeaderPath(line.slice(4));
      currentHunk = undefined;
      continue;
    }

    const hunkMatch = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
    if (hunkMatch) {
      currentHunk = {
        oldStart: Number(hunkMatch[1]),
        oldCount: hunkMatch[2] === undefined ? 1 : Number(hunkMatch[2]),
        newStart: Number(hunkMatch[3]),
        newCount: hunkMatch[4] === undefined ? 1 : Number(hunkMatch[4]),
        lines: [],
      };
      current.hunks.push(currentHunk);
      continue;
    }

    if (line === "\\ No newline at end of file") {
      throw new Error("No newline at end of file marker is not supported.");
    }

    if (!currentHunk) {
      continue;
    }

    const marker = line[0];
    const text = line.slice(1);
    if (marker === " ") {
      currentHunk.lines.push({ kind: "context", text });
    } else if (marker === "-") {
      currentHunk.lines.push({ kind: "remove", text });
    } else if (marker === "+") {
      currentHunk.lines.push({ kind: "add", text });
    }
  }

  if (current) {
    files.push(current);
  }

  const applicableFiles = files.filter((file) => file.hunks.length > 0);
  if (applicableFiles.length === 0) {
    throw new Error("Patch does not contain any unified diff hunks.");
  }
  for (const file of applicableFiles) {
    for (const hunk of file.hunks) {
      validateHunkLineCounts(hunk);
    }
  }
  return applicableFiles;
}

function validateHunkLineCounts(hunk: ParsedHunk): void {
  const oldLineCount = hunk.lines.filter((line) =>
    line.kind === "context" || line.kind === "remove"
  ).length;
  const newLineCount = hunk.lines.filter((line) =>
    line.kind === "context" || line.kind === "add"
  ).length;
  if (oldLineCount !== hunk.oldCount || newLineCount !== hunk.newCount) {
    throw new Error("Patch hunk line count does not match header.");
  }
}

function parseHeaderPath(value: string): string {
  const pathPart = value.trim().split(/\s+/)[0] ?? "";
  if (pathPart === "/dev/null") {
    return pathPart;
  }
  return pathPart.replace(/^[ab]\//, "");
}

function validateFilePatchPath(filePatch: ParsedFilePatch): string {
  if (filePatch.oldPath === "/dev/null" || filePatch.newPath === "/dev/null") {
    throw new Error("Patch file creation and deletion are not supported yet.");
  }
  if (!filePatch.oldPath || !filePatch.newPath) {
    throw new Error("Patch file headers are incomplete.");
  }
  if (filePatch.oldPath !== filePatch.newPath) {
    throw new Error("Patch file renames are not supported yet.");
  }

  const acceptedPath = acceptWorkspaceRelativePath(filePatch.newPath);
  if ("error" in acceptedPath) {
    throw new Error(acceptedPath.error);
  }
  return acceptedPath.relativePath;
}

function applyHunks(
  oldText: string,
  filePatch: ParsedFilePatch,
  relativePath: string,
): string {
  const oldLines = splitPatchText(oldText);
  const newLines: string[] = [];
  let sourceIndex = 0;

  for (const hunk of filePatch.hunks) {
    const hunkStart = hunk.oldCount === 0 ? hunk.oldStart : hunk.oldStart - 1;
    if (hunkStart < sourceIndex) {
      throw new Error(`${relativePath} has overlapping patch hunks.`);
    }

    newLines.push(...oldLines.lines.slice(sourceIndex, hunkStart));
    sourceIndex = hunkStart;

    for (const line of hunk.lines) {
      if (line.kind === "add") {
        newLines.push(line.text);
        continue;
      }

      const actual = oldLines.lines[sourceIndex];
      if (actual !== line.text) {
        throw new Error(`${relativePath} hunk does not match current file content.`);
      }
      if (line.kind === "context") {
        newLines.push(line.text);
      }
      sourceIndex += 1;
    }
  }

  newLines.push(...oldLines.lines.slice(sourceIndex));
  return joinPatchText(newLines, oldLines.hasFinalNewline, oldLines.eol);
}

function splitPatchText(text: string): { lines: string[]; hasFinalNewline: boolean; eol: string } {
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  const normalized = text.replace(/\r\n/g, "\n");
  const hasFinalNewline = normalized.endsWith("\n");
  const lines = normalized.split("\n");
  if (hasFinalNewline) {
    lines.pop();
  }
  return { lines, hasFinalNewline, eol };
}

function joinPatchText(lines: string[], hasFinalNewline: boolean, eol: string): string {
  return `${lines.join(eol)}${hasFinalNewline ? eol : ""}`;
}
