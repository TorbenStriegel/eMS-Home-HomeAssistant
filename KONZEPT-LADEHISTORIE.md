# Konzept: Ladehistorie für die Integration „ABL eMS Home“

Stand: Repo `TorbenStriegel/eMS-Home-HomeAssistant`, Version 1.3.10 (Commit `d69849d`). Alle Zeilenangaben beziehen sich auf diesen Stand.

---

## 1. Empfehlung

Die Historie bekommt einen eigenen HA-Store je Config Entry (`ems_home.<entry_id>.history`). Er wird nur beim Abschluss eines Ladevorgangs geschrieben, also höchstens 2-mal am Tag, und ist dadurch vom 20-s-Takt des Session-Stores getrennt. Jeder Eintrag entspricht genau einem `ems_home_charging_finished`-Event.

Gespeichert werden Wh und Sekunden als Ganzzahlen, Zeiten in UTC, die damals gültigen Preise und eine UUID, die beim Start vergeben wird. Diese UUID verhindert Doppel-Einträge.

Im UI kommen 4 Zeitraum-Sensoren (Woche, Monat, Jahr, Gesamt) mit den Kennzahlen als Attribute dazu, außerdem eine „Verlauf“-Ansicht in der bestehenden Karte. Die Karte holt Liste und Monatsbalken seitenweise über einen Service mit Rückgabewert (`ems_home.get_history`).

---

## 2. Datenmodell

### Ist-Zustand, auf den das Modell aufsetzt

| Fakt | Beleg |
|---|---|
| Session-Store `Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.session")` | `__init__.py:141` |
| Gespeichert werden `energy_wh`, `grid_wh`, `seconds`, `prev`, `ended`, `last_session`, gedrosselt auf 20 s bei 5 s Store-Delay | `coordinator.py:301–326` |
| Der Payload ist ein Lambda und wird erst beim tatsächlichen Schreiben ausgewertet | `coordinator.py:315` |
| Restore inklusive `ended`. Läuft der Zyklus noch, wird er nach einem Neustart fortgesetzt | `coordinator.py:255–296` |
| Es gibt keinen Startzeitpunkt: `_reset_cycle()` und `_announce_start()` speichern keine Zeit | `coordinator.py:947–956`, `1035–1039` |
| `ended_at = datetime.now(timezone.utc)` wird beim Erkennen des Endes gesetzt. Beim Leerlauf-Ende liegt das rund `IDLE_END_SECONDS` nach dem letzten Fluss | `coordinator.py:933`, `973–985` |
| `cost` gibt es nur, wenn `grid_price > 0 or pv_price > 0`. Berechnet wird sie aus den auf 3 Stellen gerundeten kWh | `coordinator.py:935–940` |
| `saved` wird erst im Event aus dem aktuellen Preis berechnet und nicht gespeichert | `coordinator.py:855–856` |
| `mode` im Finish-Event ist der Modus beim Ende | `coordinator.py:864` |
| Das Fahrzeug wird beim Abschluss gelesen | `coordinator.py:917–926` |
| Intervalle ≥ 300 s werden verworfen (Neustart- oder Lückenschutz) | `coordinator.py:1019`, `1047` |
| `set_last_session` setzt `ended_at=now`, löscht die Zähler und hat keine ID | `coordinator.py:641–689` |
| Test-Events tragen `"test": True` | `coordinator.py:716`, `739` |
| `wallbox_uuid` steht als Attribut zur Verfügung | `sensor.py:626` |
| `split_estimated: True` existiert bereits als Attribut | `sensor.py:596` |

### JSON v1 (Store-Datei)

```json
{
  "version": 1,
  "minor_version": 1,
  "key": "ems_home.<entry_id>.history",
  "data": {
    "sessions": [
      {
        "id": "3f2c9a0e5b7d4e61a0c4b2f19d8e7a55",
        "wallbox_uuid": "a1b2-…",
        "started_at": "2026-11-10T15:34:20+00:00",
        "ended_at": "2026-11-10T18:22:03+00:00",
        "last_flow_at": "2026-11-10T18:17:01+00:00",
        "duration_s": 10062,
        "energy_wh": 8704,
        "grid_wh": 8408,
        "grid_price": 0.35,
        "pv_price": 0.0,
        "cost": 2.943,
        "saved": 0.104,
        "mode_start": "hybrid",
        "mode_end": "hybrid",
        "vehicle": "Seat",
        "end_reason": "idle",
        "still_plugged": true,
        "gap_s": 0,
        "restarts": 0,
        "flags": [],
        "estimated": true,
        "source": "live"
      }
    ],
    "archive": {
      "2021-03": {
        "count": 41,
        "energy_wh": 402113,
        "grid_wh": 300551,
        "cost": 105.2,
        "saved": 35.546,
        "duration_s": 512300,
        "max_wh": 21004,
        "min_wh": 1203,
        "by_vehicle": {"Seat": {"count": 41, "energy_wh": 402113}}
      }
    }
  }
}
```

### Feldtabelle

| Feld | Typ | Einheit | nullable | Herkunft |
|---|---|---|---|---|
| id | str (uuid4 hex) | – | nein | neu, erzeugt beim bestätigten Start (an der Stelle coordinator.py:1035) und im Session-Store persistiert |
| wallbox_uuid | str | – | ja | data.evse.uuid beim Start |
| started_at | ISO-8601 UTC | – | nein | Wanduhr beim Start, zurückgerechnet auf _charge_since: now_utc − (monotonic_now − _charge_since) |
| ended_at | ISO-8601 UTC | – | nein | identisch mit _last_session["ended_at"] (:933), damit Event und Eintrag korrelieren |
| last_flow_at | ISO-8601 UTC | – | nein | neu: Wanduhr des letzten Samples über dem Noise Floor |
| duration_s | int | s | nein | round(_session_seconds), nur Zeit mit Fluss |
| energy_wh | int | Wh | nein | round(_session_energy_wh) |
| grid_wh | int | Wh | nein | round(min(_session_grid_wh, _session_energy_wh)). PV = energy_wh − grid_wh wird nicht gespeichert, damit nichts auseinanderläuft |
| grid_price, pv_price | float | €/kWh | ja | Optionen beim Abschluss. null bedeutet „kein Preis“ |
| cost | float, 3 Stellen | € | ja | wie :936–940, null ohne Preis |
| saved | float, 3 Stellen | € | ja | wie :856, aber gespeichert. null, wenn grid_price ≤ 0 |
| mode_start / mode_end | str | – | ja | _mode() beim Start bzw. beim Abschluss |
| vehicle | str | – | ja | wie :917–922 |
| end_reason | unplugged oder idle | – | nein | Pfad :987–994 bzw. :977–985 |
| still_plugged | bool | – | nein | wie :980 |
| gap_s | int | s | nein | neu: Summe der verworfenen Intervalle ≥ 300 s während eines laufenden Zyklus |
| restarts | int | – | nein | neu: Anzahl der Restores mit ended=False |
| flags | list[str] | – | nein | gap, restarted, mode_changed, clock_suspect |
| estimated | bool | – | nein | in v1 immer true (Energie aus Leistung integriert) |
| source | str | – | nein | live; reserviert für spätere Import-Einträge |

### Regeln

- **Identität:** Die UUID wird beim Start vergeben und mit dem Session-Store persistiert. Es gibt eine Datei pro Config Entry, zwei Geräte bedeuten also zwei Dateien. wallbox_uuid wird mitgeschrieben, ohne die Entitäten pro Wallbox zu trennen.
- **Zeiten:** Gespeichert wird in UTC. Lokale Zeit entsteht erst bei der Aggregation über dt_util.as_local mit der HA-Zeitzone. Die Dauer kommt aus der monotonen Uhr, Zeitumstellung und NTP-Sprung verändern sie daher nicht.
  - clock_suspect wird gesetzt, wenn ended_at < started_at gilt, wenn started_at mehr als 10 min nach der Wanduhr beim Speichern liegt oder wenn ended_at − started_at < duration_s − 60.
- **Rundung:** Energie und Zeit liegen als Ganzzahlen vor, also ohne Drift. Aggregate summieren diese Ganzzahlen und runden erst bei der Ausgabe.
  - Kosten werden je Sitzung auf 3 Stellen gespeichert, wie heute. Die Summe ist dann die Summe der gespeicherten Werte. Gegenüber einer Neuberechnung über alle Sitzungen weicht sie um höchstens 0,0005 € × n ab, bei 730 Sitzungen also ≤ 0,37 €. Dafür bleibt sie identisch zu dem, was Sensoren und Push je Sitzung gezeigt haben.
- **Schwelle:** Gespeichert wird jeder Zyklus, der ein Finish-Event ausgelöst hat. Das Start-Gate (1 kW × 60 s, const.py) lässt mindestens ~17 Wh zu, deshalb gibt es keine zweite Schwelle. Einträge unter 100 Wh markiert die UI als „kurz“.
- **Mitternacht und Woche:** Eine Sitzung zählt zu dem lokalen Tag, an dem sie gestartet ist. Wochen laufen nach ISO 8601 ab Montag.
- **Leerlauf-Ende und späterer Neustart bei angestecktem Auto** ergeben zwei Einträge, so wie es heute zwei Events gibt. Den Zusammenhang zeigt still_plugged am ersten Eintrag.
- **Pause kürzer als idle_end_seconds** ergibt einen Eintrag. Die Differenz zwischen duration_s und ended_at − started_at macht die Pause sichtbar.
- **Moduswechsel:** mode_start und mode_end werden getrennt gespeichert, dazu das Flag mode_changed.
- **Migration:**
  - Unterklasse HistoryStore(Store) mit _async_migrate_func(old_major, old_minor, data). Neue optionale Felder sind ein Minor-Bump, die Leser setzen Defaults. Nur Umbenennungen oder Einheitenwechsel sind ein Major-Bump.
  - **Unbekannte Felder werden durchgereicht:** Einträge bleiben als dict erhalten, beim Schreiben wird nichts herausgefiltert.
  - Downgrade (Datei mit höherer Major-Version): Lesen schlägt fehl. Dann wird die Historie für diese Laufzeit deaktiviert und die Datei nicht überschrieben. Das gilt für jeden Ladefehler: Lädt die Historie nicht, wird sie auch nicht geschrieben.

---

## 3. Speicher & Retention

Gemessen auf dem Hermes-LXC mit `homeassistant.helpers.json.save_json` aus `.venv-test`. HA schreibt mit Einrückung (`option=4` = `OPT_INDENT_2`). Gemessen wurde ein Datensatz mit 19 Feldern, wie im Schema oben.

| Sitzungen | Datei | kompakt | Schreiben (min. von 5) | Laden |
|---|---|---|---|---|
| 1 | 692 B | 461 B | 6,0 ms | 0,3 ms |
| 730 (1 Jahr à 2/Tag) | 410 KB | 269 KB | 5,8 ms | 3,5 ms |
| 2 190 (3 Jahre) | 1,23 MB | 806 KB | 8,9 ms | 11,8 ms |
| 3 650 (5 Jahre) | 2,05 MB | 1,34 MB | 10,9 ms | 16,5 ms |

- **Pro Sitzung:** 562 B in der Datei, 367 B kompakt.
- **Realistische Menge:** Ein Haushalt mit einem Auto hat 3–5 Ladevorgänge pro Woche, also 150–260 pro Jahr und 85–146 KB/Jahr. Die Obergrenze von 2 pro Tag ergibt 410 KB/Jahr.
- **Pi 4 mit SD-Karte (Annahme, nicht gemessen):** Ich rechne mit dem 5- bis 10-fachen der LXC-Zeit, also 30–110 ms für 2 MB. Das Schreiben läuft im Executor. Ob HA auch die Serialisierung dort erledigt, ist ungeprüft. Die Snapshot-Kopie im Event-Loop kostet unter 1 ms.
- **Schreiblast:** 2 Schreibvorgänge pro Tag mit je 2 MB ergeben ~1,5 GB/Jahr. Für eine SD-Karte ist das unkritisch. Der bestehende Session-Store schreibt während eines Ladevorgangs alle 20 s und bleibt unverändert.
- **Retention:** Option `history_retention_months` mit Default 60, `0` heißt unbegrenzt.
  - Ältere Sitzungen werden beim Laden und am Monatswechsel zu `archive[YYYY-MM]` zusammengefasst, ~300 B pro Monat. Erhalten bleiben Anzahl, Wh, Netz-Wh, Kosten, Ersparnis, Dauer, Min/Max und `by_vehicle` je Fahrzeugname.
  - Verloren gehen Einzelzeiten, Modi und Flags.
  - Die Aggregate für Jahr und Gesamt rechnen das Archiv mit ein.

---

## 4. API

### Sensoren (Variante B: ein Sensor je Zeitraum)

| Key / `unique_id`-Suffix | Name DE / EN | State | Einheit | `state_class` |
|---|---|---|---|---|
| `history_week` | Ladehistorie Woche / Charging history week | kWh | kWh | `TOTAL` + `last_reset` = Wochenstart |
| `history_month` | Ladehistorie Monat / Charging history month | kWh | kWh | `TOTAL` + `last_reset` |
| `history_year` | Ladehistorie Jahr / Charging history year | kWh | kWh | `TOTAL` + `last_reset` |
| `history_total` | Ladehistorie gesamt / Charging history total | kWh | kWh | `TOTAL` (nicht `TOTAL_INCREASING`, weil Löschen den Wert senkt) |

- **Attribute je Sensor:** `period_start`, `sessions`, `energy_grid_kwh`, `energy_pv_kwh`, `cost`, `saved`, `avg_kwh`, `max_kwh`, `min_kwh`, `duration_min`, `by_vehicle` (`{name: {sessions, energy_kwh, cost}}`, nur mit Fahrzeugsensor) und `estimated: true`. Das sind ~400–600 B. Der Recorder schreibt sie nur bei Änderungen, also beim Abschluss, beim Löschen und beim Wechsel des Zeitraums.
- **Variante A** (ein Sensor je Kennzahl und Zeitraum) bräuchte 4 × 8 = 32 Entitäten plus 4 × N je Fahrzeug. Das wäre schon bei einem Auto mehr als die heutige Liste von 30 Sensoren. Deshalb abgelehnt.
- `unique_id = f"{entry_id}_{key}"` folgt dem bestehenden Muster (`sensor.py:536`). Bestehende Entitäten bleiben unverändert.
- Kosten und Ersparnis bleiben `null`, wenn keine Sitzung im Zeitraum einen Preis hatte. Das entspricht dem heutigen Verhalten in `sensor.py:559–562`.

### Services

| Service | Felder | Nötig? |
|---|---|---|
| `ems_home.get_history` (`SupportsResponse.ONLY`) | `entry_id?`, `start?`, `end?` (Datum lokal), `vehicle?`, `limit` (Default 20, max. 200), `offset` | ja. Die Karte nutzt ihn, Skripte ebenso |
| `ems_home.delete_session` | `entry_id?`, `session_id` | ja, für Fehl- und Test-Einträge |
| `ems_home.export_history` | `entry_id?`, `format` (`csv` oder `json`), `start?`, `end?` | optional (Entscheidung 4). Schreibt nach `/config/ems_home/`, nie nach `www/` (öffentlich) |
| Nachimport | – | nein (siehe Abschnitt 10) |
| Neuberechnung | – | in v1 nein. Die Preise je Sitzung werden gespeichert, damit sie später möglich ist |

Alle Services bekommen `entry_id`, wie es beim Bestand in `__init__.py:306–320` gelöst ist. Sie werden außerdem in die Entfernen-Schleife `__init__.py:224` aufgenommen.

### Events

- Es gibt kein neues `ems_home_session_recorded`.
- Stattdessen bekommt das bestehende Finish-Event (`coordinator.py:857–869`) zusätzlich `session_id` und `started_at`. Das ist eine reine Erweiterung, bestehende Felder ändern sich nicht. Automationen bekommen so die Referenz auf den Eintrag.

### Recorder und InfluxDB

Die Historie liegt nur im Store. In den Recorder bzw. nach InfluxDB gelangen nur die 4 Zeitraum-Sensoren mit ihren Attributen. Ein Recorder-Purge berührt die Historie nicht.

---

## 5. UI

Die bestehende Karte bekommt einen Button „Verlauf“, der eine Ansicht innerhalb der Karte öffnet.

| Option | Aufwand | Bewertung |
|---|---|---|
| Ansicht in der bestehenden Karte | 8–12 h | gewählt. Kein zusätzlicher Schritt für den Nutzer, Entity-Discovery und `STRINGS` existieren schon |
| Eigene Karte | +4 h | Der Nutzer muss sie selbst hinzufügen |
| Panel | 16 h+ | Seitenleisten-Registrierung, eigener Router. Zu viel für eine Liste |

Der Code für die Verlaufsansicht kommt als eigenes Modul `frontend/ems-home-history.js` (~15–20 KB). Die Karte lädt es per `import()` erst beim ersten Öffnen. Die Static-Path-Registrierung deckt das ganze `frontend/`-Verzeichnis bereits ab (`__init__.py:266–267`). Die Karte selbst bleibt bei 69,8 KB.

```text
┌ eMS Home ───────────────────────────── [Verlauf] ┐
│ … bestehende Ansicht …                           │
└──────────────────────────────────────────────────┘

┌ Verlauf ────────────────── [Woche|Monat|Jahr|Ges.] [×] ┐
│ ┌─────────┐┌─────────┐┌─────────┐┌─────────┐           │
│ │ 14      ││ 186 kWh ││ 41,20 € ││ 18,30 € │           │
│ │Vorgänge ││ Ø 13,3  ││ Kosten  ││ gespart │           │
│ └─────────┘└─────────┘└─────────┘└─────────┘           │
│ Fahrzeug: [Alle ▾]                                      │
│ kWh/Monat  ▁▃▅▂▆█▄▃▅▇▆▄  (12 Monate, Netz/PV gestapelt) │
│ ─────────────────────────────────────────────────────── │
│ heute um 18:22   Seat   8,70 kWh  2:48 h  2,94 €  ⏵    │
│ gestern um 07:05 Seat  21,00 kWh  2:02 h  4,10 €  ⏵    │
│ 12.11. um 22:40  Seat   0,06 kWh  0:04 h  0,02 € kurz  │
│ …                                   [Weitere laden]    │
└─────────────────────────────────────────────────────────┘
```

- **Kacheln** kommen aus den Attributen der Zeitraum-Sensoren und sind sofort da, ohne zusätzlichen Aufruf.
- **Liste und Balken** kommen aus einem einzigen get_history-Aufruf mit limit=20. Die Antwort umfasst ~5 KB Sitzungen plus ~2 KB Monatsaggregate.
  - Lokal rechne ich mit < 50 ms. Hinter Cloudflare kommt pro Aufruf eine Round-Trip-Zeit dazu, geschätzt 100–200 ms (Annahme).
  - Der Python-Teil (Filtern und Summieren von ≤ 3 650 Einträgen aus einem Cache im Speicher) ist nicht gemessen. Ich schätze < 5 ms.
- **Details:** Ein Tipp auf eine Zeile klappt sie inline auf. Gezeigt werden Start/Ende, Netz/PV, Preise, Modus (Start → Ende), Endegrund, Lücken- und Neustart-Hinweise und „geschätzt“. Daneben steht ein Löschen-Button mit Bestätigung, der delete_session aufruft.
- **Bei 500 Sitzungen:** Die Liste lädt seitenweise mit „Weitere laden“ (offset), dazu kommen Zeitraum- und Fahrzeugfilter. Die Balken bleiben auf 12 Monate begrenzt.
- **Warum keine Attribute als Datenquelle:** Die volle Historie als Attribut wären 270 KB pro State-Änderung im Recorder.
- **Uhrzeiten** werden im bestehenden Kalendertag-Format angezeigt („heute um …“). Grundlage ist last_flow_at, weil das der Zeitpunkt ist, an dem tatsächlich nichts mehr floss.
- **Strings:** Alle neuen Texte kommen in STRINGS.de und STRINGS.en. preview/selftest.html wird erweitert.

---

## 6. Randfälle

| Fall | Erwartetes Verhalten | Erkennbar an |
|---|---|---|
| Neustart mitten im Laden | Gleiche `id` und `started_at` aus dem Session-Store, ein einziger Eintrag | `restarts ≥ 1`, Flag `restarted` |
| HA 3 Tage aus, Auto lädt in der Zeit | Lücken ≥ 300 s werden verworfen (`:1047`), die Energie fehlt also. Das Ende wird spät erkannt, `last_flow_at` stimmt trotzdem | `gap_s > 0`, Flag `gap` |
| Absturz zwischen Session-Store und History-Store | Abgleich beim Laden: Hat `last_session` eine `id` und `ended=True`, fehlt aber in der Historie, wird der Eintrag nachgetragen | Log-Zeile, Diagnostics `reconciled` |
| History-Store gespeichert, Session-Store noch „laufend“ | Der Zyklus läuft mit derselben `id` weiter, der Eintrag wird beim Abschluss ersetzt (Upsert) | kein Duplikat |
| `set_last_session` | Keine Änderung an der Historie. Der Snapshot hat keine `id` und wird deshalb auch beim Abgleich ignoriert | kein Eintrag |
| `test_notification` | Keine Änderung an der Historie | `test: true` im Event |
| Preis wird geändert | Nicht rückwirkend, alte Einträge behalten ihre Preise | Preisfelder je Eintrag |
| Kein Preis konfiguriert | `cost`/`saved` = `null`, Aggregate zählen nur Einträge mit Preis | `null` statt 0 |
| Kein Fahrzeugsensor | `vehicle` = `null`, `by_vehicle` fehlt, der Filter in der Karte ist ausgeblendet | – |
| Laden über Mitternacht oder Monatsende | Zählt zum Starttag bzw. Startmonat | `started_at` lokal |
| Zeitumstellung | Dauer unverändert (monotone Uhr), Tageszuordnung über die lokale Zeitzone | Tests für die DST-Tage |
| Systemuhr in der Zukunft oder NTP-Sprung | Eintrag wird trotzdem gespeichert | Flag `clock_suspect` |
| Moduswechsel während des Ladens | `mode_start ≠ mode_end` | Flag `mode_changed` |
| Leerlauf-Ende, danach lädt das Auto erneut | 2 Einträge | `still_plugged: true` am ersten |
| Store-Datei beschädigt oder höhere Version | Historie für diese Laufzeit aus, Datei bleibt unangetastet, Warnung im Log | Diagnostics `load_error` |
| Optionen geändert → Reload | Store wird neu geladen, ausstehende Schreibvorgänge werden beim Entladen per `async_save` erzwungen | – |
| Config Entry wird entfernt | `async_remove_entry` löscht den History-Store (HA-Konvention). Exportieren geht vorher | Hinweis in der README |

---

## 7. Testplan

Die Tests laufen HA-frei, wie die bestehenden `tests/*.py`. Mit **rot** markierte Fälle müssten auf Stand 1.3.10 fehlschlagen.

1. **rot:** Nach dem Abschluss enthält die Historie genau 1 Eintrag mit `id`, `started_at` und `last_flow_at`.
2. **rot:** Ein Neustart mitten im Laden (Save → neuer Coordinator → Restore → Ende) ergibt 1 Eintrag mit `restarts=1` und gleicher `id`.
3. **rot:** Ein Neustart zwischen dem Schreiben des Session-Stores und dem des History-Stores wird nachgetragen; ein doppelter Abschluss erzeugt kein Duplikat (Upsert).
4. `set_last_session` und `test_notification` verändern die Historie nicht, auch nicht nach einem Restore. Der Test ist grün, solange es keine Historie gibt, und muss danach grün bleiben.
5. **rot:** Eine Lücke ≥ 300 s im laufenden Zyklus führt zu `gap_s > 0` und dem Flag `gap`.
6. **rot:** Aggregate über Mitternacht und Monatsgrenze ordnen nach dem lokalen Start zu. Geprüft wird mit Zeitzone `Europe/Berlin` über die DST-Tage 2026-03-29 und 2026-10-25.
7. **rot:** Summen über 1 000 Einträge entsprechen exakt der Summe der Ganzzahl-Wh.
8. **rot:** Eine Preisänderung lässt alte Einträge und die Monatskosten unverändert.
9. **rot:** Retention: Einträge älter als 60 Monate landen im Archiv, die Gesamtsumme bleibt gleich.
10. **rot:** Migration: Unbekannte Felder bleiben erhalten. Eine Datei mit höherer Major-Version führt zu keinem Schreibzugriff.
11. **rot:** `get_history` paginiert und filtert, `delete_session` passt die Aggregate an.
12. **rot:** Das Finish-Event enthält `session_id` und `started_at`, alle bisherigen Felder sind unverändert (Snapshot-Vergleich).
13. Bestehende Wächter laufen auch über die neuen Teile:
    - `test_data_properties.py` erfasst die neuen `d.*`-Zugriffe.
    - Ein Übersetzungs-Test prüft, dass alle neuen Keys in `strings.json`, `de.json` und `en.json` existieren.
    - `ruff check --select F821,F811` läuft vor pytest.
14. Karte: Der Selftest öffnet die Verlaufsansicht mit einer gemockten `get_history`-Antwort und prüft „Weitere laden“, den Fahrzeugfilter und das Aufklappen der Details.

---

## 8. Etappenplan

Jede Etappe ist einzeln auslieferbar.

| # | Inhalt | Aufwand |
|---|---|---|
| 1 | Aufzeichnung im Coordinator (`id`, `started_at`, `last_flow_at`, `mode_start`, `gap_s`, `restarts`), `HistoryStore`, Upsert, Abgleich beim Laden, Diagnostics-Block, Event-Felder. Tests 1–5, 10, 12. Danach wird schon gespeichert, aber noch nichts angezeigt | 7–9 h |
| 2 | Aggregationsmodul mit Cache, 4 Zeitraum-Sensoren, Übersetzungen DE/EN, README. Tests 6–8 | 4–6 h |
| 3 | `get_history`, `delete_session`, `services.yaml`, Übersetzungen. Test 11 | 3–4 h |
| 4 | Verlaufsansicht der Karte (Lazy-Modul, Kacheln, Balken, Liste, Details), Selftest, Screenshots über `scripts/card_shots.py`, README | 8–12 h |
| 5 | Retention und Archiv, Optionen `history_enabled` und `history_retention_months`. Test 9 | 3 h |
| 6 | optional: `export_history` (CSV/JSON) | 2 h |

Summe: 25–34 h, mit Etappe 6 sind es 27–36 h.

---

## 9. Entscheidungen

1. **Historie standardmäßig an?** Empfehlung: an. Sie ändert kein bestehendes Verhalten, belegt nur ~150–410 KB/Jahr und schreibt höchstens 2-mal am Tag. Neu sind 4 Sensoren. Wer „aus“ wählt, hat nach dem Einschalten keine rückwirkenden Daten.
2. **Retention?** Empfehlung: 60 Monate Details, danach Monatsarchiv. Bei „unbegrenzt“ wächst die Datei nach 10 Jahren auf ~4 MB, das Laden auf dem Pi dauert dann ~0,2–0,4 s (Annahme). Bei 24 Monaten gehen Einzelbelege verloren, die man z. B. für eine Dienstwagen-Abrechnung bräuchte.
3. **Zuordnung beim Laden über Mitternacht?** Empfehlung: Starttag. Ein Aufteilen nach Uhrzeit wäre ohne Leistungsverlauf ungenau. Zuordnung nach dem Endtag verschiebt Nachtladungen in den nächsten Monat.
4. **Export als CSV-Datei?** Empfehlung: ja, als Etappe 6. Ohne CSV bleibt nur die JSON-Antwort von `get_history` über die Entwicklerwerkzeuge.
5. **Preisänderung rückwirkend?** Empfehlung: nein. Bei rückwirkender Berechnung würden Historie und frühere Push-Nachrichten verschiedene Beträge zeigen. Die gespeicherten Preise je Sitzung lassen einen späteren `recalculate`-Service trotzdem zu.

---

## 10. Bewusst nicht vorgeschlagen

- **Recorder-Datenbank:** Purge löscht dort Daten, und Integrationen haben kein eigenes Schema darin.
- **Eigene SQLite-Datei:** Abfragen auf ≤ 3 650 Einträgen bringen keinen messbaren Vorteil, das Laden aus JSON dauert 16,5 ms. Dafür kämen Migrationscode, Locking im Executor und ein zusätzlicher Pfad für Backups dazu.
- **Long-Term Statistics als primärer Speicher:** Dort gibt es keine Sitzungen und keine Fahrzeuge. Die `TOTAL`-Sensoren mit `last_reset` liefern trotzdem Statistiken für das Energie-Dashboard.
- **Ein Sensor je Kennzahl bzw. je Fahrzeug:** 32+ Entitäten.
- **Historie in Attributen:** 270 KB pro State im Recorder.
- **Panel:** doppelter Aufwand gegenüber der Kartenansicht, ohne zusätzliche Funktion.
- **Nachimport-Service:** Ohne Leistungsverlauf entstehen ungeprüfte Zahlen. Das Feld `source` ist dafür reserviert.
- **Neues Event `ems_home_session_recorded`:** Es würde dasselbe melden wie das bestehende Finish-Event. Zwei zusätzliche Felder im bestehenden Event reichen.
- **Getrennte Entitäten pro Wallbox:** Laut Projektentscheidung nicht geplant. `wallbox_uuid` wird nur als Feld mitgeschrieben.
- **Zweite Mindestschwelle für die Historie:** Das Start-Gate gibt es schon. Eine zweite Schwelle würde Events und Historie auseinanderlaufen lassen.
- **Energie aus dem Geräteregister `1-0:1.8.0`:** Es wäre genauer, ist aber nur für Firmware 1.1.0 belegt. Erst prüfen, dann als `device_energy_wh` in einer Minor-Version ergänzen.
- **Genauigkeit:** Die Abweichung der integrierten Energie schätze ich auf ±2–5 %. Das ist nicht gemessen. Bis zu einem Vergleich mit dem Register steht im Eintrag deshalb `estimated: true`.
