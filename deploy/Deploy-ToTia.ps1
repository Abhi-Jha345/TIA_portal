<#
.SYNOPSIS
  CD stage 3: import the SCL external sources into a TIA Portal V20 project, regenerate the
  blocks, compile and save. Exit code 1 if the compile reports errors (the pipeline fails).

.DESCRIPTION
  Uses the TIA Portal Openness API directly (no MCP server). Steps, same as done manually:
    1. open the project (TIA without user interface)
    2. delete the blocks and data types that are generated from src/*.scl
       (GenerateBlocksFromSource does not overwrite existing blocks)
    3. replace the external sources, generate blocks in dependency order (types, blocks, OB)
    4. compile the PLC software, print every message, save on success

  Requirements on the runner: Windows, TIA Portal V20 with STEP 7 and Openness installed,
  runner account member of the local group "Siemens TIA Openness".

  STATUS: written for the pipeline, NOT yet executed on a runner. Validate it once on a copy
  of the project before enabling stage 3 (repository variable TIA_RUNNER_ENABLED).
#>
param(
    [Parameter(Mandatory)] [string] $ProjectPath,
    [string] $TiaInstallPath = 'C:\Program Files\Siemens\Automation\Portal V20',
    [string] $PlcName = 'PLC_1',
    [string] $SourceDir = (Join-Path $PSScriptRoot '..\src')
)
$ErrorActionPreference = 'Stop'

$sources = @('01_Types.scl', '02_Blocks.scl', '03_OB.scl')     # generation order matters
Add-Type -Path (Join-Path $TiaInstallPath 'PublicAPI\V20\Siemens.Engineering.dll')

function Get-Service([object] $obj, [type] $serviceType) {
    # PowerShell cannot call the generic GetService<T>() directly
    $obj.GetType().GetMethod('GetService').MakeGenericMethod($serviceType).Invoke($obj, $null)
}

function Get-GeneratedNames([string[]] $files) {
    # names of all blocks / types declared in the sources
    $names = @{ Blocks = @(); Types = @() }
    foreach ($f in $files) {
        foreach ($m in [regex]::Matches((Get-Content -Raw $f),
                '(?m)^(FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK|TYPE)\s+"([^"]+)"')) {
            if ($m.Groups[1].Value -eq 'TYPE') { $names.Types += $m.Groups[2].Value }
            else { $names.Blocks += $m.Groups[2].Value }
        }
    }
    $names
}

$tia = $null
try {
    $tia = New-Object Siemens.Engineering.TiaPortal ([Siemens.Engineering.TiaPortalMode]::WithoutUserInterface)
    $project = $tia.Projects.Open([System.IO.FileInfo] $ProjectPath)
    Write-Host "Opened $ProjectPath"

    $plcSoftware = $null
    foreach ($device in $project.Devices) {
        foreach ($item in $device.DeviceItems) {
            $container = Get-Service $item ([Siemens.Engineering.HW.Features.SoftwareContainer])
            if ($container -and $container.Software.Name -eq $PlcName) { $plcSoftware = $container.Software }
        }
    }
    if (-not $plcSoftware) { throw "PLC software '$PlcName' not found" }

    $files = $sources | ForEach-Object { Join-Path $SourceDir $_ }
    $names = Get-GeneratedNames $files

    # 2. delete generated objects (blocks first, then types)
    foreach ($block in @($plcSoftware.BlockGroup.Blocks)) {
        if ($names.Blocks -contains $block.Name) { Write-Host "delete block $($block.Name)"; $block.Delete() }
    }
    foreach ($type in @($plcSoftware.TypeGroup.Types)) {
        if ($names.Types -contains $type.Name) { Write-Host "delete type  $($type.Name)"; $type.Delete() }
    }

    # 3. replace sources and generate
    $extSources = $plcSoftware.ExternalSourceGroup.ExternalSources
    foreach ($f in $files) {
        $name = [System.IO.Path]::GetFileNameWithoutExtension($f)
        $old = $extSources.Find($name)
        if ($old) { $old.Delete() }
        $src = $extSources.CreateFromFile($name, $f)
        Write-Host "generate blocks from $name"
        $src.GenerateBlocksFromSource()
    }

    # 4. compile
    $compiler = Get-Service $plcSoftware ([Siemens.Engineering.Compiler.ICompilable])
    $result = $compiler.Compile()
    function Write-Messages($messages, $indent) {
        foreach ($m in $messages) {
            Write-Host ("{0}[{1}] {2} {3}" -f $indent, $m.State, $m.Path, $m.Description)
            Write-Messages $m.Messages ($indent + '  ')
        }
    }
    Write-Messages $result.Messages ''
    Write-Host "Compile: $($result.State)  errors=$($result.ErrorCount)  warnings=$($result.WarningCount)"
    if ($result.ErrorCount -gt 0) { throw 'compile errors - project NOT saved' }

    $project.Save()
    Write-Host 'Project saved.'
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($tia) { $tia.Dispose() }
}
