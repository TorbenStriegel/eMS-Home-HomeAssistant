/**
 * eMS Home Card – an animated energy-flow card for the ABL eMS Home integration.
 *
 * Bundled with the integration and loaded automatically, so it can be used as
 * `type: custom:ems-home-card` without adding a dashboard resource manually.
 *
 * No external dependencies (no lit, no mushroom): everything is plain web
 * component + inline SVG, which keeps it fast and theme-aware.
 */

const VERSION = "1.3.0";

const DEFAULTS = {
  title: "eMS Home",
  layout: "full",
  show_controls: true,
  show_flows: true,
  price: null,
};

const STRINGS = {
  de: {
    grid: "Netz",
    hub: "eMS",
    car: "Auto",
    import: "Bezug",
    export: "Einspeisung",
    idle: "Bereit",
    charging: "Lädt",
    locked: "Gesperrt",
    session: "Ladevorgang",
    energy: "Geladen",
    duration: "Dauer",
    power: "Leistung",
    mode: "Modus",
    pv_quota: "PV-Quote",
    modes: { lock: "Gesperrt", grid: "Netz", pv: "PV", hybrid: "Hybrid" },
    unavailable: "nicht verfügbar",
    cost: "Kosten",
    house: "Hausverbrauch",
    no_stream: "Keine Live-Daten",
  },
  en: {
    grid: "Grid",
    hub: "eMS",
    car: "Car",
    import: "Import",
    export: "Export",
    idle: "Idle",
    charging: "Charging",
    locked: "Locked",
    session: "Session",
    energy: "Charged",
    duration: "Duration",
    power: "Power",
    mode: "Mode",
    pv_quota: "PV quota",
    modes: { lock: "Locked", grid: "Grid", pv: "PV", hybrid: "Hybrid" },
    unavailable: "unavailable",
    cost: "Cost",
    house: "House load",
    no_stream: "No live data",
  },
};

const ICONS = {
  flash: "M11,15H6L13,1V9H18L11,23V15Z",
  home: "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z",
  car:
    "M18.92,6.01C18.72,5.42 18.16,5 17.5,5H6.5C5.84,5 5.28,5.42 5.08,6.01L3,12V20C3,20.55 3.45,21 4,21H5C5.55,21 6,20.55 6,20V19H18V20C18,20.55 18.45,21 19,21H20C20.55,21 21,20.55 21,20V12L18.92,6.01M6.85,7H17.14L18.43,11H5.57L6.85,7M6.5,16C5.67,16 5,15.33 5,14.5C5,13.67 5.67,13 6.5,13C7.33,13 8,13.67 8,14.5C8,15.33 7.33,16 6.5,16M17.5,16C16.67,16 16,15.33 16,14.5C16,13.67 16.67,13 17.5,13C18.33,13 19,13.67 19,14.5C19,15.33 18.33,16 17.5,16Z",
  lock:
    "M12,17A2,2 0 0,0 14,15C14,13.89 13.1,13 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6A2,2 0 0,1 4,20V10C4,8.89 4.9,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z",
  plug:
    "M16,7V3H14V7H10V3H8V7H8C7.45,7 7,7.45 7,8V14.5L11,18.5V22H13V18.5L17,14.5V8C17,7.45 16.55,7 16,7Z",
  sun:
    "M12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,2L14.39,5.42C13.65,5.15 12.84,5 12,5C11.16,5 10.35,5.15 9.61,5.42L12,2M3.34,7L7.5,6.65C6.9,7.16 6.36,7.78 5.94,8.5C5.5,9.24 5.25,10 5.11,10.79L3.34,7M3.36,17L5.12,13.23C5.26,14 5.53,14.78 5.95,15.5C6.37,16.24 6.91,16.86 7.5,17.37L3.36,17M20.65,7L18.88,10.79C18.74,10 18.47,9.23 18.05,8.5C17.63,7.78 17.1,7.15 16.5,6.64L20.65,7M20.64,17L16.5,17.36C17.09,16.85 17.62,16.22 18.04,15.5C18.46,14.77 18.73,14 18.87,13.21L20.64,17M12,22L9.59,18.56C10.33,18.83 11.14,19 12,19C12.82,19 13.63,18.83 14.37,18.56L12,22Z",
  meter:
    "M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M12,6A6,6 0 0,1 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6M12,8A4,4 0 0,0 8,12A4,4 0 0,0 12,16A4,4 0 0,0 16,12A4,4 0 0,0 12,8Z",
  timer:
    "M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12.5,7H11V13L15.25,15.5L16,14.25L12.5,12.25V7Z",
  euro:
    "M15,18.5C12.5,18.5 10.5,16.5 10.5,14H15V12H10.5C10.5,9.5 12.5,7.5 15,7.5C15.9,7.5 16.7,7.7 17.5,8.1L18.5,6.4C17.4,5.8 16.2,5.5 15,5.5C11.4,5.5 8.5,8.4 8.5,12H6V14H8.5C8.5,17.6 11.4,20.5 15,20.5C16.2,20.5 17.4,20.2 18.5,19.6L17.5,17.9C16.7,18.3 15.9,18.5 15,18.5Z",
};

// stroke-based glyphs (used where a filled MDI path would be too busy at small size)
const GLYPHS = {
  pylon: '<path d="M12 3.2 6.3 20.8M12 3.2 17.7 20.8M8.6 13.4h6.8M9.6 9.4h4.8" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
};

const MODE_COLORS = {
  lock: "#94a3b8",
  grid: "#f59e0b",
  pv: "#22c55e",
  hybrid: "#38bdf8",
};

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const num = (stateObj, fallback = 0) => {
  if (!stateObj) return fallback;
  const value = Number.parseFloat(stateObj.state);
  return Number.isFinite(value) ? value : fallback;
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */

class EmsHomeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...DEFAULTS };
    this._hass = null;
    this._signature = "";
    this._entities = {};
    this._quotaTimer = null;
    this._built = false;
  }

  /* -- Lovelace API -------------------------------------------------- */

  static async getConfigElement() {
    return document.createElement("ems-home-card-editor");
  }

  static getStubConfig(hass) {
    return {
      type: "custom:ems-home-card",
      title: "eMS Home",
      layout: "full",
      show_controls: true,
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { ...DEFAULTS, ...config };
    this._entities = {};
    this._built = false;
    this._signature = "";
    if (this._hass) this._render();
  }

  getCardSize() {
    return this._config.layout === "compact" ? 3 : 6;
  }

  getGridOptions() {
    return {
      columns: this._config.layout === "compact" ? 6 : 12,
      min_columns: 4,
      rows: "auto",
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._render();
      return;
    }
    const signature = this._stateSignature();
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  /* -- entity discovery ---------------------------------------------- */

  _resolveEntities() {
    const configured = this._config.entities || {};
    const states = this._hass?.states || {};

    // Entity ids are generated from the translated entity names, so both the
    // English (legacy) and the localised spellings have to be recognised.
    const roles = {
      grid_power: ["grid_power", "netzleistung", "netz_leistung"],
      grid_export: ["grid_power_export", "einspeiseleistung", "netz_einspeisung"],
      ev_power: ["ev_charging_power", "ladeleistung"],
      ev_state: ["ev_charging_state", "ladestatus", "ladezustand"],
      charge_mode: ["charge_mode", "lademodus"],
      pv_quota: ["pv_power_quota", "pv_quote"],
      wallbox_status: ["wallbox_status", "wallbox_status_code", "evse_status"],
      session_duration: ["session_duration", "ladedauer"],
      session_energy: ["session_energy", "ladeenergie"],
      energy_import: ["energy_import", "energiebezug"],
      energy_export: ["energy_export", "energieeinspeisung"],
      pv_power: [],
    };

    const resolved = {};
    for (const [role, needles] of Object.entries(roles)) {
      if (configured[role]) {
        resolved[role] = configured[role];
        continue;
      }
      resolved[role] = null;
      if (!needles.length) continue;

      const candidates = Object.keys(states).filter((id) => {
        const [domain, objectId] = id.split(".");
        if (domain !== "sensor" && domain !== "select" && domain !== "number") return false;
        if (!objectId.includes("ems_home")) return false;
        return needles.some((needle) => objectId.endsWith(needle) || objectId.includes(`_${needle}`));
      });
      // prefer exact suffix matches over substring hits
      candidates.sort((a, b) => {
        const score = (id) => (needles.some((n) => id.endsWith(n)) ? 0 : 1) + id.length / 1000;
        return score(a) - score(b);
      });
      resolved[role] = candidates[0] || null;
    }

    // never let the EV power point at a single phase
    if (resolved.ev_power && /_l[123]$/.test(resolved.ev_power)) resolved.ev_power = null;
    if (resolved.grid_power && /_l[123]$/.test(resolved.grid_power)) resolved.grid_power = null;

    resolved.pv_power = configured.pv_power || null;
    return resolved;
  }

  _stateSignature() {
    const ids = Object.values(this._entities).filter(Boolean);
    return ids.map((id) => `${id}:${this._hass?.states?.[id]?.state ?? "-"}`).join("|");
  }

  /* -- rendering ----------------------------------------------------- */

  _t(key) {
    const locale = (this._hass?.locale?.language || this._hass?.language || "de").slice(0, 2);
    const table = STRINGS[locale] || STRINGS.de;
    return table[key] ?? STRINGS.de[key] ?? key;
  }

  _fmt(value, digits = 2) {
    const locale = this._hass?.locale?.language || "de-DE";
    try {
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value);
    } catch {
      return value.toFixed(digits);
    }
  }

  _render() {
    if (!this._hass) return;
    this._entities = this._resolveEntities();
    this._signature = this._stateSignature();
    this._built = true;

    const e = this._entities;
    const st = this._hass.states;

    const gridPower = num(st[e.grid_power]);
    const evPower = num(st[e.ev_power]);
    const mode = st[e.charge_mode]?.state || st[e.ev_state]?.state || "unknown";
    const charging = evPower > 0.05;
    const exporting = gridPower < -0.05;
    const gridColour = exporting ? "#22c55e" : "#f59e0b";
    const modeColour = MODE_COLORS[mode] || "#94a3b8";
    const compact = this._config.layout === "compact";

    const duration = num(st[e.session_duration]);
    const sessionEnergy = num(st[e.session_energy]);
    const price = Number.parseFloat(this._config.price);
    const cost = Number.isFinite(price) && sessionEnergy > 0 ? sessionEnergy * price : null;

    const live = Boolean(st[e.grid_power]) && st[e.grid_power].state !== "unavailable";

    // animation speed: 2.4s idle … 0.7s at 11 kW
    const speed = charging ? clamp(2.4 - Math.min(evPower, 11) * 0.15, 0.7, 2.4) : 0;
    const gridSpeed = Math.abs(gridPower) > 0.05 ? clamp(2.6 - Math.min(Math.abs(gridPower), 11) * 0.14, 0.9, 2.6) : 0;

    const flow = this._config.show_flows !== false;
    const controls = this._config.show_controls !== false;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card class="${compact ? "compact" : ""}">
        <div class="wrap">
          <header>
            <div class="brand">
              <span class="logo" style="--accent:${modeColour}">${this._icon(ICONS.flash)}</span>
              <div class="titles">
                <h1>${this._config.title}</h1>
                <span class="sub">${this._statusLabel(mode, charging)}${live ? "" : ` · <em>${this._t("no_stream")}</em>`}</span>
              </div>
            </div>
            <div class="badges">
              <span class="pill" style="--accent:${modeColour}">${this._modeLabel(mode)}</span>
              <span class="status ${charging ? "on" : ""}" title="${charging ? this._t("charging") : this._t("idle")}"></span>
            </div>
          </header>

          ${flow ? this._flowTemplate({ gridPower, evPower, gridColour, modeColour, mode, charging, exporting, speed, gridSpeed }) : ""}

          <div class="stats">
            ${this._statTile(
              ICONS.meter,
              exporting ? this._t("export") : this._t("import"),
              this._fmt(Math.abs(gridPower), 2),
              "kW",
              gridColour
            )}
            ${this._statTile(ICONS.car, this._t("power"), this._fmt(evPower, 2), "kW", charging ? "#38bdf8" : "var(--secondary-text-color)")}
            ${this._statTile(ICONS.home, this._t("energy"), this._fmt(sessionEnergy, 1), "kWh")}
            ${this._statTile(ICONS.timer, this._t("duration"), this._fmt(duration, 0), "min")}
          </div>
          ${
            cost !== null
              ? `<div class="caption"><span>${this._t("cost")}</span><b>${this._fmt(cost, 2)} €</b><span class="muted">· ${this._fmt(price, 2)} €/kWh</span></div>`
              : ""
          }

          ${controls ? this._controlsTemplate(mode, e, st) : ""}
        </div>
      </ha-card>
    `;

    this._attachHandlers();
  }

  _modeLabel(mode) {
    const locale = (this._hass?.locale?.language || "de").slice(0, 2);
    const table = STRINGS[locale] || STRINGS.de;
    return table.modes?.[mode] || mode;
  }

  _icon(path, cls = "") {
    return `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
  }

  _statTile(icon, label, value, unit, colour = "var(--primary-text-color)", badge = "") {
    return `
      <div class="tile" ${badge ? `title="${badge}"` : ""}>
        <span class="tile-icon" style="color:${colour}">${this._icon(icon)}</span>
        <div class="tile-body">
          <span class="tile-label">${label}</span>
          <span class="tile-value" style="color:${colour}">${value}<small>${unit}</small></span>
        </div>
      </div>`;
  }

  _flowTemplate({ gridPower, evPower, gridColour, modeColour, mode, charging, exporting, speed, gridSpeed }) {
    const gridActive = Math.abs(gridPower) > 0.05;
    const carActive = evPower > 0.05;
    // direction: import runs towards the hub, export away from it
    const gridDir = exporting ? "reverse" : "normal";

    return `
      <div class="flow">
        <svg viewBox="0 0 420 148" class="flow-svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="glow-${this._uid()}" gradientUnits="userSpaceOnUse" x1="92" y1="58" x2="172" y2="58">
              <stop offset="0%" stop-color="${gridColour}" stop-opacity="0.9"/>
              <stop offset="100%" stop-color="${modeColour}" stop-opacity="0.55"/>
            </linearGradient>
            <linearGradient id="glow2-${this._uid()}" gradientUnits="userSpaceOnUse" x1="248" y1="58" x2="328" y2="58">
              <stop offset="0%" stop-color="${modeColour}" stop-opacity="0.55"/>
              <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.95"/>
            </linearGradient>
          </defs>

          <path class="rail" d="M92 58 H172"/>
          <path class="rail" d="M248 58 H328"/>

          <path class="stream ${gridActive ? "active" : ""}"
                d="M92 58 H172"
                style="--stroke:url(#glow-${this._uid()});--dur:${gridSpeed || 2}s;animation-direction:${gridDir}"/>

          <path class="stream ${carActive ? "active" : ""}"
                d="M248 58 H328"
                style="--stroke:url(#glow2-${this._uid()});--dur:${speed || 2}s"/>

          <g class="node">
            <circle cx="62" cy="58" r="30" class="ring" style="stroke:${gridColour}"/>
            <g transform="translate(48,45) scale(1.17)" fill="${gridColour}"><path d="${ICONS.plug}"/></g>
            <text x="62" y="110" class="label">${this._t("grid")}</text>
            <text x="62" y="132" class="value" style="fill:${gridColour}">${this._fmt(Math.abs(gridPower), 2)}<tspan class="unit"> kW</tspan></text>
          </g>

          <g class="node hub ${charging ? "pulsing" : ""}">
            <circle cx="210" cy="58" r="38" class="ring hub-ring" style="stroke:${modeColour}"/>
            <g transform="translate(194,42) scale(1.33)" fill="${modeColour}"><path d="${ICONS.flash}"/></g>
            <text x="210" y="110" class="label">${this._t("hub")}</text>
            <text x="210" y="132" class="value small">${this._statusLabel(mode, charging)}</text>
          </g>

          <g class="node">
            <circle cx="358" cy="58" r="30" class="ring" style="stroke:${carActive ? "#38bdf8" : "var(--divider-color)"}"/>
            <g transform="translate(344,45) scale(1.17)" fill="${carActive ? "#38bdf8" : "var(--secondary-text-color)"}"><path d="${ICONS.car}"/></g>
            <text x="358" y="110" class="label">${this._t("car")}</text>
            <text x="358" y="132" class="value" style="fill:${carActive ? "#38bdf8" : "var(--secondary-text-color)"}">${this._fmt(evPower, 2)}<tspan class="unit"> kW</tspan></text>
          </g>
        </svg>
      </div>`;
  }

  _iconPath(path, scale = 1.17) {
    return `<path d="${path}" transform="scale(${scale})"/>`;
  }

  _statusLabel(mode, charging) {
    if (mode === "lock") return this._t("locked");
    return charging ? this._t("charging") : this._t("idle");
  }

  _controlsTemplate(mode, e, st) {
    const quotaEntity = st[e.pv_quota];
    const quota = quotaEntity ? num(quotaEntity) : 0;
    const step = Number(quotaEntity?.attributes?.step) || 10;
    this._quotaStep = step;
    const quotaAvailable = Boolean(quotaEntity) && quotaEntity.state !== "unavailable";
    const modes = ["lock", "grid", "pv", "hybrid"];

    return `
      <div class="controls">
        <div class="segmented" role="group" aria-label="${this._t("mode")}">
          ${modes
            .map(
              (m) => `
            <button data-mode="${m}" class="${mode === m ? "sel" : ""}" style="--accent:${MODE_COLORS[m]}"
                    ${st[e.charge_mode] ? "" : "disabled"}>
              ${this._icon(MODE_ICONS[m] || ICONS.flash)}
              <span>${this._modeLabel(m)}</span>
            </button>`
            )
            .join("")}
        </div>

        ${
          quotaAvailable
            ? `<div class="quota ${mode === "pv" || mode === "hybrid" ? "" : "dim"}">
                 <div class="quota-head">
                   <span>${this._t("pv_quota")}</span>
                   <b id="quota-val">${this._fmt(quota, 0)} %</b>
                 </div>
                 <input id="quota" type="range" min="0" max="100" step="${step}" value="${quota}" style="--fill:${quota}%" />
               </div>`
            : ""
        }
      </div>`;
  }

  _attachHandlers() {
    this.shadowRoot.querySelectorAll("button[data-mode]").forEach((button) => {
      button.addEventListener("click", () => this._setMode(button.dataset.mode));
    });

    const range = this.shadowRoot.getElementById("quota");
    if (range) {
      const label = this.shadowRoot.getElementById("quota-val");
      range.addEventListener("input", () => {
        const value = Number.parseFloat(range.value);
        if (label) label.textContent = `${this._fmt(value, 0)} %`;
        range.style.setProperty("--fill", `${value}%`);
      });
      range.addEventListener("change", () => {
        const value = Number.parseFloat(range.value);
        clearTimeout(this._quotaTimer);
        this._quotaTimer = setTimeout(() => this._setQuota(value), 250);
      });
    }
  }

  _setMode(mode) {
    const entity = this._entities.charge_mode;
    if (!entity || !this._hass) return;
    this._hass.callService("select", "select_option", {
      entity_id: entity,
      option: mode,
    });
  }

  _setQuota(value) {
    const entity = this._entities.pv_quota;
    if (!entity || !this._hass) return;
    // keep to the step the entity offers – the firmware drops anything between
    const step = this._quotaStep || 10;
    const rounded = Math.round(value / step) * step;
    this._hass.callService("number", "set_value", {
      entity_id: entity,
      value: rounded,
    });
  }

  _uid() {
    if (!this.__uid) this.__uid = Math.random().toString(36).slice(2, 8);
    return this.__uid;
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card {
        background: var(--ha-card-background, var(--card-background-color, #1c1c1e));
        border-radius: var(--ha-card-border-radius, 20px);
        border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(255,255,255,.08)));
        overflow: hidden;
      }
      .wrap {
        padding: 18px 18px 16px;
        background:
          radial-gradient(120% 120% at 0% 0%, rgba(56,189,248,.10), transparent 55%),
          radial-gradient(100% 100% at 100% 0%, rgba(34,197,94,.08), transparent 60%);
      }
      header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
      .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
      .logo {
        width: 38px; height: 38px; flex: 0 0 38px;
        display: grid; place-items: center; border-radius: 12px;
        background: color-mix(in srgb, var(--accent) 18%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
      }
      .logo svg { width: 20px; height: 20px; fill: var(--accent); }
      .titles { min-width: 0; }
      h1 {
        margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: .2px;
        color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .sub { font-size: .78rem; color: var(--secondary-text-color); }
      .sub em { font-style: normal; color: var(--warning-color, #f59e0b); }
      .badges { display: flex; align-items: center; gap: 10px; }
      .pill {
        font-size: .72rem; font-weight: 600; letter-spacing: .4px; text-transform: uppercase;
        padding: 5px 11px; border-radius: 999px;
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 14%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
      }
      .status {
        width: 9px; height: 9px; border-radius: 50%;
        background: var(--disabled-text-color, #6b7280); box-shadow: 0 0 0 0 rgba(56,189,248,.6);
      }
      .status.on { background: #38bdf8; animation: halo 1.8s ease-out infinite; }
      @keyframes halo {
        0% { box-shadow: 0 0 0 0 rgba(56,189,248,.55); }
        70% { box-shadow: 0 0 0 10px rgba(56,189,248,0); }
        100% { box-shadow: 0 0 0 0 rgba(56,189,248,0); }
      }

      .flow { margin: 8px -4px 2px; }
      .flow-svg { width: 100%; height: auto; display: block; overflow: visible; }
      .rail { fill: none; stroke: var(--divider-color, rgba(255,255,255,.12)); stroke-width: 3; stroke-linecap: round; opacity: .8; }
      .stream {
        fill: none; stroke: var(--stroke); stroke-width: 5; stroke-linecap: round;
        stroke-dasharray: 6 11; opacity: 0;
      }
      .stream.active {
        opacity: 1;
        animation: flow var(--dur, 2s) linear infinite;
        filter: drop-shadow(0 0 3px currentColor);
      }
      @keyframes flow { to { stroke-dashoffset: -60; } }

      .node .ring {
        fill: none;
        stroke-width: 2;
        opacity: .85;
      }
      .node .label { font-size: 12px; font-weight: 600; text-anchor: middle; fill: var(--secondary-text-color); }
      .node .value { font-size: 15px; font-weight: 700; text-anchor: middle; fill: var(--primary-text-color); }
      .node .value.small { font-size: 12px; font-weight: 600; fill: var(--secondary-text-color); }
      .node .unit { font-size: 10px; font-weight: 500; opacity: .75; }
      .hub-ring { stroke-width: 3; }
      .hub.pulsing .hub-ring { animation: pulse 2.2s ease-in-out infinite; transform-origin: 210px 58px; }
      @keyframes pulse {
        0%, 100% { opacity: .55; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.06); }
      }

      .stats {
        display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px; margin-top: 6px;
      }
      .caption {
        display: flex; align-items: baseline; gap: 6px; justify-content: flex-end;
        margin-top: 8px; font-size: .74rem; color: var(--secondary-text-color);
      }
      .caption b { color: var(--primary-text-color); font-size: .86rem; }
      .caption .muted { opacity: .6; }
      .glyph { transform-box: fill-box; }
      .tile {
        display: flex; align-items: center; gap: 8px; min-width: 0;
        padding: 9px 9px; border-radius: 14px;
        background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
        border: 1px solid color-mix(in srgb, var(--primary-text-color) 7%, transparent);
      }
      .tile-icon svg { width: 17px; height: 17px; fill: currentColor; }
      .tile-body { display: flex; flex-direction: column; min-width: 0; }
      .tile-label {
        font-size: .62rem; text-transform: uppercase; letter-spacing: .4px;
        color: var(--secondary-text-color); white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
      }
      .tile-value { font-size: 1.02rem; font-weight: 650; line-height: 1.15; }
      .tile-value small { font-size: .62rem; font-weight: 500; margin-left: 3px; opacity: .65; }

      .controls { margin-top: 14px; display: flex; flex-direction: column; gap: 12px; }
      .segmented {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;
        background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
        padding: 5px; border-radius: 14px;
      }
      .segmented button {
        display: flex; align-items: center; justify-content: center; gap: 6px;
        padding: 9px 6px; border: 0; border-radius: 10px; cursor: pointer;
        background: transparent; color: var(--secondary-text-color);
        font: inherit; font-size: .78rem; font-weight: 600;
        transition: background .18s ease, color .18s ease, transform .12s ease;
      }
      .segmented button svg { width: 16px; height: 16px; fill: currentColor; }
      .segmented button:hover:not(:disabled) { color: var(--primary-text-color); }
      .segmented button:active:not(:disabled) { transform: scale(.97); }
      .segmented button.sel {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 16%, var(--ha-card-background, #1c1c1e));
        box-shadow: 0 2px 10px color-mix(in srgb, var(--accent) 22%, transparent);
      }
      .segmented button:disabled { opacity: .4; cursor: default; }

      .quota { transition: opacity .2s ease; }
      .quota.dim { opacity: .55; }
      .quota-head {
        display: flex; justify-content: space-between; align-items: baseline;
        font-size: .74rem; color: var(--secondary-text-color); margin-bottom: 2px;
      }
      .quota-head b { color: var(--primary-text-color); font-size: .85rem; }
      input[type="range"] {
        -webkit-appearance: none; appearance: none; width: 100%; height: 6px; border-radius: 999px;
        background: linear-gradient(90deg, #22c55e 0%, #22c55e var(--fill, 0%), var(--divider-color, #3f3f46) var(--fill, 0%));
        outline: none; cursor: pointer;
      }
      input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none; width: 17px; height: 17px; border-radius: 50%;
        background: #22c55e; border: 3px solid var(--ha-card-background, #1c1c1e);
        box-shadow: 0 0 0 3px color-mix(in srgb, #22c55e 25%, transparent);
      }
      input[type="range"]::-moz-range-thumb {
        width: 14px; height: 14px; border-radius: 50%; background: #22c55e; border: 3px solid var(--ha-card-background, #1c1c1e);
      }

      .compact .wrap { padding: 14px; }
      .compact .flow { display: none; }
      .compact h1 { font-size: .98rem; }
      .compact .stats { grid-template-columns: repeat(2, 1fr); }
      .compact .caption { justify-content: flex-start; }

      @media (max-width: 420px) {
        .segmented button span { display: none; }
      }
    `;
  }
}

const MODE_ICONS = {
  lock: ICONS.lock,
  grid: ICONS.plug,
  pv: ICONS.sun,
  hybrid: ICONS.flash,
};

/* ------------------------------------------------------------------ */
/* Visual editor                                                       */
/* ------------------------------------------------------------------ */

class EmsHomeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _schema() {
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "full", label: "Vollständig" },
              { value: "compact", label: "Kompakt" },
            ],
          },
        },
      },
      { name: "show_flows", selector: { boolean: {} } },
      { name: "show_controls", selector: { boolean: {} } },
      { name: "price", selector: { number: { min: 0, max: 5, step: 0.01, mode: "box" } } },
      {
        name: "entities",
        type: "expandable",
        schema: [
          { name: "grid_power", selector: { entity: { domain: "sensor" } } },
          { name: "ev_power", selector: { entity: { domain: "sensor" } } },
          { name: "charge_mode", selector: { entity: { domain: "select" } } },
          { name: "pv_quota", selector: { entity: { domain: "number" } } },
          { name: "wallbox_status", selector: { entity: { domain: "sensor" } } },
          { name: "session_duration", selector: { entity: { domain: "sensor" } } },
          { name: "session_energy", selector: { entity: { domain: "sensor" } } },
          { name: "pv_power", selector: { entity: { domain: "sensor" } } },
        ],
      },
    ];
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>
        ha-form { display: block; padding: 4px 0; }
      </style>
      <ha-form></ha-form>
    `;
    const form = this.shadowRoot.querySelector("ha-form");
    form.hass = this._hass;
    form.data = this._config;
    form.schema = this._schema();
    form.computeLabel = (schema) => {
      const labels = {
        title: "Titel",
        layout: "Layout",
        show_flows: "Energiefluss anzeigen",
        show_controls: "Steuerung anzeigen",
        price: "Strompreis (€/kWh)",
        entities: "Entitäten (optional)",
        grid_power: "Netzleistung",
        ev_power: "Ladeleistung",
        charge_mode: "Lademodus",
        pv_quota: "PV-Quote",
        wallbox_status: "Wallbox-Status",
        session_duration: "Ladedauer",
        session_energy: "Geladene Energie",
        pv_power: "PV-Leistung (extern)",
      };
      return labels[schema.name] || schema.name;
    };
    form.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      this._config = { ...this._config, ...ev.detail.value };
      this.dispatchEvent(
        new CustomEvent("config-changed", {
          detail: { config: this._config },
          bubbles: true,
          composed: true,
        })
      );
    });
    this._form = form;
  }
}

/* ------------------------------------------------------------------ */
/* Registration                                                        */
/* ------------------------------------------------------------------ */

if (!customElements.get("ems-home-card")) {
  customElements.define("ems-home-card", EmsHomeCard);
}
if (!customElements.get("ems-home-card-editor")) {
  customElements.define("ems-home-card-editor", EmsHomeCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "ems-home-card")) {
  window.customCards.push({
    type: "ems-home-card",
    name: "eMS Home Card",
    description:
      "Animierter Energiefluss für die ABL eMS Home Wallbox-Steuerung (Netz, Ladung, Modus, PV-Quote).",
    preview: true,
    documentationURL: "https://github.com/TorbenStriegel/eMS-Home-HomeAssistant",
  });
}

console.info(`%c EMS-HOME-CARD %c ${VERSION} `, "background:#0f766e;color:#fff;border-radius:3px 0 0 3px", "background:#134e4a;color:#a7f3d0;border-radius:0 3px 3px 0");
