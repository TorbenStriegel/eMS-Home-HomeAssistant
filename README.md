# eMS Home Integration for Home Assistant

**eMS Home** is a custom integration for Home Assistant that allows you to connect to eMS smart meters and read real-time energy data using WebSockets and Protobuf messages.

## Features

* Dynamically fetches authentication token (no hardcoded token needed)
* Real-time updates of smart meter data
* Supports multiple OBIS codes with human-readable names
* Fully configurable via Home Assistant UI (domain and password; username is always `root`)

## Installation via HACS (Custom Repository)

1. Open Home Assistant and go to **HACS → Integrations → Add Custom Repository**.
2. Enter the repository URL: `https://github.com/TorbenStriegel/eMS-Home-HomeAssistant`
3. Select **Integration** and click **Add**.
4. After installation, restart Home Assistant.
5. Configure the integration:

    * Go to **Settings → Devices & Services → Add Integration**
    * Search for **eMS Home**
    * Enter your **domain** (device hostname or IP) and **password** (username is always `root`).

6. After setup, your smart meter entities will appear in Home Assistant and update in real-time.

## Configuration Options

| Option   | Description                                                |
| -------- | ---------------------------------------------------------- |
| domain   | The hostname or IP of your eMS device                      |
| password | Your eMS device password                                   |

## OBIS Codes Mapping

The integration includes a full mapping of common OBIS codes from your smart meter to human-readable names, for example:

* Total active energy import
* Current L1 active power import
* L1 voltage, L2 voltage, L3 voltage
* Reactive power total

You can add additional OBIS codes by editing the `OBIS_MAPPING` dictionary in the integration source code.

## Troubleshooting

* Make sure your device is reachable from the network where Home Assistant runs.
* Ensure the WebSocket port is open if using a local device.
* Check Home Assistant logs (`ems_home` logger) if entities do not appear or update.
* If you see WebSocket authentication errors, verify the password and device accessibility.

## License

This project is open-source and licensed under the MIT License.
