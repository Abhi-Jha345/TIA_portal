"""FB_DualChannel / FB_SafetyMonitor - safety functions SF1 (E-stop) and SF2 (guard door).

Specification (safety concept, ISO 13849-1, IEC 60204-1, ISO 13850, ISO 14119):
  R1  two-channel NC inputs; machine released only if both channels closed
  R2  channels disagreeing >= 500 ms -> latched discrepancy fault; clear only after both
      channels were open together AND a reset
  R3  E-stop -> stop category 0: EnergyEnable FALSE in the same scan
  R4  guard door -> stop category 1: EnergyEnable stays for Cat1Delay (1 s), then FALSE
  R5  manual reset only on RELEASE of the reset button (falling edge)
  R6  reset button held >= 5 s is treated as stuck: its release does not reset
  R7  no automatic restart: after power-up and after every trip a manual reset is needed
  R8  reset is ignored while a safety circuit is still open

Test design
| ID  | Technique   | Req | Stimulus                                   | Expected                        |
|-----|-------------|-----|--------------------------------------------|---------------------------------|
| S1  | STT         | R7  | power-up, circuits closed, no reset        | SafetyOk F, ResetRequired T     |
| S2  | STT         | R5  | reset pressed (not yet released)           | SafetyOk F                      |
| S3  | STT         | R5  | reset released                             | SafetyOk T, EnergyEnable T      |
| S4  | STT         | R3  | E-stop pressed                             | Cat0, Energy F same scan        |
| S5  | STT         | R7  | E-stop released, no reset                  | SafetyOk F, ResetRequired T     |
| S6  | STT invalid | R8  | reset while E-stop pressed                 | SafetyOk F                      |
| B1  | BVT time    | R4  | door open + 990 ms                         | Energy T (controlled stop)      |
| B2  | BVT time    | R4  | door open + 1000 ms                        | Energy F                        |
| B3  | BVT time    | R6  | reset held 4990 ms then released           | SafetyOk T                      |
| B4  | BVT time    | R6  | reset held 5000 ms then released           | SafetyOk F, ResetStuck seen     |
| B5  | BVT time    | R2  | channels differ 490 ms                     | no discrepancy                  |
| B6  | BVT time    | R2  | channels differ 500 ms                     | Discrepancy latched             |
| S7  | STT         | R2  | discrepancy, close both, reset             | still latched, SafetyOk F       |
| S8  | STT         | R2  | open both, reset, close both, reset        | cleared, SafetyOk T             |
| E1  | Cause-eff.  | R1  | only channel A of the door opens (< 500 ms)| SafetyOk F (one channel enough) |
"""
import pytest

SCAN = 10


class Monitor:
    def __init__(self, plc):
        self.plc = plc
        self.fb = plc.new_instance("FB_SafetyMonitor")
        self.inputs = dict(EStop_A=True, EStop_B=True, Door_A=True, Door_B=True, ResetPB=False)
        self.scan()

    def scan(self, **changes):
        self.inputs.update(changes)
        self.plc.call_fb(self.fb, dt_ms=SCAN, **self.inputs)
        return self.fb

    def run(self, ms, **changes):
        """Apply the change in one scan, then let exactly `ms` elapse."""
        self.scan(**changes)
        for _ in range(ms // SCAN):
            self.scan()
        return self.fb

    def reset(self, hold_ms=100):
        self.run(hold_ms, ResetPB=True)
        return self.scan(ResetPB=False)


@pytest.fixture
def mon(plc):
    return Monitor(plc)


@pytest.fixture
def released(mon):
    mon.reset()
    assert mon.fb.SafetyOk
    return mon


def test_S1_no_automatic_start_after_power_up(mon):
    fb = mon.run(1000)
    assert (fb.SafetyOk, fb.ResetRequired, fb.EnergyEnable) == (False, True, False)


def test_S2_reset_pressed_but_not_released(mon):
    fb = mon.run(200, ResetPB=True)
    assert fb.SafetyOk is False


def test_S3_reset_on_release_releases_machine(mon):
    fb = mon.reset()
    assert (fb.SafetyOk, fb.EnergyEnable, fb.ResetRequired) == (True, True, False)


def test_S4_estop_is_stop_category_0(released):
    fb = released.scan(EStop_A=False, EStop_B=False)
    assert (fb.StopCat0, fb.EnergyEnable, fb.SafetyOk) == (True, False, False)


def test_S5_no_restart_after_estop_release(released):
    released.scan(EStop_A=False, EStop_B=False)
    fb = released.run(500, EStop_A=True, EStop_B=True)
    assert (fb.SafetyOk, fb.ResetRequired, fb.EnergyEnable) == (False, True, False)


def test_S6_reset_ignored_while_estop_pressed(released):
    released.scan(EStop_A=False, EStop_B=False)
    released.reset()
    fb = released.scan(EStop_A=True, EStop_B=True)
    assert fb.SafetyOk is False


def test_B1_door_controlled_stop_keeps_energy_before_delay(released):
    released.scan(Door_A=False, Door_B=False)
    fb = released.run(980)
    assert (fb.StopCat1, fb.SafetyOk, fb.EnergyEnable) == (True, False, True)


def test_B2_door_energy_removed_at_delay(released):
    released.scan(Door_A=False, Door_B=False)
    released.run(980)
    fb = released.run(20)
    assert fb.EnergyEnable is False


def test_B3_reset_held_just_below_stuck_time_works(mon):
    fb = mon.reset(hold_ms=4990)
    assert fb.SafetyOk is True


def test_B4_stuck_reset_button_does_not_reset(mon):
    mon.run(5000, ResetPB=True)
    assert mon.fb.ResetStuck is True
    fb = mon.scan(ResetPB=False)
    assert fb.SafetyOk is False


def test_B5_short_channel_difference_is_not_a_discrepancy(released):
    released.run(490, EStop_A=False)
    fb = released.scan(EStop_A=True)
    assert fb.Discrepancy is False


def test_B6_discrepancy_latched_at_500ms(released):
    fb = released.run(500, EStop_A=False)
    assert fb.Discrepancy is True


def test_S7_discrepancy_needs_both_channels_open_before_ack(released):
    released.run(600, EStop_A=False)
    released.scan(EStop_A=True)
    fb = released.reset()
    assert (fb.Discrepancy, fb.SafetyOk) == (True, False)


def test_S8_discrepancy_cleared_after_both_open_and_reset(released):
    released.run(600, EStop_A=False)
    released.scan(EStop_B=False)          # both open now
    released.reset()                      # acknowledges the discrepancy
    released.scan(EStop_A=True, EStop_B=True)
    fb = released.reset()                 # normal reset
    assert (fb.Discrepancy, fb.SafetyOk) == (False, True)


def test_E1_one_door_channel_is_enough_to_stop(released):
    fb = released.scan(Door_A=False)
    assert fb.SafetyOk is False and fb.StopCat1 is True
