import os
import shutil
import zipfile

from resources.lib.i18n import T
import datetime

import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_NAME = ADDON.getAddonInfo('name')

# guisettings.xml cannot be overwritten while Kodi is running — Kodi holds it
# in memory and flushes it on exit, clobbering anything we write mid-session.
# oe_settings.xml (CoreELEC's own settings service) behaves the same way —
# service.coreelec.settings periodically re-syncs its own remembered values
# (e.g. audiooutput.audiodevice) back over guisettings.xml, so restoring
# guisettings.xml alone doesn't stick if oe_settings.xml still holds the old
# value; it gets pushed straight back on the next sync.
# Instead we stage both files here; autostart.sh copies them into place
# before Kodi/CoreELEC's settings service starts on the next boot.
GUISETTINGS_STAGING  = '/storage/.guisettings_pending.xml'
OE_SETTINGS_STAGING  = '/storage/.oe_settings_pending.xml'
OE_SETTINGS_DEST     = ('/storage/.kodi/userdata/addon_data/'
                         'service.coreelec.settings/oe_settings.xml')
OE_SETTINGS_MEMBER   = 'addon_data/service.coreelec.settings/oe_settings.xml'
AUTOSTART_PATH      = '/storage/.config/autostart.sh'
AUTOSTART_MARKER    = '# [abukarimtools] guisettings restore'

# ─── Exclusion rules ──────────────────────────────────────────────────────────
#
#  Addons that are excluded by default but can be opted-in per run via the
#  "Include skin data?" prompt shown before each backup / restore:
SKIN_ADDONS = [
    'script.skinshortcuts',
    'script.skinvariables',
]

#  Addons whose addon_data is ALWAYS excluded from backups/restores.
#  These hold machine-/build-specific state that should not travel between
#  installs (e.g. the ABUKARIM build wizard's firstrun flag). ABUKARIM TOOLS'
#  own folder is excluded whole since 3.1.0.16 - first-run lifecycle files,
#  patch toggles, sentinels and everything else stay with the box.
EXCLUDED_ADDONS = [
    'plugin.program.ABUKARIMwizard',
    'plugin.program.abukarimtools',
]

#  Partial exclusion: for these addons only specific files are KEPT;
#  everything else inside their folder is skipped.
#  Format:  { addon_id: set_of_filenames_to_keep }
PARTIAL_ADDONS = {
    'plugin.video.themoviedb.helper': {'settings.xml'},
}

#  Partial SKIP: for these addons EVERYTHING is kept EXCEPT these filenames.
#  Format:  { addon_id: set_of_filenames_to_skip }
#  (plugin.program.abukarimtools used to be here for its first-run files; it is
#  now fully excluded via EXCLUDED_ADDONS, which covers those files too.)
SKIP_FILES = {}
# ─────────────────────────────────────────────────────────────────────────────


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[plugin.program.abukarim] %s' % msg, level)


class BackupManager:

    def __init__(self):
        self.userdata_path   = xbmcvfs.translatePath('special://userdata/')
        self.addon_data_path = xbmcvfs.translatePath('special://userdata/addon_data/')
        self.home_path       = xbmcvfs.translatePath('special://home/')

    # ------------------------------------------------------------------ UI ---

    def run(self):
        choices = ['Backup', 'Restore', 'Cancel']
        dialog  = xbmcgui.Dialog()
        idx     = dialog.select('%s – Main Menu' % ADDON_NAME, choices)

        # 3.2.9: no "Include my customisations?" question any more - menus and
        # widgets (skinshortcuts + skinvariables) are always part of a backup
        # and always restored when the backup contains them.
        include_skin = set(SKIN_ADDONS)
        if idx == 0:
            self._do_backup(dialog, include_skin)
        elif idx == 1:
            self._do_restore(dialog, include_skin)

    # --------------------------------------------------------------- Backup --

    def _do_backup(self, dialog, include_skin):
        # Ask where to save
        dest_folder = dialog.browse(
            3, 'Choose backup destination folder', 'files', '', False, False,
            self.home_path
        )
        if not dest_folder:
            return

        timestamp   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_name    = 'kodi_userdata_backup_%s.zip' % timestamp
        zip_path    = os.path.join(dest_folder, zip_name)

        pbar = xbmcgui.DialogProgress()
        pbar.create(ADDON_NAME, T(30220))

        try:
            file_list = self._collect_files(include_skin)
            total     = len(file_list)

            if total == 0:
                pbar.close()
                dialog.ok(ADDON_NAME, T(30221))
                return

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, (abs_path, arc_name) in enumerate(file_list):
                    if pbar.iscanceled():
                        break
                    pct = int((i + 1) / total * 100)
                    pbar.update(pct, 'Backing up… (%d / %d)\n%s' % (i + 1, total, arc_name))
                    try:
                        with open(abs_path, 'rb') as f:
                            zf.writestr(arc_name, f.read())
                    except Exception as e:
                        _log('Could not add %s: %s' % (abs_path, e),
                             xbmc.LOGWARNING)

            pbar.close()

            if pbar.iscanceled():
                # Remove incomplete zip
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
                dialog.ok(ADDON_NAME, T(30222))
            else:
                _log('Backup written to: %s' % zip_path)
                dialog.ok(ADDON_NAME, T(30223) % (total, zip_path))
                if (SKIN_ADDONS[0] in include_skin
                        and SKIN_ADDONS[1] in include_skin):
                    _log('Both skin addons included – triggering rebuild_shortcuts.')
                    xbmc.executebuiltin(
                        'AlarmClock(rebuild_shortcuts,'
                        'RunScript(script.skinvariables,'
                        'run_executebuiltin=special://skin/shortcuts/'
                        'skinvariables-build-templates.json,use_rules),'
                        '00:01,silent)'
                    )

        except Exception as e:
            pbar.close()
            _log('Backup error: %s' % e, xbmc.LOGERROR)
            dialog.ok(ADDON_NAME, T(30224) % e)

    # -------------------------------------------------------------- Restore --

    def _do_restore(self, dialog, include_skin):
        zip_path = dialog.browse(
            1, T(30225), 'files', '*.zip', False, False,
            self.home_path
        )
        if not zip_path or not zip_path.lower().endswith('.zip'):
            return

        if not dialog.yesno(ADDON_NAME, T(30231)):
            return

        pbar = xbmcgui.DialogProgress()
        pbar.create(ADDON_NAME, T(30226))

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                members = zf.namelist()
                total   = len(members)

                for i, member in enumerate(members):
                    if pbar.iscanceled():
                        break

                    # Skip pure directory entries
                    if member.endswith('/'):
                        continue

                    # Normalise separators so Windows-created zips work on Linux
                    norm_member = member.replace('\\', '/').lstrip('/')

                    # Skip skin addon data unless the user opted in
                    member_parts = norm_member.split('/')
                    if (len(member_parts) >= 2
                            and member_parts[0] == 'addon_data'
                            and member_parts[1] in SKIN_ADDONS
                            and member_parts[1] not in include_skin):
                        continue

                    # Skip always-excluded addons (e.g. the ABUKARIM wizard's
                    # first-run state) even if an older backup still contains
                    # them, so machine-specific setup data isn't carried over.
                    if (len(member_parts) >= 2
                            and member_parts[0] == 'addon_data'
                            and member_parts[1] in EXCLUDED_ADDONS):
                        continue

                    # Skip machine-/build-specific first-run lifecycle files
                    # but keep the rest of the addon's data (e.g. patch
                    # toggles). Restoring these re-imports another box's setup
                    # state and makes first-run re-fire on the next boot after
                    # a restore.
                    if (len(member_parts) >= 3
                            and member_parts[0] == 'addon_data'
                            and member_parts[1] in SKIP_FILES
                            and member_parts[-1] in SKIP_FILES[member_parts[1]]):
                        _log('Skipping first-run state file: %s' % norm_member)
                        continue

                    # guisettings.xml must be staged — writing it while Kodi
                    # is running has no effect because Kodi overwrites it on exit.
                    if norm_member == 'guisettings.xml':
                        try:
                            data = zf.read(member)
                            with open(GUISETTINGS_STAGING, 'wb') as fh:
                                fh.write(data)
                            self._inject_autostart_restore()
                            _log('guisettings.xml staged at %s' % GUISETTINGS_STAGING)
                        except Exception as e:
                            _log('Could not stage guisettings.xml: %s' % e,
                                 xbmc.LOGWARNING)
                        continue

                    # Same reasoning as guisettings.xml above — CoreELEC's own
                    # settings service re-syncs this file's values back over
                    # guisettings.xml during the session, so it needs the same
                    # stage-and-restore-on-boot treatment or the fix doesn't stick.
                    if norm_member == OE_SETTINGS_MEMBER:
                        try:
                            data = zf.read(member)
                            with open(OE_SETTINGS_STAGING, 'wb') as fh:
                                fh.write(data)
                            self._inject_autostart_restore()
                            _log('oe_settings.xml staged at %s' % OE_SETTINGS_STAGING)
                        except Exception as e:
                            _log('Could not stage oe_settings.xml: %s' % e,
                                 xbmc.LOGWARNING)
                        continue

                    dest     = os.path.join(self.userdata_path,
                                            *norm_member.split('/'))
                    dest_dir = os.path.dirname(dest)

                    try:
                        os.makedirs(dest_dir, exist_ok=True)
                        data = zf.read(member)
                        with open(dest, 'wb') as fh:
                            fh.write(data)
                    except Exception as e:
                        _log('Could not restore %s: %s' % (member, e),
                             xbmc.LOGWARNING)

            pbar.close()

            if pbar.iscanceled():
                dialog.ok(ADDON_NAME, T(30227))
            else:
                _log('Restore completed from: %s' % zip_path)
                dialog.ok(ADDON_NAME, T(30228) % total)
                if (SKIN_ADDONS[0] in include_skin
                        and SKIN_ADDONS[1] in include_skin):
                    _log('Both skin addons restored – running rebuild_shortcuts.')
                    xbmc.executebuiltin(
                        'RunScript(script.skinvariables,'
                        'run_executebuiltin=special://skin/shortcuts/'
                        'skinvariables-build-templates.json,use_rules)'
                    )

        except Exception as e:
            pbar.close()
            _log('Restore error: %s' % e, xbmc.LOGERROR)
            dialog.ok(ADDON_NAME, T(30229) % e)

    # ------------------------------------------------- autostart.sh injection -

    def _inject_autostart_restore(self):
        """
        Append a one-shot restore block to autostart.sh that copies staged
        guisettings.xml / oe_settings.xml into place before Kodi and
        CoreELEC's settings service start on the next boot.

        This block does NOT remove itself. An earlier version tried to via
        `sed -i` on autostart.sh from inside autostart.sh while it was still
        executing — rewriting a running shell script's own file mid-read is
        unsafe on BusyBox ash and corrupted/deleted the file in practice.
        Cleanup instead happens from service.py, in a separate process that
        only runs after this script has already finished and exited — see
        _cleanup_stale_autostart() there for the reasoning.

        Does nothing if the block is already present (idempotent — may be
        called once for guisettings.xml and again for oe_settings.xml in the
        same restore; the `if [ -f ... ]` guards make re-running harmless
        even so).
        """
        block = (
            '\n%(marker)s\n'
            'if [ -f "%(gui_staging)s" ]; then\n'
            '    cp "%(gui_staging)s" /storage/.kodi/userdata/guisettings.xml\n'
            '    rm -f "%(gui_staging)s"\n'
            'fi\n'
            'if [ -f "%(oe_staging)s" ]; then\n'
            '    cp "%(oe_staging)s" "%(oe_dest)s"\n'
            '    rm -f "%(oe_staging)s"\n'
            'fi\n'
        ) % {
            'marker':      AUTOSTART_MARKER,
            'gui_staging': GUISETTINGS_STAGING,
            'oe_staging':  OE_SETTINGS_STAGING,
            'oe_dest':     OE_SETTINGS_DEST,
        }

        # Read existing content (file may not exist yet)
        try:
            with open(AUTOSTART_PATH, 'r') as f:
                content = f.read()
        except IOError:
            content = '#!/bin/sh\n'

        if AUTOSTART_MARKER in content:
            _log('autostart.sh already contains restore block, skipping inject.')
            return

        os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
        with open(AUTOSTART_PATH, 'w') as f:
            f.write(content.rstrip('\n') + block)

        _log('Injected guisettings/oe_settings restore block into %s' % AUTOSTART_PATH)

    # -------------------------------------------------------- File collection -

    def _collect_files(self, include_skin):
        """
        Walk userdata and return list of (absolute_path, archive_name) tuples.

        Included:
          • userdata/addon_data/**  – with per-addon exclusion rules
          • userdata/guisettings.xml
          • userdata/keymaps/**

        All archive names are relative to userdata/ so restore can place
        every file back at the correct path under special://userdata/.
        """
        collected = []

        # ── guisettings.xml ───────────────────────────────────────────────────
        guisettings = os.path.join(self.userdata_path, 'guisettings.xml')
        if os.path.isfile(guisettings):
            arc_name = 'guisettings.xml'
            collected.append((guisettings, arc_name))
            _log('Including guisettings.xml')
        else:
            _log('guisettings.xml not found, skipping.', xbmc.LOGWARNING)

        # ── keymaps/ ──────────────────────────────────────────────────────────
        keymaps_dir = os.path.join(self.userdata_path, 'keymaps')
        if os.path.isdir(keymaps_dir):
            for root, dirs, files in os.walk(keymaps_dir):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    rel      = os.path.relpath(abs_path, self.userdata_path)
                    arc_name = rel.replace('\\', '/')
                    collected.append((abs_path, arc_name))
            _log('Included keymaps/ directory.')
        else:
            _log('keymaps/ directory not found, skipping.', xbmc.LOGWARNING)

        # ── addon_data/ ───────────────────────────────────────────────────────
        if not os.path.isdir(self.addon_data_path):
            _log('addon_data path not found: %s' % self.addon_data_path,
                 xbmc.LOGWARNING)
            _log('Collected %d files for backup.' % len(collected))
            return collected

        for addon_id in os.listdir(self.addon_data_path):
            addon_dir = os.path.join(self.addon_data_path, addon_id)

            if not os.path.isdir(addon_dir):
                continue

            # ── Skin addons – include only if user opted in ───────────────
            if addon_id in SKIN_ADDONS and addon_id not in include_skin:
                _log('Skipping (skin addon, not opted in): %s' % addon_id)
                continue

            # ── Always-excluded addons ────────────────────────────────────
            if addon_id in EXCLUDED_ADDONS:
                _log('Skipping (always excluded): %s' % addon_id)
                continue

            # ── Partially excluded addons ─────────────────────────────────
            if addon_id in PARTIAL_ADDONS:
                allowed = PARTIAL_ADDONS[addon_id]
                _log('Partially including %s (keeping: %s)'
                     % (addon_id, ', '.join(allowed)))
                for root, dirs, files in os.walk(addon_dir):
                    for fname in files:
                        if fname in allowed:
                            abs_path = os.path.join(root, fname)
                            rel      = os.path.relpath(abs_path, self.userdata_path)
                            arc_name = rel.replace('\\', '/')
                            collected.append((abs_path, arc_name))
                continue

            # ── Skip-list addons – include everything EXCEPT named files ───
            if addon_id in SKIP_FILES:
                skip = SKIP_FILES[addon_id]
                _log('Including %s (skipping first-run state: %s)'
                     % (addon_id, ', '.join(sorted(skip))))
                for root, dirs, files in os.walk(addon_dir):
                    for fname in files:
                        if fname in skip:
                            continue
                        abs_path = os.path.join(root, fname)
                        rel      = os.path.relpath(abs_path, self.userdata_path)
                        arc_name = rel.replace('\\', '/')
                        collected.append((abs_path, arc_name))
                continue

            # ── Normal addon – include everything ─────────────────────────
            for root, dirs, files in os.walk(addon_dir):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    rel      = os.path.relpath(abs_path, self.userdata_path)
                    arc_name = rel.replace('\\', '/')
                    collected.append((abs_path, arc_name))

        _log('Collected %d files for backup.' % len(collected))
        return collected
