# Workspace Thumbs

Bar workspace switcher for [Omarchy](https://omarchy.org): each desktop is a screenshot thumb with its number on a badge. Hover opens a larger preview. Click focuses that desktop.

Fork of [Workspace Preview](https://github.com/leofle/omarchy-workspace-preview) (`io.github.bubblepaxi.workspace-preview`), itself a clone of built-in `omarchy.workspaces`. MIT, with original copyright retained.

Built by [Zute Predictive](https://zutepredictive.com).

## Install

```sh
omarchy plugin add https://github.com/lateralcoders/omarchy-workspace-thumbs.git --enable
```

Enabling takes the workspace slot on the bar (it replaces `omarchy.workspaces` or Workspace Preview if that is what you had). Disabling or removing this plugin puts that previous widget back.

## Usage

- Hover a thumb for a larger screenshot. Click to focus that desktop.
- Occupied desktops show the last captured screenshot; empty ones show wallpaper.
- Always shows desktops 1–10. Extra Hyprland workspaces up to 20 are appended.
- Snapshots refresh when you land on a desktop, then freeze until you leave and come back.

Optional `iconMode` on the bar entry in `~/.config/omarchy/shell.json` (default is `single`):

```json
{ "id": "io.github.lateralcoders.workspace-thumbs", "iconMode": "all" }
```

- `single` — one app icon (largest window) to the right of the number (default)
- `all` — up to three unique app icons
- `off` — screenshots only

Hover preview stays screenshot-only.

Summon from a keybinding:

```sh
omarchy-shell shell summon io.github.lateralcoders.workspace-thumbs '{}'
omarchy-shell shell hide io.github.lateralcoders.workspace-thumbs
```

## Dependencies

Already on a normal Omarchy install. No extra packages. No sudo or pkexec is required.

- Hyprland (`hyprctl`)
- `grim` (scaled JPEG capture)
- `jq` (focused monitor name)

Thumbnails are written to `~/.cache/omarchy/workspace-previews/`. The plugin does not install packages and does not change files outside its cache directory and your existing `shell.json` bar layout when you enable it.

## Remove

```sh
omarchy plugin disable io.github.lateralcoders.workspace-thumbs
omarchy plugin remove io.github.lateralcoders.workspace-thumbs
```

Removing an enabled copy restores the previous workspace widget in the same bar slot. If the built-in numbers are missing afterward:

```sh
omarchy plugin enable omarchy.workspaces
```

Cached thumbnails are left in `~/.cache/omarchy/workspace-previews/` and can be deleted by hand.

## License

[MIT](LICENSE)
