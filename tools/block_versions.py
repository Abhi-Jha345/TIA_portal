"""Block versioning for the SCL sources (FB, FC, DB, OB, UDT).

Every block carries `VERSION : major.minor` (TIA Portal block version, 0..15 each).
The manifest src/block_versions.json stores, per block, the released version and a
fingerprint of its INTERFACE (declarations) and its BODY (code). Comments and white space
are ignored, so editing comments needs no new version.

Rules enforced by `check` (used in CI):
  * interface changed          -> major must increase (x.y -> x+1.0)  breaking change
  * only the code changed      -> version must increase (minor at least)
  * version changed, no change -> warning only
  * version lower than before  -> error
  * new block                  -> ok (listed); removed block -> listed
  * manifest not up to date    -> error ("run: python tools/block_versions.py update")

Usage:
  python tools/block_versions.py check            # CI gate, exit 1 on violation
  python tools/block_versions.py update           # after a valid bump: rewrite the manifest
  python tools/block_versions.py table            # markdown table (release notes)
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
MANIFEST = SRC / "block_versions.json"
SOURCES = ["01_Types.scl", "02_Blocks.scl", "03_OB.scl"]

_HEADER = re.compile(r'^(FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK|TYPE)\s+"([^"]+)"',
                     re.MULTILINE)
_VERSION = re.compile(r"^\s*VERSION\s*:\s*(\d+)\.(\d+)\s*$", re.MULTILINE)


def _normalise(text):
    text = re.sub(r"\(\*.*?\*\)", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"\{[^}]*\}", "", text)                 # attributes like S7_Optimized_Access
    text = _VERSION.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _digest(text):
    return hashlib.sha256(_normalise(text).encode()).hexdigest()[:16]


def parse_blocks(src_dir=SRC, files=SOURCES):
    """Return {name: {kind, version(tuple), interface, body, file}} for all blocks."""
    blocks = {}
    for fname in files:
        text = (src_dir / fname).read_text(encoding="utf-8")
        starts = list(_HEADER.finditer(text))
        for m in starts:
            kind, name = m.group(1), m.group(2)
            end = text.find("END_" + kind, m.end())
            if end < 0:
                raise ValueError(f"{fname}: block {name} has no END_{kind}")
            chunk = text[m.start():end]
            ver = _VERSION.search(chunk)
            if not ver:
                raise ValueError(f"{fname}: block {name} has no VERSION")
            version = (int(ver.group(1)), int(ver.group(2)))
            if not all(0 <= v <= 15 for v in version):
                raise ValueError(f"{fname}: block {name} VERSION {version} outside 0.0..15.15")
            head, sep, body = chunk.partition("\nBEGIN")
            if kind == "TYPE":
                head, body = chunk, ""
            blocks[name] = {"kind": kind, "version": version, "file": fname,
                            "interface": _digest(head[m.end() - m.start():]),
                            "body": _digest(body)}
    return blocks


def load_manifest(path=MANIFEST):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    for b in data.values():
        b["version"] = tuple(b["version"])
    return data


def compare(current, released):
    """Return (errors, notes) for the current sources against the released manifest."""
    errors, notes = [], []
    for name, cur in sorted(current.items()):
        old = released.get(name)
        if old is None:
            notes.append(f"NEW      {name} {fmt(cur['version'])}")
            continue
        iface_changed = cur["interface"] != old["interface"]
        body_changed = cur["body"] != old["body"]
        cv, ov = cur["version"], old["version"]
        if cv < ov:
            errors.append(f"{name}: version {fmt(cv)} is lower than released {fmt(ov)}")
        elif iface_changed and cv[0] <= ov[0]:
            errors.append(f"{name}: INTERFACE changed -> major version must increase "
                          f"(released {fmt(ov)}, now {fmt(cv)}, expected >= {ov[0] + 1}.0)")
        elif body_changed and cv <= ov:
            errors.append(f"{name}: code changed -> version must increase "
                          f"(released {fmt(ov)}, expected >= {ov[0]}.{ov[1] + 1})")
        elif (iface_changed or body_changed) and cv > ov:
            notes.append(f"BUMPED   {name} {fmt(ov)} -> {fmt(cv)} "
                         f"({'interface' if iface_changed else 'code'} change)")
        elif cv != ov:
            notes.append(f"WARNING  {name} {fmt(ov)} -> {fmt(cv)} without any change")
    for name in sorted(set(released) - set(current)):
        notes.append(f"REMOVED  {name} (was {fmt(released[name]['version'])})")
    return errors, notes


def fmt(v):
    return f"{v[0]}.{v[1]}"


def _manifest_text(current):
    data = {n: {k: (list(v) if k == "version" else v) for k, v in b.items()}
            for n, b in sorted(current.items())}
    return json.dumps(data, indent=2) + "\n"


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    current = parse_blocks()
    released = load_manifest()
    errors, notes = compare(current, released)
    for n in notes:
        print(n)
    if cmd == "table":
        print("| Block | Type | Version |\n|---|---|---|")
        for name, b in sorted(current.items()):
            print(f"| {name} | {b['kind']} | {fmt(b['version'])} |")
        return 0
    if errors:
        print("\nVERSION ERRORS:")
        for e in errors:
            print("  " + e)
        return 1
    if cmd == "update":
        MANIFEST.write_text(_manifest_text(current), encoding="utf-8")
        print(f"manifest written: {len(current)} blocks")
        return 0
    if _manifest_text(current) != (MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""):
        print("\nManifest is not up to date: run  python tools/block_versions.py update  and commit it.")
        return 1
    print(f"OK: {len(current)} blocks, versions consistent with the manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
