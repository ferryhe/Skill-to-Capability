import path from "node:path";

export interface WorkspaceContextSettings {
  maxFiles: number;
  maxTotalBytes: number;
}

export interface PolicyAcceptedPath {
  absolutePath: string;
  relativePath: string;
}

export interface PolicyRejectedPath {
  error: string;
}

export type PolicyPathResult = PolicyAcceptedPath | PolicyRejectedPath;

export function resolveWorkspacePath(
  workspaceRoot: string,
  candidatePath: string,
): PolicyPathResult {
  const root = path.resolve(workspaceRoot);
  const absolutePath = path.resolve(candidatePath);
  const relative = path.relative(root, absolutePath);

  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    return { error: `${formatPath(candidatePath)} is outside the workspace.` };
  }

  const relativePath = toWorkspacePath(relative);
  if (isDeniedWorkspacePath(relativePath)) {
    return { error: `${relativePath} is denied by workspace context policy.` };
  }

  return { absolutePath, relativePath };
}

export function acceptWorkspaceRelativePath(relativePath: string): PolicyPathResult {
  const normalized = toWorkspacePath(path.normalize(relativePath));
  if (
    !normalized
    || normalized.startsWith("../")
    || normalized === ".."
    || path.isAbsolute(relativePath)
  ) {
    return { error: `${relativePath} is outside the workspace.` };
  }
  if (isDeniedWorkspacePath(normalized)) {
    return { error: `${normalized} is denied by workspace context policy.` };
  }
  return { absolutePath: normalized, relativePath: normalized };
}

export function byteLength(content: string): number {
  return Buffer.byteLength(content, "utf8");
}

export function isBinaryContent(content: Buffer | string): boolean {
  if (typeof content === "string") {
    return content.includes("\u0000");
  }
  return content.includes(0);
}

export function isWithinFileLimit(count: number, settings: WorkspaceContextSettings): boolean {
  return count < settings.maxFiles;
}

export function toWorkspacePath(value: string): string {
  return value.replace(/\\/g, "/").replace(/^\/+/, "");
}

function isDeniedWorkspacePath(relativePath: string): boolean {
  const parts = relativePath.split("/");
  const basename = parts[parts.length - 1] ?? "";
  return basename === ".env"
    || basename.startsWith(".env.")
    || basename.endsWith(".pem")
    || basename.endsWith(".key")
    || basename === "id_rsa"
    || basename === "credentials.json"
    || parts.includes("node_modules")
    || parts.includes(".git");
}

function formatPath(candidatePath: string): string {
  return toWorkspacePath(candidatePath) || candidatePath;
}
