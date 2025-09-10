# eMS Home Integration for Home Assistant

**eMS Home** is a custom integration for Home Assistant that allows you to connect to eMS smart meters and read real-time energy data using WebSockets and Protobuf messages.

## Features

* Dynamically fetches authentication token (no hardcoded token needed)
* Real-time updates of smart meter data
* Supports multiple OBIS codes with readable names
* Fully configurable via Home Assistant UI (domain and password)

## Installation via HACS

1. Open Home Assistant and go to **HACS → Integrations → Explore & Download Repositories**.
2. Search for **eMS Home** and install it.
3. After installation, restart Home Assistant.
4. Configure the integration in Home Assistant:

    * Go to **Settings → Devices & Services → Add Integration**
    * Search for **eMS Home**
    * Enter your **domain** and **password** (the username is always `root`)
5. After setup, your smart meter entities will appear in Home Assistant and update in real-time.

## Configuration Options

| Option   | Description                                                |
| -------- | ---------------------------------------------------------- |
| domain   | The base URL of your eMS device (e.g., `ems-device.local`) |
| password | Your eMS device password                                   |

## OBIS Codes Mapping

All common OBIS codes from the smart meter are mapped to human-readable names. Examples include:

* Total active energy import
* Current L1 active power import
* L1 voltage, L2 voltage, L3 voltage
* Reactive power total

The full mapping is included in the source code under `OBIS_MAPPING`.

## Troubleshooting

* Make sure your device is reachable from the network where Home Assistant runs.
* Ensure that the WebSocket port is open if using a local device.
* Check Home Assistant logs if entities do not appear or update.

## License

This project is open-source and licensed under the MIT License.
