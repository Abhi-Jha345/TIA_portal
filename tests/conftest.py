"""Shared fixtures for the SCL unit tests.

Every test gets a fresh PLC loaded from the real external sources in ../src, so the code
under test is byte-for-byte the code that is imported into TIA Portal.
"""
import os

import pytest

from scl_runtime import COVERAGE, Plc

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
SOURCES = [os.path.join(SRC, f) for f in ("01_Types.scl", "02_Blocks.scl", "03_OB.scl")]
SCAN_MS = 10


@pytest.fixture
def plc():
    return Plc(*SOURCES)


class Station:
    """Operator-level driver for the whole program (OB -> FB_CellSortingMain)."""

    def __init__(self, plc):
        self.plc = plc
        self.hmi = plc.db("DB_HMI")

    @property
    def sts(self):
        return self.hmi.Sts

    def run(self, ms):
        for _ in range(max(1, ms // SCAN_MS)):
            self.plc.scan(SCAN_MS)

    def run_until(self, predicate, timeout_ms=20000):
        waited = 0
        while not predicate():
            if waited >= timeout_ms:
                raise AssertionError(f"condition not reached within {timeout_ms} ms "
                                     f"(state text: {self.sts.StateText!r})")
            self.plc.scan(SCAN_MS)
            waited += SCAN_MS
        return waited

    def press(self, cmd):
        """HMI one-shot command: the PLC clears it after one scan."""
        setattr(self.hmi.Cmd, cmd, True)
        self.plc.scan(SCAN_MS)

    def hold(self, cmd, value=True):
        setattr(self.hmi.Cmd, cmd, value)
        self.plc.scan(SCAN_MS)

    def safety_reset(self, hold_ms=200):
        """Press and RELEASE the hard-wired safety reset button."""
        self.hmi.Cmd.SimResetPB = True
        self.run(hold_ms)
        self.hmi.Cmd.SimResetPB = False
        self.plc.scan(SCAN_MS)

    def bring_to_idle(self):
        self.safety_reset()
        self.press("Reset")
        self.run_until(lambda: self.sts.State == 20, 5000)

    def start_production(self):
        self.bring_to_idle()
        self.press("Start")
        assert self.sts.State == 30


@pytest.fixture
def station(plc):
    return Station(plc)


MIN_COVERAGE = float(os.environ.get("SCL_MIN_COVERAGE", "95"))
REPORT = os.environ.get("SCL_COVERAGE_REPORT", "")


def _coverage():
    points = COVERAGE["points"]
    hit = COVERAGE["hit"] & set(points)
    missed = sorted(set(points) - hit, key=lambda k: (k[0], k[1], str(k[2])))
    pct = 100.0 * len(hit) / len(points) if points else 0.0
    return points, hit, missed, pct


def pytest_sessionfinish(session, exitstatus):
    """Quality gate for CI: fail the run if SCL decision coverage drops below the minimum."""
    points, hit, missed, pct = _coverage()
    if not points:
        return
    if REPORT:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write(f"## SCL decision coverage: {len(hit)} / {len(points)} = {pct:.1f} % "
                    f"(minimum {MIN_COVERAGE:.0f} %)\n\n")
            for key in missed:
                f.write(f"- not covered: `{key[0]}` {points[key]}\n")
    if pct < MIN_COVERAGE and exitstatus == 0:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    points, hit, missed, pct = _coverage()
    if not points:
        return
    tr = terminalreporter
    tr.section("SCL decision coverage (IF branches + implicit ELSE, CASE labels + ELSE)")
    tr.write_line(f"{len(hit)} / {len(points)} decision outcomes executed = {pct:.1f} % "
                  f"(gate: >= {MIN_COVERAGE:.0f} %{'' if pct >= MIN_COVERAGE else '  -> FAILED'})")
    for key in missed:
        tr.write_line(f"  not covered: {key[0]}  {points[key]}")
