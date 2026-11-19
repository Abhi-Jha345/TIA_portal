"""Station level tests: the complete program (OB -> FB_CellSortingMain) and FB_SortStation.

Specification (design sheet + safety concept):
  modes  STOPPED(0) -> RESETTING(10) -> IDLE(20) -> EXECUTE(30); any fault -> ABORTED(90)
  steps  WAIT_CELL(100) -> MEASURE(110) -> GRADE(120) -> EJECT(130) -> RETRACT(140)
  * Stop is executed only at the end of a cycle (never a half sorted cell)
  * counters: Total = A + B + Reject, Yield = (A + B) / Total * 100
  * E-stop / door / discrepancy -> ABORTED; leaving ABORTED needs safety reset AND Reset
  * no automatic restart: after ABORTED the station returns to IDLE, never to EXECUTE
  * bin full -> hold in WAIT_CELL until "bins emptied"

Test design
| ID  | Technique      | Covers                               | Expected                                   |
|-----|----------------|--------------------------------------|--------------------------------------------|
| S1  | STT            | power-up                             | ABORTED, 'SAFETY STOP', no energy          |
| S2  | STT invalid    | Start while ABORTED                  | stays ABORTED                              |
| S3  | STT invalid    | Reset without safety reset           | stays ABORTED                              |
| S4  | STT round trip | safety reset, Reset, Start           | IDLE then EXECUTE                          |
| U1  | Use case main  | 30 s production                      | cells sorted, Total = A+B+Rej, yield ok    |
| U2  | Use case       | Stop during MEASURE                  | cycle finished, then IDLE, outputs off     |
| U3  | Use case fault | pusher B jams                        | PusherB alarm, ABORTED, valves off         |
| U4  | Use case safety| E-stop in EXECUTE                    | same scan: ABORTED, conveyor + energy off  |
| U5  | Use case safety| recovery after E-stop                | IDLE (not EXECUTE) after reset sequence    |
| U6  | Use case safety| door opened in EXECUTE               | ABORTED, energy off after 1 s              |
| U7  | Use case       | bin capacity reached                 | HELD, no new cells; resumes after emptying |
| U8  | Use case       | reset counters                       | all counters 0, yield 0                    |
| U9  | Use case safety| welded E-stop contact                | SafetyDiscrepancy alarm, no restart        |
| G1  | Glass box      | measuring unit never answers         | MeasureTimeout after 3 s                   |
| G2  | Glass box      | A cell does not leave the station    | TransportTimeout after 3 s                 |
| G3  | Glass box      | fresh FB, no reset yet               | STOPPED, text 'STOPPED'                    |
| G4  | Robustness     | corrupted state number               | falls back to STOPPED                      |
| G5  | Robustness     | corrupted step number                | falls back to WAIT_CELL                    |
| G6  | Glass box      | reject pusher never extends          | PusherR alarm, valve off, ABORTED          |
| G7  | Glass box      | cell still present after retract     | TransportTimeout                           |
"""
import pytest

STOPPED, RESETTING, IDLE, EXECUTE, ABORTED = 0, 10, 20, 30, 90
WAIT_CELL, MEASURE = 100, 110


# ------------------------------------------------------------------ mode machine
def test_S1_power_up_is_safety_stop(station):
    station.run(500)
    assert (station.sts.State, station.sts.StateText, station.sts.EnergyEnable) == \
           (ABORTED, "SAFETY STOP", False)


def test_S2_start_ignored_while_aborted(station):
    station.run(100)
    station.press("Start")
    station.run(500)
    assert station.sts.State == ABORTED


def test_S3_reset_without_safety_reset_is_ignored(station):
    station.press("Reset")
    station.run(500)
    assert station.sts.State == ABORTED


def test_S4_round_trip_to_execute(station):
    station.bring_to_idle()
    assert station.sts.State == IDLE
    station.press("Start")
    assert (station.sts.State, station.sts.Step) == (EXECUTE, WAIT_CELL)


# ------------------------------------------------------------------ use cases
def test_U1_production_sorts_cells_consistently(station):
    station.hmi.Par.BinCapacity = 1000
    station.start_production()
    station.run(120000)
    c = station.sts.Counters
    assert c.GradeA > 0 and c.GradeB > 0 and c.Reject > 0      # every output class reached
    assert station.sts.State == EXECUTE                         # no fault during production
    assert c.Total == c.GradeA + c.GradeB + c.Reject
    assert c.Yield_pct == pytest.approx(100.0 * (c.GradeA + c.GradeB) / c.Total)
    assert station.sts.BinB_Count == c.GradeB and station.sts.BinR_Count == c.Reject


def test_U2_stop_is_executed_at_end_of_cycle(station):
    station.start_production()
    station.run_until(lambda: station.sts.Step == MEASURE)
    total_before = station.sts.Counters.Total
    station.press("Stop")
    assert station.sts.State == EXECUTE and station.sts.StopPending
    station.run_until(lambda: station.sts.State == IDLE)
    assert station.sts.Counters.Total == total_before + 1          # cycle was completed
    assert not (station.sts.ConveyorRun or station.sts.PusherB or station.sts.PusherR)
    assert station.sts.CellAtStation is False                       # no cell left half sorted


def test_U3_jammed_pusher_aborts_with_valves_off(station):
    station.start_production()
    station.hold("SimJamPusherB")
    station.run_until(lambda: station.sts.Alarms.PusherB, 60000)
    assert station.sts.State == ABORTED
    assert not (station.sts.PusherB or station.sts.ConveyorRun)


def test_U4_estop_stops_in_the_same_scan(station):
    station.start_production()
    station.run(2000)
    station.hold("SimEStop")
    s = station.sts
    assert (s.State, s.ConveyorRun, s.PusherB, s.PusherR, s.EnergyEnable, s.Alarms.EStop) == \
           (ABORTED, False, False, False, False, True)


def test_U5_no_automatic_restart_after_estop(station):
    station.start_production()
    station.hold("SimEStop")
    station.hold("SimEStop", False)
    station.press("Reset")                      # machine reset alone is not enough
    station.run(300)
    assert station.sts.State == ABORTED and station.sts.ResetRequired
    station.bring_to_idle()                     # safety reset + Reset
    station.run(1000)
    assert station.sts.State == IDLE            # waits for a new Start


def test_U6_door_is_controlled_stop_category_1(station):
    station.start_production()
    station.run(2000)
    station.hold("SimDoorOpen")
    assert station.sts.State == ABORTED and station.sts.Alarms.DoorOpen
    station.run(500)
    assert station.sts.EnergyEnable is True     # controlled stop in progress
    station.run(600)
    assert station.sts.EnergyEnable is False    # energy removed after 1 s


def test_U7_bin_full_holds_and_resumes(station):
    station.hmi.Par.BinCapacity = 2
    station.start_production()
    station.run_until(lambda: station.sts.Alarms.BinBFull or station.sts.Alarms.BinRFull, 60000)
    total = station.sts.Counters.Total
    station.run(5000)
    assert station.sts.StateText.startswith("HELD")
    assert station.sts.Counters.Total == total and not station.sts.ConveyorRun
    station.press("BinsEmptied")
    station.run(8000)
    assert station.sts.Counters.Total > total


def test_U8_reset_counters(station):
    station.start_production()
    station.run(10000)
    station.press("ResetCounters")
    c = station.sts.Counters
    assert (c.Total, c.GradeA, c.GradeB, c.Reject, c.Yield_pct) == (0, 0, 0, 0, 0.0)


def test_U9_welded_estop_contact_is_detected(station):
    station.start_production()
    station.hold("SimDiscrepancy")              # channel B welded
    station.hold("SimEStop")
    station.run(600)
    assert station.sts.State == ABORTED and station.sts.Alarms.SafetyDiscrepancy
    station.hold("SimEStop", False)
    station.safety_reset()
    station.run(100)
    assert station.sts.SafetyOk is False        # cannot be reset while the fault is present


# ------------------------------------------------------------------ glass box (FB alone)
@pytest.fixture
def fb(plc):
    inst = plc.new_instance("FB_SortStation")
    base = dict(SafetyOk=True, EStopOk=True, DoorClosed=True, SafetyDiscrepancy=False,
                PusherB_Ret=True, PusherR_Ret=True, CellAtStation=False)

    def scan(dt=10, **inputs):
        merged = dict(base, **inputs)
        base.update(inputs)
        plc.call_fb(inst, dt_ms=dt, **merged)
        return inst

    scan(Reset=True)
    scan(Reset=False)
    scan(Start=True)
    scan(Start=False)
    assert inst.State == EXECUTE
    return scan


def _run(fb, ms):
    for _ in range(ms // 10):
        s = fb()
    return s


def test_G1_measuring_unit_timeout(fb):
    fb(CellAtStation=True)
    s = _run(fb, 2900)
    assert s.State == EXECUTE and s.MeasureStart and not s.Alarms.MeasureTimeout
    s = _run(fb, 200)
    assert s.Alarms.MeasureTimeout and s.State == ABORTED and not s.MeasureStart


def test_G2_transport_timeout_when_good_cell_stays(fb):
    fb(CellAtStation=True)
    fb(MeasureDone=True, Voltage_V=3.65, Resistance_mOhm=15.0)
    fb(MeasureDone=False)
    s = fb()                                     # EJECT, grade A: conveyor runs
    assert s.Step == 130 and s.ConveyorRun
    s = _run(fb, 2900)
    assert not s.Alarms.TransportTimeout
    s = _run(fb, 200)
    assert s.Alarms.TransportTimeout and s.State == ABORTED and not s.ConveyorRun


SAFE_INPUTS = dict(SafetyOk=True, EStopOk=True, DoorClosed=True, SafetyDiscrepancy=False,
                   PusherB_Ret=True, PusherR_Ret=True)


def test_G3_fresh_fb_waits_in_stopped(plc):
    inst = plc.new_instance("FB_SortStation")
    plc.call_fb(inst, dt_ms=10, **SAFE_INPUTS)
    assert (inst.State, inst.StateText) == (STOPPED, "STOPPED")


def test_G4_corrupted_state_falls_back_to_stopped(plc):
    inst = plc.new_instance("FB_SortStation")
    inst.actState = 55
    plc.call_fb(inst, dt_ms=10, **SAFE_INPUTS)
    assert inst.State == STOPPED


def test_G5_corrupted_step_falls_back_to_wait_cell(fb, plc):
    s = fb()
    s.actStep = 999
    s = fb()
    assert s.Step == WAIT_CELL


def test_G6_reject_pusher_jam(fb):
    fb(CellAtStation=True)
    fb(MeasureDone=True, Voltage_V=3.20, Resistance_mOhm=15.0)    # grade Reject
    fb(MeasureDone=False)
    s = _run(fb, 2100)                                           # pusher R never extends
    assert s.Alarms.PusherR and s.State == ABORTED and not s.ValvePusherR


def test_G7_cell_still_present_after_retract(fb):
    fb(CellAtStation=True)
    fb(MeasureDone=True, Voltage_V=3.57, Resistance_mOhm=20.0)    # grade B
    fb(MeasureDone=False)
    fb()
    fb(PusherB_Ext=True, PusherB_Ret=False)                      # pusher B extended
    s = fb()                                                     # step chain sees it next scan
    assert s.Step == 140
    fb(PusherB_Ext=False, PusherB_Ret=True)                      # retracted, cell still there
    s = _run(fb, 3200)
    assert s.Alarms.TransportTimeout and s.State == ABORTED
