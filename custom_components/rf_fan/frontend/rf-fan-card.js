/**
 * RF Fan Card — a custom Lovelace card shipped with the `rf_fan` integration.
 *
 * Usage:
 *   type: custom:rf-fan-card
 *   entity: fan.your_fan        # only required field
 *
 * It walks up to the fan's device and auto-discovers the sibling entities
 * (light, colour-temperature select, sound switch, timer buttons, colour
 * calibrate button), showing only the controls that actually exist.
 */

const VERSION = "1.1.0";
// eslint-disable-next-line no-console
console.info(`%c RF-FAN-CARD %c v${VERSION} `, "background:#2e6be6;color:#fff;border-radius:3px 0 0 3px", "background:#2bb0c6;color:#fff;border-radius:0 3px 3px 0");

class RfFanCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("fan.")) {
      throw new Error("rf-fan-card: a `entity` pointing to a fan.* is required");
    }
    this._config = config;
    this._root = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig(hass) {
    const fan = Object.keys(hass.states).find((e) => e.startsWith("fan."));
    return { entity: fan || "fan.example" };
  }

  // ---- discovery -------------------------------------------------------

  _discover() {
    const hass = this._hass;
    const fanId = this._config.entity;
    const cfg = this._config;
    const reg = hass.entities || {};
    const deviceId = reg[fanId] ? reg[fanId].device_id : undefined;

    const siblings = deviceId
      ? Object.keys(reg).filter((e) => reg[e].device_id === deviceId)
      : Object.keys(hass.states);

    const firstOf = (domain, override) => {
      if (override) return override;
      return siblings.find((e) => e.startsWith(domain + "."));
    };

    // Buttons: timers carry a "<n>h" token in their id; the rest is the calibrate button.
    const buttons = siblings.filter((e) => e.startsWith("button."));
    const timers = buttons
      .map((e) => ({ id: e, h: (e.match(/(\d+)\s*h(?![a-z])/i) || [])[1] }))
      .filter((b) => b.h)
      .sort((a, b) => Number(a.h) - Number(b.h));
    const calibrate = cfg.calibrate_entity || buttons.find((e) => !/(\d+)\s*h(?![a-z])/i.test(e));

    return {
      fan: fanId,
      light: firstOf("light", cfg.light_entity),
      color: firstOf("select", cfg.color_entity),
      sound: firstOf("switch", cfg.sound_entity),
      timers,
      calibrate,
    };
  }

  // ---- helpers ---------------------------------------------------------

  _call(domain, service, data) {
    this._hass.callService(domain, service, data);
  }

  _speedInfo(st) {
    const step = st.attributes.percentage_step || 100 / 3;
    const count = Math.max(1, Math.round(100 / step));
    const pct = st.attributes.percentage;
    const index = pct == null ? 0 : Math.round(pct / step);
    return { step, count, index, pct };
  }

  // ---- render ----------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) return;
    const ent = this._discover();
    const fan = this._hass.states[ent.fan];
    if (!fan) {
      this._ensureRoot();
      this._body.innerHTML = `<div class="warn">Entity ${ent.fan} not found</div>`;
      return;
    }

    this._ensureRoot();

    const on = fan.state === "on";
    const { count, index } = this._speedInfo(fan);
    const spinDur = on && index > 0 ? (3.4 - (index / count) * 3.0).toFixed(2) : 0;
    const name = this._config.name || fan.attributes.friendly_name || "Fan";

    // fan glyph
    const blades = [0, 120, 240]
      .map(
        (a) =>
          `<ellipse cx="50" cy="27" rx="13.5" ry="22" transform="rotate(${a} 50 50)"/>`
      )
      .join("");

    // speed segments
    let segs = "";
    for (let i = 1; i <= count; i++) {
      segs += `<button class="seg ${i <= index ? "on" : ""}" data-speed="${i}" title="Speed ${i}"></button>`;
    }

    // control rows
    const rows = [];

    if (ent.light) {
      const l = this._hass.states[ent.light];
      const lit = l && l.state === "on";
      rows.push(
        `<button class="chip ${lit ? "active amber" : ""}" data-act="light"><ha-icon icon="mdi:lightbulb${lit ? "" : "-outline"}"></ha-icon><span>Lampe</span></button>`
      );
    }
    if (ent.sound) {
      const s = this._hass.states[ent.sound];
      const son = s && s.state === "on";
      rows.push(
        `<button class="chip ${son ? "active" : ""}" data-act="sound"><ha-icon icon="mdi:volume-${son ? "high" : "off"}"></ha-icon><span>Son</span></button>`
      );
    }

    // color segments
    let colorRow = "";
    if (ent.color) {
      const c = this._hass.states[ent.color];
      const opts = (c && c.attributes.options) || [];
      const cur = c && c.state;
      const disabled = ent.light && this._hass.states[ent.light] && this._hass.states[ent.light].state === "off";
      const segsC = opts
        .map(
          (o) =>
            `<button class="cseg ${o === cur ? "active" : ""}" data-color="${o}" ${disabled ? "disabled" : ""}>${o}</button>`
        )
        .join("");
      colorRow = `<div class="crow"><ha-icon icon="mdi:thermometer-lines"></ha-icon><div class="csegs">${segsC}</div>${ent.calibrate ? `<button class="mini" data-act="calibrate" title="Recaler la couleur"><ha-icon icon="mdi:target-variant"></ha-icon></button>` : ""}</div>`;
    }

    // direction + preset
    const modeChips = [];
    const feat = fan.attributes.supported_features || 0;
    if (feat & 4) {
      const dir = fan.attributes.direction;
      modeChips.push(
        `<button class="chip ${dir !== "reverse" ? "active" : ""}" data-dir="forward"><ha-icon icon="mdi:rotate-right"></ha-icon><span>Avant</span></button>`,
        `<button class="chip ${dir === "reverse" ? "active" : ""}" data-dir="reverse"><ha-icon icon="mdi:rotate-left"></ha-icon><span>Arrière</span></button>`
      );
    }
    if (feat & 8) {
      const preset = fan.attributes.preset_mode;
      modeChips.push(
        `<button class="chip ${preset !== "natural" ? "active" : ""}" data-preset="normal"><ha-icon icon="mdi:fan"></ha-icon><span>Normal</span></button>`,
        `<button class="chip ${preset === "natural" ? "active" : ""}" data-preset="natural"><ha-icon icon="mdi:weather-windy"></ha-icon><span>Naturel</span></button>`
      );
    }

    // timers
    let timerRow = "";
    if (ent.timers.length) {
      timerRow =
        `<div class="timers">` +
        ent.timers
          .map(
            (t) =>
              `<button class="chip" data-timer="${t.id}"><ha-icon icon="mdi:timer-outline"></ha-icon><span>${t.h}h</span></button>`
          )
          .join("") +
        `</div>`;
    }

    this._body.innerHTML = `
      <div class="head">
        <div class="title">${name}</div>
        <div class="state ${on ? "on" : ""}">${on ? (index > 0 ? `Vitesse ${index}/${count}` : "Marche") : "Arrêt"}</div>
      </div>
      <div class="hero">
        <svg viewBox="0 0 100 100" class="fan ${on ? "on" : "off"}" style="--spin-dur:${spinDur}s" data-act="power" role="button" tabindex="0" aria-label="On/Off">
          <circle class="disc" cx="50" cy="50" r="48"/>
          <g class="blades">${blades}</g>
          <circle class="hub" cx="50" cy="50" r="7.5"/>
          <circle class="hub2" cx="50" cy="50" r="3"/>
        </svg>
      </div>
      <div class="speed">${segs}</div>
      ${rows.length ? `<div class="chips">${rows.join("")}</div>` : ""}
      ${colorRow}
      ${modeChips.length ? `<div class="chips">${modeChips.join("")}</div>` : ""}
      ${timerRow}
    `;
  }

  _ensureRoot() {
    if (this._root) return;
    this.attachShadow({ mode: "open" });
    const card = document.createElement("ha-card");
    const style = document.createElement("style");
    style.textContent = this._css();
    this._body = document.createElement("div");
    this._body.className = "wrap";
    card.appendChild(this._body);
    this.shadowRoot.appendChild(style);
    this.shadowRoot.appendChild(card);
    this._root = card;
    this._body.addEventListener("click", (e) => this._onClick(e));
  }

  _onClick(e) {
    const t = e.target.closest("[data-act],[data-speed],[data-color],[data-dir],[data-preset],[data-timer]");
    if (!t) return;
    const ent = this._discover();
    if (t.dataset.act === "power") this._call("fan", "toggle", { entity_id: ent.fan });
    else if (t.dataset.speed) {
      const { step } = this._speedInfo(this._hass.states[ent.fan]);
      this._call("fan", "set_percentage", { entity_id: ent.fan, percentage: Math.round(Number(t.dataset.speed) * step) });
    } else if (t.dataset.act === "light" && ent.light) this._call("light", "toggle", { entity_id: ent.light });
    else if (t.dataset.act === "sound" && ent.sound) this._call("switch", "toggle", { entity_id: ent.sound });
    else if (t.dataset.color && ent.color) this._call("select", "select_option", { entity_id: ent.color, option: t.dataset.color });
    else if (t.dataset.act === "calibrate" && ent.calibrate) this._call("button", "press", { entity_id: ent.calibrate });
    else if (t.dataset.dir) this._call("fan", "set_direction", { entity_id: ent.fan, direction: t.dataset.dir });
    else if (t.dataset.preset) this._call("fan", "set_preset_mode", { entity_id: ent.fan, preset_mode: t.dataset.preset });
    else if (t.dataset.timer) this._call("button", "press", { entity_id: t.dataset.timer });
  }

  _css() {
    return `
      ha-card { padding: 16px; }
      .head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; }
      .title { font-size:1.15rem; font-weight:600; }
      .state { font-size:.85rem; color: var(--secondary-text-color); }
      .state.on { color: var(--primary-color); }
      .hero { display:flex; justify-content:center; margin:6px 0 10px; }
      .fan { width:150px; height:150px; cursor:pointer; }
      .fan .disc { fill: var(--primary-color); opacity:.10; }
      .fan .blades { transform-origin:50px 50px; animation: rf-spin var(--spin-dur,0s) linear infinite; }
      .fan.off .blades { animation-play-state: paused; }
      .fan .blades ellipse { fill: var(--primary-color); }
      .fan.off .blades ellipse { fill: var(--disabled-text-color); }
      .fan .hub { fill: var(--card-background-color); }
      .fan .hub2 { fill: var(--primary-color); }
      @keyframes rf-spin { from { transform:rotate(0); } to { transform:rotate(360deg); } }
      .speed { display:flex; gap:5px; margin:2px 0 12px; }
      .seg { flex:1; height:12px; border:none; border-radius:6px; background: var(--divider-color); cursor:pointer; padding:0; }
      .seg.on { background: var(--primary-color); }
      .chips { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0; }
      .chip { display:inline-flex; align-items:center; gap:6px; border:none; border-radius:18px; padding:7px 12px;
              background: var(--divider-color); color: var(--primary-text-color); cursor:pointer; font-size:.85rem; }
      .chip ha-icon { --mdc-icon-size:20px; }
      .chip.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .chip.active.amber { background:#f5a623; }
      .crow { display:flex; align-items:center; gap:8px; margin:8px 0; }
      .crow > ha-icon { color: var(--secondary-text-color); --mdc-icon-size:20px; }
      .csegs { display:flex; flex:1; gap:0; border-radius:10px; overflow:hidden; }
      .cseg { flex:1; border:none; padding:8px 4px; background: var(--divider-color); color: var(--primary-text-color);
              cursor:pointer; font-size:.82rem; border-right:1px solid var(--card-background-color); }
      .cseg:last-child { border-right:none; }
      .cseg.active { background: var(--primary-color); color: var(--text-primary-color,#fff); }
      .cseg:disabled { opacity:.4; cursor:not-allowed; }
      .mini { border:none; background: var(--divider-color); border-radius:10px; padding:8px; cursor:pointer; color: var(--secondary-text-color); }
      .timers { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
      .timers .chip { flex:1; justify-content:center; }
      .warn { color: var(--error-color); padding:12px; }
    `;
  }
}

customElements.define("rf-fan-card", RfFanCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "rf-fan-card",
  name: "RF Fan Card",
  description: "Animated card for RF Fan devices (speed, light, colour, timers, sound, direction).",
  preview: true,
  documentationURL: "https://github.com/dasimon135/ha-rf-fan",
});
