# -*- coding: utf-8 -*-
"""
dialog_guard.py - Dialog().select / multiselect that survive being swallowed.

Field log 2026-10-03 09:05-09:07 (first-run on 3.2.0): right after the
Add-on Portal finished installing (Kodi rescans add-ons, Seren/Red Light start
their services) the preset list returned -1 after ~1 s and the patch
checklist returned None after ~50 ms - nobody had pressed anything. The
dialog's heading had been drawn but its list never refreshed. Same family as
the swallowed-dialog cases handled in the portal / repo picker (3.1.0.19) and
the trailers menu (3.1.19).

A "cancel" that arrives faster than a human can answer is treated as
swallowed: wait for the screen to settle, then open the dialog again (max 3).
"""

import time

import xbmc
import xbmcgui

MIN_HUMAN_S = 1.0


def _log(msg):
    xbmc.log('[AbukarimTools DialogGuard] %s' % msg, xbmc.LOGINFO)


def _settle(seconds=1.5):
    mon = xbmc.Monitor()
    waited = 0.0
    while waited < 8 and not mon.abortRequested():
        busy = xbmc.getCondVisibility('System.HasModalDialog') or \
            xbmc.getCondVisibility('Window.IsActive(busydialog)')
        if not busy and waited >= seconds:
            return
        xbmc.sleep(250)
        waited += 0.25


def _guarded(kind, call, cancelled):
    result = None
    for attempt in range(3):
        started = time.time()
        result = call()
        if not cancelled(result) or time.time() - started >= MIN_HUMAN_S:
            return result
        _log('%s answered in %.2fs without input (attempt %d) - reopening'
             % (kind, time.time() - started, attempt + 1))
        _settle()
    return result


def select(heading, items, **kwargs):
    return _guarded('select', lambda: xbmcgui.Dialog().select(heading, items, **kwargs),
                    lambda r: r is None or r < 0)


def multiselect(heading, items, **kwargs):
    return _guarded('multiselect',
                    lambda: xbmcgui.Dialog().multiselect(heading, items, **kwargs),
                    lambda r: r is None)
