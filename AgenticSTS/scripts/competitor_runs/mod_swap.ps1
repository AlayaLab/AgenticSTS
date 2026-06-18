<#
.SYNOPSIS
  Enforce complete-replacement isolation for competitor runs: clear the game's mods/
  of ALL known mod artifacts (every competitor AND our own mod), then install exactly
  one competitor's staged files. (Workstream C — see PROTOCOL.md "complete replacement".)

.DESCRIPTION
  Our mod is a CharTyr fork and ships the SAME filenames (STS2AIAgent.dll/.pck/mod_id.json),
  so "clear everything, install one" is the only safe way to guarantee the competitor
  agent sees ONLY the competitor's mod. Only one mod can Harmony-patch the game at a time.

  Staged mods live under _staged_mods/ (built by the C.B* build steps):
    sts2mcp/  -> STS2_MCP.dll + STS2_MCP.json            (flat in mods/)
    chartyr/  -> STS2AIAgent.dll + .pck + mod_id.json    (flat in mods/)
    aispire/  -> AISpire/ subfolder                       (mods/AISpire/)

.EXAMPLE
  # before the STS2MCP batch:
  powershell -ExecutionPolicy Bypass -File scripts\competitor_runs\mod_swap.ps1 -Competitor sts2mcp
  # before CharTyr:
  ... -Competitor chartyr
  # before AI-Spire:
  ... -Competitor aispire
  # clear everything (e.g. to restore our own mod manually afterward):
  ... -Competitor none

.NOTES
  After swapping, launch the game and confirm the TARGET's own health endpoint
  (STS2MCP :15526 / CharTyr :8080 / AI-Spire overlay). Our mod's :8128 must stay dead —
  the Gemini MCP host hard-aborts if :8128 answers.
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("sts2mcp", "chartyr", "aispire", "none")]
    [string]$Competitor,
    [string]$GameRoot = "C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2",
    [string]$StageRoot = (Join-Path $PSScriptRoot "_staged_mods")  # competitor mod staging dir (set to your own path)
)
$ErrorActionPreference = "Stop"

$mods = Join-Path $GameRoot "mods"
New-Item -ItemType Directory -Force -Path $mods | Out-Null

# 1. Clear ALL known mod artifacts incl. stale backups (globs): every competitor AND
#    our own mod, which shares the STS2AIAgent.* filenames and leaves *.bak/*.old cruft.
$clearGlobs = @("AISpire*", "STS2_MCP*", "STS2AIAgent*", "mod_id.json")
Write-Host "[mod_swap] clearing mods/ ..."
foreach ($g in $clearGlobs) {
    Get-ChildItem $mods -Filter $g -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force; Write-Host ("  - removed " + $_.Name)
    }
}

# 2. Install the target competitor's staged files.
switch ($Competitor) {
    "none" {
        Write-Host "[mod_swap] mods/ cleared; no competitor installed."
    }
    "aispire" {
        $src = Join-Path $StageRoot "aispire\AISpire"
        if (-not (Test-Path $src)) { throw "staged AI-Spire not found at $src (run the C.B3 build/stage first)" }
        Copy-Item $src $mods -Recurse -Force
        Write-Host "[mod_swap] installed AI-Spire -> mods/AISpire/"
    }
    default {
        $src = Join-Path $StageRoot $Competitor
        if (-not (Test-Path $src)) { throw "staged '$Competitor' not found at $src" }
        Get-ChildItem $src -File | ForEach-Object { Copy-Item $_.FullName $mods -Force }
        Write-Host "[mod_swap] installed $Competitor (flat in mods/)"
    }
}

# 3. Report final state.
Write-Host "[mod_swap] mods/ now contains:"
Get-ChildItem $mods | ForEach-Object { Write-Host ("    " + $_.Name) }
if ($Competitor -ne "none") {
    Write-Host "[mod_swap] Launch the game; confirm the TARGET's own endpoint. Our mod's :8128 must stay dead."
}
