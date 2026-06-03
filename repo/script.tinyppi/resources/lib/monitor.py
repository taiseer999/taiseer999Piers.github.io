"""
monitor.py – Lightweight background service for TinyPPI.

Runs as an ``xbmc.service`` (see addon.xml) and keeps a Kodi monitor alive
for the lifetime of the session so that other parts of the addon can react
to system-level notifications.
"""

import json
import os
import sys
import threading

import xbmc
import xbmcaddon
import xbmcgui

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADDON_ID = "script.tinyppi"

_FORCE_DEBUG_LOG = False

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(msg: str, level: int = xbmc.LOGDEBUG) -> None:
    if level == xbmc.LOGDEBUG and _FORCE_DEBUG_LOG:
        level = xbmc.LOGINFO
    xbmc.log(f"{_ADDON_ID} --> {msg}", level=level)


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class KodiMonitor(xbmc.Monitor):

    def __init__(self, win: xbmcgui.Window, addon: xbmcaddon.Addon) -> None:
        super().__init__()
        self.win   = win
        self.addon = addon
        self._poll_thread = None

    def onNotification(self, sender: str, method: str, data: str) -> None:
        try:
            payload   = json.loads(data)
            mediatype = ""

            if isinstance(payload, dict):
                item = payload.get("item") or {}
                mediatype = item.get("type", "") or payload.get("type", "")

            _log(f"sender={sender}  method={method}  type={mediatype!r}")

            if method == "Player.OnPlay":
                self._start_hdr_poll()

            if method == "Player.OnStop":
                self._clear_hdr_properties()

        except Exception as exc:
            _log(f"Exception in KodiMonitor.onNotification: {exc}", xbmc.LOGERROR)

    def _start_hdr_poll(self) -> None:
        """Start a background thread that polls HDR properties for 30 seconds."""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_thread = threading.Thread(target=self._poll_hdr_properties, daemon=True)
        self._poll_thread.start()

    def _poll_hdr_properties(self) -> None:
        """Poll every 2 seconds for 30 seconds until DV profile is found."""
        _addon_path = xbmcaddon.Addon(_ADDON_ID).getAddonInfo("path")
        sys.path.insert(0, os.path.join(_addon_path, "resources", "lib"))

        try:
            from properties import get_HdmiHdrStatusVar, get_DoviProfileVar

            for _ in range(15):  # 15 attempts x 2 seconds = 30 seconds
                xbmc.sleep(2000)

                hdr  = get_HdmiHdrStatusVar()
                dovi = get_DoviProfileVar()

                xbmc.executebuiltin(f"SetProperty(HdmiHdrStatusVar,{hdr},Home)")
                xbmc.executebuiltin(f"SetProperty(DoviProfileVar,{dovi},Home)")

                _log(f"HDR poll: HdmiHdrStatusVar={hdr!r}  DoviProfileVar={dovi!r}", xbmc.LOGINFO)

                # Stop polling once DV profile is confirmed
                if dovi:
                    _log("DV profile found — stopping poll", xbmc.LOGINFO)
                    break

        except Exception as exc:
            _log(f"_poll_hdr_properties failed: {exc}", xbmc.LOGERROR)

    def _clear_hdr_properties(self) -> None:
        """Clear HDR properties from Window(Home) when playback stops."""
        xbmc.executebuiltin("ClearProperty(HdmiHdrStatusVar,Home)")
        xbmc.executebuiltin("ClearProperty(DoviProfileVar,Home)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _addon_path = xbmcaddon.Addon().getAddonInfo("path")
    sys.path.insert(0, os.path.join(_addon_path, "resources", "lib"))

    addon   = xbmcaddon.Addon()
    win     = xbmcgui.Window(10000)
    monitor = KodiMonitor(win=win, addon=addon)

    xbmc.log("TinyPPI: KodiMonitor started", xbmc.LOGINFO)

    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break

    del monitor
