# -*- coding: utf-8 -*-
"""
service.py – ABUKARIM TOOLS first-run automation.

NOTE: the AUTOMATIC first-run at boot is currently DISABLED via the
AUTO_FIRST_RUN switch below (it caused problems in the field). The service
still runs on every boot for its other duties (post-update restart, autostart
cleanup, Arabic fallback font, and the auto-patch watchdog), but it no longer
arms or runs setup on its own. Setup is now manual only — the Tools menu item
or RunScript(plugin.program.abukarimtools, firstrun). The description below
documents the behaviour that AUTO_FIRST_RUN=True would restore.

Runs as a Kodi service on every start. It only does something when the
one-shot flag file (shipped inside the build's userdata) is present:

    special://profile/addon_data/plugin.program.abukarimtools/first_run.flag

The flag is extracted together with the build, so it exists exactly once:
on the first Kodi start after a fresh build install. The service then:

    1. Waits for Kodi's home window and for the ABUKARIM wizard to finish
       its own first-run work (enable_addons / backup_gui_skin).
    2. Deletes the flag (guarantees the sequence never repeats).
    3. Runs the Binary Installer silently (resources/lib/binary_installer.py).
    4. Shows a popup: Restore Backup / Skip.
         - Restore -> backup_manager.py restore flow
    5. Opens the Add-on Portal (resources/lib/addon_portal.py) so the user
       can tick the video add-ons they want (Back = skip).
    6. Applies patches (so freshly installed add-ons get patched too).
    7. Opens the Skin Installer last (resources/lib/skin_installer.py).
"""

import os
import time
import traceback

import xbmc
xbmc.log('[AbukarimTools Service] process started', xbmc.LOGINFO)   # 3.2.15: before any add-on-manager call
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

from resources.lib import paths as _paths


class _LazyAddon(object):
    """xbmcaddon.Addon only when really needed (never at import)."""
    _a = None

    def __getattr__(self, name):
        if _LazyAddon._a is None:
            _LazyAddon._a = xbmcaddon.Addon('plugin.program.abukarimtools')
        return getattr(_LazyAddon._a, name)


ADDON       = _LazyAddon()
ADDON_NAME  = 'ABUKARIM TOOLS'
ADDON_PATH  = _paths.ADDON_PATH
PROFILE     = _paths.PROFILE
FLAG_FILE   = os.path.join(PROFILE, 'first_run.flag')


# Marker written once first-run has completed, so it can never repeat (this is
# what stops the skin's startup from re-triggering the whole sequence in a
# loop). A separate lock guards against two launches overlapping.
DONE_FILE = os.path.join(PROFILE, 'first_run.done')
LOCK_FILE = os.path.join(PROFILE, 'first_run.lock')

# Self-trigger: a new build apply replaces the addons/ folder wholesale, so a
# version string shipped INSIDE the addon is always fresh after an install.
# We compare it against a copy stored in addon_data; if they differ (or the
# addon_data copy is missing — e.g. wiped by the build's restore), a new build
# was applied and we (re)create the first-run flag. The wipe can only REMOVE
# LAST_BUILD_FILE, which makes first-run more likely to fire, never less, so the
# trigger is immune to the addon_data wipe.
BUILD_ID_FILE   = os.path.join(ADDON_PATH, 'resources', 'build.id')   # shipped
LAST_BUILD_FILE = os.path.join(PROFILE, 'last_build.id')              # addon_data

WIZARD_ID   = 'plugin.program.ABUKARIMwizard'

# --------------------------------------------------------------------------
# Master switch for the AUTOMATIC first-run at boot.
#
# When False (current setting) the service NEVER arms or runs the first-run
# sequence by itself on startup, and never force-switches the UI language on
# boot. It caused too many problems in the field: the build.id self-trigger
# below re-armed on any build.id/done-marker mismatch (fresh apply, wiped
# addon_data, or a run interrupted by a crash/power-cycle), so setup could
# fire unexpectedly or loop, and the CoreELEC path auto-reboots at the end.
#
# Manual setup is UNAFFECTED — the menu item (default.py -> first_run) and
# RunScript(plugin.program.abukarimtools, firstrun) both call run_now()
# directly and still work exactly as before. Flip this back to True only if
# you deliberately want boot-time auto setup again.
AUTO_FIRST_RUN = False

# How long (seconds) to wait for Kodi/wizard to settle before starting.
STARTUP_TIMEOUT = 180
# If the Home window still isn't visible after this many seconds (e.g. the
# CoreELEC first-boot wizard is on screen), start anyway instead of waiting
# the full STARTUP_TIMEOUT. macOS/normal boots start the moment Home appears,
# so this only affects the *ELEC 'takes forever' case.
STARTUP_GRACE = 30

# A LOCK_FILE older than this is treated as abandoned rather than "another
# run in progress". Nothing in _run_steps legitimately runs anywhere close to
# this long even counting the _wait_no_modal(timeout=600) worst case, so a
# lock still present past this ceiling means the process that wrote it died
# without reaching the finally block that clears it — a Kodi crash, kernel
# panic, or hard power-cycle mid-sequence, all of which this box is prone to.
# Without this, one interrupted run wedges every future automatic AND manual
# attempt forever, silently (see [AbukarimTools FirstRun] "lock present"
# repeating in the log with no user-visible symptom at all).
STALE_LOCK_SECONDS = 1800  # 30 minutes


def _lock_is_stale():
    """True if LOCK_FILE exists but is old enough to be an abandoned lock
    from an interrupted run rather than one that's genuinely still active."""
    try:
        age = time.time() - os.path.getmtime(LOCK_FILE)
    except OSError:
        return False  # doesn't exist -> not stale, just absent
    return age > STALE_LOCK_SECONDS


def _clear_stale_lock(context):
    """If LOCK_FILE is stale, remove it and log why. Returns True if a lock
    remains (still fresh, a run is genuinely in progress)."""
    if not os.path.exists(LOCK_FILE):
        return False
    if _lock_is_stale():
        age = time.time() - os.path.getmtime(LOCK_FILE)
        _log('%s: stale lock (%.0fs old) found — a previous run was likely '
             'interrupted (crash/reboot) before it could finish. Clearing '
             'it and proceeding.' % (context, age), xbmc.LOGWARNING)
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        return False
    return True


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools FirstRun] %s' % msg, level)


# --------------------------------------------------------------------------
# Readiness helpers
# --------------------------------------------------------------------------
def _wizard_first_run_done():
    """
    True when the ABUKARIM wizard has finished (or will not run) its own
    first-run routine, so our dialogs won't fight with its dialogs.
    """
    try:
        wiz = xbmcaddon.Addon(WIZARD_ID)
        return wiz.getSetting('firstrun') != 'true'
    except Exception:
        # Wizard not installed / not enabled -> nothing to wait for
        return True


def _wait_until_ready(monitor):
    """Decide when it's safe to start the first-run sequence.

    Fast path (macOS / normal boot): start as soon as the Home window is
    visible and the ABUKARIM wizard has finished — usually only a few seconds.

    CoreELEC/LibreELEC: on a fresh box the *ELEC first-boot wizard owns the
    screen, so Home never reports visible for a long time and the old code sat
    here for the full STARTUP_TIMEOUT (that's the 'takes forever to start').
    To avoid that, we also start after a short GRACE period even if Home isn't
    detected — the sequence's own per-step modal waits keep it from colliding
    with anything still on screen.
    """
    waited = 0
    _log('Waiting for system to settle before first-run (grace=%ss, '
         'max=%ss)…' % (STARTUP_GRACE, STARTUP_TIMEOUT))
    while not monitor.abortRequested() and waited < STARTUP_TIMEOUT:
        home_visible = xbmc.getCondVisibility('Window.IsVisible(home)')
        if home_visible and _wizard_first_run_done():
            # Fast path (macOS / normal boot): wizard already done and we're on
            # the home screen — start right away after a short settle.
            _log('Home screen ready — starting first-run now.')
            if monitor.waitForAbort(5):
                return False
            return True
        # Fallback for CoreELEC/LibreELEC: the ABUKARIM build wizard can run a
        # long first-boot routine, and Home stays hidden behind it, so neither
        # condition above becomes true for a long time. After the grace period,
        # start anyway. We no longer require the wizard to report 'done' here —
        # the sequence's own per-step modal waits keep it from colliding with
        # any wizard dialog still on screen, and it stops the skin step from
        # being blocked indefinitely.
        if waited >= STARTUP_GRACE:
            _log('Grace period (%ss) elapsed without a clear home screen — '
                 'starting the first-run sequence anyway.' % STARTUP_GRACE)
            if monitor.waitForAbort(2):
                return False
            return True
        if monitor.waitForAbort(2):
            return False
        waited += 2
    # Timeout: continue anyway unless Kodi is shutting down
    return not monitor.abortRequested()


# --------------------------------------------------------------------------
# Sequence steps
# --------------------------------------------------------------------------
def _step_patcher(monitor):
    try:
        from resources.lib import patcher
        _log('Applying patches…')
        patcher.run()
        return True
    except Exception:
        _log('Patcher failed:\n%s' % traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            ADDON_NAME, T(30053),
            xbmcgui.NOTIFICATION_ERROR, 6000)
        return False


def _step_guarded(name, fn):
    """Run one optional 3.2 step; a crash is logged and setup continues."""
    try:
        return fn()
    except Exception:
        _log('Step %s crashed (ignored):\n%s' % (name, traceback.format_exc()),
             xbmc.LOGERROR)
        return None


def _step_addon_portal():
    try:
        from resources.lib import addon_portal
        # One question first: the preset decides what the portal pre-ticks.
        preselect = set()
        try:
            from resources.lib import presets
            preselect = presets.addon_selection(presets.choose())
        except Exception:
            _log('Preset step failed (portal opens unticked):\n%s'
                 % traceback.format_exc(), xbmc.LOGWARNING)
        _log('Opening Add-on Portal… (preselect=%s)' % sorted(preselect))
        # first_run=True: no restart recommendation at the end (the sequence
        # still has steps to run; the caller handles the final reboot).
        addon_portal.run(first_run=True, preselect=preselect)
        return True
    except Exception:
        _log('Add-on Portal failed:\n%s' % traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, T(30060),
                                      xbmcgui.NOTIFICATION_ERROR, 6000)
        return False


def _step_skin_installer():
    try:
        from resources.lib import skin_installer
        _log('Opening Skin Installer…')
        # first_run=True: the portal closes itself after a successful
        # install and the skin is applied after the modal is gone, so the
        # sequence continues automatically instead of waiting for the user
        # to press Back.
        skin_installer.run(first_run=True)
        return True
    except Exception:
        _log('Skin Installer failed:\n%s' % traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(ADDON_NAME, T(30054))
        return False


def _wait_skin_settle(monitor, seconds=8):
    """Give ReloadSkin time to finish before opening the next dialog."""
    waited = 0
    while waited < seconds:
        if monitor.waitForAbort(1):
            return False
        waited += 1
        if not xbmc.getCondVisibility('Window.IsActive(busydialog)') and waited >= 4:
            break
    return True


def _wait_no_modal(monitor, timeout=600, stable=2):
    """
    Wait until NO modal dialog is on screen for `stable` consecutive
    seconds. After a skin is applied, other addons (e.g. TMDb Helper)
    may pop their own dialogs; opening ours on top of theirs gets ours
    instantly dismissed. So we politely wait for the screen to be clear
    (up to `timeout` seconds — the user may need time to answer them).
    """
    waited = 0
    clear = 0
    while not monitor.abortRequested() and waited < timeout:
        if xbmc.getCondVisibility('System.HasModalDialog'):
            if clear:
                _log('Waiting for foreign dialog to close before continuing…')
            clear = 0
        else:
            clear += 1
            if clear >= stable:
                return True
        if monitor.waitForAbort(1):
            return False
        waited += 1
    return not monitor.abortRequested()


def _step_binary_installer(monitor):
    try:
        from resources.lib import binary_installer
        _log('Running Binary Installer (auto, no prompt)…')
        # auto=True: installs inputstream.adaptive / vfs.libarchive silently —
        # progress bar + finishing notification only, no confirmation dialog.
        binary_installer.run(auto=True)
        return True
    except Exception:
        _log('Binary Installer failed:\n%s' % traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, T(30055),
                                      xbmcgui.NOTIFICATION_ERROR, 6000)
        return False


def _step_restore():
    try:
        from resources.lib import backup_manager
        _log('Opening Backup Manager (restore)…')
        bm     = backup_manager.BackupManager()
        dialog = xbmcgui.Dialog()
        # 3.2.9: no customisations question - menus/widgets always restored
        bm._do_restore(dialog, set(backup_manager.SKIN_ADDONS))
    except Exception:
        _log('Restore failed:\n%s' % traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(ADDON_NAME, T(30056))


def _settle(monitor, seconds):
    """Plain wait that still honours Kodi shutdown."""
    return not monitor.waitForAbort(seconds)


def _final_choice(monitor):
    """Popup: Restore Backup / Skip.

    A select dialog instead of yes/no: yes/no returns False both for "Skip"
    and for "dismissed by something else", so a swallowed popup used to be
    read as the user skipping (3.1.0.19 log: dismissed 3x in 2 s, then
    "User skipped the restore step" without the user ever seeing it).
    select() returns -1 only on Back/dismiss, so:
      0  -> restore        1 -> skip (explicit)
     -1 fast (<1.5 s)     -> swallowed: wait for a clear screen, ask again
     -1 slow              -> user pressed Back: treat as skip
    """
    choice = None
    for attempt in range(1, 7):
        _wait_no_modal(monitor)
        started = time.time()
        idx = xbmcgui.Dialog().select(T(30057).replace('[CR]', ' '),
                                      [T(30058), T(30059)])
        if idx >= 0 or time.time() - started > 1.5:
            choice = (idx == 0)
            break
        _log('Restore popup was dismissed instantly (attempt %d) — waiting '
             'and asking again.' % attempt)
        if not _settle(monitor, 2):
            return
    if choice:
        _step_restore()
    else:
        _log('User skipped the restore step.')


# --------------------------------------------------------------------------
def run_first_run_sequence(monitor):
    if not _wait_until_ready(monitor):
        _log('Kodi shutting down before sequence could start — flag kept '
             'so it will run on next boot.')
        return

    # Already completed (e.g. skin reload re-fired the service) → stop.
    if os.path.exists(DONE_FILE):
        _log('First-run already completed (done marker present) — skipping.')
        try:
            os.remove(FLAG_FILE)
        except OSError:
            pass
        return
    if _clear_stale_lock('Automatic first-run'):
        _log('First-run already running (lock present) — skipping duplicate.')
        return

    try:
        with open(LOCK_FILE, 'w') as f:
            f.write('running')
    except OSError:
        pass

    # Remove the flag *before* running so the sequence is strictly one-shot
    # even if the user aborts Kodi half-way through.
    try:
        os.remove(FLAG_FILE)
    except OSError:
        pass

    try:
        _run_steps(monitor)
    finally:
        _mark_done()
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass

    # Reboot prompt LAST — only after the done marker is safely on disk, so a
    # user-approved reboot can never cut the completion record short and
    # re-trigger the sequence on the next boot.
    _prompt_reboot_if_coreelec(monitor)


def run_now(monitor=None, remove_flag=True, force=False):
    """Run the first-run steps immediately, skipping the boot-time wait.

    Guards against the loop where the skin's startup re-launches first-run on
    every skin load:
      • If first-run already completed (DONE_FILE exists) we refuse to run
        again unless force=True (the menu item passes force=True so the user
        can deliberately re-run setup).
      • A LOCK_FILE prevents two launches from overlapping.
    """
    if monitor is None:
        monitor = xbmc.Monitor()

    # Already completed → do nothing (this breaks the skin-startup loop).
    if not force and os.path.exists(DONE_FILE):
        _log('First-run already completed (done marker present) — skipping.')
        return

    # Another run in progress → do nothing, unless the caller is explicitly
    # forcing a retry (the menu item passes force=True) — in that case a
    # stuck lock is exactly the thing the user is trying to override, so
    # clear it unconditionally instead of deferring to it. Without force,
    # still honor a genuinely fresh lock but drop a stale/abandoned one.
    if force:
        if os.path.exists(LOCK_FILE):
            _log('Manual run forced — clearing existing lock '
                 '(stale or not) before proceeding.', xbmc.LOGWARNING)
            try:
                os.remove(LOCK_FILE)
            except OSError:
                pass
    elif _clear_stale_lock('Manual first-run'):
        _log('First-run already running (lock present) — skipping duplicate.')
        return

    try:
        with open(LOCK_FILE, 'w') as f:
            f.write('running')
    except OSError:
        pass

    if remove_flag:
        try:
            os.remove(FLAG_FILE)
        except OSError:
            pass

    _log('Manual run requested.')
    try:
        _run_steps(monitor)
    finally:
        # A restore during _run_steps (Step 2) can re-create first_run.flag from
        # the backup; drop it again so no stale flag survives this completed run.
        try:
            os.remove(FLAG_FILE)
        except OSError:
            pass
        # Mark complete (with the shipped build id) and release the lock.
        _mark_done()
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass

    # Same ordering rule as the automatic path: done marker first, reboot
    # prompt second.
    _prompt_reboot_if_coreelec(monitor)


def _run_steps(monitor):
    _log('Starting first-run sequence.')

    # Make Kodi's core dialogs readable before we show any: force the UI
    # language to English when the box is on Arabic (skin fonts have no Arabic
    # glyphs, so core dialog text would otherwise be tofu). No-op if already
    # English or on a deliberately-chosen non-Arabic language.
    try:
        from resources.lib import set_language
        set_language.force_english(only_if_arabic=True)
    except Exception:
        _log('UI language switch crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # (Welcome splash removed in 3.1.0.20.) The language switch above reloads
    # the skin; let that finish before the first dialog, otherwise the reload
    # tears down whatever we open.
    _wait_skin_settle(monitor)
    _wait_no_modal(monitor)

    _log('Step 1 — Binary Installer.')
    _step_binary_installer(monitor)
    # The binary installer ends with UpdateLocalAddons; Kodi's add-on rescan
    # that follows is what dismissed the restore popup instantly (3.1.0.19
    # log). Give it time to finish before showing anything.
    _settle(monitor, 3)
    _wait_no_modal(monitor)

    _log('Step 1b — Thin-build bootstrap (no-op on a full build).')
    _step_guarded('bootstrap', lambda: __import__(
        'resources.lib.bootstrap', fromlist=['run']).run())
    _wait_no_modal(monitor)

    _log('Step 1c — Device tuning (silent).')
    _step_guarded('hw_tuning', lambda: __import__(
        'resources.lib.hw_tuning', fromlist=['auto']).auto())

    _log('Step 2 — Restore popup.')
    _final_choice(monitor)

    _log('Step 3 — Preset + Add-on Portal.')
    _wait_no_modal(monitor)
    _step_addon_portal()

    _log('Step 4 — Apply Patches.')
    _wait_no_modal(monitor)
    _step_patcher(monitor)

    _log('Step 4b — Per-box remote access password.')
    _wait_no_modal(monitor)
    _step_guarded('webserver', lambda: __import__(
        'resources.lib.webserver_secure', fromlist=['first_run']).first_run())

    _log('Step 5 — Skin Installer (last).')
    _wait_no_modal(monitor)
    _step_skin_installer()

    _log('First-run sequence finished.')

    # All steps done — hand the box back to Arabic. Setup ran in English so its
    # dialogs were readable; day-to-day use is Arabic. (Whether Arabic renders
    # cleanly afterward depends on the active skin's font — Arctic Fuse 3, just
    # installed, ships Arabic fonts; Estuary does not.) Done AFTER the last
    # setup dialog so nothing shown during setup is affected, and BEFORE the
    # caller's reboot prompt — that prompt uses a hardcoded English Python
    # string, so it stays readable regardless of UI language.
    try:
        from resources.lib import set_language
        set_language.force_arabic()
    except Exception:
        _log('Switch back to Arabic crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # NOTE: the CoreELEC reboot prompt is deliberately NOT here any more.
    # It is issued by the callers AFTER the done marker has been written —
    # the Reboot builtin races the finally block, and if the system went
    # down before DONE_FILE landed, the (now DONE-keyed) trigger would
    # re-run the whole sequence on the next boot.


def _is_coreelec():
    """True on a CoreELEC installation (same check the binary installer uses)."""
    if os.path.isdir('/etc/coreelec'):
        return True
    try:
        with open('/etc/os-release') as f:
            return any('coreelec' in line.lower() for line in f)
    except OSError:
        return False


def _prompt_reboot_if_coreelec(monitor):
    if not _is_coreelec():
        _log('Reboot skipped (not CoreELEC).')
        return
    # Let the freshly-loaded skin settle before rebooting.
    if monitor.waitForAbort(10):
        return  # Kodi is shutting down anyway
    # Make sure no modal is in the way.
    _wait_no_modal(monitor)
    # Reboot automatically (no prompt) to finish applying the build. Show a
    # brief heads-up first so the reboot isn't mistaken for a crash.
    try:
        xbmc.executebuiltin(
            'Notification(%s, %s, 5000)'
            % (ADDON_NAME,
               'Setup complete — rebooting to finish. / '
               'اكتمل الإعداد — سيُعاد التشغيل.'))
    except Exception:
        pass
    if monitor.waitForAbort(5):
        return
    _log('First-run complete — rebooting system automatically.')
    xbmc.executebuiltin('Reboot')


def _read_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def _first_run_pending():
    """True if first-run has NOT completed for the currently shipped build.

    Returns (pending: bool, build_id: str). If no build.id ships with the
    addon we return (False, '') so behaviour is unchanged for builds that
    don't use this mechanism.

    The check is keyed off DONE_FILE, which stores the build id of the last
    COMPLETED first-run (written only after _run_steps finishes). This is what
    makes the trigger crash-resilient: the old code compared build.id against
    LAST_BUILD_FILE, which was recorded at ARM time — so a kernel panic /
    power-cycle mid-sequence (FLAG already consumed, DONE never written) left
    changed=False on every subsequent boot and first-run silently never ran
    again. Now an interrupted run simply re-arms on the next boot until a run
    actually completes.

    Legacy migration: pre-1.7.3.2 installs wrote the literal string 'done'
    into DONE_FILE and the build id into LAST_BUILD_FILE. If both match the
    old completed state, migrate DONE_FILE to the new format instead of
    re-running first-run on devices that already finished it.
    """
    build_id = _read_text(BUILD_ID_FILE)
    if not build_id:
        return False, ''
    done = _read_text(DONE_FILE)
    if done == build_id:
        return False, build_id
    if done == 'done' and _read_text(LAST_BUILD_FILE) == build_id:
        # Old-format completion for this same build — migrate, don't re-run.
        _mark_done(build_id)
        _log('Migrated legacy done marker for build %s.' % build_id)
        return False, build_id
    return True, build_id


def _mark_done(build_id=None):
    """Write DONE_FILE with the completed build id (repeat guard)."""
    if build_id is None:
        build_id = _read_text(BUILD_ID_FILE) or 'done'
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(DONE_FILE, 'w', encoding='utf-8') as f:
            f.write(build_id)
    except OSError as e:
        _log('Could not write done marker (%s) — first-run may re-arm on '
             'next boot.' % e, xbmc.LOGWARNING)


def _record_build(build_id):
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(LAST_BUILD_FILE, 'w', encoding='utf-8') as f:
            f.write(build_id)
        _log('Recorded build id: %s' % build_id)
    except Exception as e:
        _log('Could not record build id: %s' % e)



# autostart.sh restore cleanup:
#
# backup_manager.py writes a one-shot block into /storage/.config/autostart.sh
# to restore guisettings.xml/oe_settings.xml on the next boot (Kodi can't
# write those itself mid-session — Kodi and CoreELEC's settings service both
# hold their own copies in memory and flush them back over any external edit).
#
# autostart.sh used to try to remove that block from itself via `sed -i`
# once it had run. That is unsafe: autostart.sh runs as a shell script, and
# rewriting the very file a shell is still reading from, from inside that
# same running script, is undefined territory on BusyBox ash (the shell used
# by CoreELEC) — it corrupted/deleted the file outright in practice.
#
# The safe fix: autostart.sh no longer touches itself at all. Cleanup happens
# here instead, in a completely different, later-starting process. By the
# time this Python code runs, autostart.sh (a boot-time init script) has
# already executed to completion and exited — it is not "the same running
# script" from Kodi's point of view, so deleting it here carries none of that
# risk. If it's present when Kodi starts, its one-shot job for this boot is
# already done, so it's always safe and correct to remove it now.
AUTOSTART_PATH   = '/storage/.config/autostart.sh'
AUTOSTART_MARKER = '# [abukarimtools] guisettings restore'


def _cleanup_stale_autostart():
    if not os.path.exists(AUTOSTART_PATH):
        return
    try:
        # errors='replace': the pre-1.7.3 sed self-edit bug could leave
        # autostart.sh with corrupted (non-UTF-8) bytes. A strict read then
        # raises UnicodeDecodeError — which is NOT an OSError — and before
        # this fix that exception escaped, killed the whole service process,
        # and the build.id first-run trigger further down in main() never
        # ran at all ("first run sometimes does not auto start").
        with open(AUTOSTART_PATH, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        _log('Could not read %s for cleanup: %s' % (AUTOSTART_PATH, e))
        return

    if AUTOSTART_MARKER not in content:
        # Present but not ours — leave it alone.
        return

    try:
        os.remove(AUTOSTART_PATH)
        _log('Removed one-shot %s after restore (safe: this runs from a '
             'separate process, after the script itself already finished '
             'executing).' % AUTOSTART_PATH)
    except OSError as e:
        _log('Could not remove %s: %s' % (AUTOSTART_PATH, e),
             xbmc.LOGWARNING)


def _recommend_restart_if_updated(monitor):
    """Recommend a restart once when THIS add-on was updated in place.

    Kodi registers the new add-on folder on its mid-session rescan but does NOT
    launch the newly-registered xbmc.service until a restart, so the auto-patch
    watchdog (started only from this service) stays dormant until the next
    reboot. We used to force that reboot; now we only RECOMMEND it (a dialog the
    user can decline). If they decline, the new service/watchdog simply start on
    the next normal boot instead — nothing is lost, and repo linking is
    re-applied on every boot by the origin-fix chore in main().

    One-shot and loop-safe: the stamp is rewritten to the CURRENT version
    *before* we prompt, so the recommendation appears exactly once per version
    bump. The very first run (no stamp yet — fresh install/build) is skipped.
    """
    stamp   = os.path.join(PROFILE, 'service_version.stamp')
    current = ''
    try:
        current = _paths.version() or ''
    except Exception:
        return
    if not current:
        return

    last = _read_text(stamp)
    if last == current:
        return

    # Write the new stamp FIRST. If we cannot persist it, do not prompt —
    # an un-stamped prompt would reappear on every boot.
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(stamp, 'w', encoding='utf-8') as f:
            f.write(current)
    except OSError as e:
        _log('Could not write service version stamp (%s) — skipping the '
             'post-update restart recommendation to avoid repeating it every '
             'boot.' % e, xbmc.LOGWARNING)
        return

    if not last:
        _log('First service run for version %s — stamped, no recommendation '
             '(fresh install/build).' % current)
        return

    _log('Tools updated %s -> %s; recommending a restart (not forced) so the '
         'new service and auto-patch watchdog start.' % (last, current))
    # Let the UI settle a moment before showing the dialog.
    if monitor.waitForAbort(3):
        return
    try:
        from resources.lib import origin_fix
        origin_fix.recommend_restart(
            message=('ABUKARIM TOOLS were updated to %s.\n'
                     'A restart is recommended to finish applying the update '
                     'and start the auto-patch service.\n'
                     'تم تحديث أدوات أبوكريم إلى %s.\n'
                     'يُنصح بإعادة التشغيل لإكمال تطبيق التحديث وتشغيل خدمة '
                     'الترقيع التلقائي.' % (current, current)))
    except Exception:
        _log('Post-update restart recommendation crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)


def _relink_after_rebuild(monitor):
    from resources.lib import addons33_rebuild, origin_fix
    pending = addons33_rebuild.relink_pending()
    if not pending and not origin_fix.repo_cache_empty():
        # 3.1.11: still refresh+retry when something is linked only to an
        # out-of-date listing (or not at all) - cheap check first.
        quick = origin_fix.fix_addons(None)
        if not quick.get('stale'):
            return
    if addons33_rebuild._read_step() == '2':
        return                      # phase 2 still to run; it reboots anyway
    origins = addons33_rebuild.read_origins() if pending else None
    _log('Relinking add-ons to their repositories (%s).'
         % ('after rebuild' if pending else 'repo cache empty'))
    res = origin_fix.relink_with_repo_refresh(monitor, origins)
    if pending:
        addons33_rebuild.clear_origins()
    n = len(res['fixed'])
    if n:
        _log('Relinked %d add-on(s): %s' % (n, ', '.join(sorted(res['fixed']))))
        try:
            xbmcgui.Dialog().notification(
                'ABUKARIM TOOLS', T(30337) % n,
                xbmcgui.NOTIFICATION_INFO, 8000)
        except Exception:
            pass


SERVICE_PROP = 'abukarimtools.service.alive'
_OWNS_HEARTBEAT = False


def _start_update_watch(monitor, boot_version):
    import threading

    def loop():
        stamp = os.path.join(PROFILE, 'service_version.stamp')
        while not monitor.waitForAbort(20):
            cur = _paths.version(fresh=True)
            if not cur or cur == '?' or cur == boot_version:
                continue
            # wait for a quiet moment: no playback, no dialog
            while not monitor.abortRequested() and (
                    xbmc.getCondVisibility('Player.HasMedia')
                    or xbmc.getCondVisibility('System.HasModalDialog')):
                if monitor.waitForAbort(5):
                    return
            try:
                os.makedirs(PROFILE, exist_ok=True)
                with open(stamp, 'w', encoding='utf-8') as f:
                    f.write(cur)              # the next boot won't ask again
            except OSError:
                pass
            _log('Tools updated %s -> %s while running; recommending a restart.'
                 % (boot_version, cur))
            try:
                from resources.lib import origin_fix
                origin_fix.recommend_restart(
                    message=('ABUKARIM TOOLS were updated to %s.\n'
                             'Restart now to finish the update and start the '
                             'new auto-patch service.\n'
                             'تم تحديث أدوات أبوكريم إلى %s.\n'
                             'أعد التشغيل الآن لإكمال التحديث وتشغيل خدمة '
                             'الترقيع التلقائي الجديدة.' % (cur, cur)))
            except Exception:
                _log('Live-update restart prompt crashed:\n%s'
                     % traceback.format_exc(), xbmc.LOGERROR)
            return

    t = threading.Thread(target=loop, name='abk-update-watch')
    t.daemon = True
    t.start()


def main():
    monitor = xbmc.Monitor()

    # 3.1.10: prove in the log that the service launched (on the AM9 it
    # silently never started on some boots), and publish a heartbeat that the
    # menu checks - if it is missing the menu starts this file via RunScript.
    # The property also stops a second copy from running in the same session.
    global _OWNS_HEARTBEAT
    home = xbmcgui.Window(10000)
    # 3.2.16: after an in-place update Kodi may start the new service while the
    # old copy is still shutting down - give it 15 s to clear its heartbeat.
    for _ in range(15):
        if not home.getProperty(SERVICE_PROP):
            break
        if monitor.waitForAbort(1):
            return
    if home.getProperty(SERVICE_PROP):
        _log('Service already running (%s) - this copy exits.'
             % home.getProperty(SERVICE_PROP))
        return
    _OWNS_HEARTBEAT = True
    try:
        ver = _paths.version()
    except Exception:
        ver = '?'
    started_by = 'menu' if home.getProperty(SERVICE_PROP + '.kick') else 'boot'
    home.setProperty(SERVICE_PROP, '%s/%s' % (ver, started_by))
    xbmc.log('[AbukarimTools Service] started v%s (%s)' % (ver, started_by),
             xbmc.LOGINFO)

    # 3.2.16: prompt for the restart the moment this add-on is updated while
    # Kodi runs (not only at the next boot). Fenced.
    try:
        _start_update_watch(monitor, ver)
    except Exception:
        _log('Update watch failed to start (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # 3.2.13: reopen Home if a skin reload (active-skin update) leaves Kodi
    # with no window at all - black screen that looks like a freeze. Fenced.
    try:
        from resources.lib import window_rescue
        window_rescue.start(monitor)
    except Exception:
        _log('Window rescue failed to start (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Finish an in-progress Addons33 rebuild first (phase 2): if the add-on
    # DB was just deleted and Kodi has rebuilt a clean one, re-enable every
    # add-on and restart. This reboots when it fires, so it runs before the
    # other boot chores. Fully fenced; no-op unless a rebuild is pending.
    try:
        from resources.lib import addons33_rebuild
        addons33_rebuild.continue_if_pending(monitor)
    except Exception:
        _log('Addons33 rebuild continuation crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Recommend (never force) a restart if this add-on was just updated in
    # place, so Kodi starts the freshly-registered service (and its watchdog)
    # once the user agrees; otherwise they start on the next normal boot.
    # Fenced; no longer reboots, so ordering no longer matters, but kept here.
    try:
        _recommend_restart_if_updated(monitor)
    except Exception:
        _log('Post-update restart check crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # The boot chore below is strictly best-effort: it is not allowed to
    # prevent the first-run trigger further down from being evaluated. It is
    # fenced so an unexpected exception is logged and skipped rather than
    # killing the service process.

    # Runs on every boot, unconditionally: autostart.sh's job (if it ran at
    # all this boot) is already finished by the time Kodi is up.
    try:
        _cleanup_stale_autostart()
    except Exception:
        _log('autostart cleanup crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Runs on every boot: re-apply repository linking (installed.origin) for
    # any add-on that has an empty origin — skins/companions installed from the
    # portal or a zip. This is the "do the necessary linking after a restart"
    # safety net: because we no longer FORCE a reboot after a portal install or
    # a tools update, this guarantees the linking is in place on whatever boot
    # actually happens next. Idempotent (only touches empty origins) and fully
    # fenced. No-op when everything is already linked.
    try:
        from resources.lib import origin_fix
        res = origin_fix.fix_addons(None)
        if res.get('fixed'):
            _log('Repo linking applied on boot for: %s'
                 % ', '.join(sorted(res['fixed'])))
    except Exception:
        _log('Boot-time repo linking crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Make Arabic readable in every skin (including plugin directory listings
    # this add-on can't otherwise control) by installing an Arabic-capable
    # global fallback font. Best-effort and fully fenced, like the chore above.
    try:
        from resources.lib import font_fallback
        font_fallback.install()
    except Exception:
        _log('Fallback font install crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Force Kodi's UI language to English while first-run setup is still
    # pending, so the setup dialogs (and Kodi's own core dialogs) are readable
    # under a skin whose font lacks Arabic glyphs. Once first-run has completed
    # (_run_steps hands the box back to Arabic at the end), we must NOT keep
    # flipping it back to English on every boot — so this is gated on first-run
    # still being pending. Only switches away from Arabic; a deliberately-chosen
    # non-English language is left alone. Best-effort and fully fenced.
    # Only relevant while auto first-run is active — it makes the auto setup
    # dialogs readable. With AUTO_FIRST_RUN off we never touch the UI language
    # on boot (manual setup handles its own English/Arabic switch in _run_steps).
    try:
        if AUTO_FIRST_RUN and not os.path.exists(DONE_FILE):
            from resources.lib import set_language
            set_language.force_english(only_if_arabic=True)
    except Exception:
        _log('UI language switch crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # Self-trigger: arm first-run whenever the shipped build.id has no
    # matching COMPLETED marker (DONE_FILE). This covers both a fresh build
    # apply and a previous run that was interrupted (crash / power-cycle)
    # before it could finish — the old last_build.id comparison covered only
    # the former. Manual first_run.flag still works as before.
    pending, build_id = _first_run_pending() if AUTO_FIRST_RUN else (False, '')
    if pending:
        _log('First-run pending for build %s — arming.' % build_id)
        for stale in (DONE_FILE, LOCK_FILE):
            try:
                if os.path.exists(stale):
                    os.remove(stale)
            except Exception as e:
                _log('Could not clear %s: %s' % (stale, e))
        try:
            os.makedirs(PROFILE, exist_ok=True)
            open(FLAG_FILE, 'w').close()
        except Exception as e:
            _log('Could not create first-run flag: %s' % e)
        # Kept for logging/diagnostics only — completion is tracked in
        # DONE_FILE now, not here.
        _record_build(build_id)

    if AUTO_FIRST_RUN and os.path.exists(FLAG_FILE):
        _log('First-run flag detected: %s' % FLAG_FILE)
        run_first_run_sequence(monitor)
    elif os.path.exists(FLAG_FILE):
        # Auto first-run is disabled: a stale flag (shipped in the build's
        # userdata, or left by an older version) must NOT start setup on boot.
        # Clear it so it can't fire later either. Manual setup is unaffected.
        _log('Auto first-run disabled — ignoring and clearing stale flag: %s'
             % FLAG_FILE)
        try:
            os.remove(FLAG_FILE)
        except OSError:
            pass

    # AF3 auto-trailers (3.1.16): their engine runs on its own thread for the
    # rest of the session and idles until turned on from Toggles. Started
    # before the boot repo-linking/watchdog so it never waits on them. Fenced.
    try:
        from resources.lib.af3_trailers import engine as trailers_engine
        trailers_engine.start(monitor)
    except Exception:
        _log('AF3 auto-trailers failed to start (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # After an Addons33 rebuild (or whenever the repo listing cache is still
    # empty) the plain boot linking above cannot match anything: restore the
    # phase-1 origin snapshot and refresh the repositories, retrying for up to
    # 3 minutes. Runs before the watchdog; only on those boots. Fenced.
    # 3.2.17: in the background - with an empty repo cache this retries for
    # up to 3 minutes and used to hold the auto-patch watchdog back that long
    # (log 2026-10-04 12:15:38 -> 12:18:45).
    def _relink_bg():
        try:
            _relink_after_rebuild(monitor)
        except Exception:
            _log('Post-rebuild repo linking crashed (ignored):\n%s'
                 % traceback.format_exc(), xbmc.LOGERROR)
    import threading
    _t = threading.Thread(target=_relink_bg, name='abk-relink')
    _t.daemon = True
    _t.start()

    # 3.2: hide menu items / widgets whose add-on is missing (and bring back
    # ones whose add-on was installed since). No network, content-compared.
    try:
        from resources.lib import menu_reconcile
        menu_reconcile.run(rebuild=True)
    except Exception:
        _log('Menu reconcile crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # 3.2: pull patches.json / portal.json / presets.json / config.json from
    # the Piers repo (at most every 6 h, short timeouts). Everything that uses
    # them reads the cache only, so an offline boot just keeps the old copy.
    try:
        if not monitor.waitForAbort(5):
            from resources.lib import remote_config
            remote_config.refresh()
            remote_config.boot_notices()
    except Exception:
        _log('Remote config refresh crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)

    # From here the service stays alive for the rest of the Kodi session and
    # watches the patch targets: a Kodi add-on update replaces the add-on
    # folder wholesale, which silently wipes every patch we applied to it.
    # The watchdog notices and puts them straight back. Fenced so a fault in
    # it can never take the service (and therefore first-run) down with it.
    try:
        from resources.lib import patch_watchdog
        patch_watchdog.watch(monitor)
    except Exception:
        _log('Auto-patch watchdog crashed (ignored):\n%s'
             % traceback.format_exc(), xbmc.LOGERROR)


if __name__ == '__main__':
    try:
        main()
    finally:
        # 3.2.16: free the heartbeat when this copy stops (add-on update /
        # shutdown) so the next copy is not turned away as a duplicate
        if _OWNS_HEARTBEAT:
            try:
                xbmcgui.Window(10000).clearProperty(SERVICE_PROP)
            except Exception:
                pass
