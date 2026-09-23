/**
 * The card's life as Home Assistant actually drives it: a config that changes
 * under an element that stays, gestures that do not end in a click, and a fan
 * that is not ours.
 *
 * Run with: node --test tests/frontend/
 */

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

import { loadCard, makeHass } from "./dom_stub.mjs";

let RfFanCard;

before(async () => {
  const defined = await loadCard();
  RfFanCard = defined["rf-fan-card"];
});

/** A target that matches exactly one data-attribute selector, as `closest` would. */
function target(dataset, matches) {
  return { dataset, closest: (sel) => (matches.some((m) => sel.includes(m)) ? { dataset } : null) };
}

describe("card lifecycle", () => {
  it("survives a second setConfig on the same element", () => {
    // The dashboard editor's preview keeps the element and hands it each edit.
    const { hass } = makeHass();
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });
    card.hass = hass;

    card.setConfig({ entity: "fan.x", name: "Renamed" });
    card.hass = { ...hass };

    assert.match(card._body.innerHTML, /Renamed/);
  });

  it("does not swallow the tap after a long press that never clicked", async () => {
    // A long press opens more-info at 500 ms; the pointer comes up on the dialog, so
    // no click ever reaches the card to clear the flag it left behind.
    const { hass, calls } = makeHass();
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });
    card.hass = hass;
    card.dispatchEvent = () => {};

    card._onPointerDown({ target: target({ act: "power" }, ["data-act='power'"]) });
    await new Promise((resolve) => setTimeout(resolve, 520));

    const segment = target({ speed: "3" }, ["data-speed"]);
    card._onPointerDown({ target: segment });
    card._onClick({ target: segment });

    assert.equal(calls.length, 1, "the next tap must reach the fan");
    assert.equal(calls[0].service, "set_percentage");
  });

  it("uses no sibling that another integration owns", () => {
    // On a fan from another integration nothing exposes a translation key, and the
    // card used to pick roles by elimination: `button.restart` became "recalibrate".
    const { hass } = makeHass();
    hass.entities["button.dev_restart"] = { device_id: "d1", platform: "esphome" };
    hass.states["button.dev_restart"] = { state: "unknown", attributes: { friendly_name: "Restart" } };
    hass.entities["switch.dev_relay"] = { device_id: "d1", platform: "esphome" };
    hass.states["switch.dev_relay"] = { state: "off", attributes: { friendly_name: "Relay" } };

    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });
    card._hass = hass;
    const ent = card._discover();

    assert.equal(ent.calibrate, undefined);
    assert.equal(ent.sound, undefined);
  });
});
