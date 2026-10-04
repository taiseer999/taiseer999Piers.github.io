# -*- coding: utf-8 -*-
"""
tab_toggle.py  –  ABUKARIM TOOLS

Shared engine for enabling/disabling Arctic Fuse 3 home-switcher tabs
(DPlex = slot 1104, Korean Media = slot 1103, ...).

Each tab bundles two full settings.xml snapshots:

    resources/data/<key>/settings_on.xml
    resources/data/<key>/settings_off.xml

Instead of blindly copying the whole snapshot over the live file (which
would reset every OTHER tab to whatever state was baked into the
snapshot), the engine does a SLOT-SCOPED MERGE:

    * every <setting id="homeswitcher.<slot>.*"> line (case-insensitive)
      from the chosen snapshot replaces its counterpart in the live
      userdata/addon_data/skin.arctic.fuse.3/settings.xml
    * slot lines missing from the live file are inserted
    * everything else in the live file is left untouched

If the live file does not exist yet, the full snapshot is copied as a
fallback. When AF3 is the active skin, the in-memory toggle is synced
via Skin.SetString / Skin.Reset so Kodi's skin-settings flush on
shutdown writes the same value instead of reverting it. Finally Kodi is
force-restarted (systemctl on CoreELEC, RestartApp elsewhere).
"""

import os
import re
import shutil
import xbmc
import xbmcgui

from resources.lib.i18n import T
import xbmcvfs
import xbmcaddon

ADDON       = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_NAME  = 'ABUKARIM TOOLS'
ADDON_PATH  = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
SKIN_ID     = 'skin.arctic.fuse.3'
SKIN_DIR    = xbmcvfs.translatePath(
    'special://profile/addon_data/' + SKIN_ID)
TARGET      = os.path.join(SKIN_DIR, 'settings.xml')

DIALOG = xbmcgui.Dialog()


def _log(msg):
    xbmc.log('[AbukarimTools TabToggle] %s' % msg, xbmc.LOGINFO)


def _slot_rx(slot):
    """Match a full <setting .../> line for any homeswitcher.<slot>.* id."""
    return re.compile(
        r'<setting\s+id="(homeswitcher\.%s\.[^"]*)"[^>]*>.*?</setting>'
        % re.escape(slot),
        re.IGNORECASE)


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def _write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(data)
    os.replace(tmp, path)


def _current_state(slot):
    """True / False / None from the live toggle value."""
    try:
        data = _read(TARGET)
    except OSError:
        return None
    m = re.search(
        r'<setting\s+id="homeswitcher\.%s\.toggle"[^>]*>([^<]*)</setting>'
        % re.escape(slot), data, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().lower() == 'true'


def _merge_slot(live, snapshot, slot):
    """
    Return live text with all homeswitcher.<slot>.* settings replaced by
    (or inserted from) the snapshot. Also returns count of changes.
    """
    rx = _slot_rx(slot)
    snap_lines = {}          # lowercase id -> full line from snapshot
    for m in rx.finditer(snapshot):
        snap_lines[m.group(1).lower()] = m.group(0)

    used = set()

    def _sub(m):
        key = m.group(1).lower()
        if key in snap_lines:
            used.add(key)
            return snap_lines[key]
        return m.group(0)

    merged = rx.sub(_sub, live)

    # Insert slot lines that exist in the snapshot but not in live
    missing = [line for key, line in snap_lines.items() if key not in used]
    if missing:
        insert = '    ' + '\n    '.join(missing) + '\n</settings>'
        merged = merged.replace('</settings>', insert, 1)

    return merged, len(used) + len(missing)


def run(key, slot, label):
    """
    key   – data folder name under resources/data/  (e.g. 'dplex')
    slot  – homeswitcher slot id                    (e.g. '1104')
    label – display name                            (e.g. 'DPlex')
    """
    data_dir = os.path.join(ADDON_PATH, 'resources', 'data', key)
    src_on   = os.path.join(data_dir, 'settings_on.xml')
    src_off  = os.path.join(data_dir, 'settings_off.xml')

    for src in (src_on, src_off):
        if not os.path.isfile(src):
            DIALOG.ok(ADDON_NAME, T(30260) % src)
            return

    state = _current_state(slot)
    if state is True:
        state_lbl = T(30261)
    elif state is False:
        state_lbl = T(30262)
    else:
        state_lbl = T(30263)

    choice = DIALOG.select(
        T(30264) % (label, state_lbl),
        [T(30265) % label,
         T(30266) % label],
        preselect=1 if state is True else 0)
    if choice == -1:
        return

    enable = (choice == 0)
    src    = src_on if enable else src_off

    if not DIALOG.yesno(
            ADDON_NAME,
            T(30267)
            % (T(30268) if enable else T(30269), label),
            yeslabel=T(30270), nolabel=T(30052)):
        return

    try:
        snapshot = _read(src)
        if os.path.isfile(TARGET):
            live = _read(TARGET)
            merged, count = _merge_slot(live, snapshot, slot)
            _write_atomic(TARGET, merged)
            _log('Merged %d slot-%s setting(s) from %s into %s'
                 % (count, slot, os.path.basename(src), TARGET))
        else:
            _write_atomic(TARGET, snapshot)
            _log('No live settings.xml – copied full snapshot %s -> %s'
                 % (os.path.basename(src), TARGET))
    except OSError as e:
        _log('Write failed: %s' % e)
        DIALOG.ok(ADDON_NAME, T(30271) % (TARGET, e))
        return

    # Sync the in-memory skin setting so the shutdown flush cannot
    # revert the file during the restart.
    if xbmc.getSkinDir() == SKIN_ID:
        setting_id = 'homeswitcher.%s.toggle' % slot
        if enable:
            xbmc.executebuiltin('Skin.SetString(%s,true)' % setting_id)
        else:
            xbmc.executebuiltin('Skin.Reset(%s)' % setting_id)
        xbmc.sleep(300)

    xbmcgui.Dialog().notification(
        ADDON_NAME,
        T(30272)
        % (label, T(30273) if enable else T(30274)),
        xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.sleep(1500)
    _restart_kodi()


def _is_coreelec():
    if os.path.isdir('/etc/coreelec'):
        return True
    try:
        with open('/etc/os-release') as f:
            return any('coreelec' in line.lower() for line in f)
    except OSError:
        return False


def _restart_kodi():
    # 3.2.16: one restart path for the whole add-on (wizard Force Close)
    from resources.lib import origin_fix
    origin_fix.force_restart('tab toggle')
