param(
    [string]$RepoRoot = "C:\dev\SpatialSprite",
    [string]$GodotExe = "godot"
)

$RepoRoot = Resolve-Path -Path $RepoRoot
$ProjectFile = Join-Path $RepoRoot "project.godot"
$MainScene = Join-Path $RepoRoot "main.tscn"
$HeroScene = Join-Path $RepoRoot "outputs\hero\hero.tscn"

if (-not (Test-Path $HeroScene)) {
    Write-Error "Hero scene not found: $HeroScene. Run tools/build_sprite_asset.py first."
    exit 1
}

$godotPath = $GodotExe
if (Test-Path $godotPath -PathType Container) {
    $found = Get-ChildItem -Path $godotPath -Filter 'Godot*.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $godotPath = $found.FullName
    }
}

if (-not (Test-Path $godotPath)) {
    $resolved = Get-Command $GodotExe -ErrorAction SilentlyContinue
    if ($resolved) {
        $godotPath = $resolved.Source
    }
}

if (-not (Test-Path $godotPath)) {
    Write-Error "Godot executable '$GodotExe' was not found. Install Godot or provide the correct path to the Godot executable." 
    exit 2
}

$projectText = @'
config_version=5

[application]

config/name="SpriteSpatial"
config/description="Directional sprite spatial prototype"
config/author="SpriteSpatial"
run/main_scene="res://main.tscn"
config/version="4.6.2"
'@
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ProjectFile, $projectText, $utf8NoBom)
Write-Host "Wrote Godot project file: $ProjectFile"

$mainText = @'
[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://outputs/hero/hero.tscn" id="1_hero"]

[node name="Main" type="Node3D"]

[node name="HeroInstance" parent="." instance=ExtResource("1_hero")]

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 6 )
current = true

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 4, 6 )
'@
[System.IO.File]::WriteAllText($MainScene, $mainText, $utf8NoBom)
Write-Host "Wrote demo main scene: $MainScene"

Write-Host "Opening Godot project at $RepoRoot using $godotPath"
& "$godotPath" --path "$RepoRoot"
