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

const VERSION = "1.4.1";
// eslint-disable-next-line no-console
console.info(`%c RF-FAN-CARD %c v${VERSION} `, "background:#2e6be6;color:#fff;border-radius:3px 0 0 3px", "background:#2bb0c6;color:#fff;border-radius:0 3px 3px 0");

class RfFanCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("fan.")) {
      throw new Error("rf-fan-card: an `entity` pointing to a fan.* is required");
    }
    this._config = config;
    this._root = null;
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature();
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
    if (this._dialogCard) this._dialogCard.hass = hass;
  }

  getCardSize() {
    return this._config && this._config.layout === "tile" ? 1 : 5;
  }

  static getStubConfig(hass) {
    const reg = hass.entities || {};
    const fans = Object.keys(hass.states).filter((e) => e.startsWith("fan."));
    const rf = fans.find((e) => reg[e] && reg[e].platform === "rf_fan");
    return { entity: rf || fans[0] || "fan.example" };
  }

  static getConfigElement() {
    return document.createElement("rf-fan-card-editor");
  }

  // ---- discovery -------------------------------------------------------

  _discover() {
    const hass = this._hass;
    const fanId = this._config.entity;
    const cfg = this._config;
    const reg = hass.entities || {};
    const fanReg = reg[fanId];
    const deviceId = fanReg && fanReg.device_id;

    // Only look at entities on the SAME device. If the device can't be
    // resolved, do NOT guess across the whole system — just show the fan.
    const siblings = deviceId
      ? Object.keys(reg).filter((e) => reg[e] && reg[e].device_id === deviceId)
      : [];

    const firstOf = (domain, override) => {
      if (override) return override;
      return siblings.find((e) => e.startsWith(domain + "."));
    };

    // Buttons: timers carry a "<n>h" token; the remaining one is the calibrate button.
    const isTimer = (e) => /(?:^|[_\s])(\d+)\s*h(?![a-z])/i.test(e);
    const buttons = siblings.filter((e) => e.startsWith("button."));
    const timers = buttons
      .filter(isTimer)
      .map((e) => ({ id: e, h: (e.match(/(\d+)\s*h(?![a-z])/i) || [])[1] }))
      .sort((a, b) => Number(a.h) - Number(b.h));
    const calibrate = cfg.calibrate_entity || buttons.find((e) => !isTimer(e));

    return {
      fan: fanId,
      light: firstOf("light", cfg.light_entity),
      color: firstOf("select", cfg.color_entity),
      sound: firstOf("switch", cfg.sound_entity),
      timers,
      calibrate,
      timerSensor: siblings.find((e) => e.startsWith("sensor.")),
    };
  }

  _signature() {
    if (!this._config || !this._hass) return null;
    const ent = this._discover();
    const ids = [ent.fan, ent.light, ent.color, ent.sound, ent.calibrate, ent.timerSensor]
      .concat(ent.timers.map((t) => t.id))
      .filter(Boolean);
    return ids
      .map((id) => {
        const s = this._hass.states[id];
        if (!s) return id + ":none";
        const a = s.attributes;
        return `${id}:${s.state}:${a.percentage}:${a.direction}:${a.preset_mode}`;
      })
      .join("|");
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

  _labels() {
    const lang = (this._hass && (this._hass.language || (this._hass.locale && this._hass.locale.language))) || "en";
    const fr = String(lang).toLowerCase().startsWith("fr");
    const color = { Chaud: fr ? "Chaud" : "Warm", Neutre: fr ? "Neutre" : "Neutral", Froid: fr ? "Froid" : "Cold" };
    return {
      light: fr ? "Lampe" : "Light",
      sound: fr ? "Son" : "Sound",
      forward: fr ? "Avant" : "Forward",
      reverse: fr ? "Arrière" : "Reverse",
      normal: "Normal",
      natural: fr ? "Naturel" : "Natural",
      speed: fr ? "Vitesse" : "Speed",
      on: fr ? "Marche" : "On",
      off: fr ? "Arrêt" : "Off",
      recalibrate: fr ? "Recaler la couleur" : "Recalibrate colour",
      fan: fr ? "Ventilateur" : "Fan",
      color: (o) => color[o] || o,
    };
  }

  // ---- render ----------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) return;
    const ent = this._discover();
    const fan = this._hass.states[ent.fan];
    this._ensureRoot();
    const tile = this._config.layout === "tile";
    this._root.classList.toggle("tilecard", tile);
    if (!fan) {
      this._body.innerHTML = `<div class="warn">Entity ${ent.fan} not found</div>`;
      return;
    }

    const on = fan.state === "on";
    const L = this._labels();
    const compact = this._config.layout === "compact";
    const { count, index, pct } = this._speedInfo(fan);
    const spinDur = on && index > 0 ? (3.4 - (index / count) * 3.0).toFixed(2) : 0;
    const name = this._config.name || fan.attributes.friendly_name || L.fan;

    const blades = [0, 120, 240]
      .map((a) => `<ellipse cx="50" cy="26" rx="12" ry="23" transform="rotate(${a} 50 50)"/>`)
      .join("");

    // Tile: an ultra-compact row aligned with HA's native tile cards. Tapping
    // the name/state opens the full card in a popup (see _openCardDialog).
    if (tile) {
      const sub = on ? (index > 0 ? `${L.speed} ${index}/${count}` : L.on) : L.off;
      this._body.innerHTML = `
        <div class="tile ${on ? "" : "off"}">
          <button class="tdot" data-act="power" aria-label="${L.on}/${L.off}">
            <svg viewBox="0 0 100 100" class="tfan ${on ? "on" : "off"}" style="--spin-dur:${spinDur}s">
              <g class="blades">${blades}</g>
              <circle class="hub" cx="50" cy="50" r="9"/>
              <circle class="hub2" cx="50" cy="50" r="3.5"/>
            </svg>
          </button>
          <div class="tinfo" data-act="tileinfo" role="button" tabindex="0" aria-label="${name}">
            <span class="tname">${name}</span>
            <span class="tsub">${sub}</span>
          </div>
          <div class="tctl">
            <button class="tbtn" data-tspeed="down" aria-label="Lower">−</button>
            <button class="tbtn" data-tspeed="up" aria-label="Raise">+</button>
          </div>
        </div>`;
      return;
    }

    // speed: segmented for few speeds, slider for many
    let speedHtml;
    if (count <= 10) {
      let segs = "";
      for (let i = 1; i <= count; i++) {
        segs += `<button class="seg ${i <= index ? "on" : ""}" data-speed="${i}" title="${L.speed} ${i}"></button>`;
      }
      speedHtml = `<div class="speed">${segs}</div>`;
    } else {
      speedHtml = `<div class="speed"><input class="slider" type="range" min="0" max="100" step="1" value="${pct || 0}" data-slider/></div>`;
    }

    const rows = [];
    if (ent.light) {
      const l = this._hass.states[ent.light];
      const lit = l && l.state === "on";
      rows.push(`<button class="chip ${lit ? "active amber" : ""}" data-act="light"><ha-icon icon="mdi:lightbulb${lit ? "" : "-outline"}"></ha-icon><span>${L.light}</span></button>`);
    }
    if (ent.sound) {
      const s = this._hass.states[ent.sound];
      const son = s && s.state === "on";
      rows.push(`<button class="chip ${son ? "active" : ""}" data-act="sound"><ha-icon icon="mdi:volume-${son ? "high" : "off"}"></ha-icon><span>${L.sound}</span></button>`);
    }

    let colorRow = "";
    if (ent.color) {
      const c = this._hass.states[ent.color];
      const opts = (c && c.attributes.options) || [];
      const cur = c && c.state;
      const lightOff = ent.light && this._hass.states[ent.light] && this._hass.states[ent.light].state === "off";
      const tint = (i) => (i === 0 ? "#f5a623" : i === opts.length - 1 ? "#3391e6" : "var(--primary-color)");
      const segsC = opts
        .map((o, i) => `<button class="cseg ${o === cur ? "active" : ""}" style="${o === cur ? `background:${tint(i)};color:#fff` : ""}" data-color="${o}" ${lightOff ? "disabled" : ""}>${L.color(o)}</button>`)
        .join("");
      colorRow = `<div class="crow"><ha-icon icon="mdi:thermometer-lines"></ha-icon><div class="csegs">${segsC}</div>${ent.calibrate ? `<button class="mini" data-act="calibrate" title="${L.recalibrate}"><ha-icon icon="mdi:crosshairs-gps"></ha-icon></button>` : ""}</div>`;
    }

    const feat = fan.attributes.supported_features || 0;
    const modeChips = [];
    if (feat & 4) {
      const dir = fan.attributes.direction;
      modeChips.push(
        `<button class="chip ${dir !== "reverse" ? "active" : ""}" data-dir="forward"><ha-icon icon="mdi:rotate-right"></ha-icon><span>${L.forward}</span></button>`,
        `<button class="chip ${dir === "reverse" ? "active" : ""}" data-dir="reverse"><ha-icon icon="mdi:rotate-left"></ha-icon><span>${L.reverse}</span></button>`
      );
    }
    if (feat & 8) {
      const preset = fan.attributes.preset_mode;
      modeChips.push(
        `<button class="chip ${preset !== "natural" ? "active" : ""}" data-preset="normal"><ha-icon icon="mdi:fan"></ha-icon><span>${L.normal}</span></button>`,
        `<button class="chip ${preset === "natural" ? "active" : ""}" data-preset="natural"><ha-icon icon="mdi:weather-windy"></ha-icon><span>${L.natural}</span></button>`
      );
    }

    let timerRow = "";
    if (ent.timers.length) {
      timerRow = `<div class="timers">` + ent.timers
        .map((t) => `<button class="chip" data-timer="${t.id}"><ha-icon icon="mdi:timer-outline"></ha-icon><span>${t.h}h</span></button>`)
        .join("") + `</div>`;
    }

    let timerLine = "";
    if (ent.timerSensor) {
      const ts = this._hass.states[ent.timerSensor];
      if (ts && ts.state !== "unknown" && ts.state !== "unavailable") {
        const disp = this._hass.formatEntityState ? this._hass.formatEntityState(ts) : ts.state;
        timerLine = `<div class="timerline"><ha-icon icon="mdi:timer-sand"></ha-icon><span>${disp}</span></div>`;
      }
    }

    this._body.innerHTML = `
      <div class="head">
        <div class="title">${name}</div>
        <div class="state ${on ? "on" : ""}">${on ? (index > 0 ? `${L.speed} ${index}/${count}` : L.on) : L.off}</div>
      </div>
      <div class="hero">
        <svg viewBox="0 0 100 100" class="fan ${on ? "on" : "off"} ${compact ? "compact" : ""}" style="--spin-dur:${spinDur}s" data-act="power" role="button" tabindex="0" aria-label="On/Off">
          <defs>
            <radialGradient id="rfDisc" cx="50%" cy="42%" r="62%">
              <stop offset="0%" stop-color="var(--primary-color)" stop-opacity="0.22"/>
              <stop offset="100%" stop-color="var(--primary-color)" stop-opacity="0.05"/>
            </radialGradient>
          </defs>
          <circle class="disc" cx="50" cy="50" r="48" fill="url(#rfDisc)"/>
          <g class="blades">${blades}</g>
          <circle class="hub" cx="50" cy="50" r="7.5"/>
          <circle class="hub2" cx="50" cy="50" r="3"/>
        </svg>
      </div>
      ${speedHtml}
      ${rows.length ? `<div class="chips">${rows.join("")}</div>` : ""}
      ${compact ? "" : colorRow}
      ${compact || !modeChips.length ? "" : `<div class="chips">${modeChips.join("")}</div>`}
      ${compact ? "" : timerLine}
      ${compact ? "" : timerRow}
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
    this._body.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.closest("[data-act='tileinfo']")) {
        e.preventDefault();
        this._onTileTap();
      }
    });
    this._body.addEventListener("change", (e) => this._onChange(e));
    this._body.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    this._body.addEventListener("pointerup", () => this._clearHold());
    this._body.addEventListener("pointerleave", () => this._clearHold());
    this._body.addEventListener("pointercancel", () => this._clearHold());
  }

  _onPointerDown(e) {
    if (!e.target.closest("[data-act='power']")) return;
    this._holdTimer = window.setTimeout(() => {
      this._held = true;
      this._clearHold();
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this._discover().fan },
          bubbles: true,
          composed: true,
        })
      );
    }, 500);
  }

  _clearHold() {
    if (this._holdTimer) {
      window.clearTimeout(this._holdTimer);
      this._holdTimer = null;
    }
  }

  // Tile tap → full card in a popup (or HA's native more-info when
  // `tile_tap: more-info` is configured).
  _onTileTap() {
    if (this._config.tile_tap === "more-info") {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this._discover().fan },
          bubbles: true,
          composed: true,
        })
      );
      return;
    }
    this._openCardDialog();
  }

  // Self-contained modal overlay (no external dependency). Mounted on
  // document.body so it is never clipped by the tile's grid cell; HA theme
  // custom properties inherit through the shadow boundary.
  _openCardDialog() {
    if (this._dialog) return;
    // Self-heal: clear any orphaned popup a prior instance may have left, so a
    // stale full-screen overlay can never linger and swallow page clicks.
    document.querySelectorAll("[data-rf-fan-popup]").forEach((h) => h.remove());
    const host = document.createElement("div");
    host.setAttribute("data-rf-fan-popup", "");
    const sr = host.attachShadow({ mode: "open" });
    sr.innerHTML = `<style>
      .scrim { position:fixed; inset:0; z-index:1000; display:grid; place-items:center;
        box-sizing:border-box; padding:16px; background:rgba(0,0,0,.5); animation:rff .15s ease; }
      @keyframes rff { from{opacity:0} to{opacity:1} }
      .wrap { position:relative; width:100%; max-width:400px; }
      .x { position:absolute; top:-12px; right:-12px; z-index:1; width:34px; height:34px;
        border-radius:50%; border:none; cursor:pointer; font-size:17px; line-height:1;
        display:grid; place-items:center;
        background:var(--card-background-color,#fff); color:var(--primary-text-color,#222);
        box-shadow:0 2px 10px rgba(0,0,0,.35); }
      .x:focus-visible { outline:2px solid var(--primary-color,#03a9f4); outline-offset:2px; }
      @media (prefers-reduced-motion: reduce) { .scrim { animation:none } }
    </style>
    <div class="scrim"><div class="wrap"><button class="x" aria-label="Close">✕</button></div></div>`;
    const card = document.createElement("rf-fan-card");
    card.setConfig({ ...this._config, layout: "full" });
    card.hass = this._hass;
    sr.querySelector(".wrap").appendChild(card);
    const close = () => this._closeCardDialog();
    // Tapping anywhere off the card (scrim OR the empty area around it) closes
    // it — far easier to dismiss on a phone than aiming at a thin margin.
    sr.querySelector(".scrim").addEventListener("click", (e) => { if (!e.composedPath().includes(card)) close(); });
    sr.querySelector(".x").addEventListener("click", close);
    this._dialogKey = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", this._dialogKey);
    document.body.appendChild(host);
    this._dialog = host;
    this._dialogCard = card;
  }

  _closeCardDialog() {
    if (this._dialogKey) window.removeEventListener("keydown", this._dialogKey);
    if (this._dialog) this._dialog.remove();
    this._dialog = null;
    this._dialogCard = null;
    this._dialogKey = null;
  }

  disconnectedCallback() { this._closeCardDialog(); }

  _onChange(e) {
    const s = e.target.closest("[data-slider]");
    if (!s) return;
    const ent = this._discover();
    this._call("fan", "set_percentage", { entity_id: ent.fan, percentage: Number(s.value) });
  }

  _onClick(e) {
    if (this._held) {
      this._held = false;
      return;
    }
    const t = e.target.closest("[data-act],[data-speed],[data-color],[data-dir],[data-preset],[data-timer],[data-tspeed]");
    if (!t) return;
    const ent = this._discover();
    if (t.dataset.act === "power") this._call("fan", "toggle", { entity_id: ent.fan });
    else if (t.dataset.act === "tileinfo") this._onTileTap();
    else if (t.dataset.tspeed) {
      const { step, count, index } = this._speedInfo(this._hass.states[ent.fan]);
      const next = Math.max(0, Math.min(count, index + (t.dataset.tspeed === "up" ? 1 : -1)));
      this._call("fan", "set_percentage", { entity_id: ent.fan, percentage: Math.round(next * step) });
    } else if (t.dataset.speed) {
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
      /* Tile (ultra-compact) layout — config: layout: tile */
      ha-card.tilecard { padding: 10px 12px; }
      .tile { display:flex; align-items:center; gap:12px; }
      .tdot { flex:0 0 auto; width:42px; height:42px; border-radius:50%; border:none; cursor:pointer;
              display:grid; place-items:center; padding:0; background: var(--divider-color); }
      .tile:not(.off) .tdot { background: color-mix(in srgb, var(--primary-color) 22%, var(--card-background-color));
              box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 55%, transparent),
                          0 0 14px 1px color-mix(in srgb, var(--primary-color) 45%, transparent); }
      .tfan { width:26px; height:26px; }
      .tfan .blades { transform-origin:50px 50px; animation: rf-spin var(--spin-dur,0s) linear infinite; }
      .tfan.off .blades { animation-play-state: paused; }
      .tfan .blades ellipse { fill: var(--primary-color); }
      .tile.off .tfan .blades ellipse { fill: var(--disabled-text-color); }
      .tfan .hub { fill: var(--card-background-color); }
      .tfan .hub2 { fill: var(--primary-color); }
      .tinfo { flex:1 1 auto; min-width:0; display:flex; flex-direction:column; gap:1px;
               cursor:pointer; border-radius:8px; outline:none; }
      .tinfo:focus-visible { box-shadow: 0 0 0 2px var(--primary-color); }
      .tname { font-weight:600; font-size:.95rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .tsub { font-size:.78rem; color: var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .tctl { flex:0 0 auto; display:flex; gap:6px; }
      .tbtn { width:34px; height:34px; border-radius:9px; border:1px solid var(--divider-color);
              background: var(--card-background-color); color: var(--primary-text-color); font-size:1.1rem;
              cursor:pointer; transition: transform .12s, border-color .2s; }
      .tbtn:hover { border-color: var(--primary-color); }
      .tbtn:active { transform: scale(.9); }
      .head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; }
      .title { font-size:1.15rem; font-weight:600; }
      .state { font-size:.85rem; color: var(--secondary-text-color); }
      .state.on { color: var(--primary-color); }
      .hero { display:flex; justify-content:center; margin:6px 0 10px; }
      .fan { width:150px; height:150px; cursor:pointer; filter: drop-shadow(0 3px 8px rgba(0,0,0,.25)); transition: transform .3s ease; }
      .fan.off { transform: scale(.97); }
      .fan.compact { width:96px; height:96px; }
      .fan .blades { transform-origin:50px 50px; animation: rf-spin var(--spin-dur,0s) linear infinite; transition: opacity .4s ease; }
      .fan.off .blades { animation-play-state: paused; }
      .fan .blades ellipse { fill: var(--primary-color); }
      .fan.off .blades ellipse { fill: var(--disabled-text-color); }
      .fan .hub { fill: var(--card-background-color); }
      .fan .hub2 { fill: var(--primary-color); }
      @keyframes rf-spin { from { transform:rotate(0); } to { transform:rotate(360deg); } }
      .speed { display:flex; gap:5px; margin:2px 0 12px; }
      .seg { flex:1; height:12px; border:none; border-radius:6px; background: var(--divider-color); cursor:pointer; padding:0; }
      .seg.on { background: var(--primary-color); }
      .slider { flex:1; accent-color: var(--primary-color); }
      .chips { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0; }
      .chip { display:inline-flex; align-items:center; gap:6px; border:none; border-radius:18px; padding:7px 12px;
              background: var(--divider-color); color: var(--primary-text-color); cursor:pointer; font-size:.85rem; }
      .chip ha-icon { --mdc-icon-size:20px; }
      .chip.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .chip.active.amber { background:#f5a623; }
      .chip, .seg, .cseg, .mini { transition: filter .15s ease, transform .1s ease, background .2s ease; }
      .chip:hover, .seg:hover, .cseg:not(:disabled):hover, .mini:hover { filter: brightness(1.12); }
      .chip:active, .seg:active, .cseg:not(:disabled):active, .mini:active, .fan:active { transform: scale(.95); }
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
      .timerline { display:flex; align-items:center; gap:6px; margin:8px 0 2px; color: var(--secondary-text-color); font-size:.85rem; }
      .timerline ha-icon { --mdc-icon-size:18px; }
      .warn { color: var(--error-color); padding:12px; }
    `;
  }
}

customElements.define("rf-fan-card", RfFanCard);

/** Visual editor: a native ha-form with a fan entity picker + optional name. */
class RfFanCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({
          entity: "Fan entity (required)",
          name: "Name (optional)",
          layout: "Layout",
          light_entity: "Light entity (override)",
          color_entity: "Colour select (override)",
          sound_entity: "Sound switch (override)",
        }[s.name] || s.name);
      this._form.addEventListener("value-changed", (e) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: e.detail.value },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { domain: "fan" } } },
      { name: "name", selector: { text: {} } },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "full", label: "Full" },
              { value: "compact", label: "Compact" },
              { value: "tile", label: "Tile" },
            ],
          },
        },
      },
      { name: "light_entity", selector: { entity: { domain: "light" } } },
      { name: "color_entity", selector: { entity: { domain: "select" } } },
      { name: "sound_entity", selector: { entity: { domain: "switch" } } },
    ];
    this._form.data = this._config;
  }
}

customElements.define("rf-fan-card-editor", RfFanCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "rf-fan-card",
  name: "RF Fan Card",
  description: "Animated card for RF Fan devices (speed, light, colour, timers, sound, direction).",
  preview: true,
  documentationURL: "https://github.com/dasimon135/ha-rf-fan",
});
