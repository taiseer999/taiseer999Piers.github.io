# -*- coding: utf-8 -*-
"""
wizard_runner.py  -  hand-off to the ABUKARIM Wizard (plugin.program.ABUKARIMwizard).

Up to 3.1.2 this module ran an embedded copy of OpenWizard 2.0.8.1 in-process
(Addon shim + import finder + addDirectoryItem patch). Since ABUKARIM Wizard
3.9.20 ported the OpenWizard maintenance feature, the embedded copy was removed
and every former OpenWizard entry point now calls the installed wizard by its
own plugin URL, so the wizard runs with its own add-on context and settings.

Wizard modes used (resources/lib/modules/plugin.py in the wizard):
    5    Maintenance menu (Cleaning / Addon / Logging / Misc / Tweaks)
    210  Total Clean Up (archive, cache, function cache, packages, thumbnails)
    214  Clear Old Thumbnails
"""

import json

import xbmc
import xbmcgui

WIZARD_ID  = 'plugin.program.ABUKARIMwizard'
WIZARD_URL = 'plugin://%s/' % WIZARD_ID

MODE_MAINTENANCE = 5
MODE_TOTAL_CLEAN = 210
MODE_OLD_THUMBS  = 214


def wizard_installed():
    """True when the wizard is installed AND enabled.

    Not System.HasAddon(): Kodi lowercases condition strings, so the
    mixed-case id 'plugin.program.ABUKARIMwizard' never matches there and the
    wizard always looked missing (3.1.3). JSON-RPC keeps the id's case, and
    unlike xbmcaddon.Addon() it logs nothing when the add-on is absent.
    """
    try:
        req = {'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddonDetails',
               'params': {'addonid': WIZARD_ID, 'properties': ['enabled']}}
        res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
        addon = (res.get('result') or {}).get('addon')
        if addon is not None:
            return bool(addon.get('enabled', True))
        if 'error' in res:
            return False
    except Exception:
        pass
    try:                                    # fallback: raises if missing/disabled
        import xbmcaddon
        xbmcaddon.Addon(WIZARD_ID)
        return True
    except Exception:
        return False


def wizard_url(mode=None):
    return WIZARD_URL if mode is None else '%s?mode=%d' % (WIZARD_URL, mode)


def _ensure_wizard():
    """True when the wizard is installed and enabled. Otherwise tell the user
    and offer Kodi's own InstallAddon (works when a repo that carries the
    wizard is installed)."""
    if wizard_installed():
        return True
    from resources.lib.i18n import T
    if xbmcgui.Dialog().yesno('ABUKARIM TOOLS', T(30022)):
        xbmc.executebuiltin('InstallAddon(%s)' % WIZARD_ID)
    return False


def open_wizard(mode=MODE_MAINTENANCE):
    """Open a wizard directory (default: its Maintenance menu) in Programs."""
    if _ensure_wizard():
        xbmc.executebuiltin('ActivateWindow(Programs,"%s",return)' % wizard_url(mode))


def _run_action(mode):
    if _ensure_wizard():
        xbmc.executebuiltin('RunPlugin(%s)' % wizard_url(mode))


def run_total_clean():
    """Wizard 'Total Clean Up' - shows its own confirm dialog."""
    _run_action(MODE_TOTAL_CLEAN)


def run_old_thumbs():
    """Wizard 'Clear Old Thumbnails' - textures unused for 7+ days."""
    _run_action(MODE_OLD_THUMBS)
