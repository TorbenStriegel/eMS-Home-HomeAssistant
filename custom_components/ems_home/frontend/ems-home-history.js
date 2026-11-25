/** Shared charging history view for the flow card and standalone widgets. */
export const STRINGS = {
  de: {
    history: "Verlauf", analysis: "Ladeauswertung", cost: "Kosten", saved: "gespart",
    grid: "Netz", pv: "PV", mode: "Modus",
    modes: {lock: "Gesperrt", grid: "Netz", pv: "PV", hybrid: "Hybrid"},
    chart_months: "Energie je Monat · letzte {months} Monate",
    all_vehicles: "alle Fahrzeuge",
    chart_cost: "Kosten und Ersparnis je Monat · letzte {months} Monate",
    chart_days: "Energie je Tag · letzte {days} Tage",
    chart_cost_days: "Kosten und Ersparnis je Tag · letzte {days} Tage",
    paid: "Kosten", avoided: "Ersparnis", unknown: "unbekannt",
    no_sessions: "keine Ladevorgänge",
    stack_note: "Der Balken zeigt Kosten und Ersparnis zusammen.",
    stack_total: "zusammen",
    compact_summary: "{period}: Kosten {cost}, Ersparnis {saved}",
    compact_summary_energy: "{period}: {energy} kWh, {sessions} Vorgänge",
    sessions_title: "Ladevorgänge ({count})",
    selection_hint: "Tippe auf einen Balken für die genauen Werte.",
    selected: "ausgewählt", previous_day: "Vorheriger Tag", next_day: "Nächster Tag",
    unit_energy: "Energie in kWh", unit_cost: "Kosten und Ersparnis in Euro",
    chart_unit: "Diagrammeinheit",
    cost_partial: "Einzelne Monate enthalten keine Kostendaten.",
    cost_partial_days: "Einzelne Tage enthalten keine Kostendaten.",
    split_partial: "Einzelne Monate enthalten keine Netz/PV-Aufteilung.",
    no_money: "Keine gespeicherten Preisdaten in diesem Zeitraum.",
    export_csv: "Als CSV exportieren", export_running: "Export läuft …",
    export_ready: "CSV mit {rows} Vorgängen, {range}. Link bis {until}.",
    export_expired: "Link abgelaufen. Bitte erneut exportieren.",
    export_link: "Falls kein Download startet: Datei laden",
    export_failed: "Export fehlgeschlagen:",
    editor_export_hint: "Export: das Download-Symbol über dem Diagramm speichert den angezeigten Zeitraum als CSV.",
    history_description: "Ladehistorie mit Filtern, Details und Löschen.",
    chart_description: "Kennzahlen und monatliche Ladeenergie ohne Verlaufsliste.",
    week: "Woche", month: "Monat", year: "Jahr", total: "Gesamt", close: "Schließen",
    sessions: "Vorgänge", average: "Ø {value} kWh je Vorgang", vehicle: "Fahrzeug", all: "Alle",
    kpi_energy: "Energie (kWh)", kpi_cost: "Kosten (€)", kpi_saved: "Ersparnis (€)",
    chart: "kWh / Monat · letzte 12 Monate · alle Fahrzeuge", empty: "Noch keine abgeschlossenen Ladevorgänge in dieser Auswahl.",
    loading: "Lade Verlauf …", error: "Verlauf konnte nicht geladen werden.", retry: "Erneut versuchen",
    load_error: "Der Historienspeicher konnte nicht geladen werden. Die Datei bleibt unverändert.",
    more: "Weitere laden", start: "Start", end: "Ende", prices: "Preise", reason: "Endegrund",
    unplugged: "Fahrzeug getrennt", idle: "Keine Ladeleistung", estimated: "geschätzt",
    gap: "Datenlücke", restarted: "Neustart während des Ladens", mode_changed: "Modus geändert",
    clock_suspect: "Zeitangaben möglicherweise unzuverlässig", remove: "Vorgang löschen",
    confirm: "Diesen Ladevorgang dauerhaft löschen?", cancel: "Abbrechen", confirm_remove: "Ja, löschen",
    delete_error: "Löschen fehlgeschlagen. Der Vorgang wurde nicht entfernt.",
    total_only: "Gesamtenergie: Die Monatsdaten enthalten keine Netz/PV-Aufteilung.",
    vehicle_saved: "Ersparnis pro Fahrzeug nicht verfügbar.", partial: "Kosten nur für Vorgänge mit gespeichertem Preis.",
    unavailable_history: "Historie ist derzeit nicht verfügbar.",
    target_error: "Historie nicht eindeutig zuordenbar. Zeitraum-Sensoren oder entry_id konfigurieren.",
  },
  en: {
    history: "History", analysis: "Charging summary", cost: "Cost", saved: "saved",
    grid: "Grid", pv: "PV", mode: "Mode",
    modes: {lock: "Locked", grid: "Grid", pv: "PV", hybrid: "Hybrid"},
    chart_months: "Energy per month · last {months} months",
    all_vehicles: "all vehicles",
    chart_cost: "Cost and savings per month · last {months} months",
    chart_days: "Energy per day · last {days} days",
    chart_cost_days: "Cost and savings per day · last {days} days",
    paid: "Cost", avoided: "Savings", unknown: "unknown",
    no_sessions: "no charging sessions",
    stack_note: "The bar shows cost and savings together.",
    stack_total: "together",
    compact_summary: "{period}: cost {cost}, savings {saved}",
    compact_summary_energy: "{period}: {energy} kWh, {sessions} charges",
    sessions_title: "Charging sessions ({count})",
    selection_hint: "Tap a bar for the exact values.",
    selected: "selected", previous_day: "Previous day", next_day: "Next day",
    unit_energy: "Energy in kWh", unit_cost: "Cost and savings in euro",
    chart_unit: "Chart unit",
    cost_partial: "Some months carry no cost data.",
    cost_partial_days: "Some days carry no cost data.",
    split_partial: "Some months carry no grid/PV split.",
    no_money: "No stored price data in this period.",
    export_csv: "Export as CSV", export_running: "Exporting …",
    export_ready: "CSV with {rows} sessions, {range}. Link until {until}.",
    export_expired: "Link expired. Please export again.",
    export_link: "If no download starts: load the file",
    export_failed: "Export failed:",
    editor_export_hint: "Export: the download symbol above the chart saves the visible range as CSV.",
    history_description: "Charging history with filters, details and deletion.",
    chart_description: "Key figures and monthly charging energy without a session list.",
    week: "Week", month: "Month", year: "Year", total: "Total", close: "Close",
    sessions: "Sessions", average: "Ø {value} kWh per session", vehicle: "Vehicle", all: "All",
    kpi_energy: "Energy (kWh)", kpi_cost: "Cost (€)", kpi_saved: "Savings (€)",
    chart: "kWh / month · last 12 months · all vehicles", empty: "No completed charging sessions in this selection yet.",
    loading: "Loading history …", error: "Could not load history.", retry: "Try again",
    load_error: "The history store could not be loaded. The file is left unchanged.",
    more: "Load more", start: "Start", end: "End", prices: "Prices", reason: "End reason",
    unplugged: "Vehicle unplugged", idle: "No charging power", estimated: "estimated",
    gap: "Data gap", restarted: "Restart during charging", mode_changed: "Mode changed",
    clock_suspect: "Timestamps may be unreliable", remove: "Delete session",
    confirm: "Permanently delete this charging session?", cancel: "Cancel", confirm_remove: "Yes, delete",
    delete_error: "Deletion failed. The session was not removed.",
    total_only: "Total energy: monthly data does not include the grid/PV split.",
    vehicle_saved: "Savings per vehicle are unavailable.", partial: "Costs only include sessions with a stored price.",
    unavailable_history: "History is currently unavailable.",
    target_error: "Cannot identify history unambiguously. Configure period sensors or entry_id.",
  },
};

// Service data and vehicle names are untrusted, including in HTML attributes.
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
const numeric = value => typeof value === "number" && Number.isFinite(value);
const PERIODS = ["week", "month", "year", "total"];
const STYLES = `
  .history-view {
    container-type: inline-size; padding: 16px; color: var(--primary-text-color);
    /* #03a9f4 only reaches 2,63:1 on white; the darker tone reaches 4,8:1. */
    --history-bar: var(--primary-color);
  }
  .history-view[data-dark="0"] { --history-bar: #0277bd; }
  .history-view [hidden] { display: none !important; }
  .history-view .history-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .history-view h2 { margin: 0 auto 0 0; font-size: 1rem; }
  .history-view button, .history-view select {
    font: inherit; font-size: .8rem; color: var(--primary-text-color);
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--divider-color); border-radius: 8px;
    /* Fingers need a target, not a hint of one. */
    min-height: 44px; padding: 10px 14px; cursor: pointer;
  }
  .history-view [data-close] { min-width: 44px; min-height: 44px; font-size: 1.25rem; line-height: 1; }
  .history-view .history-filter select { min-height: 44px; width: 100%; }
  .history-view button:disabled { opacity: .5; cursor: default; }
  .history-view button[aria-pressed="true"] { border-color: var(--primary-color); color: var(--primary-color); }
  .history-view .history-periods { display: flex; flex-wrap: wrap; gap: 4px; }
  .history-view .history-filter { display: block; margin-top: 12px; font-size: .8rem; }
  .history-view .history-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 10px 0 12px; }
  .history-view .history-kpi { min-width: 0; padding: 1px 10px; border-left: 1px solid var(--divider-color); }
  .history-view .history-kpi:first-child { border-left: 0; padding-left: 0; }
  .history-view .history-kpi > small:first-child {
    display: block; font-size: .66rem; line-height: 1.25; text-transform: uppercase;
    letter-spacing: .02em; color: var(--secondary-text-color); overflow-wrap: anywhere;
  }
  .history-view .history-kpi b {
    display: block; font-size: 1.08rem; font-weight: 600; line-height: 1.25;
    white-space: nowrap; font-variant-numeric: tabular-nums;
  }
  .history-view .history-kpi > small:last-child {
    display: block; font-size: .68rem; line-height: 1.3; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }
  .history-view small, .history-view .history-note { font-size: .74rem; color: var(--secondary-text-color); }
  .history-view figure { margin: 14px 0; }
  .history-view .history-figure-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; margin-bottom: 8px; }
  .history-view figcaption { font-size: .8rem; flex: 1 1 0; min-width: 0; }
  .history-view .history-metrics { display: flex; gap: 4px; }
  .history-view .history-metrics button { min-width: 52px; min-height: 44px; padding: 8px 12px; font-size: .8rem; }
  .history-view .history-step { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 8px; }
  .history-view .history-step button { min-width: 48px; min-height: 48px; font-size: 1.15rem; line-height: 1; padding: 0; }
  .history-view .history-step [data-step-label] { font-size: .8rem; color: var(--secondary-text-color); min-width: 0; text-align: center; }
  .history-view .history-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; font-size: .72rem; color: var(--secondary-text-color); }
  .history-view .history-legend span { display: inline-flex; align-items: center; gap: 4px; }
  .history-view .history-legend i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
  .history-view .history-legend .grid, .history-view .history-legend .paid { background: var(--history-bar); }
  .history-view .history-legend .pv { background: var(--success-color, var(--accent-color)); }
  .history-view .history-legend .avoided { background: repeating-linear-gradient(45deg, var(--success-color, var(--accent-color)) 0 2px, transparent 2px 4px); border: 1px solid var(--success-color, var(--accent-color)); }
  .history-view .history-legend .total { background: var(--secondary-text-color); }
  /* The selected column draws a 2 px ring around its track. A scrolling chart clips at
     its padding edge, so the ring needs room above and beside the track. */
  .history-view .history-chart { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 3px; padding: 3px 3px 0; }
  .history-view .history-chart[data-money="1"] { gap: 4px; overflow-x: auto; padding: 3px 3px 2px; }
  .history-view .history-chart[data-daily="1"] { overflow-x: auto; }
  .history-view .history-chart[data-daily="1"] .history-column { font-size: .58rem; }
  .history-view .history-column { min-width: 0; text-align: center; font-size: .62rem; cursor: pointer; }
  .history-view [data-export] { display: inline-flex; align-items: center; justify-content: center;
    gap: 5px; min-width: 0; min-height: 44px; padding: 0 10px; flex: none; align-self: center;
    font-size: .78rem; }
  .history-view [data-export][disabled] { opacity: .55; }
  .history-view .history-export-note { margin: 0 0 6px; font-size: .78rem; color: var(--secondary-text-color); }
  .history-view .history-export-note a { color: var(--history-bar); text-decoration: underline; }
  .history-view .history-column:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; border-radius: 4px; }
  /* The ring hugs the bar, not the empty track above it, and it has to be painted
     above the stacked segments: an inset shadow sits behind them and disappears. */
  .history-view .history-column[data-selected] .history-bar {
    position: relative; border-radius: 4px 4px 0 0; }
  .history-view .history-column[data-selected] .history-bar::after {
    content: ""; position: absolute; inset: 0;
    border: 2px solid var(--primary-text-color, currentColor);
    border-radius: 4px 4px 0 0; pointer-events: none; }
  .history-view .history-column[data-selected] > span { color: var(--primary-text-color); font-weight: 700; }
  .history-view .history-column > span { display: block; overflow: visible; white-space: nowrap; }
  /* Compact tile: numbers and a shape, nothing to click. */
  .history-view.history-compact { padding: 10px 12px 12px; }
  .history-view.history-compact .history-head { margin-bottom: 6px; align-items: baseline; }
  .history-view.history-compact .history-head h2 { font-size: .95rem; }
  .history-view.history-compact .hc-range { font-size: .72rem; color: var(--secondary-text-color); }
  .history-view.history-compact .history-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; padding: 0; }
  .history-view.history-compact .history-kpi { padding: 4px 8px 6px; }
  .history-view.history-compact .history-kpi small { font-size: .64rem; }
  .history-view.history-compact .history-kpi b { font-size: 1.02rem; }
  .history-view.history-compact figure { margin: 8px 0 0; }
  .history-view.history-compact .history-figure-head { margin-bottom: 4px; }
  .history-view.history-compact figcaption { font-size: .68rem; }
  .history-view.history-compact .history-track { height: 56px; }
  /* A day without a charge still belongs to the timeline: a faint stub instead of a
     hole, so seven days do not look like four and thirty not like a blank field. */
  .history-view .history-track { position: relative; }
  .history-view .history-column[data-idle] .history-track::before {
    content: ""; position: absolute; bottom: 3px; left: 28%; right: 28%; height: 2px;
    border-radius: 1px; background: var(--secondary-text-color); opacity: .35;
  }
  .history-view.history-compact .history-column { cursor: default; }
  .history-view.history-compact [data-export],
  .history-view.history-compact .history-export-note { display: none; }
  .history-view.history-compact .history-column > span { display: none; }
  .history-view.history-compact .history-chart { padding-bottom: 0; overflow-x: hidden; }
  .history-view .history-track { height: 130px; display: flex; align-items: flex-end; border-bottom: 1px solid var(--divider-color); border-radius: 4px 4px 0 0; overflow: hidden; }
  .history-view .history-column[data-current] span { color: var(--primary-text-color); font-weight: 600; }
  .history-view .history-bar { width: 100%; display: flex; flex-direction: column-reverse; }
  .history-view .history-grid { background: var(--history-bar); }
  .history-view .history-pv { background: var(--success-color, var(--accent-color)); }
  .history-view .history-total { background: var(--secondary-text-color); }
  /* One bar per period: the paid part sits at the bottom, the avoided part on top.
     The full height is what the charge would have cost without the own PV. */
  .history-view .history-stack { display: flex; flex-direction: column-reverse; width: 100%; height: 100%; border-radius: 3px 3px 0 0; overflow: hidden; }
  .history-view .history-stack > div { width: 100%; min-height: 0; }
  .history-view .history-bar > div { box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .18); }
  .history-view .history-slot { visibility: hidden; }
  .history-view .history-paid { background: var(--history-bar); }
  .history-view .history-avoided {
    background: repeating-linear-gradient(45deg, var(--success-color, var(--accent-color)) 0 2px, transparent 2px 4px);
    border: 1px solid var(--success-color, var(--accent-color)); border-bottom: 0;
  }
  .history-view .history-selection { min-height: 1.3em; margin-top: 8px; font-size: .8rem; color: var(--secondary-text-color); overflow-wrap: anywhere; }
  .history-view .history-selection b { color: var(--primary-text-color); font-weight: 600; font-variant-numeric: tabular-nums; }
  .history-view .history-list-wrap > summary {
    display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 6px 0;
    border-top: 1px solid var(--divider-color); font-size: .82rem; cursor: pointer;
  }
  .history-view .history-list-wrap > summary::marker { color: var(--secondary-text-color); }
  .history-view .history-list { max-height: 540px; overflow-y: auto; }
  .history-view details { border-top: 1px solid var(--divider-color); padding: 9px 0; }
  .history-view summary { cursor: pointer; font-size: .8rem; overflow-wrap: anywhere; }
  .history-view .history-row { display: inline-flex; flex-wrap: wrap; gap: 5px 12px; }
  .history-view dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 5px 10px; font-size: .78rem; }
  .history-view dt { color: var(--secondary-text-color); }
  .history-view dd { margin: 0; overflow-wrap: anywhere; }
  .history-view .history-flags { padding-left: 20px; font-size: .76rem; }
  .history-view .history-confirm { padding: 10px 0; font-size: .8rem; }
  .history-view .history-error { color: var(--error-color); }
  /* The card can be narrow in a wide dashboard, so measure the card, not the screen. */
  @container (max-width: 400px) {
    .history-view .history-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 10px; }
    .history-view .history-kpi:nth-child(3) { border-left: 0; padding-left: 0; }
    .history-view .history-kpi:nth-child(n+3) {
      border-top: 1px solid var(--divider-color); padding-top: 7px; margin-top: 2px;
    }
    .history-view .history-kpi { padding-right: 6px; }
    .history-view .history-track { height: 160px; }
    .history-view .history-kpi b { font-size: 1.28rem; }
    .history-view .history-metrics button { min-width: 48px; }
  }
`;

export class HistoryView {
  constructor(card, options = {}) {
    this.card = card;
    this.options = options;
    // A tile shows numbers and a shape, not a second full view: fewer elements, not
    // smaller type. Everything interactive stays in the full layout.
    this.compact = options.compact === true;
    this.period = options.period || "month";
    this.vehicle = options.vehicle || "";
    // "energy" shows kWh per month, "cost" shows paid and avoided money.
    this.metric = options.metric === "cost" ? "cost" : "energy";
    this.sessions = [];
    this.months = [];
    this.exporting = false;
    this.exportResult = null;
    this.exportError = "";
    this.exportExpired = false;
    this._expiryTimer = null;
    this.offset = 0;
    this.count = 0;
    this.revision = 0;
    this.closed = false;
    this.loading = false;
  }

  t(key) {
    const language = (this.card._hass?.locale?.language || this.card._hass?.language || "en").slice(0, 2);
    return (STRINGS[language] || STRINGS.en)[key] || this.card._t(key);
  }

  fmt(value, digits = 2) { return numeric(value) ? this.card._fmt(value, digits) : "–"; }
  money(value) { return numeric(value) ? `${this.fmt(value)} €` : "–"; }

  // Reuse the card's device selection, but do history discovery only while open.
  sources() {
    const { _hass: hass, _entities: entities, _config: config } = this.card;
    const registry = hass.entities || {};
    const anchor = registry[entities.session_energy] || registry[entities.grid_power];
    const entryOf = item => item?.config_entry_id || String(item?.unique_id || "").match(/^(.*)_(?:evse_session_energy|grid_power_total|history_(?:week|month|year|total))$/)?.[1] || null;
    const anchorEntry = entryOf(anchor);
    const entryId = config.entry_id || anchorEntry || null;
    const sensors = {};
    const found = [];
    for (const period of PERIODS) {
      const role = `history_${period}`;
      const mapped = config.entities?.[role];
      const candidates = Object.values(registry).filter(item => item.platform === "ems_home" &&
        item.entity_id?.startsWith("sensor.") &&
        (item.translation_key === role || String(item.unique_id || "").endsWith(`_${role}`)) &&
        (!entryId || !entryOf(item) || entryOf(item) === entryId) &&
        (!anchor?.device_id || item.device_id === anchor.device_id));
      const id = mapped || (candidates.length === 1 ? candidates[0].entity_id : null) ||
        (!anchor?.device_id && !entryId ? Object.keys(hass.states).find(id => id.startsWith("sensor.") && id.includes("ems_home") && id.endsWith(`_${role}`)) : null);
      sensors[period] = hass.states[id];
      if (id) found.push(id);
    }
    // A single device cannot be confused with another one. With several devices the
    // mapping is only trusted when it can be proven: an explicit anchor, period
    // sensors that all sit on one entry, or a complete explicit mapping plus entry.
    const devices = new Set(Object.values(registry)
      .filter(item => item.platform === "ems_home" && item.device_id)
      .map(item => item.device_id));
    sensors.singleDevice = devices.size <= 1;
    sensors.explicit = PERIODS.every(period => Boolean(config.entities?.[`history_${period}`]));
    const oneDevice = found.length > 0 && new Set(found.map(id => registry[id]?.device_id || null)).size === 1;
    const derivedEntry = oneDevice ? entryOf(registry[found[0]]) : null;
    sensors.entryId = entryId || derivedEntry || null;
    sensors.trusted = sensors.singleDevice ||
      Boolean(anchorEntry || derivedEntry || (sensors.explicit && sensors.entryId)) ||
      // Without an anchor, a complete mapping that spans one device is still provable.
      (sensors.explicit && oneDevice);
    return sensors;
  }

  open() {
    this.normal = this.card.shadowRoot.querySelector("ha-card > .wrap");
    if (this.normal) this.normal.hidden = true;
    this.panel = document.createElement("section");
    this.panel.className = "history-view";
    this.style = document.createElement("style");
    this.style.textContent = STYLES;
    this.card.shadowRoot.appendChild(this.style);
    (this.normal?.parentNode || this.card.shadowRoot.querySelector("ha-card")).appendChild(this.panel);
    this.panel.innerHTML = `
      <div class="history-head"><h2>${esc(this.t("history"))}</h2>
        <div class="history-periods" role="group" aria-label="${esc(this.t("history"))}">
          ${PERIODS.map(p => `<button data-period="${p}" aria-pressed="${p === this.period}">${esc(this.t(p))}</button>`).join("")}
        </div><button data-close aria-label="${esc(this.t("close"))}">×</button></div>

      <label class="history-filter" hidden><span></span> <select data-vehicle></select></label>
      <div class="history-kpis"></div><div class="history-note" data-kpi-note></div>
      <figure>
        <div class="history-figure-head"><figcaption></figcaption>
          ${this.options.showExport === false ? "" : `<button data-export aria-label="${esc(this.t("export_csv"))}" title="${esc(this.t("export_csv"))}"><svg viewBox="0 0 24 24" width="17" height="17"
            aria-hidden="true"><path d="M12 3v10m0 0 4-4m-4 4-4-4M5 19h14" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><span aria-hidden="true">CSV</span></button>`}
          <div class="history-metrics" role="group" aria-label="${esc(this.t("chart_unit"))}">
            <button data-metric="energy" aria-pressed="${this.metric === "energy"}" aria-label="${esc(this.t("unit_energy"))}">kWh</button>
            <button data-metric="cost" aria-pressed="${this.metric === "cost"}" aria-label="${esc(this.t("unit_cost"))}">€</button>
          </div></div>
        <div class="history-chart"></div>
        <div class="history-step" data-step hidden>
          <button data-dir="-1" aria-label="${esc(this.t("previous_day"))}">‹</button>
          <span data-step-label></span>
          <button data-dir="1" aria-label="${esc(this.t("next_day"))}">›</button>
        </div>
        <div class="history-legend"></div>
        <p class="history-export-note" data-export-note role="status" hidden></p>
        <div class="history-selection" data-selection aria-live="polite"></div>
        <div class="history-note" data-chart-note></div></figure>
      <p data-status role="status"></p><button data-retry hidden></button>
      <details class="history-list-wrap" data-list-wrap><summary data-list-summary></summary>
        <div class="history-list"></div></details><button data-more hidden></button>`;
    this.panel.querySelector("[data-list-wrap]")?.addEventListener("toggle", event => {
      if (event.target.open) this.renderList();
    });
    const exportButton = this.panel.querySelector("[data-export]");
    if (exportButton) exportButton.onclick = () => this.exportCsv();
    const close = this.panel.querySelector("[data-close]");
    close.onclick = () => this.close();
    close.hidden = Boolean(this.options.standalone);
    if (this.options.chartOnly) this.panel.querySelector(".history-filter").remove();
    // The session list is an advanced view, not part of the first screen.
    if (this.options.showSessions !== true) {
      this.panel.querySelector("[data-list-wrap]")?.remove();
      this.panel.querySelector("[data-more]")?.remove();
    }
    this.panel.querySelectorAll("[data-period]").forEach(button => {
      button.onclick = () => { this.period = button.dataset.period; this.update(false); this.load(); };
    });
    this.panel.querySelectorAll("[data-metric]").forEach(button => {
      button.onclick = () => {
        if (this.metric === button.dataset.metric) return;
        this.metric = button.dataset.metric;
        this.update(false);
      };
    });
    const vehicle = this.panel.querySelector("[data-vehicle]");
    if (vehicle) vehicle.onchange = event => {
      this.vehicle = event.target.value;
      this.update(false);
      this.load();
    };
    const chart = this.panel.querySelector(".history-chart");
    if (!this.compact) {
    chart.addEventListener("pointerdown", event => {
      this.dragStart = {x: event.clientX, y: event.clientY};
    }, {passive: true});
    chart.addEventListener("pointercancel", () => { this.dragStart = null; }, {passive: true});
    // A tap selects a bucket; a drag scrolls the chart and must not select.
    chart.addEventListener("click", event => {
      const column = event.target.closest?.(".history-column");
      if (!column) return;
      const dx = this.dragStart ? event.clientX - this.dragStart.x : 0;
      const dy = this.dragStart ? event.clientY - this.dragStart.y : 0;
      this.dragStart = null;
      // A scroll gesture moves in either direction; only a still finger selects.
      if (Math.hypot(dx, dy) > 8) return;
      this.pick(Number(column.dataset.index));
    });
    chart.addEventListener("keydown", event => {
      const column = event.target.closest?.(".history-column");
      if (!column || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      this.pick(Number(column.dataset.index));
    });
    this.panel.querySelectorAll("[data-dir]").forEach(button => {
      button.onclick = () => this.step(Number(button.dataset.dir));
    });
    const more = this.panel.querySelector("[data-more]");
    if (more) more.onclick = () => this.load(true);
    }
    this.panel.querySelector("[data-retry]").onclick = () => this.load(this.offset > 0 && this.sessions.length > 0);
    if (this.compact) this.reduce();
    this.update(false);
    this.load();
    if (typeof ResizeObserver === "function") {
      this.resizeObserver = new ResizeObserver(() => this.scrollToNewest());
      this.resizeObserver.observe(this.panel);
    }
    if (!this.options.standalone) close.focus();
  }

  reduce() {
    // Turn the full view into a tile: no tabs, no arrows, no selection, no list.
    this.panel.classList.add("history-compact");
    for (const selector of [
      ".history-periods", ".history-filter", "[data-close]", ".history-metrics",
      "[data-step]", "[data-chart-note]", "[data-selection]", ".history-legend",
      "[data-list-wrap]", "[data-more]", "[data-kpi-note]",
    ]) {
      this.panel.querySelectorAll(selector).forEach(node => node.remove());
    }
    const head = this.panel.querySelector(".history-head");
    const range = document.createElement("span");
    range.className = "hc-range";
    head?.appendChild(range);
    const chart = this.panel.querySelector(".history-chart");
    if (chart) {
      chart.setAttribute("role", "img");
      // Not a control any more: no tab stops, no fake buttons.
      chart.removeAttribute("aria-label");
    }
  }

  compactRange(attrs) {
    // "Woche · 17.–23.11." is the one line of orientation the tile keeps.
    const label = this.t(this.period);
    const start = attrs.period_start ? new Date(attrs.period_start) : null;
    const end = attrs.period_end ? new Date(attrs.period_end) : null;
    const locale = this.card._hass?.locale?.language || "en";
    if (!start || Number.isNaN(start.getTime())) return label;
    const day = date => date.toLocaleDateString(locale, {day: "numeric", month: "numeric"});
    // period_end is exclusive: step one millisecond back, not a day, or a DST change
    // would drop the last day (23.–29.03. would read 23.–28.03.).
    const last = end && !Number.isNaN(end.getTime()) ? new Date(end.getTime() - 1) : null;
    return last ? `${label} · ${day(start)}–${day(last)}` : label;
  }

  close() {
    this.closed = true;
    ++this.revision;
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.panel?.remove();
    this.style?.remove();
    if (this.normal) this.normal.hidden = false;
    this.card._history = null;
    if (this.card.isConnected) {
      this.card.hass = this.card._hass;
      this.card.shadowRoot.querySelector("[data-history]")?.focus();
    }
  }

  update(refresh = true) {
    if (this.closed || !this.panel) return;
    this.source = this.sources();
    this.panel.dataset.dark = this.card._hass?.themes?.darkMode ? "1" : "0";
    const sensor = this.source[this.period];
    const attrs = sensor?.attributes || {};
    this.loadError = Boolean(attrs.load_error);
    this.unavailable = sensor?.state === "unavailable" || sensor?.state === "unknown";
    // The chart covers every month, so a change in any period sensor must invalidate
    // the view — not only a change in the currently selected KPI period.
    const sourceSignature = JSON.stringify([
      this.source.entryId, this.period, this.vehicle,
      PERIODS.map(period => [this.source[period]?.state, this.source[period]?.attributes]),
    ]);
    const changed = this.sourceSignature !== undefined && sourceSignature !== this.sourceSignature;
    this.sourceSignature = sourceSignature;
    const vehicles = attrs.by_vehicle || {};
    const select = this.panel.querySelector("[data-vehicle]");
    // Preserve an active filter even when its vehicle has no charges in this period.
    const names = [...new Set([...Object.keys(vehicles), ...(this.vehicle ? [this.vehicle] : [])])];
    const signature = JSON.stringify([names, this.t("all")]);
    if (select && this.vehicleSignature !== signature) {
      this.vehicleSignature = signature;
      select.innerHTML = `<option value="">${esc(this.t("all"))}</option>` + names.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    }
    if (select) {
      select.value = this.vehicle;
      select.parentNode.hidden = names.length === 0;
      select.previousElementSibling.textContent = this.t("vehicle");
    }
    const values = this.vehicle ? (vehicles[this.vehicle] || {sessions: 0, energy_kwh: 0}) : {
      ...attrs, energy_kwh: Number.parseFloat(sensor?.state),
    };
    const average = this.vehicle ? (values.sessions ? values.energy_kwh / values.sessions : 0) : attrs.avg_kwh;
    // Units live in the label, so the four values stay one line and the average
    // becomes a shared footnote instead of stretching a single tile.
    const kpis = this.compact
      ? (this.metric === "cost"
        ? [["cost", this.t("kpi_cost"), this.money(values.cost), ""],
           ["saved", this.t("kpi_saved"), this.money(values.saved), ""]]
        : [["energy", this.t("kpi_energy"), this.fmt(values.energy_kwh, 1), ""],
           ["sessions", this.t("sessions"), this.fmt(values.sessions, 0), ""]])
      : [
        ["sessions", this.t("sessions"), this.fmt(values.sessions, 0), ""],
        ["energy", this.t("kpi_energy"), this.fmt(values.energy_kwh, 1), ""],
        ["cost", this.t("kpi_cost"), this.money(values.cost), ""],
        ["saved", this.t("kpi_saved"), this.money(values.saved), ""],
      ];
    const html = kpis.map(([key, label, value, sub]) => `<div class="history-kpi" data-kpi="${key}"><small>${esc(label)}</small><b>${esc(this.loadError || this.unavailable ? "–" : value)}</b><small>${esc(this.loadError || this.unavailable ? "" : sub)}</small></div>`).join("");
    const tiles = this.panel.querySelector(".history-kpis");
    if (tiles.innerHTML !== html) tiles.innerHTML = html;
    const average_note = values.sessions
      ? this.t("average").replace("{value}", this.fmt(average, 1)) : "";
    const partial_note = this.vehicle ? this.t("vehicle_saved") :
      numeric(attrs.priced_sessions) && attrs.priced_sessions < attrs.sessions ? this.t("partial") : "";
    const note = this.panel.querySelector("[data-kpi-note]");
    if (note) note.textContent = [average_note, partial_note].filter(Boolean).join(" · ");
    this.panel.querySelector("h2").textContent = this.options.title ?? this.t(this.options.chartOnly ? "analysis" : "history");
    this.panel.querySelector("[data-close]")?.setAttribute("aria-label", this.t("close"));
    if (this.compact) {
      const range = this.panel.querySelector(".hc-range");
      if (range) range.textContent = this.compactRange(attrs);
      const chart = this.panel.querySelector(".history-chart");
      if (chart) {
        chart.setAttribute("aria-label", (this.metric === "cost"
          ? this.t("compact_summary")
            .replace("{period}", this.t(this.period))
            .replace("{cost}", this.money(values.cost))
            .replace("{saved}", this.money(values.saved))
          : this.t("compact_summary_energy")
            .replace("{period}", this.t(this.period))
            .replace("{energy}", this.fmt(values.energy_kwh, 1))
            .replace("{sessions}", this.fmt(values.sessions, 0))));
      }
    }
    this.panel.querySelectorAll("[data-period]").forEach(button => {
      button.textContent = this.t(button.dataset.period);
      button.setAttribute("aria-pressed", String(button.dataset.period === this.period));
    });
    this.panel.querySelectorAll("[data-metric]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.metric === this.metric));
    });
    const more = this.panel.querySelector("[data-more]");
    if (more) more.textContent = this.t("more");
    this.panel.querySelector("[data-retry]").textContent = this.t("retry");
    this.renderChart();
    this.status();
    if (refresh && changed && !this.deleting) this.load();
  }

  exportRange() {
    // The chart draws a rolling window (the service buckets the last 7 days, 30 days or
    // 12 months), so the file must use the same window or the numbers would not match.
    const now = new Date();
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    if (this.period === "week") {
      return {start: new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6), end: tomorrow};
    }
    if (this.period === "month") {
      return {start: new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29), end: tomorrow};
    }
    if (this.period === "total") return null;  // everything, archive included
    const count = Number(this.options.months) || 12;
    return {start: new Date(now.getFullYear(), now.getMonth() - (count - 1), 1), end: tomorrow};
  }

  rangeLabel(range) {
    if (!range) return this.t("total");
    const locale = this.card._hass?.locale?.language || "en";
    const day = date => date.toLocaleDateString(locale, {day: "numeric", month: "numeric"});
    const last = new Date(range.end.getFullYear(), range.end.getMonth(), range.end.getDate() - 1);
    return `${day(range.start)}–${day(last)}`;
  }

  scheduleExpiry(expiresAt) {
    if (this._expiryTimer) clearTimeout(this._expiryTimer);
    const ms = expiresAt ? new Date(expiresAt).getTime() - Date.now() : 0;
    if (!(ms > 0)) return;
    this._expiryTimer = setTimeout(() => {
      this.exportResult = null;
      this.exportExpired = true;
      this.renderExport();
    }, Math.min(ms, 2147483647));
  }

  async exportCsv() {
    // The entity button runs on the server, so it cannot start a download. Here the
    // click is ours: ask for a signed link and hand the browser an anchor.
    const button = this.panel.querySelector("[data-export]");
    if (this.exporting || !button) return;
    const range = this.exportRange();
    const data = {format: "csv"};
    if (range) { data.start = range.start.toISOString(); data.end = range.end.toISOString(); }
    if (this.source.entryId) data.entry_id = this.source.entryId;
    const token = (this.exportToken = (this.exportToken || 0) + 1);
    this.exporting = true;
    this.exportError = "";
    this.exportExpired = false;
    this.renderExport();
    try {
      const answer = await this.card._hass.callService(
        "ems_home", "export_history", data, undefined, false, true);
      const result = answer?.response ?? answer;
      if (!result?.url) throw new Error(this.t("export_failed"));
      // The download belongs to the click, so it always starts; the note only stays if
      // the period did not move on while the file was being written.
      this.triggerDownload(result.url);
      if (this.exportToken !== token) return;
      this.exportResult = {...result, range: this.rangeLabel(range)};
      this.scheduleExpiry(result.expires_at);
    } catch (error) {
      if (this.exportToken !== token) return;
      this.exportError = String(error?.message || error);
    } finally {
      if (this.exportToken === token) {
        this.exporting = false;
        this.renderExport();
      }
    }
  }

  triggerDownload(url) {
    // Same origin and a signed path: an anchor with download saves the file without
    // leaving the dashboard and without a popup blocker guessing.
    const link = document.createElement("a");
    link.href = url;
    link.download = "ems-home-history.csv";
    link.rel = "noopener";
    link.hidden = true;
    (this.panel || document.body).appendChild(link);
    link.click();
    link.remove();
  }

  renderExport() {
    const button = this.panel.querySelector("[data-export]");
    const note = this.panel.querySelector("[data-export-note]");
    if (!note) return;
    if (!button) { note.hidden = true; note.textContent = ""; return; }
    button.disabled = this.exporting;
    button.setAttribute("aria-busy", this.exporting ? "true" : "false");
    if (this.exporting) {
      note.textContent = this.t("export_running");
      note.hidden = false;
      return;
    }
    if (this.exportError) {
      note.textContent = `${this.t("export_failed")} ${this.exportError}`;
      note.hidden = false;
      return;
    }
    const result = this.exportResult;
    if (!result && this.exportExpired) {
      note.textContent = this.t("export_expired");
      note.hidden = false;
      return;
    }
    if (!result) {
      note.hidden = true;
      note.textContent = "";
      return;
    }
    let until = "";
    if (result.expires_at) {
      const locale = this.card._hass?.locale?.language || "en";
      until = new Date(result.expires_at).toLocaleTimeString(locale, {
        hour: "2-digit", minute: "2-digit",
      });
    }
    const text = this.t("export_ready")
      .replace("{rows}", String(result.rows ?? 0))
      .replace("{range}", result.range || "")
      .replace("{until}", until);
    const link = document.createElement("a");
    link.href = result.url;
    link.download = "ems-home-history.csv";
    link.rel = "noopener";
    link.textContent = this.t("export_link");
    note.textContent = `${text} `;
    note.appendChild(link);
    note.hidden = false;
  }

  status() {
    const status = this.panel.querySelector("[data-status]");
    status.textContent = this.loadError ? this.t("load_error") : this.unavailable ? this.t("unavailable_history") : this.error ? this.t(this.error) :
      this.loading ? this.t("loading") : this.sessions.length === 0 &&
        !(this.options.chartOnly && this.months.some(month => month.sessions > 0)) ? this.t("empty") : "";
    status.classList.toggle("history-error", this.loadError || this.unavailable || Boolean(this.error));
    this.panel.querySelector("[data-retry]").hidden = !this.error || this.loadError;
    const more = this.panel.querySelector("[data-more]");
    if (more) {
      more.hidden = this.sessions.length < 20 || this.offset >= this.count || this.loadError || this.unavailable;
      more.disabled = this.loading || this.deleting;
    }
  }

  async service(service, data) {
    // HA's response-only services require return_response over the WebSocket API.
    const result = await this.card._hass.callWS({
      type: "call_service", domain: "ems_home", service, service_data: data, return_response: true,
    });
    return result?.response;
  }

  async load(append = false) {
    if (this.closed || (append && (this.loading || this.deleting))) return;
    const revision = ++this.revision;
    this.loading = true;
    this.error = null;
    if (!append) {
      this.sessions = [];
      this.offset = 0;
      this.count = 0;
      this.exportResult = null;
      this.exportError = "";
      this.exportExpired = false;
      if (this._expiryTimer) { clearTimeout(this._expiryTimer); this._expiryTimer = null; }
      this.renderExport();
      this.renderList();
    }
    this.status();
    if (this.loadError || this.unavailable) { this.loading = false; this.status(); return; }
    const sensor = this.source[this.period];
    const attrs = sensor?.attributes || {};
    // The chart card has no list unless it was asked for; asking for one row it never
    // shows would leave the "load more" button unable to appear.
    const wantsList = !this.options.chartOnly || this.options.showSessions === true;
    const data = {limit: wantsList ? 20 : 1, offset: this.offset};
    if (this.options.months && this.options.months !== 12) data.months = this.options.months;
    // A week or a month is unreadable as twelve monthly bars: show one bar per day.
    const dayView = this.period === "week" || this.period === "month";
    this.resolution = dayView ? "day" : "month";
    this.windowDays = this.period === "week" ? 7 : 30;
    if (dayView) { data.resolution = "day"; data.days = this.windowDays; }
    if (this.source.entryId) data.entry_id = this.source.entryId;
    // Missing period sensors must not silently show another period's list, and with
    // several devices an unprovable mapping must not mix two histories.
    if (!this.source.trusted || !sensor ||
        (this.period !== "total" && (!attrs.period_start || !attrs.period_end))) {
      this.error = "target_error";
      this.loading = false;
      this.status();
      return;
    }
    if (this.period !== "total") { data.start = attrs.period_start; data.end = attrs.period_end; }
    if (this.vehicle) data.vehicle = this.vehicle;
    try {
      const response = await this.service("get_history", data);
      if (this.closed || revision !== this.revision) return;
      if (!Array.isArray(response?.sessions) || !Array.isArray(response?.months) || !numeric(response.count)) throw new Error("Invalid history response");
      this.sessions = append ? [...this.sessions, ...response.sessions] : response.sessions;
      this.offset = data.offset + response.sessions.length;
      this.count = response.sessions.length ? response.count : this.offset;
      this.months = response.months;
      this.buckets = Array.isArray(response.buckets) ? response.buckets : response.months;
      this.renderChart();
      this.renderList();
    } catch {
      if (!this.closed && revision === this.revision) this.error = "error";
    } finally {
      if (!this.closed && revision === this.revision) { this.loading = false; this.status(); }
    }
  }

  renderChart() {
    // "energy" splits the bar into grid and PV, where detailed months allow it.
    // "cost" draws two separate bars per month — paid and avoided — because a saving
    // is not an expense and the stored cost already contains the PV tariff.
    const money = this.metric === "cost";
    const daily = this.resolution === "day";
    const all = this.buckets || this.months;
    const months = daily ? all : (this.options.months ? all.slice(-this.options.months) : all);
    // Paid and avoided money are two separate facts on one shared axis: `cost`
    // already contains the PV tariff, so they must never be stacked or summed.
    const paid = month => (numeric(month.cost) ? Math.max(0, month.cost) : 0);
    const avoided = month => (numeric(month.saved) ? Math.max(0, month.saved) : 0);
    // One bar per period: paid at the bottom, the avoided part on top, so the full
    // height is what the charge would have cost without the own PV.
    const value = month => (money ? paid(month) + avoided(month) : Math.max(0, month.energy_kwh || 0));
    const max = Math.max(0, ...months.map(value));
    const now = new Date();
    const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const keyOf = month => month.key || month.month || month.day || "";
    const currentKey = daily
      ? `${current}-${String(now.getDate()).padStart(2, "0")}`
      : current;
    const html = months.map((month, index) => {
      const total = value(month);
      const height = max ? total / max * 100 : 0;
      const split = numeric(month.energy_grid_kwh) && numeric(month.energy_pv_kwh);
      let label = `${keyOf(month)}: ${this.fmt(total, 1)} ${money ? "€" : "kWh"}`;
      let bars;
      if (money) {
        const costs = paid(month), savings = avoided(month);
        // A missing amount is unknown, never zero: it draws no bar and says so.
        const idle = Number(month.sessions) === 0;
        const knownCost = numeric(month.cost) || idle, knownSaved = numeric(month.saved) || idle;
        // An idle day has a real 0 €, but no bar to draw.
        const spent = !idle && knownCost ? costs : 0;
        const avoidedPart = !idle && knownSaved ? savings : 0;
        const sum = spent + avoidedPart;
        label = `${keyOf(month)} · ${this.t("paid")}: ${knownCost ? this.money(costs) : this.t("unknown")} · ${
          this.t("avoided")}: ${knownSaved ? this.money(savings) : this.t("unknown")}` +
          (knownCost && knownSaved ? ` · ${this.t("stack_total")}: ${this.money(costs + savings)}` : "") +
          (idle ? ` · ${this.t("no_sessions")}` : "");
        // The two segments fill their own bar: their shares add up to 100 %.
        bars = sum > 0
          ? `<div class="history-stack">${
            spent > 0 ? `<div class="history-paid" style="flex:0 0 ${(spent / sum * 100).toFixed(2)}%"></div>` : ""
          }<div class="history-avoided" style="flex:1 1 auto"></div></div>`
          : "";
      } else if (split) {
        label += ` · ${this.t("grid")}: ${this.fmt(month.energy_grid_kwh, 1)} · ${this.t("pv")}: ${this.fmt(month.energy_pv_kwh, 1)}`;
        bars = `<div class="history-grid" style="height:${total ? month.energy_grid_kwh / total * 100 : 0}%"></div><div class="history-pv" style="height:${total ? month.energy_pv_kwh / total * 100 : 0}%"></div>`;
      } else {
        bars = `<div class="history-total" style="height:100%"></div>`;
      }
      const date = new Date(`${keyOf(month).slice(0, 10)}T12:00:00`);
      const locale = this.card._hass?.locale?.language || "en";
      // Seven days fit seven labels; thirty do not, so those get every fifth and the
      // newest. Three labels in a week read as "the rest has no data".
      const every = months.length <= 10 ? 1 : 5;
      const tick = Number.isNaN(date.getTime()) ? keyOf(month)
        : daily ? (index % every === 0 || index === months.length - 1 ? String(date.getDate()) : "")
        : date.toLocaleDateString(locale, {month: "short"});
      const pressed = index === this.selectedIndex;
      const controls = this.compact ? "" : ` role="button" tabindex="0" aria-pressed="${pressed}"${pressed ? " data-selected" : ""} aria-label="${esc(label)}"`;
      // An empty day is a fact, not a gap: mark it in every layout, not only the tile.
      const idleAttr = Number(month.sessions || 0) === 0 ? " data-idle" : "";
      return `<div class="history-column"${controls} data-index="${index}" title="${esc(label)}"${keyOf(month) === currentKey ? " data-current" : ""}${idleAttr}>
        <div class="history-track"><div class="history-bar" style="height:${height}%">${bars}</div></div><span>${esc(tick)}</span></div>`;
    }).join("");
    this.selectionLabels = months.map(month => this.describeBucket(month));
    const chart = this.panel.querySelector(".history-chart");
    // Rebuild only when the data changed. Comparing innerHTML rebuilt the columns on
    // every selection change (the toggled attributes differ from the template) and
    // dropped keyboard focus with them.
    const signature = JSON.stringify([this.metric, this.resolution, months.map(month => [
      keyOf(month), value(month), month.sessions, month.energy_grid_kwh,
      month.energy_pv_kwh, month.cost, month.saved,
    ])]);
    const focused = chart.querySelector(".history-column:focus")?.dataset.index;
    if (this.chartSignature !== signature) {
      this.chartSignature = signature;
      chart.innerHTML = html;
      if (focused !== undefined) {
        chart.querySelector(`.history-column[data-index="${focused}"]`)?.focus();
      }
    }
    chart.dataset.money = money ? "1" : "0";
    chart.dataset.daily = daily ? "1" : "0";
    if (!Number.isInteger(this.selectedIndex) || this.selectedIndex >= months.length) {
      this.selectedIndex = months.length - 1;
    }
    this.chartMonths = months;
    this.selectIndex(this.selectedIndex);
    // Two bars per month need a readable minimum; below that the chart scrolls.
    // A day is narrow too: without a minimum its two-digit label is cut off.
    // A tile fits all bars: 30 days at 320 px must not need a scrollbar.
    const minimum = this.compact ? 3 : (money ? 30 : (daily ? 12 : 0));
    chart.style.gridTemplateColumns = `repeat(${Math.max(1, months.length)}, minmax(${minimum}px, 1fr))`;
    const span = daily ? this.windowDays : (this.options.months || 12);
    const caption = (daily
      ? this.t(money ? "chart_cost_days" : "chart_days").replace("{days}", span)
      : this.t(money ? "chart_cost" : "chart_months").replace("{months}", span));
    this.panel.querySelector("figcaption").textContent =
      this.vehicle ? `${caption} · ${this.t("all_vehicles")}` : caption;
    const legend = this.panel.querySelector(".history-legend");
    const items = money
      ? [[this.t("paid"), "paid"], [this.t("avoided"), "avoided"]]
      : (months.some(month => numeric(month.energy_grid_kwh)) ? [[this.t("grid"), "grid"], [this.t("pv"), "pv"]] : []);
    if (legend) legend.innerHTML = items.map(([name, key]) => `<span><i class="${key}"></i>${esc(name)}</span>`).join("") +
      (money ? `<span class="history-stack-note">${esc(this.t("stack_note"))}</span>` : "");
    this.scrollToNewest();
    const anyMoney = months.some(month => numeric(month.cost) || numeric(month.saved));
    // A day without a charge has no cost either; that is not missing data. Only warn
    // when a day charged and still has no money.
    const chargedWithoutCost = months.some(
      month => Number(month.sessions || 0) > 0 && !numeric(month.cost),
    );
    const anySessions = months.some(month => Number(month.sessions || 0) > 0);
    const chartNote = this.panel.querySelector("[data-chart-note]");
    if (chartNote) chartNote.textContent = money
      ? (!anySessions ? ""
        : !anyMoney ? this.t("no_money")
        : chargedWithoutCost
          ? this.t(daily ? "cost_partial_days" : "cost_partial")
          : "")
      : (all.every(month => !numeric(month.energy_grid_kwh))
        ? this.t("total_only")
        : all.some(month => !numeric(month.energy_grid_kwh)) ? this.t("split_partial") : "");
  }

  step(direction) {
    const count = this.selectionLabels?.length || 0;
    if (count === 0) return;
    const from = Number.isInteger(this.selectedIndex) ? this.selectedIndex : count - 1;
    const next = Math.min(count - 1, Math.max(0, from + direction));
    this.selectIndex(next);
    this.panel.querySelector(".history-column[data-selected]")
      ?.scrollIntoView({block: "nearest", inline: "nearest"});
  }

  pick(index) {
    this.selectIndex(this.selectedIndex === index ? null : index);
  }

  refreshStep() {
    const box = this.panel?.querySelector("[data-step]");
    if (!box) return;
    const months = this.chartMonths || [];
    const daily = this.resolution === "day";
    box.hidden = !daily || months.length === 0;
    const label = this.panel.querySelector("[data-step-label]");
    const selected = months[this.selectedIndex];
    if (label) label.textContent = selected ? this.bucketTitle(selected) : "";
    this.panel.querySelectorAll("[data-dir]").forEach(button => {
      button.disabled = !daily || months.length === 0 ||
        (Number(button.dataset.dir) < 0 ? this.selectedIndex <= 0 : this.selectedIndex >= months.length - 1);
    });
  }

  selectIndex(index) {
    if (this.compact) return;  // a tile has nothing to select and nothing to announce

    const chart = this.panel?.querySelector(".history-chart");
    if (!chart) return;
    this.selectedIndex = Number.isInteger(index) && index >= 0 ? index : null;
    chart.querySelectorAll(".history-column").forEach(column => {
      const on = this.selectedIndex !== null && Number(column.dataset.index) === this.selectedIndex;
      if (on) column.setAttribute("data-selected", "");
      else column.removeAttribute("data-selected");
      column.setAttribute("aria-pressed", String(on));
    });
    const box = this.panel.querySelector("[data-selection]");
    if (!box) return;
    // The newest bucket is preselected, so a phone user reads exact values without
    // hunting for a hover that does not exist on touch.
    box.innerHTML = this.selectedIndex === null
      ? esc(this.t("selection_hint"))
      : (this.selectionLabels?.[this.selectedIndex] || esc(this.t("selection_hint")));
    this.refreshStep();
  }

  bucketTitle(month) {
    const key = month.key || month.month || month.day || "";
    const date = new Date(`${String(key).slice(0, 10)}T12:00:00`);
    const locale = this.card._hass?.locale?.language || this.card._hass?.language || "en";
    if (Number.isNaN(date.getTime())) return String(key);
    return this.resolution === "day"
      ? date.toLocaleDateString(locale, {weekday: "short", day: "2-digit", month: "2-digit"})
      : date.toLocaleDateString(locale, {month: "long", year: "numeric"});
  }

  describeBucket(month) {
    const key = month.key || month.month || month.day || "";
    const date = new Date(`${String(key).slice(0, 10)}T12:00:00`);
    const locale = this.card._hass?.locale?.language || this.card._hass?.language || "en";
    const when = Number.isNaN(date.getTime()) ? key : date.toLocaleDateString(locale,
      this.resolution === "day"
        ? {weekday: "short", day: "2-digit", month: "2-digit"}
        : {month: "long", year: "numeric"});
    if (Number(month.sessions) === 0) return `${esc(when)} · ${esc(this.t("no_sessions"))}`;
    const parts = [];
    if (this.metric === "cost") {
      const knownCost = numeric(month.cost), knownSaved = numeric(month.saved);
      parts.push(`${esc(this.t("paid"))} <b>${esc(knownCost ? this.money(month.cost) : this.t("unknown"))}</b>`);
      parts.push(`${esc(this.t("avoided"))} <b>${esc(knownSaved ? this.money(month.saved) : this.t("unknown"))}</b>`);
      if (knownCost && knownSaved) {
        parts.push(`${esc(this.t("stack_total"))} <b>${esc(this.money(month.cost + month.saved))}</b>`);
      }
    } else {
      parts.push(`<b>${esc(this.fmt(month.energy_kwh, 1))} kWh</b>`);
      if (numeric(month.energy_grid_kwh) && numeric(month.energy_pv_kwh)) {
        parts.push(`${esc(this.t("grid"))} ${esc(this.fmt(month.energy_grid_kwh, 1))} kWh`);
        parts.push(`${esc(this.t("pv"))} ${esc(this.fmt(month.energy_pv_kwh, 1))} kWh`);
      }
    }
    return `<span>${esc(when)}</span> · ${parts.join(" · ")}`;
  }

  scrollToNewest() {
    const chart = this.panel?.querySelector(".history-chart");
    if (chart && chart.scrollWidth > chart.clientWidth + 1) {
      chart.scrollLeft = chart.scrollWidth;
    }
  }

  renderList() {
    const list = this.panel.querySelector(".history-list");
    const wrap = this.panel.querySelector("[data-list-wrap]");
    const summary = wrap?.querySelector("[data-list-summary]");
    if (summary) {
      const total = Math.max(this.count || 0, this.sessions.length);
      summary.textContent = this.t("sessions_title").replace("{count}", String(total));
    }
    if (!list) return;
    if (wrap) wrap.hidden = this.sessions.length === 0;
    // A closed disclosure needs no rows: build them when it opens.
    if (wrap && !wrap.open) { list.innerHTML = ""; return; }
    const opened = new Set([...list.querySelectorAll("details[open]")].map(node => node.dataset.id));
    list.innerHTML = this.sessions.map((session, index) => {
      const duration = numeric(session.duration_s) ? `${Math.floor(session.duration_s / 3600)}:${String(Math.floor(session.duration_s / 60) % 60).padStart(2, "0")}` : "–";
      const mode = value => this.card._modeLabel(value);
      const fields = [
        [this.t("start"), this.card._whenLabel(session.started_at) || "–"],
        [this.t("end"), this.card._whenLabel(session.ended_at) || "–"],
        [this.t("grid"), `${this.fmt(session.grid_wh / 1000, 1)} kWh`],
        [this.t("pv"), `${this.fmt((session.energy_wh - session.grid_wh) / 1000, 1)} kWh`],
        [this.t("prices"), `${this.t("grid")}: ${this.money(session.grid_price)} / kWh · ${this.t("pv")}: ${this.money(session.pv_price)} / kWh`],
        [this.t("mode"), `${mode(session.mode_start)} → ${mode(session.mode_end)}`],
        [this.t("reason"), ["unplugged", "idle"].includes(session.end_reason) ? this.t(session.end_reason) : "–"],
      ];
      const flags = (session.flags || []).filter(flag => ["gap", "restarted", "mode_changed", "clock_suspect"].includes(flag));
      return `<details data-id="${esc(session.id)}" ${opened.has(String(session.id)) ? "open" : ""}>
        <summary><span class="history-row"><span>${esc(this.card._whenLabel(session.last_flow_at || session.ended_at) || "–")}</span>${session.vehicle ? `<span>${esc(session.vehicle)}</span>` : ""}<span>${esc(this.fmt(session.energy_wh / 1000, 1))} kWh</span><span>${esc(duration)} h</span><span>${esc(this.money(session.cost))}</span></span></summary>
        <dl>${fields.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join("")}</dl>
        <ul class="history-flags">${flags.map(flag => `<li>${esc(this.t(flag))}${flag === "gap" ? ` (${esc(this.fmt(session.gap_s, 0))} s)` : flag === "restarted" ? ` (${esc(this.fmt(session.restarts, 0))})` : ""}</li>`).join("")}</ul>
        ${session.estimated ? `<p class="history-note">${esc(this.t("estimated"))}</p>` : ""}
        <button data-delete="${index}" ${this.deleting ? "disabled" : ""}>${esc(this.t("remove"))}</button>
        <div class="history-confirm" hidden><p>${esc(this.t("confirm"))}</p><button data-confirm="${index}">${esc(this.t("confirm_remove"))}</button> <button data-cancel>${esc(this.t("cancel"))}</button></div>
      </details>`;
    }).join("");
    list.querySelectorAll("[data-delete]").forEach(button => {
      button.onclick = () => {
        button.hidden = true;
        button.nextElementSibling.hidden = false;
        button.nextElementSibling.querySelector("[data-cancel]").focus();
      };
    });
    list.querySelectorAll("[data-cancel]").forEach(button => {
      button.onclick = () => {
        const box = button.parentNode;
        box.hidden = true;
        box.previousElementSibling.hidden = false;
        box.previousElementSibling.focus();
      };
    });
    list.querySelectorAll("[data-confirm]").forEach(button => {
      button.onclick = () => this.remove(this.sessions[Number(button.dataset.confirm)]);
    });
  }

  async remove(session) {
    if (this.deleting || this.closed || this.loadError || this.unavailable) return;
    this.deleting = true;
    this.panel.querySelectorAll("[data-period], [data-vehicle], [data-confirm], [data-delete]").forEach(button => { button.disabled = true; });
    this.status();
    const revision = this.revision;
    const data = {session_id: session.id, confirm: true};
    if (this.source.entryId) data.entry_id = this.source.entryId;
    try {
      const response = await this.service("delete_session", data);
      if (!response?.deleted) throw new Error("Session not deleted");
      if (!this.closed) { this.update(false); await this.load(); }
    } catch {
      if (!this.closed && revision === this.revision) { this.error = "delete_error"; this.status(); }
    } finally {
      this.deleting = false;
      if (!this.closed) {
        this.panel.querySelectorAll("[data-period], [data-vehicle]").forEach(button => { button.disabled = false; });
        this.renderList(); this.status();
      }
    }
  }
}
