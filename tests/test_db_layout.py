"""tools/db_layout.py - S7 standard (non-optimized) DB layout and the HMI address check.

| ID | Technique           | Input                                         | Expected                         |
|----|---------------------|-----------------------------------------------|----------------------------------|
| R1 | rule: Bool packing  | 9 Bools                                       | 0.0 .. 0.7, 1.0                  |
| R2 | rule: even align    | Bool, Int                                     | Int at byte 2                    |
| R3 | rule: byte no align | Bool, Byte                                    | Byte at byte 1                   |
| R4 | rule: struct pad    | Struct{Bool}, Byte                            | Byte at 2 (struct size 2)        |
| R5 | rule: String[n]     | String[24], Int                               | Int at 26 (24 + 2 bytes)         |
| R6 | rule: unsupported   | Array                                         | ValueError                       |
| V1 | reference values    | real DB_HMI                                   | = addresses verified in TIA V20  |
| C1 | check: consistent   | repo hmi_tags.json                            | no error                         |
| C2 | check: shifted DB   | member inserted before Sts in DB_HMI          | address errors                   |
| C3 | check: wrong type   | Real tag bound to an Int member               | type error                       |
| C4 | check: bad member   | tag member that does not exist                | member error                     |
| C5 | check: screen tag   | screen binds a tag not in hmi_tags.json       | error                            |
"""
import json
import pathlib
import shutil
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import db_layout as dl  # noqa: E402


def lay(decl, udts=""):
    src = f"{udts}\nDATA_BLOCK \"DB_T\"\nVERSION : 1.0\n   VAR\n{decl}\n   END_VAR\nBEGIN\nEND_DATA_BLOCK\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "layout.scl"
        path.write_text(src, encoding="utf-8")
        udt_map, dbs = dl.parse_declarations([path])
    return {k: (b, bit) for k, (_t, b, bit) in dl.layout(dbs["DB_T"], udt_map).items()}


def test_R1_bools_share_bytes():
    out = lay("\n".join(f"B{i} : Bool;" for i in range(9)))
    assert out["B7"] == (0, 7) and out["B8"] == (1, 0)


def test_R2_int_aligns_to_even_byte():
    assert lay("A : Bool;\nN : Int;")["N"] == (2, 0)


def test_R3_byte_is_not_aligned():
    assert lay("A : Bool;\nX : Byte;")["X"] == (1, 0)


def test_R4_struct_size_rounded_to_even():
    assert lay("S : Struct\n A : Bool;\nEND_STRUCT;\nX : Byte;")["X"] == (2, 0)


def test_R5_string_takes_n_plus_2_bytes():
    out = lay("T : String[24];\nN : Int;")
    assert out["T"] == (0, 0) and out["N"] == (26, 0)


def test_R6_array_rejected():
    with pytest.raises(ValueError, match="arrays"):
        lay("A : Array[0..3] of Int;")


def test_V1_db_hmi_matches_addresses_verified_in_tia():
    udts, dbs = dl.parse_declarations()
    out = dl.layout(dbs["DB_HMI"], udts)
    verified = {"Cmd.SimDiscrepancy": "%DB1.DBX1.1", "Sts.State": "%DB1.DBW28",
                "Sts.StateText": "%DB1.DBX30.0", "Sts.ResetRequired": "%DB1.DBX59.1",
                "Sts.Alarms.SafetyDiscrepancy": "%DB1.DBX61.0", "Sts.Counters.Total": "%DB1.DBD62",
                "Sts.Counters.Yield_pct": "%DB1.DBD78", "Sts.BinR_Count": "%DB1.DBW98"}
    assert {m: dl.address(1, *out[m]) for m in verified} == verified


@pytest.fixture
def work(tmp_path):
    for f in ("01_Types.scl", "02_Blocks.scl"):
        shutil.copy(ROOT / "src" / f, tmp_path / f)
    shutil.copy(ROOT / "hmi" / "hmi_tags.json", tmp_path / "tags.json")
    shutil.copy(ROOT / "hmi" / "overview_bindings.json", tmp_path / "bind.json")
    return tmp_path


def run_check(d):
    return dl.check(d / "tags.json", d / "bind.json", [d / "01_Types.scl", d / "02_Blocks.scl"])


def edit_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_C1_repository_is_consistent(work):
    assert run_check(work) == []


def test_C2_inserted_member_shifts_addresses(work):
    path = work / "02_Blocks.scl"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("      Sts : Struct\n", "      Spare : Int;\n      Sts : Struct\n", 1),
                    encoding="utf-8")
    errors = run_check(work)
    assert any("Sts_State: address %DB1.DBW28 but Sts.State is at %DB1.DBW30" in e for e in errors)


def test_C3_type_mismatch_detected(work):
    def wrong(d):
        next(t for t in d["tags"] if t["name"] == "Sts_State")["type"] = "Real"
    edit_json(work / "tags.json", wrong)
    assert any("Sts_State: HMI type Real" in e for e in run_check(work))


def test_C4_unknown_member_detected(work):
    edit_json(work / "tags.json", lambda d: d["tags"][0].update(member="Cmd.Nope"))
    assert any("does not exist" in e for e in run_check(work))


def test_C5_screen_binding_to_unknown_tag_detected(work):
    edit_json(work / "bind.json", lambda d: d["ioValues"].append({"item": "x", "tag": "Ghost"}))
    assert "screen binds unknown HMI tag Ghost" in run_check(work)
