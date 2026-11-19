# Battery Cell Test & Sort Station - S7-1500 PLC pilot

SIMATIC S7-1500 (CPU 1516-3 PN/DP), TIA Portal V20, SCL, WinCC Unified PC RT.
Cells are measured (voltage, internal resistance), graded A / B / Reject and sorted by two
pneumatic pushers. Includes mode handling (PackML inspired), a step chain, fault reaction,
safety functions (E-stop stop cat. 0, guard door stop cat. 1, reset on release, two-channel
discrepancy monitoring) and a plant simulation for testing without hardware.

| Folder | Content |
|---|---|
| `src/` | SCL external sources imported into TIA Portal, `block_versions.json` |
| `tests/` | 84 unit tests that execute the real SCL in a scan-based test runtime |
| `tools/` | block version check, SCL ASCII check, UML generator |
| `docs/` | design sheet, safety concept, UML (`docs/uml/*.puml`) |
| `hmi/` | WinCC Unified screen design |
| `deploy/` | Openness script: import, generate, compile in TIA (self-hosted runner) |
| `.github/workflows/` | CI on every push, release pipeline on `v*` tags |

## Run the checks locally

```
pip install -r tests/requirements.txt
python tools/check_scl_ascii.py
python tools/block_versions.py check
python -m pytest tests -q
python tools/scl_to_plantuml.py          # regenerate the class diagram
```

## Changing a block

1. Edit the block in `src/*.scl` and raise its `VERSION`
   (interface change: next major `2.0`, code only: next minor `1.1`).
2. `python tools/block_versions.py update`
3. Run the tests, commit both files.

## Note on safety

The safety functions are a standard-PLC mirror of the intended F-program (executable
specification, diagnostics, tests). On a real machine they must run in an F-CPU with
certified F-blocks and PROFIsafe F-I/O; see `docs/CellSortingStation_SafetyConcept.pdf`.
