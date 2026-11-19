"""Fidelity of the test runtime itself (tests/scl_runtime.py) - integer data types.

S7-1500 rule modelled: integer variables wrap (two's complement) when a result outside the
range is assigned; an implicit Real/Bool -> integer conversion is a compile error in TIA.

| ID | Technique        | Input                                   | Expected                  |
|----|------------------|-----------------------------------------|---------------------------|
| B1 | BVT Int max      | 32767                                   | 32767                     |
| B2 | BVT Int max+     | 32768                                   | -32768                    |
| B3 | BVT Int min-     | -32769                                  | 32767                     |
| B4 | BVT DInt max+    | 2147483648                              | -2147483648               |
| B5 | BVT UInt min-    | -1                                      | 65535                     |
| B6 | BVT Word max+    | 16#10000                                | 0                         |
| I1 | ECT invalid      | Real assigned to Int                    | SclError                  |
| I2 | ECT invalid      | Bool assigned to Int                    | SclError                  |
| G1 | SCL end-to-end   | Int static incremented past 32767       | -32768 (wraps, no crash)  |
| G2 | SCL end-to-end   | DInt static incremented past 2^31-1     | -2^31                     |
"""
import pytest

from scl_runtime import Plc, SclError, wrap_int

SRC = """
FUNCTION_BLOCK "FB_Wrap"
VERSION : 1.0
   VAR_INPUT
      Step : Int;
   END_VAR
   VAR
      I : Int;
      D : DInt;
      R : Real;
   END_VAR
BEGIN
   #I := #I + #Step;
   #D := #D + #Step;
END_FUNCTION_BLOCK

FUNCTION_BLOCK "FB_BadReal"
VERSION : 1.0
   VAR
      I : Int;
      R : Real;
   END_VAR
BEGIN
   #R := 1.5;
   #I := #R;
END_FUNCTION_BLOCK
"""


@pytest.mark.parametrize("dtype, value, expected", [
    ("INT", 32767, 32767),                    # B1
    ("INT", 32768, -32768),                   # B2
    ("INT", -32769, 32767),                   # B3
    ("DINT", 2147483648, -2147483648),        # B4
    ("UINT", -1, 65535),                      # B5
    ("WORD", 0x10000, 0),                     # B6
])
def test_B_integer_wrap_boundaries(dtype, value, expected):
    assert wrap_int(dtype, value) == expected


def test_I1_real_to_int_rejected():
    with pytest.raises(SclError, match="type mismatch"):
        wrap_int("INT", 1.5)


def test_I2_bool_to_int_rejected():
    with pytest.raises(SclError, match="type mismatch"):
        wrap_int("INT", True)


@pytest.fixture
def plc(tmp_path):
    path = tmp_path / "wrap.scl"
    path.write_text(SRC, encoding="utf-8")
    return Plc(str(path))


def test_G1_int_static_wraps_in_scl(plc):
    inst = plc.new_instance("FB_Wrap")
    inst.I = 32760
    plc.call_fb(inst, Step=10)
    assert inst.I == -32766


def test_G2_dint_static_wraps_in_scl(plc):
    inst = plc.new_instance("FB_Wrap")
    inst.D = 2147483647
    plc.call_fb(inst, Step=1)
    assert inst.D == -2147483648


def test_I3_real_assigned_to_int_in_scl_raises(plc):
    with pytest.raises(SclError, match="type mismatch"):
        plc.call_fb(plc.new_instance("FB_BadReal"))
