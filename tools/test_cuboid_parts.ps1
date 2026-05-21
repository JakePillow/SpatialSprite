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
$GodotPath = $env:GODOT_EXE # Check env var first.
$PythonExe = "python" # Assumes 'python' is in your system's PATH.

# --- Godot Path Resolution ---
if (-not $GodotPath -or -not (Test-Path $GodotPath)) {
    $GodotPath = (Get-Command godot -ErrorAction SilentlyContinue).Source
}
if (-not $GodotPath -or -not (Test-Path $GodotPath)) {
    $GodotPath = "$env:LOCALAPPDATA\Programs\Godot\godot.exe" # Fallback to common install path
}

# --- Asset Generation ---
# Ensure the test sprite exists by running the creation script first.
$CreateHumanoidSpriteScript = Join-Path $RepoRoot "tools\create_humanoid_test_sprite.py"
$CreateEnemySpriteScript = Join-Path $RepoRoot "tools\create_enemy_test_sprite.py"

if ($FrontSprite -like "*topology_humanoid_front.png*" -and -not (Test-Path $FrontSprite)) {
    Write-Verbose "Default humanoid test sprite not found. Generating it..."
    & $PythonExe $CreateHumanoidSpriteScript "--output" $FrontSprite
}
elseif ($FrontSprite -like "*topology_enemy_front.png*" -and -not (Test-Path $FrontSprite)) {
    Write-Verbose "Default enemy test sprite not found. Generating it..."
    & $PythonExe $CreateEnemySpriteScript "--output" $FrontSprite
}

# --- Build Arguments ---
$BuildScript = Join-Path $RepoRoot "tools\build_topological_sprite_model.py"

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
if (-not (Test-Path $GodotPath)) {
    Write-Error "Godot executable not found. Please update the path in the script, install Godot to a standard location, or add it to your PATH."
    Write-Error "You can also set a 'GODOT_EXE' environment variable."
    exit 1
}

Write-Host "Launching Godot to open scene: $ScenePath" -ForegroundColor Green

& $GodotPath --path $RepoRoot $ScenePath

Write-Verbose "Script finished."
