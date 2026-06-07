# gpsd-mqtt

Bridge a [gpsd](https://gpsd.io/) GPS receiver to MQTT, with
[Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).

`gpsd` speaks its own JSON protocol on TCP 2947 but does not publish to MQTT.
This small daemon watches a gpsd instance and republishes the fix as MQTT
sensors that Home Assistant auto-discovers as a single device — no YAML, no
custom component.

## Features

- Streams gpsd's `WATCH` feed (TPV + SKY reports); no polling.
- Publishes HA discovery for fix mode, lat/lon, altitude, speed, course,
  climb, satellites used / in view, HDOP/PDOP, fix time, and a `GPS fix`
  connectivity binary sensor.
- Availability via MQTT Last-Will plus per-entity `expire_after`, so HA shows
  the device offline if either the bridge or the broker drops.
- Auto-reconnects to both gpsd and the broker.
- Single dependency (`paho-mqtt`); installs a `gpsd-mqtt` console script.
- Hardened systemd unit included (`DynamicUser`, `ProtectSystem=strict`, ...).

## How it works

```
GPS ──USB/serial──> gpsd ──TCP 2947 JSON──> gpsd-mqtt ──MQTT──> broker ──> Home Assistant
```

The bridge connects to gpsd, sends `?WATCH={"enable":true,"json":true}`, and
folds each TPV/SKY report into a running state object that it publishes to MQTT
on fix-mode changes and at most every `--interval` seconds otherwise.

## Requirements

- Python 3.9+
- A reachable `gpsd` (≥ 3.x). If the bridge runs on a different host than
  gpsd, start gpsd with `-G` so it listens on all interfaces, e.g.
  `gpsd -n -G /dev/ttyUSB0`.
- An MQTT broker, and Home Assistant with the MQTT integration configured.

## Install

```bash
pip install gpsd-mqtt        # from PyPI (once published)
# or, from a checkout:
pip install .
```

## Run

```bash
# All settings have env-var and CLI equivalents; see --help.
gpsd-mqtt --gpsd-host 127.0.0.1 --mqtt-host 192.0.2.10 \
          --mqtt-username gps --mqtt-password secret
```

Or via environment (the systemd unit's `EnvironmentFile` path):

```bash
cp gpsd-mqtt.env.example /etc/default/gpsd-mqtt   # then edit, chmod 0600
gpsd-mqtt
```

### Configuration

| Env var | CLI flag | Default | Meaning |
| --- | --- | --- | --- |
| `GPSD_HOST` | `--gpsd-host` | `127.0.0.1` | gpsd host |
| `GPSD_PORT` | `--gpsd-port` | `2947` | gpsd port |
| `MQTT_HOST` | `--mqtt-host` | `127.0.0.1` | broker host |
| `MQTT_PORT` | `--mqtt-port` | `1883` | broker port |
| `MQTT_USERNAME` | `--mqtt-username` | — | broker username |
| `MQTT_PASSWORD` | `--mqtt-password` | — | broker password |
| `MQTT_TLS` | `--mqtt-tls` | `false` | enable TLS |
| `MQTT_CA_CERT` | `--mqtt-ca-cert` | — | CA bundle for TLS |
| `MQTT_CLIENT_ID` | `--mqtt-client-id` | `gpsd-mqtt` | MQTT client id |
| `HA_DISCOVERY_PREFIX` | `--discovery-prefix` | `homeassistant` | HA discovery prefix |
| `GPSD_MQTT_TOPIC_BASE` | `--topic-base` | `gpsd` | state topic base |
| `GPSD_MQTT_DEVICE_ID` | `--device-id` | `gpsd_<hostname>` | HA device id (groups entities) |
| `GPSD_MQTT_DEVICE_NAME` | `--device-name` | `GPS (gpsd)` | HA device name |
| `GPSD_MQTT_DEVICE_MANUFACTURER` | `--device-manufacturer` | `gpsd` | HA device manufacturer |
| `GPSD_MQTT_DEVICE_MODEL` | `--device-model` | `gpsd MQTT bridge` | HA device model |
| `GPSD_MQTT_INTERVAL` | `--interval` | `2.0` | min seconds between publishes |
| `GPSD_MQTT_EXPIRE_AFTER` | `--expire-after` | `120` | HA staleness timeout (s) |
| `GPSD_MQTT_LOG_LEVEL` | `--log-level` | `INFO` | log level |

To attach these entities to an **existing** Home Assistant device (e.g. one
created by another integration), set `GPSD_MQTT_DEVICE_ID` to that device's
identifier; matching its `DEVICE_MANUFACTURER`/`DEVICE_MODEL` avoids HA
rewriting the device's metadata.

## systemd

```bash
sudo cp gpsd-mqtt.env.example /etc/default/gpsd-mqtt   # edit + chmod 0600
sudo install -m0644 systemd/gpsd-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gpsd-mqtt.service
```

## Home Assistant entities

After the first run, HA shows a device (named by `GPSD_MQTT_DEVICE_NAME`) with:

- **Fix mode** (Unknown / No fix / 2D / 3D)
- **GPS fix** (connectivity binary sensor)
- **Latitude**, **Longitude**, **Altitude**
- **Speed**, **Course**, **Climb**
- **Satellites used**, **Satellites in view**
- **HDOP**, **PDOP**
- **Fix time** (timestamp)

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## License

MIT — see [LICENSE](LICENSE).
