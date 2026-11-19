# Self-hosted runner for CD stage 3 (TIA import + compile)

Stage 3 of `.github/workflows/release.yml` runs on this laptop. Do these steps once.

## 1. Secure the repository first

The repository is public. With a self-hosted runner, a pull request from anyone could change
a workflow to execute code on this machine. Choose one:

- **Recommended:** make the repository private
  (Settings > General > Danger Zone > Change visibility).
- Or keep it public and set Settings > Actions > General >
  "Fork pull request workflows from outside collaborators" to
  **Require approval for all outside collaborators**.

## 2. Register the runner (interactive mode)

1. GitHub: Settings > Actions > Runners > **New self-hosted runner** > Windows x64.
   Follow the download commands shown there into `C:\actions-runner`
   (the page contains the exact version and SHA-256 to verify).
2. Configure with the labels the workflow expects (token comes from that page, valid 1 h):
   ```
   .\config.cmd --url https://github.com/Abhi-Jha345/TIA_portal --token <TOKEN> ^
                --labels tia-v20 --name tia-laptop --unattended
   ```
   (`self-hosted` and `windows` labels are added automatically.)
3. Start it only when you want deployments: `.\run.cmd`
   It runs as your user, which is a member of "Siemens TIA Openness". Stop with Ctrl+C.

## 3. Repository variables (Settings > Secrets and variables > Actions > Variables)

| Variable | Value |
|---|---|
| `TIA_RUNNER_ENABLED` | `true` |
| `TIA_INSTALL_PATH` | `D:\siemens\tia\Portal V20` |
| `TIA_PROJECT_PATH` | path to a **copy** of the project, e.g. `D:\siemens\deploy-target\CellSortingStation\CellSortingStation.ap20` |

Use a copy: Openness cannot open a project that is already open in the TIA Portal window.

Optional: Settings > Environments > `plant-engineering` > Required reviewers = you,
so every deployment waits for your approval.

## 4. First run - test the script by hand

`Deploy-ToTia.ps1` has not been executed on a runner yet. Try it once manually on the copy:

```
powershell -ExecutionPolicy Bypass -File deploy\Deploy-ToTia.ps1 ^
  -ProjectPath "D:\siemens\deploy-target\CellSortingStation\CellSortingStation.ap20" ^
  -TiaInstallPath "D:\siemens\tia\Portal V20"
```

Expected end of output: `Compile: Success errors=0 warnings=0` and `Project saved.`

## 5. Deploy

```
git tag v1.0.0
git push origin v1.0.0
```

The release workflow runs the tests, builds the release package and then, on this laptop,
imports the sources into the project copy, compiles and saves it.
