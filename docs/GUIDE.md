# The eMS Home guide

This is the long version: what the integration does, how to set it up once, what the
card is telling you, and which checks keep it running over the years. The
[README](../README.md) has the short tables if that is all you need.

This guide is for ABL eMS Home owners who already have Home Assistant running.

A note on words, because they come back constantly:

- A **session** is one completed charge, from the first watt to the end-of-charge
  pause. It is not the time the cable stays connected.
- **PV** means charging from solar surplus. **Hybrid** means charging fast with a
  share of solar.
- **Arming** means giving the automatic one order: hold the wallbox locked until the
  conditions are met, then release once.
- **Automatic** is the button and switch. **Automatic release** is the feature behind
  them; the text uses "the automatic" as shorthand for both.

What is where:

1. [What this is, and what stays with the wallbox](#1-what-this-is-and-what-stays-with-the-wallbox)
2. [Install, and the first check](#2-install-and-the-first-check)
3. [The card, in daily use](#3-the-card-in-daily-use)
4. [The automatic release](#4-the-automatic-release)
5. [History, periods and money](#5-history-periods-and-money)
6. [Restarts, outages, stopping](#6-restarts-outages-stopping)
7. [Backups, updates, and the five-minute check](#7-backups-updates-and-the-five-minute-check)
8. [Services, events and recipes](#8-services-events-and-recipes)
9. [Troubleshooting](#9-troubleshooting)
10. [Data and privacy](#10-data-and-privacy)
11. [Glossary](#11-glossary)
12. [Where things live](#12-where-things-live)

---

## 1. What this is, and what stays with the wallbox

The integration talks to your ABL eMS Home energy manager over your local network. It
reads what the house meter, the solar inverter and the wallbox are doing, shows that
on a dashboard card, and lets you pick a charging mode from the same card. It keeps a
local record of every completed charge, with energy, cost and the share that came
from your own roof.

It is **not** a charge controller. The wallbox and its energy manager decide how much
current flows. When you pick *PV*, the eMS Home keeps the car on solar power; the
integration only tells it to do so. The same is true after an automatic release: one
permission is given, then the integration watches. It never adjusts the current
itself.

The numbers come from the wallbox's power readings. Session energy is integrated from
them once per poll; the grid/solar split is computed from your meter and PV sensors at
the same moments, and when a source is unknown the energy counts as grid, so the
integration never invents savings. Cost is that energy times the tariff. All of it
carries the polling interval's error and the meter's resolution, and nothing more.

The integration itself goes nowhere else: its HTTP and WebSocket connections target the
host you configured, the history stays on your Home Assistant machine, and there is no
telemetry of its own.

What you need:

- An ABL eMS Home (the energy manager, not just the wallbox) reachable on your LAN.
- The password from the rating plate. The web interface uses the fixed user `admin`.
- Home Assistant 2024.12 or newer, with HACS if you want updates without copying files.

---

## 2. Install, and the first check

The repository is a custom HACS repository.

1. In HACS, open the three-dot menu, choose **Custom repositories**, paste
   `https://github.com/TorbenStriegel/eMS-Home-HomeAssistant`, category
   **Integration**, and add it.
2. Search for **ABL eMS Home** in HACS and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for
   **ABL eMS Home**.
5. Enter host, password and, if you changed it, the port. The default port is 80.

The integration creates one device with a set of sensors, a few controls, and one
entry per function that you enable later. The password is stored in the config entry
like every other Home Assistant credential. If it changes, the device login fails; the
new password goes in through **Reconfigure** on the integration page.

### What appears after setup

| Entity | What it means |
|---|---|
| Grid power | Positive is import, negative is export. This is the house meter, not the wallbox |
| PV power, battery power | Your existing sensors, shown because you mapped them in the options. Not created by the integration |
| Wallbox status | `available`, `charging`, `locked`, and the raw device state as an attribute |
| Charging power, session energy, session duration | What the car is drawing right now |
| Charge mode | The wallbox's mode: `lock`, `grid`, `pv`, `hybrid` |
| PV quota | The minimum solar share the wallbox must use in hybrid mode (0-100 %, 10 % steps) |

Sensors go `unavailable` when the device is unreachable for longer than the stream
timeout. A short reconnect does not blank them, on purpose: an automation that
triggers on `unavailable` should not fire because the Wi-Fi blinked.

### Three things to check before you trust the card

1. **The sign of grid power.** The house meter sensor must report import as positive
   and export as negative, because the card's flows use that convention. The automatic
   uses a different input, your export sensor, where export must be positive; the
   options call this out separately. Check both at a moment when you know whether the
   house is importing or exporting.
2. **The tariffs.** The grid price defaults to `0.35 €/kWh`, the value of your own
   solar energy to `0.00 €/kWh`. Set both in the integration options, or the cost
   line is a number with the wrong basis. A card can override them for its display.
3. **One real charge.** Charge for a few minutes, switch to *Locked*, and look at the
   last session. A session starts after a minute above 1 kW and ends after five
   minutes without power by default, so a one-minute test would prove nothing. If
   energy and duration look plausible, the sensors and the thresholds are fine.

---

## 3. The card, in daily use

The card is a bundled frontend module with no external card dependency, registered as
`custom:ems-home-card`. The history window is loaded from the same bundle on demand. You
add the card with **Add card → Manual** and a few lines of YAML; the full option list is
at the end of this chapter.

The header shows the device name, the current mode as a coloured pill, and a short
status line. A **History** button opens the charging history inside the card. Below the
header, the energy flow animates between the grid, the roof, the house and the car. The
tiles underneath carry the numbers for the current or last charge: grid import, energy
charged, duration, cost. The segmented bar at the bottom is the mode selector.

The four modes, in plain words:

- **Locked.** The wallbox will not charge. Use it when the car should stay quiet, for
  example during a power outage or when it should only charge at work.
- **Grid.** Charge at full power from the grid. Useful when the car must be full by
  morning and the sun will not do it.
- **PV.** Charge from surplus solar power, under the wallbox's own solar control. The
  car slows down and may pause while a cloud passes; a small import can happen when
  the wallbox resumes.
- **Hybrid.** Charge at full power, but keep a minimum share of solar in the mix. The
  PV quota slider sets that minimum, in 10 % steps; the rest may come from the grid.

The **Automatic** button above *Locked* is a separate thing, explained in the next
chapter. It is not a fifth mode.

### What the numbers mean

Cost is energy times the tariff from the integration options, split into the part that
came from the grid and the part that came from your roof. The PV part is valued at the
"value of own PV" tariff, which is your feed-in rate or whatever your own solar energy
is worth to you. Both tariffs live in the integration options; a card may override
them with `price` and `pv_price` for its own display, but stored history keeps the
values that were in force when the charge ended.

If no price is configured, the card hides the cost line entirely. If the line is
missing, check the integration tariff and any card-level override.

### Compact layout

`layout: compact` is for a phone dashboard where the card shares a column with other
tiles. It keeps the header, the mode icons, the Automatic button, the Automatic status
and up to three numbers, and drops the flow animation and the session list. The History
window still opens in full.

### Card options

```yaml
type: custom:ems-home-card
title: eMS Home
layout: full            # or compact
price: 0.35             # overrides the integration tariff for this card
pv_price: 0.08
show_flows: true
show_controls: true
show_automatic: true    # the Automatic button, needs the option in the integration
show_history: true      # the History button
```

Everything can also be set in the visual editor, which writes only what differs from
the defaults into your YAML.

The `history:` block sets how the History window opens. It takes the same six keys as
the standalone history card:

```yaml
history:
  period: week          # week | month | year | total (default month)
  metric: cost          # energy (default) or cost
  title: Charging history   # any text; the default is translated
  vehicle: SEAT Leon    # preselect one car
  show_sessions: false  # the list is on by default in this window
  show_export: false    # the export button is on by default
```

A misspelt key is reported when the card is saved, with the key in the message. Blank
text counts as "not set", so `vehicle: ""` means all cars.

---

## 4. The automatic release

**Read this before you enable it: turning Automatic on locks the wallbox. If a charge
is running at that moment, it stops.** The card asks for a second tap for that reason;
an automation that calls the switch does not get that question.

The feature is optional. Enabling it in the options only creates the switch and two
sensors. It does not arm anything.

### The idea

The wallbox regulates solar charging well. What it cannot know is whether you want the
car charged today at all, or whether you would rather keep the surplus for the house
battery and the evening. Automatic release makes that decision once per activation: it
holds the wallbox locked until there is clearly enough sun, then gives one permission
and goes back to watching.

After the release, the wallbox controls the current as usual. The integration observes
the charge and records it; it does not adjust the current and does not lock the
wallbox again when the export falls.

### Setting it up

Everything lives in **Settings → Devices & Services → ABL eMS Home → Configure →
Automatic charge release**. Host, port and password are not in that form; they belong to
**Reconfigure**, which is the entry's other dialog.

Two definitions first, because the table uses them:

- A **guard** is an entity that gives another controller priority. While it is on (or
  unknown, or unavailable), the automatic writes nothing, not even a lock.
- **Arming** is not the same as enabling the feature. Enabling creates the entities;
  arming gives the one order and locks the wallbox.

The release has **two paths**, and one of them is enough:

- **Path 1, house battery full.** The battery is above the full level (default 99 %).
- **Path 2, enough export.** The export stays above the threshold (default 4000 W)
  for the required duration (default 120 s) without interruption, **and** the battery
  is above the path-2 minimum (default 90 %).

The two battery numbers belong to different paths. The minimum only limits path 2:
the dialog insists that the full level is higher, so a battery above the full level
is always above the minimum too. The dialog is built the same way: the sensors first,
then **Path 1: house battery full – only with a battery sensor**, **Path 2: enough export** and **Release
behaviour**.

No house battery? Leave the battery sensor empty. Path 1 then does not exist, and
path 2 has no battery condition: the export alone decides.

| Option | What to enter | Default |
|---|---|---|
| Set up the automatic release | Creates the switch, the state sensor and the problem sensor | off |
| Grid export power (sensor) | What flows into the grid, positive while exporting; W or kW, the sensor's unit is read. This integration's own *Grid power export* sensor fits; it ships disabled, so enable it under the device's entities first, then the dialog suggests it. A grid sensor that reports export as a negative value never releases | – |
| House battery level (sensor, optional) | State of charge of the house battery, in %. Not the car. Empty means no house battery | - |
| External control takes priority | While this entity is on, unknown, unavailable or missing, nothing is written | - |
| Path 1: release when the house battery is above | Strictly above, without waiting for export. The export sensor still has to report a value. 99 is the highest usable value; if your battery reports at most 99 %, choose 98 | 99 % |
| Path 2: export above | More than this, always in W | 4000 W |
| Path 2: … without interruption for | A dip below the threshold, a missing value or an unplugged car restarts the wait. 0 releases on the first reading | 120 s |
| Path 2: … while the house battery is above | At or below this, the export does not count and the wait restarts | 90 % |
| Charge with solar power only | After the release, choose PV instead of hybrid | off |
| Release even without a vehicle | Do not check the plug; the order can be used up before the car arrives | off |

Choose an export threshold and hold duration that match your available surplus and how
stable it is. A threshold below your usual cloudy-afternoon export will qualify too
often; a hold time shorter than a passing gap will release on noise.

The path-2 battery level is checked on every evaluation of the armed wait, not once,
and the battery has to be **above** it: with the default of 90 %, a reading of exactly
90 % waits and restarts the export timer. After the release the battery is no longer
checked, so a running charge is not interrupted when the house battery empties.

### The conditions, together

The automatic checks in this order on every evaluation:

1. **The car is plugged in**, unless *Release even without a vehicle* is on. Without a
   car the order waits (`No vehicle`), and the export wait starts again once the car is
   back, because a dip in between would have gone unseen.
2. **Data is known.** The battery level (if a battery sensor is set), the export power
   and, unless you allowed a release without a vehicle, the plug state. A missing
   value is not treated as zero.
3. **One path holds.** Path 1: the battery is above the full level. Path 2: the battery
   is above the path-2 level and the export stayed above the threshold for the
   required duration, without interruption.

### How it behaves

1. You switch the **Automatic** button on. The wallbox goes to `lock` and the
   conditions are checked from that moment on. You do not have to wait for a threshold
   to be crossed.
2. The release happens as soon as one of the two paths holds.
3. The order is used up. The switch goes off, the card shows *released*, then
   *charging*, then *finished*. If no charging is detected within fifteen minutes after
   the release, the order ends as `finished` instead of waiting forever. It never arms
   itself again.
4. Switching it off gives normal charging back (`hybrid`) and never stops a running
   charge. Switching it on while a charge runs does stop it, because it locks the
   wallbox.

### What it refuses to do

Unknown data never releases. A missing battery level (with a battery sensor set), a
missing export value, a missing plug state: the state sensor says *Data missing* and
names the value. This also holds for path 1 when the battery is full, because a full
battery next to a dead export sensor is still a guess.

A car that is not plugged in keeps the order waiting (`No vehicle`) unless you allowed
a release without a vehicle. With that option, the release can be consumed before a
vehicle is connected; the plug state is then not checked.

If the wallbox changed the mode behind its back, the integration does not fight for
it. It reports `External control` and stays out of the way. The same happens while your
guard entity is on: nothing is written, and even switching the automatic off only
clears the order instead of sending a mode.

### The states you will see

| State | Meaning | What to do |
|---|---|---|
| `off` | Not armed | Nothing |
| `arming` | Waiting for the wallbox to confirm the lock | Wait a second or two |
| `armed` | Holding the lock, watching the conditions | Wait |
| `waiting_soc` | The battery is at or below the path-2 level, so neither path can hold | Wait for the sun |
| `waiting_surplus` | Not enough export (yet), the card names the missing watts | Wait |
| `blocked_no_vehicle` | Armed, but no car | Plug in, or allow a release without one |
| `starting` | The release was sent, waiting for confirmation | A few seconds |
| `released` | Released, no current flowing yet | Check the car |
| `charging` | The car is charging | Nothing |
| `finished` | The charge ended, the order is used up | Arm it again tomorrow |
| `degraded_unavailable` | A value it needs is missing | Look at the sensor it names |
| `conflict_external` | Someone else (or you) changed the mode | Arm it again if you want it |

The problem sensor turns on for the last two only. Waiting is not a problem.

### Coming from an automation

If you built the same thing with an automation and helpers, the migration is simple,
but the order matters. A guard that is on makes the automatic refuse to arm, so a
running old automation cannot be the guard while you switch over. Disable the old
automation first (`automation.turn_off` with `stop_actions: true`), set the automatic up
with the same sensors, then arm it and watch the states for a day.

Keep the guard entity for the opposite case: another controller that should win while
it is active. Never let both write the mode. The integration reports a conflict and
steps aside, but the wallbox would see two opinions.

---

## 5. History, periods and money

The integration records every completed charge: start and end, duration, energy from
the grid and from your roof, the tariffs that were in force, the mode, and how the
charge ended. Nothing is uploaded.

A charge starts when the power stays above the minimum power for the minimum duration.
It ends when no power flows for the end-of-charge time, even if the car stays plugged
in. All three numbers are options, because every household has a different noise floor.

### Two different windows

The history view mixes two windows, and knowing which is which prevents most
confusion:

- **The KPI row** above the chart comes from the period sensor. For *month* that is the
  calendar month, day 1 to the last day, even if the month just started.
- **The bars** always roll: one bar per day for the last 7 or 30 days, one bar per month
  for the last 12 months. A bar chart does not stop at a calendar boundary.

The note under the KPIs names both windows, so a half-finished month with a full bar
chart is not a bug. Week and month draw daily bars; year and total draw monthly bars.

A vehicle filter narrows the list and the KPIs; the bars always show all cars, so a
filter never changes the history you are looking at.

### Seeing and correcting

Open it with the History button in the main card, the standalone
`custom:ems-home-history-card`, or the chart-only variant. All three read the same data.
The standalone cards default to the current month, energy, without the session list;
set the keys you want:

```yaml
type: custom:ems-home-history-card
period: month        # week | month | year | total
metric: cost         # energy (default) or cost
show_sessions: true  # the list is off by default here
```

The list is newest first, twenty rows at a time. Expand a row for the details. Deleting
a charge asks for confirmation and updates the totals; it does not change the
last-charge snapshot on the card, and it never touches the wallbox.

Each session stores the price that was valid when it ended. If you change a tariff in
the options later, old sessions keep their old price. That is deliberate: otherwise
your January costs would change every time you renegotiate your contract. You can
correct a single session with `ems_home.update_session`, for example when you had a
different tariff that day; cost and saving are recalculated from the stored energy.

Sessions without a price keep `null` instead of `0`, and the chart says so. A null cost
means no price was recorded; it is different from a known cost of zero.

### Retention, and why old details disappear

`history_retention_months` decides how long individual sessions are kept, sixty months
by default. Older months are compacted into a monthly total that still has energy, cost
and savings, but no single charges. `0` keeps everything forever.

This matters before you try to edit or export an old month: **once a month is archived,
its details are gone.** `ems_home.update_session` answers `updated: false` for it, and
an export that covers it comes back with a warning. The monthly totals keep the chart
and the year sums correct, but the individual charges cannot be restored.

The archive bounds the detail, not the calendar: archived months keep one compact
record each, so the file grows with the number of months even when their charges are
gone. A month with thirty charges becomes a handful of numbers; a decade of months stays
a decade of numbers.

### Exports

Three ways to get a file:

- The **CSV** button in the history card exports the selected range: the days in the
  chart for week, month and year, and all sessions for *total*. The download starts in
  your browser.
- The button entity **Export charging history** runs on the server, writes to
  `<config>/ems_home/` and posts a persistent notification with the download link.
- The service `ems_home.export_history` with a format and an optional range.

Exports never go into `www`. They are private files, and the link returned by the
service is signed and expires after five minutes or four downloads. The folder has a
budget of twenty files and 64 MiB: the hourly sweep removes the oldest files, and an
export that would break the budget is refused with a clear message instead of writing
past it. Files younger than ten minutes are spared because a download may still be
running. A restart invalidates every outstanding link.

The service answers with the keys you need in an automation:

| Key | Meaning |
|---|---|
| `path` | The file inside `<config>/ems_home/` |
| `url` | The signed download link |
| `expires_at` | When the link stops working |
| `rows` | How many charges are in the file |
| `warnings` | Only present when something to say: `no_sessions_in_range`, `archived_details_unavailable`, `incomplete_records_skipped` |
| `skipped` | Only present when records were incomplete; the count |

A single export is limited to 10,000 sessions and 16 MiB, separate from the folder
budget. Larger ranges are refused with a message; export them in months.

`ems_home.cleanup_exports` answers with `path`, `applied`, `keep_hours`, `removed`,
`files` and `bytes`. Without `apply` it only counts; with `apply` it deletes files older
than `keep_hours` (default 24 hours) and drops expired download tickets. `removed` counts
only files; expired tickets are dropped without being counted. Files younger than ten
minutes are always spared, because a download may still need them.

---

## 6. Restarts, outages, stopping

### When Home Assistant restarts

The automatic reloads its order from the store. It does not blindly lock again: it
checks the mode the wallbox reports. If it is still `lock`, the order continues; if
something else changed it, the integration keeps its hands off and reports
`External control`.

A release that was in flight is treated as "watch and see". The old clock is never
reused, so a reboot cannot leave an order hanging in `starting`; if nothing charges
within the no-charge timeout, the order ends as `finished`.

### When the device is offline

Sensors go unavailable after the stream timeout, the coordinator keeps polling, and the
streams reconnect with a backoff. The automatic reports *Data missing* instead of
releasing. When the device comes back, everything resumes without a reload. If it stays
offline for hours, the integration does not hammer it; the log shows reconnect
attempts, not a traceback every second.

A single failed poll is bridged with the last values, so a blink does not blank
everything. The automatic only releases on values it can confirm in that cycle; from
the second consecutive failure the coordinator reports no device at all.

### Stopping, or removing it

- To stop the automatic, switch **Automatic** off. If the wallbox is not under another
  controller's guard, the mode goes back to `hybrid`; a running charge is not stopped.
- To stop the integration without removing it, disable it in
  **Settings → Devices & Services** (three-dot menu → **Disable**). Entities become
  unavailable, nothing is written, the streams close.
- To remove it, delete the entry. The config entry, its entities and its history store
  are removed. Export any history you want to keep first; a backup still contains the
  old store if you removed the entry by mistake.

---

## 7. Backups, updates, and the five-minute check

### Backups

The history lives in Home Assistant's `.storage`, so it is part of a normal backup. A
restore brings it back, including the archive. Exported files in `<config>/ems_home/`
are not part of the integration's storage, but they are inside your config directory if
your backup covers it; they are disposable by design.

After a restore, open the card once. If a sensor shows a stale value, reload the
integration; the streams reconnect on their own within a minute otherwise.

### Updates

HACS shows pre-releases only if you enable beta versions for this repository. For
routine use, prefer stable releases and read the release notes before a major version.
The card and the integration share a version; if the card is newer than the integration,
a button can be missing.

A HACS update replaces the files; restart Home Assistant afterwards so the new
integration and card are loaded. A running charge is not interrupted by the reload; the
wallbox keeps doing what it was told.

### Storage

The history file grows with the number of charges, not with time: a compacted month is
a compact bunch of numbers no matter how often you charged. Measured with the real
record format and 60 months of retention, five years of 8 charges a month come to about
350 kB, 30 charges a month to about 1.3 MB, 60 charges a month to about 2.6 MB, before
anything is archived. If you set retention to `0`, it grows forever, and that is your
choice.

Export files are capped by the folder budget (twenty files, 64 MiB). You do not have to
clean them up.

### A five-minute monthly check

1. Open the card. Does the status line make sense, and does the number match the
   wallbox app?
2. Open the history. Is the last charge there, with a plausible cost?
3. Look at **Settings → Devices & Services → ABL eMS Home**: any repair issues or
   unavailable entities?
4. Check the automatic's state sensor. If it has been in `degraded_unavailable` for
   days, a sensor is broken.
5. Optional: `ems_home.cleanup_exports` without `apply` and look at `files`.

---

## 8. Services, events and recipes

### Events

The integration fires `ems_home_charging_started` and `ems_home_charging_finished` for
every charge, whether or not the built-in notification is on. The finished event carries
energy, cost, duration, the grid/PV split, the mode and the vehicle name, so an
automation does not have to read the sensors.

```yaml
trigger:
  - platform: event
    event_type: ems_home_charging_finished
action:
  - service: notify.mobile_app_pixel
    data:
      message: >
        {{ trigger.event.data.energy_kwh | round(1) }} kWh,
        {{ '%.2f' | format(trigger.event.data.cost | default(0, true)) }} €,
        {{ trigger.event.data.vehicle | default('car') }}
```

The built-in notification is an option, not a service. Use one or the other, not both,
or you will get every message twice. There is a test switch that sends a sample message
with the last session's values, so you can check the channel without waiting for a
charge.

### History services

The history services are `ems_home.get_history`, `ems_home.update_session`,
`ems_home.delete_session`, `ems_home.export_history` and `ems_home.cleanup_exports`.
The first four support response data and an optional `entry_id` when you run more than
one wallbox; `cleanup_exports` works on the shared folder and takes only `apply` and
`keep_hours`.

`get_history` returns `sessions`, `count`, `months` and `buckets` (the chart data), plus
the `offset` and `limit` it applied. Archived months appear in `months` as totals; their
individual charges are not in `sessions`.

### A few recipes

**Charge with solar power, automatically, when the sun is there.** Set the automatic up
with the export sensor and, if you have one, the house battery level. Leave *Charge with solar power only*
off if you want hybrid after the release, or turn it on for pure PV. Arm it in the
evening with an automation, or tap the button when you plug in. The integration does not
read the car's state of charge; the car stops the charge at its own limit, and the
session ends when no power flows.

**Export the last month on the first of the month.**

```yaml
trigger:
  - platform: time
    at: "06:00:00"
condition:
  - condition: template
    value_template: "{{ now().day == 1 }}"
action:
  - service: ems_home.export_history
    data:
      format: csv
      # first to last day of the previous month
      start: "{{ (now().replace(day=1) - timedelta(days=1)).replace(day=1).date() }}"
      end: "{{ (now().replace(day=1) - timedelta(days=1)).date() }}"
    response_variable: export
  - service: notify.mobile_app_pixel
    data:
      message: "{{ export.rows }} charges exported to {{ export.path }}"
```

**Lock the wallbox when the car is plugged in but you do not want to charge.** Use the
card's mode buttons, or a small automation with `select.select_option` on the charge
mode entity; the integration exposes the same select the card uses.

---

## 9. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Sensors stay `unavailable` | Wrong host, firewall, device asleep | Check the host in the integration, ping it, look at the log |
| Card shows no entities | Card and integration versions differ, or the card was added before setup | Reload the browser, update both, check the entity names in the editor |
| Cost line is missing | No tariff configured, or the sensor has no price | Set the grid price in the options |
| Automatic stays in `waiting_surplus` | The export never reaches the threshold, or the sensor reports export as a negative value | Lower the threshold; check that the sensor is positive while exporting (the integration's own *Grid power export* is) |
| Automatic says `Data missing` | The export sensor, the configured battery sensor or the plug state is unavailable | Look at the value named in the card; a sensor of a disabled or offline integration counts as missing |
| Automatic says `External control` | The mode was changed, or the guard is on | Arm again, or check the guard entity |
| History is empty | History disabled, or no charge has completed since | Check the option, look at the last-charge sensor |
| Export produces no useful file | The range is empty (a valid file with a warning), the folder is full (an error), or a record was incomplete | Read `warnings` and `skipped`, run `cleanup_exports` |
| An old month cannot be edited | It was archived | Nothing; the details are gone by design |
| Charge mode changes by itself | Another automation writes the same select | Disable one of them |

Logs: **Settings → System → Logs**, filter for `ems_home`. Verbose logging is an option;
turn it on for a day when something is odd, then off again, because it writes a summary
every minute.

---

## 10. Data and privacy

The integration talks only to your device, over your network. There is no cloud account
and no telemetry. The password lives in the config entry like any other credential.

The history contains when you charged, how much, and what it cost. It stays in
`.storage` and in the files you export yourself. Exports are private files with a
short-lived signed link, never in `www`.

The automatic writes exactly one thing to the wallbox: the charge mode. It never writes
current limits, never unlocks a connector, and never changes a schedule. Everything else
stays with the device.

Arming Automatic sends the lock command and interrupts any charge in progress; the
wallbox stops the current, not the integration.

---

## 11. Glossary

- **Armed.** The automatic has an order and is holding the wallbox locked.
- **Release.** The single permission to charge. After it, the order is used up.
- **Session.** One completed charge, from the first watt to the end-of-charge timeout.
- **Archive.** Monthly totals that replace individual sessions older than the retention
  window.
- **Guard.** An entity that, while on or unknown, tells the automatic to stay out.
- **PV quota.** The minimum share of a hybrid charge that must come from the roof.
- **KPI row.** The four numbers above the chart; they use the period sensor's calendar
  window, while the bars roll.

---

## 12. Where things live

- Integration: `custom_components/ems_home/`
- Card: `custom_components/ems_home/frontend/ems-home-card.js`
- History view: `custom_components/ems_home/frontend/ems-home-history.js`
- Services: `custom_components/ems_home/services.yaml`
- Diagnostics: **Settings → Devices & Services → ABL eMS Home → Download diagnostics**
- Issues: <https://github.com/TorbenStriegel/eMS-Home-HomeAssistant/issues>

The README has the reference tables. Report documentation errors through the issue
tracker linked above.
