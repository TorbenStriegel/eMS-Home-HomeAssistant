/** Standalone dashboards over the same history view, sensors and services. */
// The view module is imported with the same cache-busting query this module was
// loaded with, so an update cannot leave an old view behind for four hours.
const _version = new URL(import.meta.url).searchParams.get("v");
const {HistoryView, STRINGS} = await import(
  `./ems-home-history.js${_version ? `?v=${encodeURIComponent(_version)}` : ""}`
);

const PERIODS = ["week", "month", "year", "total"];
const METRICS = ["energy", "cost"];
const STYLES = `
  :host { display: block; min-width: 0; box-sizing: border-box; }
  ha-card { display: block; overflow: hidden; box-sizing: border-box; max-width: 100%; }
  .history-view[data-chart] { padding: 12px; }
  .history-view[data-chart] .history-periods { display: none; }
  .history-view[data-chart] .history-kpi > small:last-child { display: none; }
  .history-view[data-chart] .history-column > span { display: block; overflow: hidden; white-space: nowrap; }
  .history-view[data-chart] .history-kpi { padding: 6px; }
  .history-view[data-chart] .history-kpi b { font-size: .9rem; }
  .history-view[data-chart] .history-track { height: 64px; }
  .history-view[data-chart] figure { margin-bottom: 0; }
  .history-view [data-status]:empty { display: none; }
`;

class HistoryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._config = {period: "month", layout: "full", months: 12, metric: "energy"};
    this._entities = {};
  }

  get chartOnly() { return false; }

  setConfig(config = {}) {
    const next = {period: "month", layout: "full", months: 12, metric: "energy", ...config};
    if (!PERIODS.includes(next.period)) throw new Error("period: week | month | year | total");
    if (!this.chartOnly && !["full", "compact"].includes(next.layout)) throw new Error("layout: full | compact");
    if (this.chartOnly && (!Number.isInteger(next.months) || next.months < 6 || next.months > 24)) {
      throw new Error("months: integer 6–24");
    }
    if (!METRICS.includes(next.metric)) throw new Error("metric: energy | cost");
    if (next.title !== undefined && typeof next.title !== "string") throw new Error("title: string");
    if (next.show_sessions !== undefined && typeof next.show_sessions !== "boolean") {
      throw new Error("show_sessions: boolean");
    }
    if (next.show_export !== undefined && typeof next.show_export !== "boolean") {
      throw new Error("show_export: boolean");
    }
    if (next.vehicle !== undefined && typeof next.vehicle !== "string") throw new Error("vehicle: string");
    if (next.entities !== undefined && (!next.entities || typeof next.entities !== "object" || Array.isArray(next.entities) ||
        Object.values(next.entities).some(value => typeof value !== "string"))) throw new Error("entities: role → entity_id");
    this._dispose();
    this._config = next;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._history) this._history.update();
    else this._render();
  }

  connectedCallback() { this._render(); }
  disconnectedCallback() { this._dispose(); }

  _dispose() {
    // Invalidate in-flight reads/deletes without triggering the modal close path.
    if (this._history) {
      this._history.closed = true;
      ++this._history.revision;
      this._history = null;
    }
  }

  _render() {
    if (!this._hass || !this.isConnected || this._history) return;
    this.shadowRoot.innerHTML = "<ha-card></ha-card>";
    const style = document.createElement("style");
    style.textContent = STYLES;
    const view = new HistoryView(this, {
      standalone: true,
      chartOnly: this.chartOnly,
      period: this._config.period,
      vehicle: this.chartOnly ? "" : this._config.vehicle,
      months: this.chartOnly ? this._config.months : 12,
      metric: this._config.metric,
      title: this._config.title,
      // A chart widget shows the numbers, not the ledger. The full history card keeps
      // the ledger as a collapsed disclosure; the chart card only on request.
      // Opt-in everywhere: the ledger is an advanced view, not a default.
      showSessions: this._config.show_sessions === true,
      showExport: this._config.show_export !== false,
      // The compact layout is a tile: same data, a fraction of the controls.
      compact: !this.chartOnly && this._config.layout === "compact",
    });
    this._history = view;
    view.open();
    view.panel.dataset.layout = this._config.layout;
    if (this.chartOnly) view.panel.setAttribute("data-chart", "");
    // Append after the shared styles so compact/narrow-grid rules take precedence.
    this.shadowRoot.appendChild(style);
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (STRINGS[lang] || STRINGS.en)[key] ?? STRINGS.en[key] ?? key;
  }

  _fmt(value, digits = 2) {
    if (!Number.isFinite(value)) return "–";
    try {
      return new Intl.NumberFormat(this._hass?.locale?.language || this._hass?.language || "en", {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
      }).format(value);
    } catch { return value.toFixed(digits); }
  }

  _modeLabel(mode) { return this._t("modes")[mode] || "–"; }

  _whenLabel(iso) {
    const date = new Date(iso);
    if (!iso || Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(this._hass?.locale?.language || this._hass?.language || "en", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  getCardSize() {
    if (!this.chartOnly) return this._config.layout === "compact" ? 4 : 10;
    const height = this.shadowRoot.querySelector("ha-card")?.getBoundingClientRect().height;
    return height ? Math.ceil(height / 50) : 5;
  }
  static getConfigElement() { return document.createElement("ems-home-history-card-editor"); }
  static getStubConfig() { return {period: "month", layout: "full", metric: "energy"}; }
}


const FIELD_LABELS = {
  de: {title: "Überschrift", period: "Startzeitraum", layout: "Darstellung",
       months: "Monate im Diagramm", metric: "Diagramm zeigt", vehicle: "Fahrzeug (Vorauswahl)",
       entry_id: "Config Entry (nur bei mehreren Geräten)", energy: "Energie (kWh)", cost: "Kosten (€)",
       show_sessions: "Ladevorgänge auflisten (erweitert)",
       show_export: "CSV-Export in der Karte zeigen",
       full: "Groß", compact: "Kompakt", all: "Alle Fahrzeuge"},
  en: {title: "Title", period: "Initial period", layout: "Layout",
       months: "Months in the chart", metric: "Chart shows", vehicle: "Vehicle (preset)",
       entry_id: "Config entry (several devices only)", energy: "Energy (kWh)", cost: "Cost (€)",
       show_sessions: "List charging sessions (advanced)",
       show_export: "Show the CSV export in the card",
       full: "Full", compact: "Compact", all: "All vehicles"},
};

class HistoryCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._config = {};
  }

  set hass(hass) { this._hass = hass; this._render(); }
  setConfig(config = {}) { this._config = {...config}; this._render(); }

  get chartOnly() { return false; }

  _text(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (FIELD_LABELS[lang] || FIELD_LABELS.en)[key] || key;
  }

  _schema() {
    const periodOptions = PERIODS.map(period => ({value: period, label: this._t(period)}));
    const fields = [
      {name: "title", selector: {text: {}}},
      {name: "period", selector: {select: {mode: "dropdown", options: periodOptions}}},
      {name: "metric", selector: {select: {mode: "dropdown", options: [
        {value: "energy", label: this._text("energy")}, {value: "cost", label: this._text("cost")}]}}},
    ];
    if (this.chartOnly) {
      // `months` only shapes the monthly chart, so it stays hidden while the card
      // starts on a week or a month (those draw days).
      const period = this._config.period;
      if (period === "year" || period === "total") {
        fields.splice(2, 0, {name: "months", type: "integer", selector: {number: {min: 6, max: 24, step: 1, mode: "box"}}});
      }
    } else {
      fields.splice(2, 0, {name: "layout", selector: {select: {mode: "dropdown", options: [
        {value: "full", label: this._text("full")}, {value: "compact", label: this._text("compact")}]}}});
    }
    if (!this.chartOnly) {
      // Suggestions come from the stored history; a new car can still be typed.
      const vehicles = this._vehicles();
      fields.push({name: "vehicle", selector: {select: {
        mode: "dropdown", custom_value: true,
        options: [{value: "", label: this._text("all")},
                  ...vehicles.map(name => ({value: name, label: name}))],
      }}});
      // The ledger stays out of the first screen unless it is asked for.
      fields.push({name: "show_sessions", selector: {boolean: {}}});
    }
    if (this.chartOnly || this._config.layout !== "compact") {
      // A compact tile has no export, so the switch would only lie.
      fields.push({name: "show_export", selector: {boolean: {}}});
    }
    fields.push(
      // Picking the entry is safer than typing an opaque id.
      {name: "entry_id", selector: {config_entry: {integration: "ems_home"}}},
    );
    return fields;
  }

  _help(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    const text = {
      de: {months: "Wirkt nur im Zeitraum Jahr oder Gesamt; Woche und Monat zeigen Tage.",
           vehicle: "Wirkt auf Liste und Kennzahlen, nicht auf die Monatsbalken.",
           show_sessions: "Standard aus. Zeigt unter dem Diagramm die einzelnen Ladevorgänge.",
           show_export: "Standard an. Das Download-Symbol über dem Diagramm und der Ersatzlink."},
      en: {months: "Only affects the year and total periods; week and month draw days.",
           vehicle: "Affects the list and the KPIs, not the month bars.",
           show_sessions: "Off by default. Shows the individual charging sessions below the chart.",
           show_export: "On by default. The download symbol above the chart and its fallback link."},
    };
    return ((text[lang] || text.en)[key]) || "";
  }

  _vehicles() {
    const names = new Set();
    for (const state of Object.values(this._hass?.states || {})) {
      const stored = state.attributes?.by_vehicle;
      if (stored && typeof stored === "object") {
        for (const name of Object.keys(stored)) names.add(name);
      }
    }
    return [...names].sort((a, b) => a.localeCompare(b));
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      const style = document.createElement("style");
      style.textContent = ":host { display: block; } ha-form { display: block; }"
        + " p.export-hint { margin: 8px 2px 0; font-size: .78rem; line-height: 1.35;"
        + " color: var(--secondary-text-color); }";
      this._form = document.createElement("ha-form");
      this._form.computeLabel = schema => this._text(schema.name) || schema.name;
      this._form.computeHelper = schema => this._help(schema.name);
      this._form.addEventListener("value-changed", event => this._changed(event));
      this._hint = document.createElement("p");
      this._hint.className = "export-hint";
      this.shadowRoot.append(style, this._form, this._hint);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = {...this._config};
    this._hint.textContent = this._t("editor_export_hint");
    this._hint.hidden = !this.chartOnly && this._config.layout === "compact";
  }

  _changed(event) {
    const next = {};
    for (const [key, value] of Object.entries(event.detail.value || {})) {
      if (value === undefined || value === null) continue;
      // An emptied field must remove the option instead of storing a blank value.
      if (typeof value === "string" && !value.trim()) continue;
      next[key] = value;
    }
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", {detail: {config: next}, bubbles: true, composed: true}));
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (STRINGS[lang] || STRINGS.en)[key] ?? STRINGS.en[key] ?? key;
  }
}

class HistoryChartEditor extends HistoryCardEditor {
  get chartOnly() { return true; }
}

class HistoryChart extends HistoryCard {
  get chartOnly() { return true; }
  static getConfigElement() { return document.createElement("ems-home-history-chart-editor"); }
  static getStubConfig() { return {period: "month", months: 12, metric: "energy"}; }
}

for (const [tag, element] of [
  ["ems-home-history-card", HistoryCard], ["ems-home-history-chart", HistoryChart],
  ["ems-home-history-card-editor", HistoryCardEditor], ["ems-home-history-chart-editor", HistoryChartEditor],
]) {
  if (!customElements.get(tag)) customElements.define(tag, element);
}

const language = (document.documentElement.lang || navigator.language || "en").slice(0, 2);
const strings = STRINGS[language] || STRINGS.en;
window.customCards = window.customCards || [];
for (const [type, name, description] of [
  ["ems-home-history-card", strings.history, strings.history_description],
  ["ems-home-history-chart", strings.analysis, strings.chart_description],
]) {
  if (!window.customCards.some(card => card.type === type)) window.customCards.push({type, name, description, preview: true});
}
