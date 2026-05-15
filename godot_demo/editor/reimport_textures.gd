tool
extends EditorScript

# Simple helper: lists all PNG textures under res://assets/samples and
# instructs the user to reimport them with Filter = off and Generate Mipmaps = off.
# Run this from the Godot Editor: Project -> Tools -> Run Script, or use
# the Command-Line editor scripting option if available for your build.

func _run() -> void:
    var dir = DirAccess.open("res://assets/samples")
    if not dir:
        printerr("Could not access res://assets/samples")
        return

    var to_process := []
    dir.list_dir_begin(true, true)
    var name = dir.get_next()
    while name != "":
        if name.to_lower().ends_with(".png"):
            to_process.append(dir.get_current_dir().plus_file(name))
        name = dir.get_next()
    dir.list_dir_end()

    if to_process.empty():
        print("No PNGs found under res://assets/samples")
        return

    print("Found textures to reimport:")
    for p in to_process:
        print(" - ", p)

    print("\nTo ensure nearest-neighbour sampling: for each texture listed above, select it in the FileSystem dock, then in the Import dock set Filter = Off and Generate Mipmaps = Off, then click Reimport.")
