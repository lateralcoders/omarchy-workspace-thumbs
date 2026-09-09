function workspaceLabel(id) {
  return String(id)
}

function previewDirectory(home) {
  return String(home || "") + "/.cache/omarchy/workspace-previews"
}

function previewPath(dir, workspaceId) {
  return String(dir || "") + "/ws-" + String(workspaceId) + ".jpg"
}

function previewUrl(dir, workspaceId) {
  return "file://" + previewPath(dir, workspaceId)
}

function previewUrlWithRev(dir, workspaceId, rev) {
  // Fragment, not query: QFile strips it, Qt's image cache key keeps it, so
  // the same jpeg reloads after grim overwrites the file.
  return previewUrl(dir, workspaceId) + "#e=" + String(rev || 0)
}

function wallpaperPath(home) {
  return String(home || "") + "/.local/state/omarchy/current/background"
}

function wallpaperUrl(home) {
  return "file://" + wallpaperPath(home)
}

function sameIdList(left, right) {
  if (!left || !right || left.length !== right.length) return false
  for (var i = 0; i < left.length; i++) {
    if (left[i] !== right[i]) return false
  }
  return true
}

function bumpEpochs(epochs, id) {
  var next = {}
  for (var key in epochs) next[key] = epochs[key]
  next[String(id)] = Date.now()
  return next
}
