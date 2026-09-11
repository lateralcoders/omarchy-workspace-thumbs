import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "io.github.lateralcoders.workspace-thumbs"
  ipcTarget: "io.github.lateralcoders.workspace-thumbs"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property int selectedWorkspaceId: 1
  property bool captureQueued: false
  property int lastFocusId: -1
  property int capturingId: -1
  property var captureStamps: ({})
  property string shotSource: ""
  property bool pendingRefresh: false
  property int windowBorderSize: 2
  property color windowBorderColor: Color.accent
  readonly property int frameWidth: Math.max(1, root.windowBorderSize)

  readonly property string home: Quickshell.env("HOME")
  readonly property string previewDir: Model.previewDirectory(root.home)
  readonly property string wallpaperUrl: root.hostWidget && root.hostWidget.wallpaperUrl
    ? root.hostWidget.wallpaperUrl
    : Model.wallpaperUrl(root.home)
  readonly property string helper: String(Qt.resolvedUrl("preview-helper.py")).replace(/^file:\/\//, "")
  readonly property int focusId: Hyprland.focusedWorkspace !== null ? Hyprland.focusedWorkspace.id : -1
  readonly property var barWindow: root.hostWidget && root.hostWidget.QsWindow ? root.hostWidget.QsWindow.window : null
  readonly property var previewScreen: root.barWindow ? root.barWindow.screen : null
  readonly property real monitorWidth: root.previewScreen && root.previewScreen.width > 0
    ? root.previewScreen.width
    : (Hyprland.focusedMonitor && Hyprland.focusedMonitor.width > 0 ? Hyprland.focusedMonitor.width : 1920)
  readonly property real monitorHeight: root.previewScreen && root.previewScreen.height > 0
    ? root.previewScreen.height
    : (Hyprland.focusedMonitor && Hyprland.focusedMonitor.height > 0 ? Hyprland.focusedMonitor.height : 1080)
  readonly property int previewWidth: {
    var maxW = 320
    var scale = Math.min(0.14, maxW / Math.max(1, root.monitorWidth))
    return Math.max(200, Math.round(root.monitorWidth * scale))
  }
  readonly property int previewHeight: Math.max(112, Math.round(root.previewWidth * root.monitorHeight / Math.max(1, root.monitorWidth)))

  function currentWorkspaceId() {
    if (root.focusId > 0) return root.focusId
    return 1
  }

  function onFocusedOutput() {
    if (!root.previewScreen) return true
    var mapped = Hyprland.monitorFor(root.previewScreen)
    if (!mapped || !Hyprland.focusedMonitor) return true
    return mapped.name === Hyprland.focusedMonitor.name
  }

  function workspaceOccupied(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      var ws = values[i]
      if (ws && ws.id === id) return ws.toplevels.values.length > 0
    }
    return false
  }

  function shotUrl(workspaceId) {
    var epoch = 0
    if (root.hostWidget && root.hostWidget.epochFor)
      epoch = root.hostWidget.epochFor(workspaceId)
    return Model.previewUrlWithRev(root.previewDir, workspaceId, epoch)
  }

  function showWorkspace(workspaceId, anchor) {
    if (workspaceId <= 0) return
    if (anchor) root.anchorItem = anchor
    root.selectedWorkspaceId = workspaceId
    root.setShot(workspaceId)
  }

  function setShot(workspaceId) {
    if (workspaceId <= 0) {
      root.shotSource = root.wallpaperUrl
      return
    }
    var epoch = root.hostWidget && root.hostWidget.epochFor ? root.hostWidget.epochFor(workspaceId) : 0
    if (root.workspaceOccupied(workspaceId) || epoch > 0) {
      root.shotSource = root.shotUrl(workspaceId)
      return
    }
    root.shotSource = root.wallpaperUrl
  }

  function markCaptured(id) {
    var next = {}
    for (var key in root.captureStamps) next[key] = root.captureStamps[key]
    next[id] = Date.now()
    root.captureStamps = next
    if (root.hostWidget && root.hostWidget.noteCaptured) root.hostWidget.noteCaptured(id)
    if (root.opened && root.selectedWorkspaceId === id) root.setShot(id)
  }

  function recentlyCaptured(id) {
    var stamp = root.captureStamps[id]
    return !!stamp && (Date.now() - stamp) < 2500
  }

  function openForWorkspace(workspaceId, anchor) {
    closeTimer.stop()
    root.showWorkspace(workspaceId, anchor)
    root.controller.show()
  }

  function openFromHotkey() {
    openForWorkspace(root.selectedWorkspaceId > 0 ? root.selectedWorkspaceId : root.currentWorkspaceId(), root.anchorItem)
  }

  function close() {
    closeTimer.stop()
    root.controller.hide()
  }

  function scheduleClose() {
    if (panel.containsMouse) return
    closeTimer.restart()
  }

  function cancelClose() {
    closeTimer.stop()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function overlayOnScreen() {
    return panel.visible
  }

  function abortCapture() {
    stallTimer.stop()
    if (captureProc.running) captureProc.running = false
    root.captureQueued = false
    root.capturingId = -1
  }

  function captureWorkspace(id, force) {
    if (id <= 0) return
    if (!force && !root.onFocusedOutput()) return
    if (!force && root.recentlyCaptured(id)) return
    if (!force && root.overlayOnScreen()) return
    if (root.captureQueued || captureProc.running) {
      root.pendingRefresh = true
      return
    }
    root.pendingRefresh = false
    root.captureQueued = true
    root.capturingId = id
    stallTimer.restart()
    captureProc.running = false
    captureProc.command = ["/usr/bin/python3", root.helper, "capture", String(id), Model.previewPath(root.previewDir, id)]
    captureProc.running = true
  }

  function captureCurrentWorkspace() {
    root.captureWorkspace(root.currentWorkspaceId(), true)
  }

  onFocusIdChanged: {
    if (root.focusId <= 0) return
    if (root.focusId === root.lastFocusId) return
    root.lastFocusId = root.focusId
    settleTimer.restart()
  }

  onOpenedChanged: {
    if (root.opened) {
      root.abortCapture()
      return
    }
    // Clicking a chip keeps the hover card open, which skips the settle
    // capture. Recapture once the overlay is gone.
    settleTimer.restart()
  }

  Component.onCompleted: {
    root.lastFocusId = root.currentWorkspaceId()
    root.setShot(root.selectedWorkspaceId)
    settleTimer.restart()
  }

  Timer {
    id: settleTimer
    interval: 400
    repeat: false
    onTriggered: {
      if (root.overlayOnScreen()) return
      root.captureWorkspace(root.currentWorkspaceId(), true)
    }
  }

  Timer {
    id: closeTimer
    interval: 250
    repeat: false
    onTriggered: {
      if (panel.containsMouse) return
      root.close()
    }
  }

  Timer {
    id: stallTimer
    interval: 2000
    repeat: false
    onTriggered: {
      captureProc.running = false
      root.captureQueued = false
      root.capturingId = -1
    }
  }

  Process {
    id: captureProc
    command: ["/usr/bin/true"]
    running: false
    onExited: function(exitCode) {
      var capturedId = root.capturingId
      stallTimer.stop()
      root.captureQueued = false
      root.capturingId = -1
      if (exitCode !== 0 || capturedId <= 0) {
        if (root.pendingRefresh) Qt.callLater(function() { root.captureWorkspace(root.currentWorkspaceId()) })
        return
      }
      root.markCaptured(capturedId)
      if (root.pendingRefresh) Qt.callLater(function() { root.captureWorkspace(root.currentWorkspaceId()) })
    }
  }

  PopupCard {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    triggerMode: "hover"
    centerOnBar: false
    padding: 0
    margin: 6
    borderSpec: Border.none()
    contentWidth: root.previewWidth
    contentHeight: root.previewHeight

    Rectangle {
      anchors.fill: parent
      color: root.windowBorderColor

      Rectangle {
        anchors.fill: parent
        anchors.margins: root.frameWidth
        color: Color.background

        Image {
          id: shot
          anchors.fill: parent
          source: root.shotSource
          sourceSize.width: Math.max(1, root.previewWidth)
          sourceSize.height: Math.max(1, root.previewHeight)
          fillMode: Image.PreserveAspectFit
          smooth: true
          asynchronous: true
          cache: false
          onStatusChanged: {
            if (status !== Image.Error) return
            if (root.shotSource === root.wallpaperUrl) return
            Qt.callLater(function() {
              if (shot.status === Image.Error) root.shotSource = root.wallpaperUrl
            })
          }
        }

        Text {
          id: hoverNumber
          anchors.left: parent.left
          anchors.top: parent.top
          anchors.margins: 10
          text: String(root.selectedWorkspaceId)
          color: "#f4f4f5"
          font.family: Style.font.family
          font.pixelSize: Style.font.heading
          font.bold: true
          style: Text.Outline
          styleColor: "#000000"
          renderType: Text.NativeRendering
        }
      }
    }
  }
}
