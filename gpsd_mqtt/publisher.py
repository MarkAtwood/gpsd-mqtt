"""Home Assistant MQTT-discovery publisher for GPS state.

Publishes one HA discovery config per entity (retained), a Last-Will-backed
availability topic, and per-key state updates. Entities are grouped onto a
single HA device via the ``device.identifiers`` field so they appear as one
card.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

import paho.mqtt.client as mqtt

from .config import Config
from .gpsd import GpsState

log = logging.getLogger(__name__)

# Each entry describes one HA "sensor": (state key, friendly name, extra config).
# The state key is also the trailing topic level and the discovery object_id.
SENSORS: List[Dict] = [
    {"key": "mode", "name": "Fix mode", "icon": "mdi:crosshairs-gps"},
    {"key": "latitude", "name": "Latitude", "icon": "mdi:latitude",
     "unit_of_measurement": "°", "suggested_display_precision": 6,
     "state_class": "measurement"},
    {"key": "longitude", "name": "Longitude", "icon": "mdi:longitude",
     "unit_of_measurement": "°", "suggested_display_precision": 6,
     "state_class": "measurement"},
    {"key": "altitude", "name": "Altitude", "device_class": "distance",
     "unit_of_measurement": "m", "suggested_display_precision": 1,
     "state_class": "measurement"},
    {"key": "speed", "name": "Speed", "device_class": "speed",
     "unit_of_measurement": "m/s", "suggested_display_precision": 2,
     "state_class": "measurement"},
    {"key": "track", "name": "Course", "icon": "mdi:compass",
     "unit_of_measurement": "°", "suggested_display_precision": 1,
     "state_class": "measurement"},
    {"key": "climb", "name": "Climb", "device_class": "speed",
     "unit_of_measurement": "m/s", "suggested_display_precision": 2,
     "state_class": "measurement"},
    {"key": "satellites_used", "name": "Satellites used",
     "icon": "mdi:satellite-variant", "state_class": "measurement"},
    {"key": "satellites_seen", "name": "Satellites in view",
     "icon": "mdi:satellite-variant", "state_class": "measurement"},
    {"key": "hdop", "name": "HDOP", "icon": "mdi:crosshairs",
     "suggested_display_precision": 2, "state_class": "measurement"},
    {"key": "pdop", "name": "PDOP", "icon": "mdi:crosshairs",
     "suggested_display_precision": 2, "state_class": "measurement"},
    {"key": "time", "name": "Fix time", "device_class": "timestamp",
     "icon": "mdi:clock-outline"},
]


class HaMqttPublisher:
    """Owns the paho MQTT client and renders GPS state to HA topics."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=cfg.mqtt_client_id,
        )
        if cfg.mqtt_username:
            self._client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
        if cfg.mqtt_tls:
            self._client.tls_set(ca_certs=cfg.mqtt_ca_cert)
        self._client.will_set(
            cfg.availability_topic, payload="offline", qos=1, retain=True,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ---- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        log.info("connecting to MQTT broker %s:%d", self.cfg.mqtt_host, self.cfg.mqtt_port)
        self._client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        try:
            self._client.publish(
                self.cfg.availability_topic, "offline", qos=1, retain=True,
            )
        finally:
            self._client.loop_stop()
            self._client.disconnect()

    # ---- callbacks ---------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("connected to MQTT broker")
        self._publish_discovery()
        client.publish(self.cfg.availability_topic, "online", qos=1, retain=True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        log.warning("disconnected from MQTT broker: %s", reason_code)

    # ---- discovery ---------------------------------------------------------
    def _device_block(self) -> Dict:
        return {
            "identifiers": [self.cfg.device_id],
            "name": self.cfg.device_name,
            "manufacturer": self.cfg.device_manufacturer,
            "model": self.cfg.device_model,
        }

    def _publish_discovery(self) -> None:
        device = self._device_block()
        prefix = self.cfg.discovery_prefix
        dev_id = self.cfg.device_id

        for s in SENSORS:
            key = s["key"]
            cfg = {
                "name": s["name"],
                "unique_id": f"{dev_id}_{key}",
                "object_id": f"{dev_id}_{key}",
                "state_topic": self.cfg.state_topic(key),
                "availability_topic": self.cfg.availability_topic,
                "expire_after": self.cfg.expire_after,
                "device": device,
            }
            for extra in ("icon", "unit_of_measurement", "device_class",
                          "state_class", "suggested_display_precision"):
                if extra in s:
                    cfg[extra] = s[extra]
            topic = f"{prefix}/sensor/{dev_id}/{key}/config"
            self._client.publish(topic, json.dumps(cfg), qos=1, retain=True)

        # binary_sensor: GPS fix (connectivity)
        fix_cfg = {
            "name": "GPS fix",
            "unique_id": f"{dev_id}_has_fix",
            "object_id": f"{dev_id}_has_fix",
            "state_topic": self.cfg.state_topic("has_fix"),
            "availability_topic": self.cfg.availability_topic,
            "device_class": "connectivity",
            "payload_on": "ON",
            "payload_off": "OFF",
            "expire_after": self.cfg.expire_after,
            "device": device,
        }
        self._client.publish(
            f"{prefix}/binary_sensor/{dev_id}/has_fix/config",
            json.dumps(fix_cfg), qos=1, retain=True,
        )
        log.info("published HA discovery (%d sensors + fix binary_sensor)", len(SENSORS))

    # ---- state -------------------------------------------------------------
    def publish_state(self, state: GpsState) -> None:
        values: Dict[str, Optional[object]] = {
            "mode": state.mode_name,
            "latitude": state.latitude,
            "longitude": state.longitude,
            "altitude": state.altitude,
            "speed": state.speed,
            "track": state.track,
            "climb": state.climb,
            "satellites_used": state.satellites_used,
            "satellites_seen": state.satellites_seen,
            "hdop": state.hdop,
            "pdop": state.pdop,
            "time": state.time,
        }
        for key, val in values.items():
            if val is None:
                # Skip unknown values; expire_after will age the entity out.
                continue
            self._client.publish(self.cfg.state_topic(key), str(val), qos=0)
        self._client.publish(
            self.cfg.state_topic("has_fix"),
            "ON" if state.has_fix else "OFF", qos=0,
        )
