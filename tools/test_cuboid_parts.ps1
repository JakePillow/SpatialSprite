<#
.SYNOPSIS
    Builds the 'cuboid_parts' model and opens it in Godot.
.DESCRIPTION
    This script automates the testing workflow for the semantic cuboid reconstruction.
    1. It runs the `build_topological_sprite_model.py` script with the `--representation-style cuboid_parts`.
    2. It then launches the Godot editor, opening the newly generated scene file.

    You can customize the paths to your Godot and Python executables in the configuration section.
.PARAMETER FrontSprite
    The path to the front-facing sprite image to use for the model.
.PARAMETER OutputDir
    The directory where the generated model assets will be saved.
.PARAMETER ScenePath
    The path where the generated Godot scene file (.tscn) will be saved.
.EXAMPLE
    .\tools\test_cuboid_parts.ps1
    Runs the entire build and test process.
.EXAMPLE
    .\tools\test_cuboid_parts.ps1 -FrontSprite "C:\Path\To\Your\Sprite.png"
    Runs the build process using a custom sprite.
 #>
[CmdletBinding()]
param (
    [string]$FrontSprite = (Join-Path $PSScriptRoot "..\assets\samples\internal\topology_humanoid_front.png"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "..\outputs\internal_cuboid_test"),
    [string]$ScenePath = (Join-Path $PSScriptRoot "..\scenes\internal_cuboid_test.tscn")
)

$ErrorActionPreference = 'Stop'

# --- Configuration ---
$RepoRoot = $PSScriptRoot | Split-Path | Resolve-Path
$GodotExe = $env:GODOT_EXE -or "$env:LOCALAPPDATA\Programs\Godot\godot.exe" # Check env var, then common path.
$PythonExe = "python" # Assumes 'python' is in your system's PATH.

# --- Asset Generation ---
# Ensure the test sprite exists by running the creation script first.
$CreateSpriteScript = Join-Path $RepoRoot "tools\create_internal_test_sprite.py"

if ($FrontSprite -match "topology_humanoid_front.png" -and -not (Test-Path $FrontSprite)) {
    Write-Verbose "Default test sprite not found. Generating a new one at '$FrontSprite'..."
    try {
        & $PythonExe $CreateSpriteScript "--output" $FrontSprite
    }
    catch {
        Write-Error "Failed to create the internal test sprite. Aborting. Error: $_"
        exit 1
    }
}

# --- Build Arguments ---
$BuildScript = Join-Path $RepoRoot "tools\build_topological_sprite_model.py"

Write-Verbose "Using build script: $BuildScript"
$BuildScriptText = Get-Content -LiteralPath $BuildScript -Raw
if ($BuildScriptText -notmatch "cuboid_parts") {
    Write-Error "Stale build script detected: --representation-style does not include cuboid_parts."
    exit 1
}
if ($BuildScriptText -match "colour = _paper_face_colour\(pixels\[x, y\], label, face\)") {
    Write-Error "Stale build script detected: paper_cutout might be using an old pixel access method. Please verify the build script."
    exit 1
}
Write-Verbose "Build script sanity check passed."

# 1. Run the Python build script to generate the cuboid model.
Write-Host "Building cuboid model from '$(Split-Path $FrontSprite -Leaf)'..." -ForegroundColor Cyan

$buildArgs = @(
    $BuildScript,
    "--front", $FrontSprite,
    "--output-dir", $OutputDir,
    "--scene-path", $ScenePath,
    "--representation-style", "cuboid_parts"
)

try {
    & $PythonExe $buildArgs
    Write-Host "Build successful. Model and scene generated." -ForegroundColor Green
}
catch {
    Write-Error "Python build script failed. Aborting. Error: $_"
    exit 1
}

# 2. Launch Godot to view the generated scene.
if (-not (Test-Path $GodotExe)) {
    Write-Error "Godot executable not found at '$GodotExe'. Please update the path in the script."
    Write-Error "You can also set a 'GODOT_EXE' environment variable."
    exit 1
}

Write-Host "Launching Godot to open scene: $ScenePath" -ForegroundColor Green

& $GodotExe --path $RepoRoot $ScenePath

Write-Verbose "Script finished."
