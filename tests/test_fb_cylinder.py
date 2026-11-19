"""FB_Cylinder - pneumatic cylinder with end position monitoring.

Specification:
  * ValveExtend = CmdExtend AND NOT Error (monostable valve, de-energised = retracted = safe)
  * extend not confirmed within MoveTimeout (2 s) -> Error, ErrorCode 16#0001, valve drops
  * retract not confirmed within MoveTimeout       -> Error, ErrorCode 16#0002
  * both end position sensors on                   -> Error, ErrorCode 16#0003 (immediately)
  * Error is latched until Reset; Reset with the cause gone clears it

Test design
| ID | Technique        | Covers                         | Stimulus                           | Expected                  |
|----|------------------|--------------------------------|------------------------------------|---------------------------|
| S1 | STT normal       | retracted -> extended          | cmd, sensors follow                | IsExtended, no error      |
| B1 | BVT time max-    | extend timeout - 10 ms         | cmd, no sensor, 1990 ms            | no error                  |
| B2 | BVT time max     | extend timeout reached         | cmd, no sensor, 2000 ms            | code 1, valve off         |
| B3 | BVT time max     | retract timeout                | no cmd, not retracted, 2000 ms     | code 2                    |
| I1 | Invalid input EC | both sensors on                | ext AND ret                        | code 3 at once            |
| S2 | STT error->ok    | reset after cause removed      | Reset with sensors ok              | Error FALSE, code 0       |
| S3 | STT error latch  | error stays without reset      | cause removed, no Reset            | Error TRUE                |
"""
import pytest


@pytest.fixture
def cyl(plc):
    inst = plc.new_instance("FB_Cylinder")

    def call(dt=0, **inputs):
        plc.call_fb(inst, dt_ms=dt, **inputs)
        return inst
    return call


def test_S1_normal_extend(cyl):
    cyl(CmdExtend=True, SensorExtended=False, SensorRetracted=True)
    c = cyl(dt=400, SensorExtended=True, SensorRetracted=False)
    assert (c.ValveExtend, c.IsExtended, c.Error) == (True, True, False)


def test_B1_extend_just_before_timeout_no_error(cyl):
    cyl(CmdExtend=True, SensorExtended=False, SensorRetracted=True)
    c = cyl(dt=1990)
    assert c.Error is False and c.ValveExtend is True


def test_B2_extend_timeout_drops_valve(cyl):
    cyl(CmdExtend=True, SensorExtended=False, SensorRetracted=True)
    cyl(dt=1990)
    c = cyl(dt=10)
    assert (c.Error, c.ErrorCode, c.ValveExtend) == (True, 0x0001, False)


def test_B3_retract_timeout(cyl):
    cyl(CmdExtend=False, SensorExtended=True, SensorRetracted=False)
    c = cyl(dt=2000)
    assert (c.Error, c.ErrorCode) == (True, 0x0002)


def test_I1_both_sensors_on_is_sensor_fault(cyl):
    c = cyl(CmdExtend=False, SensorExtended=True, SensorRetracted=True)
    assert (c.Error, c.ErrorCode) == (True, 0x0003)


def test_S2_reset_clears_error_when_cause_gone(cyl):
    cyl(CmdExtend=False, SensorExtended=True, SensorRetracted=True)
    c = cyl(SensorExtended=False, Reset=True)
    assert (c.Error, c.ErrorCode) == (False, 0)


def test_S3_error_stays_latched_without_reset(cyl):
    cyl(CmdExtend=False, SensorExtended=True, SensorRetracted=True)
    c = cyl(dt=100, SensorExtended=False)
    assert c.Error is True
