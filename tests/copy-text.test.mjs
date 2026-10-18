import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
const require = createRequire(new URL("../web/package.json", import.meta.url));
const ts = require("typescript");
const source = ts.transpileModule(readFileSync(new URL("../web/src/lib/copy-text.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
function setup(clipboard) {
  let copied = "", focused = false, removed = false;
  class Element { closest() { return null; } focus() { focused = true; } }
  const field = { style: {}, select() {}, setSelectionRange() {}, remove() { removed = true; } };
  const context = vm.createContext({ exports: {}, HTMLElement: Element, navigator: { clipboard }, document: {
    activeElement: new Element(), getSelection: () => null, createElement: () => field,
    body: { append() {} }, execCommand(command) { assert.equal(command, "copy"); copied = field.value; return true; },
  }});
  vm.runInContext(source, context);
  return { copy: context.exports.copyText, result: () => ({ copied, focused, removed }) };
}
test("modern clipboard keeps Unicode text intact", async () => {
  let value;
  const app = setup({ writeText: async text => { value = text; } });
  await app.copy("garden, 蓝天");
  assert.equal(value, "garden, 蓝天");
  assert.equal(app.result().copied, "");
});
test("HTTP without Clipboard API copies and restores focus", async () => {
  const app = setup(undefined);
  await app.copy("42\ngarden, blue sky");
  assert.deepEqual(app.result(), { copied: "42\ngarden, blue sky", focused: true, removed: true });
});
