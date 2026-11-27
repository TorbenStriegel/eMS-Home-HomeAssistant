# The eMS Home guide

This is the long version. It explains what the integration does, how to set it up
once, what the card is telling you, and how to keep the whole thing running for
years without thinking about it. If you only want the short version, the
[README](../README.md) has the tables.

Written for people who own an ABL eMS Home wallbox and a Home Assistant instance,
and who would rather understand the thing than click through it.

---

## 1. What this is, and what it is not

The integration talks to your ABL eMS Home energy manager over your local network.
It reads what the house meter, the solar inverter and the wallbox are doing, shows
that on a dashboard card, and lets you pick a charging mode from the same card.
It also keeps a local record of every completed charge, with energy, cost and the
share that came from your own roof.

It is **not** a charge controller. The wallbox and its energy manager decide how
much current flows. When you pick *PV*, the eMS Home keeps the car on solar power;
the integration only tells it to do so. This distinction matters for the automatic
release later: the integration gives one permission and then watches, it never
adjusts the current itself.

It also does not talk to any cloud. Everything stays in your network, and the
history stays on your Home Assistant machine.

What you need:

- An ABL eMS Home (the energy manager, not just the wallbox) reachable on your LAN.
- The password from the rating plate. The web interface uses the fixed user `admin`.
- Home Assistant with HACS, if you want updates without copying files.

---

## 2. Installing it

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
entry per function that you enable later.

The password is stored in the config entry like every other Home Assistant
credential: in `.storage`, not in YAML. If it changes, the integration asks for a
new one through the re-authentication dialog instead of failing silently.

### What appears after setup

| Entity | What it means |
|---|---|
| Grid power | Positive is import, negative is export. This is the house meter, not the wallbox |
| PV power, battery power | Only if you mapped those sensors in the options |
| Wallbox status | `available`, `charging`, `locked`, and the raw device state as an attribute |
| Charging power, session energy, session duration | What the car is drawing right now |
| Charge mode | The wallbox's mode: `lock`, `grid`, `pv`, `hybrid` |
| PV quota | The slider that tells the wallbox how much of the charge may come from the roof in hybrid mode |

Sensors go `unavailable` when the device is unreachable for longer than the stream
timeout. A short reconnect does not blank them, on purpose: an automation that
triggers on `unavailable` should not fire because the Wi-Fi blinked.

---

## 3. The card

The card is one file, no dependencies, and it is registered as
`custom:ems-home-card`. A minimal configuration is:

```yaml
type: custom:ems-home-card
title: eMS Home
```

You can add it in the dashboard editor: **Add card → Manual** and paste that.

### What you see

The header shows the device name, the current mode as a coloured pill, and a short
status line. A **History** button opens the charging history inside the card. Below
the header, the energy flow animates between the grid, the roof, the house and the
car. The tiles underneath carry the numbers for the current or last charge: grid
import, energy charged, duration, cost. The segmented bar at the bottom is the mode
selector.

The four modes, in plain words:

- **Locked.** The wallbox will not charge. Use it when you want the car to stay
  quiet, for example during a power outage or when the car should only charge at
  work.
- **Grid.** Charge at full power from the grid. The expensive one, useful when you
  need the car full by morning.
- **PV.** Charge only from surplus solar power. The car slows down and stops as
  clouds pass. Nothing is imported.
- **Hybrid.** Charge as fast as possible, but only with a share of your own solar
  power. The quota slider decides how much of the current may come from the grid.

The **Automatic** button above *Locked* is a separate thing, explained in the next
section. It is not a fifth mode.

### The numbers

Cost is energy times the tariff from the integration options, split into the part
that came from the grid and the part that came from your roof. The PV part is
valued at the "value of own PV" tariff, which is your feed-in rate or whatever your
own solar energy is worth to you. Both tariffs live in the integration options; a
card may override them with `price` and `pv_price` for its own display, but stored
history keeps the values that were in force when the charge ended.

If no price is configured, the card hides the cost line entirely rather than
showing a dash. That sentence is worth remembering when you wonder where the cost
went.

### Card options

```yaml
type: custom:ems-home-card
title: eMS Home
layout: full            # or compact: three tiles, no flow
price: 0.35             # overrides the integration tariff for this card
pv_price: 0.08
show_flows: true
show_controls: true
show_automatic: true    # the Automatic button, needs the option in the integration
show_history: true      # the History button
```

Everything can also be set in the visual editor, which writes only what differs
from the defaults into your YAML.

The `history:` block sets how the History window opens. It takes the same six keys
as the standalone history card:

```yaml
history:
  period: week          # week | month | year | total
  metric: cost          # energy (kWh, default) or cost
  title: Ladeverlauf
  vehicle: SEAT Leon    # preselect one car
  show_sessions: false  # the list of charges, on by default in this window
  show_export: false
```

A misspelt key is reported when the card is saved, with the key in the message.
Blank text counts as "not set", so `vehicle: ""` means all cars.

### Compact layout

`layout: compact` is for a phone dashboard where the card shares a column with
other tiles. It keeps the header, the mode icons, the Automatic button and three
numbers, and drops the animation, the rule text and the session list. The History
window still opens in full.

---

## 4. The automatic release

This is the part people install the integration for. It is also the part that can
surprise you, so it is worth reading once, completely.

### The idea

Your wallbox is good at charging with solar power. What it cannot know is whether
you want the car charged today at all, or whether you would rather keep the solar
power for the house battery and the evening. The automatic release answers that
question once a day: it holds the wallbox locked until there is clearly enough
sun, then gives one permission and goes back to watching.

One permission. Not a control loop. After the release, the wallbox does what it
always does; the integration only records what happens.

### Setting it up

Everything lives in **Settings → Devices & Services → ABL eMS Home → Configure →
Automatic charge release**. It is off until you enable it; enabling it does not
arm anything, it only creates the switch and two sensors.

| Option | What to enter | Default |
|---|---|---|
| Set up the automatic charge release | Creates the switch, the state sensor and the problem sensor | off |
| Grid export power sensor | The sensor that shows what flows into the grid. Positive is export | – |
| House battery level sensor | State of charge of the house battery, in %. Not the car | – |
| Grid export above | The export has to be above this | 4000 W |
| Required duration | And it has to stay there, without interruption | 120 s |
| Release when the battery is above | Alternatively, release when the battery is full | 99 % |
| Minimum battery level | Below this, the automatic waits | 90 % |
| Charge with solar power only | After the release, choose PV instead of hybrid | off |
| Release even without a vehicle | Let the order continue when the car is unplugged | off |
| External control takes priority | While this entity is on, unknown or unavailable, nothing is written | – |

Two rules of thumb. The export threshold should be high enough that a cloudy
afternoon does not qualify, and the duration should be long enough that one bright
gap between clouds does not either. If your inverter is small, lower the watts; if
your house has a heat pump that eats the surplus, raise them.

The minimum battery level is a starting condition, not a target, and it is
inclusive: with the default of 90 % the battery has to be **above** 90 % before
the automatic looks at the export. Once the order is running, the battery may drop
below it again; the order is not cancelled by that.

### How it behaves

1. You switch the **Automatic** button on. The wallbox goes to `lock` and the
   conditions are checked from that moment on. You do not have to wait for a
   threshold to be crossed.
2. The release happens when the house battery climbed above the full level, or when
   the export stayed above the threshold for the required duration.
3. The order is used up. The switch goes off, the card shows *released*, then
   *charging*, then *finished*. It never arms itself again.
4. Switching it off gives normal charging back (`hybrid`) and never stops a running
   charge. Switching it on while a charge runs does stop it, because it locks the
   wallbox; the card therefore asks for a second tap in that case.

### What it refuses to do

Unknown data never releases. A missing battery level, a missing export value, a
missing plug state: the state sensor says *Data missing* and names the value. This
also holds when the battery is full, because a full battery next to a dead sensor
is still a guess.

A car that is not plugged in keeps the order waiting (`No vehicle`) unless you
allow the release without a vehicle. Then the plug state is not checked at all,
while the battery level and the export still have to be known; the order is used up
at the first opportunity, which is what you want if the car is usually plugged in
later.

If the wallbox changed the mode behind its back, the integration does not fight
for it. It reports `External control` and stays out of the way. The same happens
while your guard entity is on.

### The states you will see

| State | Meaning | What to do |
|---|---|---|
| `off` | Not armed | Nothing |
| `arming` | Waiting for the wallbox to confirm the lock | Wait a second or two |
| `armed` | Holding the lock, watching the conditions | Wait |
| `waiting_soc` | The battery is below the minimum | Wait for the sun |
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

If you built the same thing with an automation and helpers, the migration is
simple, but the order matters. A guard that is on makes the automatic refuse to arm,
so a running old automation cannot be the guard while you switch over. Disable the
old automation first (`automation.turn_off` with `stop_actions: true`), set the
automatic up with the same sensors, then arm it and watch the states for a day.
Keep the guard entity for the opposite case: another controller that should win
while it is active. Never let both write the mode; the integration reports a
conflict and steps aside, but the wallbox would see two opinions.

---

## 5. Charging history

The integration records every completed charge locally: start and end, duration,
energy from the grid and from your roof, the tariffs that were in force, the mode,
and how the charge ended. Nothing is uploaded.

A charge starts when the power stays above the minimum power for the minimum
duration. It ends when no power flows for the end-of-charge time, even if the car
stays plugged in. Those three numbers are options, because every household has a
different noise floor.

### Where you see it

The History button in the main card, the standalone `custom:ems-home-history-card`,
and a chart-only variant. All three read the same data.

The window has four periods. Week and month draw one bar per day, year and total
one bar per month for the last twelve months. The KPI row above the chart shows
sessions, energy, average and cost for the selected period. A vehicle filter
narrows the list and the KPIs; the bars always show all cars, so a filter never
changes the history you are looking at.

The list is newest first, twenty rows at a time. Expand a row for the details.
Deleting a charge asks for confirmation and updates the totals; it does not change
the last-charge snapshot on the card, and it never touches the wallbox.

### Money

Each session stores the price that was valid when it ended. If you change a tariff
in the options later, old sessions keep their old price. That is deliberate:
otherwise your January costs would change every time you renegotiate your contract.

You can correct a single session with the `ems_home.update_session` service, for
example when you had a different tariff that day. The cost and the saving are
recalculated from the stored energy. Archived months are immutable; the service
answers `updated: false` for them.

Sessions without a price keep `null` instead of `0`, and the chart says so. Zero
would be a statement; nothing is honest.

### Exports

Three ways to get a file:

- The **CSV** button in the history card exports what the chart draws and starts the
  download in your browser.
- The button entity **Export charging history** runs on the server and writes to
  `<config>/ems_home/` and posts a persistent notification with the download link.
- The service `ems_home.export_history` with a format and an optional range.

Exports never go into `www`. They are private files, and the link returned by the
service is signed and expires after five minutes or four downloads. The folder has
a budget of twenty files and 64 MiB: the hourly sweep removes the oldest files, and
while the folder is full a new export is refused with a clear message instead of
writing past the budget. A loop of exports therefore cannot fill your disk. Files younger than ten minutes are spared
because a download may still be running. A restart invalidates every outstanding
link.

If you ever want to see what is in there, `ems_home.cleanup_exports` answers with
numbers: path, files, bytes, and what it would delete. Without `apply` it only
counts.

### Retention

`history_retention_months` decides how long individual sessions are kept, sixty
months by default. Older months are compacted into a monthly total that still has
energy, cost and savings, but no single charges. `0` keeps everything forever.

The archive is what makes the chart useful after a few years without letting the
file grow without limit. A month with thirty charges becomes a handful of numbers;
the eleven-month chart and the year totals stay correct.

### Backups

The history lives in Home Assistant's `.storage`, so it is part of a normal backup.
Two things are worth knowing:

- A restore brings the history back, including the archive.
- Exported files in `<config>/ems_home/` are not part of the integration's storage,
  but they are inside your config directory if your backup covers it. They are
  disposable by design.

After a restore, open the card once. If a sensor shows a stale value, reload the
integration; the streams reconnect on their own within a minute otherwise.

---

## 6. Services, events and automations

The integration fires `ems_home_charging_started` and `ems_home_charging_finished`
for every charge, whether or not the built-in notification is on. The finished
event carries energy, cost, duration, the grid/PV split, the mode and the vehicle
name, so an automation does not have to read the sensors.

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

The built-in notification is an option, not a service. Use one or the other, not
both, or you will get every message twice. There is a test switch that sends a
sample message with the last session's values, so you can check the channel without
waiting for a charge.

The history services (get, delete, update, export, cleanup) are documented in the
README. The first four support response data and an optional `entry_id` when you run
more than one wallbox; `cleanup_exports` works on the shared folder and takes only
`apply` and `keep_hours`.

### A few recipes

**Charge only with solar power, automatically, and stop when the car is full.**
Set the automatic up with your export sensor and the battery level, leave *Charge
with solar power only* off if you want hybrid after the release, or turn it on for
pure PV. Arm it in the evening with an automation, or tap the button when you plug
in.

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

**Ask the wallbox to lock itself when the car is plugged in but you do not want to
charge.** Use the card's mode buttons or a small automation with
`select.select_option` on the charge mode entity; the integration exposes the same
select the card uses.

---

## 7. Keeping it running for years

The integration is built for unattended operation. These are the things that
actually matter over a long period.

### Storage

The history file grows with the number of charges, not with time: a compacted month
is a compact bunch of numbers no matter how often you charged. Measured with the real
record format and 60 months of retention, five years of 8 charges a month come to
about 350 kB, 30 charges a month to about 1.3 MB, before anything is archived. If you
set retention to `0`, it grows forever, and that is your choice.

Export files are capped by the folder budget (twenty files, 64 MiB). You do not
have to clean them up.

### Updates

HACS shows pre-releases only if you enable beta versions for this repository. The
stable releases are what you want for a system that must not surprise you. Read the
release notes before a major version; the card and the integration share a version,
and a card that is newer than the integration is the usual reason for a missing
button.

After an update, Home Assistant reloads the entry. A running charge is not
interrupted by the reload; the wallbox keeps doing what it was told.

### A five-minute monthly check

1. Open the card. Does the status line make sense, and does the number match the
   wallbox app?
2. Open the history. Is the last charge there, with a plausible cost?
3. Look at **Settings → Devices & Services → ABL eMS Home**: any repair issues or
   unavailable entities?
4. Check the automatic's state sensor. If it has been in `degraded_unavailable` for
   days, a sensor is broken.
5. Optional: `ems_home.cleanup_exports` without `apply` and look at `files`.

### When the device is offline

Sensors go unavailable after the stream timeout, the coordinator keeps polling, and
the streams reconnect with a backoff. The automatic reports *Data missing* instead
of releasing. When the device comes back, everything resumes without a reload. If
it stays offline for hours, the integration does not hammer it; the log shows
reconnect attempts, not a traceback every second.

### When Home Assistant restarts

The automatic reloads its order from the store. It does not blindly lock again: it
checks the mode the wallbox reports. If it is still `lock`, the order continues; if
something else changed it, the integration keeps its hands off and reports
`External control`. A release that was in flight is treated as "watch and see": the
old clock is never reused, and if nothing charges within the no-charge timeout the
order ends as `finished` instead of hanging in `starting`.

---

## 8. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Sensors stay `unavailable` | Wrong host, firewall, device asleep | Check the host in the integration, ping it, look at the log |
| Card shows no entities | Card and integration versions differ, or the card was added before setup | Reload the browser, update both, check the entity names in the editor |
| Cost line is missing | No tariff configured, or the sensor has no price | Set the grid price in the options |
| Automatic stays in `waiting_surplus` | The export never reaches the threshold | Lower the threshold, check the sensor's unit (W vs kW) |
| Automatic says `Data missing` | One of the two sensors is unavailable | Look at the sensor named in the card |
| Automatic says `External control` | The mode was changed, or the guard is on | Arm again, or check the guard entity |
| History is empty | History disabled, or no charge has completed since | Check the option, look at the last-charge sensor |
| Export produces no file | The service failed, or the range is empty | Read `warnings` in the response, check `skipped` |
| Charge mode changes by itself | Another automation writes the same select | Disable one of them |

Logs: **Settings → System → Logs**, filter for `ems_home`. Verbose logging is an
option; turn it on for a day when something is odd, then off again, because it
writes a summary every minute.

---

## 9. Privacy and safety

The integration talks only to your device, over your network. There is no cloud
account, no telemetry, and no external request in the code. The password lives in
the config entry like any other credential.

The history contains when you charged, how much, and what it cost. It stays in
`.storage` and in the files you export yourself. Exports are private files with a
short-lived signed link, never in `www`.

The automatic writes exactly one thing to the wallbox: the charge mode. It never
writes current limits, never unlocks a connector, and never changes a schedule.
Everything else stays with the device.

One safety note, because it is easy to forget: arming the automatic locks the
wallbox. If a charge is running at that moment, arming stops it. The card asks for
a second tap for that reason, but an automation that calls the switch does not get
that question.

---

## 10. Glossary

- **Armed.** The automatic has an order and is holding the wallbox locked.
- **Release.** The single permission to charge. After it, the order is used up.
- **Session.** One completed charge, from the first watt to the end-of-charge
  timeout.
- **Archive.** Monthly totals that replace individual sessions older than the
  retention window.
- **Guard.** An entity that, while on or unknown, tells the automatic to stay out.
- **PV quota.** The share of a hybrid charge that may come from the roof.

---

## 11. Where things live

- Integration: `custom_components/ems_home/`
- Card: `custom_components/ems_home/frontend/ems-home-card.js`
- History view: `custom_components/ems_home/frontend/ems-home-history.js`
- Services: `custom_components/ems_home/services.yaml`
- Diagnostics: **Settings → Devices & Services → ABL eMS Home → Download diagnostics**
- Issues: <https://github.com/TorbenStriegel/eMS-Home-HomeAssistant/issues>

If something in this guide is wrong, the code is the truth; the README tries to
keep up, and this page explains the why.
