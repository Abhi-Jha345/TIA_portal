<#
.SYNOPSIS
  CD stage 3: import the SCL external sources into a TIA Portal V20 project, regenerate the
  blocks, compile and save. Exit code 1 if the compile reports errors (the pipeline fails).

.DESCRIPTION
  Uses the TIA Portal Openness API directly (no MCP server). Steps:
    1. open the project (TIA without user interface) and ARCHIVE it (.zap20) as a backup
       before anything is changed
    2. delete the blocks and data types that are generated from src/*.scl
       (GenerateBlocksFromSource does not overwrite existing blocks)
    3. replace the external sources, generate blocks in dependency order (types, blocks, OB)
    4. PIN the HMI interface DB to the number the HMI tags use (hmi/hmi_tags.json, DB1):
       the HMI connection is non-integrated, its tags address %DB1... absolutely
    5. compile the PLC software and the HMI, print every message; fail on any error
    6. save and archive the result (path written to GITHUB_OUTPUT 'archive' for the pipeline)
  To restore: TIA Portal > Project > Retrieve > select the *_before_*.zap20 archive.

  Requirements on the runner: Windows, TIA Portal V20 with STEP 7 and Openness installed,
  runner account member of the local group "Siemens TIA Openness".

  STATUS: tested 2026-11-19 on a copy of the project with TIA Portal V20: backup archive,
  15 objects regenerated, DB_HMI pinned to DB1, PLC compile 0 errors / 0 warnings, saved,
  archived. The HMI compile step runs and currently FAILS on purpose: the WinCC Unified runtime
  settings password of HMI_RT_1 is not set (2 errors) - set it in TIA, or set the repository
  variable TIA_HMI_NAME = none to skip the HMI compile.
#>
param(
    [Parameter(Mandatory)] [string] $ProjectPath,
    [string] $TiaInstallPath = 'C:\Program Files\Siemens\Automation\Portal V20',
    [string] $PlcName = 'PLC_1',
    [string] $SourceDir = '',                            # default: <repo>\src
    [string] $HmiName = 'HMI_RT_1',                      # '' or 'none' = skip the HMI compile
    [string] $HmiTagsFile = '',                          # default: <repo>\hmi\hmi_tags.json
    [string] $BackupDir = '',                            # default: <project folder>\..\backups
    [string] $Label = 'manual',                          # e.g. the release tag
    [int]    $KeepBackups = 10
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1: $PSScriptRoot is empty inside param() defaults, so resolve here
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $SourceDir) { $SourceDir = Join-Path $scriptDir '..\src' }
if (-not $HmiTagsFile) { $HmiTagsFile = Join-Path $scriptDir '..\hmi\hmi_tags.json' }
# Openness rejects paths containing '..' (CreateFromFile: 'method is not supported')
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
$HmiTagsFile = [System.IO.Path]::GetFullPath($HmiTagsFile)

$sources = @('01_Types.scl', '02_Blocks.scl', '03_OB.scl')     # generation order matters
# Openness: load the API with LoadFrom and resolve its dependencies from the TIA folders
# (Add-Type would enumerate all types and fail on dependencies it cannot locate).
# The resolver is compiled C#: a PowerShell script block as AssemblyResolve handler recurses
# into assembly resolution itself and ends in a StackOverflowException.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Reflection;
public static class TiaAssemblyResolver {
    private static string[] _dirs;
    public static void Register(string[] dirs) {
        _dirs = dirs;
        AppDomain.CurrentDomain.AssemblyResolve += Resolve;
    }
    private static Assembly Resolve(object sender, ResolveEventArgs args) {
        string name = new AssemblyName(args.Name).Name;
        if (name.EndsWith(".resources")) return null;
        foreach (string dir in _dirs) {
            string candidate = Path.Combine(dir, name + ".dll");
            if (File.Exists(candidate)) return Assembly.LoadFrom(candidate);
        }
        return null;
    }
}
'@
[TiaAssemblyResolver]::Register(@((Join-Path $TiaInstallPath 'PublicAPI\V20'),
                                  (Join-Path $TiaInstallPath 'Bin\PublicAPI'),
                                  (Join-Path $TiaInstallPath 'Bin')))
[void][System.Reflection.Assembly]::LoadFrom((Join-Path $TiaInstallPath 'PublicAPI\V20\Siemens.Engineering.dll'))

function Get-Service([object] $obj, [type] $serviceType) {
    # PowerShell cannot call the generic GetService<T>() directly. Call it through the interface:
    # some objects (e.g. WinCC Unified device items) implement it explicitly, so
    # $obj.GetType().GetMethod('GetService') returns $null for them.
    # Objects that are no service provider at all (e.g. the WinCC Unified HmiSoftware) give $null.
    if ($obj -isnot [Siemens.Engineering.IEngineeringServiceProvider]) { return $null }
    [Siemens.Engineering.IEngineeringServiceProvider].GetMethod('GetService').
        MakeGenericMethod($serviceType).Invoke($obj, $null)
}

function Get-AllBlocks($group) {
    foreach ($b in $group.Blocks) { $b }
    foreach ($g in $group.Groups) { Get-AllBlocks $g }
}

function Find-Software($project, [string] $name) {
    # returns @(software, device item, device) of the software with that name, or $null
    foreach ($device in $project.Devices) {
        foreach ($item in $device.DeviceItems) {
            $container = Get-Service $item ([Siemens.Engineering.HW.Features.SoftwareContainer])
            if ($container -and $container.Software.Name -eq $name) {
                return ,@($container.Software, $item, $device)
            }
        }
    }
    $null
}

function Save-Archive($project, [string] $dir, [string] $name) {
    # .zap20 = compressed project archive, restorable with Project > Retrieve
    New-Item -ItemType Directory -Force $dir | Out-Null
    $fileName = "$name.zap20"                       # Openness uses the name as given, no extension added
    $project.Archive([System.IO.DirectoryInfo] $dir, $fileName,
                     [Siemens.Engineering.ProjectArchivationMode]::Compressed)
    $file = Get-Item (Join-Path $dir $fileName) -ErrorAction SilentlyContinue
    if (-not $file) { throw "archive $fileName was not created in $dir" }
    Write-Host "archive: $($file.FullName)  ($([math]::Round($file.Length / 1MB, 1)) MB)"
    $file.FullName
}

function Set-DbNumber($plcSoftware, [string] $dbName, [int] $number) {
    $blocks = @(Get-AllBlocks $plcSoftware.BlockGroup)
    $db = $blocks | Where-Object { $_.Name -eq $dbName }
    if (-not $db) { throw "data block $dbName not found" }
    $dbs = @($blocks | Where-Object { $_ -is [Siemens.Engineering.SW.Blocks.DataBlock] })
    $other = $dbs | Where-Object { $_.Number -eq $number -and $_.Name -ne $dbName }
    if ($other) {                                   # move the conflicting DB to a free number
        $free = (($dbs | Measure-Object -Property Number -Maximum).Maximum) + 1
        Write-Host "renumber $($other.Name) DB$number -> DB$free"
        $other.AutoNumber = $false
        $other.Number = $free
    }
    $db.AutoNumber = $false
    $db.Number = $number
    if ($db.Number -ne $number) { throw "$dbName could not be pinned to DB$number" }
    Write-Host "pinned $dbName = DB$($db.Number)"
}

function Write-Messages($messages, $indent) {
    foreach ($m in $messages) {
        Write-Host ("{0}[{1}] {2} {3}" -f $indent, $m.State, $m.Path, $m.Description)
        Write-Messages $m.Messages ($indent + '  ')
    }
}

function Get-Compiler([object[]] $candidates) {
    # first object in the list that offers ICompilable (WinCC Unified: not always the software)
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        $svc = Get-Service $c ([Siemens.Engineering.Compiler.ICompilable])
        if ($svc) { Write-Host "compile service from $($c.GetType().Name) '$($c.Name)'"; return $svc }
    }
    $null
}

function Invoke-Compile([object[]] $candidates, [string] $what) {
    $compiler = Get-Compiler $candidates
    if (-not $compiler) { throw "$what offers no compile service (ICompilable)" }
    $result = $compiler.Compile()
    Write-Messages $result.Messages ''
    Write-Host ("Compile {0}: {1}  errors={2}  warnings={3}" -f $what, $result.State, $result.ErrorCount, $result.WarningCount)
    if ($result.ErrorCount -gt 0) { throw "$what compile errors - project NOT saved" }
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

    $plcFound = Find-Software $project $PlcName
    if (-not $plcFound) { throw "PLC software '$PlcName' not found" }
    $plcSoftware = $plcFound[0]
    $hmiSpec = Get-Content -Raw $HmiTagsFile | ConvertFrom-Json

    # 1. backup before any change
    if (-not $BackupDir) { $BackupDir = Join-Path (Split-Path (Split-Path $ProjectPath)) 'backups' }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $safeLabel = $Label -replace '[^A-Za-z0-9._-]', '_'
    [void](Save-Archive $project $BackupDir "$($project.Name)_before_${safeLabel}_$stamp")

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

    # 4. HMI interface DB must keep the number the absolute HMI addresses use
    Set-DbNumber $plcSoftware $hmiSpec.db ([int] $hmiSpec.db_number)

    # 5. compile PLC, then HMI (the HMI compile also resolves the %DB1 tag addresses)
    Invoke-Compile $plcFound 'PLC'
    if ($HmiName -and $HmiName -ne 'none') {
        $hmiFound = Find-Software $project $HmiName
        if (-not $hmiFound) { throw "HMI software '$HmiName' not found" }
        Invoke-Compile $hmiFound 'HMI'
    }

    # 6. save + archive the deployed state, keep the newest $KeepBackups archives
    $project.Save()
    Write-Host 'Project saved.'
    $archive = Save-Archive $project $BackupDir "$($project.Name)_${safeLabel}_$stamp"
    if ($env:GITHUB_OUTPUT) { "archive=$archive" | Out-File -Append -Encoding utf8 $env:GITHUB_OUTPUT }
    Get-ChildItem $BackupDir -Filter '*.zap*' | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $KeepBackups | ForEach-Object { Write-Host "prune $($_.Name)"; Remove-Item $_.FullName }
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($tia) { $tia.Dispose() }
}
