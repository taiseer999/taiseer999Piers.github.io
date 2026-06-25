# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013-2021 Skin Shortcuts (script.skinshortcuts)
    This file is part of script.skinshortcuts
    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only.txt for more information.

    Kodi 22 (Piers) entry point.

    Kodi removed the ability to invoke addons declared with the
    xbmc.python.library extension point via RunScript(). Scripts must now use
    the xbmc.python.script extension point. This root-level default.py is that
    entry point; it adds resources/lib to sys.path and runs the original
    script logic that previously lived in resources/lib/entry_point.py.
"""

import os
import sys

import xbmcaddon

# Ensure resources/lib is importable (the 'skinshorcuts' package lives there).
ADDON_PATH = xbmcaddon.Addon(id='script.skinshortcuts').getAddonInfo('path')
LIB_PATH = os.path.join(ADDON_PATH, 'resources', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

# pylint: disable=wrong-import-position
from skinshorcuts import skinshortcuts
from skinshorcuts.common import log
from skinshorcuts.constants import ADDON_VERSION

if __name__ == '__main__':
    log('script version %s started' % ADDON_VERSION)
    script = skinshortcuts.Script()
    script.route()
    log('script stopped')
