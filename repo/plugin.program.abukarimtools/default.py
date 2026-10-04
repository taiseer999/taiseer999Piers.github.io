# -*- coding: utf-8 -*-
import sys
import os
from urllib.parse import parse_qsl

import xbmc
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmcvfs

ADDON      = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_ID   = ADDON.getAddonInfo('id')
HANDLE     = int(sys.argv[1]) if len(sys.argv) > 1 else -1
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
if not ADDON_PATH.endswith('/') and not ADDON_PATH.endswith('\\'):
    ADDON_PATH += '/'

FANART = ADDON_PATH + 'fanart.jpg'
ICONS  = {
    'skin_install':   ADDON_PATH + 'resources/icons/skin_installer.png',
    'skin_switch':    ADDON_PATH + 'resources/icons/skin_switcher.png',
    'backup':         ADDON_PATH + 'resources/icons/backup.png',
    'abukarimwizard': ADDON_PATH + 'resources/icons/abukarimwizard.png',
    'patcher':        ADDON_PATH + 'resources/icons/patcher.png',
    'binary_install': ADDON_PATH + 'resources/icons/binary_install.png',
    'first_run':      ADDON_PATH + 'resources/icons/first_run.png',
    'dplex_toggle':   ADDON_PATH + 'resources/icons/dplex_toggle.png',
    'korean_toggle':  ADDON_PATH + 'resources/icons/korean_toggle.png',
    'icons_toggle':   ADDON_PATH + 'resources/icons/icons_toggle.png',
    'af3_trailers':   ADDON_PATH + 'resources/icons/af3_trailers.png',
    'af3_waves':      ADDON_PATH + 'resources/icons/af3_waves.png',
    'origin_fix':     ADDON_PATH + 'resources/icons/sources.png',
    'rebuild_addons33': ADDON_PATH + 'resources/icons/rebuild_addons33.png',
    'total_clean':    ADDON_PATH + 'resources/icons/clear_cache.png',
    'old_thumbs':     ADDON_PATH + 'resources/icons/clear_cache.png',
    'speedtest':      ADDON_PATH + 'resources/icons/speedtest.png',
    'addon_portal':   ADDON_PATH + 'resources/icons/addon_portal.png',
    # 3.2
    'bootstrap':      ADDON_PATH + 'resources/icons/bootstrap.png',
    'hw_tuning':      ADDON_PATH + 'resources/icons/hw_tuning.png',
    'webserver':      ADDON_PATH + 'resources/icons/webserver.png',
    'log_share':      ADDON_PATH + 'resources/icons/log_share.png',
    'remote_refresh': ADDON_PATH + 'resources/icons/remote_refresh.png',
    'menu_reconcile': ADDON_PATH + 'resources/icons/menu_reconcile.png',
    'profile_export': ADDON_PATH + 'resources/icons/profile_export.png',
    'profile_restore': ADDON_PATH + 'resources/icons/backup.png',
    'cat_profiles':   ADDON_PATH + 'resources/icons/profile_export.png',
    # category folder icons
    'cat_setup':      ADDON_PATH + 'resources/icons/install_setup.png',
    'cat_patch':      ADDON_PATH + 'resources/icons/patcher.png',
    'cat_maint':      ADDON_PATH + 'resources/icons/clear_cache.png',
    'cat_toggle':     ADDON_PATH + 'resources/icons/skin_switcher.png',
}

# Grouped menu: each category is (cat_key, category_label_id, icon_key, [items])
# where each item is (mode, label_id). Folder vs. action is decided per-mode
# below (only 'skin_switch' is a non-folder top-level action historically;
# inside a category, every entry is a leaf action).
CATEGORIES = [
    ('setup',  30014, 'cat_setup', [
        ('first_run',      30001),
        ('backup',         30002),
        ('skin_install',   30003),
        ('addon_portal',   30021),
        ('binary_install', 30004),
        ('bootstrap',      30590),
        ('hw_tuning',      30591),
        ('webserver',      30592),
    ]),
    ('patch',  30015, 'cat_patch', [
        ('patcher',        30005),
        ('origin_fix',     30007),
        ('remote_refresh', 30594),
    ]),
    ('maint',  30016, 'cat_maint', [
        ('abukarimwizard', 30008),
        ('total_clean',    30012),
        ('old_thumbs',     30013),
        ('rebuild_addons33', 30018),
        ('speedtest',      30019),
        ('log_share',      30593),
        ('menu_reconcile', 30595),
    ]),
    ('toggle', 30017, 'cat_toggle', [
        ('skin_switch',    30009),
        ('dplex_toggle',   30010),
        ('korean_toggle',  30011),
        ('icons_toggle',   30020),
        ('af3_trailers',   30430),
        ('af3_waves',      30603),
    ]),
    ('profiles', 30598, 'cat_profiles', [
        ('profile_export',  30596),
        ('profile_restore', 30597),
    ]),
]

# Modes that are leaf actions (run then return), not plugin folders.
ACTION_MODES = {'skin_switch', 'first_run', 'abukarimwizard',
                'total_clean', 'old_thumbs',
                # 3.1.19: an action, not a folder - as a folder its URL became
                # the container path, so the skin reload re-ran it in a loop
                'af3_trailers', 'af3_waves',
                # 3.2 tools: dialogs only, never folders (same reason as above)
                'bootstrap', 'hw_tuning', 'webserver', 'log_share',
                'remote_refresh', 'menu_reconcile', 'profile_export',
                'profile_restore'}


def _add_folder(label, cat_key, icon_key):
    url = sys.argv[0] + '?cat=' + cat_key
    li  = xbmcgui.ListItem(label)
    li.setArt({'icon': ICONS[icon_key], 'thumb': ICONS[icon_key], 'fanart': FANART})
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)


def _add_item(label, mode, is_folder=True):
    url = sys.argv[0] + '?mode=' + mode
    if mode == 'abukarimwizard':
        # Installed: link straight into the wizard's Maintenance menu, so it
        # opens with its own add-on context and Back returns here. Missing:
        # keep our own mode, which offers to install it.
        from resources.lib import wizard_runner
        if wizard_runner.wizard_installed():
            url = wizard_runner.wizard_url(wizard_runner.MODE_MAINTENANCE)
            is_folder = True
    li  = xbmcgui.ListItem(label)
    li.setArt({'icon': ICONS[mode], 'thumb': ICONS[mode], 'fanart': FANART})
    if not is_folder:
        li.setProperty('IsPlayable', 'false')
    xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)


def _ensure_fallback_font():
    """Self-heal: install the Arabic-capable global fallback font when the menu
    is opened, so Arabic is readable even if the boot service didn't run (e.g.
    service disabled, or on the very first open before a restart). Best-effort;
    a change only takes effect on the next Kodi start."""
    try:
        from resources.lib import font_fallback
        font_fallback.install()
    except Exception:
        pass


def _ensure_patches():
    """Self-heal: re-apply the automatic patch set when the menu is opened, in
    case the background watchdog service never ran this session.

    3.1.0.11: no longer a daemon thread inside this plugin invocation. The
    plugin exits in milliseconds and Kodi finalized the interpreter while the
    thread was mid-sweep, which on Kodi 22 / Python 3.14 stopped the menu from
    opening. The sweep now runs as its own RunPlugin invocation (mode
    'menu_sweep'), synchronously on that invocation's main thread, so the menu
    never waits on it and nothing is left running when either script ends.
    Every patch is idempotent, so a redundant sweep writes nothing.
    """
    try:
        xbmc.executebuiltin('RunPlugin(plugin://%s/?mode=menu_sweep)' % ADDON_ID)
    except Exception:
        pass


def _ensure_service():
    """3.1.10: Kodi sometimes never launches our xbmc.service at boot (zero
    [AbukarimTools] lines in a full boot log), which silently kills the
    auto-patch watchdog and the boot-time repo linking. The service sets a Home
    heartbeat property; if it is missing when the menu opens, start
    service.py ourselves as a script (it runs for the whole session)."""
    try:
        home = xbmcgui.Window(10000)
        if home.getProperty('abukarimtools.service.alive'):
            return
        if home.getProperty('abukarimtools.service.alive.kick'):
            return                      # already kicked this session
        home.setProperty('abukarimtools.service.alive.kick', '1')
        xbmc.log('[AbukarimTools Menu] service not running - starting it',
                 xbmc.LOGWARNING)
        xbmc.executebuiltin('RunScript(%s)'
                            % os.path.join(ADDON_PATH.rstrip('/\\'), 'service.py'))
    except Exception as e:
        xbmc.log('[AbukarimTools Menu] could not start service: %s' % e,
                 xbmc.LOGWARNING)


def _menu_relink():
    """Link add-ons with an empty update source whenever the menu opens,
    independent of the service. Quick: one SQLite pass over the cached repo
    listings; a repo refresh (slow) is left to the service."""
    try:
        from resources.lib import origin_fix
        res = origin_fix.fix_addons(None)
        if res.get('fixed'):
            xbmc.log('[AbukarimTools Menu] linked on menu open: %s'
                     % ', '.join('%s -> %s' % kv for kv in sorted(res['fixed'].items())),
                     xbmc.LOGINFO)
        if res.get('unmatched'):
            xbmc.log('[AbukarimTools Menu] no repository carries: %s'
                     % ', '.join(sorted(res['unmatched'])), xbmc.LOGINFO)
        home = xbmcgui.Window(10000)
        if res.get('stale') and not home.getProperty('abukarimtools.reporefresh'):
            # Only an out-of-date cached listing carries these (e.g. AF3 5.10.18
            # vs a cached 5.5.25): refresh the repos once per session; the next
            # menu open / boot corrects the origin from the fresh listing.
            home.setProperty('abukarimtools.reporefresh', '1')
            xbmc.log('[AbukarimTools Menu] out-of-date repo listing for %s - '
                     'refreshing repositories' % ', '.join(sorted(res['stale'])),
                     xbmc.LOGINFO)
            xbmc.executebuiltin('UpdateAddonRepos')
        if res.get('fixed'):
            from resources.lib.i18n import T
            xbmcgui.Dialog().notification(
                'ABUKARIM TOOLS', T(30337) % len(res['fixed']),
                xbmcgui.NOTIFICATION_INFO, 8000)
    except Exception as e:
        xbmc.log('[AbukarimTools Menu] relink failed: %s' % e, xbmc.LOGWARNING)


def _menu_sweep():
    """Body of the 'menu_sweep' invocation. Main thread, no directory."""
    _ensure_service()
    _menu_relink()
    try:
        from resources.lib import patch_watchdog, patcher
        if patch_watchdog.first_run_active():
            return                      # never sweep under first-run dialogs
        ids = [a for a in patcher.target_addon_ids() if patch_watchdog._addon_path(a)]
        if ids:
            patcher.apply_set(addon_ids=ids)
            patcher.reload_skin_if_pending()
    except Exception as e:
        xbmc.log('[AbukarimTools MenuSweep] failed: %s' % e, xbmc.LOGWARNING)


def _continue_addons33_rebuild():
    """If an Addons33 rebuild is mid-flight (phase 2: DB deleted, Kodi has
    rebuilt a fresh one), finish it when the menu is opened even if the boot
    service never ran. No-op otherwise.

    3.1.7: no longer runs inline. Phase 2 waits ~25 s, enables add-ons and
    reboots; doing that inside this directory listing blocked the menu (the
    box looked frozen on "Programs"). It now runs as its own RunPlugin
    invocation (mode=addons33_continue), like the menu sweep."""
    try:
        from resources.lib import addons33_rebuild
        if addons33_rebuild._read_step() == '2':
            xbmc.executebuiltin(
                'RunPlugin(plugin://%s/?mode=addons33_continue)' % ADDON_ID)
    except Exception:
        pass


def _mlog(msg):
    """Menu-open trace (DEBUG level; was WARNING in the 3.1.0.13/14 diagnostics)."""
    try:
        xbmc.log('[AbukarimTools Menu] %s' % msg, xbmc.LOGDEBUG)
    except Exception:
        pass


def main_menu():
    _mlog('open: start (argv=%r)' % (sys.argv,))
    from resources.lib.i18n import T
    _mlog('i18n imported')
    _continue_addons33_rebuild()
    _mlog('addons33 continue checked')
    _ensure_fallback_font()
    _mlog('fallback font checked')
    for cat_key, label_id, icon_key, _items in CATEGORIES:
        label = T(label_id)
        _mlog('item %s: label ok' % cat_key)
        _add_folder(label, cat_key, icon_key)
        _mlog('item %s: added' % cat_key)
    xbmcplugin.setContent(HANDLE, 'files')
    _mlog('setContent done - calling endOfDirectory')
    xbmcplugin.endOfDirectory(HANDLE)
    _mlog('endOfDirectory returned')
    # The self-heal sweep is queued only AFTER the listing is handed back, so
    # nothing it does can overlap with building the menu.
    _ensure_patches()
    _mlog('sweep queued - done')


def category_menu(cat_key):
    from resources.lib.i18n import T
    for c_key, _label_id, _icon, items in CATEGORIES:
        if c_key != cat_key:
            continue
        for mode, label_id in items:
            label = T(label_id)
            if mode == 'af3_waves':
                try:
                    from resources.lib import af3_waves_toggle as _wt
                    label = '%s: %s' % (label, T(30436) if _wt.waves_on() else T(30437))
                except Exception:
                    pass
            if mode == 'af3_trailers':
                # show the current state right in the Toggles list
                try:
                    from resources.lib.af3_trailers import config as _tcfg
                    label = '%s: %s' % (label, T(30436) if _tcfg.load()['enabled'] else T(30437))
                except Exception:
                    pass
            _add_item(label, mode, is_folder=(mode not in ACTION_MODES))
        break
    xbmcplugin.setContent(HANDLE, 'files')
    # not cached: the Toggles list shows live on/off states
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def _end_directory():
    xbmcplugin.setContent(HANDLE, 'files')
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True,
                               updateListing=False, cacheToDisc=False)


def router():
    raw     = sys.argv[2][1:] if len(sys.argv) > 2 else ''
    params  = dict(parse_qsl(raw))
    mode    = params.get('mode')
    cat     = params.get('cat')      # set when a category folder is opened

    # --- Category folder ---
    if cat is not None and mode is None:
        category_menu(cat)
        return

    # --- Top-level menu ---
    if mode is None:
        main_menu()
        return

    if mode == 'menu_sweep':
        _menu_sweep()
        return

    if mode == 'addons33_continue':
        try:
            from resources.lib import addons33_rebuild
            addons33_rebuild.continue_if_pending(xbmc.Monitor())
        except Exception as e:
            xbmc.log('[AbukarimTools Addons33] continue failed: %s' % e,
                     xbmc.LOGWARNING)
        return

    if mode == 'first_run':
        # Non-folder action (3.1.0.20): no plugin listing is opened, and the
        # sequence runs as its own RunPlugin invocation (mode=first_run_exec), detached from this
        # plugin call and from the Programs container (whose refreshes during
        # add-on rescans were tearing setup dialogs down).
        from resources.lib.i18n import T
        if xbmcgui.Dialog().yesno(
                'ABUKARIM TOOLS',
                T(30050),
                yeslabel=T(30051), nolabel=T(30052)):
            # RunPlugin (not RunScript-by-path, which has no add-on context:
            # 3.1.0.20 crashed with "No valid addon id could be obtained").
            # handle=-1 invocation, detached from any directory listing.
            xbmc.executebuiltin(
                'RunPlugin(plugin://%s/?mode=first_run_exec)' % ADDON_ID)
        return

    if mode == 'first_run_exec':
        import_root = ADDON_PATH.rstrip('/\\')
        if import_root not in sys.path:
            sys.path.insert(0, import_root)
        import service
        service.run_now(remove_flag=True, force=True)
        return

    if mode == 'skin_install':
        _end_directory()
        from resources.lib import skin_installer
        skin_installer.run()

    elif mode == 'addon_portal':
        _end_directory()
        from resources.lib import addon_portal
        addon_portal.run()

    elif mode == 'skin_switch':
        # Non-folder action: don't open/close a plugin listing (that leaves an
        # empty container with a back arrow). Just run; the switcher closes
        # to the new skin's Home itself via _close_to_home().
        from resources.lib import skin_switcher
        skin_switcher.run()

    elif mode == 'backup':
        _end_directory()
        from resources.lib import backup_manager
        backup_manager.BackupManager().run()

    elif mode == 'abukarimwizard':
        # Non-folder action: only reached when the wizard link could not be
        # used (wizard missing) or from an old favourite/shortcut.
        from resources.lib import wizard_runner
        wizard_runner.open_wizard()

    elif mode == 'total_clean':
        from resources.lib import wizard_runner
        wizard_runner.run_total_clean()

    elif mode == 'old_thumbs':
        from resources.lib import wizard_runner
        wizard_runner.run_old_thumbs()

    elif mode == 'openwizard':
        # Legacy URL (<= 3.1.2 favourites / skin shortcuts), which were
        # opened as a folder: close that listing, then hand off.
        if HANDLE >= 0:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        from resources.lib import wizard_runner
        wizard_runner.open_wizard()

    elif mode == 'patcher':
        _end_directory()
        from resources.lib import patcher
        patcher.run()

    elif mode == 'rebuild_addons33':
        _end_directory()
        from resources.lib import addons33_rebuild
        addons33_rebuild.run()

    elif mode == 'speedtest':
        _end_directory()
        # Ookla speedtest-cli vendored at resources/lib/modules/speedtest.py.
        # Run it as a standalone script (RunScript adds its own directory to
        # sys.path so the sibling backtothefuture import resolves) — it draws
        # its own DialogProgress and shows the result image on completion.
        script = ADDON_PATH + 'resources/lib/modules/speedtest.py'
        xbmc.executebuiltin('RunScript(%s)' % script)

    elif mode == 'binary_install':
        _end_directory()
        from resources.lib import binary_installer
        binary_installer.run()

    elif mode == 'dplex_toggle':
        _end_directory()
        from resources.lib import dplex_toggle
        dplex_toggle.run()

    elif mode == 'korean_toggle':
        _end_directory()
        from resources.lib import korean_toggle
        korean_toggle.run()

    elif mode == 'icons_toggle':
        _end_directory()
        from resources.lib import icons_toggle
        icons_toggle.run()

    elif mode == 'af3_trailers':
        from resources.lib import af3_trailers_toggle
        af3_trailers_toggle.run()

    elif mode == 'af3_waves':
        from resources.lib import af3_waves_toggle
        af3_waves_toggle.run()

    elif mode == 'origin_fix':
        _end_directory()
        from resources.lib import origin_fix
        origin_fix.run()

    # ---- 3.2 ----
    elif mode == 'bootstrap':
        from resources.lib import bootstrap
        from resources.lib.i18n import T
        if not bootstrap.pending():
            xbmcgui.Dialog().notification('ABUKARIM TOOLS', T(30542))
        else:
            bootstrap.run()

    elif mode == 'hw_tuning':
        from resources.lib import hw_tuning
        hw_tuning.run()

    elif mode == 'webserver':
        from resources.lib import webserver_secure
        webserver_secure.run()

    elif mode == 'log_share':
        from resources.lib import log_share
        log_share.run()

    elif mode == 'remote_refresh':
        from resources.lib import remote_config
        from resources.lib.i18n import T
        res = remote_config.refresh(force=True)
        lines = ['%s: %s' % kv for kv in sorted(res.items())]
        # 3.2.6: apply what was just downloaded now, not at the next sweep
        try:
            from resources.lib import patcher, patch_watchdog
            ids = [a for a in patcher.target_addon_ids() if patch_watchdog._addon_path(a)]
            ok_n, fail_n, written, _r = patcher.apply_set(addon_ids=ids)
            lines.append('')
            lines.append('patches: %d OK, %d failed, %d written' % (ok_n, fail_n, written))
        except Exception as e:
            lines.append('patches: %s' % e)
        xbmcgui.Dialog().ok('ABUKARIM TOOLS', T(30599) % '[CR]'.join(lines))

    elif mode == 'menu_reconcile':
        from resources.lib import menu_reconcile
        from resources.lib.i18n import T
        res = menu_reconcile.run(rebuild=True)
        xbmcgui.Dialog().notification('ABUKARIM TOOLS', T(30589) % (res['hidden'], res['shown']))

    elif mode == 'profile_export':
        from resources.lib import skin_profiles
        skin_profiles.export_current()

    elif mode == 'profile_restore':
        from resources.lib import skin_profiles
        skin_profiles.restore_backup()


router()
