/** Standalone dashboards over the same history view, sensors and services. */
import {HistoryView, STRINGS} from "./ems-home-history.js";

const PERIODS = ["week", "month", "year", "total"];
const STYLES = `
  :host { display: block; min-width: 0; }
  ha-card { display: block; overflow: hidden; }
  .history-view[data-layout="compact"] { padding: 12px; }
  .history-view[data-layout="compact"] .history-list { max-height: 280px; }
  .history-view[data-layout="compact"] .history-track { height: 64px; }
  .history-view[data-chart] { padding: 12px; }
  .history-view[data-chart] .history-kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
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
    this._config = {period: "month", layout: "full", months: 12};
    this._entities = {};
  }

  get chartOnly() { return false; }

  setConfig(config = {}) {
    const next = {period: "month", layout: "full", months: 12, ...config};
    if (!PERIODS.includes(next.period)) throw new Error("period: week | month | year | total");
    if (!this.chartOnly && !["full", "compact"].includes(next.layout)) throw new Error("layout: full | compact");
    if (this.chartOnly && (!Number.isInteger(next.months) || next.months < 6 || next.months > 24)) {
      throw new Error("months: integer 6–24");
    }
    if (next.title !== undefined && typeof next.title !== "string") throw new Error("title: string");
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
      title: this._config.title,
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
    if (!this.chartOnly) return this._config.layout === "compact" ? 7 : 10;
    const height = this.shadowRoot.querySelector("ha-card")?.getBoundingClientRect().height;
    return height ? Math.ceil(height / 50) : 5;
  }
  static getStubConfig() { return {}; }
}

class HistoryChart extends HistoryCard {
  get chartOnly() { return true; }
}

for (const [tag, element] of [["ems-home-history-card", HistoryCard], ["ems-home-history-chart", HistoryChart]]) {
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
