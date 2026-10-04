# -*- coding: utf-8 -*-
"""
font_fallback.py - make Arabic readable in EVERY skin, including plugin
directory listings this add-on cannot otherwise control.

The problem
-----------
The ABUKARIM TOOLS main menu and the ABUKARIM wizard menu are ordinary Kodi
plugin directory listings (xbmcgui.ListItem + addDirectoryItem). Their font is
chosen entirely by the ACTIVE SKIN, not by us - an add-on has no way to set a
font on a directory listing. When the active skin's font has no Arabic glyphs
(or during a fresh install before the skin's Arabic fonts are in place), Kodi
substitutes its GLOBAL FALLBACK font, which is a glyph-less arial.ttf, and every
Arabic label renders as tofu (the empty boxes seen on first install).

The fix
-------
Kodi's global fallback lives at special://home/media/fonts/arial.ttf (i.e.
.kodi/media/fonts/arial.ttf). It is what EVERY skin drops to when its own font
lacks a glyph. If that file is Arabic-capable, the tofu disappears everywhere at
once - both our menus, the wizard's menus, and any other skin surface - with no
per-skin work and nothing that a skin update can wipe.

We already ship an Arabic-capable TTF (resources/fonts/Noto-Regular.ttf, verified
to cover every Arabic character used in both add-ons' strings), so we simply copy
it into the fallback location on boot. Kodi loads media/fonts/arial.ttf once at
start, so a freshly written file takes effect on the NEXT Kodi start; we compare
by size first so we only write when it actually differs (no needless churn, and
the "changed -> a restart will apply it" signal is meaningful).

This is best-effort and fully fenced: it must never raise into the caller
(service boot chores must still reach the first-run trigger).
"""

import os
import shutil

import xbmc
import xbmcaddon
import xbmcvfs

ADDON     = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_ID  = ADDON.getAddonInfo('id')

# The Arabic-capable font we ship. Noto-Regular.ttf is the monadit/Figtree copy
# used for the TinyPPI overlay; it carries every Arabic char used in the UI.
_SRC_REL  = 'resources/fonts/Noto-Regular.ttf'

# Kodi's global fallback font. media/fonts/arial.ttf is what skins fall back to
# for any glyph their own font is missing.
_DEST_VFS = 'special://home/media/fonts/arial.ttf'


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools FallbackFont] %s' % msg, level)


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def install(force=False):
    """Copy the Arabic-capable font over Kodi's global fallback arial.ttf.

    Returns True if the fallback file was (re)written this call, False if it
    was already correct or nothing could be done. Never raises.
    """
    try:
        src = xbmcvfs.translatePath(
            'special://home/addons/%s/%s' % (ADDON_ID, _SRC_REL))
        if not os.path.exists(src):
            _log('Source font missing (%s) - cannot install fallback.' % src,
                 xbmc.LOGWARNING)
            return False

        dest_dir = xbmcvfs.translatePath('special://home/media/fonts/')
        dest     = xbmcvfs.translatePath(_DEST_VFS)

        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as e:
            _log('Could not create %s: %s' % (dest_dir, e), xbmc.LOGWARNING)
            return False

        # Only write when the destination differs, so we don't rewrite the
        # fallback on every boot. Size is enough here: the source is a fixed
        # shipped file, so an identical size means it is already our font.
        if not force and _size(dest) == _size(src):
            _log('Fallback arial.ttf already Arabic-capable - no change.')
            return False

        shutil.copyfile(src, dest)
        _log('Installed Arabic-capable fallback font -> %s (takes effect on '
             'next Kodi start).' % dest)
        return True
    except Exception as e:  # never propagate into boot chores
        _log('Fallback font install failed (ignored): %s' % e,
             xbmc.LOGERROR)
        return False
