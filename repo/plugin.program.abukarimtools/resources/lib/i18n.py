# -*- coding: utf-8 -*-
"""
Translation helper for ABUKARIM TOOLS.

T(string_id) returns the localized string for the current Kodi UI language
via Addon.getLocalizedString, which reads the matching resource.language
strings.po. If Kodi returns an empty string (id missing from the active .po),
we fall back to the English text baked into strings_map so nothing ever shows
blank.

Usage:
    from resources.lib.i18n import T
    label = T(30005)                 # "Apply Patches" / "\u062a\u0637\u0628\u064a\u0642 \u0627\u0644\u062a\u0631\u0642\u064a\u0639\u0627\u062a"
    msg   = T(30122) % skin_title    # format args applied by the caller
"""

import xbmcaddon

_ADDON = None   # 3.2.15: created on first use, never at import


def _addon():
    global _ADDON
    if _ADDON is None:
        _ADDON = xbmcaddon.Addon('plugin.program.abukarimtools')
    return _ADDON


def T(string_id):
    """Return the localized string for the given id (int).

    Reads via getLocalizedString so the add-on follows Kodi's UI language:
    Arabic .po when the box is Arabic, English otherwise. Falls back to the
    English source of truth in strings_map if Kodi returns nothing for the id.
    """
    try:
        s = _addon().getLocalizedString(int(string_id))
        if s:
            return s
    except Exception:
        pass
    # fall back to the English source of truth
    try:
        from resources.lib.strings_map import STRINGS
        pair = STRINGS.get(int(string_id))
        if pair:
            return pair[0]
    except Exception:
        pass
    return ''
