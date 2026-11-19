"""tools/block_versions.py - the CI rule "every change to a block needs a new block version".

Test design (cause-effect over: what changed x how the version changed)
| ID | Change made to FC_GradeCell          | Version change | Expected                      |
|----|--------------------------------------|----------------|-------------------------------|
| E1 | nothing                              | none           | no error                      |
| E2 | comment only                         | none           | no error (comments ignored)   |
| E3 | code (body)                          | none           | error "code changed"          |
| E4 | code (body)                          | minor 1.0->1.1 | ok, listed as BUMPED          |
| E5 | interface (new input)                | minor 1.0->1.1 | error "INTERFACE changed"     |
| E6 | interface (new input)                | major 1.0->2.0 | ok                            |
| E7 | nothing                              | 1.0 -> 0.9     | error "lower than released"   |
| B1 | version outside TIA range            | 16.0           | ValueError                    |
"""
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import block_versions as bv  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
FC_HEADER = 'FUNCTION "FC_GradeCell" : Int\n{ S7_Optimized_Access := \'TRUE\' }\nVERSION : 1.0'


@pytest.fixture
def work(tmp_path):
    for f in bv.SOURCES:
        shutil.copy(SRC / f, tmp_path / f)
    released = bv.parse_blocks(tmp_path)
    return tmp_path, released


def edit(folder, old, new):
    path = folder / "02_Blocks.scl"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"test setup: {old!r} not found"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def errors_after(folder, released):
    return bv.compare(bv.parse_blocks(folder), released)


def test_E1_no_change(work):
    folder, released = work
    assert errors_after(folder, released)[0] == []


def test_E2_comment_only_needs_no_bump(work):
    folder, released = work
    edit(folder, "// Classifies one battery cell", "// Grades one battery cell (comment edited)")
    assert errors_after(folder, released)[0] == []


def test_E3_code_change_without_bump_fails(work):
    folder, released = work
    edit(folder, "#FC_GradeCell := #GRADE_B;", "#FC_GradeCell := #GRADE_A;")
    errors, _ = errors_after(folder, released)
    assert len(errors) == 1 and "FC_GradeCell: code changed" in errors[0]


def test_E4_code_change_with_minor_bump_ok(work):
    folder, released = work
    edit(folder, "#FC_GradeCell := #GRADE_B;", "#FC_GradeCell := #GRADE_A;")
    edit(folder, FC_HEADER, FC_HEADER.replace("1.0", "1.1"))
    errors, notes = errors_after(folder, released)
    assert errors == [] and any("BUMPED   FC_GradeCell 1.0 -> 1.1" in n for n in notes)


def test_E5_interface_change_with_minor_bump_fails(work):
    folder, released = work
    edit(folder, "      Limits : \"UDT_GradeLimits\";\n   END_VAR",
         "      Limits : \"UDT_GradeLimits\";\n      Strict : Bool;\n   END_VAR")
    edit(folder, FC_HEADER, FC_HEADER.replace("1.0", "1.1"))
    errors, _ = errors_after(folder, released)
    assert any("FC_GradeCell: INTERFACE changed" in e for e in errors)


def test_E6_interface_change_with_major_bump_ok(work):
    folder, released = work
    edit(folder, "      Limits : \"UDT_GradeLimits\";\n   END_VAR",
         "      Limits : \"UDT_GradeLimits\";\n      Strict : Bool;\n   END_VAR")
    edit(folder, FC_HEADER, FC_HEADER.replace("1.0", "2.0"))
    assert errors_after(folder, released)[0] == []


def test_E7_version_decrease_fails(work):
    folder, released = work
    edit(folder, FC_HEADER, FC_HEADER.replace("1.0", "0.9"))
    errors, _ = errors_after(folder, released)
    assert any("lower than released" in e for e in errors)


def test_B1_version_outside_tia_range_rejected(work):
    folder, _ = work
    edit(folder, FC_HEADER, FC_HEADER.replace("1.0", "16.0"))
    with pytest.raises(ValueError, match="outside 0.0..15.15"):
        bv.parse_blocks(folder)
