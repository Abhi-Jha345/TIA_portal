"""Generates the WinCC Unified 'Overview' screen design (dark, flat, 1920x1080)
plus the tag binding plan. Output: overview_design.json, overview_bindings.json"""
import json, os

OUT = os.path.dirname(os.path.abspath(__file__))

# ---- palette (TIA ARGB) --------------------------------------------------
BG = "0xFF0D1117"
PANEL = "0xFF161B22"
TILE = "0xFF1C2430"
EDGE = "0xFF2A3441"
TEXT = "0xFFE6EDF3"
MUTED = "0xFF8B98A5"
ACCENT = "0xFF00A3B4"
GREEN = "0xFF2EA043"
AMBER = "0xFFD29922"
RED = "0xFFDA3633"
OFF = "0xFF30363D"

items = []
bind = {"ioValues": [], "visible": [], "buttons": []}


def add(name, typ, l, t, w, h, text=None, props=None, font=None):
    it = {"name": name, "type": typ, "left": l, "top": t, "width": w, "height": h}
    if text is not None:
        it["text"] = text
    if props:
        it["properties"] = props
    if font:
        it["font"] = font
    items.append(it)


def panel(name, l, t, w, h, title):
    add(name, "Rectangle", l, t, w, h, props={"BackColor": PANEL, "BorderColor": EDGE, "BorderWidth": 1})
    add(name + "_t", "Text", l + 24, t + 16, w - 48, 28, title,
        {"ForeColor": MUTED}, {"Size": 14, "Weight": "Bold"})


def label(name, l, t, w, h, text, color=MUTED, size=14, bold=False):
    add(name, "Text", l, t, w, h, text, {"ForeColor": color}, {"Size": size, "Weight": "Bold" if bold else "Normal"})


def value(name, l, t, w, h, tag, size=30, color=TEXT):
    add(name, "IOField", l, t, w, h, props={"BackColor": TILE, "ForeColor": color, "BorderWidth": 0},
        font={"Size": size, "Weight": "Bold"})
    bind["ioValues"].append({"item": name, "tag": tag})


def lamp(name, l, t, size, tag, on_color, caption):
    """grey base + coloured overlay whose Visible follows a Bool tag"""
    add(name + "_off", "Rectangle", l, t, size, size, props={"BackColor": OFF, "BorderWidth": 0})
    add(name + "_on", "Rectangle", l, t, size, size, props={"BackColor": on_color, "BorderWidth": 0})
    bind["visible"].append({"item": name + "_on", "tag": tag})
    label(name + "_l", l + size + 14, t - 2, 260, size + 4, caption, TEXT, 15)


def button(name, l, t, w, h, text, color, tag, fore=TEXT):
    add(name, "Button", l, t, w, h, text, {"BackColor": color, "ForeColor": fore},
        {"Size": 18, "Weight": "Bold"})
    bind["buttons"].append({"item": name, "tag": tag})


# ---- header --------------------------------------------------------------
add("hdr", "Rectangle", 0, 0, 1920, 88, props={"BackColor": PANEL, "BorderWidth": 0})
add("hdr_accent", "Rectangle", 0, 86, 1920, 2, props={"BackColor": ACCENT, "BorderWidth": 0})
label("hdr_title", 32, 14, 900, 40, "Battery Cell Test & Sort Station", TEXT, 26, True)
label("hdr_sub", 32, 52, 900, 24, "S7-1500  |  cell grading A / B / Reject", MUTED, 14)
add("hdr_badge", "Rectangle", 1380, 20, 508, 48, props={"BackColor": TILE, "BorderColor": ACCENT, "BorderWidth": 2})
label("hdr_badge_l", 1400, 32, 90, 24, "STATE", MUTED, 13, True)
value("io_state", 1490, 26, 380, 36, "Sts_StateText", 20, ACCENT)
lamp("lmp_fault", 1336, 32, 24, "Sts_AnyFault", RED, "")

# ---- operation panel ------------------------------------------------------
panel("p_op", 32, 112, 360, 936, "OPERATION")
button("btn_start", 56, 168, 312, 72, "START", GREEN, "Cmd_Start")
button("btn_stop", 56, 256, 312, 72, "STOP", AMBER, "Cmd_Stop", BG)
button("btn_reset", 56, 344, 312, 72, "RESET", ACCENT, "Cmd_Reset", BG)
label("op_note", 56, 428, 312, 44, "Stop is executed at the end of the current cycle.", MUTED, 13)
button("btn_bins", 56, 500, 312, 60, "BINS EMPTIED", TILE, "Cmd_BinsEmptied")
button("btn_rcnt", 56, 576, 312, 60, "RESET COUNTERS", TILE, "Cmd_ResetCounters")
label("sim_t", 56, 680, 312, 28, "SIMULATION", MUTED, 14, True)
button("btn_estop", 56, 724, 312, 72, "E-STOP  (hold)", RED, "Cmd_SimEStop")
button("btn_jam", 56, 812, 312, 60, "JAM PUSHER B  (hold)", TILE, "Cmd_SimJamPusherB")
label("sim_note", 56, 884, 312, 60, "Fault injection for the demo: both raise an alarm and abort the station.", MUTED, 13)

# ---- process mimic ---------------------------------------------------------
panel("p_proc", 416, 112, 1000, 600, "PROCESS")
# bin B (top) and reject bin (bottom)
add("binB", "Rectangle", 786, 168, 200, 96, props={"BackColor": TILE, "BorderColor": EDGE, "BorderWidth": 2})
label("binB_l", 806, 178, 160, 24, "BIN B", MUTED, 13, True)
value("io_binB", 806, 206, 160, 44, "Sts_BinB_Count", 24)
add("binR", "Rectangle", 786, 584, 200, 96, props={"BackColor": TILE, "BorderColor": EDGE, "BorderWidth": 2})
label("binR_l", 806, 594, 160, 24, "REJECT BIN", MUTED, 13, True)
value("io_binR", 806, 622, 160, 44, "Sts_BinR_Count", 24)
# pushers: grey body, coloured when valve energised
lamp("pB", 866, 284, 40, "Sts_PusherB", AMBER, "")
lamp("pR", 866, 528, 40, "Sts_PusherR", AMBER, "")
# conveyor and measuring station
add("conv_off", "Rectangle", 456, 404, 920, 44, props={"BackColor": OFF, "BorderWidth": 0})
add("conv_on", "Rectangle", 456, 404, 920, 44, props={"BackColor": ACCENT, "BorderWidth": 0})
bind["visible"].append({"item": "conv_on", "tag": "Sts_ConveyorRun"})
add("station", "Rectangle", 826, 340, 120, 172, props={"BackColor": "0x00000000", "BorderColor": TEXT, "BorderWidth": 2})
label("station_l", 806, 344, 160, 22, "", MUTED, 12)
add("cell", "Rectangle", 856, 396, 60, 60, props={"BackColor": GREEN, "BorderColor": TEXT, "BorderWidth": 2})
bind["visible"].append({"item": "cell", "tag": "Sts_CellAtStation"})
label("conv_in", 456, 458, 300, 24, "infeed", MUTED, 13)
label("conv_out", 1196, 458, 180, 24, "to module assembly  >", MUTED, 13)
label("meas_l", 960, 352, 200, 24, "MEASURING", MUTED, 13, True)
# status row
lamp("l_conv", 456, 650, 20, "Sts_ConveyorRun", ACCENT, "Conveyor")
lamp("l_cell", 640, 650, 20, "Sts_CellAtStation", GREEN, "Cell present")
lamp("l_meas", 1030, 650, 20, "Sts_MeasureStart", ACCENT, "Measuring")
lamp("l_stop", 1210, 650, 20, "Sts_StopPending", AMBER, "Stop pending")

# ---- KPI tiles ---------------------------------------------------------------
panel("p_kpi", 1440, 112, 448, 600, "PRODUCTION")
tiles = [("Total cells", "Sts_Total", TEXT), ("Yield  %", "Sts_Yield", ACCENT),
         ("Grade A", "Sts_GradeA", GREEN), ("Grade B", "Sts_GradeB", AMBER),
         ("Reject", "Sts_Reject", RED)]
for i, (cap, tag, col) in enumerate(tiles):
    col_i, row_i = i % 2, i // 2
    x, y = 1464 + col_i * 208, 160 + row_i * 176
    add(f"kpi{i}", "Rectangle", x, y, 192, 160, props={"BackColor": TILE, "BorderWidth": 0})
    add(f"kpi{i}_bar", "Rectangle", x, y, 4, 160, props={"BackColor": col, "BorderWidth": 0})
    label(f"kpi{i}_l", x + 20, y + 16, 160, 24, cap, MUTED, 14)
    value(f"io_kpi{i}", x + 16, y + 64, 164, 56, tag, 34, col)

# ---- last cell -----------------------------------------------------------------
panel("p_cell", 416, 736, 720, 312, "LAST CELL")
for i, (cap, tag, unit) in enumerate([("Cell ID", "Sts_LastId", ""), ("Voltage", "Sts_LastVoltage", "V"),
                                       ("Resistance", "Sts_LastRes", "mOhm"), ("Grade (1 A / 2 B / 3 Rej)", "Sts_LastGrade", "")]):
    y = 788 + i * 62
    label(f"lc{i}_l", 440, y + 10, 300, 28, cap, MUTED, 15)
    value(f"io_lc{i}", 760, y, 240, 48, tag, 24)
    label(f"lc{i}_u", 1012, y + 10, 100, 28, unit, MUTED, 15)

# ---- alarms --------------------------------------------------------------------
panel("p_alm", 1160, 736, 728, 312, "ALARMS")
alarms = [("Sts_AlmEStop", "E-stop circuit open", RED), ("Sts_AlmPusherB", "Pusher B end position", RED),
          ("Sts_AlmPusherR", "Pusher Reject end position", RED), ("Sts_AlmMeasure", "Measuring unit timeout", RED),
          ("Sts_AlmTransport", "Cell transport timeout", RED), ("Sts_AlmBinBFull", "Bin B full (hold)", AMBER),
          ("Sts_AlmBinRFull", "Reject bin full (hold)", AMBER)]
for i, (tag, txt, col) in enumerate(alarms):
    col_i, row_i = i // 4, i % 4
    lamp(f"alm{i}", 1188 + col_i * 352, 792 + row_i * 58, 22, tag, col, txt)

design = {"screen": {"BackColor": BG, "Width": 1920, "Height": 1080}, "items": items}
with open(os.path.join(OUT, "overview_design.json"), "w", encoding="utf-8") as f:
    json.dump(design, f, indent=1)
with open(os.path.join(OUT, "overview_bindings.json"), "w", encoding="utf-8") as f:
    json.dump(bind, f, indent=1)
print(len(items), "items;", sum(len(v) for v in bind.values()), "bindings")
