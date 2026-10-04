# -*- coding: utf-8 -*-
"""
addons33_rebuild.py – ABUKARIM TOOLS

Guided rebuild of Kodi's add-on database (Addons33.db).

Why this exists
---------------
On this build Addons33.db keeps coming up at boot as
    "Can't update database Addons33 from version 0 - it's too old"
A corrupt/too-old add-on DB at boot can stop Kodi registering and auto-starting
services — including this add-on's own xbmc.service, which is where the
background auto-patch watchdog lives. When the service never starts, patches
only re-apply when ABUKARIM TOOLS is opened by hand (the menu self-heal), i.e.
"no autopatching".

Deleting the corrupt DB lets Kodi build a clean one. The catch the user flagged:
a fresh rebuild can leave add-ons disabled until they are re-enabled. So this
module automates the whole cycle rather than leaving the box half-configured:

    Phase 1  (user taps "Rebuild Add-on Database"):
        confirm  ->  delete Addons33.db (+ -wal/-shm)  ->  mark step=2  ->  reboot

    Phase 2  (next boot: Kodi has already rebuilt a fresh Addons33.db):
        continue_if_pending() runs from the service AND, as a fallback, when the
        menu is opened  ->  enable every installed add-on (JSON-RPC)  ->  clear
        the marker  ->  reboot once more so the freshly-registered services
        (this add-on's watchdog included) start clean.

Worst case: if the rebuild leaves THIS add-on disabled too, neither its service
nor its menu can run, so phase 2 cannot self-continue. The user then only has to
re-enable ABUKARIM TOOLS once (My add-ons) — opening it, or the next boot,
finishes the rest automatically. That is documented in the confirm dialog.
"""

import json
import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

ADDON       = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_NAME  = 'ABUKARIM TOOLS'
ADDON_ICON  = xbmcvfs.translatePath(ADDON.getAddonInfo('icon'))
PROFILE     = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
MARKER      = os.path.join(PROFILE, 'addons33_rebuild.step')
# Phase-1 snapshot: which add-ons were enabled and which skin was active, so
# phase 2 restores exactly that state instead of enabling everything (3.1.5).
SNAPSHOT    = os.path.join(PROFILE, 'addons33_rebuild.snapshot.json')
# {addonID: origin} from the OLD database, restored after the rebuild (3.1.8).
# Separate file, kept until the service has relinked on the following boot.
ORIGINS     = os.path.join(PROFILE, 'addons33_rebuild.origins.json')

# Never re-enabled by the no-snapshot fallback: known leftovers that must stay
# off (the standalone OpenWizard runs its own first-run/auto-update service).
NEVER_ENABLE = {
    'plugin.program.openwizard',
}

# CoreELEC one-shot: the DB must be deleted BEFORE Kodi starts, because Kodi
# holds Addons33.db open for the whole session and rewrites it during shutdown
# — deleting it from inside a running Kodi does not reliably survive the
# reboot. autostart.sh runs before Kodi, so the delete there always sticks.
#
# The block does NOT remove itself: rewriting a running shell script's own file
# mid-read is unsafe on BusyBox ash and has corrupted autostart.sh here before
# (see backup_manager._inject_autostart_restore). Instead it is guarded by a
# TRIGGER FILE and deletes only that, so a block left behind for any reason is
# inert on every later boot. The block text itself is removed from Python in
# phase 2, from a separate process, long after the script has exited.
AUTOSTART_PATH   = '/storage/.config/autostart.sh'
AUTOSTART_MARKER = '# [abukarimtools] addons33 rebuild'
TRIGGER_FILE     = '/storage/.addons33_rebuild_pending'
# 3.1.9: a fresh Addons33.db registers every non-system add-on DISABLED,
# ABUKARIM TOOLS included, so nothing of ours can run to start phase 2 and the
# user had to enable it by hand. autostart.sh now also launches this helper in
# the background: it waits for Kodi's web server and enables ABUKARIM TOOLS over
# JSON-RPC (HTTP), which starts our service -> phase 2 runs by itself.
HELPER_PATH      = '/storage/.config/abukarimtools_addons33_enable.sh'
SELF_ID          = 'plugin.program.abukarimtools'

# Set once per Kodi session so a phase-2 continuation can never run twice (e.g.
# the service starts it and the user also opens the menu before the reboot).
_CONTINUE_STARTED = False


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools Addons33] %s' % msg, level)


def _notify(message, seconds=6000):
    try:
        xbmcgui.Dialog().notification(ADDON_NAME, message, ADDON_ICON, seconds)
    except Exception:
        pass


# ---------------------------------------------------------------------------
def _is_coreelec():
    """True on a *ELEC box (reboots the OS) vs a desktop dev install (quits)."""
    if os.path.isdir('/storage/.kodi'):
        return True
    try:
        return xbmcvfs.translatePath('special://home/').startswith('/storage/')
    except Exception:
        return False


def _restart():
    """Restart the box (CoreELEC) or quit Kodi (desktop)."""
    if _is_coreelec():
        xbmc.executebuiltin('Reboot')
    else:
        from resources.lib import origin_fix
        origin_fix.force_restart('add-on database rebuild')


def _db_dir():
    return xbmcvfs.translatePath('special://database/')


def _addons33_files():
    """All Addons33.* files (the DB plus any -wal/-shm sidecars)."""
    out = []
    d = _db_dir()
    try:
        for name in os.listdir(d):
            low = name.lower()
            if low.startswith('addons33') and (
                    low.endswith('.db') or low.endswith('.db-wal')
                    or low.endswith('.db-shm')):
                out.append(os.path.join(d, name))
    except Exception as e:
        _log('Could not list database dir %s: %s' % (d, e), xbmc.LOGWARNING)
    return out


def _inject_autostart_delete():
    """Append the one-shot Addons33 delete block to autostart.sh (CoreELEC).

    Returns True when the block is in place (already present counts as
    success). The real database directory is resolved now and baked into the
    script so a non-default userdata path still works.
    """
    db_glob = os.path.join(_db_dir(), 'Addons33.db')
    block = (
        '\n%(marker)s\n'
        'if [ -f "%(trigger)s" ]; then\n'
        '    rm -f "%(db)s" "%(db)s-wal" "%(db)s-shm"\n'
        '    rm -f "%(trigger)s"\n'
        '    [ -f "%(helper)s" ] && (sh "%(helper)s" >/dev/null 2>&1 &)\n'
        'fi\n'
    ) % {'marker': AUTOSTART_MARKER, 'trigger': TRIGGER_FILE, 'db': db_glob,
         'helper': HELPER_PATH}

    try:
        with open(AUTOSTART_PATH, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except IOError:
        content = '#!/bin/sh\n'
    except Exception as e:
        _log('Could not read %s: %s' % (AUTOSTART_PATH, e), xbmc.LOGWARNING)
        return False

    try:
        if AUTOSTART_MARKER in content:
            # Replace a block left by an older version (no helper launch).
            content = _strip_block(content)
        os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
        with open(AUTOSTART_PATH, 'w', encoding='utf-8') as f:
            f.write((content.rstrip('\n') or '#!/bin/sh') + block)
        _log('Injected Addons33 delete block into %s' % AUTOSTART_PATH)
        try:
            os.chmod(AUTOSTART_PATH, 0o755)
        except Exception:
            pass
        # Arm the trigger: without it the block is a no-op.
        with open(TRIGGER_FILE, 'w', encoding='utf-8') as f:
            f.write('addons33\n')
        return True
    except Exception as e:
        _log('Could not write autostart block: %s' % e, xbmc.LOGERROR)
        return False


def _strip_block(content):
    """content with our marker..closing 'fi' block removed."""
    head, _, tail = content.partition(AUTOSTART_MARKER)
    _, _, after = tail.partition('\nfi\n')
    return head.rstrip('\n') + '\n' + after.lstrip('\n')


def _webserver_info():
    """Kodi web server settings for the helper, turning the server on if it
    is off. Returns a dict, or None when JSON-RPC over HTTP is not usable
    (the user then enables ABUKARIM TOOLS by hand, as before)."""
    def get(name):
        r = _jsonrpc('Settings.GetSettingValue', {'setting': name})
        return (r.get('result') or {}).get('value')

    info = {'was_off': False}
    if not get('services.webserver'):
        r = _jsonrpc('Settings.SetSettingValue',
                     {'setting': 'services.webserver', 'value': True})
        if r.get('result') is not True or not get('services.webserver'):
            _log('Web server is off and could not be enabled - the user will '
                 'have to enable ABUKARIM TOOLS by hand after the rebuild.',
                 xbmc.LOGWARNING)
            return None
        info['was_off'] = True
    info['port'] = int(get('services.webserverport') or 8080)
    auth = get('services.webserverauthentication')
    info['user'] = (get('services.webserverusername') or 'kodi') if auth is not False else ''
    info['password'] = (get('services.webserverpassword') or '') if auth is not False else ''
    return info


def _sh_quote(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def _write_helper(info):
    """Write the background enabler run by autostart.sh after the DB delete.

    Polls http://127.0.0.1:<port>/jsonrpc every 5 s for up to 15 min: once
    Kodi has registered ABUKARIM TOOLS (disabled) it enables it, which starts
    our service and with it phase 2. Exits as soon as it reads enabled:true.
    """
    auth = ''
    if info.get('user') or info.get('password'):
        auth = '-u %s' % _sh_quote('%s:%s' % (info.get('user', ''),
                                                info.get('password', '')))
    script = """#!/bin/sh
# [abukarimtools] addons33 rebuild - re-enable ABUKARIM TOOLS once Kodi is up.
# Written by ABUKARIM TOOLS phase 1, started by autostart.sh, removed in phase 2.
URL='http://127.0.0.1:%(port)d/jsonrpc'
HDR='Content-Type: application/json'
GET='{"jsonrpc":"2.0","id":1,"method":"Addons.GetAddonDetails","params":{"addonid":"%(id)s","properties":["enabled"]}}'
SET='{"jsonrpc":"2.0","id":1,"method":"Addons.SetAddonEnabled","params":{"addonid":"%(id)s","enabled":true}}'
i=0
while [ $i -lt 180 ]; do
    sleep 5
    i=$((i+1))
    R=$(curl -s -m 5 %(auth)s -H "$HDR" -d "$GET" "$URL" 2>/dev/null)
    if echo "$R" | grep -Eq '"enabled": ?true'; then
        exit 0
    fi
    if echo "$R" | grep -Eq '"enabled": ?false'; then
        curl -s -m 5 %(auth)s -H "$HDR" -d "$SET" "$URL" >/dev/null 2>&1
    fi
done
exit 1
""" % {'port': int(info.get('port') or 8080), 'id': SELF_ID, 'auth': auth}
    try:
        os.makedirs(os.path.dirname(HELPER_PATH), exist_ok=True)
        with open(HELPER_PATH, 'w', encoding='utf-8') as f:
            f.write(script)
        os.chmod(HELPER_PATH, 0o700)
        _log('Wrote self-enable helper %s (port %d%s).'
             % (HELPER_PATH, info.get('port') or 8080,
                ', auth' if auth else ''))
        return True
    except Exception as e:
        _log('Could not write helper: %s' % e, xbmc.LOGWARNING)
        return False


def cleanup_autostart_block():
    """Remove our one-shot block from autostart.sh, leaving anything else.

    Safe to call any time: this runs from Python, in a separate process, after
    autostart.sh has already finished executing for this boot. If our block is
    the only content left, the file is removed entirely.
    """
    if not os.path.exists(AUTOSTART_PATH):
        return
    try:
        with open(AUTOSTART_PATH, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        _log('Could not read %s for cleanup: %s' % (AUTOSTART_PATH, e),
             xbmc.LOGWARNING)
        return

    if AUTOSTART_MARKER not in content:
        return

    remainder = _strip_block(content).strip()

    try:
        if remainder in ('', '#!/bin/sh'):
            os.remove(AUTOSTART_PATH)
            _log('Removed %s (our block was its only content).' % AUTOSTART_PATH)
        else:
            with open(AUTOSTART_PATH, 'w', encoding='utf-8') as f:
                f.write(remainder + '\n')
            _log('Removed Addons33 delete block from %s' % AUTOSTART_PATH)
    except Exception as e:
        _log('Could not clean %s: %s' % (AUTOSTART_PATH, e), xbmc.LOGWARNING)

    for path in (TRIGGER_FILE, HELPER_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _read_step():
    try:
        with open(MARKER, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def _write_step(step):
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(MARKER, 'w', encoding='utf-8') as f:
            f.write(step)
        return True
    except Exception as e:
        _log('Could not write marker: %s' % e, xbmc.LOGWARNING)
        return False


def _clear_step():
    try:
        if os.path.exists(MARKER):
            os.remove(MARKER)
    except Exception:
        pass


def _settle(monitor, seconds):
    """Sleep that respects an abort request when a Monitor is available."""
    if monitor is not None:
        monitor.waitForAbort(seconds)
    else:
        xbmc.sleep(int(seconds * 1000))


def _jsonrpc(method, params):
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
    except Exception as e:
        _log('%s failed: %s' % (method, e), xbmc.LOGWARNING)
        return {}


def _take_snapshot():
    """Phase 1: remember the enabled add-ons and the active skin."""
    res = _jsonrpc('Addons.GetAddons', {'enabled': True})
    ids = [a.get('addonid') for a in
           (res.get('result', {}).get('addons') or []) if a.get('addonid')]
    snap = {'enabled': sorted(ids), 'skin': xbmc.getSkinDir()}
    try:
        from resources.lib import origin_fix
        origins = origin_fix.snapshot_origins()
    except Exception as e:
        _log('Origin snapshot failed: %s' % e, xbmc.LOGWARNING)
        origins = {}
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(SNAPSHOT, 'w', encoding='utf-8') as f:
            json.dump(snap, f)
        with open(ORIGINS, 'w', encoding='utf-8') as f:
            json.dump(origins, f)
        _log('Phase 1: snapshot of %d enabled add-on(s), skin %s.'
             % (len(ids), snap['skin']))
    except Exception as e:
        _log('Could not write snapshot: %s' % e, xbmc.LOGWARNING)


def _read_snapshot():
    try:
        with open(SNAPSHOT, 'r', encoding='utf-8') as f:
            snap = json.load(f)
        if isinstance(snap, dict) and snap.get('enabled'):
            return snap
    except Exception:
        pass
    return None


def _snapshot_set(key, value):
    try:
        with open(SNAPSHOT, 'r', encoding='utf-8') as f:
            snap = json.load(f)
        snap[key] = value
        with open(SNAPSHOT, 'w', encoding='utf-8') as f:
            json.dump(snap, f)
    except Exception as e:
        _log('Could not update snapshot (%s): %s' % (key, e), xbmc.LOGWARNING)


def read_origins():
    try:
        with open(ORIGINS, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def relink_pending():
    """True from the rebuild until the service has relinked once."""
    return os.path.exists(ORIGINS)


def clear_origins():
    try:
        if os.path.exists(ORIGINS):
            os.remove(ORIGINS)
    except Exception:
        pass


def _clear_snapshot():
    try:
        if os.path.exists(SNAPSHOT):
            os.remove(SNAPSHOT)
    except Exception:
        pass


def _restore_skin(skin_id):
    """Put the pre-rebuild skin back. The fresh DB registers home add-ons
    disabled, so Kodi fails to load the saved skin at boot and RESETS
    lookandfeel.skin to Estuary; without this the box comes back on Estuary."""
    if not skin_id or xbmc.getSkinDir() == skin_id:
        return
    try:
        from resources.lib import skin_switcher
        skin_switcher._swap_skin(skin_id)
    except Exception as e:
        _log('Skin restore failed (%s): %s' % (skin_id, e), xbmc.LOGWARNING)


def _enable_all_addons(only=None):
    """Enable installed-but-disabled add-ons via JSON-RPC.

    only: set of ids to enable (the phase-1 snapshot). None = every disabled
    add-on except NEVER_ENABLE (fallback for rebuilds scheduled before 3.1.5).

    Two passes: enabling an add-on whose dependency is still disabled can fail
    the first time, so a second sweep mops those up. Returns (enabled, failed).
    """
    enabled = failed = 0
    for _pass in range(2):
        try:
            req = {'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddons',
                   'params': {'enabled': False, 'properties': ['name']}}
            res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
            addons = res.get('result', {}).get('addons', []) or []
        except Exception as e:
            _log('GetAddons failed: %s' % e, xbmc.LOGWARNING)
            break
        if not addons:
            break
        for a in addons:
            aid = a.get('addonid')
            if not aid:
                continue
            if only is not None:
                if aid not in only:
                    continue
            elif aid in NEVER_ENABLE:
                continue
            try:
                er = {'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
                      'params': {'addonid': aid, 'enabled': True}}
                r = json.loads(xbmc.executeJSONRPC(json.dumps(er)))
                if 'error' in r:
                    failed += 1
                else:
                    enabled += 1
            except Exception:
                failed += 1
    return enabled, failed


# ---------------------------------------------------------------------------
def run():
    """Phase 1: schedule the rebuild, then restart into it.

    On CoreELEC the delete is handed to autostart.sh so it happens BEFORE Kodi
    opens the database. Elsewhere (macOS dev box) there is no autostart.sh, so
    fall back to deleting in-process and tell the user to reopen Kodi — Kodi
    does not relaunch itself there.
    """
    dlg = xbmcgui.Dialog()
    if not dlg.yesno(ADDON_NAME, T(30330), yeslabel=T(30051), nolabel=T(30052)):
        return

    if _is_coreelec():
        _take_snapshot()
        info = _webserver_info()
        if info:
            _write_helper(info)
            _snapshot_set('webserver_was_off', info['was_off'])
        if not _inject_autostart_delete():
            dlg.ok(ADDON_NAME, T(30335))
            return
        _write_step('2')
        _log('Phase 1: delete scheduled via autostart.sh. Rebooting.')
        dlg.ok(ADDON_NAME, T(30331))
        _restart()
        return

    # --- non-CoreELEC fallback (dev machines) ---
    files = _addons33_files()
    if not files:
        if dlg.yesno(ADDON_NAME, T(30334), yeslabel=T(30051), nolabel=T(30052)):
            _take_snapshot()
            _write_step('2')
            _notify_manual_restart(dlg)
        return

    _take_snapshot()
    removed = 0
    for f in files:
        try:
            os.remove(f)
            removed += 1
            _log('Deleted %s' % f)
        except Exception as e:
            _log('Could not delete %s: %s' % (f, e), xbmc.LOGWARNING)

    if not removed:
        dlg.ok(ADDON_NAME, T(30335))
        return

    _write_step('2')
    _log('Phase 1 (fallback): deleted %d Addons33 file(s).' % removed)
    _notify_manual_restart(dlg)


def _notify_manual_restart(dlg):
    """Kodi cannot relaunch itself off CoreELEC — say so before quitting.

    Previously this path called Quit silently, so Kodi just disappeared and the
    rebuild looked broken even when the delete had worked.
    """
    dlg.ok(ADDON_NAME, T(30336))
    from resources.lib import origin_fix
    origin_fix.force_restart('add-on database rebuild')


def continue_if_pending(monitor=None):
    """Phase 2: after the rebuild reboot, re-enable the add-ons that were
    enabled before (phase-1 snapshot), put the skin back, then restart.

    3.1.5 hardening (a 3.1.4 run hung inside the origin repair and never
    rebooted, leaving the box on Estuary with every add-on force-enabled):
      * the step marker is cleared FIRST, so a hang or crash can never make
        phase 2 run again on the next boot;
      * only the snapshot's add-ons are enabled (fallback: all but
        NEVER_ENABLE), so deliberately-disabled add-ons stay disabled;
      * no direct SQLite work here any more - the origin repair runs from the
        service on the next (quiet) boot, as it does on every boot;
      * the pre-rebuild skin is restored before the restart.

    Safe to call from the service on boot and from the menu on open; runs at
    most once per session and no-ops unless a rebuild is mid-flight.
    """
    global _CONTINUE_STARTED
    if _CONTINUE_STARTED:
        return False
    if _read_step() != '2':
        return False
    _CONTINUE_STARTED = True

    # Disarm before doing anything that could hang.
    _clear_step()
    cleanup_autostart_block()

    snap = _read_snapshot()
    _log('Phase 2: Addons33 rebuilt - re-enabling %s.'
         % ('%d snapshot add-on(s)' % len(snap['enabled']) if snap
            else 'all add-ons (no snapshot)'))
    _notify(T(30332))
    # Give Kodi time to finish rebuilding the DB and scanning add-ons.
    _settle(monitor, 20)
    if monitor is not None and monitor.abortRequested():
        return True

    enabled, failed = _enable_all_addons(set(snap['enabled']) if snap else None)
    _log('Phase 2: enabled %d add-on(s), %d could not be enabled.'
         % (enabled, failed))
    _settle(monitor, 3)

    # Put the update sources back from the phase-1 snapshot now, so they are
    # active after the restart below. One transaction, one connection; the
    # service repeats it on the next boot (plus a repo-refresh match for the
    # rest) and only then deletes ORIGINS.
    origins = read_origins()
    if origins:
        try:
            from resources.lib import origin_fix
            origin_fix.restore_origins(origins)
        except Exception as e:
            _log('Origin restore failed (service retries): %s' % e,
                 xbmc.LOGWARNING)

    if snap:
        _restore_skin(snap.get('skin'))
        if snap.get('webserver_was_off'):
            _jsonrpc('Settings.SetSettingValue',
                     {'setting': 'services.webserver', 'value': False})
    _clear_snapshot()

    _settle(monitor, 2)
    _log('Phase 2 complete - restarting into the clean database.')
    _restart()
    return True
