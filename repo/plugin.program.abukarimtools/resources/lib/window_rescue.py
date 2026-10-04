# -*- coding: utf-8 -*-
"""
window_rescue.py - bring Kodi back when a skin reload leaves no window open.

3.2.13: updating the ACTIVE skin (seen with Arctic Fuse 3 5.10.25 -> 5.10.26 on
Kodi 22) makes Kodi unload the skin before extracting the update, then
ReloadSkin. ReloadSkin remembers "the window that was open" - but after the
first unload there is none (WINDOW_INVALID), so the new skin loads and nothing
is activated: black screen, no input, looks frozen. kodi.log then shows only
"EXCEPTION: Window id does not exist" ~15x a second from TMDbHelper's monitor
(it asks for Window(getCurrentWindowId()) = 9999).

The GUI thread is fine, it just has no window. This thread notices an invalid
current window that lasts a few seconds and opens Home.
"""

import threading
import time

import xbmc
import xbmcgui

WINDOW_INVALID = 9999
GRACE_S = 4          # boot / normal reloads pass through 9999 for a moment
COOLDOWN_S = 15


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools WindowRescue] %s' % msg, level)


def _loop(monitor):
    bad_since = None
    last_fix = None
    # let Kodi finish its own startup before judging anything
    if monitor.waitForAbort(20):
        return
    while not monitor.abortRequested():
        try:
            wid = xbmcgui.getCurrentWindowId()
        except Exception:
            wid = None
        now = time.monotonic()
        if wid == WINDOW_INVALID:
            if bad_since is None:
                bad_since = now
            elif now - bad_since >= GRACE_S and (last_fix is None or now - last_fix >= COOLDOWN_S):
                _log('no active window for %ds (skin reload after an update?) '
                     '- opening Home' % int(now - bad_since), xbmc.LOGWARNING)
                xbmc.executebuiltin('Dialog.Close(all,true)')
                xbmc.executebuiltin('ActivateWindow(Home)')
                last_fix = now
        else:
            if bad_since is not None and last_fix is not None and now - last_fix < COOLDOWN_S:
                _log('recovered (window %s)' % wid)
            bad_since = None
        if monitor.waitForAbort(1):
            break


def start(monitor):
    t = threading.Thread(target=_loop, args=(monitor,), name='abk-window-rescue')
    t.daemon = True
    t.start()
    return t
