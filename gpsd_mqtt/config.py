"""Configuration for the gpsd-mqtt bridge.

All settings can be supplied via command-line flags or environment variables.
Environment variables take the form documented in ``gpsd-mqtt.env.example`` and
are the intended path for systemd / container deployment; the CLI flags are
mainly for ad-hoc runs and tests.
"""

from __future__ import annotations

import argparse
import os
import socket
from dataclasses import dataclass
from typing import Optional, Sequence


def _default_device_id() -> str:
    host = socket.gethostname().split(".")[0]
    return f"gpsd_{host}"


@dataclass
class Config:
    """Runtime configuration for the bridge."""

    gpsd_host: str = "127.0.0.1"
    gpsd_port: int = 2947

    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_tls: bool = False
    mqtt_ca_cert: Optional[str] = None
    mqtt_client_id: str = "gpsd-mqtt"

    discovery_prefix: str = "homeassistant"
    topic_base: str = "gpsd"
    device_id: str = "gpsd"
    device_name: str = "GPS (gpsd)"

    interval: float = 2.0
    expire_after: int = 120
    log_level: str = "INFO"

    # ---- derived topics ----------------------------------------------------
    @property
    def availability_topic(self) -> str:
        return f"{self.topic_base}/{self.device_id}/availability"

    def state_topic(self, key: str) -> str:
        return f"{self.topic_base}/{self.device_id}/{key}"

    # ---- loading -----------------------------------------------------------
    @classmethod
    def load(cls, argv: Optional[Sequence[str]] = None) -> "Config":
        """Build a Config from argv, falling back to environment, then defaults."""
        env = os.environ

        def _bool(val: Optional[str], default: bool) -> bool:
            if val is None:
                return default
            return val.strip().lower() in ("1", "true", "yes", "on")

        defaults = cls()

        p = argparse.ArgumentParser(
            prog="gpsd-mqtt",
            description="Bridge a gpsd GPS receiver to MQTT with Home Assistant discovery.",
        )
        p.add_argument("--gpsd-host", default=env.get("GPSD_HOST", defaults.gpsd_host))
        p.add_argument(
            "--gpsd-port", type=int,
            default=int(env.get("GPSD_PORT", defaults.gpsd_port)),
        )
        p.add_argument("--mqtt-host", default=env.get("MQTT_HOST", defaults.mqtt_host))
        p.add_argument(
            "--mqtt-port", type=int,
            default=int(env.get("MQTT_PORT", defaults.mqtt_port)),
        )
        p.add_argument(
            "--mqtt-username",
            default=env.get("MQTT_USERNAME", defaults.mqtt_username),
        )
        p.add_argument(
            "--mqtt-password",
            default=env.get("MQTT_PASSWORD", defaults.mqtt_password),
        )
        p.add_argument(
            "--mqtt-tls", action="store_true",
            default=_bool(env.get("MQTT_TLS"), defaults.mqtt_tls),
        )
        p.add_argument(
            "--mqtt-ca-cert",
            default=env.get("MQTT_CA_CERT", defaults.mqtt_ca_cert),
        )
        p.add_argument(
            "--mqtt-client-id",
            default=env.get("MQTT_CLIENT_ID", defaults.mqtt_client_id),
        )
        p.add_argument(
            "--discovery-prefix",
            default=env.get("HA_DISCOVERY_PREFIX", defaults.discovery_prefix),
        )
        p.add_argument(
            "--topic-base",
            default=env.get("GPSD_MQTT_TOPIC_BASE", defaults.topic_base),
        )
        p.add_argument(
            "--device-id",
            default=env.get("GPSD_MQTT_DEVICE_ID", _default_device_id()),
        )
        p.add_argument(
            "--device-name",
            default=env.get("GPSD_MQTT_DEVICE_NAME", defaults.device_name),
        )
        p.add_argument(
            "--interval", type=float,
            default=float(env.get("GPSD_MQTT_INTERVAL", defaults.interval)),
        )
        p.add_argument(
            "--expire-after", type=int,
            default=int(env.get("GPSD_MQTT_EXPIRE_AFTER", defaults.expire_after)),
        )
        p.add_argument(
            "--log-level",
            default=env.get("GPSD_MQTT_LOG_LEVEL", defaults.log_level),
        )

        a = p.parse_args(argv)
        return cls(
            gpsd_host=a.gpsd_host,
            gpsd_port=a.gpsd_port,
            mqtt_host=a.mqtt_host,
            mqtt_port=a.mqtt_port,
            mqtt_username=a.mqtt_username or None,
            mqtt_password=a.mqtt_password or None,
            mqtt_tls=a.mqtt_tls,
            mqtt_ca_cert=a.mqtt_ca_cert or None,
            mqtt_client_id=a.mqtt_client_id,
            discovery_prefix=a.discovery_prefix,
            topic_base=a.topic_base,
            device_id=a.device_id,
            device_name=a.device_name,
            interval=a.interval,
            expire_after=a.expire_after,
            log_level=a.log_level.upper(),
        )
