# -*- coding: utf-8 -*-
"""
af3_trailers_toggle.py  -  ABUKARIM TOOLS

Toggles menu entry for the Arctic Fuse 3 auto-trailers: on/off, sound,
how long the cursor rests on a title before its trailer starts, and the
trailer quality. The settings live in addon_data (af3_trailers.json) and the
engine inside the ABUKARIM TOOLS service picks a change up within a second -
no restart. Turning it on also applies the small AF3 skin patch (Back key and
now-playing footer ignore a trailer) and reloads the skin if it changed.
"""
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T
from resources.lib.af3_trailers import config

ADDON = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_NAME = 'ABUKARIM TOOLS'
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ICON = os.path.join(ADDON_PATH, 'resources', 'icons', 'af3_trailers.png')
SKIN_ID = 'skin.arctic.fuse.3'
ENGINE_PROP = 'abukarimtools.trailers.engine'

DIALOG = xbmcgui.Dialog()


def _log(msg):
    xbmc.log('[AbukarimTools TrailersToggle] %s' % msg, xbmc.LOGINFO)


def _on_off(value):
    return T(30436) if value else T(30437)


def _skin_installed():
    return bool(xbmc.getCondVisibility('System.HasAddon(%s)' % SKIN_ID))


def _ensure_engine():
    """Start the trailer engine now unless it already runs (service or Home)."""
    try:
        home = xbmcgui.Window(10000)
        if home.getProperty(ENGINE_PROP):
            return
        _log('trailer engine not running - starting it')
        xbmc.executebuiltin('RunScript(%s,toggle)'
                            % os.path.join(ADDON_PATH.rstrip('/\\'), 'trailers.py'))
    except Exception as exc:
        _log('could not start the trailer engine: %s' % exc)


def _apply_skin_patch():
    """Apply the AF3 patch entries now (idempotent) and reload the skin if they wrote."""
    try:
        from resources.lib import patcher
        _ok, failed, changed, _res = patcher.apply_set(addon_ids=[SKIN_ID])
        _log('skin patch: %d written, %d failed' % (changed, failed))
        # 3.1.19: the skin is reloaded only after the settings list closes
        # (a reload under the open list re-ran this entry in a loop)
    except Exception as exc:
        _log('skin patch failed: %s' % exc)


def _pick(heading, values, current, fmt):
    labels = [fmt(v) for v in values]
    pre = values.index(current) if current in values else 0
    choice = DIALOG.select(heading, labels, preselect=pre)
    return values[choice] if choice >= 0 else current


def _set_enabled(cfg, on):
    cfg['enabled'] = bool(on)
    config.save(cfg)
    _log('auto trailers turned %s' % ('ON' if on else 'off'))
    if on:
        _ensure_engine()
        _apply_skin_patch()
        msg = T(30438)
        if xbmc.getSkinDir() != SKIN_ID:
            msg = T(30441)
        elif xbmc.getCondVisibility('Skin.HasSetting(Background.DisableVideo)'):
            DIALOG.ok(ADDON_NAME, T(30442))
    else:
        msg = T(30439)
    DIALOG.notification(ADDON_NAME, msg, ICON, 3000)


MENU_PROP = 'abukarimtools.trailers.menu'


def run():
    """Toggles entry. One copy at a time; the skin reload waits until it closes."""
    home = xbmcgui.Window(10000)
    if home.getProperty(MENU_PROP):
        _log('settings already open - this copy exits')
        return
    home.setProperty(MENU_PROP, '1')
    try:
        _run()
    finally:
        home.clearProperty(MENU_PROP)
        try:
            from resources.lib import patcher
            patcher.reload_skin_if_pending()
        except Exception:
            pass
        xbmc.executebuiltin('Container.Refresh')


def _run():
    if not _skin_installed():
        DIALOG.ok(ADDON_NAME, T(30440))
        return
    # picking the entry while it is off switches it ON at once; the settings
    # list that follows can turn it off or tune it
    cfg = config.load()
    if not cfg['enabled']:
        _set_enabled(cfg, True)
    else:
        _ensure_engine()
    pos = 0
    quick = 0
    while True:
        cfg = config.load()
        items = [
            T(30431) % _on_off(cfg['enabled']),
            T(30432) % _on_off(cfg['sound']),
            T(30433) % cfg['delay'],
            T(30434) % ('%dp' % cfg['quality']),
        ]
        shown = time.monotonic()
        choice = DIALOG.select(T(30430), items, preselect=pos)
        if choice < 0:
            break
        # a list that answers without ever showing (Kodi busy reloading the
        # skin) must never drive the loop: stop after two instant answers
        if time.monotonic() - shown < 0.25:
            quick += 1          # never acted on: nobody picks a line that fast
            if quick >= 2:
                _log('settings list did not show - closing it')
                break
            xbmc.sleep(300)
            continue
        quick = 0
        pos = choice
        if choice == 0:
            _set_enabled(cfg, not cfg['enabled'])
        elif choice == 1:
            cfg['sound'] = not cfg['sound']
            config.save(cfg)
        elif choice == 2:
            cfg['delay'] = _pick(T(30435), list(config.DELAYS), cfg['delay'],
                                 lambda v: T(30443) % v)
            config.save(cfg)
        elif choice == 3:
            cfg['quality'] = _pick(T(30444), list(config.QUALITIES), cfg['quality'],
                                   lambda v: '%dp' % v)
            config.save(cfg)
