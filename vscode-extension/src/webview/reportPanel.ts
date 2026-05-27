import type * as vscode from "vscode";

import { stripServerOnlyFields } from "../security/publicFields";

type JsonObject = Record<string, unknown>;

export interface CapabilityRunReport {
  task_id: string;
  status: string;
  capability_id?: string;
  created_at?: string;
  updated_at?: string;
  result?: unknown;
}

const artifactMetadataFields = [
  "name",
  "uri",
  "mime_type",
  "size",
  "sha256",
  "created_at",
  "updated_at",
  "type",
] as const;

export function showCapabilityReportPanel(report: CapabilityRunReport): void {
  const vscodeApi = require("vscode") as typeof vscode;
  const panel = vscodeApi.window.createWebviewPanel(
    "skillCapability.report",
    "Skill Capability Report",
    vscodeApi.ViewColumn.Beside,
    {
      enableScripts: false,
      retainContextWhenHidden: true,
    },
  );
  panel.webview.html = renderReportHtml(report);
}

export function renderReportHtml(report: CapabilityRunReport): string {
  const publicReport = stripServerOnlyFields(report) as CapabilityRunReport;
  const result = isJsonObject(publicReport.result) ? publicReport.result : undefined;
  const sections = [
    renderTaskMetadata(publicReport),
    result ? renderCompletedResult(result) : "<section><p>No completed result yet.</p></section>",
  ];

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 16px; line-height: 1.45; }
    h1, h2, h3 { margin: 0 0 8px; }
    section { border-top: 1px solid var(--vscode-panel-border); padding: 14px 0; }
    .meta, .finding, .artifact { margin: 8px 0; }
    .label { color: var(--vscode-descriptionForeground); font-size: 12px; text-transform: uppercase; }
    .finding { padding: 8px; background: var(--vscode-editorWidget-background); border-radius: 4px; }
    pre { white-space: pre-wrap; word-break: break-word; background: var(--vscode-textCodeBlock-background); padding: 8px; border-radius: 4px; }
    ul { padding-left: 20px; }
  </style>
  <title>Skill Capability Report</title>
</head>
<body>
  <h1>Skill Capability Report</h1>
  ${sections.join("\n")}
</body>
</html>`;
}

function renderTaskMetadata(report: CapabilityRunReport): string {
  const optionalMetadata = [
    ["Capability ID", report.capability_id],
    ["Created At", report.created_at],
    ["Updated At", report.updated_at],
  ].filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1] !== "");

  return `<section>
  <h2>Task</h2>
  <div class="meta"><span class="label">Task ID</span><br>${escapeHtml(report.task_id)}</div>
  <div class="meta"><span class="label">Status</span><br>${escapeHtml(report.status)}</div>
  ${optionalMetadata.map(([label, value]) =>
    `<div class="meta"><span class="label">${escapeHtml(label)}</span><br>${escapeHtml(value)}</div>`,
  ).join("\n")}
</section>`;
}

function renderCompletedResult(result: JsonObject): string {
  return [
    renderTextSection("Summary", result.summary),
    renderFindings(result.findings),
    renderTextSection("Safe Rationale", result.safe_rationale),
    renderTextSection("Confidence", result.confidence),
    renderPatch(result.patch ?? result.patch_preview),
    renderListSection("Recommended Tests", result.recommended_tests),
    renderArtifacts(result.artifacts),
  ].filter(Boolean).join("\n");
}

function renderTextSection(title: string, value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  return `<section><h2>${escapeHtml(title)}</h2><p>${escapeHtml(formatValue(value))}</p></section>`;
}

function renderFindings(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) {
    return "";
  }

  const findings = value.map((finding) => {
    if (!isJsonObject(finding)) {
      return `<div class="finding">${escapeHtml(formatValue(finding))}</div>`;
    }
    const severity = formatValue(finding.severity ?? "unspecified");
    const path = formatValue(finding.path ?? finding.file ?? "");
    const message = formatValue(finding.message ?? finding.summary ?? finding.description ?? "");
    return `<div class="finding">
      <h3>${escapeHtml(severity)}${path ? ` - ${escapeHtml(path)}` : ""}</h3>
      <p>${escapeHtml(message)}</p>
    </div>`;
  }).join("\n");

  return `<section><h2>Findings</h2>${findings}</section>`;
}

function renderPatch(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  const preview = formatValue(value).slice(0, 600);
  return `<section><h2>Patch</h2><p>Patch available</p><details><summary>Preview patch</summary><pre>${escapeHtml(preview)}</pre></details></section>`;
}

function renderListSection(title: string, value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) {
    return "";
  }
  const items = value.map((item) => `<li>${escapeHtml(formatValue(item))}</li>`).join("");
  return `<section><h2>${escapeHtml(title)}</h2><ul>${items}</ul></section>`;
}

function renderArtifacts(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) {
    return "";
  }
  const items = value.map((artifact) => {
    if (!isJsonObject(artifact)) {
      return "";
    }
    const metadata = artifactMetadataFields
      .filter((key) => artifact[key] !== undefined && artifact[key] !== null)
      .map((key) => `${key}: ${formatValue(artifact[key])}`)
      .join(" | ");
    if (!metadata) {
      return "";
    }
    return `<li class="artifact">${escapeHtml(metadata)}</li>`;
  }).filter(Boolean).join("");
  if (!items) {
    return "";
  }
  return `<section><h2>Artifacts</h2><ul>${items}</ul></section>`;
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
