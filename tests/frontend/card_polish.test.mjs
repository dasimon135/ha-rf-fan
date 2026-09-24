/**
 * Second-review polish on the bundled card: the keyboard, the popup's role, what a
 * re-render notices, a timer with no hour to read, and the visual editor.
 *
 * Run with: node --test tests/frontend/
 */

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

import { loadCard, makeHass } from "./dom_stub.mjs";

let RfFanCard;
let RfFanCardEditor;

before(async () => {
  const defined = await loadCard();
  RfFanCard = defined["rf-fan-card"];
  RfFanCardEditor = defined["rf-fan-card-editor"];
});

function mounted(config = { entity: "fan.x" }, options = {}) {
  const made = makeHass(options);
  const card = new RfFanCard();
  card.setConfig(config);
  card.hass = made.hass;
  return { card, ...made };
}

describe("card polish", () => {
  it("toggles the fan when Enter is pressed on the focused fan picture", () => {
    const { card, calls } = mounted();
    let prevented = false;
    card._body.fire("keydown", {
      key: "Enter",
      preventDefault: () => (prevented = true),
      target: { closest: (sel) => (sel.includes("data-act='power'") ? { dataset: { act: "power" } } : null) },
    });

    assert.equal(calls.length, 1);
    assert.equal(calls[0].service, "toggle");
    assert.ok(prevented, "Space must not also scroll the page");
  });

  it("re-renders when only a friendly name changes", () => {
    const { card, hass } = mounted();
    const renamed = {
      ...hass,
      states: {
        ...hass.states,
        "fan.x": {
          ...hass.states["fan.x"],
          attributes: { ...hass.states["fan.x"].attributes, friendly_name: "Plafonnier" },
        },
      },
    };
    card.hass = renamed;

    assert.match(card._body.innerHTML, /Plafonnier/);
  });

  it("does not draw a bare 'h' for a timer whose hours cannot be read", () => {
    const { card } = mounted(
      { entity: "fan.x" },
      { buttons: [{ id: "button.f_nap", translation_key: "timer", name: "Nap" }] }
    );

    assert.doesNotMatch(card._body.innerHTML, /<span>h<\/span>/);
  });

  it("offers every option the card reads in the visual editor", () => {
    const editor = new RfFanCardEditor();
    editor.setConfig({ entity: "fan.x" });
    editor.hass = makeHass().hass;
    const names = editor._form.schema.map((field) => field.name);

    assert.ok(names.includes("tile_tap"), "tile_tap");
    assert.ok(names.includes("calibrate_entity"), "calibrate_entity");
  });

  it("reports a smaller size for the compact layout", () => {
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x", layout: "compact" });
    const full = new RfFanCard();
    full.setConfig({ entity: "fan.x" });

    assert.ok(card.getCardSize() < full.getCardSize());
  });
});
