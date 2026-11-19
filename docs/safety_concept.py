"""Safety concept for the battery cell sorting station (A4 portrait, 2 pages)."""
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)

OUT = sys.argv[1]
INK, MUTED, ACCENT, RULE = HexColor("#1d2733"), HexColor("#5b6773"), HexColor("#0b6e8a"), HexColor("#c9d3db")
FAULT = HexColor("#b3261e")

h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)
sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED)
h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=ACCENT,
                    spaceBefore=7, spaceAfter=3)
body = ParagraphStyle("body", fontName="Helvetica", fontSize=8, leading=10.3, textColor=INK)
cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.2, leading=8.8, textColor=INK)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
note = ParagraphStyle("note", parent=body, fontSize=7.4, leading=9.4, textColor=MUTED)


def P(t, s=cell):
    return Paragraph(t, s)


def table(rows, widths, head=True):
    data = [[P(c, cellb if (head and i == 0) else cell) if isinstance(c, str) else c for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), ACCENT)]
        for j in range(len(rows[0])):
            data[0][j].style = ParagraphStyle("hw", parent=cellb, textColor=white)
    t.setStyle(TableStyle(st))
    return t


story = [
    Paragraph("Safety Concept - Battery Cell Test &amp; Sort Station", h1),
    Paragraph("Pilot project | basis: Machinery Regulation (EU) 2023/1230 (replaces 2006/42/EC from Jan 2027), "
              "ISO 12100, ISO 13849-1/-2, IEC 60204-1, ISO 13850, ISO 14119, ISO 14118 | status: concept, "
              "values to be confirmed with SISTEMA and manufacturer data", sub),
    Spacer(1, 4),

    Paragraph("1  Scope and limits of the machine (ISO 12100, 5.3)", h2),
    Paragraph("Station in a battery cell production line: conveyor, measuring station (voltage / internal "
              "resistance), two pneumatic pushers (bin B, reject bin). Automatic operation behind a fixed guard "
              "with one interlocked access door for jam clearing and bin exchange. Operators: trained line "
              "operators and maintenance staff. Foreseeable misuse: reaching through the open door while "
              "the station runs, bridging the door switch, holding the reset button down.", body),

    Paragraph("2  Risk assessment (ISO 12100, 5.4 - 5.6)", h2),
    table([
        ["ID", "Hazard (zone / task)", "Consequence", "Risk reduction (3-step method, ISO 12100 6.1)"],
        ["H1", "Crushing / shearing by pusher B or R (sorting station / jam clearing)",
         "finger / hand injury, irreversible", "1) limited pusher force and stroke, 2) fixed guard + interlocked "
         "door SF2, E-stop SF1, 3) warning label, instruction"],
        ["H2", "Drawing-in at conveyor drive and return pulley (infeed / cleaning)",
         "hand drawn in", "1) guarded pulleys, 2) SF2, SF1, STO of the conveyor drive"],
        ["H3", "Unexpected start-up during intervention (jam clearing)",
         "as H1 / H2", "manual reset outside the hazard zone, no automatic restart (SF3, ISO 14118)"],
        ["H4", "Stored pneumatic energy after a stop", "pusher moves after stop",
         "two-channel dump valve exhausts the pushers (part of SF1 / SF2)"],
        ["H5", "Short circuit of a cell at the measuring contacts", "arc, heat, cell fire",
         "1) current-limited measuring unit, 2) plausibility check: R &lt;= 0 or V &lt;= 0 is rejected "
         "(FC_GradeCell, found by unit test), 3) fire-safe reject bin (process measure, not a SF)"],
    ], [9, 52, 30, 89]),

    Paragraph("3  Safety functions and required performance level (ISO 13849-1, risk graph Annex A)", h2),
    table([
        ["SF", "Safety function", "Trigger / reaction", "S", "F", "P", "PLr"],
        ["SF1", "Emergency stop (complementary protective measure, ISO 13850)",
         "E-stop pressed: stop category 0 (IEC 60204-1 9.2.2): STO conveyor drive and dump valve "
         "immediately", "S2", "F1", "P2", "d"],
        ["SF2", "Guard door interlock (ISO 14119, type 2, two-channel)",
         "door opened: stop category 1: pushers retract, conveyor stops, energy removed after 1 s",
         "S2", "F2", "P1", "d"],
        ["SF3", "Manual reset / prevention of unexpected start-up (ISO 13849-1 5.2.2, ISO 14118)",
         "reset only on release of a hard-wired button outside the hazard zone; stuck button ignored; "
         "no restart after power-up; machine start needs a separate Start", "-", "-", "-", "d*"],
    ], [10, 45, 92, 7, 7, 7, 12]),
    Paragraph("S2 = serious, irreversible injury; F1 / F2 = seldom / frequent exposure (door is opened for every "
              "jam); P1 / P2 = avoidance possible / scarcely possible. *SF3 is part of SF1 / SF2 and realised "
              "in the same safety channel, therefore same PL.", note),

    Paragraph("4  Architecture and PL verification (ISO 13849-1, 6.2 / Annex K)", h2),
    table([
        ["Subsystem", "Realisation", "Cat.", "MTTFd", "DCavg", "CCF"],
        ["Input SF1", "E-stop, 2 NC contacts with direct opening (ISO 13850), F-DI with test pulses: "
         "discrepancy and cross-circuit detection", "3", "high", "medium (&gt;= 90 %), conservative", "&gt;= 65"],
        ["Input SF2", "door switch with separate actuator, 2 channels (ISO 14119), coded actuator against "
         "bridging, F-DI", "3", "high", "medium", "&gt;= 65"],
        ["Logic", "F-CPU (e.g. CPU 1516F) running STEP 7 Safety: ESTOP1, SFDOOR, FDBACK, ACK_GL",
         "-", "certified up to PL e / SIL 3", "-", "-"],
        ["Output", "F-DQ: STO of the conveyor drive (PROFIsafe) + redundant dump valve with "
         "position feedback (FDBACK)", "3", "high", "medium", "&gt;= 65"],
    ], [20, 92, 10, 22, 22, 14]),
    Paragraph("Result: every subsystem in category 3 with MTTFd high and DCavg medium reaches at least "
              "PL d, so PL &gt;= PLr for SF1 - SF3. The combined PL has to be calculated with SISTEMA using "
              "the manufacturers' B10d / PFHd values before release.", body),

    PageBreak(),
    Paragraph("5  Implementation in this project", h2),
    Paragraph("The safety functions belong in the F-program of an F-CPU. This pilot uses a standard "
              "CPU 1516-3 PN/DP, so the behaviour of SF1 - SF3 is implemented as a <b>standard-PLC mirror</b> "
              "(FB_SafetyMonitor, FB_DualChannel). It drives the operating logic, diagnostics, the HMI and the "
              "unit tests, and it is the executable specification for the F-program. It does <b>not</b> "
              "replace it.", body),
    Spacer(1, 3),
    table([
        ["Requirement", "Standard", "Where in the code"],
        ["Two-channel input evaluation, discrepancy time 500 ms, fault latched until both channels "
         "were open (proves both contacts switch)", "ISO 13849-1 cat. 3, ISO 13849-2",
         "FB_DualChannel"],
        ["E-stop: energy off in the same scan", "IEC 60204-1 stop cat. 0, ISO 13850",
         "FB_SafetyMonitor.Stop_categories"],
        ["Door: controlled stop, energy off after Cat1Delay = 1 s", "IEC 60204-1 stop cat. 1",
         "FB_SafetyMonitor.Stop_categories"],
        ["Reset on falling edge only, stuck button (&gt; 5 s) ignored, edge memory starts FALSE",
         "ISO 13849-1 5.2.2", "FB_SafetyMonitor.Reset_button"],
        ["No automatic start after power-up or after a trip; machine Start is a separate command",
         "IEC 60204-1 7.5, ISO 14118", "FB_SafetyMonitor.Release, FB_SortStation"],
        ["Any fault forces ABORTED and all actuators off in the same scan",
         "safe state (IEC 60204-1 9.4)", "FB_SortStation.Fault_reaction, FC_AnyFault"],
        ["Monostable valves: de-energised = retracted", "ISO 4414 (pneumatics), ISO 13849-2 Annex B",
         "FB_Cylinder"],
    ], [92, 45, 43]),

    Paragraph("6  Verification and validation (ISO 13849-2)", h2),
    Paragraph("<b>Verification of the logic (done):</b> 76 automated unit tests execute the real SCL "
              "source (01_Types.scl, 02_Blocks.scl, 03_OB.scl) in a scan-based test runtime; SCL decision "
              "coverage 114 / 115 = 99.1 % (the remaining outcome is unreachable defensive code). "
              "Safety-related tests:", body),
    Spacer(1, 2),
    table([
        ["SF", "Test IDs (tests/)", "What is proven"],
        ["SF1", "test_fb_safety S4, S5, S6; test_station U4, U5",
         "cat. 0 in the same scan; no restart after release; reset ignored while pressed"],
        ["SF2", "test_fb_safety B1, B2, E1; test_station U6",
         "energy kept 990 ms, removed at 1000 ms; one channel is enough to stop"],
        ["SF3", "test_fb_safety S1 - S3, B3, B4; test_station S1, S3",
         "no start after power-up; reset only on release; stuck button ignored"],
        ["Cat. 3", "test_fb_safety B5, B6, S7, S8; test_station U9",
         "490 ms no fault / 500 ms fault; fault cleared only after both channels opened"],
    ], [12, 70, 98]),
    Spacer(1, 3),
    Paragraph("<b>Defects found by the tests and fixed before release:</b> (1) R = 0 / negative resistance "
              "was graded A (short-circuited cell shipped); (2) cylinder valve dropped one scan after its "
              "fault; (3) step and cylinder faults switched the station to ABORTED one scan late.", body),
    Spacer(1, 3),
    Paragraph("<b>Validation on the machine (open, ISO 13849-2 fault list):</b> functional test of each SF; "
              "fault insertion: wire break and cross circuit per channel, welded E-stop contact, bridged door "
              "switch (coded actuator), dump valve stuck (feedback); stopping time measurement for the door "
              "(ISO 13855 safety distance); check of the F-parameters and the safety signature; "
              "documentation in the validation report and technical file.", body),

    Paragraph("7  Open points before CE marking", h2),
    Paragraph("Replace the standard CPU with an F-CPU and program SF1 - SF3 with certified F-blocks; select "
              "F-I/O and safety components and run SISTEMA; measure stopping times and fix the safety "
              "distance; complete the validation report, operating instructions and technical file; "
              "EU declaration of conformity.", body),
]

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                        topMargin=13 * mm, bottomMargin=12 * mm,
                        title="Safety Concept - Battery Cell Sorting Station")
doc.build(story)
print("written", OUT)
