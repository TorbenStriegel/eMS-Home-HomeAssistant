/** Shared charging history view for the flow card and standalone widgets. */
export const STRINGS = {
  de: {
    history: "Verlauf", analysis: "Ladeauswertung", cost: "Kosten", saved: "gespart",
    grid: "Netz", pv: "PV", mode: "Modus",
    modes: {lock: "Gesperrt", grid: "Netz", pv: "PV", hybrid: "Hybrid"},
    chart_months: "kWh / Monat · letzte {months} Monate · alle Fahrzeuge",
    chart_cost: "Bezahlt und vermieden je Monat · letzte {months} Monate",
    chart_days: "kWh / Tag · letzte {days} Tage · alle Fahrzeuge",
    chart_cost_days: "Bezahlt und vermieden je Tag · letzte {days} Tage",
    paid: "bezahlt", avoided: "vermieden", unknown: "unbekannt",
    no_sessions: "keine Ladevorgänge",
    unit_energy: "Energie in kWh", unit_cost: "Bezahlt und vermieden in Euro",
    cost_partial: "Einzelne Monate enthalten keine Kostendaten.",
    cost_partial_days: "Einzelne Tage enthalten keine Kostendaten.",
    split_partial: "Einzelne Monate enthalten keine Netz/PV-Aufteilung.",
    no_money: "Keine gespeicherten Preisdaten in diesem Zeitraum.",
    history_description: "Ladehistorie mit Filtern, Details und Löschen.",
    chart_description: "Kennzahlen und monatliche Ladeenergie ohne Verlaufsliste.",
    week: "Woche", month: "Monat", year: "Jahr", total: "Gesamt", close: "Schließen",
    sessions: "Vorgänge", average: "Ø {value} kWh pro Vorgang", vehicle: "Fahrzeug", all: "Alle",
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
    chart_months: "kWh / month · last {months} months · all vehicles",
    chart_cost: "Paid and avoided per month · last {months} months",
    chart_days: "kWh / day · last {days} days · all vehicles",
    chart_cost_days: "Paid and avoided per day · last {days} days",
    paid: "paid", avoided: "avoided", unknown: "unknown",
    no_sessions: "no charging sessions",
    unit_energy: "Energy in kWh", unit_cost: "Paid and avoided in euro",
    cost_partial: "Some months carry no cost data.",
    cost_partial_days: "Some days carry no cost data.",
    split_partial: "Some months carry no grid/PV split.",
    no_money: "No stored price data in this period.",
    history_description: "Charging history with filters, details and deletion.",
    chart_description: "Key figures and monthly charging energy without a session list.",
    week: "Week", month: "Month", year: "Year", total: "Total", close: "Close",
    sessions: "Sessions", average: "Ø {value} kWh per session", vehicle: "Vehicle", all: "All",
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
  .history-view { padding: 16px; color: var(--primary-text-color); }
  .history-view [hidden] { display: none !important; }
  .history-view .history-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .history-view h2 { margin: 0 auto 0 0; font-size: 1rem; }
  .history-view button, .history-view select {
    font: inherit; font-size: .8rem; color: var(--primary-text-color);
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 7px; cursor: pointer;
  }
  .history-view button:disabled { opacity: .5; cursor: default; }
  .history-view button[aria-pressed="true"] { border-color: var(--primary-color); color: var(--primary-color); }
  .history-view .history-periods { display: flex; flex-wrap: wrap; gap: 4px; }
  .history-view .history-filter { display: block; margin-top: 12px; font-size: .8rem; }
  .history-view .history-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; margin: 12px 0; }
  .history-view .history-kpi { min-width: 0; padding: 8px; border-radius: 10px; background: var(--secondary-background-color); overflow-wrap: anywhere; }
  .history-view .history-kpi b { display: block; font-size: 1.05rem; }
  .history-view small, .history-view .history-note { font-size: .72rem; color: var(--secondary-text-color); }
  .history-view figure { margin: 14px 0; }
  .history-view .history-figure-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; margin-bottom: 8px; }
  .history-view figcaption { font-size: .8rem; flex: 1 1 auto; }
  .history-view .history-metrics { display: flex; gap: 4px; }
  .history-view .history-metrics button { padding: 4px 9px; font-size: .72rem; }
  .history-view .history-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; font-size: .72rem; color: var(--secondary-text-color); }
  .history-view .history-legend span { display: inline-flex; align-items: center; gap: 4px; }
  .history-view .history-legend i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
  .history-view .history-legend .grid, .history-view .history-legend .paid { background: var(--primary-color); }
  .history-view .history-legend .pv { background: var(--success-color, var(--accent-color)); }
  .history-view .history-legend .avoided { background: repeating-linear-gradient(45deg, var(--success-color, var(--accent-color)) 0 2px, transparent 2px 4px); border: 1px solid var(--success-color, var(--accent-color)); }
  .history-view .history-legend .total { background: var(--secondary-text-color); }
  .history-view .history-chart { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 3px; }
  .history-view .history-chart[data-money="1"] { gap: 4px; overflow-x: auto; padding-bottom: 2px; }
  .history-view .history-column { min-width: 0; text-align: center; font-size: .6rem; }
  .history-view .history-track { height: 90px; display: flex; align-items: flex-end; border-bottom: 1px solid var(--divider-color); border-radius: 4px 4px 0 0; overflow: hidden; }
  .history-view .history-column[data-current] span { color: var(--primary-text-color); font-weight: 600; }
  .history-view .history-bar { width: 100%; display: flex; flex-direction: column-reverse; }
  .history-view .history-grid { background: var(--primary-color); }
  .history-view .history-pv { background: var(--success-color, var(--accent-color)); }
  .history-view .history-total { background: var(--secondary-text-color); }
  .history-view .history-pair { display: flex; align-items: flex-end; gap: 2px; width: 100%; height: 100%; }
  .history-view .history-pair > div { flex: 1 1 0; min-width: 2px; border-radius: 3px 3px 0 0; }
  .history-view .history-slot { visibility: hidden; }
  .history-view .history-paid { background: var(--primary-color); }
  .history-view .history-avoided {
    background: repeating-linear-gradient(45deg, var(--success-color, var(--accent-color)) 0 2px, transparent 2px 4px);
    border: 1px solid var(--success-color, var(--accent-color)); border-bottom: 0;
  }
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
  @media (max-width: 420px) { .history-view .history-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
`;

export class HistoryView {
  constructor(card, options = {}) {
    this.card = card;
    this.options = options;
    this.period = options.period || "month";
    this.vehicle = options.vehicle || "";
    // "energy" shows kWh per month, "cost" shows paid and avoided money.
    this.metric = options.metric === "cost" ? "cost" : "energy";
    this.sessions = [];
    this.months = [];
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
          <div class="history-metrics" role="group" aria-label="${esc(this.t("chart"))}">
            <button data-metric="energy" aria-pressed="${this.metric === "energy"}" aria-label="${esc(this.t("unit_energy"))}">kWh</button>
            <button data-metric="cost" aria-pressed="${this.metric === "cost"}" aria-label="${esc(this.t("unit_cost"))}">€</button>
          </div></div>
        <div class="history-chart"></div><div class="history-legend"></div>
        <div class="history-note" data-chart-note></div></figure>
      <p data-status role="status"></p><button data-retry hidden></button>
      <div class="history-list"></div><button data-more hidden></button>`;
    const close = this.panel.querySelector("[data-close]");
    close.onclick = () => this.close();
    close.hidden = Boolean(this.options.standalone);
    if (this.options.chartOnly) {
      this.panel.querySelector(".history-filter").remove();
      this.panel.querySelector(".history-list").remove();
      this.panel.querySelector("[data-more]").remove();
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
    const more = this.panel.querySelector("[data-more]");
    if (more) more.onclick = () => this.load(true);
    this.panel.querySelector("[data-retry]").onclick = () => this.load(this.offset > 0 && this.sessions.length > 0);
    this.update(false);
    this.load();
    if (!this.options.standalone) close.focus();
  }

  close() {
    this.closed = true;
    ++this.revision;
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
    const kpis = [
      ["sessions", this.t("sessions"), this.fmt(values.sessions, 0), ""],
      ["energy", "kWh", this.fmt(values.energy_kwh, 1), this.t("average").replace("{value}", this.fmt(average, 1))],
      ["cost", this.t("cost"), this.money(values.cost), ""],
      ["saved", this.t("saved"), this.money(values.saved), ""],
    ];
    const html = kpis.map(([key, label, value, sub]) => `<div class="history-kpi" data-kpi="${key}"><small>${esc(label)}</small><b>${esc(this.loadError || this.unavailable ? "–" : value)}</b><small>${esc(this.loadError || this.unavailable ? "" : sub)}</small></div>`).join("");
    const tiles = this.panel.querySelector(".history-kpis");
    if (tiles.innerHTML !== html) tiles.innerHTML = html;
    this.panel.querySelector("[data-kpi-note]").textContent = this.vehicle ? this.t("vehicle_saved") :
      numeric(attrs.priced_sessions) && attrs.priced_sessions < attrs.sessions ? this.t("partial") : "";
    this.panel.querySelector("h2").textContent = this.options.title ?? this.t(this.options.chartOnly ? "analysis" : "history");
    this.panel.querySelector("[data-close]").setAttribute("aria-label", this.t("close"));
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
      this.renderList();
    }
    this.status();
    if (this.loadError || this.unavailable) { this.loading = false; this.status(); return; }
    const sensor = this.source[this.period];
    const attrs = sensor?.attributes || {};
    const data = {limit: this.options.chartOnly ? 1 : 20, offset: this.offset};
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
    const value = month => (money ? Math.max(paid(month), avoided(month)) : Math.max(0, month.energy_kwh || 0));
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
        // The bar height already encodes this month's maximum, so the two segments
        // must be scaled to that value — not to the chart maximum again.
        const top = Math.max(knownCost ? costs : 0, knownSaved ? savings : 0) || 1;
        label = `${keyOf(month)} · ${this.t("paid")}: ${knownCost ? this.money(costs) : this.t("unknown")} · ${
          this.t("avoided")}: ${knownSaved ? this.money(savings) : this.t("unknown")}` +
          (Number(month.sessions) === 0 ? ` · ${this.t("no_sessions")}` : "");
        // An idle day has a real 0 €, but no bar to draw.
        const drawCost = !idle && knownCost && costs > 0;
        const drawAvoided = !idle && knownSaved && savings > 0;
        bars = `<div class="history-pair">${
          drawCost ? `<div class="history-paid" style="height:${costs / top * 100}%"></div>`
            : `<div class="history-slot"></div>`}${
          drawAvoided ? `<div class="history-avoided" style="height:${savings / top * 100}%"></div>`
            : `<div class="history-slot"></div>`}</div>`;
      } else if (split) {
        label += ` · ${this.t("grid")}: ${this.fmt(month.energy_grid_kwh, 1)} · ${this.t("pv")}: ${this.fmt(month.energy_pv_kwh, 1)}`;
        bars = `<div class="history-grid" style="height:${total ? month.energy_grid_kwh / total * 100 : 0}%"></div><div class="history-pv" style="height:${total ? month.energy_pv_kwh / total * 100 : 0}%"></div>`;
      } else {
        bars = `<div class="history-total" style="height:100%"></div>`;
      }
      const date = new Date(`${keyOf(month).slice(0, 10)}T12:00:00`);
      const locale = this.card._hass?.locale?.language || "en";
      // Thirty day labels do not fit: label every fifth day and the newest one.
      const tick = Number.isNaN(date.getTime()) ? keyOf(month)
        : daily ? (index % 5 === 0 || index === months.length - 1 ? String(date.getDate()) : "")
        : date.toLocaleDateString(locale, {month: "short"});
      return `<div class="history-column" title="${esc(label)}" aria-label="${esc(label)}"${keyOf(month) === currentKey ? " data-current" : ""}>
        <div class="history-track"><div class="history-bar" style="height:${height}%">${bars}</div></div><span>${esc(tick)}</span></div>`;
    }).join("");
    const chart = this.panel.querySelector(".history-chart");
    if (chart.innerHTML !== html) chart.innerHTML = html;
    chart.dataset.money = money ? "1" : "0";
    // Two bars per month need a readable minimum; below that the chart scrolls.
    const minimum = money ? 30 : 0;
    chart.style.gridTemplateColumns = `repeat(${Math.max(1, months.length)}, minmax(${minimum}px, 1fr))`;
    const span = daily ? this.windowDays : (this.options.months || 12);
    this.panel.querySelector("figcaption").textContent = daily
      ? this.t(money ? "chart_cost_days" : "chart_days").replace("{days}", span)
      : money
        ? this.t("chart_cost").replace("{months}", span)
        : this.t("chart_months").replace("{months}", span);
    const legend = this.panel.querySelector(".history-legend");
    const items = money
      ? [[this.t("paid"), "paid"], [this.t("avoided"), "avoided"]]
      : (months.some(month => numeric(month.energy_grid_kwh)) ? [[this.t("grid"), "grid"], [this.t("pv"), "pv"]] : []);
    legend.innerHTML = items.map(([name, key]) => `<span><i class="${key}"></i>${esc(name)}</span>`).join("");
    // Only the newest bar matters on a narrow card: keep it in view.
    if (chart.scrollWidth > chart.clientWidth + 1) chart.scrollLeft = chart.scrollWidth;
    const anyMoney = months.some(month => numeric(month.cost) || numeric(month.saved));
    this.panel.querySelector("[data-chart-note]").textContent = money
      ? (!anyMoney ? this.t("no_money")
        : months.some(month => !numeric(month.cost))
          ? this.t(daily ? "cost_partial_days" : "cost_partial")
          : "")
      : (all.every(month => !numeric(month.energy_grid_kwh))
        ? this.t("total_only")
        : all.some(month => !numeric(month.energy_grid_kwh)) ? this.t("split_partial") : "");
  }

  renderList() {
    const list = this.panel.querySelector(".history-list");
    if (!list) return;
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
