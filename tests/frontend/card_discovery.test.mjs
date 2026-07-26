/**
 * Sibling-entity discovery in the bundled card.
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

function discover(hass, config = { entity: "fan.x" }) {
  const card = new RfFanCard();
  card.setConfig(config);
  card._hass = hass;
  return card._discover();
}

// What the integration actually creates: four timer buttons sharing the "timer"
// translation key, plus one calibrate button.
const DEFAULT_BUTTONS = [
  { id: "button.f_1h_timer", translation_key: "timer", name: "1h timer" },
  { id: "button.f_2h_timer", translation_key: "timer", name: "2h timer" },
  { id: "button.f_4h_timer", translation_key: "timer", name: "4h timer" },
  { id: "button.f_8h_timer", translation_key: "timer", name: "8h timer" },
  {
    id: "button.f_recalibrate_colour_to_warm",
    translation_key: "recalibrate_color",
    name: "Recalibrate colour (to Warm)",
  },
];

describe("button discovery", () => {
  it("separates timers from the calibrate button", () => {
    const { hass } = makeHass({ buttons: DEFAULT_BUTTONS });
    const ent = discover(hass);

    assert.equal(ent.timers.length, 4);
    assert.equal(ent.calibrate, "button.f_recalibrate_colour_to_warm");
  });

  it("orders the timers by duration", () => {
    const { hass } = makeHass({ buttons: DEFAULT_BUTTONS });
    const ent = discover(hass);

    assert.deepEqual(
      ent.timers.map((t) => t.h),
      ["1", "2", "4", "8"]
    );
  });

  it("classifies renamed entities by their translation key", () => {
    // A user is free to rename entity_ids; the "<n>h" token then disappears and
    // a name-based guess would take a timer for the calibrate button.
    const renamed = [
      { id: "button.minuterie_une_heure", translation_key: "timer", name: "Minuterie 1h" },
      { id: "button.recaler_couleur", translation_key: "recalibrate_color", name: "Recaler" },
    ];
    const { hass } = makeHass({ buttons: renamed });
    const ent = discover(hass);

    assert.equal(ent.calibrate, "button.recaler_couleur");
    assert.deepEqual(
      ent.timers.map((t) => t.id),
      ["button.minuterie_une_heure"]
    );
  });

  it("reads the hours from the friendly name when the id has no token", () => {
    const renamed = [
      { id: "button.minuterie_courte", translation_key: "timer", name: "Minuterie 2h" },
      { id: "button.minuterie_longue", translation_key: "timer", name: "Minuterie 8h" },
    ];
    const { hass } = makeHass({ buttons: renamed });
    const ent = discover(hass);

    assert.deepEqual(
      ent.timers.map((t) => t.h),
      ["2", "8"]
    );
  });

  it("falls back to the id pattern when no translation key is exposed", () => {
    // Older Home Assistant registries do not surface translation_key.
    const legacy = DEFAULT_BUTTONS.map((b) => ({ ...b, translation_key: null }));
    const { hass } = makeHass({ buttons: legacy });
    const ent = discover(hass);

    assert.equal(ent.timers.length, 4);
    assert.equal(ent.calibrate, "button.f_recalibrate_colour_to_warm");
  });

  it("respects an explicit calibrate_entity override", () => {
    const { hass } = makeHass({ buttons: DEFAULT_BUTTONS });
    const ent = discover(hass, { entity: "fan.x", calibrate_entity: "button.f_1h_timer" });

    assert.equal(ent.calibrate, "button.f_1h_timer");
  });
});
