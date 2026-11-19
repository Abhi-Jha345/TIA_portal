"""Absolute addresses of a non-optimized ("standard") data block, computed from the SCL source.

Why: the WinCC Unified connection to the S7-1500 is non-integrated on V20, so the HMI tags
address DB_HMI absolutely (%DB1.DBX58.4, %DB1.DBD62, ...). Inserting one member in front of
another silently shifts every following address and the HMI shows wrong values. CI therefore
recomputes the layout from src/*.scl and compares it with hmi/hmi_tags.json.

S7 standard memory layout rules implemented here:
  * Bool                    : next free bit; consecutive Bools share a byte (bit 0..7)
  * Byte, Char, SInt, USInt : next free byte (no alignment)
  * every other elementary type (Int, Word, DInt, Real, Time, ...) : next EVEN byte
  * String[n]               : n + 2 bytes (max length, actual length, chars), even byte
  * Struct / UDT            : starts at an even byte, its size is rounded up to even
  * Arrays are not used in DB_HMI and are rejected (no silent guessing)

Usage:
  python tools/db_layout.py               # print the DB_HMI layout
  python tools/db_layout.py check         # CI gate: hmi/hmi_tags.json matches the layout
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "src" / "01_Types.scl", ROOT / "src" / "02_Blocks.scl"]
TAGS = ROOT / "hmi" / "hmi_tags.json"
BINDINGS = ROOT / "hmi" / "overview_bindings.json"

_SIZES = {"BYTE": 1, "CHAR": 1, "SINT": 1, "USINT": 1,
          "INT": 2, "UINT": 2, "WORD": 2, "DATE": 2,
          "DINT": 4, "UDINT": 4, "DWORD": 4, "REAL": 4, "TIME": 4, "TOD": 4,
          "LREAL": 8, "LINT": 8, "ULINT": 8, "LWORD": 8}
# HMI address width letter per PLC type (Bool and String use the bit form DBX)
_WIDTH = {1: "B", 2: "W", 4: "D"}
_COMPATIBLE = {"Bool": {"BOOL"}, "Int": {"INT"}, "DInt": {"DINT"}, "Real": {"REAL"},
               "String": {"STRING"}, "Word": {"WORD"}, "Byte": {"BYTE"}}

_DECL = re.compile(r'^\s*([A-Za-z_]\w*)\s*:\s*("[^"]+"|Struct\b|[A-Za-z_]\w*(?:\s*\[\s*\d+\s*\])?)',
                   re.IGNORECASE)


def _strip(text):
    text = re.sub(r"\(\*.*?\*\)", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"\{[^}]*\}", "", text)


def _parse_members(lines, pos):
    """Parse declarations until END_STRUCT / END_VAR. Returns ([(name, type)], next_pos)."""
    members = []
    while pos < len(lines):
        line = lines[pos].strip()
        pos += 1
        if not line:
            continue
        if re.match(r"END_(STRUCT|VAR)\b", line, re.IGNORECASE):
            return members, pos
        m = _DECL.match(line)
        if not m:
            raise ValueError(f"cannot parse declaration: {line!r}")
        name, typ = m.group(1), m.group(2)
        if typ.upper() == "STRUCT":
            sub, pos = _parse_members(lines, pos)
            members.append((name, ("struct", sub)))
        elif "ARRAY" in line.upper():
            raise ValueError(f"{name}: arrays are not supported by the layout calculator")
        else:
            members.append((name, ("named", typ.strip('"'))))
    raise ValueError("missing END_STRUCT / END_VAR")


def parse_declarations(paths=SOURCES):
    """Return ({udt_name: members}, {db_name: members}) for UDTs and global DBs."""
    udts, dbs = {}, {}
    for path in paths:
        lines = _strip(pathlib.Path(path).read_text(encoding="utf-8")).splitlines()
        for i, line in enumerate(lines):
            m = re.match(r'\s*(TYPE|DATA_BLOCK)\s+"([^"]+)"', line)
            if not m:
                continue
            start = next(j for j in range(i + 1, len(lines))
                         if re.match(r"\s*(STRUCT|VAR)\b", lines[j], re.IGNORECASE)
                         or re.match(r'\s*"', lines[j]))
            if re.match(r'\s*"', lines[start]):        # instance DB "x" : "FB" - no layout here
                continue
            members, _ = _parse_members(lines, start + 1)
            (udts if m.group(1) == "TYPE" else dbs)[m.group(2)] = members
    return udts, dbs


class _Cursor:
    def __init__(self):
        self.byte, self.bit = 0, 0

    def close_bits(self):
        if self.bit:
            self.byte, self.bit = self.byte + 1, 0

    def align_even(self):
        self.close_bits()
        self.byte += self.byte % 2


def layout(members, udts, prefix="", cur=None):
    """Return {member_path: (plc_type, byte, bit)} for all elementary members."""
    cur = cur or _Cursor()
    out = {}
    for name, (kind, info) in members:
        path = f"{prefix}{name}"
        if kind == "struct" or info in udts:
            cur.align_even()
            out.update(layout(info if kind == "struct" else udts[info], udts, path + ".", cur))
            cur.align_even()                              # struct size rounded up to even
            continue
        typ = info.upper().replace(" ", "")
        if typ == "BOOL":
            out[path] = ("BOOL", cur.byte, cur.bit)
            cur.bit += 1
            if cur.bit == 8:
                cur.byte, cur.bit = cur.byte + 1, 0
            continue
        string = re.fullmatch(r"STRING(?:\[(\d+)\])?", typ)
        if string:
            cur.align_even()
            out[path] = ("STRING", cur.byte, 0)
            cur.byte += int(string.group(1) or 254) + 2
            continue
        if typ not in _SIZES:
            raise ValueError(f"{path}: data type {info} not supported")
        size = _SIZES[typ]
        cur.close_bits() if size == 1 else cur.align_even()
        out[path] = (typ, cur.byte, 0)
        cur.byte += size
    return out


def address(db_number, plc_type, byte, bit):
    if plc_type in ("BOOL", "STRING"):
        return f"%DB{db_number}.DBX{byte}.{bit}"
    return f"%DB{db_number}.DB{_WIDTH[_SIZES[plc_type]]}{byte}"


def check(tags_file=TAGS, bindings_file=BINDINGS, sources=SOURCES):
    """Return a list of error strings (empty = HMI tags consistent with the DB layout)."""
    spec = json.loads(pathlib.Path(tags_file).read_text(encoding="utf-8"))
    udts, dbs = parse_declarations(sources)
    if spec["db"] not in dbs:
        return [f"DB {spec['db']} not found in the sources"]
    lay = layout(dbs[spec["db"]], udts)
    errors = []
    for tag in spec["tags"]:
        name, member = tag["name"], tag["member"]
        if member not in lay:
            errors.append(f"{name}: member {spec['db']}.{member} does not exist")
            continue
        plc_type, byte, bit = lay[member]
        if plc_type not in _COMPATIBLE.get(tag["type"], set()):
            errors.append(f"{name}: HMI type {tag['type']} does not match PLC type {plc_type}")
        expected = address(spec["db_number"], plc_type, byte, bit)
        if tag["address"] != expected:
            errors.append(f"{name}: address {tag['address']} but {member} is at {expected}")
    errors += _check_bindings(spec, bindings_file)
    return errors


def _check_bindings(spec, bindings_file):
    """Every tag the screen generator binds must be declared in hmi_tags.json."""
    path = pathlib.Path(bindings_file)
    if not path.exists():
        return []
    known = {t["name"] for t in spec["tags"]}
    used = {b["tag"] for group in json.loads(path.read_text(encoding="utf-8")).values()
            for b in group if isinstance(b, dict) and "tag" in b}
    return [f"screen binds unknown HMI tag {t}" for t in sorted(used - known)]


def main(argv):
    if len(argv) > 1 and argv[1] == "check":
        errors = check()
        for e in errors:
            print("ERROR " + e)
        if errors:
            return 1
        n = len(json.loads(TAGS.read_text(encoding="utf-8"))["tags"])
        print(f"OK: {n} HMI tags match the computed DB_HMI layout")
        return 0
    udts, dbs = parse_declarations()
    for member, (typ, byte, bit) in layout(dbs["DB_HMI"], udts).items():
        print(f"{address(1, typ, byte, bit):<18} {typ:<7} {member}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
