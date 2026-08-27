/**
 * The rows of the full card: brightness, colour temperature, blade direction.
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

const DIMMABLE = { supported_color_modes: ["brightness"], brightness: 128 };
const ONOFF = { supported_color_modes: ["onoff"] };

const COLOR = (options, state) => [
  { id: "select.c", translation_key: "color_temperature", name: "Colour", options, state },
];

/** A change/click target that resolves only for the selector it was made for. */
const target = (selector, el) => ({ closest: (q) => (q === selector ? el : null) });

describe("brightness row", () => {
  it("is offered when the lamp declares a brightness mode", () => {
    const { hass } = makeHass({ light: "on", lightAttrs: DIMMABLE });
    const { html } = render(RfFanCard, FULL, hass);

    assert.match(html, /data-bright/, "no brightness control on a dimmable lamp");
    assert.match(html, /value="128"/, "the slider does not show the current level");
  });

  it("is withheld from a lamp that only knows on and off", () => {
    const { hass } = makeHass({ light: "on", lightAttrs: ONOFF });
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-bright/, "a slider that can move nothing was drawn");
  });

  it("is withheld from a fan with no light at all", () => {
    const { hass } = makeHass({ light: null });
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-bright/);
  });

  it("rests at the bottom while the lamp is off, rather than vanishing", () => {
    const { hass } = makeHass({ light: "off", lightAttrs: { supported_color_modes: ["brightness"] } });
    const { html } = render(RfFanCard, FULL, hass);

    assert.match(html, /data-bright/);
    assert.match(html, /value="1"/);
  });

  it("sets the level on the light entity when moved", () => {
    const { hass, calls } = makeHass({ light: "on", lightAttrs: DIMMABLE });
    const { card } = render(RfFanCard, FULL, hass);

    card._onChange({ target: target("[data-bright]", { value: "200" }) });

    assert.deepEqual(calls, [
      { domain: "light", service: "turn_on", data: { entity_id: "light.x", brightness: 200 } },
    ]);
  });

  it("leaves the speed slider alone", () => {
    const { hass, calls } = makeHass({ light: "on", lightAttrs: DIMMABLE });
    const { card } = render(RfFanCard, FULL, hass);

    card._onChange({ target: target("[data-slider]", { value: "66" }) });

    assert.deepEqual(calls, [
      { domain: "fan", service: "set_percentage", data: { entity_id: "fan.x", percentage: 66 } },
    ]);
  });

  it("redraws when only the level changed", () => {
    const { hass } = makeHass({ light: "on", lightAttrs: DIMMABLE });
    const { card } = render(RfFanCard, FULL, hass);

    hass.states["light.x"].attributes.brightness = 240;
    card.hass = hass;

    assert.match(card._body.innerHTML, /value="240"/, "the slider is stuck on a stale level");
  });
});

describe("colour row", () => {
  it("stays usable while the lamp is off (#29)", () => {
    const { hass } = makeHass({
      light: "off",
      selects: COLOR(["1", "2", "3", "4", "5", "6", "7", "8"], "3"),
    });
    const { html } = render(RfFanCard, FULL, hass);

    assert.match(html, /data-color="8"/, "the eight positions were not drawn");
    assert.doesNotMatch(html, /disabled/, "the row refuses what the select entity accepts");
  });

  it("selects the position that was clicked", () => {
    const { hass, calls } = makeHass({
      light: "off",
      selects: COLOR(["1", "2", "3", "4", "5", "6", "7", "8"], "3"),
    });
    const { card } = render(RfFanCard, FULL, hass);

    card._onClick({ target: { closest: () => ({ dataset: { color: "6" } }) } });

    assert.deepEqual(calls, [
      { domain: "select", service: "select_option", data: { entity_id: "select.c", option: "6" } },
    ]);
  });

  // His registry handed the card no translation keys, so it fell through to "the
  // first select" and drew the assumed brightness position — nine segments under a
  // thermometer icon, for a fan configured with five colour positions, and every
  // click silent because that select emits nothing by design.
  const POSITION_FIRST = [
    {
      id: "select.pos",
      translation_key: null,
      entity_category: "config",
      name: "Assumed brightness position",
      options: ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
      state: "5",
    },
    {
      id: "select.c",
      translation_key: null,
      name: "Colour",
      options: ["1", "2", "3", "4", "5"],
      state: "2",
    },
  ];

  it("ignores a config-category select even with no translation key (#29)", () => {
    const { hass } = makeHass({ light: "on", selects: POSITION_FIRST });
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-color="9"/, "the row is drawing the position select");
    assert.match(html, /data-color="5"/);
    assert.doesNotMatch(html, /data-color="6"/, "five positions, not nine");
  });

  it("drives the colour select, not the position one", () => {
    const { hass, calls } = makeHass({ light: "on", selects: POSITION_FIRST });
    const { card } = render(RfFanCard, FULL, hass);

    card._onClick({ target: { closest: () => ({ dataset: { color: "4" } }) } });

    assert.deepEqual(calls, [
      { domain: "select", service: "select_option", data: { entity_id: "select.c", option: "4" } },
    ]);
  });

  it("also recognises the category as the raw wire index", () => {
    // `config` travels as 0, which is falsy — a truthiness test would let it past.
    const numbered = POSITION_FIRST.map((s) =>
      s.entity_category === "config" ? { ...s, entity_category: 0 } : s
    );
    const { hass } = makeHass({ light: "on", selects: numbered });
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-color="9"/);
  });

  it("tightens the segments once there are more than the three named ones", () => {
    const three = render(RfFanCard, FULL, makeHass({ selects: COLOR(["Chaud", "Neutre", "Froid"], "Chaud") }).hass).html;
    const eight = render(RfFanCard, FULL, makeHass({ selects: COLOR(["1", "2", "3", "4", "5", "6", "7", "8"], "1") }).hass).html;

    assert.match(three, /class="csegs"/);
    assert.match(eight, /class="csegs many"/);
  });
});

describe("blade direction", () => {
  it("turns the blades backwards in reverse", () => {
    const { hass } = makeHass({ direction: "reverse" });
    const { html } = render(RfFanCard, FULL, hass);

    assert.match(html, /class="fan on\s+reverse"/);
  });

  it("turns them forwards otherwise", () => {
    const forward = render(RfFanCard, FULL, makeHass({ direction: "forward" }).hass).html;
    const unknown = render(RfFanCard, FULL, makeHass({}).hass).html;

    // Narrowed to the blades: the direction *chips* carry the word too.
    assert.doesNotMatch(forward, /class="fan [^"]*reverse/);
    assert.doesNotMatch(unknown, /class="fan [^"]*reverse/);
  });

  it("does the same on the tile layout", () => {
    const { hass } = makeHass({ direction: "reverse" });
    const { html } = render(RfFanCard, { entity: "fan.x", layout: "tile" }, hass);

    assert.match(html, /class="tfan on reverse"/);
  });
});

describe("card i18n", () => {
  // The card carries its own two-language table rather than reading Home
  // Assistant's, so anything it writes has to be added there by hand — which is
  // exactly what gets forgotten. aria-labels count: a screen reader announces them.
  const FR = { entity: "fan.x" };

  it("translates the tile's speed buttons", () => {
    const en = render(RfFanCard, { ...FR, layout: "tile" }, makeHass({}).hass).html;
    const fr = render(RfFanCard, { ...FR, layout: "tile" }, makeHass({ language: "fr" }).hass).html;

    assert.match(en, /aria-label="Lower"/);
    assert.match(fr, /aria-label="Diminuer"/);
    assert.match(fr, /aria-label="Augmenter"/);
  });

  it("translates the power control and the brightness slider", () => {
    const fr = render(
      RfFanCard,
      FR,
      makeHass({ language: "fr", light: "on", lightAttrs: DIMMABLE }).hass
    ).html;

    assert.match(fr, /aria-label="Marche\/Arrêt"/);
    assert.match(fr, /aria-label="Luminosité"/);
  });

  it("translates the missing-entity warning", () => {
    const { hass } = makeHass({});
    const fr = render(RfFanCard, { entity: "fan.gone" }, { ...hass, language: "fr" }).html;
    const en = render(RfFanCard, { entity: "fan.gone" }, hass).html;

    assert.match(fr, /Entité fan\.gone introuvable/);
    assert.match(en, /Entity fan\.gone not found/);
  });

  it("leaves no English string behind in a French render", () => {
    const fr = render(
      RfFanCard,
      FR,
      makeHass({
        language: "fr",
        light: "on",
        lightAttrs: DIMMABLE,
        selects: COLOR(["Chaud", "Neutre", "Froid"], "Chaud"),
      }).hass
    ).html;

    for (const english of ["Lower", "Raise", "On/Off", "Brightness", "Light", "Sound", "Forward"]) {
      assert.doesNotMatch(fr, new RegExp(`"${english}"|>${english}<`), `untranslated: ${english}`);
    }
  });
});
