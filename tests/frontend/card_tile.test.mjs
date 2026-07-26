/**
 * Tile layout of the bundled Lovelace card.
 *
 * Run with: node --test tests/frontend/
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

describe("tile layout", () => {
  it("offers a light toggle when the device has a light", () => {
    const { hass } = makeHass({ light: "off" });
    const { html } = render(RfFanCard, TILE, hass);

    assert.match(html, /data-act="light"/, "no light control on the tile");
  });

  it("marks the light control as active while the light is on", () => {
    const off = render(RfFanCard, TILE, makeHass({ light: "off" }).hass).html;
    const on = render(RfFanCard, TILE, makeHass({ light: "on" }).hass).html;

    assert.doesNotMatch(off, /class="tbtn tlight active"/);
    assert.match(on, /class="tbtn tlight active"/);
  });

  it("omits the light control on a fan without a light", () => {
    const { hass } = makeHass({ light: null });
    const { html } = render(RfFanCard, TILE, hass);

    assert.doesNotMatch(html, /data-act="light"/);
  });

  it("keeps the speed controls and the power dot", () => {
    const { hass } = makeHass({ light: "off" });
    const { html } = render(RfFanCard, TILE, hass);

    assert.match(html, /data-tspeed="down"/);
    assert.match(html, /data-tspeed="up"/);
    assert.match(html, /data-act="power"/);
    assert.match(html, /data-act="tileinfo"/);
  });

  it("toggles the light entity when the control is clicked", () => {
    const { hass, calls } = makeHass({ light: "off" });
    const { card } = render(RfFanCard, TILE, hass);

    // The card delegates clicks from its body; simulate the resolved target.
    card._onClick({ target: { closest: () => ({ dataset: { act: "light" } }) } });

    assert.deepEqual(calls, [
      { domain: "light", service: "toggle", data: { entity_id: "light.x" } },
    ]);
  });
});
