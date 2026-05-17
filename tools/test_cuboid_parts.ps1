<#
.SYNOPSIS
    Builds the 'cuboid_parts' model and opens it in Godot.
.DESCRIPTION
    This script automates the testing workflow for the semantic cuboid reconstruction.
    1. It runs the `build_topological_sprite_model.py` script with the `--representation-style cuboid_parts`.
    2. It then launches the Godot editor, opening the newly generated scene file.

    You can customize the paths to your Godot and Python executables in the configuration section.
.EXAMPLE
    .\tools\test_cuboid_parts.ps1
    Runs the entire build and test process.
 #>

# --- Configuration ---
$RepoRoot = $PSScriptRoot | Split-Path | Resolve-Path
$GodotExe = "$env:LOCALAPPDATA\Programs\Godot\godot.exe" # Common install path, adjust if needed.
$PythonExe = "python" # Assumes 'python' is in your system's PATH.

# --- Asset Generation ---
# Ensure the test sprite exists by running the creation script first.
$CreateSpriteScript = Join-Path $RepoRoot "tools\create_internal_test_sprite.py"
$TestSprite = Join-Path $RepoRoot "assets\samples\internal\topology_humanoid_front.png"

Write-Host "Ensuring internal test sprite exists at '$TestSprite'..." -ForegroundColor Cyan
& $PythonExe $CreateSpriteScript "--output" $TestSprite
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create the internal test sprite. Aborting."
    exit 1
}

# --- Build Arguments ---
$BuildScript = Join-Path $RepoRoot "tools\build_topological_sprite_model.py"
$FrontSprite = $TestSprite # Use the guaranteed test sprite.
$OutputDir = Join-Path $RepoRoot "outputs\internal_cuboid_test"
$ScenePath = Join-Path $RepoRoot "scenes\internal_cuboid_test.tscn"

# 1. Run the Python build script to generate the cuboid model.
Write-Host "Building cuboid model from '$($FrontSprite.Name)'..." -ForegroundColor Cyan

$buildArgs = @(
    $BuildScript,
    "--front", $FrontSprite,
    "--output-dir", $OutputDir,
    "--scene-path", $ScenePath,
    "--representation-style", "cuboid_parts"
)

& $PythonExe $buildArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "Python build script failed. Aborting."
    exit 1
}

Write-Host "Build successful. Model and scene generated." -ForegroundColor Green

# 2. Launch Godot to view the generated scene.
if (-not (Test-Path $GodotExe)) {
    Write-Error "Godot executable not found at '$GodotExe'. Please update the path in the script."
    exit 1
}

Write-Host "Launching Godot to open scene: $ScenePath" -ForegroundColor Green

$godotArgs = @("--path", $RepoRoot, $ScenePath)

Start-Process -FilePath $GodotExe -ArgumentList $godotArgs