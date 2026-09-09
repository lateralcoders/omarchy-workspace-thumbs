# Workspace Thumbs

Omarchy bar widget: each virtual desktop is a screenshot thumb with its number on a badge. Hover opens a larger preview (number on that shot too). Click focuses that desktop.

Fork of [io.github.bubblepaxi.workspace-preview](https://github.com/leofle/omarchy-workspace-preview). Keep that plugin installed if you want to switch back.

## Install

```sh
omarchy plugin add https://github.com/lateralcoders/omarchy-workspace-thumbs --enable
```

Or clone into `~/.config/omarchy/plugins/b0des.workspace-thumbs`.

## What you are looking at

- Thumbs sit in the bar (Omarchy clips bar widgets to ~26px). Hover for a large preview.
- Always shows desktops 1–10. Extra Hyprland workspaces up to 20 are appended.
- Occupied desktops show the last captured screenshot; empty ones show wallpaper.
- Number badge is drawn above the shot. Focused desktop gets an accent border.
- Snapshots refresh when you land on a desktop, then freeze until you leave and come back.

## iconMode (experimental)

Off by default. Set on the bar entry in `~/.config/omarchy/shell.json`:

```json
{ "id": "b0des.workspace-thumbs", "iconMode": "single" }
```

- `off` — screenshots only
- `single` — one app icon (largest window on that desktop) to the right of the number
- `all` — up to three unique app icons

Hover preview stays screenshot-only. Icons come from Hyprland `class` via the icon theme (cached). Hidden/unmapped windows are skipped.

Files: `~/.cache/omarchy/workspace-previews/`

## Shortcut

```sh
omarchy-shell shell summon b0des.workspace-thumbs '{}'
omarchy-shell shell hide b0des.workspace-thumbs
```

## Remove

```sh
omarchy plugin disable b0des.workspace-thumbs
omarchy plugin remove b0des.workspace-thumbs
```

Disabling first puts the original hover plugin back. Removing deletes this folder only.
