"""Project documentation PDF for the battery cell test & sort station pilot (A4 portrait).

Reads everything at run time from the repository (SCL sources, block_versions.json, tests,
HMI json, UML sources, deploy script, workflows), runs the pytest suite and renders the UML
diagrams with PlantUML (if Java + tools/plantuml/plantuml.jar exist), then writes one PDF with
a clickable table of contents, PDF bookmarks and the complete source code as appendix.

Usage:  python docs/project_documentation.py [output.pdf]
        (default: docs/CellSortingStation_ProjectDocumentation.pdf)
Needs:  reportlab. Optional: java (UML images). Nothing is written inside the repo except
        the PDF; UML PNGs and pytest output go to a temp directory.
"""
import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "docs" / "CellSortingStation_ProjectDocumentation.pdf")

TITLE = "Battery Cell Test & Sort Station — Project Documentation"
RUNNING = "Battery Cell Test & Sort Station - Project Documentation"
DATE = "2026-11-19"
DOCVER = "v1.0.x"

# ---------------------------------------------------------------- look (same as the other PDFs)
INK, MUTED, ACCENT = HexColor("#1d2733"), HexColor("#5b6773"), HexColor("#0b6e8a")
RULE, FILL, FAULT, FAULTFILL = HexColor("#c9d3db"), HexColor("#e8f3f6"), HexColor("#b3261e"), HexColor("#fbeaea")
CODEBG, CODEKW, CODECM, CODESTR = HexColor("#f5f7f9"), HexColor("#0b6e8a"), HexColor("#6b7a86"), HexColor("#8a4b08")

h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=INK, spaceBefore=0, spaceAfter=6)
h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=ACCENT, spaceBefore=10, spaceAfter=4)
h3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=INK, spaceBefore=8, spaceAfter=3)
h3n = ParagraphStyle("H3n", parent=h3)
body = ParagraphStyle("body", fontName="Helvetica", fontSize=8.8, leading=11.6, textColor=INK, spaceAfter=4)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=11, bulletIndent=2, spaceAfter=2)
cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.4, leading=9.0, textColor=INK)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
cellm = ParagraphStyle("cellm", parent=cell, fontName="Courier", fontSize=7.0, leading=8.6)
note = ParagraphStyle("note", parent=body, fontSize=7.8, leading=10, textColor=MUTED)
cap = ParagraphStyle("cap", parent=note, alignment=1, spaceBefore=2, spaceAfter=8)

PAGE_W, PAGE_H = A4
LM = RM = 20 * mm
TM, BM = 24 * mm, 20 * mm
FW = PAGE_W - LM - RM


def P(text, style=body):
    return Paragraph(text, style)


def E(s):
    return escape(str(s))


def bullets(items):
    return [Paragraph(t, bullet, bulletText="•") for t in items]


def table(rows, widths, head=True, mono_cols=(), zebra=True):
    """rows: list of lists of str (markup allowed) ; widths in mm"""
    data = []
    for i, r in enumerate(rows):
        line = []
        for j, c in enumerate(r):
            if not isinstance(c, str):
                line.append(c)
            elif head and i == 0:
                line.append(Paragraph(c, ParagraphStyle("hw", parent=cellb, textColor=white)))
            else:
                line.append(Paragraph(c, cellm if j in mono_cols else cell))
        data.append(line)
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT))
    if zebra:
        for i in range(2 if head else 1, len(rows), 2):
            st.append(("BACKGROUND", (0, i), (-1, i), HexColor("#f4f8fa")))
    t.setStyle(TableStyle(st))
    return t


# ---------------------------------------------------------------- headings / bookmarks / TOC
class Heading(Paragraph):
    pass


_key = [0]


def H(text, level):
    """level 0/1/2 -> TOC + bookmark; level 3 = plain sub heading (no TOC)."""
    style = {0: h1, 1: h2, 2: h3, 3: h3n}[level]
    text = text.replace("face='Courier'", "face='Courier-Bold'")
    p = Heading(text, style)
    if level < 3:
        _key[0] += 1
        p._toc = (level, re.sub(r"<[^>]+>", "", text), f"bm{_key[0]}")
    return p


class Doc(BaseDocTemplate):
    def afterFlowable(self, f):
        t = getattr(f, "_toc", None)
        if t:
            level, text, key = t
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level, closed=(level >= 1 and False))
            self.notify("TOCEntry", (level, text, self.page, key))


# ---------------------------------------------------------------- code listing flowable
SCL_KW = set("""IF THEN ELSIF ELSE END_IF CASE OF END_CASE REGION END_REGION BEGIN VAR VAR_INPUT VAR_OUTPUT
VAR_IN_OUT VAR_TEMP CONSTANT END_VAR STRUCT END_STRUCT TYPE END_TYPE FUNCTION END_FUNCTION FUNCTION_BLOCK
END_FUNCTION_BLOCK DATA_BLOCK END_DATA_BLOCK ORGANIZATION_BLOCK END_ORGANIZATION_BLOCK AND OR XOR NOT MOD
TRUE FALSE VERSION TITLE NON_RETAIN FOR TO DO END_FOR WHILE END_WHILE RETAIN""".split())
PS_KW = set("""param function if else elseif foreach try catch finally return throw switch while for in begin
process end Add-Type""".split())
YAML_KW = set("on jobs steps uses run env with name needs runs-on if permissions".split())


def classify(line, lang):
    """per-character class: 0 text, 1 keyword, 2 comment, 3 string"""
    cls = [0] * len(line)
    cm = None
    if lang == "scl":
        m = re.search(r"//", line)
        cm = m.start() if m else None
    else:
        m = re.search(r"(^|\s)#", line)
        cm = m.start() + (len(m.group(1)) if m else 0) if m else None
    code_end = cm if cm is not None else len(line)
    if cm is not None:
        for i in range(cm, len(line)):
            cls[i] = 2
    for m in re.finditer(r"'(?:[^']|'')*'|\"[^\"]*\"", line[:code_end]):
        for i in range(m.start(), m.end()):
            cls[i] = 3
    kws = SCL_KW if lang == "scl" else (PS_KW if lang == "ps1" else set())
    for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9\-]*", line[:code_end]):
        w = m.group(0)
        if cls[m.start()] == 0 and ((w.upper() in kws) if lang == "scl" else (w.lower() in {k.lower() for k in kws})):
            for i in range(m.start(), m.end()):
                cls[i] = 1
    if lang == "yaml":
        m = re.match(r"^(\s*-?\s*)([A-Za-z_][\w\-]*)(:)", line)
        if m and cls[m.start(2)] == 0:
            for i in range(m.start(2), m.end(2)):
                cls[i] = 1
    return cls


FONTS = {0: "Courier", 1: "Courier-Bold", 2: "Courier-Oblique", 3: "Courier"}
COLORS = {0: INK, 1: CODEKW, 2: CODECM, 3: CODESTR}


def wrap_line(line, maxc):
    """Return list of (start, end) slices; wrap at a space when possible, indent continuations."""
    if len(line) <= maxc:
        return [(0, len(line), 0)]
    indent = len(line) - len(line.lstrip(" "))
    cont = min(indent + 4, 24)
    out, pos, first = [], 0, True
    while pos < len(line):
        room = maxc if first else maxc - cont
        if len(line) - pos <= room:
            out.append((pos, len(line), 0 if first else cont))
            break
        cut = line.rfind(" ", pos + (indent if first else 0) + 8, pos + room + 1)
        if cut <= pos:
            cut = pos + room
        else:
            cut += 1          # keep the space on the upper line
        out.append((pos, cut, 0 if first else cont))
        pos = cut
        first = False
    return out


class CodeListing(Flowable):
    FS, LH, PAD = 7.5, 8.9, 5

    def __init__(self, lines, lang="scl", first_no=1, numbers=True, width=None, rows=None):
        super().__init__()
        self.FS, self.LH = CodeListing.FS, CodeListing.LH
        self.lines, self.lang, self.first_no, self.numbers = lines, lang, first_no, numbers
        self.cw = stringWidth("M", "Courier", self.FS)
        self.gut = (len(str(first_no + len(lines))) + 1) * self.cw if numbers else 0
        self.width_ = width or FW
        self.maxc = int((self.width_ - 2 * self.PAD - self.gut) / self.cw)
        if rows is None:
            rows = []
            for i, ln in enumerate(lines):
                ln = ln.expandtabs(4).rstrip()
                cls = classify(ln, lang)
                for k, (a, b, ind) in enumerate(wrap_line(ln, self.maxc)):
                    rows.append((first_no + i if k == 0 else None, ind, ln[a:b], cls[a:b]))
            self.gut = (len(str(rows[-1][0] if rows and rows[-1][0] else first_no + len(lines))) + 1) * self.cw if numbers else 0
        self.rows = rows

    def wrap(self, aw, ah):
        self.width = self.width_
        self.height = len(self.rows) * self.LH + 2 * self.PAD
        return self.width, self.height

    def split(self, aw, ah):
        n = int((ah - 2 * self.PAD) / self.LH)
        if n >= len(self.rows) or n < 3:
            return [] if n < 3 else [self]
        a = CodeListing(self.lines, self.lang, self.first_no, self.numbers, self.width_, self.rows[:n])
        b = CodeListing(self.lines, self.lang, self.first_no, self.numbers, self.width_, self.rows[n:])
        for x in (a, b):
            x.gut, x.FS, x.LH, x.cw, x.maxc = self.gut, self.FS, self.LH, self.cw, self.maxc
        return [a, b]

    def draw(self):
        c = self.canv
        c.setFillColor(CODEBG)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.rect(0, 0, self.width, self.height, stroke=1, fill=1)
        if self.numbers:
            c.setStrokeColor(RULE)
            c.line(self.PAD + self.gut - 2, 0, self.PAD + self.gut - 2, self.height)
        y = self.height - self.PAD - self.FS * 0.85 - (self.LH - self.FS) / 2
        for no, ind, text, cls in self.rows:
            if no is not None and self.numbers:
                c.setFont("Courier", self.FS)
                c.setFillColor(MUTED)
                c.drawRightString(self.PAD + self.gut - 5, y, str(no))
            x = self.PAD + self.gut + ind * self.cw
            i = 0
            while i < len(text):
                j = i
                while j < len(text) and cls[j] == cls[i]:
                    j += 1
                c.setFont(FONTS[cls[i]], self.FS)
                c.setFillColor(COLORS[cls[i]])
                c.drawString(x + i * self.cw, y, text[i:j])
                i = j
            y -= self.LH


def listing_plain(text, size=6.8):
    """small monospace box for docstring tables"""
    cl = CodeListing(text.rstrip("\n").split("\n"), "none", numbers=False)
    cl.FS, cl.LH = size, size * 1.2
    cl.cw = stringWidth("M", "Courier", size)
    cl.maxc = int((cl.width_ - 2 * cl.PAD) / cl.cw)
    rows = []
    for ln in cl.lines:
        ln = ln.expandtabs(4).rstrip()
        for k, (a, b, ind) in enumerate(wrap_line(ln, cl.maxc)):
            rows.append((0, ind, ln[a:b], [0] * (b - a)))
    cl.rows = rows
    cl.gut = 0
    return cl


# ---------------------------------------------------------------- SCL parsing
SOURCES = ["01_Types.scl", "02_Blocks.scl", "03_OB.scl"]
BLOCK_RE = re.compile(r'^(TYPE|FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK)\s+"([^"]+)"\s*(?::\s*(\w+))?')
END_OF = {"TYPE": "END_TYPE", "FUNCTION_BLOCK": "END_FUNCTION_BLOCK", "FUNCTION": "END_FUNCTION",
          "DATA_BLOCK": "END_DATA_BLOCK", "ORGANIZATION_BLOCK": "END_ORGANIZATION_BLOCK"}
KIND_LONG = {"TYPE": "UDT", "FUNCTION_BLOCK": "FB", "FUNCTION": "FC", "DATA_BLOCK": "DB", "ORGANIZATION_BLOCK": "OB"}


def parse_scl(fname):
    lines = (ROOT / "src" / fname).read_text(encoding="utf-8").split("\n")
    blocks, cur = [], None
    for no, ln in enumerate(lines, 1):
        m = BLOCK_RE.match(ln)
        if m and cur is None:
            cur = dict(kind=m.group(1), name=m.group(2), ret=m.group(3), file=fname, start=no, lines=[])
        if cur is not None:
            cur["lines"].append(ln)
            if ln.strip().rstrip(";") == END_OF[cur["kind"]]:
                cur["end"] = no
                vm = re.search(r"^VERSION\s*:\s*(\d+)\.(\d+)", "\n".join(cur["lines"]), re.M)
                cur["version"] = f"{vm.group(1)}.{vm.group(2)}" if vm else "?"
                cur["members"] = parse_members(cur)
                blocks.append(cur)
                cur = None
    return blocks


def parse_members(b):
    """list of (dir, name, type, default, comment)"""
    out, sec, stack = [], None, []
    secmap = {"VAR_INPUT": "IN", "VAR_OUTPUT": "OUT", "VAR_IN_OUT": "IN/OUT", "VAR_TEMP": "TEMP"}
    for ln in b["lines"]:
        s = ln.strip()
        if s.startswith("//") or not s:
            continue
        if b["kind"] == "TYPE":
            sec = "MEMBER"
        else:
            tok = s.split()[0].rstrip(";")
            if tok in secmap:
                sec = secmap[tok]
                continue
            if tok == "VAR":
                sec = "CONST" if "CONSTANT" in s else ("DATA" if b["kind"] == "DATA_BLOCK" else "STAT")
                continue
            if tok == "END_VAR":
                sec = None
                continue
            if tok == "BEGIN":
                break
        if s.startswith("END_STRUCT"):
            if stack:
                stack.pop()
            continue
        if s == "STRUCT":
            stack.append(None)
            continue
        m = re.match(r"^(\w+)\s*:\s*(.+?)\s*(?::=\s*([^;/]+?))?\s*;?\s*(?://\s*(.*))?$", s)
        if not m or sec is None:
            continue
        if m.group(1) in ("VERSION", "TITLE"):
            continue
        name, typ, dflt, com = m.group(1), m.group(2).rstrip(";").strip(), m.group(3), m.group(4) or ""
        if typ.upper().startswith("STRUCT"):
            stack.append(name)
            continue
        if dflt is None and ":=" in typ:
            typ, dflt = [x.strip() for x in typ.split(":=", 1)]
        path = ".".join([x for x in stack if x] + [name])
        out.append((sec, path, typ.strip('"'), (dflt or "").strip(), com.strip()))
    return out


def load_blocks():
    allb = []
    for f in SOURCES:
        allb += parse_scl(f)
    return allb


PURPOSE = {
    "UDT_CellData": "One measured cell: id, voltage, internal resistance, grade (0 none, 1 A, 2 B, 3 Reject).",
    "UDT_GradeLimits": "Grading limits for A and B with defaults (3.60-3.70 V / 18 mOhm and 3.55-3.75 V / 25 mOhm).",
    "UDT_Counters": "Production counters: total, grade A, grade B, reject, yield in percent.",
    "UDT_Alarms": "Alarm bits (faults EStop, PusherB/R, timeouts, DoorOpen, SafetyDiscrepancy; warnings bin full).",
    "FC_GradeCell": "Pure function: classify a cell as A / B / Reject; implausible values (V or R <= 0) are Reject.",
    "FC_AnyFault": "Single definition of 'station must not run' (all faults or no safety release; warnings excluded).",
    "FB_Cylinder": "Reusable pneumatic cylinder with end-position monitoring, timeouts, latched error and error code.",
    "FB_ProcessSim": "Plant simulation (conveyor, cell arrival, measuring unit, two pushers, fault injection) for tests without hardware.",
    "FB_DualChannel": "Two-channel NC input evaluation with 500 ms discrepancy monitoring and acknowledge-after-both-open rule.",
    "FB_SafetyMonitor": "Standard-PLC mirror of SF1 E-stop (cat 0), SF2 guard door (cat 1) and SF3 reset logic.",
    "FB_SortStation": "Station logic: PackML-style modes, step chain, fault reaction, bins, counters, HMI status text.",
    "DB_HMI": "Global HMI interface DB (Cmd / Par / Sts); non-optimized, DB1, absolute addressing for the HMI.",
    "FB_CellSortingMain": "Top level: wires safety, simulation, station and DB_HMI; clears one-shot commands.",
    "iDB_CellSortingMain": "Instance data block of FB_CellSortingMain (called from the OB).",
    "OB_CellSorting": "Cyclic program OB: calls the main instance with SimMode := TRUE.",
}


def load_versions():
    return json.loads((ROOT / "src" / "block_versions.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- external steps
def run_pytest(tmp):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("SCL_COVERAGE_REPORT", None)
    res = {"ok": False, "lines": [], "result": "not executed", "cov": "", "per_file": {}}
    try:
        col = subprocess.run([sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-p", "no:cacheprovider"],
                             cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        for ln in col.stdout.splitlines():
            m = re.match(r"tests[/\\](test_\w+\.py)::", ln)
            if m:
                res["per_file"][m.group(1)] = res["per_file"].get(m.group(1), 0) + 1
        r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        out = [l.rstrip() for l in (r.stdout + r.stderr).splitlines() if l.strip()]
        res["lines"] = [l for l in out if not re.fullmatch(r"[.FEsx\s\[\]\d%]+", l)]
        for l in out:
            if re.search(r"\d+ (passed|failed)", l):
                res["result"] = l.strip("= ")
            if "decision outcomes" in l:
                res["cov"] = l.strip()
        res["ok"] = r.returncode == 0
    except Exception as exc:  # pragma: no cover
        res["lines"] = [f"pytest could not be run: {exc}"]
    return res


def render_uml(tmp):
    """returns {stem_name: png_path}; empty dict if rendering is impossible"""
    jar = ROOT / "tools" / "plantuml" / "plantuml.jar"
    if not jar.exists() or not shutil.which("java"):
        return {}
    outdir = pathlib.Path(tmp) / "uml"
    outdir.mkdir(exist_ok=True)
    pumls = sorted((ROOT / "docs" / "uml").glob("*.puml"))
    try:
        subprocess.run(["java", "-Djava.awt.headless=true", "-jar", str(jar), "-Playout=smetana", "-tpng",
                        "-o", str(outdir)] + [str(p) for p in pumls], capture_output=True, timeout=600, check=True,
                       cwd=tmp)
    except Exception:
        pass
    res = {}
    for p in pumls:
        m = re.search(r"@startuml\s+(\S+)", p.read_text(encoding="utf-8"))
        png = outdir / ((m.group(1) if m else p.stem) + ".png")
        if png.exists():
            res[p.name] = png
    return res


# ---------------------------------------------------------------- page decoration
def deco(canv, doc):
    canv.saveState()
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.5)
    canv.line(LM, PAGE_H - 16 * mm, PAGE_W - RM, PAGE_H - 16 * mm)
    canv.setFont("Helvetica-Bold", 7.6)
    canv.setFillColor(ACCENT)
    canv.drawString(LM, PAGE_H - 13.5 * mm, RUNNING)
    canv.setFont("Helvetica", 7.6)
    canv.setFillColor(MUTED)
    canv.drawRightString(PAGE_W - RM, PAGE_H - 13.5 * mm, f"S7-1500 | TIA Portal V20 | {DOCVER}")
    canv.line(LM, 14 * mm, PAGE_W - RM, 14 * mm)
    canv.drawString(LM, 10 * mm, DATE)
    canv.drawCentredString(PAGE_W / 2, 10 * mm, f"Page {doc.page}")
    canv.drawRightString(PAGE_W - RM, 10 * mm, "Project documentation")
    canv.restoreState()


def title_page(canv, doc):
    canv.saveState()
    canv.setFillColor(ACCENT)
    canv.rect(0, PAGE_H - 70 * mm, PAGE_W, 70 * mm, stroke=0, fill=1)
    canv.setFillColor(white)
    canv.setFont("Helvetica", 10)
    canv.drawString(LM, PAGE_H - 22 * mm, "SIMATIC S7-1500  |  CPU 1516-3 PN/DP  |  TIA Portal V20")
    canv.setFont("Helvetica-Bold", 25)
    canv.drawString(LM, PAGE_H - 40 * mm, "Battery Cell Test & Sort Station")
    canv.setFont("Helvetica", 17)
    canv.drawString(LM, PAGE_H - 51 * mm, "Project Documentation")
    canv.setFillColor(MUTED)
    canv.setFont("Helvetica", 8)
    canv.drawString(LM, 14 * mm, "PLC software pilot: SCL, WinCC Unified, ISO 13849 safety functions, pytest on real SCL, CI/CD")
    canv.restoreState()


# ---------------------------------------------------------------- content
def build():
    tmp = tempfile.mkdtemp(prefix="projdoc_")
    blocks = load_blocks()
    versions = load_versions()
    pt = run_pytest(tmp)
    uml = render_uml(tmp)
    by = {b["name"]: b for b in blocks}
    S = []

    # ---- title page
    S += [Spacer(1, 62 * mm), P("<b>Battery Cell Test &amp; Sort Station — Project Documentation</b>",
                               ParagraphStyle("t", parent=body, fontSize=13, leading=17)), Spacer(1, 4 * mm)]
    S.append(table([
        ["Item", "Value"],
        ["Controller", "SIMATIC S7-1500, CPU 1516-3 PN/DP (PLC_1)"],
        ["HMI", "WinCC Unified PC Runtime (HMI_RT_1), non-integrated connection"],
        ["Engineering", "TIA Portal V20, STEP 7 SCL external sources"],
        ["Document version", f"{DOCVER} (block versions: see sections 3 and 7)"],
        ["Date", DATE],
        ["Scope", "Software architecture, block catalogue, safety summary, HMI, verification, versioning and CI/CD, UML, complete PLC source code"],
        ["Related documents", "docs/CellSortingStation_DesignSheet.pdf, docs/CellSortingStation_SafetyConcept.pdf"],
    ], [38, 132], head=True))
    S += [Spacer(1, 6 * mm), P("This document is generated by <font face='Courier'>docs/project_documentation.py</font> from the repository "
                              "sources (SCL, block_versions.json, tests, HMI json, UML, workflows). It is regenerated, not edited.", note)]
    S.append(NextPageTemplate("main"))
    S.append(PageBreak())

    # ---- TOC
    S.append(Heading("Contents", h1))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("t0", fontName="Helvetica-Bold", fontSize=9, leading=13, leftIndent=0, spaceBefore=3, textColor=INK),
        ParagraphStyle("t1", fontName="Helvetica", fontSize=8.4, leading=11, leftIndent=12, textColor=INK),
        ParagraphStyle("t2", fontName="Helvetica", fontSize=7.8, leading=10, leftIndent=26, textColor=MUTED),
    ]
    toc.dotsMinLevel = 0
    S.append(toc)
    S.append(PageBreak())

    # ================================================================= 1 Overview
    S.append(H("1  Overview", 0))
    S.append(H("1.1  Process description", 1))
    S.append(P("The station tests and sorts battery cells. A conveyor feeds single cells to a measuring station that "
               "determines the open-circuit voltage and the internal resistance. The PLC grades each cell as "
               "<b>A</b>, <b>B</b> or <b>Reject</b>. Grade A continues on the conveyor to module assembly; grade B and "
               "Reject are pushed into their bins by two pneumatic pushers (pusher B and pusher Reject). The PLC counts "
               "cells per grade, computes the yield and holds the station when a bin is full until the operator confirms "
               "that the bins were emptied."))
    S.append(P("The project is a pilot: it shows structured SCL for the S7-1500 (typed interfaces, reusable blocks, mode "
               "handling, fault reaction), safety-related control functions designed along ISO 13849-1, an HMI, unit tests "
               "that execute the real SCL, block versioning and a CI/CD pipeline. A plant simulation block replaces the "
               "real I/O so everything can be demonstrated without hardware."))
    S.append(H("1.2  Station sequence", 1))
    S.append(table([
        ["Step", "Number", "What happens", "Leaves the step when"],
        ["WAIT_CELL", "100", "Conveyor runs until a cell is detected. Holds if bin B or Reject bin is full. A pending stop request is executed here (back to IDLE).", "CellAtStation"],
        ["MEASURE", "110", "Measuring unit started; voltage and resistance are taken over.", "MeasureDone (timeout 3 s: alarm MeasureTimeout)"],
        ["GRADE", "120", "Cell id assigned, FC_GradeCell called, counters updated, LastCell published.", "next scan"],
        ["EJECT", "130", "A: conveyor carries the cell on. B / Reject: matching pusher extends.", "A: cell gone; B/R: pusher extended"],
        ["RETRACT", "140", "Pushers retract, cell must have left the station.", "Both retracted and no cell (timeout 3 s: TransportTimeout)"],
    ], [24, 15, 87, 44]))
    S.append(H("1.3  Grading rules (UDT_GradeLimits defaults)", 1))
    lim = {m[1]: m[3] for m in by["UDT_GradeLimits"]["members"]}
    S.append(table([
        ["Grade", "Voltage", "Internal resistance", "Note"],
        ["A", f"{lim['A_VoltMin']} V <= U <= {lim['A_VoltMax']} V", f"R <= {lim['A_ResMax_mOhm']} mOhm", "Checked first, after the plausibility test"],
        ["B", f"{lim['B_VoltMin']} V <= U <= {lim['B_VoltMax']} V", f"R <= {lim['B_ResMax_mOhm']} mOhm", "Everything that is not A but inside the B window"],
        ["Reject", "all other values", "all other values", "Also implausible measurements: U <= 0 V or R <= 0 mOhm (short circuit / contact fault)"],
    ], [20, 50, 38, 62]))
    S.append(P("The limits are parameters in <font face='Courier'>DB_HMI.Par.Limits</font> and can be changed at run time; "
               "bin capacity is <font face='Courier'>DB_HMI.Par.BinCapacity</font> (default 20).", note))
    S.append(H("1.4  Hardware and software architecture", 1))
    S.append(table([
        ["Component", "Description"],
        ["PLC_1", "SIMATIC S7-1500, CPU 1516-3 PN/DP. Program: OB_CellSorting -> FB_CellSortingMain. All blocks use optimized access except DB_HMI."],
        ["HMI_RT_1", "WinCC Unified PC Runtime, screen 'Station' (1920 x 1080). Connection HMI_Connection_1 is <b>non-integrated</b> in V20, so tags use absolute addresses."],
        ["DB_HMI", "Global DB, <b>non-optimized access</b>, DB number 1. The HMI addresses it absolutely (for example %DB1.DBX0.0). Layout is computed from the SCL and compared with hmi/hmi_tags.json in CI (tools/db_layout.py)."],
        ["Simulation", "FB_ProcessSim stands in for conveyor, light barrier, measuring unit, pushers and compressed air. On real hardware it is replaced by the I/O mapping."],
        ["Safety", "Standard-PLC mirror (FB_SafetyMonitor). The real safety functions belong in an F-CPU with PROFIsafe F-I/O, see section 5."],
    ], [26, 144]))

    # ================================================================= 2 Software architecture
    S.append(H("2  Software architecture", 0))
    S.append(H("2.1  Block call hierarchy", 1))
    S.append(CodeListing([
        "OB_CellSorting                     (cyclic program OB)",
        " +-- iDB_CellSortingMain  =  FB_CellSortingMain(SimMode := TRUE)",
        "      |-- safety  : FB_SafetyMonitor",
        "      |     |-- dcEStop : FB_DualChannel      (E-stop, 2 channels)",
        "      |     +-- dcDoor  : FB_DualChannel      (guard door, 2 channels)",
        "      |-- sim     : FB_ProcessSim              (plant simulation)",
        "      +-- station : FB_SortStation",
        "            |-- cylB : FB_Cylinder             (pusher B)",
        "            |-- cylR : FB_Cylinder             (pusher Reject)",
        "            |-- FC_GradeCell(...)              (call in step GRADE)",
        "            +-- FC_AnyFault(...)               (call in Faults and Fault_reaction)",
        "",
        "DB_HMI (Cmd / Par / Sts) is read and written only by FB_CellSortingMain.",
        "Data types: UDT_CellData, UDT_GradeLimits, UDT_Counters, UDT_Alarms.",
    ], "none", numbers=False))
    S.append(Spacer(1, 3))
    S.append(P("Every FB is instantiated as a <b>multi-instance</b> inside its caller, so the whole program has exactly one "
               "instance data block (iDB_CellSortingMain). FB_CellSortingMain is the only place that knows the HMI DB; "
               "FB_SortStation and the safety blocks have clean typed interfaces and are testable in isolation."))
    S.append(H("2.2  Mode and state machine (PackML style)", 1))
    S.append(table([
        ["State", "No.", "Meaning", "Transitions"],
        ["STOPPED", "0", "Initial state after block initialisation", "Reset edge -> RESETTING"],
        ["RESETTING", "10", "Bring the station to home position", "Both pushers retracted -> IDLE"],
        ["IDLE", "20", "Ready, waiting for Start", "Start edge -> EXECUTE (step WAIT_CELL)"],
        ["EXECUTE", "30", "Step chain runs; Stop is deferred to end of cycle", "Stop request honoured in WAIT_CELL -> IDLE; any fault -> ABORTED"],
        ["ABORTED", "90", "Fault or safety stop; all actuators off", "Reset edge AND SafetyOk -> alarms cleared, RESETTING"],
    ], [24, 11, 63, 72]))
    S.append(P("An unknown state number falls back to STOPPED, an unknown step number to WAIT_CELL (tests G4, G5). "
               "After ABORTED the station returns to IDLE, never directly to EXECUTE: there is no automatic restart.", note))
    S.append(H("2.3  Step chain", 1))
    S.append(P("The chain WAIT_CELL (100) -> MEASURE (110) -> GRADE (120) -> EJECT (130) -> RETRACT (140) -> WAIT_CELL is a "
               "nested CASE inside state EXECUTE. A step timer (TON_TIME, 30 s preset, restarted whenever the step number "
               "changes) provides the per-step supervision used for the 3 s timeouts. The stop request is only evaluated in "
               "WAIT_CELL, so no half-sorted cell remains in the station."))
    S.append(H("2.4  Fault-reaction region", 1))
    S.append(P("FB_SortStation evaluates faults twice per scan. The first check (region <i>Faults</i>) latches E-stop, door and "
               "discrepancy alarms from the safety monitor and forces ABORTED. The second check (region <i>Fault_reaction</i>, after "
               "the actuators were called) catches faults that appeared during this scan (cylinder errors, step timeouts): it "
               "sets ABORTED and forces <b>every actuator output to FALSE in the same scan</b>. This was found by unit test U3. "
               "FC_AnyFault is the single definition of 'station must not run'; bin-full is a warning and not a fault."))
    S.append(P("Region order in FB_SortStation: Edges, Faults, Step_timer, State_machine, Actuators, Fault_reaction, "
               "Bins_and_counters, Status_text, Outputs.", note))
    S.append(H("2.5  Design rules", 1))
    S += bullets([
        "<b>Outputs default to OFF</b> at the start of every scan (ConveyorRun, MeasureStart, pusher commands); a step switches on what it needs. A step that is left can never leave an output stuck on.",
        "<b>Statics hold the state</b> (actState, actStep, alarms, counters, bin counts, edge memories). The interface outputs carry no state.",
        "<b>Outputs are written at the end</b> in a dedicated region <i>Outputs</i>; internal logic works on the statics. FB_Cylinder writes its outputs after its fault check so the valve drops in the same scan.",
        "<b>Safe state = de-energised</b>: monostable valves retract on power loss or error; the safety release is lost on any trip and is only restored by a manual reset with closed circuits.",
        "<b>Plausibility before classification</b>: FC_GradeCell rejects U <= 0 or R <= 0 before it compares limits.",
        "<b>One-shot HMI commands</b> are cleared by the PLC after one scan; the station uses R_TRIG edges, never levels.",
        "<b>Pure functions for decisions</b> (FC_GradeCell, FC_AnyFault) so they are unit-testable without state.",
        "<b>ASCII-only sources</b> (checked in CI): TIA reads external sources without BOM in the system code page.",
    ])

    # ================================================================= 3/4 Block catalogue
    S.append(H("3  Block catalogue", 0))
    S.append(P("Versions come from <font face='Courier'>src/block_versions.json</font>; interfaces are parsed from the SCL at "
               "generation time. 'Interface' gives the number of members per section (IN / OUT / IN-OUT / STAT / MEMBER / DATA); "
               "the complete member lists are in section 3.2."))
    S.append(H("3.1  Catalogue", 1))
    rows = [["Block", "Kind", "Ver.", "File", "Purpose", "Interface"]]
    order = ["UDT_CellData", "UDT_GradeLimits", "UDT_Counters", "UDT_Alarms", "FC_GradeCell", "FC_AnyFault", "FB_Cylinder",
             "FB_ProcessSim", "FB_DualChannel", "FB_SafetyMonitor", "FB_SortStation", "DB_HMI", "FB_CellSortingMain",
             "iDB_CellSortingMain", "OB_CellSorting"]
    order += [n for n in by if n not in order]
    for n in order:
        b = by[n]
        v = versions.get(n, {}).get("version")
        ver = ".".join(map(str, v)) if v else b["version"] + "*"
        cnt = {}
        for m in b["members"]:
            cnt[m[0]] = cnt.get(m[0], 0) + 1
        ifs = ", ".join(f"{k} {c}" for k, c in cnt.items()) or "none"
        if b["ret"]:
            ifs += f"; returns {b['ret']}"
        if b["kind"] == "DATA_BLOCK" and not b["members"]:
            ifs = "instance of FB_CellSortingMain"
        rows.append([f"<font face='Courier'>{E(n)}</font>", KIND_LONG[b["kind"]], ver, b["file"].replace(".scl", ""),
                     E(PURPOSE.get(n, "")), E(ifs)])
    S.append(table(rows, [34, 9, 9, 17, 66, 35]))
    S.append(P("Version comes from block_versions.json; a trailing * would mean the block is not yet in the manifest.", note))
    S.append(H("3.2  Interfaces", 1))
    for n in order:
        b = by[n]
        if not b["members"]:
            continue
        hd = f"{n}" + (f" : {b['ret']}" if b["ret"] else "")
        rows = [["Dir", "Name", "Type", "Default", "Comment"]]
        for d, name, typ, dflt, com in b["members"]:
            rows.append([d, f"<font face='Courier'>{E(name)}</font>", f"<font face='Courier'>{E(typ)}</font>",
                         E(dflt), E(com)])
        S.append(KeepTogether([H(f"<font face='Courier'>{E(hd)}</font>  ({KIND_LONG[b['kind']]})", 3),
                               table(rows[:6], [17, 40, 28, 18, 67])]) if len(rows) <= 6 else H(f"<font face='Courier'>{E(hd)}</font>  ({KIND_LONG[b['kind']]})", 3))
        if len(rows) > 6:
            S.append(table(rows, [17, 40, 28, 18, 67]))

    # ================================================================= 5 Safety
    S.append(H("4  Safety summary", 0))
    S.append(P("Source: docs/CellSortingStation_SafetyConcept.pdf. Target: <b>PLr d</b>, category 3 behaviour (ISO 13849-1), "
               "stop categories per IEC 60204-1, E-stop per ISO 13850, interlocking per ISO 14119."))
    S.append(table([
        ["ID", "Function", "Behaviour", "Implemented in"],
        ["SF1", "Emergency stop, stop <b>category 0</b>", "Two-channel NC contacts. Either channel open removes SafetyOk and EnergyEnable in the same scan (dump valve / STO release). Alarm EStop, station ABORTED.", "FB_SafetyMonitor, FB_DualChannel dcEStop"],
        ["SF2", "Guard door, stop <b>category 1</b>", "Two-channel interlock. Door open: controlled stop, energy stays for Cat1Delay (<b>1 s</b>), then EnergyEnable FALSE. Alarm DoorOpen.", "FB_SafetyMonitor (tonCat1), dcDoor"],
        ["SF3", "Reset / restart prevention", "Reset only on the <b>falling edge</b> of the reset button with closed circuits. Button held longer than <b>5 s</b> counts as stuck (ResetStuck), its release does nothing. No automatic restart after power-up or after any trip.", "FB_SafetyMonitor region Reset_button / Release"],
        ["DC", "Two-channel discrepancy", "Channels that disagree for <b>500 ms</b> latch a discrepancy fault (welded contact, wire break). It can only be acknowledged after both channels were open together (proves both contacts still switch) and a reset.", "FB_DualChannel"],
    ], [10, 36, 88, 36]))
    S.append(Spacer(1, 4))
    S.append(P("<b>Important limit.</b> FB_SafetyMonitor is a <b>standard-PLC mirror</b> of the safety logic: an executable "
               "specification used for operation, HMI diagnostics and unit tests. It is not a safety function. On a real "
               "machine SF1 and SF2 must run in an <b>F-CPU</b> (STEP 7 Safety) with certified F-blocks and PROFIsafe F-I/O, for "
               "example ESTOP1 (E-stop), SFDOOR (guard door), FDBACK (feedback / start-up test) and ACK_GL (global acknowledge). "
               "The performance level (PLr d) would have to be verified there with the real components (MTTFd, DC, CCF) and "
               "validated by test; the unit tests in this project do not replace that."))
    S.append(P("PLC reaction in the station: any safety trip makes FC_AnyFault TRUE (SafetyOk FALSE or alarms), the station "
               "goes to ABORTED with text 'SAFETY STOP' and leaves it only through the safety reset followed by the normal "
               "Reset. FB_ProcessSim loses compressed air (AirOk := EnergyEnable) so simulated pushers cannot extend after a stop.", note))

    # ================================================================= 6 HMI
    S.append(H("5  HMI (WinCC Unified)", 0))
    S.append(H("5.1  Screen 'Station'", 1))
    design = json.loads((ROOT / "hmi" / "overview_design.json").read_text(encoding="utf-8"))
    sc = design["screen"]
    btn_texts = [(i["left"], i["top"], i["text"]) for i in design["items"] if i["type"] == "Button"]
    S.append(P(f"One dark, flat screen of {sc['Width']} x {sc['Height']} px, generated by hmi/build_overview.py and "
               "hmi/build_safety_items.py (design and binding plan as json, applied to TIA with the Openness tools). "
               "Layout from left to right:"))
    S += bullets([
        "<b>Left column, OPERATION:</b> START, STOP, RESET, BINS EMPTIED, RESET COUNTERS (momentary buttons bound to the Cmd_ tags) with a note that Stop acts at the end of the current cycle.",
        "<b>Left column, SIMULATION / SAFETY:</b> E-STOP (hold), JAM PUSHER B (hold), GUARD DOOR (toggle), WELD E-STOP CH.B (toggle), SAFETY RESET (acts on release; held more than 5 s is ignored).",
        "<b>Centre, PROCESS:</b> animated plant view: infeed, conveyor, measuring unit, bin B and reject bin with counts, cell present, pushers B / R, 'to module assembly'; status lamps for conveyor, cell present, measuring, stop pending.",
        "<b>Top right, STATE and PRODUCTION:</b> state text (Sts_StateText) and KPI tiles total cells, yield %, grade A, grade B, reject.",
        "<b>Bottom centre, LAST CELL:</b> cell id, voltage, resistance, grade (1 A / 2 B / 3 Reject).",
        "<b>Bottom right, ALARMS:</b> lamps for E-stop, pusher B, pusher Reject, measuring unit timeout, transport timeout, bin B full, reject bin full, plus the safety items (door, discrepancy, safety release, reset required).",
    ])
    S.append(P("Operating philosophy: the HMI only writes the Cmd_ bits and the parameters; the PLC clears the one-shot "
               "commands and publishes every status in the Sts_ structure. Colour semantics: green = running / ok, amber = "
               "warning (bin full), red = fault, grey = off.", note))
    S.append(H("5.2  Tag list", 1))
    tagfile = ROOT / "hmi" / "hmi_tags.json"
    if tagfile.exists():
        tj = json.loads(tagfile.read_text(encoding="utf-8"))
        tags = [(t["name"], t["member"], t["type"], t["address"]) for t in tj["tags"]]
        S.append(P(f"Source: hmi/hmi_tags.json. HMI device {E(tj.get('hmi_device', ''))}, tag table '{E(tj.get('tag_table', ''))}', "
                   f"connection {E(tj.get('connection', ''))} (non-integrated, absolute addressing) to DB {E(tj.get('db', ''))} "
                   f"(number {tj.get('db_number', '')}). {len(tags)} tags. CI recomputes the layout from the SCL "
                   "(tools/db_layout.py check) and fails if an address moved."))
        rows = [["HMI tag", "DB_HMI member", "Type", "Address"]]
        rows += [[f"<font face='Courier'>{E(a)}</font>", f"<font face='Courier'>{E(b)}</font>", E(c), f"<font face='Courier'>{E(d)}</font>"] for a, b, c, d in tags]
        S.append(table(rows, [44, 66, 18, 42]))
    else:
        bj = json.loads((ROOT / "hmi" / "overview_bindings.json").read_text(encoding="utf-8"))
        rows = [["Tag", "Used by item", "Kind"]]
        for kind in ("ioValues", "visible", "buttons"):
            for e in bj.get(kind, []):
                rows.append([f"<font face='Courier'>{E(e['tag'])}</font>", E(e["item"]), kind])
        S.append(P("hmi/hmi_tags.json was not present; tags are taken from overview_bindings.json (no addresses)."))
        S.append(table(rows, [60, 70, 40]))

    # ================================================================= 7 Verification
    S.append(H("6  Verification", 0))
    S.append(H("6.1  Test strategy", 1))
    S.append(P("The tests do not mock the PLC logic. <font face='Courier'>tests/scl_runtime.py</font> parses the <b>same .scl files</b> "
               "that are imported into TIA Portal and executes them scan by scan with a simulated clock (TON_TIME, R_TRIG, "
               "F_TRIG, structs, UDTs, FB and FC calls, integer wrap-around like the S7-1500). Each test gets a fresh PLC "
               "loaded from src/. Test cases are derived with systematic techniques (boundary value, equivalence classes, "
               "cause-effect, state transition, use case, glass box) and documented as a design table in the header of each "
               "test file. A decision-coverage gate (IF branches incl. implicit ELSE, CASE labels incl. ELSE) fails the run below 95 %."))
    S.append(H("6.2  Test files", 1))
    tdir = ROOT / "tests"
    files = sorted(tdir.glob("test_*.py"))
    rows = [["File", "Tests", "Subject"]]
    docs = {}
    for f in files:
        mod = ast.parse(f.read_text(encoding="utf-8"))
        d = ast.get_docstring(mod) or ""
        docs[f.name] = d
        first = d.split("\n")[0] if d else ""
        rows.append([f"<font face='Courier'>{E(f.name)}</font>", str(pt["per_file"].get(f.name, "?")), E(first)])
    rows.append(["<b>total</b>", f"<b>{sum(pt['per_file'].values()) or '?'}</b>", ""])
    S.append(table(rows, [44, 14, 112]))
    S.append(P("Support: tests/conftest.py (fixtures: fresh PLC, Station driver with run / press / safety_reset), "
               "tests/scl_runtime.py (SCL interpreter and coverage registry).", note))
    S.append(H("6.3  Design tables", 1))
    for f in files:
        d = docs[f.name]
        if not d:
            continue
        S.append(H(f"<font face='Courier'>{E(f.name)}</font>", 3))
        S.append(listing_plain(d))
        S.append(Spacer(1, 4))
    S.append(H("6.4  Result of the run", 1))
    S.append(P(f"The suite was executed while generating this document: <font face='Courier'>python -m pytest tests -q -p no:cacheprovider</font> "
               f"(working directory: project root, {DATE})."))
    S.append(listing_plain("\n".join(pt["lines"]) or "(no output)", 7.4))
    S.append(Spacer(1, 4))
    S.append(P(f"<b>Result:</b> <font face='Courier'>{E(pt['result'])}</font>"))
    if pt["cov"]:
        S.append(P(f"<b>SCL decision coverage:</b> <font face='Courier'>{E(pt['cov'])}</font>"))
    S.append(H("6.5  Limits (stated honestly)", 1))
    S += bullets([
        "<b>No PLCSIM and no real CPU:</b> the results are not cross-checked against a real S7-1500 or PLCSIM (no licence available). The runtime is a test tool for the SCL subset used here, not an emulator.",
        "<b>Scan model:</b> a scan takes zero time (the test chooses dt); no cycle-time / watchdog effects, no process image or I/O timing, no retentivity or warm-restart behaviour; intermediate expression results are not truncated, only the assigned value.",
        "<b>Coverage figure</b> is decision coverage of the SCL (branch outcomes), not MC/DC and not a proof of correctness. Uncovered outcomes are listed in the run output above.",
        "<b>Safety:</b> the tests verify the behaviour of the standard-PLC mirror against the specification. They are not the validation of a safety function; PL verification and validation belong to the F-program on an F-CPU.",
        "<b>Compile check:</b> the SCL was compiled in TIA Portal V20 through the deploy script (0 errors, 0 warnings, per deploy/RUNNER_SETUP.md); this document did not repeat that.",
    ])

    # ================================================================= 8 Versioning & CI/CD
    S.append(H("7  Versioning and CI/CD", 0))
    S.append(H("7.1  Block versioning", 1))
    S.append(P("Every block carries <font face='Courier'>VERSION : major.minor</font> (TIA block version, 0..15 each). "
               "<font face='Courier'>src/block_versions.json</font> stores per block the released version, the file and a fingerprint "
               "of the <b>interface</b> and of the <b>body</b>; comments and white space are ignored. "
               "tools/block_versions.py <i>check</i> is a CI gate:"))
    S.append(table([
        ["Change", "Required version", "Result"],
        ["Interface changed (declarations; includes interfaces of referenced UDTs / FBs)", "next major (x.y -> x+1.0)", "otherwise error"],
        ["Only the code changed", "at least next minor (x.y -> x.y+1)", "otherwise error"],
        ["Only comments / white space", "none", "no error"],
        ["Version raised but nothing changed", "-", "warning"],
        ["Version lower than released", "-", "error"],
        ["Manifest not up to date", "run <font face='Courier'>block_versions.py update</font>", "error"],
    ], [84, 54, 32]))
    S.append(Spacer(1, 4))
    vr = [["Block", "Kind", "Version", "Interface hash", "Body hash"]]
    for n, v in sorted(versions.items()):
        vr.append([f"<font face='Courier'>{E(n)}</font>", E(v["kind"]), ".".join(map(str, v["version"])),
                   f"<font face='Courier'>{E(v['interface'])}</font>", f"<font face='Courier'>{E(v['body'])}</font>"])
    S.append(P("Released manifest (from block_versions.json):"))
    S.append(table(vr, [38, 44, 16, 36, 36]))
    S.append(P("Changing a block: edit the SCL and raise VERSION, run <i>block_versions.py update</i>, run the tests, commit both.", note))
    S.append(H("7.2  Pipeline", 1))
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    rel = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    ci_steps = re.findall(r"^\s+- name:\s*(.+)$", ci, re.M)
    S.append(P("<b>ci.yml</b> runs on every push, pull request and manually, and is reused by the release workflow "
               "(workflow_call). It needs no TIA Portal. Steps in order:"))
    S += bullets([E(s.strip("'\"")) for s in ci_steps])
    S.append(P("<b>release.yml</b> is triggered by a tag <font face='Courier'>v*</font> or manually. Nothing is packaged or deployed if a test fails."))
    jobs = re.findall(r'^  (\w[\w\-]*):\n    name:\s*"?([^"\n]+)"?', rel, re.M)
    S.append(table([["Job", "Stage"]] + [[f"<font face='Courier'>{E(a)}</font>", E(b)] for a, b in jobs], [34, 136]))
    S += bullets([
        "<b>Stage 1 (test):</b> calls ci.yml: ASCII check, block versions, pytest with coverage gate, class diagram up to date, UML rendering.",
        "<b>Stage 2 (package):</b> collects SCL sources, block_versions.json, block-version table, PDFs, UML sources and rendered diagrams, HMI files and the deploy script into CellSortingStation-&lt;version&gt;.zip; creates a GitHub release for v* tags with the block version table as body.",
        "<b>Stage 3 (deploy-tia):</b> runs on a self-hosted Windows runner with labels [self-hosted, windows, tia-v20], only if the repository variable TIA_RUNNER_ENABLED is true, behind the optional environment 'plant-engineering' (manual approval). Calls deploy/Deploy-ToTia.ps1 (backup archive, import, pin DB_HMI, compile PLC and HMI, save) and uploads the resulting project archive as artifact and release asset.",
    ])
    S.append(H("7.3  Deploy script (deploy/Deploy-ToTia.ps1)", 1))
    S.append(P("Uses the TIA Portal Openness API directly (no MCP server). The assembly resolver is compiled C# because a "
               "PowerShell script block as AssemblyResolve handler ends in a StackOverflowException. Exit code 1 if the compile reports errors."))
    ps = (ROOT / "deploy" / "Deploy-ToTia.ps1").read_text(encoding="utf-8-sig")
    desc = ps.split(".DESCRIPTION", 1)[-1].split("#>", 1)[0]
    steps, curs = [], None
    for ln in desc.splitlines():
        m = re.match(r"^\s+(\d+)\.\s+(.*)$", ln)
        if m:
            curs = [m.group(2).strip()]
            steps.append(curs)
        elif curs is not None and ln.strip() and re.match(r"^\s{6,}\S", ln):
            curs.append(ln.strip())
        else:
            curs = None
    S += bullets([E(" ".join(x)) for x in steps])
    S.append(P("Runner requirements: Windows, TIA Portal V20 with STEP 7 and Openness, runner account in the local group "
               "'Siemens TIA Openness'. Use a copy of the project (Openness cannot open a project that is open in the TIA window). "
               "Because a self-hosted runner executes workflow code, the repository must be private or require approval for outside "
               "collaborators (deploy/RUNNER_SETUP.md). Tested manually on 2026-11-19 on a project copy (compile 0 errors / 0 warnings, project saved, see RUNNER_SETUP.md).", note))
    S.append(H("7.4  Tools", 1))
    rows = [["Tool", "Purpose"]]
    for f in sorted((ROOT / "tools").glob("*.py")):
        d = ast.get_docstring(ast.parse(f.read_text(encoding="utf-8"))) or ""
        rows.append([f"<font face='Courier'>tools/{E(f.name)}</font>", E(d.split("\n\n")[0].replace("\n", " "))])
    S.append(table(rows, [46, 124]))

    # ================================================================= 9 UML
    S.append(H("8  UML diagrams", 0))
    if uml:
        S.append(P("The diagrams are the PlantUML sources in docs/uml/*.puml, rendered for this document with "
                   "<font face='Courier'>java -jar tools/plantuml/plantuml.jar -Playout=smetana -tpng</font> into a temporary folder. "
                   "The class diagram is generated from the SCL by tools/scl_to_plantuml.py."))
        captions = {
            "01_class_blocks.puml": "Figure 1: Class diagram of blocks, UDTs and instances (generated from the SCL, with versions)",
            "02_state_station.puml": "Figure 2: Station mode / state machine (FB_SortStation)",
            "03_state_safety.puml": "Figure 3: Safety monitor states (SF1, SF2, SF3)",
            "04_sequence_estop.puml": "Figure 4: Sequence: E-stop pressed, reaction, recovery",
            "05_deployment.puml": "Figure 5: Deployment view (PLC, HMI, engineering station)",
            "06_activity_cicd.puml": "Figure 6: Activity diagram of the CI/CD pipeline",
        }
        avail_h = PAGE_H - TM - BM - 40
        for name, png in uml.items():
            iw, ih = ImageReader(str(png)).getSize()
            w = FW
            h = w * ih / iw
            if h > avail_h:
                h = avail_h
                w = h * iw / ih
            S.append(PageBreak())
            S.append(H(name.replace(".puml", ""), 1))
            im = Image(str(png), width=w, height=h)
            im.hAlign = "CENTER"
            S.append(im)
            S.append(P(captions.get(name, name), cap))
    else:
        S.append(P("<b>Rendering was not possible</b> (Java or tools/plantuml/plantuml.jar not available). The PlantUML sources "
                   "are included as listings instead."))
        for p in sorted((ROOT / "docs" / "uml").glob("*.puml")):
            S.append(H(p.name, 1))
            S.append(CodeListing(p.read_text(encoding="utf-8").split("\n"), "none"))

    # ================================================================= Appendix A
    S.append(PageBreak())
    S.append(H("Appendix A  Source code (SCL)", 0))
    S.append(P("Complete content of src/*.scl, block by block. Line numbers refer to the file. Keywords bold, comments grey italic. "
               "Long lines are wrapped (continuation lines are indented)."))
    for f in SOURCES:
        fb = [b for b in blocks if b["file"] == f]
        total = len((ROOT / "src" / f).read_text(encoding="utf-8").split("\n"))
        S.append(H(f"src/{f}  ({len(fb)} blocks, {total} lines)", 1))
        for b in fb:
            title = f"{b['name']}  ({KIND_LONG[b['kind']]}, v{b['version']}, lines {b['start']}-{b['end']})"
            S.append(H(f"<font face='Courier'>{E(title)}</font>", 2))
            S.append(CodeListing(b["lines"], "scl", first_no=b["start"]))
            S.append(Spacer(1, 4))

    # ================================================================= Appendix B
    S.append(PageBreak())
    S.append(H("Appendix B  Deployment and pipeline files", 0))
    for rel_path, lang in [("deploy/Deploy-ToTia.ps1", "ps1"), (".github/workflows/ci.yml", "yaml"),
                           (".github/workflows/release.yml", "yaml")]:
        txt = (ROOT / rel_path).read_text(encoding="utf-8-sig").split("\n")
        if txt and txt[-1] == "":
            txt.pop()
        S.append(H(f"<font face='Courier'>{E(rel_path)}</font>  ({len(txt)} lines)", 1))
        S.append(CodeListing(txt, lang))
        S.append(Spacer(1, 6))

    # ---- build
    doc = Doc(OUT, pagesize=A4, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
              title=TITLE, author="", subject="S7-1500 / TIA Portal V20 pilot project", creator="docs/project_documentation.py")
    fr = Frame(LM, BM, FW, PAGE_H - TM - BM, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("title", [fr], onPage=title_page), PageTemplate("main", [fr], onPage=deco)])
    doc.multiBuild(S)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"written {OUT}")
    print("pytest:", pt["result"], "|", pt["cov"])
    print("uml rendered:", len(uml))


if __name__ == "__main__":
    build()
