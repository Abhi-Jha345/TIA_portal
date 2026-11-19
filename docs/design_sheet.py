"""One-page design sheet for the battery cell sorting station pilot (A4 landscape)."""
import sys
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

OUT = sys.argv[1]
W, H = landscape(A4)
M = 26
GAP = 16
CW = (W - 2 * M - 2 * GAP) / 3
C1, C2, C3 = M, M + CW + GAP, M + 2 * (CW + GAP)

INK = HexColor("#1d2733")
MUTED = HexColor("#5b6773")
ACCENT = HexColor("#0b6e8a")
FILL = HexColor("#e8f3f6")
FAULT = HexColor("#b3261e")
FAULTFILL = HexColor("#fbeaea")
RULE = HexColor("#c9d3db")

body = ParagraphStyle("body", fontName="Helvetica", fontSize=7.6, leading=9.6, textColor=INK)
small = ParagraphStyle("small", parent=body, fontSize=7.0, leading=8.6)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=8, bulletIndent=0, spaceAfter=1.5)

c = canvas.Canvas(OUT, pagesize=(W, H))
c.setTitle("Battery Cell Sorting Station - PLC Design Sheet")


def para(text, x, y, w, style=body):
    p = Paragraph(text, style)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, y - h)
    return y - h


def heading(num, text, x, y):
    y -= 8
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x, y, f"{num}  {text}" if num else text)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(x, y - 3, x + CW, y - 3)
    return y - 14


def box(cx, cy, w, h, label, sub=None, fault=False):
    c.setLineWidth(0.9)
    c.setStrokeColor(FAULT if fault else ACCENT)
    c.setFillColor(FAULTFILL if fault else FILL)
    c.roundRect(cx - w / 2, cy - h / 2, w, h, 3, stroke=1, fill=1)
    c.setFillColor(INK)
    if sub:
        c.setFont("Helvetica-Bold", 7.6)
        c.drawCentredString(cx, cy + 1.5, label)
        c.setFont("Helvetica", 6.6)
        c.setFillColor(MUTED)
        c.drawCentredString(cx, cy - 7, sub)
    else:
        c.setFont("Helvetica-Bold", 7.8)
        c.drawCentredString(cx, cy - 2.7, label)


def arrowhead(x, y, direction):
    s = 3.2
    p = c.beginPath()
    if direction == "down":
        p.moveTo(x, y); p.lineTo(x - s, y + s * 1.6); p.lineTo(x + s, y + s * 1.6)
    elif direction == "up":
        p.moveTo(x, y); p.lineTo(x - s, y - s * 1.6); p.lineTo(x + s, y - s * 1.6)
    elif direction == "left":
        p.moveTo(x, y); p.lineTo(x + s * 1.6, y - s); p.lineTo(x + s * 1.6, y + s)
    else:
        p.moveTo(x, y); p.lineTo(x - s * 1.6, y - s); p.lineTo(x - s * 1.6, y + s)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def poly_arrow(points, color=INK, dash=None, end="down"):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(0.8)
    if dash:
        c.setDash(*dash)
    p = c.beginPath()
    p.moveTo(*points[0])
    for pt in points[1:]:
        p.lineTo(*pt)
    c.drawPath(p, stroke=1, fill=0)
    c.setDash()
    arrowhead(points[-1][0], points[-1][1], end)


def label(x, y, text, color=MUTED, size=6.8, align="left"):
    c.setFillColor(color)
    c.setFont("Helvetica-Oblique", size)
    if align == "left":
        c.drawString(x, y, text)
    else:
        c.drawCentredString(x, y, text)


def table(data, x, y, widths, header_bg=ACCENT, fault_rows=()):
    t = Table(data, colWidths=widths)
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.0),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 6.9),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in fault_rows:
        style.append(("TEXTCOLOR", (1, r), (1, r), FAULT))
    t.setStyle(TableStyle(style))
    _, h = t.wrap(sum(widths), 1000)
    t.drawOn(c, x, y - h)
    return y - h


def P(text, style=small):
    return Paragraph(text, style)


# ---------------------------------------------------------------- header
c.setFillColor(INK)
c.setFont("Helvetica-Bold", 15)
c.drawString(M, H - M - 10, "Battery Cell Test & Sort Station")
c.setFont("Helvetica", 9)
c.setFillColor(MUTED)
c.drawString(M, H - M - 24,
             "PLC pilot project  |  SIMATIC S7-1500 (CPU 1516-3 PN/DP)  |  TIA Portal V20  |  SCL  |  WinCC Unified HMI")
c.setStrokeColor(ACCENT)
c.setLineWidth(1.4)
c.line(M, H - M - 31, W - M, H - M - 31)
top = H - M - 50

# ---------------------------------------------------------------- column 1
y = heading("1", "Process", C1, top)
y = para("Cells arrive on a conveyor at a <b>measuring station</b>. Open circuit voltage and internal "
         "resistance are measured, the cell is <b>graded A / B / Reject</b> and leaves the station: "
         "A continues on the conveyor to module assembly, B and Reject are pushed into bins by two "
         "pneumatic pushers. Throughput, yield and bin levels are tracked.", C1, y, CW) - 10

y = heading("2", "Mode state machine (PackML inspired)", C1, y)
bx, bw, bh = C1 + 92, 104, 19
ys = {"STOPPED": y - 14, "RESETTING": y - 54, "IDLE": y - 94, "EXECUTE": y - 134, "ABORTED": y - 184}
box(bx, ys["STOPPED"], bw, bh, "STOPPED")
box(bx, ys["RESETTING"], bw, bh, "RESETTING", "pushers to home")
box(bx, ys["IDLE"], bw, bh, "IDLE")
box(bx, ys["EXECUTE"], bw, bh, "EXECUTE", "step chain, see 3")
box(bx, ys["ABORTED"], bw, bh, "ABORTED", "all actuators off", fault=True)
for a, b, txt in (("STOPPED", "RESETTING", "Reset"), ("RESETTING", "IDLE", "both pushers retracted"),
                  ("IDLE", "EXECUTE", "Start")):
    poly_arrow([(bx, ys[a] - bh / 2), (bx, ys[b] + bh / 2)])
    label(bx + 5, (ys[a] + ys[b]) / 2 - 2, txt)
poly_arrow([(bx, ys["EXECUTE"] - bh / 2), (bx, ys["ABORTED"] + bh / 2)], color=FAULT, dash=(2, 2))
label(bx + 5, (ys["EXECUTE"] + ys["ABORTED"]) / 2 - 2, "any fault, from every state", color=FAULT)
r = bx + bw / 2
poly_arrow([(r, ys["EXECUTE"]), (r + 22, ys["EXECUTE"]), (r + 22, ys["IDLE"]), (r, ys["IDLE"])], end="left")
c.saveState()
c.translate(r + 29, ys["EXECUTE"] - 4)
c.rotate(90)
label(0, 0, "Stop: at end of cycle")
c.restoreState()
lft = bx - bw / 2
poly_arrow([(lft, ys["ABORTED"]), (lft - 22, ys["ABORTED"]), (lft - 22, ys["RESETTING"]),
            (lft, ys["RESETTING"])], color=FAULT, end="right")
c.saveState()
c.translate(lft - 26, ys["ABORTED"] + 6)
c.rotate(90)
label(0, 0, "Reset, E-stop OK, faults cleared", color=FAULT)
c.restoreState()
y = ys["ABORTED"] - bh / 2 - 16

y = heading("", "Grading rules (parameters in DB_HMI.Par)", C1, y)
y = table([["Grade", "Voltage [V]", "Ri [mOhm]", "Leaves via"],
           ["A", "3.60 - 3.70", "<= 18", "conveyor -> module assembly"],
           ["B", "3.55 - 3.75", "<= 25", "pusher B -> bin B"],
           ["Reject", "otherwise", "", "pusher R -> reject bin"]],
          C1, y, [34, 50, 42, CW - 126])

# ---------------------------------------------------------------- column 2
y = heading("3", "EXECUTE step chain", C2, top)
sx, sw, sh = C2 + 78, 132, 23
steps = [("100  WAIT_CELL", "conveyor ON"),
         ("110  MEASURE", "start measuring unit"),
         ("120  GRADE", "FC_GradeCell, counters"),
         ("130  EJECT", "A: conveyor ON  |  B / R: pusher out"),
         ("140  RETRACT", "pushers back, station empty")]
trans = ["cell at light barrier", "measurement done", "(one scan)", "B / R: pusher extended"]
sy = []
yy = y - 16
for i, (name, act) in enumerate(steps):
    box(sx, yy, sw, sh, name, act)
    sy.append(yy)
    if i < len(trans):
        poly_arrow([(sx, yy - sh / 2), (sx, yy - 44 + sh / 2)])
        label(sx + 5, yy - 24.5, trans[i])
    yy -= 44
# loop back from RETRACT and from EJECT (grade A) to WAIT_CELL
rx = sx + sw / 2
poly_arrow([(rx, sy[4]), (rx + 26, sy[4]), (rx + 26, sy[0]), (rx, sy[0])], end="left")
c.saveState()
c.translate(rx + 33, sy[4] + 2)
c.rotate(90)
label(0, 0, "pushers home and cell gone")
c.restoreState()
lx = sx - sw / 2
poly_arrow([(lx, sy[3]), (lx - 14, sy[3]), (lx - 14, sy[0]), (lx, sy[0])], end="right")
c.saveState()
c.translate(lx - 18, sy[3] + 2)
c.rotate(90)
label(0, 0, "A: cell left station")
c.restoreState()
y = sy[4] - sh / 2 - 14

y = para("<b>Supervision.</b> A step timer restarts on every step change. MEASURE, EJECT (A) and RETRACT "
         "raise a fault after 3 s; pushers are watched by their own FB (2 s). "
         "<b>Stop</b> sets a flag that is only acted on in WAIT_CELL, so a cell is never left half sorted. "
         "<b>Bin full</b> holds the chain in WAIT_CELL until the operator confirms the bins were emptied.",
         C2, y, CW) - 10

y = heading("", "Simulation (no hardware needed)", C2, y)
y = para("FB_ProcessSim models conveyor, light barrier, measuring unit (pseudo random values, 8 % deep "
         "discharged cells) and both pushers. Fault injection: <i>SimJamPusherB</i> and <i>SimEStop</i> in "
         "DB_HMI (HMI buttons). On the real machine this FB is replaced by the I/O mapping, the station FB stays unchanged.",
         C2, y, CW)

# ---------------------------------------------------------------- column 3
y = heading("4", "Block structure", C3, top)
tree = [
    ("OB_CellSorting", "program cycle OB"),
    ("+- FB_CellSortingMain", "wiring, HMI mirror"),
    ("   +- FB_ProcessSim", "plant model"),
    ("   +- FB_SortStation", "modes + step chain"),
    ("      +- FB_Cylinder x2", "pusher B / Reject"),
    ("      +- FC_GradeCell", "stateless, testable"),
    ("DB_HMI", "Cmd / Par / Sts"),
    ("UDTs", "CellData, GradeLimits,"),
    ("", "Counters, Alarms"),
]
yy = y - 2
for left, right in tree:
    c.setFont("Courier-Bold" if left and not left.startswith(" ") and not left.startswith("+") else "Courier", 7.3)
    c.setFillColor(INK)
    c.drawString(C3, yy - 7, left)
    c.setFont("Helvetica", 6.9)
    c.setFillColor(MUTED)
    c.drawString(C3 + 132, yy - 7, right)
    yy -= 10
y = yy - 10

y = heading("5", "Alarms", C3, y)
y = table([["Alarm", "Class", "Reaction"],
           ["EStop", "Fault", P("ABORTED, every actuator off")],
           ["PusherB / PusherR", "Fault", P("end position not reached in 2 s or both sensors on: valve drops, ABORTED")],
           ["MeasureTimeout", "Fault", P("no result within 3 s: ABORTED")],
           ["TransportTimeout", "Fault", P("cell did not leave within 3 s: ABORTED")],
           ["BinBFull / BinRFull", "Warning", P("hold before next cell, resume when bins emptied")]],
          C3, y, [74, 34, CW - 108], fault_rows=(1, 2, 3, 4)) - 10

y = heading("6", "Design decisions", C3, y)
for txt in [
    "Modes and sequence are separated; steps are numbered 100, 110, ... so new steps fit in between.",
    "All outputs default to OFF every scan and the active step switches on what it needs: no forgotten latched actuator.",
    "Monostable valves: de-energised = retracted = safe. FB_Cylinder drops the valve on error.",
    "Reusable FB_Cylinder; FC_GradeCell has no state, so it can be unit tested.",
    "Grading limits are parameters: a new cell type needs no code change.",
    "HMI buttons are one-shot commands cleared by the PLC; all status goes through one interface DB.",
    "<b>Next steps on a real line:</b> E-stop in an F-CPU safety program (PROFIsafe), real I/O mapping, "
    "Held / Suspended states, cell ID traceability to MES.",
]:
    y = para(txt, C3, y, CW, bullet.clone("b", bulletText="-")) - 0.5

c.save()
print("written", OUT)
