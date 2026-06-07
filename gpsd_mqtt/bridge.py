"""Main loop: stream gpsd reports and publish GPS state to MQTT."""

from __future__ import annotations

import logging
import signal
import time
from typing import Optional, Sequence

from .config import Config
from .gpsd import GpsdClient, GpsState
from .publisher import HaMqttPublisher

log = logging.getLogger(__name__)


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = Config.load(argv)
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pub = HaMqttPublisher(cfg)
    pub.connect()

    gpsd = GpsdClient(cfg.gpsd_host, cfg.gpsd_port)
    state = GpsState()

    def _shutdown(signum, frame):
        log.info("signal %s received, shutting down", signum)
        gpsd.close()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    last_pub = 0.0
    try:
        for report in gpsd.reports():
            cls = report.get("class")
            changed = False
            if cls == "TPV":
                prev_mode = state.mode
                state.update_tpv(report)
                changed = state.mode != prev_mode
            elif cls == "SKY":
                state.update_sky(report)
            else:
                continue

            now = time.monotonic()
            if changed or (now - last_pub) >= cfg.interval:
                pub.publish_state(state)
                last_pub = now
    finally:
        log.info("stopping")
        pub.disconnect()
    return 0
