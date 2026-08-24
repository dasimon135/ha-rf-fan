/**
 * Minimal DOM stub so the Lovelace card can be rendered under `node --test`.
 *
 * The card only ever builds markup through `innerHTML` and appends a handful of
 * elements, so a full DOM implementation (jsdom) would be a dependency for
 * nothing. This covers exactly what `_ensureRoot` / `_render` touch.
 */

class StubElement {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
    this._classes = new Set();
    this.classList = {
      toggle: (name, force) => {
        const want = force === undefined ? !this._classes.has(name) : Boolean(force);
        if (want) this._classes.add(name);
        else this._classes.delete(name);
      },
      contains: (name) => this._classes.has(name),
    };
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener() {}
  setAttribute() {}
  remove() {}
}

class StubHTMLElement extends StubElement {
  constructor() {
    super("custom");
    this.shadowRoot = null;
  }

  attachShadow() {
    this.shadowRoot = new StubElement("#shadow-root");
    return this.shadowRoot;
  }

  dispatchEvent() {}
}

/** Install the globals the card module needs, and return the defined classes. */
export async function loadCard() {
  const defined = {};
  globalThis.HTMLElement = StubHTMLElement;
  // `get` matters as much as `define` here: the card guards both of its
  // registrations on it, so that loading the module twice (integration
  // `add_extra_js_url` + a manual Lovelace resource) does not throw.
  globalThis.customElements = {
    define: (name, cls) => (defined[name] = cls),
    get: (name) => defined[name],
  };
  globalThis.document = {
    createElement: (tag) => new StubElement(tag),
    querySelectorAll: () => [],
    body: new StubElement("body"),
  };
  globalThis.window = { customCards: [], setTimeout, clearTimeout };

  await import("../../custom_components/rf_fan/frontend/rf-fan-card.js");
  return defined;
}

/**
 * A hass double with one rf_fan device: a fan, plus whatever extras are asked for.
 *
 * `buttons` and `selects` entries are `{id, translation_key, name}` — pass
 * `translation_key: null` to emulate a registry that does not expose it (older
 * Home Assistant).
 */
export function makeHass({
  fanState = "on",
  light = null,
  language = "en",
  supportedFeatures = 61,
  buttons = [],
  selects = [],
} = {}) {
  const states = {
    "fan.x": {
      state: fanState,
      attributes: {
        friendly_name: "Ventilo",
        percentage: fanState === "on" ? 50 : 0,
        percentage_step: 100 / 3,
        supported_features: supportedFeatures,
      },
    },
  };
  const entities = { "fan.x": { device_id: "d1", platform: "rf_fan" } };

  if (light !== null) {
    states["light.x"] = { state: light, attributes: {} };
    entities["light.x"] = { device_id: "d1", platform: "rf_fan" };
  }

  for (const b of buttons) {
    states[b.id] = { state: "unknown", attributes: { friendly_name: b.name } };
    entities[b.id] = { device_id: "d1", platform: "rf_fan" };
    if (b.translation_key) entities[b.id].translation_key = b.translation_key;
  }

  for (const sel of selects) {
    states[sel.id] = {
      state: sel.state || "unknown",
      attributes: { friendly_name: sel.name, options: sel.options || [] },
    };
    entities[sel.id] = { device_id: "d1", platform: "rf_fan" };
    if (sel.translation_key) entities[sel.id].translation_key = sel.translation_key;
  }

  const calls = [];
  return {
    hass: {
      language,
      states,
      entities,
      callService: (domain, service, data) => calls.push({ domain, service, data }),
    },
    calls,
  };
}

/** Render the card with a config and return the produced markup. */
export function render(RfFanCard, config, hass) {
  const card = new RfFanCard();
  card.setConfig(config);
  card.hass = hass;
  return { card, html: card._body.innerHTML };
}
