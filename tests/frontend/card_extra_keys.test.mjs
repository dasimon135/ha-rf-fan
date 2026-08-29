/**
 * Free-form keys as chips (#18).
 *
 * The chips are found by translation key — `extra_1`, `extra_2` — and never by
 * elimination. That is #29's lesson: "the button that is not a timer" is what once
 * wired a colour row to the button that walks the lamp down to its bottom stop.
 * Where the registry exposes no keys at all, which is exactly the install that bug
 * was found on, nothing is drawn. Drawing nothing is recoverable; firing the wrong
 * RF code is not.
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

/** Two extra keys, declared out of order to prove the card sorts by index. */
const EXTRAS = [
  { id: "button.ion", translation_key: "extra_2", name: "Ionisation" },
  { id: "button.mem", translation_key: "extra_1", name: "Mémoire" },
];

describe("free-form key chips", () => {
  it("draws one chip per key, named by its owner", () => {
    const { hass } = makeHass({ buttons: EXTRAS });
    const { html } = render(RfFanCard, FULL, hass);

    assert.match(html, /data-extra="button\.mem"/, "the first key was not drawn");
    assert.match(html, /data-extra="button\.ion"/, "the second key was not drawn");
    assert.match(html, /Mémoire/);
    assert.match(html, /Ionisation/);
  });

  it("puts them in the order of the keys on the remote", () => {
    const { hass } = makeHass({ buttons: EXTRAS });
    const { html } = render(RfFanCard, FULL, hass);

    assert.ok(
      html.indexOf("Mémoire") < html.indexOf("Ionisation"),
      "the chips are in alphabetical order, not extra_1 then extra_2"
    );
  });

  it("presses the button that was clicked", () => {
    const { hass, calls } = makeHass({ buttons: EXTRAS });
    const { card } = render(RfFanCard, FULL, hass);

    card._onClick({ target: { closest: () => ({ dataset: { extra: "button.mem" } }) } });

    assert.deepEqual(calls, [
      { domain: "button", service: "press", data: { entity_id: "button.mem" } },
    ]);
  });

  it("draws nothing when the registry exposes no translation keys", () => {
    // @elmr91's install, where the fallbacks had to guess and guessed wrong (#29).
    const unkeyed = EXTRAS.map(({ id, name }) => ({ id, name, translation_key: null }));
    const { hass } = makeHass({ buttons: unkeyed });
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-extra/, "a chip was drawn for a button it had to guess");
  });

  it("is absent from a fan that declared none", () => {
    const { hass } = makeHass({});
    const { html } = render(RfFanCard, FULL, hass);

    assert.doesNotMatch(html, /data-extra/);
  });

  it("stays out of the compact tile, which is one line by construction", () => {
    const { hass } = makeHass({ buttons: EXTRAS });
    const { html } = render(RfFanCard, { ...FULL, layout: "tile" }, hass);

    assert.doesNotMatch(html, /data-extra/);
  });
});
