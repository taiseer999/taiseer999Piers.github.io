"""Approach A helper (by ABUKARIM TOOLS): publish TinyPPI's player data onto the
Home window (10000) so a native skin dialog — Arctic Fuse 3's
DialogPlayerProcessInfo — can read it via $INFO[Window(10000).Property(*Var)]
even when TinyPPI's own overlay window is closed.

This module deliberately does NOT edit properties.py. TinyPPI's own
``update_properties(window)`` already writes every *Var onto whatever window it
is handed; we simply hand it a thin proxy for the Home window. That keeps this
version-agnostic: it works against whatever TinyPPI build is installed, with no
dependency on that build's internal structure (no whole-file replacement, so no
version-drift breakage such as a missing ``coded_frame`` import).

Started by the service (monitor.py) on a background thread while video plays.
"""

import os
import threading

import xbmc
import xbmcgui

_HOME_ID = 10000
_ADDON_ID = "script.tinyppi"

# Absolute media root for the channel-layout graphics, so a FOREIGN skin dialog
# (whose own media folder lacks TinyPPI's "channels/…" files) can still draw the
# speaker diagram. TinyPPI's own window keeps using the relative paths.
_MEDIA_ROOT = ("special://home/addons/%s/resources/skins/Default/media/"
               % _ADDON_ID)


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log("TinyPPI-PPIAF3: %s" % msg, level)


class _HomeProxy:
    """Quacks like an xbmcgui.Window for TinyPPI's update_properties():

    * setProperty / getProperty / clearProperty forward to the real Home window,
      so every *Var TinyPPI computes lands on Window(10000).
    * getControl returns a dummy whose setPercent is a no-op — Home has no
      progress controls (the overlay used control id 9100), and the skin dialog
      binds its <progress> to infolabels / a published property instead.
    """

    class _NullControl:
        def setPercent(self, _value):
            pass

        def setLabel(self, *_a, **_k):
            pass

        def setVisible(self, *_a, **_k):
            pass

    def __init__(self):
        self._home = xbmcgui.Window(_HOME_ID)
        self._null = self._NullControl()

    def setProperty(self, key, value):
        self._home.setProperty(key, value)

    def getProperty(self, key):
        return self._home.getProperty(key)

    def clearProperty(self, key):
        self._home.clearProperty(key)

    def getControl(self, _control_id):
        return self._null


def _publish_absolute_channel_paths(home):
    """Add absolute special:// twins of the two relative channel-image props so a
    foreign skin dialog can render them. Empty stays empty."""
    for rel_name, abs_name in (("ChannelLayerVar", "ChannelLayerAbsVar"),
                               ("ChannelIconVar", "ChannelIconAbsVar")):
        rel = home.getProperty(rel_name)
        home.setProperty(abs_name, (_MEDIA_ROOT + rel) if rel else "")


def _publish_cpu_temp_progress(home):
    """Publish the 0-100 CPU-temperature progress as a Home property so the skin
    dialog can bind a <progress> to it (the overlay used a control id instead)."""
    try:
        from info.properties import get_CpuTemperatureProgressVar
        home.setProperty("TinyPPI.CpuTempProgress",
                         str(get_CpuTemperatureProgressVar()))
    except Exception:
        pass


# Names TinyPPI has used (across builds) for "write every *Var onto this window".
# The installed build may expose any one of these; we probe in order. Resolved
# once and cached so the hot 1 Hz loop doesn't re-scan the module every tick.
_UPDATE_FN_NAMES = (
    "update_properties",   # <= 2.3.1
    "set_properties",
    "update_window_properties",
    "update_all",
    "update",
    "refresh_properties",
    "refresh",
    "publish",
    "publish_properties",
)

_update_fn = None
_resolve_failed = False


def _resolve_update_fn(properties):
    """Find the installed build's 'update every *Var onto <window>' callable.

    TinyPPI renamed this across versions, so a hard-coded name breaks whenever
    the user's installed build drifts (the observed
    'module info.properties has no attribute update_properties'). We try the
    known names, then fall back to any module-level function whose single
    required arg looks like a window sink.
    """
    for name in _UPDATE_FN_NAMES:
        fn = getattr(properties, name, None)
        if callable(fn):
            return fn

    # Last resort: a lone public function taking exactly one positional arg.
    import inspect
    candidates = []
    for name in dir(properties):
        if name.startswith("_"):
            continue
        fn = getattr(properties, name, None)
        if not callable(fn) or inspect.isclass(fn):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        required = [p for p in sig.parameters.values()
                    if p.default is p.empty
                    and p.kind in (p.POSITIONAL_ONLY,
                                   p.POSITIONAL_OR_KEYWORD)]
        if len(required) == 1:
            candidates.append((name, fn))
    if len(candidates) == 1:
        _log("resolved update fn by signature: %s" % candidates[0][0])
        return candidates[0][1]
    return None


def publish_once():
    """Compute TinyPPI's player properties straight onto Home (10000)."""
    global _update_fn, _resolve_failed

    from info import properties  # the installed build's own module

    if _update_fn is None:
        _update_fn = _resolve_update_fn(properties)
        if _update_fn is None:
            if not _resolve_failed:
                _resolve_failed = True
                _log("no compatible update function on info.properties "
                     "(tried: %s); Home bridge disabled for this session"
                     % ", ".join(_UPDATE_FN_NAMES), xbmc.LOGWARNING)
            return

    proxy = _HomeProxy()
    _update_fn(proxy)

    home = xbmcgui.Window(_HOME_ID)
    _publish_absolute_channel_paths(home)
    _publish_cpu_temp_progress(home)


def _enabled():
    """Opt-out via a settings flag; default ON."""
    try:
        import xbmcaddon
        return xbmcaddon.Addon().getSetting("home_publish") != "false"
    except Exception:
        return True


class HomePublisher(threading.Thread):
    """Keeps Home (10000) fresh with TinyPPI data while video plays, so the AF3
    dialog shows live values without TinyPPI's own overlay being open."""

    _INTERVAL = 1.0

    def __init__(self, monitor):
        super().__init__(name="TinyPPI-PPIAF3-HomePublisher", daemon=True)
        self._monitor = monitor
        self._player = xbmc.Player()

    _MAX_CONSECUTIVE_FAILURES = 5

    def run(self):
        _log("Home publisher started")
        fails = 0
        while not self._monitor.abortRequested():
            try:
                playing = (self._player.isPlaying()
                           and xbmc.getCondVisibility("Player.HasVideo"))
            except Exception:
                playing = False

            if not (playing and _enabled()):
                fails = 0  # fresh start next time media plays
                if self._monitor.waitForAbort(2.0):
                    break
                continue

            # After repeated failures, stop hammering at 1 Hz: log once and
            # idle until playback state changes. A single broken build must not
            # flood the log or add load during a playback transition.
            if fails >= self._MAX_CONSECUTIVE_FAILURES:
                if self._monitor.waitForAbort(5.0):
                    break
                continue

            try:
                publish_once()
                fails = 0
            except Exception as exc:
                fails += 1
                if fails <= self._MAX_CONSECUTIVE_FAILURES:
                    _log("publish failed (%d/%d): %s"
                         % (fails, self._MAX_CONSECUTIVE_FAILURES, exc),
                         xbmc.LOGERROR)
                if fails == self._MAX_CONSECUTIVE_FAILURES:
                    _log("suppressing further publish errors this session",
                         xbmc.LOGWARNING)

            if self._monitor.waitForAbort(self._INTERVAL):
                break
        _log("Home publisher stopped")


def start(monitor):
    """Start the background publisher; safe to call once from the service."""
    try:
        HomePublisher(monitor).start()
    except Exception as exc:  # pragma: no cover
        _log("failed to start: %s" % exc, xbmc.LOGWARNING)
