import type * as vscode from "vscode";

export async function showPatchPreview(patch: string): Promise<void> {
  const vscodeApi = require("vscode") as typeof vscode;
  const document = await vscodeApi.workspace.openTextDocument({
    content: patch,
    language: "diff",
  });
  await vscodeApi.window.showTextDocument(document, {
    preview: true,
    viewColumn: vscodeApi.ViewColumn.Beside,
  });
}
