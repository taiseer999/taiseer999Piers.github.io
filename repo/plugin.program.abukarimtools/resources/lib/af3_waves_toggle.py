# -*- coding: utf-8 -*-
"""
af3_waves_toggle.py - ABUKARIM TOOLS (3.2.10)

Toggles entry "AF3: Waves While Loading". Arctic Fuse 3 plays the
resource.images.arctic.waves animation full-screen behind Kodi's busy dialog -
most visibly in the seconds after a movie's player is chosen. This flips the
AF3 skin bool abk.nobusywaves; the always-on AF3 patch in patcher.py
(Includes_Background.xml) makes the loader hide while it is set. Skin settings
are evaluated live, so the change shows on the very next busy dialog.
"""
import xbmc
import xbmcgui

from resources.lib.i18n import T

SKIN_ID = 'skin.arctic.fuse.3'
SETTING = 'abk.nobusywaves'
TITLE = 'ABUKARIM TOOLS'


def _log(msg):
    xbmc.log('[AbukarimTools WavesToggle] %s' % msg, xbmc.LOGINFO)


def waves_on():
    """True while the waves are shown (the default)."""
    return not xbmc.getCondVisibility('Skin.HasSetting(%s)' % SETTING)


def _ensure_patch():
    """Apply the AF3 patch now; reload the skin only if the XML changed."""
    try:
        from resources.lib import patcher
        _ok, _failed, changed, _r = patcher.apply_set(addon_ids=[SKIN_ID])
        return changed > 0
    except Exception as exc:
        _log('skin patch failed: %s' % exc)
        return False


def run():
    if not xbmc.getCondVisibility('System.HasAddon(%s)' % SKIN_ID):
        xbmcgui.Dialog().ok(TITLE, T(30440))          # AF3 is not installed
        return
    if xbmc.getSkinDir() != SKIN_ID:
        xbmcgui.Dialog().ok(TITLE, T(30602))          # switch to AF3 first
        return
    reload_needed = _ensure_patch()
    if waves_on():
        xbmc.executebuiltin('Skin.SetBool(%s)' % SETTING)
        msg = T(30601)
        _log('waves while loading: OFF')
    else:
        xbmc.executebuiltin('Skin.Reset(%s)' % SETTING)
        msg = T(30600)
        _log('waves while loading: ON')
    xbmcgui.Dialog().notification(TITLE, msg, xbmcgui.NOTIFICATION_INFO, 3000)
    if reload_needed:
        xbmc.sleep(300)
        xbmc.executebuiltin('ReloadSkin()')
    else:
        xbmc.executebuiltin('Container.Refresh')
