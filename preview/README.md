# Card preview & self-test

Development harness for `custom_components/ems_home/frontend/ems-home-card.js`,
kept in the repo so visual and behavioural changes can be checked without a
Home Assistant instance.

```bash
# from the repository root
python3 -m http.server 8899
# then open http://127.0.0.1:8899/preview/index.html     – renders the variants
# and        http://127.0.0.1:8899/preview/selftest.html – prints PASS/FAIL
```

`selftest.html` runs in headless Chrome too:

```bash
google-chrome --headless=new --virtual-time-budget=4000 --dump-dom \
  http://127.0.0.1:8899/preview/selftest.html | grep -o 'PASS.*\|FAIL.*'
```

It uses the entity ids and the entity-registry layout of a real installation
(device name `controlroom`, including the `sensor.ems_home_charge_mode` decoy
next to `select.ems_home_charge_mode`) and checks that

- entity discovery finds the right entities, in the right domain,
- a mode click reaches `select.select_option` on the select entity,
- a state update patches values instead of rebuilding the DOM,
- grid power is throttled to 5 s while charging power stays live,
- locked mode hides flow and figures, PV/hybrid show "PV + Netz".
