/**
 * How often the card walks the entity registry.
 *
 * Home Assistant hands every card a new `hass` on EVERY state change anywhere in
 * the house, and the card used to answer each one by filtering the whole entity
 * registry to find its device's siblings -- twice when it then re-rendered. On a
 * large install that is thousands of keys, many times a second, per card.
 *
 * The registry object is only replaced when the registry changes, so its identity
 * is the cache key: same object, same siblings.
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

/** Wrap a registry so that every full enumeration of it is counted. */
function counted(entities) {
  const scans = { count: 0 };
  const proxy = new Proxy(entities, {
    ownKeys(target) {
      scans.count += 1;
      return Reflect.ownKeys(target);
    },
  });
  return { proxy, scans };
}

describe("entity registry scans", () => {
  it("does not rescan while the registry object is the same", () => {
    const { hass } = makeHass({ light: "off" });
    const { proxy, scans } = counted(hass.entities);
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });

    card.hass = { ...hass, entities: proxy };
    assert.equal(scans.count, 1, "one scan to find the siblings");

    // The lamp comes on: a state change, a re-render, the same registry.
    const states = { ...hass.states, "light.x": { state: "on", attributes: {} } };
    card.hass = { ...hass, entities: proxy, states };

    assert.equal(scans.count, 1);
    assert.match(card._body.innerHTML, /mdi:lightbulb"/, "and it did re-render");
  });

  it("rescans when the registry is replaced", () => {
    const { hass } = makeHass();
    const first = counted(hass.entities);
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });
    card.hass = { ...hass, entities: first.proxy };

    // A light joins the device: Home Assistant delivers a NEW registry object.
    const grown = makeHass({ light: "on" }).hass;
    const second = counted(grown.entities);
    card.hass = { ...grown, entities: second.proxy };

    assert.equal(second.scans.count, 1);
    assert.match(card._body.innerHTML, /data-act="light"/);
  });

  it("escapes a preset name it did not choose", () => {
    // The card accepts any `fan.*`, so `preset_modes` is not always ours.
    const { hass } = makeHass();
    hass.states["fan.x"].attributes.preset_modes = ['a"b<c'];
    const card = new RfFanCard();
    card.setConfig({ entity: "fan.x" });
    card.hass = hass;

    assert.match(card._body.innerHTML, /data-preset="a&quot;b&lt;c"/);
  });
});
