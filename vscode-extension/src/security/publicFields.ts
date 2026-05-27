type JsonObject = Record<string, unknown>;

const prohibitedOutputKeys = new Set([
  "chain_of_thought",
  "chainofthought",
  "developerprompt",
  "internal",
  "internalstate",
  "model_policy",
  "modelpolicy",
  "modelprovider",
  "prompt",
  "prompttext",
  "provider",
  "providerinfo",
  "raw_runner_output",
  "rawrunneroutput",
  "skill_body",
  "skill_ref",
  "skill_text",
  "skillbody",
  "skillref",
  "skilltext",
  "systemprompt",
  "tooltrace",
  "trace",
]);

const prohibitedOutputKeyPatterns = [
  /^(?:[a-z0-9]+_)*prompt(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*trace(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*internal(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*provider(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*skill_(?:body|text|ref)(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*chain_of_thought(?:_[a-z0-9]+)*$/,
  /^(?:[a-z0-9]+_)*raw_runner_output(?:_[a-z0-9]+)*$/,
];

export function stripServerOnlyFields(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripServerOnlyFields);
  }
  if (!isJsonObject(value)) {
    return value;
  }

  const result: JsonObject = {};
  for (const [key, nested] of Object.entries(value)) {
    if (isProhibitedOutputKey(key)) {
      continue;
    }
    result[key] = stripServerOnlyFields(nested);
  }
  return result;
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeKey(key: string): string {
  return key
    .trim()
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function isProhibitedOutputKey(key: string): boolean {
  const normalizedKey = normalizeKey(key);
  return prohibitedOutputKeys.has(normalizedKey)
    || prohibitedOutputKeyPatterns.some((pattern) => pattern.test(normalizedKey));
}
