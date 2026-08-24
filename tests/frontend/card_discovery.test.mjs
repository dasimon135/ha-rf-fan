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


// An entry whose remote steps its brightness owns a second button and a second
// select. Both sit next to the ones the card already drives, and both would fire
// the wrong thing if the card matched by position instead of by key.
const BRIGHTNESS_BUTTON = {
  id: "button.f_resynchronise_brightness_to_the_lowest_step",
  translation_key: "resync_brightness",
  name: "Resynchronise brightness (to the lowest step)",
};

const COLOUR_SELECT = {
  id: "select.f_colour_temperature",
  translation_key: "color_temperature",
  name: "Colour temperature",
  state: "Chaud",
  options: ["Chaud", "Neutre", "Froid"],
};

const BRIGHTNESS_SELECT = {
  id: "select.f_assumed_brightness_position",
  translation_key: "brightness_position",
  name: "Assumed brightness position",
  state: "5",
  options: ["1", "2", "3"],
};

describe("stepped-control siblings", () => {
  it("does not mistake the brightness resync button for the colour calibrate one", () => {
    const { hass } = makeHass({
      buttons: [...DEFAULT_BUTTONS, BRIGHTNESS_BUTTON],
    });
    const ent = discover(hass);

    assert.equal(ent.calibrate, "button.f_recalibrate_colour_to_warm");
    assert.equal(ent.timers.length, 4);
  });

  it("keeps them apart without a registry translation key", () => {
    // Older Home Assistant: nothing to match on but the entity_id. Getting this
    // wrong walks the lamp to its dimmest step when the user asks to recalibrate
    // the colour.
    const { hass } = makeHass({
      buttons: [
        { id: "button.f_1h_timer", translation_key: null, name: "1h timer" },
        { id: "button.f_recalibrate_colour", translation_key: null, name: "Recalibrate" },
        { id: "button.f_resync_brightness", translation_key: null, name: "Resync" },
      ],
    });
    const ent = discover(hass);

    assert.equal(ent.calibrate, "button.f_recalibrate_colour");
  });

  it("picks the colour select, not whichever select comes first", () => {
    // Ordered so the WRONG one comes first: the brightness position select emits
    // nothing, so driving the colour row into it would look dead rather than wrong.
    const { hass } = makeHass({ selects: [BRIGHTNESS_SELECT, COLOUR_SELECT] });
    const ent = discover(hass);

    assert.equal(ent.color, "select.f_colour_temperature");
  });

  it("falls back to the first select when no key is exposed", () => {
    const { hass } = makeHass({
      selects: [{ ...COLOUR_SELECT, translation_key: null }],
    });
    const ent = discover(hass);

    assert.equal(ent.color, "select.f_colour_temperature");
  });

  it("prefers an explicit override over any discovery", () => {
    const { hass } = makeHass({ selects: [BRIGHTNESS_SELECT, COLOUR_SELECT] });
    const ent = discover(hass, {
      entity: "fan.x",
      color_entity: "select.somewhere_else",
    });

    assert.equal(ent.color, "select.somewhere_else");
  });
});
