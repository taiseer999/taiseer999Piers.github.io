# -*- coding: utf-8 -*-
"""
set_language.py - force Kodi's UI language to English (en_gb).

Why this exists
---------------
ABUKARIM TOOLS renders its own interface in English (see i18n.T), but the
buttons, breadcrumbs and counters inside Kodi's *core* dialogs - the file
browser's OK/Cancel, the "1/1 - Objects N" line, Estuary's window title - are
drawn by Kodi itself using whichever UI language the box is set to. On an
Arabic-set device those core strings render as tofu because the active skin's
font has no Arabic glyphs (a limitation that cannot be fixed from an add-on).

Setting Kodi's UI language to English makes every one of those core strings
render in Latin text, so the whole interface is readable and consistent with
the add-on's own English strings.

This is best-effort and fully fenced: it must never raise into the caller.
It only acts when the language actually differs, so it is a no-op on boxes that
are already English, and it never fights a user who has deliberately chosen a
non-Arabic language - it only switches *away from Arabic*.
"""

import json

import xbmc

# Kodi's UI-language setting id and the English (UK) language resource that
# ships with every Kodi install.
_SETTING = 'locale.language'
_ENGLISH = 'resource.language.en_gb'
_ARABIC  = 'resource.language.ar_sa'

# Only languages we replace. We switch away from Arabic specifically rather
# than clobbering any non-English choice, so a user who set, say, French is
# left alone - only the tofu-causing Arabic case is corrected.
_REPLACE = ('resource.language.ar_sa', 'resource.language.ar_')


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools SetLanguage] %s' % msg, level)


def _jsonrpc(method, params=None):
    payload = {'jsonrpc': '2.0', 'method': method, 'id': 1}
    if params is not None:
        payload['params'] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception as exc:
        _log('jsonrpc %s failed: %r' % (method, exc), xbmc.LOGWARNING)
        return {}


def _current_language():
    resp = _jsonrpc('Settings.GetSettingValue', {'setting': _SETTING})
    try:
        return resp['result']['value']
    except (KeyError, TypeError):
        return ''


def _flush():
    """Persist settings to guisettings.xml and give the write time to land.

    Settings.SetSettingValue updates the value in memory; Kodi flushes it to
    disk asynchronously. If a hard restart follows quickly - the interactive
    Origin Fix uses RestartApp, and on CoreELEC 'systemctl restart kodi' is a
    hard kill with no clean-shutdown flush - the language change can be lost.
    We force a save and wait briefly so the new value is on disk before any
    such restart. Best-effort: never raises.
    """
    try:
        # Ask Kodi to write settings now. Not all builds expose SaveSettings as
        # a builtin; if it is a no-op the sleep below still covers the normal
        # async flush window.
        xbmc.executebuiltin('SaveSettings')
    except Exception as exc:
        _log('SaveSettings builtin failed (ignored): %r' % exc,
             xbmc.LOGWARNING)
    # Give the write time to reach disk before the caller restarts Kodi.
    try:
        xbmc.sleep(1500)
    except Exception:
        pass


def force_english(only_if_arabic=True):
    """Set Kodi's UI language to English (en_gb).

    only_if_arabic=True (default): only switch when the box is currently on an
    Arabic language resource, leaving any other non-English choice untouched.
    only_if_arabic=False: switch to English from whatever is set, unless it is
    already English.

    Returns True if the language was changed this call, False otherwise.
    Never raises.
    """
    try:
        current = _current_language()
        if current == _ENGLISH:
            _log('UI language already English - no change.')
            return False

        if only_if_arabic and not any(
                current.startswith(p) for p in _REPLACE):
            _log('UI language is %r (not Arabic) - leaving it unchanged.'
                 % current)
            return False

        resp = _jsonrpc('Settings.SetSettingValue',
                        {'setting': _SETTING, 'value': _ENGLISH})
        if resp.get('result') is True:
            _flush()
            _log('UI language switched to English (was %r).' % current)
            return True
        _log('SetSettingValue did not confirm the change (resp=%r). The '
             'English language resource may not be installed.' % resp,
             xbmc.LOGWARNING)
        return False
    except Exception as exc:  # never propagate into boot / first-run chores
        _log('force_english failed (ignored): %r' % exc, xbmc.LOGERROR)
        return False


def force_arabic():
    """Set Kodi's UI language to Arabic (ar_sa).

    Used at the very end of the first-run sequence to hand the box back to
    Arabic once setup - which is shown in English so its dialogs are readable -
    has finished. No-op if already Arabic. Never raises.

    Note: whether Arabic then renders cleanly depends on the ACTIVE SKIN having
    an Arabic-capable font. Arctic Fuse 3 (installed during first-run) ships
    Arabic fonts; the stock Estuary skin does not, so core dialogs would show
    tofu again under Estuary. This function only sets the language - it makes
    no claim about glyph coverage.
    """
    try:
        current = _current_language()
        if current == _ARABIC:
            _log('UI language already Arabic - no change.')
            return False

        resp = _jsonrpc('Settings.SetSettingValue',
                        {'setting': _SETTING, 'value': _ARABIC})
        if resp.get('result') is True:
            _flush()
            _log('UI language switched to Arabic (was %r).' % current)
            return True
        _log('SetSettingValue did not confirm the switch to Arabic '
             '(resp=%r). The Arabic language resource may not be installed.'
             % resp, xbmc.LOGWARNING)
        return False
    except Exception as exc:
        _log('force_arabic failed (ignored): %r' % exc, xbmc.LOGERROR)
        return False
