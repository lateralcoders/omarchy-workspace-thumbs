import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "b0des.workspace-thumbs"

  property int hoveredWorkspaceId: -1
  property var displayedIds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  property var previewEpochs: ({})
  property var iconCache: ({})
  readonly property string iconMode: {
    var value = String(setting("iconMode", "off") || "off").toLowerCase()
    if (value === "all" || value === "single") return value
    return "off"
  }

  readonly property string home: Quickshell.env("HOME")
  readonly property string previewDir: Model.previewDirectory(root.home)
  readonly property string wallpaperUrl: Model.wallpaperUrl(root.home)
  readonly property int thumbPad: Math.max(1, Style.space(1))
  readonly property int thumbGap: Math.max(2, Style.space(2))
  readonly property int thumbInner: Math.max(12, root.barSize - thumbPad * 2)
  readonly property real monitorAspect: {
    var mon = Hyprland.focusedMonitor
    var w = mon && mon.width > 0 ? mon.width : 16
    var h = mon && mon.height > 0 ? mon.height : 9
    return Math.max(1.2, Math.min(2.4, w / Math.max(1, h)))
  }
  readonly property int thumbWidth: root.vertical
    ? root.barSize
    : Math.max(Style.space(22), Math.round(thumbInner * monitorAspect))
  readonly property int thumbHeight: root.vertical
    ? Math.max(Style.space(14), Math.round(thumbInner / monitorAspect))
    : root.barSize

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }
    return null
  }

  function workspaceIds() {
    var ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 10 && id <= 20 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function syncDisplayedIds() {
    var ids = root.workspaceIds()
    if (!Model.sameIdList(ids, root.displayedIds)) root.displayedIds = ids
  }

  function workspaceLabel(id) {
    return Model.workspaceLabel(id)
  }

  function currentWorkspaceId() {
    if (Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id > 0)
      return Hyprland.focusedWorkspace.id
    return 1
  }

  function focusWorkspace(id) {
    if (panelLoader.item) panelLoader.item.close()
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  function open() {
    ensurePanel()
    var id = root.hoveredWorkspaceId > 0 ? root.hoveredWorkspaceId : root.currentWorkspaceId()
    if (panelLoader.item) panelLoader.item.openForWorkspace(id, root)
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function toggle() {
    if (panelLoader.item && panelLoader.item.opened) close()
    else open()
  }

  function setPreviewWorkspace(id) {
    if (id <= 0) return
    hoveredWorkspaceId = id
    ensurePanel()
    previewCloseTimer.stop()
    if (panelLoader.item && panelLoader.item.opened) {
      panelLoader.item.showWorkspace(id, root)
      return
    }
    if (!previewOpenTimer.running) previewOpenTimer.start()
  }

  function stripLeft() {
    hoveredWorkspaceId = -1
    previewOpenTimer.stop()
    previewCloseTimer.restart()
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("anchorItem" in target) target.anchorItem = root
    if ("hostWidget" in target) target.hostWidget = root
  }

  function ensurePanel() {
    if (!panelLoader.active) panelLoader.active = true
  }

  function noteCaptured(id) {
    if (!(id > 0)) return
    root.previewEpochs = Model.bumpEpochs(root.previewEpochs, id)
  }

  function epochFor(id) {
    return root.previewEpochs[String(id)] || 0
  }

  function shotUrlFor(id, occupied) {
    if (!occupied) return root.wallpaperUrl
    return Model.previewUrlWithRev(root.previewDir, id, root.epochFor(id))
  }

  function lookupIcon(klass) {
    var names = Model.iconLookupNames(klass)
    for (var i = 0; i < names.length; i++) {
      var path = Quickshell.iconPath(names[i], true)
      if (path && path.length) return path
    }
    return Quickshell.iconPath("application-x-executable", true)
  }

  function iconForClass(klass) {
    return Model.cachedIcon(root.iconCache, klass, root.lookupIcon)
  }

  function iconsForWorkspace(id) {
    if (root.iconMode === "off") return []
    var ws = root.workspaceById(id)
    var tops = ws && ws.toplevels ? ws.toplevels.values : []
    var classes = Model.classesForToplevels(tops, root.iconMode, 3)
    var urls = []
    for (var i = 0; i < classes.length; i++) urls.push(root.iconForClass(classes[i]))
    return urls
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item && panelLoader.item.closeForPopoutSwitch)
      panelLoader.item.closeForPopoutSwitch()
  }

  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
  readonly property real openPanelIndicatorWidth: 0
  readonly property real openPanelIndicatorHeight: 0

  implicitWidth: root.vertical ? root.barSize : grid.implicitWidth + trailingGap
  implicitHeight: root.barSize

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)

  onBarChanged: injectPanel()
  Component.onCompleted: root.syncDisplayedIds()

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (!event) return
      var name = String(event.name || "")
      if (name.indexOf("workspace") === -1 && name.indexOf("focusedmon") === -1) return
      root.syncDisplayedIds()
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Timer {
    id: previewOpenTimer
    interval: 20
    repeat: false
    onTriggered: {
      if (root.hoveredWorkspaceId <= 0) return
      if (panelLoader.item) panelLoader.item.openForWorkspace(root.hoveredWorkspaceId, root)
    }
  }

  Timer {
    id: previewCloseTimer
    interval: 250
    repeat: false
    onTriggered: {
      if (root.hoveredWorkspaceId > 0) return
      if (panelLoader.item) panelLoader.item.scheduleClose()
    }
  }

  IpcHandler {
    target: root.moduleName

    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { if (panelLoader.item && panelLoader.item.captureCurrentWorkspace) panelLoader.item.captureCurrentWorkspace() }
  }

  HoverHandler {
    onHoveredChanged: {
      if (hovered) previewCloseTimer.stop()
      else root.stripLeft()
    }
  }

  component WorkspaceThumb: Item {
    id: thumb

    required property int modelData

    property var registeredBar: null
    property bool interactive: true
    property bool pressable: true

    readonly property var workspace: root.workspaceById(modelData)
    readonly property bool occupied: workspace !== null && workspace.toplevels.values.length > 0
    readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData
    readonly property bool hovered: thumbHover.hovered
    readonly property bool tooltipHovered: visible && interactive && hovered
    readonly property int epoch: root.epochFor(modelData)
    readonly property string label: root.workspaceLabel(modelData)
    readonly property string liveUrl: root.shotUrlFor(modelData, occupied)
    readonly property var appIcons: {
      var _count = workspace && workspace.toplevels ? workspace.toplevels.values.length : 0
      if (root.iconMode === "off" || _count < 0) return []
      return root.iconsForWorkspace(modelData)
    }
    property bool showA: true
    property string pendingUrl: ""

    onLiveUrlChanged: {
      if (!occupied) return
      if (liveUrl === pendingUrl) return
      pendingUrl = liveUrl
      if (showA) bufB.source = liveUrl
      else bufA.source = liveUrl
    }

    function acceptBuffer(which) {
      var img = which === "A" ? bufA : bufB
      if (img.status !== Image.Ready) return
      if (String(img.source) !== String(thumb.pendingUrl)) return
      thumb.showA = which === "A"
    }

    Connections {
      target: bufA
      function onStatusChanged() { thumb.acceptBuffer("A") }
    }
    Connections {
      target: bufB
      function onStatusChanged() { thumb.acceptBuffer("B") }
    }



    implicitWidth: root.vertical ? root.barSize : root.thumbWidth
    implicitHeight: root.vertical ? root.thumbHeight : root.barSize
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    opacity: occupied || focused ? 1 : 0.55

    function triggerPress(buttonCode) {
      if (root.bar) root.bar.hideTooltip(thumb)
      if (buttonCode === Qt.LeftButton) root.focusWorkspace(modelData)
    }

    function syncClickRegistration() {
      if (registeredBar && registeredBar.unregisterClickTarget) registeredBar.unregisterClickTarget(thumb)
      registeredBar = root.bar
      if (registeredBar && registeredBar.registerClickTarget) registeredBar.registerClickTarget(thumb)
    }

    Connections {
      target: root
      function onBarChanged() { thumb.syncClickRegistration() }
    }

    Component.onCompleted: {
      thumb.syncClickRegistration()
      thumb.pendingUrl = thumb.liveUrl
      bufA.source = thumb.liveUrl
    }
    Component.onDestruction: if (registeredBar && registeredBar.unregisterClickTarget) registeredBar.unregisterClickTarget(thumb)

    HoverHandler {
      id: thumbHover
      onHoveredChanged: {
        if (hovered) root.setPreviewWorkspace(modelData)
      }
    }

    Item {
      id: frame
      anchors.fill: parent
      anchors.margins: root.thumbPad
      clip: true

      Rectangle {
        anchors.fill: parent
        color: Color.background
        radius: frameRadius
      }

      Image {
        id: wallpaper
        anchors.fill: parent
        source: root.wallpaperUrl
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
        z: 0
      }

      Image {
        id: bufA
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
        z: thumb.showA ? 2 : 1
        opacity: thumb.occupied && thumb.showA && status === Image.Ready ? 1 : 0
        sourceSize.width: Math.max(1, frame.width)
        sourceSize.height: Math.max(1, frame.height)
      }

      Image {
        id: bufB
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
        z: thumb.showA ? 1 : 2
        opacity: thumb.occupied && !thumb.showA && status === Image.Ready ? 1 : 0
        sourceSize.width: Math.max(1, frame.width)
        sourceSize.height: Math.max(1, frame.height)
      }

      Row {
        z: 10
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 2
        spacing: 2

        Rectangle {
          id: numberBadge
          width: numberLabel.implicitWidth + 6
          height: numberLabel.implicitHeight + 2
          radius: 2
          color: Qt.rgba(0, 0, 0, thumb.focused ? 0.72 : 0.55)

          Text {
            id: numberLabel
            anchors.centerIn: parent
            text: thumb.label
            color: "#f4f4f5"
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            font.bold: true
            renderType: Text.NativeRendering
          }
        }

        Repeater {
          model: thumb.appIcons
          Image {
            required property var modelData
            width: 12
            height: 12
            source: String(modelData || "")
            sourceSize.width: 16
            sourceSize.height: 16
            asynchronous: true
            cache: true
            smooth: true
            fillMode: Image.PreserveAspectFit
          }
        }
      }

      Rectangle {
        z: 11
        anchors.fill: parent
        color: "transparent"
        radius: frameRadius
        border.width: thumb.focused ? 2 : 1
        border.color: thumb.focused
          ? Color.accent
          : (thumb.hovered ? Qt.rgba(1, 1, 1, 0.7) : Qt.rgba(1, 1, 1, 0.38))
      }
    }

    readonly property int frameRadius: Math.max(2, Math.min(5, Style.cornerRadius || 4))
  }

  GridLayout {
    id: grid
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    columns: root.vertical ? 1 : root.displayedIds.length
    columnSpacing: root.vertical ? 0 : root.thumbGap
    rowSpacing: root.vertical ? root.thumbGap : 0

    Repeater {
      model: root.displayedIds
      WorkspaceThumb {}
    }
  }
}
