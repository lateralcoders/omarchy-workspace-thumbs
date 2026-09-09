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

function clientIpc(toplevel) {
  if (!toplevel) return null
  if (toplevel.lastIpcObject) return toplevel.lastIpcObject
  return toplevel
}

function clientVisible(ipc) {
  if (!ipc) return false
  if (ipc.mapped === false) return false
  if (ipc.hidden === true) return false
  if (ipc.minimized === true) return false
  return true
}

function clientClass(ipc, toplevel) {
  if (ipc && ipc.class) return String(ipc.class)
  if (ipc && ipc.initialClass) return String(ipc.initialClass)
  if (toplevel && toplevel.wayland && toplevel.wayland.appId) return String(toplevel.wayland.appId)
  return ""
}

function clientArea(ipc) {
  var size = ipc && ipc.size
  if (!size || size.length < 2) return 0
  return Number(size[0]) * Number(size[1]) || 0
}

function iconLookupNames(klass) {
  var raw = String(klass || "")
  if (!raw) return []
  var names = [raw]
  var lower = raw.toLowerCase()
  if (names.indexOf(lower) === -1) names.push(lower)
  var parts = raw.split(".")
  if (parts.length > 1) {
    var last = parts[parts.length - 1]
    if (last && names.indexOf(last) === -1) names.push(last)
    var lastLower = last.toLowerCase()
    if (names.indexOf(lastLower) === -1) names.push(lastLower)
  }
  if (lower === "code") {
    names.push("vscode")
    names.push("visual-studio-code")
  }
  return names
}

function cachedIcon(cache, klass, lookupFn) {
  var key = String(klass || "").toLowerCase()
  if (!key) return ""
  if (cache[key] !== undefined) return cache[key]
  var src = lookupFn ? lookupFn(klass) : ""
  cache[key] = src || ""
  return cache[key]
}

function classesForToplevels(toplevels, mode, maxIcons) {
  mode = String(mode || "off")
  if (mode !== "all" && mode !== "single") return []
  maxIcons = maxIcons || 3
  var values = toplevels || []
  var rows = []
  for (var i = 0; i < values.length; i++) {
    var top = values[i]
    var ipc = clientIpc(top)
    if (!clientVisible(ipc)) continue
    var klass = clientClass(ipc, top)
    if (!klass) continue
    rows.push({ klass: klass, area: clientArea(ipc) })
  }
  if (!rows.length) return []
  if (mode === "single") {
    var best = rows[0]
    for (var j = 1; j < rows.length; j++) {
      if (rows[j].area > best.area) best = rows[j]
    }
    return [best.klass]
  }
  var seen = {}
  var out = []
  for (var k = 0; k < rows.length; k++) {
    var key = rows[k].klass.toLowerCase()
    if (seen[key]) continue
    seen[key] = true
    out.push(rows[k].klass)
    if (out.length >= maxIcons) break
  }
  return out
}
