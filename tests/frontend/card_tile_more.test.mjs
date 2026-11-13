/**
 * The tile's secondary line, and the lamp belief corrected by a long press.
 * See docs/plans/2026-11-12-card-tile-sub-and-lamp-hold-design.md.
 *
 * Run with: node --test "tests/frontend/*.test.mjs"
 */

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

import { loadCard, makeHass, render } from "./dom_stub.mjs";

let RfFanCard;

before(async () => {
  const defined = await loadCard();
  RfFanCard = defined["rf-fan-card"];
  assert.ok(RfFanCard, "rf-fan-card was not registered");
});

const TILE = { entity: "fan.x", layout: "tile" };
const END = "2026-11-12T21:30:00+00:00";
const LIGHT_STATE = {
  id: "select.ls",
  translation_key: "light_state",
  entity_category: "config",
  name: "Assumed lamp state",
  options: ["on", "off"],
};

const sub = (opts) => {
  const { card } = render(RfFanCard, TILE, makeHass(opts).hass);
  return card._tileSub();
};
const hhmm = (iso, lang) =>
  new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });

describe("tile secondary line", () => {
  it("shows the speed alone on a running fan in normal airflow", () => {
    assert.equal(sub({ presetMode: "normal" }), "Speed 2/3");
  });

  it("adds a preset that is not normal", () => {
    assert.equal(sub({ presetMode: "natural" }), "Speed 2/3 · Natural");
    assert.equal(sub({ presetMode: "natural 2" }), "Speed 2/3 · Natural 2");
  });

  it("adds the time the timer ends", () => {
    assert.equal(sub({ timerEnd: END }), `Speed 2/3 · until ${hhmm(END, "en")}`);
  });

  it("says nothing of a timer that does not run", () => {
    assert.equal(sub({ timerEnd: "unknown" }), "Speed 2/3");
    assert.equal(sub({ timerEnd: "unavailable" }), "Speed 2/3");
  });

  it("is only Off on a stopped fan, whatever else is set", () => {
    assert.equal(sub({ fanState: "off", presetMode: "natural", timerEnd: END }), "Off");
  });

  it("speaks French", () => {
    assert.equal(
      sub({ language: "fr", presetMode: "natural", timerEnd: END }),
      `Vitesse 2/3 · Naturel · jusqu'à ${hhmm(END, "fr")}`,
    );
  });

  it("is what the tile renders", () => {
    const { html } = render(RfFanCard, TILE, makeHass({ presetMode: "natural" }).hass);
    assert.match(html, /<span class="tsub">Speed 2\/3 · Natural<\/span>/);
  });
});

// The light button, as the delegated handlers resolve it.
const lightTarget = { closest: (sel) => (sel.includes("power") ? null : { dataset: { act: "light" } }) };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

describe("long press on the tile's lamp button", () => {
  it("finds the assumed lamp state select by its translation key", () => {
    const { card } = render(RfFanCard, TILE, makeHass({ light: "on", selects: [LIGHT_STATE] }).hass);
    assert.equal(card._discover().lightState, "select.ls");
  });

  it("flips the belief, sends nothing, and swallows the click that ends it", async () => {
    const { hass, calls } = makeHass({ light: "on", selects: [LIGHT_STATE] });
    const { card } = render(RfFanCard, TILE, hass);
    const events = [];
    card.dispatchEvent = (ev) => events.push(ev);

    card._onPointerDown({ target: lightTarget });
    await wait(600);
    card._onClick({ target: lightTarget });

    assert.deepEqual(calls, [
      { domain: "select", service: "select_option", data: { entity_id: "select.ls", option: "off" } },
    ]);
    const toast = events.find((e) => e.type === "hass-notification");
    assert.ok(toast, "no toast");
    assert.match(toast.detail.message, /off/i);
  });

  it("marks an unlit lamp as lit", async () => {
    const { hass, calls } = makeHass({ light: "off", selects: [LIGHT_STATE] });
    const { card } = render(RfFanCard, TILE, hass);
    card.dispatchEvent = () => {};

    card._onPointerDown({ target: lightTarget });
    await wait(600);

    assert.equal(calls[0].data.option, "on");
  });

  it("leaves a short press sending the code", async () => {
    const { hass, calls } = makeHass({ light: "on", selects: [LIGHT_STATE] });
    const { card } = render(RfFanCard, TILE, hass);

    card._onPointerDown({ target: lightTarget });
    card._clearHold();
    await wait(600);
    card._onClick({ target: lightTarget });

    assert.deepEqual(calls, [{ domain: "light", service: "toggle", data: { entity_id: "light.x" } }]);
  });

  it("does nothing special without the select", async () => {
    const { hass, calls } = makeHass({ light: "on" });
    const { card } = render(RfFanCard, TILE, hass);

    card._onPointerDown({ target: lightTarget });
    await wait(600);
    card._onClick({ target: lightTarget });

    assert.deepEqual(calls, [{ domain: "light", service: "toggle", data: { entity_id: "light.x" } }]);
  });
});
