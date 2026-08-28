/**
 * The card must survive a Home Assistant that is not finished loading (#44).
 *
 * `hui-card` wraps `element.hass = this.hass` in a try/catch, and on ANY exception
 * it replaces the card with a bare error card — permanently, and with no message,
 * because the frontend only renders an error card's detail in editor preview. So a
 * single throw on one early update is indistinguishable from "custom element
 * doesn't exist", and costs the user a working card until they reload.
 *
 * On a cold load the registry and the state machine do not arrive together, so the
 * card can legitimately be handed a `hass` where its siblings are registered but
 * have no state yet — or where nothing has arrived at all.
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

const FULL = { entity: "fan.x" };

const SIBLINGS = {
  light: "on",
  lightAttrs: { supported_color_modes: ["brightness"], brightness: 128 },
  buttons: [{ id: "button.t1", translation_key: "timer", name: "1h timer" }],
  selects: [
    {
      id: "select.c",
      translation_key: "color_temperature",
      name: "Colour",
      options: ["1", "2", "3"],
      state: "2",
    },
  ],
};

describe("a partially loaded Home Assistant", () => {
  it("does not throw when the registry is ahead of the state machine", () => {
    const { hass } = makeHass(SIBLINGS);
    // Every sibling is registered on the device, and none of them has arrived in
    // the state machine yet — the ordering a cold load can produce.
    for (const id of Object.keys(hass.states)) {
      if (id !== "fan.x") delete hass.states[id];
    }

    assert.doesNotThrow(() => render(RfFanCard, FULL, hass));
  });

  it("does not throw when even the fan has no state yet", () => {
    const { hass } = makeHass(SIBLINGS);
    for (const id of Object.keys(hass.states)) delete hass.states[id];

    assert.doesNotThrow(() => render(RfFanCard, FULL, hass));
  });

  it("does not throw when the entity registry has not arrived at all", () => {
    const { hass } = makeHass(SIBLINGS);
    delete hass.entities;

    assert.doesNotThrow(() => render(RfFanCard, FULL, hass));
  });

  it("recovers once the states turn up", () => {
    const { hass } = makeHass(SIBLINGS);
    const full = { ...hass.states };
    for (const id of Object.keys(hass.states)) delete hass.states[id];

    const { card } = render(RfFanCard, FULL, hass);
    Object.assign(hass.states, full);
    card.hass = hass;

    assert.match(card._body.innerHTML, /data-speed/, "the card never came back");
  });
});
