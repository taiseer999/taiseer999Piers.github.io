# -*- coding: utf-8 -*-
"""
Skin Installer – fetches skins.json from remote and downloads/installs skins.
Adapted from script.portal.
"""

import os
import shutil
import tempfile
import zipfile
import urllib.request
import urllib.error
import json

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

import xbmcaddon as _xbmcaddon
ADDON_PATH    = xbmcvfs.translatePath(_xbmcaddon.Addon('plugin.program.abukarimtools').getAddonInfo('path'))
if not ADDON_PATH.endswith(os.sep):
    ADDON_PATH += os.sep
PACKAGES_PATH = xbmcvfs.translatePath('special://home/addons/packages/')
ADDONS_PATH   = xbmcvfs.translatePath('special://home/addons/')

KODI_JSON  = ('https://raw.githubusercontent.com/taiseer999/'
              'taiseer999.github.io/master/skins.json')
CE_JSON    = ('https://raw.githubusercontent.com/taiseer999/'
              'taiseer999ce.github.io/master/skins.json')
PIERS_JSON = ('https://raw.githubusercontent.com/taiseer999/'
              'taiseer999Piers.github.io/master/skins.json')

# Each skins.json source maps to the repository add-on id that carries its
# skins. The origin column is written deterministically from this so a portal
# install links to its repo (and thus receives updates) even when the repo's
# listing was never cached into the Addons DB.
_REPO_ID_FOR_JSON = {
    KODI_JSON:  'repository.taiseer',
    CE_JSON:    'repository.taiseerCE',
    PIERS_JSON: 'repository.taiseerKODI22',
}

TITLE = 'ABUKARIM – Skin Installer'


# ---------------------------------------------------------------------------
# Companion add-ons: when a given skin is installed, silently pull one or more
# companion add-ons from the SAME repo (same repo/zips/<id>/ path) with no
# prompt and without switching skins. Each companion's current version is read
# from its own addon.xml in the repo, so the versioned zip name resolves
# automatically without hardcoding it here.
# ---------------------------------------------------------------------------
_SKIN_COMPANIONS = {
    'skin.arctic.fuse.3': ['plugin.video.themoviedb.helper'],
}


def _notify(msg, icon=xbmcgui.NOTIFICATION_INFO, ms=3000):
    xbmcgui.Dialog().notification(TITLE, msg, icon, ms)


def _log(msg):
    xbmc.log('[AbukarimTools SkinInstaller] %s' % msg, xbmc.LOGINFO)


def _error(msg):
    xbmcgui.Dialog().ok(TITLE, msg)


def _merge_tree(src, dest):
    """Overwrite dest with src's contents in place, without requiring dest to
    be empty or removable.

    os.rename onto an existing non-empty dir raises ENOTEMPTY (Errno 66), and
    rmtree can't clear a directory whose files Kodi holds open (the active
    skin) -- on macOS the unlink fails mid-walk, leaving residue that then
    blocks the rename. So instead of replacing the top folder, recurse and
    overwrite each file individually: open files can still be rewritten in
    place, so a live skin updates cleanly.
    """
    if os.path.isdir(src):
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(src):
            _merge_tree(os.path.join(src, name), os.path.join(dest, name))
    else:
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copy2(src, dest)


def _fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Kodi'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _skin_installed(addonid):
    return xbmcvfs.exists(os.path.join(ADDONS_PATH, addonid, ''))


_REPO_ENTRIES = [
    ('Kodi 21.3 Repository',              'repo_kodi.png',     KODI_JSON,  'backgroundkodi.jpg'),
    ('CoreELEC 21.3 "NG" Repository',     'repo_coreelec.png', CE_JSON,    'backgroundcoreelec.jpg'),
    ('Piers and Kodi 22 "NO" Repository', 'repo_piers.png',    PIERS_JSON, 'backgroundpiers.jpg'),
]


class _RepoSelectDialog(xbmcgui.WindowXMLDialog):
    """Custom dialog that shows icon + label for each repository option."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._result = [-1]   # mutable so GUI thread writes, caller reads after doModal

    def onInit(self):
        try:
            media_base = ('special://home/addons/plugin.program.abukarimtools'
                          '/resources/media/')
            # Static fallback background (first repo's image) shown before the
            # list gains focus or if a per-item background can't be resolved.
            self.setProperty('background', media_base + _REPO_ENTRIES[0][3])

            panel = self.getControl(100)
            panel.reset()
            icons_path = os.path.join(ADDON_PATH, 'resources', 'icons')
            for label, icon_file, _json, bg in _REPO_ENTRIES:
                li = xbmcgui.ListItem(label)
                icon_full = os.path.join(icons_path, icon_file)
                li.setArt({'icon': icon_full, 'thumb': icon_full})
                # Per-repo background so the window photo follows the focus.
                li.setProperty('repo_bg', media_base + bg)
                panel.addItem(li)
            # Focus the list. Right after a skin reload the control can briefly
            # refuse focus ("Control 100 ... asked to focus, but it can't"),
            # which leaves the dialog visible but non-interactive. Retry a few
            # times with a short wait so focus lands once the control is ready.
            for _attempt in range(10):
                self.setFocusId(100)
                if self.getFocusId() == 100:
                    break
                xbmc.sleep(100)
            # Static labels set from Python: $LOCALIZE resolves against the
            # active skin, not this addon, so it comes back blank for our ids.
            try:
                self.getControl(9001).setLabel(T(30322))  # title
                self.getControl(9002).setLabel(T(30323))  # hint
            except Exception:
                pass
        except Exception as e:
            xbmc.log('[AbukarimTools] onInit error: %s' % str(e), xbmc.LOGERROR)

    def onClick(self, control_id):
        if control_id == 100:
            self._result[0] = self.getControl(100).getSelectedPosition()
        self.close()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_NAV_BACK,
                               xbmcgui.ACTION_PREVIOUS_MENU,
                               xbmcgui.ACTION_STOP):
            self.close()


def _choose_source():
    import time
    idx = -1
    # Closed in under 1.5 s with no pick = swallowed by a reload/rescan, not
    # the user pressing Back: reopen (3.1.0.19 first-run log showed exactly
    # this — the repo picker vanished 2 s after opening).
    for attempt in range(3):
        started = time.time()
        dlg = _RepoSelectDialog('select_repo.xml', ADDON_PATH, 'Default', '1080i')
        dlg.doModal()
        idx = dlg._result[0]
        del dlg
        if idx >= 0 or time.time() - started > 1.5:
            break
        _log('repo picker closed instantly (attempt %d) - reopening'
             % (attempt + 1))
        xbmc.sleep(1500)
    if idx < 0:
        return None, None
    _label, _icon, json_url, bg = _REPO_ENTRIES[idx]
    return json_url, bg


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _kodi_major():
    import re as _re
    m = _re.match(r'(\d+)', xbmc.getInfoLabel('System.BuildVersion') or '')
    return int(m.group(1)) if m else 22


def _platform_tags():
    tags = set()
    if os.path.isdir('/etc/coreelec') or os.path.isfile('/etc/coreelec-release'):
        tags.add('coreelec')
    for cond, tag in (('System.Platform.Android', 'android'),
                      ('System.Platform.Linux', 'linux'),
                      ('System.Platform.OSX', 'osx'),
                      ('System.Platform.Windows', 'windows'),
                      ('System.Platform.IOS', 'ios'),
                      ('System.Platform.TVOS', 'tvos')):
        try:
            if xbmc.getCondVisibility(cond):
                tags.add(tag)
        except Exception:
            pass
    return tags


def _compatible(item):
    """skins.json optional filters: min_kodi / max_kodi (major numbers) and
    platforms (any of coreelec, android, linux, osx, windows, ios, tvos)."""
    try:
        major = _kodi_major()
        if item.get('min_kodi') and major < int(item['min_kodi']):
            return False
        if item.get('max_kodi') and major > int(item['max_kodi']):
            return False
        plats = item.get('platforms')
        if plats and not (set(p.lower() for p in plats) & _platform_tags()):
            return False
    except Exception:
        return True
    return True


def _verify_zip(path, expected_bytes=None, expected_sha256=None):
    """Strict integrity check for a downloaded zip.

    is_zipfile() only proves the End-Of-Central-Directory record exists, so a
    file truncated mid-stream (dropped connection, short read, an HTML error
    page saved as .zip) can still slip through and only blow up later inside
    Kodi's CZipManager::GetZipList. This checks, in order:
      1. the file exists and is non-empty;
      2. if the server sent Content-Length, that we actually got every byte;
      3. that it is a zip at all (EOCD present);
      4. that every member's CRC is intact (testzip) — the real truncation catch.
    Returns True only if all pass.
    """
    try:
        if not path or not os.path.isfile(path):
            return False
        actual = os.path.getsize(path)
        if actual == 0:
            _log('zip verify: empty file %s' % path)
            return False
        if expected_bytes and actual != expected_bytes:
            _log('zip verify: size mismatch %s (%d of %d bytes)'
                 % (path, actual, expected_bytes))
            return False
        if not zipfile.is_zipfile(path):
            _log('zip verify: not a zip archive %s' % path)
            return False
        with zipfile.ZipFile(path, 'r') as zf:
            bad = zf.testzip()
            if bad is not None:
                _log('zip verify: CRC/truncation failure, first bad member %s' % bad)
                return False
        if expected_sha256:
            got = _sha256_file(path)
            if got.lower() != expected_sha256.lower():
                _log('zip verify: sha256 mismatch %s (got %s, want %s)'
                     % (path, got, expected_sha256))
                return False
        return True
    except Exception as e:
        _log('zip verify: exception on %s: %s' % (path, e))
        return False


def _download_zip(url, addonid, sha256=None):
    if not xbmcvfs.exists(PACKAGES_PATH):
        xbmcvfs.mkdirs(PACKAGES_PATH)

    # على Android لا توجد /tmp — نحدد المجلد صراحةً
    _tmp_dir = xbmcvfs.translatePath('special://temp/')
    os.makedirs(_tmp_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='abukarim_dl_', dir=_tmp_dir)
    progress = xbmcgui.DialogProgress()
    progress.create(TITLE, T(30100))

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Kodi'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total       = int(resp.headers.get('Content-Length', 0))
            chunk_size  = 65536
            downloaded  = 0
            with os.fdopen(tmp_fd, 'wb') as fh:
                tmp_fd = None
                while True:
                    if progress.iscanceled():
                        progress.close()
                        _notify(T(30101), xbmcgui.NOTIFICATION_WARNING)
                        return None
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        progress.update(pct, T(30102)
                                        % (downloaded // 1024, total // 1024))
                    else:
                        progress.update(0, T(30103) % (downloaded // 1024))

        progress.update(100, T(30104))
        if not _verify_zip(tmp_path, expected_bytes=(total or None),
                           expected_sha256=sha256):
            _error(T(30105))
            return None

        zip_path = os.path.join(PACKAGES_PATH, '%s.zip' % addonid)
        try:
            os.replace(tmp_path, zip_path)
        except OSError:
            shutil.copy2(tmp_path, zip_path)
            os.remove(tmp_path)
        tmp_path = None
        progress.close()
        return zip_path

    except urllib.error.URLError as e:
        progress.close()
        _error(T(30106) % e.reason)
    except Exception as e:
        progress.close()
        _error(T(30106) % e)
    finally:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return None


def _extract_zip(zip_path):
    progress = xbmcgui.DialogProgress()
    progress.create(TITLE, T(30107))
    staging_parent = os.path.join(ADDONS_PATH, '.abukarim_staging')
    staging_dir    = None

    try:
        os.makedirs(staging_parent, exist_ok=True)
        staging_dir = tempfile.mkdtemp(dir=staging_parent, prefix='extract_')

        with zipfile.ZipFile(zip_path, 'r') as zf:
            progress.update(0, T(30108))
            bad = zf.testzip()
            if bad:
                progress.close()
                _error(T(30109) % bad)
                return False

            members     = zf.infolist()
            total_bytes = sum(m.file_size for m in members) or 1
            done_bytes  = 0

            for info in members:
                if progress.iscanceled():
                    progress.close()
                    _notify(T(30110), xbmcgui.NOTIFICATION_WARNING)
                    return False
                zf.extract(info, staging_dir)
                if not info.filename.endswith('/'):
                    dest   = os.path.join(staging_dir, info.filename)
                    actual = os.path.getsize(dest) if os.path.exists(dest) else -1
                    if actual != info.file_size:
                        progress.close()
                        _error(T(30111) % info.filename)
                        return False
                done_bytes += info.file_size
                progress.update(int(done_bytes * 100 / total_bytes),
                                'Extracting: %s' % os.path.basename(info.filename))

        progress.update(99, T(30112))
        for top_name in os.listdir(staging_dir):
            src  = os.path.join(staging_dir, top_name)
            dest = os.path.join(ADDONS_PATH, top_name)
            _merge_tree(src, dest)

        progress.update(100, T(30113))
        progress.close()

    except zipfile.BadZipFile:
        progress.close()
        _error(T(30114))
        return False
    except Exception as e:
        progress.close()
        _error(T(30115) % e)
        return False
    finally:
        if staging_dir and os.path.exists(staging_dir):
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass
        try:
            if os.path.exists(staging_parent) and not os.listdir(staging_parent):
                os.rmdir(staging_parent)
        except Exception:
            pass

    try:
        xbmcvfs.delete(zip_path)
    except Exception:
        try:
            os.remove(zip_path)
        except Exception:
            pass

    xbmc.executebuiltin('UpdateLocalAddons')
    xbmc.sleep(3000)
    return True


def _addon_is_enabled(addonid):
    """True only when Kodi reports the addon as ENABLED (not just installed).

    System.HasAddon() is true even for a DISABLED addon, so relying on it let
    the skin be selected while still disabled — which is exactly what makes
    Kodi throw the 'Add-on required / enable this add-on?' popup. We query the
    real enabled flag instead.
    """
    try:
        import json as _json
        resp = xbmc.executeJSONRPC(
            '{"jsonrpc":"2.0","method":"Addons.GetAddonDetails",'
            '"params":{"addonid":"%s","properties":["enabled"]},"id":1}' % addonid)
        return _json.loads(resp).get('result', {}).get('addon', {}).get('enabled', False)
    except Exception:
        return False


def _enable_addon(addonid):
    """Enable the addon silently via JSON-RPC (synchronous).

    3.1.0.22: the EnableAddon() builtin used to be fired unconditionally as a
    "secondary path". That builtin ALWAYS shows Kodi's "Add-on required - To
    use this feature you must enable an add-on: X - Would you like to enable
    this add-on?" yes/no (strings 24076/24135/24136) - even when JSON-RPC had
    already enabled it - so every portal install left one popup per add-on
    for the user to click. Now the builtin is only a fallback when JSON-RPC
    did not take, and its prompt is answered Yes automatically.
    """
    try:
        resp = xbmc.executeJSONRPC(
            '{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled",'
            '"params":{"addonid":"%s","enabled":true},"id":1}' % addonid)
        _log('SetAddonEnabled(%s) -> %s' % (addonid, resp))
    except Exception as e:
        _log('SetAddonEnabled failed: %s' % e)

    waited = 0
    while waited < 2000:
        if _addon_is_enabled(addonid):
            return
        xbmc.sleep(200)
        waited += 200

    _log('JSON-RPC enable did not take for %s - builtin fallback '
         '(auto-confirmed)' % addonid)
    xbmc.executebuiltin('EnableAddon(%s)' % addonid)
    waited = 0
    while waited < 6000:
        if xbmc.getCondVisibility('Window.IsActive(yesnodialog)'):
            xbmc.executebuiltin('SendClick(yesnodialog, 11)')   # 11 = Yes
            _log('auto-confirmed "Add-on required" for %s' % addonid)
            xbmc.sleep(300)
        if _addon_is_enabled(addonid):
            return
        xbmc.sleep(100)
        waited += 100


def _wait_addon_enabled(addonid, timeout_ms=10000):
    """Poll until Kodi reports the addon as ENABLED, or timeout."""
    waited = 0
    step = 400
    while waited < timeout_ms:
        if _addon_is_enabled(addonid):
            return True
        xbmc.sleep(step)
        waited += step
    return _addon_is_enabled(addonid)


def _answer_enable_prompt_once():
    """If the 'Add-on required / enable this add-on?' (or a keep-skin) yes/no
    dialog is showing, answer YES immediately.

    On this dialog (confirmed from a CoreELEC/Arctic Fuse screenshot) the YES
    button is already the focused/default option, so the most reliable answer
    is simply to activate the focused control with Select — this works no
    matter which control id or screen position the skin uses for Yes. We also
    fire the common Yes control ids as a backup for skins where Yes is not the
    default focus. Returns True if a dialog was present.
    """
    if xbmc.getCondVisibility('Window.IsActive(yesnodialog)') \
            or xbmc.getCondVisibility('Window.IsActive(DialogConfirm.xml)') \
            or xbmc.getCondVisibility('Window.IsActive(10100)'):
        # YES is control 11 (NO is the focused control 10 — do NOT use
        # Action(Select), which would activate No). Click control 11 only.
        xbmc.executebuiltin('SendClick(yesnodialog, 11)')
        xbmc.sleep(60)
        xbmc.executebuiltin('SendClick(11)')
        return True
    return False


def _set_skin_setting(addonid):
    """Set the active skin via JSON-RPC (same method the Skin Switcher uses)."""
    try:
        query = ('{"jsonrpc":"2.0","method":"Settings.SetSettingValue",'
                 '"params":{"setting":"lookandfeel.skin","value":"%s"},"id":1}'
                 % addonid)
        xbmc.executeJSONRPC(query)
        return True
    except Exception as e:
        xbmc.log('[AbukarimTools] set skin setting failed: %s' % e, xbmc.LOGERROR)
        return False


def _current_skin():
    """Return the currently active skin addon id, or '' if unknown."""
    try:
        return xbmc.getSkinDir() or ''
    except Exception:
        pass
    try:
        import json as _json
        resp = xbmc.executeJSONRPC(
            '{"jsonrpc":"2.0","method":"Settings.GetSettingValue",'
            '"params":{"setting":"lookandfeel.skin"},"id":1}')
        return _json.loads(resp).get('result', {}).get('value', '') or ''
    except Exception:
        return ''


def _start_yes_watchdog():
    """Start a background thread that clicks YES on any enable/keep yes-no
    dialog for a short while. Returns a stop() callable.

    The popup fires at the exact moment the skin is set, and on CoreELEC it
    appears even when the addon already reports enabled. Watching from a
    background thread guarantees we answer it no matter which code path does
    the set (and even when the main loop short-circuits because the skin
    already reads active).
    """
    import threading

    stop_flag = {'stop': False}

    def _worker():
        waited = 0
        while not stop_flag['stop'] and waited < 15000:
            # Use the SAME detection + click that the working binary installer
            # uses: IsActive(yesnodialog) + SendClick(yesnodialog, 11).
            if xbmc.getCondVisibility('Window.IsActive(yesnodialog)') \
                    or xbmc.getCondVisibility('Window.IsActive(DialogConfirm.xml)') \
                    or xbmc.getCondVisibility('Window.IsActive(10100)'):
                xbmc.executebuiltin('SendClick(yesnodialog, 11)')   # 11 = Yes
                xbmc.sleep(60)
                xbmc.executebuiltin('SendClick(11)')
                _log('watchdog: answered enable/confirm popup (Yes)')
            xbmc.sleep(80)
            waited += 80

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()

    def _stop():
        stop_flag['stop'] = True
    return _stop



def _apply_skin(addonid, title):
    _log('apply start: %s (%s)' % (title, addonid))
    _notify(T(30116) % title)
    # Enable RELIABLY before touching the skin setting.
    _enable_addon(addonid)

    if not _wait_addon_enabled(addonid):
        _log('addon never became enabled: %s' % addonid)
        _error(T(30117) % title)
        return False
    _log('addon enabled (verified): %s' % addonid)

    # A freshly-installed skin is not immediately a valid value for
    # lookandfeel.skin — Kodi needs time to load its addon.xml into the
    # settings/addon system. Refreshing local addons and pausing lets the
    # skin become selectable before we switch.
    xbmc.executebuiltin('UpdateLocalAddons')
    xbmc.sleep(2000)

    _notify(T(30118) % title)

    # Start answering the enable/keep popup in the background BEFORE we set the
    # skin, so it's caught the instant it appears (it fires right at the set,
    # even when the addon already reports enabled — confirmed on CoreELEC).
    stop_watchdog = _start_yes_watchdog()
    try:
        from resources.lib import skin_switcher
    except Exception as e:
        _log('skin_switcher import failed: %s' % e)
        skin_switcher = None

    for attempt in range(1, 7):
        if _current_skin() == addonid:
            _log('skin active after %d attempt(s): %s' % (attempt - 1, addonid))
            break

        if skin_switcher is not None:
            skin_switcher._swap_skin(addonid)
        else:
            _set_skin_setting(addonid)
        _log('swap attempt %d: lookandfeel.skin=%s' % (attempt, addonid))

        # Safety net: for a few seconds after the swap, auto-answer YES to any
        # enable/keep popup the instant it appears, and stop as soon as the
        # skin is actually active. This is what removes the need for the user
        # to catch the 2-3s popup, and prevents the endless retry loop.
        watched = 0
        while watched < 8000:
            _answer_enable_prompt_once()
            if _current_skin() == addonid \
                    and not xbmc.getCondVisibility('Window.IsActive(yesnodialog)') \
                    and not xbmc.getCondVisibility('Window.IsActive(DialogConfirm.xml)'):
                break
            xbmc.sleep(100)
            watched += 100

        if _current_skin() == addonid:
            _log('verified active after attempt %d: %s' % (attempt, addonid))
            break
        _log('not active yet after attempt %d (current=%s)'
             % (attempt, _current_skin()))
        xbmc.sleep(1000)

    if _current_skin() != addonid:
        stop_watchdog()
        _log('FAILED to activate %s (current=%s)' % (addonid, _current_skin()))
        _error(T(30119) % title)
        return False

    stop_watchdog()
    _log('skin activated: %s' % addonid)

    # The "Keep this skin?" confirmation (yesnodialog with a ~15s revert
    # countdown) fires right as the skin becomes active — i.e. exactly when the
    # watchdog above tends to stop. Without an explicit answer the countdown
    # expires and Kodi REVERTS to the previous skin. So after activation, spend
    # a dedicated window aggressively clicking YES (control 11) until the keep
    # dialog is gone and the skin is still our target. This is the final
    # auto-confirm the user asked for.
    confirmed = 0
    while confirmed < 16000:
        if xbmc.getCondVisibility('Window.IsActive(yesnodialog)') \
                or xbmc.getCondVisibility('Window.IsActive(DialogConfirm.xml)') \
                or xbmc.getCondVisibility('Window.IsActive(10100)'):
            xbmc.executebuiltin('SendClick(yesnodialog, 11)')   # 11 = Yes/Keep
            xbmc.sleep(60)
            xbmc.executebuiltin('SendClick(11)')
            _log('keep-skin dialog auto-confirmed (Yes)')
            xbmc.sleep(400)
            # once answered and no dialog remains, we're done
            if not (xbmc.getCondVisibility('Window.IsActive(yesnodialog)')
                    or xbmc.getCondVisibility('Window.IsActive(10100)')):
                break
        xbmc.sleep(120)
        confirmed += 120

    return True


def _repo_base_from_zipurl(zipurl):
    """Derive the repo's '.../repo/zips/' base from a skin's own zip URL.

    A skins.json zip entry looks like:
      https://.../taiseer999Piers.github.io/master/repo/zips/skin.x/skin.x-1.2.3.zip
    Everything up to and including 'repo/zips/' is the shared base from which
    companion add-ons are fetched, so the companion comes from the SAME repo
    the user just selected (Piers / CE / Kodi) without hardcoding which one.
    """
    marker = '/repo/zips/'
    idx = zipurl.find(marker)
    if idx < 0:
        return None
    return zipurl[:idx + len(marker)]


def _companion_version(repo_base, addonid):
    """Read a companion add-on's current version from its addon.xml in the repo
    so the versioned zip filename can be built. Returns '' on failure."""
    url = '%s%s/addon.xml' % (repo_base, addonid)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Kodi'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode('utf-8', 'replace')
        import re
        # The <addon ...> opening tag's own version. [^>] also matches the
        # newlines Kodi addon.xml files often put between attributes, and stops
        # at the first '>', so this won't wander into a <requires> import's
        # version. Anchored on '<addon' to skip the xml prolog's version="1.0".
        m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', data)
        if m:
            return m.group(1)
    except Exception as e:
        _log('companion version lookup failed for %s: %s' % (addonid, e))
    return ''


def _download_zip_silent(url):
    """Download a zip with no progress dialog. Returns a temp path or None."""
    _tmp_dir = xbmcvfs.translatePath('special://temp/')
    os.makedirs(_tmp_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='abukarim_comp_',
                                        dir=_tmp_dir)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Kodi'})
        with urllib.request.urlopen(req, timeout=30) as resp, \
                os.fdopen(tmp_fd, 'wb') as fh:
            tmp_fd = None
            expected = int(resp.headers.get('Content-Length', 0)) or None
            shutil.copyfileobj(resp, fh, 65536)
        if not _verify_zip(tmp_path, expected_bytes=expected):
            _log('companion download corrupt: %s' % url)
            os.remove(tmp_path)
            return None
        return tmp_path
    except Exception as e:
        _log('companion download failed (%s): %s' % (url, e))
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return None


def _extract_zip_silent(zip_path):
    """Extract an add-on zip into the addons dir with no dialogs. The archive's
    top-level folder is the add-on id, matching the main installer's layout."""
    staging_parent = os.path.join(ADDONS_PATH, '.abukarim_staging')
    staging_dir = None
    try:
        os.makedirs(staging_parent, exist_ok=True)
        staging_dir = tempfile.mkdtemp(dir=staging_parent, prefix='comp_')
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if zf.testzip():
                return False
            zf.extractall(staging_dir)
        for top_name in os.listdir(staging_dir):
            src = os.path.join(staging_dir, top_name)
            dest = os.path.join(ADDONS_PATH, top_name)
            _merge_tree(src, dest)
        return True
    except Exception as e:
        _log('companion extract failed: %s' % e)
        return False
    finally:
        if staging_dir and os.path.exists(staging_dir):
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass
        try:
            if os.path.exists(staging_parent) and not os.listdir(staging_parent):
                os.rmdir(staging_parent)
        except Exception:
            pass
        try:
            os.remove(zip_path)
        except OSError:
            pass


# Every known repo's '.../repo/zips/' base, paired with the repository add-on
# id that carries it. A companion is not always present in the same repo as the
# skin the user picked (e.g. TMDb Helper lives in the Kodi repo but Arctic Fuse
# 3 is installed from the Piers repo), so companion resolution tries the skin's
# own repo first and then falls back across these until the add-on is found.
_ALL_REPO_BASES = [
    ('https://raw.githubusercontent.com/taiseer999/'
     'taiseer999.github.io/master/repo/zips/',      'repository.taiseer'),
    ('https://raw.githubusercontent.com/taiseer999/'
     'taiseer999ce.github.io/master/repo/zips/',    'repository.taiseerce'),
    ('https://raw.githubusercontent.com/taiseer999/'
     'taiseer999Piers.github.io/master/repo/zips/', 'repository.taiseerkodi22'),
]


def _resolve_companion(repo_base_first, addonid):
    """Find a companion's zip across the known repos.

    Tries repo_base_first (the repo the skin came from) first, then every other
    known repo base, since a companion may live in a different repo than the
    skin. Returns (zip_url, version, repo_base, repo_id) for the first repo that
    actually has the add-on's addon.xml, or (None, '', None, '') if none do.
    """
    # Ordered, de-duplicated: the skin's own repo first, then the rest.
    ordered = []
    seen = set()
    for base in [repo_base_first] + [b for b, _ in _ALL_REPO_BASES]:
        if base and base not in seen:
            seen.add(base)
            ordered.append(base)

    base_to_repo = dict((b, r) for b, r in _ALL_REPO_BASES)

    for base in ordered:
        version = _companion_version(base, addonid)
        if version:
            zip_url = '%s%s/%s-%s.zip' % (base, addonid, addonid, version)
            return zip_url, version, base, base_to_repo.get(base, '')
    return None, '', None, ''


def _install_companions(skin_id, skin_zipurl, repo_id='', companions=None):
    """Silently install every companion mapped to skin_id.

    Runs with no user-facing prompts and never changes the active skin. Any
    failure is logged and skipped so it can never block the skin install the
    user actually asked for. A companion is fetched from whichever known repo
    actually carries it (not assumed to be the skin's repo), and linked for
    updates to THAT repo.
    """
    # skins.json "companions" wins; the built-in map is the fallback.
    if companions is None:
        companions = _SKIN_COMPANIONS.get(skin_id)
    if not companions:
        return

    skin_repo_base = _repo_base_from_zipurl(skin_zipurl)  # may be None

    for addonid in companions:
        try:
            zip_url, version, found_base, found_repo_id = _resolve_companion(
                skin_repo_base, addonid)
            if not zip_url:
                _log('companion %s not found in any known repo — skipping.'
                     % addonid)
                continue

            _log('silent companion install: %s <- %s' % (addonid, zip_url))
            tmp = _download_zip_silent(zip_url)
            if not tmp:
                continue
            if not _extract_zip_silent(tmp):
                continue

            # Register and enable it (skins like AF3 expect the companion ready,
            # but we never switch the skin to it).
            xbmc.executebuiltin('UpdateLocalAddons')
            xbmc.sleep(1200)
            _enable_addon(addonid)
            _wait_addon_enabled(addonid, timeout_ms=8000)
            _log('companion ready: %s (enabled=%s)'
                 % (addonid, _addon_is_enabled(addonid)))

            # Link the companion back to the repository it actually came from,
            # so it shows as repo-installed and keeps receiving auto-updates.
            # Staged extraction leaves origin empty, which blocks updates. Prefer
            # the repo we found the companion in; fall back to the skin's repo id
            # and then the DB-listing lookup.
            from resources.lib import origin_fix
            xbmc.executebuiltin('UpdateAddonRepos')
            xbmc.sleep(3000)
            wrote = False
            link_repo = found_repo_id or repo_id
            if link_repo:
                wrote = origin_fix.set_origin_silent(addonid, link_repo)
            if not wrote:
                origin_fix.fix_addons_silent([addonid])
        except Exception as e:
            _log('companion install error for %s: %s' % (addonid, e))


class SkinPortal(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.items      = kwargs.get('items', [])
        self.background = kwargs.get('background', 'backgroundkodi.jpg')
        # Repository add-on id that carries this source's skins, used to write
        # the origin deterministically so the skin auto-updates.
        self.repo_id    = kwargs.get('repo_id', '')
        # first_run mode: close the portal right after a successful install
        # and let the caller apply the skin AFTER the modal is gone, so
        # ReloadSkin never fires while this window is still open.
        self.first_run  = kwargs.get('first_run', False)
        self.pending    = None      # (addonid, title) applied by run() afterwards

    def onInit(self):
        bg_path = ('special://home/addons/plugin.program.abukarimtools'
                   '/resources/media/%s' % self.background)
        self.setProperty('background', bg_path)
        self.setProperty('portal_icon', os.path.join(
            ADDON_PATH, 'resources', 'icons', 'skin_installer.png'))
        panel = self.getControl(100)
        panel.reset()
        self.items = [i for i in self.items if _compatible(i)]
        for idx, item in enumerate(self.items):
            li = xbmcgui.ListItem(item.get('name', ''))
            li.setProperty('item_index', str(idx))
            li.setArt({'thumb': item.get('screenshot', ''),
                       'icon':  item.get('screenshot', '')})
            li.setProperty('addonid',  item.get('id', ''))
            li.setProperty('zipurl',   item.get('zip', ''))
            li.setProperty('version',  item.get('version', ''))
            if _skin_installed(item.get('id', '')):
                li.setProperty('installed', 'true')
            panel.addItem(li)
        if self.items:
            self.setFocusId(100)
        # Static labels set from Python: $LOCALIZE resolves against the active
        # skin, not this addon, so our custom ids come back blank in the XML.
        for ctl_id, strid in ((9001, 30320), (9002, 30321), (210, 30325)):
            try:
                self.getControl(ctl_id).setLabel(T(strid))
            except Exception:
                pass

    def onClick(self, controlId):
        if controlId != 100:
            return
        panel   = self.getControl(100)
        item    = panel.getSelectedItem()
        addonid = item.getProperty('addonid')
        zipurl  = item.getProperty('zipurl')
        title   = item.getLabel()
        already = item.getProperty('installed') == 'true'
        try:
            entry = self.items[int(item.getProperty('item_index'))]
        except Exception:
            entry = {'id': addonid, 'zip': zipurl}

        if not zipurl:
            _error(T(30120))
            return

        msg = (T(30121) % title if already else T(30122) % title)
        if not xbmcgui.Dialog().yesno(TITLE, msg):
            return

        zip_path = _download_zip(zipurl, addonid, sha256=entry.get('sha256'))
        if not zip_path:
            return
        if not _extract_zip(zip_path):
            return
        _log('installed via portal: %s (first_run=%s)' % (addonid, self.first_run))

        # Silently pull any companion add-on(s) mapped to this skin from the
        # SAME repo (e.g. AF3 -> TMDbHelper). No
        # prompts, no skin switch — runs before we defer the skin apply.
        _install_companions(addonid, zipurl, self.repo_id,
                            companions=entry.get('companions'))

        # Piers profile for this skin (settings, menus, widgets) when the
        # catalog publishes one. Applied BEFORE the skin is activated so it
        # loads with them. Best-effort: a failure never blocks the install.
        try:
            from resources.lib import skin_profiles
            skin_profiles.apply_for_item(entry, first_run=self.first_run)
        except Exception as e:
            _log('profile apply failed for %s: %s' % (addonid, e))

        # Enable the freshly-extracted skin RIGHT NOW, before anything else
        # touches it. If it's left disabled, Kodi throws the 'Add-on required /
        # enable this add-on?' popup the moment the skin is referenced — which
        # is the dialog the user keeps seeing. UpdateLocalAddons registers the
        # new addon so SetAddonEnabled can take effect.
        xbmc.executebuiltin('UpdateLocalAddons')
        xbmc.sleep(1500)
        _enable_addon(addonid)
        _wait_addon_enabled(addonid, timeout_ms=8000)
        _log('skin pre-enabled in portal: %s (enabled=%s)'
             % (addonid, _addon_is_enabled(addonid)))

        # Link the skin back to its repository (origin) so it shows as
        # repo-installed and auto-updates. UpdateLocalAddons only rescans
        # local folders — it does NOT populate the repo listing tables that
        # the join-based fix depends on — so we (1) force a real repo listing
        # refresh, then (2) write the origin deterministically from the repo
        # the user picked, which works even if that listing is still empty.
        from resources.lib import origin_fix
        xbmc.executebuiltin('UpdateAddonRepos')
        xbmc.sleep(3000)
        wrote = False
        if self.repo_id:
            wrote = origin_fix.set_origin_silent(addonid, self.repo_id)
        if not wrote:
            # Fallback: look the skin up in whatever repo listing is cached.
            origin_fix.fix_addons_silent([addonid])

        # Always defer the skin switch until AFTER this portal (window 13001)
        # has closed. Applying while the portal is still open leaves it
        # lingering on top of the new skin (and the keep/enable confirmation
        # must be handled with no custom WindowXMLDialog open). So in every
        # mode: record the pending skin, close the portal, and let run() apply
        # it on a clean screen.
        self.pending = (addonid, title)
        item.setProperty('installed', 'true')
        self.close()
        return

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_NAV_BACK,
                               xbmcgui.ACTION_PREVIOUS_MENU):
            self.close()


def _patch_now():
    """Patch what was just installed right away (3.1.0.27) instead of waiting
    for the watchdog poll. Idempotent, never raises."""
    try:
        from resources.lib import patch_watchdog
        patch_watchdog.patch_after_install(reason='skin-portal')
    except Exception as e:
        _log('post-install patch failed: %s' % e)


def run(first_run=False):
    """Guarded entry point for the skin installer.

    Serialises with the skin switcher on a single shared lock: a skin swap
    starting while this flow has a custom modal dialog open (or vice-versa)
    reloads every window, tearing the dialog down and re-creating it under a
    new id — the handle goes stale and the dialog freezes ("Window id does not
    exist"; the repo-select screen stuck and non-interactive). Only one skin
    operation runs at a time; a colliding trigger is refused.
    """
    from resources.lib import skin_switcher
    if skin_switcher.skin_op_busy():
        _log('skin operation already in progress — refusing installer run.')
        return False
    skin_switcher.set_skin_op_busy(True)
    try:
        return _run_impl(first_run=first_run)
    finally:
        skin_switcher.set_skin_op_busy(False)


def _run_impl(first_run=False):
    url, background = _choose_source()
    if not url:
        return False

    try:
        items = _fetch_json(url)
    except urllib.error.URLError as e:
        _error(T(30123) % e.reason)
        return False
    except json.JSONDecodeError:
        _error(T(30124))
        return False
    except Exception as e:
        _error(T(30125) % e)
        return False

    if not items:
        return False

    repo_id = _REPO_ID_FOR_JSON.get(url, '')

    win = SkinPortal(
        'portal.xml',
        ADDON_PATH,
        'Default',
        '1080i',
        items=items,
        background=background,
        first_run=first_run,
        repo_id=repo_id,
    )
    win.doModal()
    pending = win.pending
    del win

    # The portal closed itself after a successful install; apply the skin now
    # that no custom modal window is open (applies in all modes).
    if pending:
        addonid, title = pending
        _log('deferred apply: %s' % addonid)
        ok = _apply_skin(addonid, title)
        if ok:
            _notify(T(30126) % title)
            if not first_run:
                _patch_now()
            try:
                from resources.lib import skin_switcher
                skin_switcher._close_to_home()
            except Exception as e:
                _log('close-to-home failed: %s' % e)
            # Kodi keeps add-on origins in memory and only uses them for update
            # checks after a restart. The skin (and any companion) was just
            # linked to its repo (written to the Addons DB above). During
            # first-run we must NOT restart here — the service still has other
            # steps to run. On a MANUAL install we no longer FORCE a restart:
            # recommend one instead. The linking is already on disk, so if the
            # user declines it simply takes effect on the next normal start,
            # and the service re-applies linking on every boot as a safety net.
            if first_run:
                _log('skin installed (first-run) — deferring restart to the '
                     'end of the first-run sequence.')
            else:
                try:
                    from resources.lib import origin_fix
                    _log('skin installed — recommending a restart (not forced).')
                    xbmc.sleep(500)
                    origin_fix.recommend_restart(
                        message=('The skin was installed and linked to its '
                                 'repository.\nA restart is recommended so its '
                                 'updates become active.\n'
                                 'تم تثبيت الواجهة وربطها بالمستودع.\n'
                                 'يُنصح بإعادة التشغيل حتى تصبح تحديثاتها '
                                 'فعّالة.'))
                except Exception as e:
                    _log('post-install restart recommendation failed: %s' % e)
        return ok

    _log('portal closed with no pending skin to apply')
    return False
