"""Digonto Player - video and music player. Qt Multimedia (PySide6) only: no other player is installed or started."""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy, QSlider, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

import digonto_ui as ui

APP_NAME = "Digonto Player"
SLUG = "digonto-player"
VERSION = "1.0.6"
VIDEO = (".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv", ".vob")
AUDIO = (".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".aiff", ".aif", ".wma", ".ape", ".mka", ".weba")
LISTS = (".m3u", ".m3u8")
MEDIA = VIDEO + AUDIO
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


# ---- shared recent list (read by Digonto Studio)
def base_dir():
    env = (os.environ.get("DIGONTO_BASE") or os.environ.get("PROTTOY_BASE"))
    return env if env else os.path.dirname(os.path.dirname(HERE))


def add_recent(path):
    rp = os.path.join(base_dir(), "recent.json")
    try:
        with open(rp, encoding="utf-8") as f:
            items = [r for r in json.load(f) if isinstance(r, dict)]
    except (OSError, ValueError):
        items = []
    items = [r for r in items if r.get("path") != path]
    items.insert(0, {"app": SLUG, "path": path, "time": time.time()})
    try:
        os.makedirs(base_dir(), exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(items[:40], f)
    except OSError:
        pass


def fmt_time(ms):
    s = max(0, int(ms // 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def is_media(p):
    return p.lower().endswith(MEDIA)


def expand(paths):
    """files and folders -> media files (folders are read in name order, with their sub-folders); .m3u lists are read"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs.sort(key=str.lower)
                for f in sorted(files, key=str.lower):
                    if is_media(f):
                        out.append(os.path.join(root, f))
        elif p.lower().endswith(LISTS):
            out += read_m3u(p)
        elif os.path.isfile(p) and is_media(p):
            out.append(p)
        elif p.startswith(("http://", "https://")):
            out.append(p)
    return out


def read_m3u(path):
    out = []
    base = os.path.dirname(os.path.abspath(path))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(("http://", "https://")):
                    out.append(line)
                else:
                    q = line if os.path.isabs(line) else os.path.join(base, line)
                    if os.path.isfile(q):
                        out.append(q)
    except OSError:
        pass
    return out


def write_m3u(path, items):
    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for p in items:
            f.write(p + "\n")


# ---- icons, drawn here (no icon files, sharp at every size)
def icon(kind, color="#1B1040", size=22):
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    s = float(size)

    def poly(pts):
        path = QPainterPath()
        path.moveTo(QPointF(pts[0][0] * s, pts[0][1] * s))
        for x, y in pts[1:]:
            path.lineTo(QPointF(x * s, y * s))
        path.closeSubpath()
        p.drawPath(path)
    if kind == "play":
        poly([(.28, .16), (.28, .84), (.84, .5)])
    elif kind == "pause":
        p.drawRoundedRect(int(s * .22), int(s * .16), int(s * .2), int(s * .68), 2, 2)
        p.drawRoundedRect(int(s * .58), int(s * .16), int(s * .2), int(s * .68), 2, 2)
    elif kind == "stop":
        p.drawRoundedRect(int(s * .22), int(s * .22), int(s * .56), int(s * .56), 3, 3)
    elif kind == "next":
        poly([(.18, .2), (.18, .8), (.62, .5)])
        p.drawRect(int(s * .68), int(s * .2), int(s * .13), int(s * .6))
    elif kind == "prev":
        poly([(.82, .2), (.82, .8), (.38, .5)])
        p.drawRect(int(s * .19), int(s * .2), int(s * .13), int(s * .6))
    elif kind in ("volume", "mute"):
        poly([(.1, .38), (.28, .38), (.5, .18), (.5, .82), (.28, .62), (.1, .62)])
        p.setBrush(Qt.NoBrush)
        pen = QPen(c, s * .075, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        if kind == "volume":
            p.drawArc(int(s * .42), int(s * .3), int(s * .26), int(s * .4), -60 * 16, 120 * 16)
            p.drawArc(int(s * .42), int(s * .17), int(s * .42), int(s * .66), -60 * 16, 120 * 16)
        else:
            p.drawLine(QPointF(s * .62, s * .38), QPointF(s * .9, s * .62))
            p.drawLine(QPointF(s * .9, s * .38), QPointF(s * .62, s * .62))
    elif kind == "list":
        for i in range(3):
            y = s * (.24 + i * .26)
            p.drawRoundedRect(int(s * .1), int(y), int(s * .1), int(s * .1), 1, 1)
            p.drawRoundedRect(int(s * .28), int(y), int(s * .62), int(s * .1), 2, 2)
    elif kind in ("full", "window"):
        p.setBrush(Qt.NoBrush)
        pen = QPen(c, s * .085, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        p.setPen(pen)
        m, a = s * .14, s * .26
        pts = [((m, m + a), (m, m), (m + a, m)), ((s - m - a, m), (s - m, m), (s - m, m + a)),
               ((m, s - m - a), (m, s - m), (m + a, s - m)), ((s - m - a, s - m), (s - m, s - m), (s - m, s - m - a))]
        if kind == "window":
            d = s * .12
            pts = [((m + a, m + a - d + d), (m + a, m + a), (m, m + a)), ((s - m - a, m), (s - m - a, m + a), (s - m, m + a)),
                   ((m, s - m - a), (m + a, s - m - a), (m + a, s - m)), ((s - m, s - m - a), (s - m - a, s - m - a), (s - m - a, s - m))]
        for t in pts:
            path = QPainterPath()
            path.moveTo(QPointF(*t[0]))
            path.lineTo(QPointF(*t[1]))
            path.lineTo(QPointF(*t[2]))
            p.drawPath(path)
    elif kind in ("repeat", "repeat1", "shuffle"):
        p.setBrush(Qt.NoBrush)
        pen = QPen(c, s * .08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if kind == "shuffle":
            path = QPainterPath()
            path.moveTo(s * .1, s * .3)
            path.cubicTo(s * .45, s * .3, s * .45, s * .7, s * .8, s * .7)
            p.drawPath(path)
            path = QPainterPath()
            path.moveTo(s * .1, s * .7)
            path.cubicTo(s * .45, s * .7, s * .45, s * .3, s * .8, s * .3)
            p.drawPath(path)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            poly([(.78, .16), (.94, .3), (.78, .44)])
            poly([(.78, .56), (.94, .7), (.78, .84)])
        else:
            p.drawRoundedRect(int(s * .12), int(s * .26), int(s * .76), int(s * .48), s * .18, s * .18)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            poly([(.6, .14), (.8, .26), (.6, .38)])
            poly([(.4, .62), (.2, .74), (.4, .86)])
            if kind == "repeat1":
                p.setPen(c)
                f = p.font()
                f.setPixelSize(int(s * .4))
                f.setBold(True)
                p.setFont(f)
                p.drawText(QPointF(s * .42, s * .62), "1")
    elif kind == "music":
        p.drawEllipse(QPointF(s * .34, s * .74), s * .17, s * .13)
        p.drawEllipse(QPointF(s * .78, s * .66), s * .17, s * .13)
        p.drawRect(int(s * .46), int(s * .2), int(s * .08), int(s * .55))
        p.drawRect(int(s * .9), int(s * .12), int(s * .08), int(s * .55))
        poly([(.46, .2), (.98, .12), (.98, .26), (.46, .34)])
    p.end()
    return QIcon(pm)


class NullAudio:
    """stands in for the sound output when there is none (only used by DIGONTO_PLAYER_NOAUDIO=1, for tests on a machine without sound)"""

    def __init__(self):
        self._v, self._m = 0.8, False

    def setVolume(self, v):
        self._v = v

    def volume(self):
        return self._v

    def setMuted(self, m):
        self._m = m

    def isMuted(self):
        return self._m

    def device(self):
        return None

    def setDevice(self, d):
        pass


class JumpSlider(QSlider):
    """a slider where a click moves the handle to the click (not one page step)"""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            span = max(1, self.width() - 1)
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / span
            self.setValue(int(round(max(self.minimum(), min(self.maximum(), v)))))
            self.sliderMoved.emit(self.value())
            self.sliderPressed.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            span = max(1, self.width() - 1)
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / span
            self.setValue(int(round(max(self.minimum(), min(self.maximum(), v)))))
            self.sliderMoved.emit(self.value())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.sliderReleased.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)


def tool(ic, tip, fn, checkable=False):
    b = QToolButton()
    b.setIcon(ic)
    b.setIconSize(QSize(22, 22))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    b.setAutoRaise(True)
    b.setStyleSheet("QToolButton{border:none; border-radius:6px; padding:5px;} QToolButton:hover{background:#E3D7EF;} QToolButton:checked{background:#FBDCE5;}")
    b.clicked.connect(fn)
    return b


class Main(QMainWindow):
    def __init__(self, paths=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.icon = ui.app_icon(HERE, SLUG)
        self.setWindowIcon(self.icon)
        ui.fit_window(self, 1180, 720)
        self.setMinimumSize(560, 380)
        self.setAcceptDrops(True)
        self.st = QSettings("Digonto", "Player")
        self.items = []            # file paths or addresses, in the order of the list
        self.order = []            # play order (indexes into items; shuffled when shuffle is on)
        self.pos_in_order = -1
        self.repeat = int(self.st.value("repeat", 0))      # 0 off, 1 all, 2 one
        self.shuffle = str(self.st.value("shuffle", "false")).lower() == "true"
        self.seeking = False
        self.full = False
        self.resume = {}
        try:
            self.resume = json.loads(str(self.st.value("resume", "{}")))
        except ValueError:
            self.resume = {}
        self.pending_seek = 0

        self.player = QMediaPlayer(self)
        if os.environ.get("DIGONTO_PLAYER_NOAUDIO"):
            self.audio = NullAudio()
        else:
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
        self.audio.setVolume(float(self.st.value("volume", 0.8)))
        self.audio.setMuted(str(self.st.value("muted", "false")).lower() == "true")
        self.video = QVideoWidget()
        self.video.setStyleSheet("background:black;")
        self.video.setMouseTracking(True)
        self.player.setVideoOutput(self.video)

        # ---- the stage: video, or a music page
        self.stage = QStackedWidget()
        self.start_page = ui.StartScreen(
            "Play video and music - all common formats, folders and play lists",
            [("Open files …", "open", self.open_files, True), ("Open folder …", "folder", self.open_folder, False)],
            "or drop video or music here", lambda: ui.recent_paths(SLUG), self.open_path)
        self.music_page = self._music_page()
        self.stage.addWidget(self.start_page)
        self.stage.addWidget(self.video)
        self.stage.addWidget(self.music_page)
        self.video.installEventFilter(self)
        self.music_page.installEventFilter(self)

        # ---- play list (side panel)
        self.side = QWidget()
        self.side.setFixedWidth(300)
        sv = QVBoxLayout(self.side)
        sv.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Play list</b>"))
        top.addStretch()
        for t, fn in (("Add ...", self.open_files), ("Clear", self.clear_list)):
            b = QPushButton(t)
            b.clicked.connect(fn)
            top.addWidget(b)
        sv.addLayout(top)
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemDoubleClicked.connect(lambda it: self.play_index(self.list.row(it)))
        self.list.model().rowsMoved.connect(self._list_moved)
        self.list.setStyleSheet("QListWidget::item{padding:5px 4px;} QListWidget::item:selected{background:#FBDCE5; color:#1B1040;}")
        sv.addWidget(self.list, 1)
        self.side.setVisible(str(self.st.value("playlist", "true")).lower() == "true")

        # ---- controls
        self.bar = QWidget()
        self.bar.setStyleSheet("QWidget#bar{background:#F6F2FA; border-top:1px solid #DDD3E9;}")
        self.bar.setObjectName("bar")
        bv = QVBoxLayout(self.bar)
        bv.setContentsMargins(10, 6, 10, 6)
        bv.setSpacing(2)
        srow = QHBoxLayout()
        self.tcur = QLabel("0:00")
        self.tcur.setMinimumWidth(54)
        self.tcur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.tend = QLabel("0:00")
        self.tend.setMinimumWidth(54)
        self.seek = JumpSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setStyleSheet("QSlider::groove:horizontal{height:6px; background:#DDD3E9; border-radius:3px;}"
                                "QSlider::sub-page:horizontal{background:#C2395C; border-radius:3px;}"
                                "QSlider::handle:horizontal{background:#8A2150; width:14px; margin:-5px 0; border-radius:7px;}")
        self.seek.sliderPressed.connect(lambda: setattr(self, "seeking", True))
        self.seek.sliderReleased.connect(self._seek_done)
        self.seek.sliderMoved.connect(lambda v: self.tcur.setText(fmt_time(v)))
        srow.addWidget(self.tcur)
        srow.addWidget(self.seek, 1)
        srow.addWidget(self.tend)
        bv.addLayout(srow)
        brow = QHBoxLayout()
        brow.setSpacing(2)
        self.b_prev = tool(icon("prev"), "Previous (B)", self.previous)
        self.b_play = tool(icon("play"), "Play / pause (Space)", self.toggle)
        self.b_stop = tool(icon("stop"), "Stop (S)", self.stop)
        self.b_next = tool(icon("next"), "Next (N)", self.next)
        self.b_shuf = tool(icon("shuffle"), "Shuffle (H)", self.toggle_shuffle, True)
        self.b_rep = tool(icon("repeat"), "Repeat: off (R)", self.cycle_repeat)
        for b in (self.b_prev, self.b_play, self.b_stop, self.b_next):
            brow.addWidget(b)
        brow.addSpacing(10)
        brow.addWidget(self.b_shuf)
        brow.addWidget(self.b_rep)
        brow.addSpacing(10)
        self.title = QLabel("")
        self.title.setStyleSheet("color:#3B2A63;")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        brow.addWidget(self.title, 1)
        self.speed_btn = QPushButton("1x")
        self.speed_btn.setToolTip("Speed")
        self.speed_btn.setFixedWidth(52)
        self.speed_btn.clicked.connect(self.speed_menu)
        brow.addWidget(self.speed_btn)
        self.b_mute = tool(icon("volume"), "Mute (M)", self.toggle_mute)
        brow.addWidget(self.b_mute)
        self.vol = JumpSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(110)
        self.vol.setValue(int(self.audio.volume() * 100))
        self.vol.setStyleSheet(self.seek.styleSheet())
        self.vol.valueChanged.connect(self.set_volume)
        brow.addWidget(self.vol)
        self.b_list = tool(icon("list"), "Show / hide the play list (L)", self.toggle_list, True)
        self.b_list.setChecked(self.side.isVisible())
        self.b_full = tool(icon("full"), "Full screen (F)", self.toggle_full)
        brow.addWidget(self.b_list)
        brow.addWidget(self.b_full)
        bv.addLayout(brow)

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.rail = ui.Rail(
            [("open", "open", "Open files (Ctrl+O)", self.open_files),
             ("folder", "folder", "Open a folder", self.open_folder),
             ("url", "export", "Open a web address (stream)", self.open_url),
             ("snapshot", "img2pdf", "Save a picture of the video", self.snapshot),
             None,
             ("playlist", "playlist", "Show or hide the play list (L)", self.toggle_list),
             ("full", "crop", "Full screen (F)", self.toggle_full)],
            [("settings", "settings", "Settings and help", self.rail_settings)])
        bl.addWidget(self.rail)
        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(self.stage, 1)
        left.addWidget(self.bar)
        bl.addLayout(left, 1)
        bl.addWidget(self.side)
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.header = ui.make_header(APP_NAME, "Play video and music", self.icon, self.about)
        cl.addWidget(self.header)
        cl.addWidget(body, 1)
        self.setCentralWidget(central)
        self.statusBar().setStyleSheet("QStatusBar{background:#EDE6F4; color:#5B5278;}")

        self.build_menu()
        self.hide_timer = QTimer(self, singleShot=True, interval=2500, timeout=self._hide_controls)
        self.click_timer = QTimer(self, singleShot=True, interval=240, timeout=self.toggle)

        p = self.player
        p.positionChanged.connect(self._position)
        p.durationChanged.connect(self._duration)
        p.playbackStateChanged.connect(self._state)
        p.mediaStatusChanged.connect(self._status)
        p.errorOccurred.connect(self._error)
        p.metaDataChanged.connect(self._meta)
        p.tracksChanged.connect(self._tracks)
        p.hasVideoChanged.connect(self._stage)
        self._sync_icons()
        geo = self.st.value("geometry")
        if geo:
            try:
                self.restoreGeometry(geo)
            except Exception:  # noqa: BLE001
                pass
        if paths:
            self.open_paths(paths)

    # ------------------------------------------------------------------ pages
    def _start_page(self):
        w = QWidget()
        w.setObjectName("start")
        w.setStyleSheet("QWidget#start{background:#1B1040;} QLabel{background:transparent;}"
                        "QPushButton{background:white; color:#1B1040; border:none; border-radius:8px; padding:9px 20px;"
                        " font-size:14px; font-weight:600; min-width:130px;}"
                        "QPushButton:hover{background:#FBDCE5;} QPushButton:pressed{background:#F3C3D3;}")
        v = QVBoxLayout(w)
        v.addStretch()
        pic = QLabel()
        pic.setPixmap(self.icon.pixmap(QSize(110, 110)))
        pic.setAlignment(Qt.AlignCenter)
        v.addWidget(pic)
        t = QLabel("<span style='font-size:20px; color:white; font-weight:600'>Digonto Player</span><br>"
                   "<span style='font-size:13px; color:#CDBFE3'>Drop video or music here, or press Open.</span>")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        row = QHBoxLayout()
        row.addStretch()
        b1 = QPushButton("Open files ...")
        b1.clicked.connect(self.open_files)
        b2 = QPushButton("Open folder ...")
        b2.clicked.connect(self.open_folder)
        row.addWidget(b1)
        row.addSpacing(10)
        row.addWidget(b2)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return w

    def _music_page(self):
        w = QWidget()
        w.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1D1548,stop:0.55 #4A1F6E,stop:1 #8A2150);")
        v = QVBoxLayout(w)
        v.addStretch()
        self.cover = QLabel()
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet("background:transparent;")
        v.addWidget(self.cover)
        self.mtitle = QLabel("")
        self.mtitle.setAlignment(Qt.AlignCenter)
        self.mtitle.setWordWrap(True)
        self.mtitle.setStyleSheet("background:transparent; color:white; font-size:22px; font-weight:600;")
        self.msub = QLabel("")
        self.msub.setAlignment(Qt.AlignCenter)
        self.msub.setWordWrap(True)
        self.msub.setStyleSheet("background:transparent; color:#E9D5EE; font-size:14px;")
        v.addWidget(self.mtitle)
        v.addWidget(self.msub)
        v.addStretch()
        self._default_cover()
        return w

    def _default_cover(self):
        pm = icon("music", "#FFB05A", 120).pixmap(QSize(120, 120))
        self.cover.setPixmap(pm)

    def _stage(self, *_):
        if hasattr(self, "rail"):
            self.rail.set_enabled(["snapshot"], bool(self.items) and self.player.hasVideo())
        if not self.items:
            self.start_page.refresh()
            self.stage.setCurrentWidget(self.start_page)
        elif self.player.hasVideo():
            self.stage.setCurrentWidget(self.video)
        else:
            self.stage.setCurrentWidget(self.music_page)

    # ------------------------------------------------------------------ menu
    def build_menu(self):
        mb = self.menuBar()

        def add(menu, text, fn, key=None, checkable=False):
            a = QAction(text, self)
            if key:
                a.setShortcut(QKeySequence(key))
            a.setCheckable(checkable)
            a.triggered.connect(lambda _=False, fn=fn: fn())
            menu.addAction(a)
            return a
        fm = mb.addMenu("File")
        add(fm, "Open files ...", self.open_files, "Ctrl+O")
        add(fm, "Open folder ...", self.open_folder, "Ctrl+Shift+O")
        add(fm, "Open web address ...", self.open_url, "Ctrl+U")
        self.recent_menu = fm.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        fm.addSeparator()
        add(fm, "Save play list ...", self.save_list, "Ctrl+S")
        add(fm, "Save picture of this moment ...", self.snapshot, "Ctrl+Shift+S")
        fm.addSeparator()
        add(fm, "Close project", self.close_project, "Ctrl+W")
        fm.addSeparator()
        add(fm, "Exit", self.close, "Ctrl+Q")
        add(fm, "Quit (force)", lambda: os._exit(0), "Ctrl+Shift+Q")

        pm = mb.addMenu("Playback")
        self.a_play = add(pm, "Play / pause", self.toggle, "Space")
        add(pm, "Stop", self.stop, "S")
        add(pm, "Next", self.next, "N")
        add(pm, "Previous", self.previous, "B")
        pm.addSeparator()
        add(pm, "Back 5 seconds", lambda: self.skip(-5000), "Left")
        add(pm, "Forward 5 seconds", lambda: self.skip(5000), "Right")
        add(pm, "Back 30 seconds", lambda: self.skip(-30000), "Shift+Left")
        add(pm, "Forward 30 seconds", lambda: self.skip(30000), "Shift+Right")
        add(pm, "Back 5 minutes", lambda: self.skip(-300000), "Ctrl+Left")
        add(pm, "Forward 5 minutes", lambda: self.skip(300000), "Ctrl+Right")
        pm.addSeparator()
        self.a_shuf = add(pm, "Shuffle", self.toggle_shuffle, "H", True)
        self.a_shuf.setChecked(self.shuffle)
        add(pm, "Repeat: off / all / one", self.cycle_repeat, "R")
        pm.addSeparator()
        sp = pm.addMenu("Speed")
        grp = QActionGroup(self)
        for sv in SPEEDS:
            a = QAction(f"{sv:g}x", self, checkable=True)
            a.setChecked(sv == 1.0)
            a.triggered.connect(lambda _=False, sv=sv: self.set_speed(sv))
            grp.addAction(a)
            sp.addAction(a)
        self.speed_actions = grp
        add(sp, "Slower", lambda: self.step_speed(-1), "[")
        add(sp, "Faster", lambda: self.step_speed(1), "]")
        add(sp, "Normal speed", lambda: self.set_speed(1.0), "\\")

        am = mb.addMenu("Audio")
        add(am, "Louder", lambda: self.step_volume(5), "Up")
        add(am, "Quieter", lambda: self.step_volume(-5), "Down")
        add(am, "Mute", self.toggle_mute, "M")
        am.addSeparator()
        self.track_menu = am.addMenu("Audio track")
        self.sub_menu = am.addMenu("Subtitles")
        self.dev_menu = am.addMenu("Output device")
        self.dev_menu.aboutToShow.connect(self._fill_devices)

        vm = mb.addMenu("View")
        add(vm, "Full screen", self.toggle_full, "F")
        add(vm, "Leave full screen", self.leave_full, "Esc")
        self.a_list = add(vm, "Play list", self.toggle_list, "L", True)
        self.a_list.setChecked(self.side.isVisible())
        vm.addSeparator()
        ar = vm.addMenu("Picture shape")
        g2 = QActionGroup(self)
        for text, mode in (("Fit (keep the shape)", Qt.KeepAspectRatio), ("Fill (crop the edges)", Qt.KeepAspectRatioByExpanding),
                           ("Stretch", Qt.IgnoreAspectRatio)):
            a = QAction(text, self, checkable=True)
            a.setChecked(mode == Qt.KeepAspectRatio)
            a.triggered.connect(lambda _=False, mode=mode: self.video.setAspectRatioMode(mode))
            g2.addAction(a)
            ar.addAction(a)
        self.a_top = add(vm, "Always on top", self.toggle_top, "T", True)
        # Help (Quick help / All shortcuts / About) is added by the Digonto UI

    # ------------------------------------------------------------------ open
    def open_files(self):
        d = str(self.st.value("last_dir", ""))
        ps, _ = QFileDialog.getOpenFileNames(self, "Open video or music", d,
                                             "Video and music (" + " ".join("*" + e for e in MEDIA + LISTS) + ");;All files (*)")
        if ps:
            self.st.setValue("last_dir", os.path.dirname(ps[0]))
            self.open_paths(ps)

    def rail_settings(self):
        m = QMenu(self)
        m.addAction("Keyboard shortcuts", lambda: ui.show_all_shortcuts(self, APP_NAME))
        m.addAction(f"About {APP_NAME}", self.about)
        b = self.rail.button("settings")
        m.exec(b.mapToGlobal(b.rect().topRight()))

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open a folder with video or music", str(self.st.value("last_dir", "")))
        if d:
            self.st.setValue("last_dir", d)
            self.open_paths([d])

    def open_url(self):
        u, ok = QInputDialog.getText(self, "Open web address", "Address of a video or music file or stream (http / https):")
        if ok and u.strip().startswith(("http://", "https://")):
            self.open_paths([u.strip()])

    def open_path(self, path):          # one file, from another launch of the program
        self.open_paths([path])

    def open_paths(self, paths, play=True):
        new = expand([str(p) for p in paths])
        if not new:
            self.statusBar().showMessage("Nothing to play there (video or music files, folders and .m3u lists work).", 4000)
            return
        start = len(self.items)
        fresh = not self.items
        for p in new:
            self._add_item(p)
        if paths and os.path.exists(str(paths[0])):
            add_recent(os.path.abspath(str(paths[0])))
        self._rebuild_order()
        if play and (fresh or self.player.playbackState() == QMediaPlayer.StoppedState or len(paths) == 1):
            self.play_index(start)
        self._enable()

    def _add_item(self, p):
        self.items.append(p)
        name = os.path.basename(p) if not p.startswith("http") else p
        it = QListWidgetItem(os.path.splitext(name)[0] if not p.startswith("http") else name)
        it.setToolTip(p)
        self.list.addItem(it)

    def _list_moved(self, *_):
        """the list was re-ordered by dragging: the items follow it"""
        cur = self.items[self.order[self.pos_in_order]] if 0 <= self.pos_in_order < len(self.order) else None
        self.items = [self.list.item(i).toolTip() for i in range(self.list.count())]
        self._rebuild_order()
        if cur in self.items:
            self.pos_in_order = self.order.index(self.items.index(cur))
        self._mark()

    def clear_list(self):
        self.stop()
        self.items, self.order, self.pos_in_order = [], [], -1
        self.list.clear()
        self.player.setSource(QUrl())
        self.title.setText("")
        self.setWindowTitle(APP_NAME)
        self._stage()
        self._enable()

    def close_project(self):
        self.clear_list()

    def save_list(self):
        if not self.items:
            self.statusBar().showMessage("The play list is empty.", 3000)
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save play list", str(self.st.value("last_dir", "")) + "/playlist.m3u", "Play list (*.m3u *.m3u8)")
        if p:
            if not p.lower().endswith(LISTS):
                p += ".m3u"
            try:
                write_m3u(p, self.items)
                self.statusBar().showMessage("Saved " + p, 4000)
            except OSError as e:
                QMessageBox.warning(self, APP_NAME, f"Could not save the play list.\n{e}")

    def _fill_recent(self):
        self.recent_menu.clear()
        rp = os.path.join(base_dir(), "recent.json")
        try:
            with open(rp, encoding="utf-8") as f:
                rec = [r for r in json.load(f) if isinstance(r, dict) and r.get("app") == SLUG and os.path.exists(r.get("path", ""))]
        except (OSError, ValueError):
            rec = []
        for r in rec[:10]:
            a = self.recent_menu.addAction(os.path.basename(r["path"]))
            a.triggered.connect(lambda _=False, p=r["path"]: self.open_paths([p]))
        if not rec:
            self.recent_menu.addAction("(nothing yet)").setEnabled(False)

    # ------------------------------------------------------------------ order
    def _rebuild_order(self):
        cur = self.order[self.pos_in_order] if 0 <= self.pos_in_order < len(self.order) else None
        self.order = list(range(len(self.items)))
        if self.shuffle:
            random.shuffle(self.order)
            if cur is not None and cur in self.order:       # the playing one stays first
                self.order.remove(cur)
                self.order.insert(0, cur)
        self.pos_in_order = self.order.index(cur) if cur is not None and cur in self.order else -1

    def play_index(self, i):
        """play the item with this number in the list"""
        if not 0 <= i < len(self.items):
            return
        if i not in self.order:
            self._rebuild_order()
        self.pos_in_order = self.order.index(i)
        self._load(i)

    def _load(self, i):
        self._save_resume()
        p = self.items[i]
        self.player.setSource(QUrl(p) if p.startswith("http") else QUrl.fromLocalFile(p))
        key = p
        self.pending_seek = int(self.resume.get(key, 0)) if not p.startswith("http") else 0
        self.title.setText(os.path.splitext(os.path.basename(p))[0] if not p.startswith("http") else p)
        self.setWindowTitle(f"{self.title.text()} - {APP_NAME}")
        self.mtitle.setText(self.title.text())
        self.msub.setText("")
        self._default_cover()
        self.player.play()
        self._mark()
        self._stage()

    def _mark(self):
        cur = self.order[self.pos_in_order] if 0 <= self.pos_in_order < len(self.order) else -1
        for r in range(self.list.count()):
            it = self.list.item(r)
            f = it.font()
            f.setBold(r == cur)
            it.setFont(f)
            it.setForeground(QColor("#8A2150") if r == cur else QColor("#1B1040"))
        if cur >= 0:
            self.list.scrollToItem(self.list.item(cur))

    def next(self):
        if not self.order:
            return
        n = self.pos_in_order + 1
        if n >= len(self.order):
            if self.repeat == 1:
                n = 0
            else:
                return
        self.pos_in_order = n
        self._load(self.order[n])

    def previous(self):
        if not self.order:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        n = self.pos_in_order - 1
        if n < 0:
            n = len(self.order) - 1 if self.repeat == 1 else 0
        self.pos_in_order = n
        self._load(self.order[n])

    # ------------------------------------------------------------------ playback
    def toggle(self):
        if not self.items:
            self.open_files()
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.player.playbackState() == QMediaPlayer.StoppedState and self.player.mediaStatus() == QMediaPlayer.EndOfMedia:
                self.player.setPosition(0)
            if self.player.source().isEmpty() and self.pos_in_order < 0 and self.order:
                self.play_index(0)
            else:
                self.player.play()

    def stop(self):
        self._save_resume()
        self.player.stop()

    def skip(self, ms):
        if not self.items:
            return
        d = self.player.duration()
        t = self.player.position() + ms
        self.player.setPosition(max(0, min(t, d if d > 0 else t)))
        self.statusBar().showMessage(fmt_time(self.player.position()), 1200)

    def _seek_done(self):
        self.seeking = False
        self.player.setPosition(self.seek.value())

    def _position(self, ms):
        if not self.seeking:
            self.seek.setValue(ms)
            self.tcur.setText(fmt_time(ms))

    def _duration(self, ms):
        self.seek.setRange(0, max(0, ms))
        self.tend.setText(fmt_time(ms))
        if ms > 0 and self.pending_seek > 5000 and self.pending_seek < ms - 10000:
            self.player.setPosition(self.pending_seek)
            self.statusBar().showMessage("Continued where you stopped: " + fmt_time(self.pending_seek), 3000)
        self.pending_seek = 0

    def _state(self, s):
        self._sync_icons()

    def _status(self, s):
        if s == QMediaPlayer.EndOfMedia:
            key = self.items[self.order[self.pos_in_order]] if 0 <= self.pos_in_order < len(self.order) else None
            if key:
                self.resume.pop(key, None)
            if self.repeat == 2:
                self.player.setPosition(0)
                self.player.play()
            elif self.pos_in_order + 1 < len(self.order) or self.repeat == 1:
                self.next()
            else:
                self._sync_icons()

    def _error(self, err, text):
        name = self.title.text()
        self.statusBar().showMessage(f"Cannot play {name}: {text}", 8000)
        if self.pos_in_order + 1 < len(self.order):
            QTimer.singleShot(600, self.next)

    def _save_resume(self):
        """long files continue where you stopped"""
        try:
            if 0 <= self.pos_in_order < len(self.order):
                p = self.items[self.order[self.pos_in_order]]
                pos, d = self.player.position(), self.player.duration()
                if not p.startswith("http") and d > 600000 and 5000 < pos < d - 10000:
                    self.resume[p] = pos
                    if len(self.resume) > 60:
                        self.resume.pop(next(iter(self.resume)))
                else:
                    self.resume.pop(p, None)
        except Exception:  # noqa: BLE001
            pass

    def _sync_icons(self):
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.b_play.setIcon(icon("pause" if playing else "play"))
        self.b_mute.setIcon(icon("mute" if (self.audio.isMuted() or self.audio.volume() == 0) else "volume"))
        self.b_rep.setIcon(icon("repeat1" if self.repeat == 2 else "repeat"))
        self.b_rep.setStyleSheet(self.b_rep.styleSheet() + ("QToolButton{background:#FBDCE5;}" if self.repeat else ""))
        self.b_rep.setToolTip("Repeat: " + ("off", "all", "one")[self.repeat] + " (R)")
        self.b_shuf.setChecked(self.shuffle)
        self.b_full.setIcon(icon("window" if self.full else "full"))

    def _enable(self):
        has = bool(self.items)
        for b in (self.b_prev, self.b_play, self.b_stop, self.b_next):
            b.setEnabled(has)

    # ------------------------------------------------------------------ sound, speed, modes
    def set_volume(self, v):
        self.audio.setVolume(v / 100.0)
        if v > 0 and self.audio.isMuted():
            self.audio.setMuted(False)
        self._sync_icons()

    def step_volume(self, d):
        v = max(0, min(100, self.vol.value() + d))
        self.vol.setValue(v)
        self.statusBar().showMessage(f"Volume {v} %", 1200)

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self._sync_icons()

    def set_speed(self, v):
        self.player.setPlaybackRate(v)
        self.speed_btn.setText(f"{v:g}x")
        for a in self.speed_actions.actions():
            a.setChecked(a.text() == f"{v:g}x")

    def step_speed(self, d):
        cur = min(SPEEDS, key=lambda s: abs(s - self.player.playbackRate()))
        i = max(0, min(len(SPEEDS) - 1, SPEEDS.index(cur) + d))
        self.set_speed(SPEEDS[i])

    def speed_menu(self):
        m = QMenu(self)
        for sv in SPEEDS:
            a = m.addAction(f"{sv:g}x")
            a.setCheckable(True)
            a.setChecked(abs(sv - self.player.playbackRate()) < 0.01)
            a.triggered.connect(lambda _=False, sv=sv: self.set_speed(sv))
        m.exec(self.speed_btn.mapToGlobal(QPoint(0, -m.sizeHint().height())))

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.a_shuf.setChecked(self.shuffle)
        self._rebuild_order()
        self._sync_icons()
        self.statusBar().showMessage("Shuffle " + ("on" if self.shuffle else "off"), 1500)

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        self._sync_icons()
        self.statusBar().showMessage("Repeat: " + ("off", "all", "one")[self.repeat], 1500)

    # ------------------------------------------------------------------ tracks, devices
    def _tracks(self):
        for menu, tracks, active, setter in ((self.track_menu, self.player.audioTracks(), self.player.activeAudioTrack(), self.player.setActiveAudioTrack),
                                             (self.sub_menu, self.player.subtitleTracks(), self.player.activeSubtitleTrack(), self.player.setActiveSubtitleTrack)):
            menu.clear()
            grp = QActionGroup(self)
            if menu is self.sub_menu:
                a = QAction("Off", self, checkable=True)
                a.setChecked(active < 0)
                a.triggered.connect(lambda _=False: self.player.setActiveSubtitleTrack(-1))
                grp.addAction(a)
                menu.addAction(a)
            for i, t in enumerate(tracks):
                lang = t.stringValue(QMediaMetaData.Language) if hasattr(t, "stringValue") else ""
                ttl = t.stringValue(QMediaMetaData.Title) if hasattr(t, "stringValue") else ""
                name = " - ".join(x for x in (f"Track {i + 1}", ttl, lang) if x)
                a = QAction(name, self, checkable=True)
                a.setChecked(i == active)
                a.triggered.connect(lambda _=False, i=i, setter=setter: setter(i))
                grp.addAction(a)
                menu.addAction(a)
            if not tracks and menu is self.track_menu:
                menu.addAction("(no other tracks)").setEnabled(False)
            if not tracks and menu is self.sub_menu:
                menu.addAction("(no subtitles in this file)").setEnabled(False)

    def _fill_devices(self):
        self.dev_menu.clear()
        grp = QActionGroup(self)
        cur = self.audio.device()
        for d in QMediaDevices.audioOutputs():
            a = QAction(d.description(), self, checkable=True)
            a.setChecked(cur is not None and d.id() == cur.id())
            a.triggered.connect(lambda _=False, d=d: self.audio.setDevice(d))
            grp.addAction(a)
            self.dev_menu.addAction(a)

    def _meta(self):
        md = self.player.metaData()
        t = md.stringValue(QMediaMetaData.Title)
        art = md.stringValue(QMediaMetaData.AlbumArtist) or md.stringValue(QMediaMetaData.ContributingArtist)
        alb = md.stringValue(QMediaMetaData.AlbumTitle)
        if t:
            self.mtitle.setText(t)
            self.title.setText((art + " - " if art else "") + t)
            self.setWindowTitle(f"{self.title.text()} - {APP_NAME}")
        self.msub.setText(" - ".join(x for x in (art, alb) if x))
        img = md.value(QMediaMetaData.CoverArtImage) or md.value(QMediaMetaData.ThumbnailImage)
        if isinstance(img, QImage) and not img.isNull():
            self.cover.setPixmap(QPixmap.fromImage(img).scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------------------------ view
    def toggle_list(self):
        on = not self.side.isVisible()
        self.side.setVisible(on)
        self.b_list.setChecked(on)
        self.a_list.setChecked(on)

    def toggle_top(self):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.a_top.isChecked())
        self.show()

    def toggle_full(self):
        if self.full:
            self.leave_full()
            return
        self.full = True
        self._was_max = self.isMaximized()
        self._side_was = self.side.isVisible()
        self.menuBar().hide()
        self.header.hide()
        self.statusBar().hide()
        self.side.hide()
        self.rail.hide()
        self.showFullScreen()
        self._sync_icons()
        self.hide_timer.start()

    def leave_full(self):
        if not self.full:
            return
        self.full = False
        self.hide_timer.stop()
        self.menuBar().show()
        self.header.setVisible(str(QSettings("Digonto", "ui").value("header_hidden", "false")).lower() != "true")
        self.statusBar().show()
        self.bar.show()
        self.rail.show()
        self.side.setVisible(self._side_was)
        self.unsetCursor()
        self.video.unsetCursor()
        if self._was_max:
            self.showMaximized()
        else:
            self.showNormal()
        self._sync_icons()

    def _hide_controls(self):
        if self.full and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.bar.hide()
            self.video.setCursor(Qt.BlankCursor)
            self.music_page.setCursor(Qt.BlankCursor)

    def _wake(self):
        if self.full:
            self.bar.show()
            self.video.unsetCursor()
            self.music_page.unsetCursor()
            self.hide_timer.start()

    def eventFilter(self, o, e):
        if o in (self.video, self.music_page):
            t = e.type()
            if t == QEvent.MouseMove:
                self._wake()
            elif t == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton:
                self.click_timer.start()                        # a second click within a moment is a double-click
            elif t == QEvent.MouseButtonDblClick:
                self.click_timer.stop()
                self.toggle_full()
                return True
            elif t == QEvent.Wheel:
                self.step_volume(5 if e.angleDelta().y() > 0 else -5)
                return True
        return super().eventFilter(o, e)

    def snapshot(self):
        if not self.player.hasVideo():
            self.statusBar().showMessage("There is no picture to save (this is music).", 3000)
            return
        img = self.video.videoSink().videoFrame().toImage()
        if img.isNull():
            self.statusBar().showMessage("Could not get the picture of this moment.", 3000)
            return
        name = os.path.splitext(self.title.text() or "picture")[0] + f" {fmt_time(self.player.position()).replace(':', '-')}.png"
        p, _ = QFileDialog.getSaveFileName(self, "Save picture", os.path.join(str(self.st.value("last_dir", "")), name), "PNG (*.png);;JPG (*.jpg)")
        if p:
            img.save(p)
            self.statusBar().showMessage("Saved " + p, 4000)

    # ------------------------------------------------------------------ drag and drop, keys, close
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            if self.stage.currentWidget() is self.start_page:
                self.start_page.set_dropping(True)

    def dragLeaveEvent(self, e):
        self.start_page.set_dropping(False)

    def dropEvent(self, e):
        self.start_page.set_dropping(False)
        ps = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if ps:
            self.open_paths(ps)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.full:
            self.leave_full()
            return
        super().keyPressEvent(e)

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3>{APP_NAME} {VERSION}</h3><p>Plays video and music: MP4, MKV, WebM, AVI, MOV, MP3, FLAC, WAV, OGG, Opus, M4A and more, "
                          "play lists, shuffle and repeat, speed 0.5x to 2x, audio tracks and subtitles inside the file, full screen.</p>"
                          "<p>Long files continue where you stopped. Built with Qt Multimedia (PySide6); nothing else is installed.</p>")

    def closeEvent(self, e):
        self._save_resume()
        self.st.setValue("volume", self.audio.volume())
        self.st.setValue("muted", "true" if self.audio.isMuted() else "false")
        self.st.setValue("repeat", self.repeat)
        self.st.setValue("shuffle", "true" if self.shuffle else "false")
        self.st.setValue("playlist", "true" if (self._side_was if self.full else self.side.isVisible()) else "false")
        self.st.setValue("resume", json.dumps(self.resume))
        if not self.full:
            self.st.setValue("geometry", self.saveGeometry())
        self.player.stop()
        e.accept()
        QTimer.singleShot(1200, lambda: os._exit(0))


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    ui.mac_app_name(APP_NAME)
    app = QApplication(sys.argv)
    if ui.forward_to_running(SLUG, sys.argv[1:]):
        os._exit(0)
    ui.setup_app(app, APP_NAME, SLUG, ui.app_icon(HERE, SLUG), theme=True)
    from PySide6.QtCore import QObject

    class _Opener(QObject):          # macOS hands files to a program through an event (double-click, "Open with", dock drop)
        win = None
        pending = []

        def eventFilter(self, o, e):
            if e.type() == QEvent.FileOpen:
                if self.win is None:
                    self.pending.append(e.file())
                else:
                    self.win.open_paths([e.file()])
                return True
            return False
    opener = _Opener()
    app.installEventFilter(opener)
    files = [a for a in sys.argv[1:] if os.path.exists(a) or a.startswith("http")]
    w = Main(files)
    opener.win = w
    w.show()
    if opener.pending:
        w.open_paths(opener.pending)
    ui.serve_single(SLUG, w, w.open_path)
    rc = app.exec()
    os._exit(rc)


if __name__ == "__main__":
    main()
