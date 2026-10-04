# -*- coding: utf-8 -*-
"""Add-on paths without asking Kodi's add-on manager (3.2.15).

xbmcaddon.Addon() goes through Kodi's add-on manager. On Kodi 22 / Py3.14
with a damaged Addons33.db ("Can't update database Addons33 from version 0")
that call can block at boot - the service then hangs before its first log line
and never auto-patches. Everything the service needs at import time is built
from special:// paths instead.
"""
import os
import re

import xbmcvfs

ADDON_ID = 'plugin.program.abukarimtools'
ADDON_PATH = xbmcvfs.translatePath('special://home/addons/%s/' % ADDON_ID)
PROFILE = xbmcvfs.translatePath('special://profile/addon_data/%s/' % ADDON_ID)
ICON = os.path.join(ADDON_PATH, 'icon.png')

_version = None


def version(fresh=False):
    global _version
    if _version is None or fresh:
        try:
            with open(os.path.join(ADDON_PATH, 'addon.xml'), 'r', encoding='utf-8') as f:
                m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', f.read())
            _version = m.group(1) if m else '?'
        except OSError:
            _version = '?'
    return _version
