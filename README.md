# Battery Cell Test & Sort Station - S7-1500 PLC pilot

SIMATIC S7-1500 (CPU 1516-3 PN/DP), TIA Portal V20, SCL, WinCC Unified PC RT.
Cells are measured (voltage, internal resistance), graded A / B / Reject and sorted by two
pneumatic pushers. Includes mode handling (PackML inspired), a step chain, fault reaction,
safety functions (E-stop stop cat. 0, guard door stop cat. 1, reset on release, two-channel
discrepancy monitoring) and a plant simulation for testing without hardware.

| Folder | Content |
|---|---|
| `src/` | SCL external sources imported into TIA Portal, `block_versions.json` |
| `tests/` | unit tests that execute the real SCL in a scan-based test runtime |
| `tools/` | block version check, DB_HMI layout / HMI address check, SCL ASCII check, UML generator |
| `docs/` | design sheet, safety concept, project documentation, UML (`docs/uml/*.puml`) |
| `hmi/` | WinCC Unified screen design, `hmi_tags.json` (42 HMI tags with absolute addresses) |
| `hw/` | hardware configuration as AutomationML (CAx export of the PLC and PC station) |
| `deploy/` | Openness script: backup, import, pin DB_HMI, compile PLC + HMI, archive (self-hosted runner) |
| `.github/workflows/` | CI on every push, release pipeline on `v*` tags; Dependabot for pinned actions |

## Run the checks locally

```
pip install -r tests/requirements.txt
python tools/check_scl_ascii.py
python tools/block_versions.py check
python tools/db_layout.py check          # HMI tag addresses = computed DB_HMI layout
python -m pytest tests -q
python tools/scl_to_plantuml.py          # regenerate the class diagram
```

## Changing a block

1. Edit the block in `src/*.scl` and raise its `VERSION`
   (interface change: next major `2.0`, code only: next minor `1.1`).
2. `python tools/block_versions.py update`
3. Run the tests, commit both files.

A changed UDT changes the interface of every block that uses it, so those blocks need a new
major version too (the check lists them). Inserting a member into `DB_HMI` shifts the absolute
HMI addresses: `tools/db_layout.py check` fails until `hmi/hmi_tags.json` and the HMI tags in
TIA are updated (`python tools/db_layout.py` prints the new layout).

## Pipeline safeguards

- `main` is protected: the check *SCL checks and unit tests* must pass, no force push / delete.
- Workflows from fork pull requests need approval (the self-hosted runner is on this laptop).
- All actions are pinned to commit SHAs; the PlantUML jar is verified by SHA-256.
- Every deployment archives the TIA project before (`*_before_*.zap20`) and after the change;
  the deployed archive is attached to the GitHub release. `DB_HMI` is pinned to DB1.

## Known limits

- No PLCSIM licence: the test runtime is not cross-checked against a real CPU, and the
  pipeline compiles a project copy but does not download to a CPU.
- The runtime models integer wrap on assignment, not cycle time, retentivity or I/O timing.

## Note on safety

The safety functions are a standard-PLC mirror of the intended F-program (executable
specification, diagnostics, tests). On a real machine they must run in an F-CPU with
certified F-blocks and PROFIsafe F-I/O; see `docs/CellSortingStation_SafetyConcept.pdf`.
