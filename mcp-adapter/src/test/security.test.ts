import assert from "node:assert/strict";
import test from "node:test";

import { redactSensitiveText } from "../security.js";

test("redactSensitiveText redacts common sensitive query parameters", () => {
  const text = [
    "https://gateway.example.com/run?password=pwd&authorization=BearerThing&credentials=json",
    "https://gateway.example.com/run?access_key=access&refresh_token=refresh&api_key=api",
    "https://gateway.example.com/run?token=token&key=key&secret=secret&tenant_id=tenant",
  ].join(" ");

  const redacted = redactSensitiveText(text);

  assert.doesNotMatch(redacted, /password=pwd/);
  assert.doesNotMatch(redacted, /authorization=BearerThing/);
  assert.doesNotMatch(redacted, /credentials=json/);
  assert.doesNotMatch(redacted, /access_key=access/);
  assert.doesNotMatch(redacted, /refresh_token=refresh/);
  assert.doesNotMatch(redacted, /api_key=api/);
  assert.doesNotMatch(redacted, /token=token/);
  assert.doesNotMatch(redacted, /key=key/);
  assert.doesNotMatch(redacted, /secret=secret/);
  assert.match(redacted, /password=\[REDACTED\]/);
  assert.match(redacted, /authorization=\[REDACTED\]/);
  assert.match(redacted, /credentials=\[REDACTED\]/);
  assert.match(redacted, /access_key=\[REDACTED\]/);
  assert.match(redacted, /refresh_token=\[REDACTED\]/);
  assert.match(redacted, /api_key=\[REDACTED\]/);
  assert.match(redacted, /token=\[REDACTED\]/);
  assert.match(redacted, /key=\[REDACTED\]/);
  assert.match(redacted, /secret=\[REDACTED\]/);
  assert.match(redacted, /tenant_id=tenant/);
});
