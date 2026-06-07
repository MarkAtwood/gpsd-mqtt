"""Minimal streaming client for the gpsd JSON protocol.

Speaks just enough of the gpsd protocol (https://gpsd.io/gpsd_json.html) to
watch a receiver: it issues a ``?WATCH`` request and yields each decoded JSON
report object. Reconnects automatically if the gpsd connection drops.

Only the TPV (time/position/velocity) and SKY (satellite) report classes are
interpreted by :class:`GpsState`; other classes (VERSION, DEVICES, ...) are
yielded as raw dicts and ignored by the bridge.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass
from typing import Dict, Iterator, Optional

log = logging.getLogger(__name__)

# gpsd fix mode codes (TPV "mode").
MODE_NAMES = {0: "Unknown", 1: "No fix", 2: "2D", 3: "3D"}

# Request a JSON watch stream once connected.
WATCH_CMD = '?WATCH={"enable":true,"json":true}\n'


@dataclass
class GpsState:
    """Accumulated GPS state, updated from successive gpsd reports."""

    mode: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None
    track: Optional[float] = None
    climb: Optional[float] = None
    time: Optional[str] = None
    satellites_used: Optional[int] = None
    satellites_seen: Optional[int] = None
    hdop: Optional[float] = None
    pdop: Optional[float] = None
    vdop: Optional[float] = None

    @property
    def mode_name(self) -> str:
        return MODE_NAMES.get(self.mode, "Unknown")

    @property
    def has_fix(self) -> bool:
        return self.mode >= 2

    def update_tpv(self, r: Dict) -> None:
        """Apply a TPV (time/position/velocity) report."""
        self.mode = int(r.get("mode", self.mode) or 0)
        # When a fix is lost gpsd reports mode<2 and drops the position fields;
        # leave the last-known values in place rather than blanking them.
        if "lat" in r:
            self.latitude = r["lat"]
        if "lon" in r:
            self.longitude = r["lon"]
        # Altitude: prefer mean-sea-level, then generic alt, then HAE ellipsoid.
        if "altMSL" in r:
            self.altitude = r["altMSL"]
        elif "alt" in r:
            self.altitude = r["alt"]
        elif "altHAE" in r:
            self.altitude = r["altHAE"]
        if "speed" in r:
            self.speed = r["speed"]
        if "track" in r:
            self.track = r["track"]
        if "climb" in r:
            self.climb = r["climb"]
        if "time" in r:
            self.time = r["time"]

    def update_sky(self, r: Dict) -> None:
        """Apply a SKY (satellite) report."""
        sats = r.get("satellites")
        if isinstance(sats, list):
            self.satellites_seen = len(sats)
            self.satellites_used = sum(1 for s in sats if s.get("used"))
        # Explicit counts, if gpsd supplies them, are authoritative.
        if "nSat" in r:
            self.satellites_seen = r["nSat"]
        if "uSat" in r:
            self.satellites_used = r["uSat"]
        if "hdop" in r:
            self.hdop = r["hdop"]
        if "pdop" in r:
            self.pdop = r["pdop"]
        if "vdop" in r:
            self.vdop = r["vdop"]


class GpsdClient:
    """Streaming gpsd reader with automatic reconnect."""

    def __init__(self, host: str, port: int, reconnect_delay: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self._sock: Optional[socket.socket] = None
        self._buf = b""
        self._closed = False

    def reports(self) -> Iterator[Dict]:
        """Yield decoded gpsd JSON report objects forever (reconnecting)."""
        while not self._closed:
            try:
                if self._sock is None:
                    self._connect()
                for obj in self._read_objects():
                    yield obj
            except (OSError, ValueError) as exc:
                if self._closed:
                    break
                log.warning("gpsd connection error: %s; reconnecting in %.0fs",
                            exc, self.reconnect_delay)
                self._drop_socket()
                time.sleep(self.reconnect_delay)

    def _connect(self) -> None:
        log.info("connecting to gpsd at %s:%d", self.host, self.port)
        s = socket.create_connection((self.host, self.port), timeout=10)
        s.settimeout(60)
        s.sendall(WATCH_CMD.encode("ascii"))
        self._sock = s
        self._buf = b""
        log.info("connected to gpsd, watch stream started")

    def _read_objects(self) -> Iterator[Dict]:
        assert self._sock is not None
        while not self._closed:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise OSError("gpsd closed the connection")
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    log.debug("skipping unparseable gpsd line: %r", line)

    def _drop_socket(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._buf = b""

    def close(self) -> None:
        """Stop the stream and close the socket (safe from a signal handler)."""
        self._closed = True
        self._drop_socket()
