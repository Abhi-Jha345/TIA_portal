"""FC_GradeCell - grading of one battery cell.

Specification (oracle, from the design sheet / UDT_GradeLimits defaults):
  A      : 3.60 V <= V <= 3.70 V  and  R <= 18 mOhm
  B      : not A, 3.55 V <= V <= 3.75 V  and  R <= 25 mOhm
  Reject : everything else, INCLUDING implausible measurements (V <= 0 or R <= 0),
           which indicate a contact / measuring fault and must never pass as a good cell.
Inputs V and R are not independent (the grade depends on both) -> boundary tests vary one
variable with the other held at a nominal value of the class under test, plus a decision
table over the combinations.

Test design
| ID     | Technique              | Covers                         | Input (V, R)       | Expected |
|--------|------------------------|--------------------------------|--------------------|----------|
| B1-B13 | Robust BVT on V        | B min-..max+, A min-..max+     | V varies, R=15     | see table|
| B14-20 | Robust BVT on R        | A max-..max+, B max-..max+     | V=3.65, R varies   | see table|
| E1-E6  | Cause-effect columns   | (V class) x (R class)          | one per column     | see table|
| I1-I4  | Invalid input ECT      | implausible measurement        | V<=0 or R<=0       | Reject   |
| O1-O3  | Output EC              | each grade once                | nominal            | 1 / 2 / 3|
"""
import pytest

A, B, REJECT = 1, 2, 3


@pytest.fixture
def grade(plc):
    limits = plc.make_value(("named", "UDT_GradeLimits"))

    def _grade(v, r):
        return plc.call_fc("FC_GradeCell", Voltage_V=v, Resistance_mOhm=r, Limits=limits)
    return _grade


@pytest.mark.parametrize("tid, v, expected", [
    ("B1 B-min-", 3.549, REJECT), ("B2 B-min", 3.55, B), ("B3 B-min+", 3.551, B),
    ("B4 A-min-", 3.599, B), ("B5 A-min", 3.60, A), ("B6 A-min+", 3.601, A),
    ("B7 nom", 3.65, A),
    ("B8 A-max-", 3.699, A), ("B9 A-max", 3.70, A), ("B10 A-max+", 3.701, B),
    ("B11 B-max-", 3.749, B), ("B12 B-max", 3.75, B), ("B13 B-max+", 3.751, REJECT),
])
def test_B_boundary_voltage(grade, tid, v, expected):
    assert grade(v, 15.0) == expected, tid


@pytest.mark.parametrize("tid, r, expected", [
    ("B14 A-max-", 17.999, A), ("B15 A-max", 18.0, A), ("B16 A-max+", 18.001, B),
    ("B17 B-max-", 24.999, B), ("B18 B-max", 25.0, B), ("B19 B-max+", 25.001, REJECT),
    ("B20 R min (smallest plausible)", 0.001, A),
    ("B21 R min- (zero)", 0.0, REJECT),
])
def test_B_boundary_resistance(grade, tid, r, expected):
    assert grade(3.65, r) == expected, tid


@pytest.mark.parametrize("tid, v, r, expected", [
    ("E1 V in A, R in A", 3.65, 15.0, A),
    ("E2 V in A, R only in B", 3.65, 22.0, B),
    ("E3 V only in B, R in A", 3.58, 15.0, B),
    ("E4 V only in B, R only in B", 3.73, 22.0, B),
    ("E5 V in A, R too high", 3.65, 30.0, REJECT),
    ("E6 V too low (deep discharge), R in A", 3.20, 15.0, REJECT),
])
def test_E_cause_effect_columns(grade, tid, v, r, expected):
    assert grade(v, r) == expected, tid


@pytest.mark.parametrize("tid, v, r", [
    ("I1 R = 0 (short / contact fault)", 3.65, 0.0),
    ("I2 R negative", 3.65, -5.0),
    ("I3 V = 0 (no contact)", 0.0, 15.0),
    ("I4 V negative (reversed polarity)", -3.65, 15.0),
])
def test_I_implausible_measurement_is_rejected(grade, tid, v, r):
    assert grade(v, r) == REJECT, tid


@pytest.mark.parametrize("tid, v, r, expected", [
    ("O1", 3.65, 12.0, A), ("O2", 3.57, 20.0, B), ("O3", 3.40, 30.0, REJECT),
])
def test_O_each_output_class(grade, tid, v, r, expected):
    assert grade(v, r) == expected, tid
