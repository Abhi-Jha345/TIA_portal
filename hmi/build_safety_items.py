"""Safety additions to the 'Station' screen (applied on top of build_overview.py)."""
import json
TEXT, MUTED, TILE, OFF = "0xFFE6EDF3", "0xFF8B98A5", "0xFF1C2430", "0xFF30363D"
GREEN, AMBER, RED, ACCENT, BLUE = "0xFF2EA043", "0xFFD29922", "0xFFDA3633", "0xFF00A3B4", "0xFF1F6FEB"
items = []
def it(name, typ, l, t, w, h, text=None, props=None, font=None):
    d = {"name": name, "type": typ, "left": l, "top": t, "width": w, "height": h}
    if text is not None: d["text"] = text
    if props: d["properties"] = props
    if font: d["font"] = font
    items.append(d)
def lamp(name, l, t, s, color, caption, cw=260):
    it(name + "_off", "Rectangle", l, t, s, s, props={"BackColor": OFF, "BorderWidth": 0})
    it(name + "_on", "Rectangle", l, t, s, s, props={"BackColor": color, "BorderWidth": 0})
    it(name + "_l", "Text", l + s + 12, t - 3, cw, s + 6, caption, {"ForeColor": TEXT}, {"Size": 14, "Weight": "Normal"})
B = {"Size": 16, "Weight": "Bold"}
# re-layout of the existing simulation area (updates existing items)
it("sim_t", "Text", 56, 652, 312, 28, "SIMULATION / SAFETY", {"ForeColor": MUTED}, {"Size": 14, "Weight": "Bold"})
it("btn_estop", "Button", 56, 688, 312, 56, "E-STOP  (hold)", {"BackColor": RED, "ForeColor": TEXT}, B)
it("btn_jam", "Button", 56, 752, 312, 44, "JAM PUSHER B  (hold)", {"BackColor": TILE, "ForeColor": TEXT}, B)
it("sim_note", "Text", 56, 990, 312, 50, "Safety reset acts on RELEASE; held > 5 s counts as stuck and is ignored.", {"ForeColor": MUTED}, {"Size": 12, "Weight": "Normal"})
# new buttons
it("btn_door", "Button", 56, 804, 312, 44, "GUARD DOOR  (toggle)", {"BackColor": TILE, "ForeColor": TEXT}, B)
it("btn_disc", "Button", 56, 856, 312, 44, "WELD E-STOP CH.B  (toggle)", {"BackColor": TILE, "ForeColor": TEXT}, B)
it("btn_sreset", "Button", 56, 916, 312, 64, "SAFETY RESET", {"BackColor": BLUE, "ForeColor": TEXT}, {"Size": 18, "Weight": "Bold"})
# header safety status
lamp("lmp_safe", 960, 22, 20, GREEN, "Safety OK", 150)
lamp("lmp_energy", 1140, 22, 20, ACCENT, "Energy released", 200)
lamp("lmp_rst", 960, 54, 20, AMBER, "Safety reset required", 330)
# alarms
lamp("alm7", 1540, 966, 22, RED, "Guard door opened")
lamp("alm8", 1188, 1016, 22, RED, "Safety input discrepancy")
dj = json.dumps({"items": items}, separators=(",", ":"))
print(json.dumps({"hmiSoftwarePath": "HMI_RT_1", "screenName": "Station", "strict": True, "designJson": dj}, separators=(",", ":")))
