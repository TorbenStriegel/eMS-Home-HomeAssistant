# OBIS Mapping (readable names)
OBIS_MAPPING = {
    "1-0:1.8.0*255": "Total active energy import",
    "1-0:2.8.0*255": "Total active energy export",
    "1-0:3.8.0*255": "Total reactive energy import",
    "1-0:4.8.0*255": "Total reactive energy export",
    "1-0:1.4.0*255": "Tariff 1 active energy import",
    "1-0:2.4.0*255": "Tariff 1 active energy export",
    "1-0:3.4.0*255": "Tariff 1 reactive energy import",
    "1-0:4.4.0*255": "Tariff 1 reactive energy export",
    "1-0:9.4.0*255": "Current L1 active power import",
    "1-0:9.8.0*255": "Current L1 reactive power import",
    "1-0:10.4.0*255": "Current L2 active power import",
    "1-0:10.8.0*255": "Current L2 reactive power import",
    "1-0:13.4.0*255": "Current L3 active power import",
    "1-0:14.4.0*255": "Current L3 reactive power import",
    "1-0:21.4.0*255": "Tariff 2 active energy import",
    "1-0:21.8.0*255": "Tariff 2 reactive energy import",
    "1-0:22.4.0*255": "Tariff 2 active energy export",
    "1-0:22.8.0*255": "Tariff 2 reactive energy export",
    "1-0:23.4.0*255": "Tariff 3 active energy import",
    "1-0:23.8.0*255": "Tariff 3 reactive energy import",
    "1-0:24.4.0*255": "Tariff 3 active energy export",
    "1-0:24.8.0*255": "Tariff 3 reactive energy export",
    "1-0:29.4.0*255": "L1 voltage",
    "1-0:29.8.0*255": "L1 current",
    "1-0:30.4.0*255": "L2 voltage",
    "1-0:30.8.0*255": "L2 current",
    "1-0:31.4.0*255": "L3 voltage",
    "1-0:32.4.0*255": "L3 current",
    "1-0:33.4.0*255": "Neutral current",
    "1-0:41.4.0*255": "Frequency",
    "1-0:41.8.0*255": "Power factor",
    "1-0:42.4.0*255": "Phase angle L1",
    "1-0:42.8.0*255": "Phase angle L2",
    "1-0:43.4.0*255": "Phase angle L3",
    "1-0:43.8.0*255": "Phase angle N",
    "1-0:44.4.0*255": "Reactive power L1",
    "1-0:44.8.0*255": "Reactive power L2",
    "1-0:49.4.0*255": "Apparent power L1",
    "1-0:49.8.0*255": "Apparent power L2",
    "1-0:50.4.0*255": "Apparent power L3",
    "1-0:50.8.0*255": "Apparent power N",
    "1-0:51.4.0*255": "Active power L1",
    "1-0:52.4.0*255": "Active power L2",
    "1-0:53.4.0*255": "Active power L3",
    "1-0:61.4.0*255": "Reactive power total",
    "1-0:61.8.0*255": "Reactive power import total",
    "1-0:62.4.0*255": "Reactive power export total",
    "1-0:62.8.0*255": "Reactive power total L1",
    "1-0:63.4.0*255": "Reactive power total L2",
    "1-0:63.8.0*255": "Reactive power total L3",
    "1-0:64.4.0*255": "Apparent power total",
    "1-0:64.8.0*255": "Apparent power total L1",
    "1-0:69.4.0*255": "Total harmonic distortion L1",
    "1-0:69.8.0*255": "Total harmonic distortion L2",
    "1-0:70.4.0*255": "Total harmonic distortion L3",
    "1-0:70.8.0*255": "Total harmonic distortion N",
    "1-0:71.4.0*255": "Max demand L1",
    "1-0:72.4.0*255": "Max demand L2",
    "1-0:73.4.0*255": "Max demand L3",
}

def decode_obis_key(key: int):
    """Decode integer OBIS key to human-readable format."""
    t = [0] * 8
    e = key
    for r in range(8):
        n = e & 0xFF
        t[7 - r] = n
        e = (e - n) // 256
    t = t[2:]
    Media, Channel, Indicator, Mode, Quantities, Storage = t
    return f"{Media}-{Channel}:{Indicator}.{Mode}.{Quantities}*{Storage}"