# Hardware configuration (AutomationML / CAx export)

Exported from the TIA Portal V20 project with Openness (`ExportDeviceAml`) on 2026-11-19, so
the hardware is versioned next to the code and can be re-created in an empty project
(TIA Portal: *Tools > Import CAx data*).

| File | Content |
|---|---|
| `PLC_station.aml` | S7-1500 station: CPU 1516-3 PN/DP 6ES7516-3AN02-0AB0 FW V2.9 (`PLC_1`), PROFINET interface X1 192.168.0.1 on subnet `PN_IE_1`, X2 192.168.1.1, default tag table |
| `HMI_PC_station.aml` | PC station `PC-System_1`: IE general 192.168.0.2 on `PN_IE_1` |

Limits:
- The CAx export skips the WinCC Unified runtime item `HMI_RT_1` (TIA reports *"Unable to
  process device item 'HMI_RT_1'"*). It has to be inserted by hand once (WinCC Unified PC RT V20)
  after the import. Its content is reproducible from the repository:
  - HMI tags + absolute addresses: `hmi/hmi_tags.json` (checked against the DB layout in CI)
  - screen "Station": `hmi/build_overview.py`, `hmi/build_safety_items.py`, `hmi/overview_*.json`
- The HMI connection `HMI_Connection_1` (non-integrated) is not part of the CAx data.
- The complete project state is additionally kept as a `.zap20` archive: the deploy script
  archives the project before and after every deployment, and the release pipeline attaches
  the deployed archive to the GitHub release.

Re-export after hardware changes (TIA project open, MCP server or Openness):
`ExportDeviceAml(devicePath: "S7-1500/ET200MP station_1", exportPath: "hw/PLC_station.aml")`.
