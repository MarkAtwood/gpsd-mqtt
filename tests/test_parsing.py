"""Unit tests for gpsd report parsing.

The oracle here is the published gpsd JSON format (gpsd_json(5) /
https://gpsd.io/gpsd_json.html): each fixture below is a representative report
object as gpsd emits it, and the assertions encode what that report *means*
independent of our parser. The parser is never used to validate itself.
"""

from gpsd_mqtt.gpsd import GpsState


def test_tpv_3d_fix():
    state = GpsState()
    # A 3D fix report as gpsd emits it.
    state.update_tpv({
        "class": "TPV", "device": "/dev/ttyUSB0", "mode": 3,
        "time": "2026-06-06T12:34:56.000Z",
        "lat": 47.6204, "lon": -122.3491,
        "altMSL": 56.4, "altHAE": 36.1,
        "speed": 0.12, "track": 145.0, "climb": -0.03,
    })
    assert state.mode == 3
    assert state.mode_name == "3D"
    assert state.has_fix is True
    assert state.latitude == 47.6204
    assert state.longitude == -122.3491
    assert state.altitude == 56.4  # altMSL preferred
    assert state.speed == 0.12
    assert state.track == 145.0
    assert state.climb == -0.03
    assert state.time == "2026-06-06T12:34:56.000Z"


def test_tpv_no_fix_keeps_last_position():
    state = GpsState()
    state.update_tpv({"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0})
    # gpsd drops lat/lon when the fix is lost and reports mode 1.
    state.update_tpv({"class": "TPV", "mode": 1})
    assert state.mode == 1
    assert state.mode_name == "No fix"
    assert state.has_fix is False
    # Last-known position is retained rather than blanked.
    assert state.latitude == 1.0
    assert state.longitude == 2.0


def test_sky_satellites_from_array():
    state = GpsState()
    state.update_sky({
        "class": "SKY", "device": "/dev/ttyUSB0",
        "hdop": 0.8, "pdop": 1.5, "vdop": 1.2,
        "satellites": [
            {"PRN": 1, "used": True},
            {"PRN": 2, "used": True},
            {"PRN": 3, "used": False},
            {"PRN": 4, "used": True},
        ],
    })
    assert state.satellites_seen == 4
    assert state.satellites_used == 3
    assert state.hdop == 0.8
    assert state.pdop == 1.5
    assert state.vdop == 1.2


def test_sky_explicit_counts_override_array():
    state = GpsState()
    # gpsd may supply nSat/uSat alongside a (possibly truncated) array;
    # the explicit counts are authoritative.
    state.update_sky({
        "class": "SKY",
        "nSat": 12, "uSat": 9,
        "satellites": [{"PRN": 1, "used": True}],
    })
    assert state.satellites_seen == 12
    assert state.satellites_used == 9


def test_altitude_falls_back_when_no_altMSL():
    state = GpsState()
    state.update_tpv({"class": "TPV", "mode": 3, "alt": 40.0, "altHAE": 36.1})
    assert state.altitude == 40.0  # generic alt over altHAE
    state2 = GpsState()
    state2.update_tpv({"class": "TPV", "mode": 3, "altHAE": 36.1})
    assert state2.altitude == 36.1  # only HAE available
