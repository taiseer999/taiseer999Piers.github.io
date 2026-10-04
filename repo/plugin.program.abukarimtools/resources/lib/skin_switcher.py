# -*- coding: utf-8 -*-
"""
Skin Switcher – switch between installed skins.
Adapted from script.skinswitcher.

Behaviour: pick a skin from the list, the switcher closes, the chosen skin
applies with no visible prompts. Kodi's own "Keep this change?" revert dialog
is what causes the flicker/loop; we avoid it by confirming any add-on-enable
prompt ourselves and dismissing the revert dialog immediately if it appears.
"""

import os
import glob
import json
import re

import xbmc
import xbmcgui

from resources.lib.i18n import T
import xbmcaddon
import xbmcvfs

HOME   = xbmcvfs.translatePath('special://home/')
ADDONS = os.path.join(HOME, 'addons')
TITLE  = 'ABUKARIM – Skin Switcher'


def _log(msg):
    xbmc.log('[AbukarimTools SkinSwitcher] %s' % msg, xbmc.LOGINFO)


def _jsonrpc(method, params=None):
    payload = {'jsonrpc': '2.0', 'method': method, 'id': 1}
    if params is not None:
        payload['params'] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception as exc:
        _log('jsonrpc %s failed: %r' % (method, exc))
        return {}


def _curr_skin_id():
    return xbmc.getSkinDir()



def _is_enabled(addon_id):
    r = _jsonrpc('Addons.GetAddonDetails',
                 {'addonid': addon_id, 'properties': ['enabled']})
    try:
        return bool(r['result']['addon']['enabled'])
    except Exception:
        return False


def _enable(addon_id):
    _jsonrpc('Addons.SetAddonEnabled', {'addonid': addon_id, 'enabled': True})


def _dismiss_confirm_dialogs(deadline_ms):
    """
    While waiting for the skin to load, silently handle the two dialogs Kodi
    can throw up:
      * "Add-on needs to be enabled" yes/no  -> Yes = control 11
      * "Keep this skin change?" revert timer -> Yes = control 11 (No is the
        default focus, so a bare Select would revert; we click 11 explicitly)
    """
    waited = 0
    while waited < deadline_ms:
        active = (xbmc.getCondVisibility('Window.IsActive(yesnodialog)')
                  or xbmc.getCondVisibility('Window.IsActive(10100)'))
        if active:
            xbmc.executebuiltin('SendClick(yesnodialog, 11)')   # 11 = Yes
            xbmc.sleep(60)
            xbmc.executebuiltin('SendClick(11)')                # backup, same id
            xbmc.sleep(200)
        xbmc.sleep(80)
        waited += 80



def _close_to_home(settle=True):
    """
    After the skin has changed, leave the user on the NEW skin's Home window
    instead of reopening AbukarimTools. Close every dialog/plugin container
    silently so nothing of the switcher is left on screen.

    settle=True waits for a freshly loaded skin to settle before the final
    close; pass settle=False on cancel/no-change where no skin reload happened.
    """
    try:
        xbmc.executebuiltin('Dialog.Close(all, true)')
    except Exception:
        pass
    # Let a freshly loaded skin settle its Home window first, then make sure we
    # are actually sitting on Home (not an empty plugin container) before the
    # switcher script exits.
    if settle:
        xbmc.sleep(1200)
    xbmc.executebuiltin('ActivateWindow(Home)')


_SKIN_BUSY_PROP = 'abukarimtools.skinop.busy'


def skin_op_busy():
    """True if a skin install/switch is already in progress.

    Both the skin installer and the skin switcher change lookandfeel.skin,
    which reloads every window. If one runs while the other has a custom modal
    dialog open, the reload tears that window down and re-creates it under a
    new id — the script's handle goes stale and the dialog freezes. The two
    flows serialise on this single Home-window property so they can never
    overlap. The property is in-memory, so a Kodi restart always clears it (no
    stale-lock risk across restarts).
    """
    try:
        return xbmcgui.Window(10000).getProperty(_SKIN_BUSY_PROP) == '1'
    except Exception:
        return False


def set_skin_op_busy(on):
    try:
        win = xbmcgui.Window(10000)
        if on:
            win.setProperty(_SKIN_BUSY_PROP, '1')
        else:
            win.clearProperty(_SKIN_BUSY_PROP)
    except Exception:
        pass


def _swap_skin(addon_id):
    # Make sure the target skin is enabled first — a disabled skin is what
    # triggers the extra "enable this add-on?" prompt.
    if not _is_enabled(addon_id):
        _enable(addon_id)
        xbmc.sleep(300)

    current = _curr_skin_id()
    if current == addon_id:
        return

    # Set the skin via JSON-RPC. This does not block, and Kodi begins loading
    # the new skin immediately; any confirm/revert dialog is answered below.
    _jsonrpc('Settings.SetSettingValue',
             {'setting': 'lookandfeel.skin', 'value': addon_id})

    # Answer prompts and wait for the skin to actually change over.
    waited = 0
    while waited < 12000:
        _dismiss_confirm_dialogs(240)
        if xbmc.getSkinDir() == addon_id:
            break
        waited += 240

    # Belt-and-braces: if the skin loaded but a revert timer is still counting
    # down, confirm once more so it can't flip back.
    _dismiss_confirm_dialogs(500)
    _log('active skin now: %s (wanted %s)' % (xbmc.getSkinDir(), addon_id))


def run():
    if skin_op_busy():
        _log('skin operation already in progress — refusing skin switch.')
        xbmc.executebuiltin('Dialog.Close(busydialog)')
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        return
    set_skin_op_busy(True)
    try:
        _run_impl()
    finally:
        set_skin_op_busy(False)


def _run_impl():
    xbmc.executebuiltin('Dialog.Close(busydialog)')
    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')

    skin_folders = glob.glob(os.path.join(ADDONS, 'skin*'))
    names     = []
    addon_ids = []

    for folder in sorted(skin_folders):
        foldername = os.path.basename(folder.rstrip(os.sep))
        xml_path   = os.path.join(folder, 'addon.xml')
        if not os.path.exists(xml_path):
            continue
        try:
            with open(xml_path, encoding='utf-8') as f:
                content = f.read()
            m = re.search(r'<addon[^>]+id=["\']([^"\']+)["\']', content)
            addon_id = m.group(1) if m else foldername
            addon = xbmcaddon.Addon(id=addon_id)
            names.append(addon.getAddonInfo('name'))
            addon_ids.append(addon_id)
        except Exception:
            pass

    if not names:
        xbmcgui.Dialog().ok(TITLE, T(30150))
        return

    current_id = _curr_skin_id()

    # Mark the active skin in the list, and don't offer it as a switch target.
    choices    = []
    selectable = []
    for name, aid in zip(names, addon_ids):
        if aid == current_id:
            choices.append('%s  [active]' % name)
        else:
            choices.append(name)
        selectable.append(aid)

    idx = xbmcgui.Dialog().select(T(30151), choices)
    if idx < 0:
        _close_to_home(settle=False)
        return

    chosen_id = selectable[idx]
    if chosen_id == current_id:
        _close_to_home(settle=False)
        return

    # Stop any playback and let it fully tear down before swapping skins.
    if xbmc.Player().isPlaying():
        xbmc.Player().stop()
        waited = 0
        while xbmc.Player().isPlaying() and waited < 5000:
            xbmc.sleep(200)
            waited += 200
        xbmc.sleep(500)

    _swap_skin(chosen_id)

    # Skin is now active and confirmed. Leave the user on the new skin's Home
    # screen silently instead of reopening the AbukarimTools menu.
    _close_to_home()
