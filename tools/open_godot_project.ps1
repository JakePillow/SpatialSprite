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

if (-not (Test-Path $ProjectFile)) {
    @"
[gd_resource type=\"ProjectSettings\" load_steps=2 format=3]
[application]
config/name=\"SpriteSpatial\"
config/description=\"Directional sprite spatial prototype\"
config/author=\"SpriteSpatial\"
config/main_scene=\"res://main.tscn\"
config/version={"major":4,"minor":0,"patch":0}
"@ | Set-Content -Path $ProjectFile -Encoding UTF8
    Write-Host "Created Godot project file: $ProjectFile"
}

if (-not (Test-Path $MainScene)) {
    @"
[ext_resource path=\"res://outputs/hero/hero.tscn\" type=\"PackedScene\" id=1]

[gd_scene load_steps=3 format=3]
[node name=\"Main\" type=Node3D]
[node name=\"HeroInstance\" type=Instance3D parent=\".\"]
scene = ExtResource( 1 )
[node name=\"Camera3D\" type=Camera3D parent=\".\"]
transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 6 )
current = true
[node name=\"DirectionalLight3D\" type=DirectionalLight3D parent=\".\"]
transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 4, 6 )
"@ | Set-Content -Path $MainScene -Encoding UTF8
    Write-Host "Created demo main scene: $MainScene"
}

Write-Host "Opening Godot project at $RepoRoot"
& $GodotExe --path $RepoRoot
