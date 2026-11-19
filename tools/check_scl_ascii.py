"""CI check: SCL external sources must be pure ASCII.

TIA Portal reads a .scl external source without BOM in the system code page, so any
non-ASCII character (umlaut, en dash, typographic quote) is imported as garbage and can
break the block generation. Exit code 1 lists every offending line.
"""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent.parent / "src"
bad = []
for path in sorted(root.glob("*.scl")):
    for no, line in enumerate(path.read_bytes().split(b"\n"), start=1):
        if any(b > 127 for b in line):
            bad.append(f"{path.name}:{no}: {line.decode('utf-8', 'replace').strip()}")

if bad:
    print("Non-ASCII characters in SCL sources:")
    print("\n".join(bad))
    sys.exit(1)
print(f"OK: {len(list(root.glob('*.scl')))} SCL files are pure ASCII")
