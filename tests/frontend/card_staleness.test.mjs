/**
 * A stale copy of the card must announce itself (#29).
 *
 * The module can legitimately be loaded twice, so `define()` is guarded. The cost
 * of that guard is that the FIRST copy to run wins and cannot be replaced: when a
 * browser is still serving an old build alongside the current one, the old one is
 * what renders, and a release looks like it changed nothing. @elmr91 upgraded twice
 * and kept seeing v1.7.0 in his console with none of the fixes in it.
 *
 * Run with: node --test "tests/frontend/*.test.mjs"
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { before, describe, it } from "node:test";

import { loadCard } from "./dom_stub.mjs";

const CARD = "../../custom_components/rf_fan/frontend/rf-fan-card.js";
const SOURCE = readFileSync(new URL(CARD, import.meta.url), "utf8");

/** Run the card source again, which is what a second <script> tag does to a browser.
 *
 * Not a second `import()` with a cache-busting query: Node stopped re-evaluating on
 * that, so the copy silently never ran and the tests passed by doing nothing. The
 * card is a classic script with no import/export, so evaluating its text is both
 * possible and a truer model of two dashboard URLs than a module import would be.
 */
function anotherCopy() {
  new Function(SOURCE)();
}

/**
 * Load one copy into a registry where `firstVersion` has already won the race.
 *
 * Pass `firstVersion: undefined` for a pre-1.8.0 build, which never recorded one —
 * which is exactly the situation anyone hitting this is in.
 */
async function loadBehind(firstVersion) {
  const warnings = [];
  const realWarn = console.warn;
  console.warn = (message) => warnings.push(String(message));
  try {
    await loadCard();
    globalThis.customElements.define("rf-fan-card", class Incumbent {});
    globalThis.window.__rfFanCardVersion = firstVersion;
    anotherCopy();
    return warnings;
  } finally {
    console.warn = realWarn;
  }
}

let CURRENT;

before(async () => {
  await loadCard();
  anotherCopy();
  CURRENT = globalThis.window.__rfFanCardVersion;
  assert.ok(CURRENT, "the card did not record the version it registered");
});

describe("loading the card twice", () => {
  it("says nothing when both copies are the same build", async () => {
    const warnings = await loadBehind(CURRENT);

    assert.deepEqual(warnings, [], `unexpected warning: ${warnings[0]}`);
  });

  it("names both versions when an older copy already won", async () => {
    const warnings = await loadBehind("1.7.0");

    assert.equal(warnings.length, 1, "the stale copy went unreported");
    assert.match(warnings[0], /1\.7\.0/, "the version in the way is not named");
    assert.match(warnings[0], new RegExp(CURRENT.replace(/\./g, "\\.")), "the new version is not named");
    assert.match(warnings[0], /Resources/, "no pointer at where the stale copy lives");
  });

  it("does not print 'undefined' when the incumbent left no version", async () => {
    // Builds before this change never set the marker, so the fallback text is the
    // path everyone who actually hits this will take.
    const warnings = await loadBehind(undefined);

    assert.equal(warnings.length, 1);
    assert.doesNotMatch(warnings[0], /undefined/, "the message reads 'vundefined'");
    assert.match(warnings[0], /1\.7\.0 or older/);
  });
});
