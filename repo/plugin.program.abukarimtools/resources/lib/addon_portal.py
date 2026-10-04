# -*- coding: utf-8 -*-
"""
Add-on Portal – pick one or more video add-ons from a fixed catalogue and
install each one FROM ITS CHOSEN REPOSITORY.

Why not just InstallAddon(id) for everything?
  Kodi picks the source itself when several enabled repos carry the same id
  (highest version, official repo wins). Two catalogue entries collide:
  YouTube (repository.xbmc.org / umbrella / redwizard) and RedLight
  (repository.taiseerKODI22 v3.x vs repository.redwizard). The catalogue
  pins a repo per add-on, so the MAIN add-on zip is resolved and downloaded
  from that repo's own addons.xml, deterministically.

Flow per run:
  1. Repos: every repo the selection needs is installed if missing. All five
     repo zips are mirrored in repository.taiseer's datadir, so they are
     resolved from there (current version read from its addons.xml).
     Then UpdateAddonRepos + wait, so Kodi has listings for dependencies.
  2. Main add-on: read the pinned repo's LOCAL addon.xml -> every <dir> that
     matches this Kodi version -> its addons.xml -> highest version of the id
     -> datadir/<id>/<id>-<ver>.zip -> download, CRC-verify, stage-extract.
  3. Dependencies: every non-optional <import> not already present is handed
     to Kodi's own InstallAddon(dep) (resolves nested deps across all repos);
     its "Install add-on?" prompt is auto-answered Yes by a watchdog thread.
  4. UpdateLocalAddons, enable, and write installed.origin = pinned repo so
     the add-on keeps updating from THAT repo.
  Any resolve/download failure for step 2 falls back to InstallAddon(id).
"""

import os
import re
import gzip
import json
import threading
import urllib.request
import xml.etree.ElementTree as ET

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

import xbmcaddon as _xbmcaddon
ADDON_ID    = 'plugin.program.abukarimtools'
ADDON_PATH  = xbmcvfs.translatePath(_xbmcaddon.Addon(ADDON_ID).getAddonInfo('path'))
if not ADDON_PATH.endswith(os.sep):
    ADDON_PATH += os.sep
ADDONS_PATH = xbmcvfs.translatePath('special://home/addons/')

TITLE       = 'ABUKARIM – Add-on Portal'
PORTAL_ICON = os.path.join(ADDON_PATH, 'resources', 'icons', 'addon_portal.png')

# Bootstrap source for repository zips (all five are mirrored here).
TAISEER_ZIPS = ('https://raw.githubusercontent.com/taiseer999/'
                'taiseer999.github.io/main/repo/zips/')

# (addon id, display name, pinned repo, remote icon fallback)
CATALOG = [
    ('plugin.video.dexhub',      'Dex Hub',     'repository.dexworld',
     'https://dexworld.cc/kodi/plugin.video.dexhub/resources/media/icon.png'),
    ('plugin.video.dplex',       'DPlex',       'repository.dexworld',
     'https://dexworld.cc/kodi/plugin.video.dplex/resources/media/icon.png'),
    ('plugin.video.fenlight',    'Fen Light+',  'repository.taiseer',
     TAISEER_ZIPS + 'plugin.video.fenlight/resources/media/fenlight_plus_icon.png'),
    ('plugin.video.last_played', 'Last Played', 'repository.taiseer',
     TAISEER_ZIPS + 'plugin.video.last_played/icon.png'),
    ('plugin.video.pov',         'POV',         'repository.kodifitzwell',
     ''),
    ('plugin.video.redlight',    'Red Light',   'repository.redwizard',
     'https://repo.redwizard.xyz/redwizardrepo/main/plugin.video.redlight/'
     'resources/media/addon_icons/icon.png'),
    ('plugin.video.seren',       'Seren',       'repository.taiseer',
     TAISEER_ZIPS + 'plugin.video.seren/resources/images/ico-seren-3.png'),
    ('plugin.video.umbrella',    'Umbrella',    'repository.umbrella',
     'https://raw.githubusercontent.com/umbrellaplug/umbrellaplug.github.io/'
     'master/nexus/zips/plugin.video.umbrella/icon.png'),
    ('plugin.video.youtube',     'YouTube',     'repository.redwizard',
     'https://repo.redwizard.xyz/redwizardrepo/main/plugin.video.youtube/'
     'resources/media/icon.png'),
]

REPO_NAMES = {
    'repository.dexworld':     'DexWorld',
    'repository.taiseer':      'ABUKARIM',
    'repository.kodifitzwell': 'kodifitzwell',
    'repository.redwizard':    'The Red Repo',
    'repository.umbrella':     'Umbrella',
}


def _remote_portal():
    try:
        from resources.lib import remote_config
        return remote_config.load('portal.json', {}) or {}
    except Exception:
        return {}


def _catalog():
    """CATALOG, or the list published in abukarim/portal.json.

    portal.json: {"schema": 1,
                  "addons": [{"id": .., "name": .., "repo": .., "icon": ..}],
                  "repo_names": {"repository.x": "Nice Name"},
                  "repo_zips": {"repository.x": "https://.../repository.x-1.0.zip"}}
    A broken or empty list falls back to the built-in CATALOG.
    """
    data = _remote_portal()
    out = []
    for e in data.get('addons') or []:
        try:
            if e['id'] and e['repo']:
                out.append((e['id'], e.get('name') or e['id'], e['repo'],
                            e.get('icon', '')))
        except Exception:
            continue
    if out:
        names = data.get('repo_names') or {}
        REPO_NAMES.update({k: v for k, v in names.items() if isinstance(v, str)})
        return out
    return list(CATALOG)


# Import ids that are never fetched (core ABIs / always present).
_SKIP_DEP_PREFIXES = ('xbmc.', 'kodi.')


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools AddonPortal] %s' % msg, level)


def _is_local(addon_id):
    return os.path.isfile(os.path.join(ADDONS_PATH, addon_id, 'addon.xml'))


def _has_addon(addon_id):
    return bool(xbmc.getCondVisibility('System.HasAddon(%s)' % addon_id))


def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Kodi'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if data[:2] == b'\x1f\x8b':          # addons.xml.gz / compressed info
        data = gzip.decompress(data)
    return data


def _ver_key(v):
    """Loose Kodi-style version ordering: numeric parts compared as ints,
    anything after '~' (pre-release) sorts lower."""
    v = (v or '').strip()
    pre = 0 if '~' in v else 1
    core = v.split('~')[0].split('+')[0]
    parts = []
    for p in re.split(r'[.\-_]', core):
        m = re.match(r'(\d+)(.*)', p)
        if m:
            parts.append((int(m.group(1)), m.group(2)))
        elif p:
            parts.append((-1, p))
    return (parts, pre, v)


def _kodi_version():
    raw = xbmc.getInfoLabel('System.BuildVersion') or ''
    m = re.match(r'(\d+(?:\.\d+)*)', raw)
    return tuple(int(x) for x in m.group(1).split('.')) if m else (22, 0)


def _vtuple(s):
    try:
        return tuple(int(x) for x in re.findall(r'\d+', s))
    except Exception:
        return ()


def _local_icon(addon_id, remote):
    """Installed add-on's own icon, else the remote URL, else the portal icon."""
    base = os.path.join(ADDONS_PATH, addon_id)
    try:
        root = ET.parse(os.path.join(base, 'addon.xml')).getroot()
        el = root.find('.//assets/icon')
        if el is not None and el.text:
            p = os.path.join(base, el.text.strip())
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    p = os.path.join(base, 'icon.png')
    if os.path.isfile(p):
        return p
    return remote or PORTAL_ICON


# ---------------------------------------------------------------------------
# repository resolution
# ---------------------------------------------------------------------------

def _addons_xml_version(addons_xml_bytes, addon_id):
    m = re.search(br'<addon\b[^>]*\bid="%s"[^>]*>' % re.escape(addon_id.encode()),
                  addons_xml_bytes)
    if not m:
        return ''
    v = re.search(br'\bversion="([^"]+)"', m.group(0))
    return v.group(1).decode('utf-8', 'replace') if v else ''


def _repo_dirs(repo_id):
    """[(info_url, datadir, zip_bool)] from the INSTALLED repo's addon.xml,
    filtered to <dir> blocks whose min/maxversion match this Kodi."""
    path = os.path.join(ADDONS_PATH, repo_id, 'addon.xml')
    if not os.path.isfile(path):
        return []
    kv = _kodi_version()
    out = []
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        _log('cannot parse %s: %s' % (path, e), xbmc.LOGWARNING)
        return []
    for ext in root.findall('extension'):
        if ext.get('point') != 'xbmc.addon.repository':
            continue
        blocks = ext.findall('dir') or [ext]     # legacy: info/datadir directly
        for d in blocks:
            mn, mx = d.get('minversion'), d.get('maxversion')
            if mn and kv < _vtuple(mn):
                continue
            if mx and kv > _vtuple(mx):
                continue
            info = d.find('info')
            data = d.find('datadir')
            if info is None or data is None or not info.text or not data.text:
                continue
            datadir = data.text.strip()
            if not datadir.endswith('/'):
                datadir += '/'
            out.append((info.text.strip(), datadir,
                        (data.get('zip') or 'false').lower() == 'true'))
    return out


def _resolve_zip_in_repo(repo_id, addon_id):
    """Highest version of addon_id across the repo's matching dirs.
    Returns (zip_url, version) or (None, '')."""
    best = None
    for info_url, datadir, is_zip in _repo_dirs(repo_id):
        if not is_zip:
            continue
        try:
            ver = _addons_xml_version(_http_get(info_url), addon_id)
        except Exception as e:
            _log('%s: listing %s failed: %s' % (repo_id, info_url, e))
            continue
        if ver and (best is None or _ver_key(ver) > _ver_key(best[1])):
            best = ('%s%s/%s-%s.zip' % (datadir, addon_id, addon_id, ver), ver)
    return best or (None, '')


def _resolve_repo_zip(repo_id):
    """Repository zips come from the repository.taiseer mirror (or an explicit
    URL published in portal.json's repo_zips map)."""
    override = (_remote_portal().get('repo_zips') or {}).get(repo_id)
    if override:
        return override
    try:
        ver = _addons_xml_version(_http_get(TAISEER_ZIPS + 'addons.xml'), repo_id)
    except Exception as e:
        _log('mirror listing failed: %s' % e, xbmc.LOGWARNING)
        return None
    if not ver:
        return None
    return '%s%s/%s-%s.zip' % (TAISEER_ZIPS, repo_id, repo_id, ver)


# ---------------------------------------------------------------------------
# install primitives (reuse the skin installer's proven helpers)
# ---------------------------------------------------------------------------

def _si():
    from resources.lib import skin_installer
    return skin_installer


def _install_zip(url):
    si = _si()
    tmp = si._download_zip_silent(url)
    if not tmp:
        return False
    return si._extract_zip_silent(tmp)


def _enable(addon_id, timeout_ms=8000):
    si = _si()
    if si._addon_is_enabled(addon_id):
        return True
    si._enable_addon(addon_id)
    return si._wait_addon_enabled(addon_id, timeout_ms=timeout_ms)


def _force_origin(addon_id, repo_id, timeout_ms=10000):
    """installed.origin = repo_id (overwrites, unlike origin_fix.set_origin,
    because a reinstall from a different repo must re-point updates)."""
    from resources.lib import origin_fix
    db = origin_fix._find_addons_db()
    if not db:
        return False
    waited = 0
    while waited <= timeout_ms:
        conn = None
        try:
            conn = origin_fix._connect(db)
            cur = conn.cursor()
            cur.execute('UPDATE installed SET origin = ? WHERE addonID = ?',
                        (repo_id, addon_id))
            conn.commit()
            if cur.rowcount:
                _log('origin %s -> %s' % (addon_id, repo_id))
                return True
        except Exception as e:
            _log('origin write failed for %s: %s' % (addon_id, e))
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        xbmc.sleep(500)           # not registered yet -> wait for Kodi
        waited += 500
    return False


def _required_imports(addon_id):
    path = os.path.join(ADDONS_PATH, addon_id, 'addon.xml')
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []
    deps = []
    for imp in root.findall('./requires/import'):
        dep = imp.get('addon') or ''
        if not dep or dep.startswith(_SKIP_DEP_PREFIXES):
            continue
        if (imp.get('optional') or '').lower() == 'true':
            continue
        deps.append(dep)
    return deps


class _YesWatchdog(object):
    """Answers Kodi's 'Install add-on?' / dependency yes-no prompts while a
    Kodi-side InstallAddon runs. Only alive during that window, so it can
    never click one of the portal's own dialogs."""

    def __init__(self):
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run)
        self._t.daemon = True

    def _run(self):
        while not self._stop.is_set():
            if xbmc.getCondVisibility('Window.IsActive(yesnodialog)'):
                xbmc.executebuiltin('SendClick(yesnodialog, 11)')   # 11 = Yes
                _log('auto-confirmed install prompt')
                xbmc.sleep(400)
            xbmc.sleep(100)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(2)
        return False


def _kodi_install(addon_id, timeout_ms=90000):
    """Hand one id to Kodi's own installer (resolves nested deps). Blocks
    until it is present or times out."""
    if _has_addon(addon_id):
        return True
    with _YesWatchdog():
        xbmc.executebuiltin('InstallAddon(%s)' % addon_id)
        waited = 0
        mon = xbmc.Monitor()
        while waited < timeout_ms and not mon.abortRequested():
            if _has_addon(addon_id):
                xbmc.sleep(1500)          # let the extract/registration settle
                return True
            xbmc.sleep(500)
            waited += 500
    _log('InstallAddon(%s) timed out' % addon_id, xbmc.LOGWARNING)
    return _has_addon(addon_id)


def _wait_repo_listings(repo_ids, timeout_ms=40000):
    """After UpdateAddonRepos: wait until every repo has a cached listing
    (repo.lastcheck set), so InstallAddon can resolve dependencies."""
    from resources.lib import origin_fix
    db = origin_fix._find_addons_db()
    if not db or not repo_ids:
        xbmc.sleep(5000)
        return
    waited = 0
    pending = set(repo_ids)
    while pending and waited < timeout_ms:
        conn = None
        try:
            conn = origin_fix._connect(db)
            rows = conn.execute("SELECT addonID FROM repo WHERE "
                                "lastcheck IS NOT NULL AND lastcheck != ''"
                                ).fetchall()
            have = set(r[0].lower() for r in rows)
            pending = set(r for r in pending if r.lower() not in have)
        except Exception:
            pass
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        if pending:
            xbmc.sleep(1000)
            waited += 1000
    if pending:
        _log('repo listings still pending: %s' % sorted(pending))


# ---------------------------------------------------------------------------
# the install run
# ---------------------------------------------------------------------------

def _install_selection(entries):
    """entries = [(addon_id, name, repo_id)]. Returns [(name, ok, note)]."""
    results = []
    prog = xbmcgui.DialogProgress()
    prog.create(TITLE, T(30401))
    # Answer every "Add-on required / enable this add-on?" (and install)
    # yes/no for the WHOLE run, plus a short tail after it: freshly enabled
    # add-ons can fire EnableAddon() on themselves from their own service
    # (POV re-enables itself right after its service starts - the prompt in
    # the 3.1.0.21 log came 1 s after POV's service started). Nothing of ours
    # asks a yes/no during this window, so auto-Yes is safe here.
    guard = _YesWatchdog()
    guard.__enter__()
    try:
        # 1) repositories -------------------------------------------------
        repos = []
        for _aid, _n, rid in entries:
            if rid not in repos:
                repos.append(rid)
        new_repos = []
        for i, rid in enumerate(repos):
            prog.update(int(i * 15 / max(len(repos), 1)),
                        T(30402) % REPO_NAMES.get(rid, rid))
            if not _is_local(rid):
                url = _resolve_repo_zip(rid)
                if url and _install_zip(url):
                    new_repos.append(rid)
                    _log('repo installed: %s' % rid)
                else:
                    _log('repo install failed: %s' % rid, xbmc.LOGWARNING)
        xbmc.executebuiltin('UpdateLocalAddons')
        xbmc.sleep(2500)
        for rid in repos:
            if _is_local(rid):
                _enable(rid)
        for rid in new_repos:
            _force_origin(rid, rid)
        prog.update(18, T(30403))
        xbmc.executebuiltin('UpdateAddonRepos')
        _wait_repo_listings([r for r in repos if _is_local(r)])

        # 2+3) each add-on ------------------------------------------------
        n = len(entries)
        for i, (aid, name, rid) in enumerate(entries):
            if prog.iscanceled():
                results.append((name, False, T(30410)))
                continue
            base = 20 + int(i * 75 / n)
            prog.update(base, T(30404) % (name, REPO_NAMES.get(rid, rid)))

            via = 'zip'
            ok = False
            if _is_local(rid):
                zip_url, ver = _resolve_zip_in_repo(rid, aid)
                if zip_url:
                    _log('%s %s <- %s' % (aid, ver, zip_url))
                    ok = _install_zip(zip_url)
            if not ok:
                # Could not pin the source (repo missing / host down):
                # let Kodi resolve it from whatever repo carries it.
                via = 'kodi'
                _log('%s: falling back to InstallAddon' % aid, xbmc.LOGWARNING)
                ok = _kodi_install(aid)
            if not ok:
                results.append((name, False, T(30411)))
                continue

            if via == 'zip':
                deps = [d for d in _required_imports(aid) if not _has_addon(d)]
                for j, dep in enumerate(deps):
                    prog.update(base + int(60 / n), T(30405) % (name, dep))
                    if not _kodi_install(dep):
                        _log('%s: dependency %s not installed' % (aid, dep),
                             xbmc.LOGWARNING)
                xbmc.executebuiltin('UpdateLocalAddons')
                xbmc.sleep(2000)
                # deps installed while disabled (rare) must be enabled too
                for dep in _required_imports(aid):
                    if _is_local(dep):
                        _enable(dep, timeout_ms=4000)

            enabled = _enable(aid)
            _force_origin(aid, rid)
            missing = [d for d in _required_imports(aid) if not _has_addon(d)]
            if missing:
                results.append((name, enabled, T(30412) % ', '.join(missing)))
            else:
                results.append((name, enabled, '' if enabled else T(30413)))
        prog.update(100, T(30406))
        # tail: catch self-enable prompts from add-on services starting now
        mon = xbmc.Monitor()
        mon.waitForAbort(8)
    finally:
        guard.__exit__(None, None, None)
        prog.close()
    return results


# ---------------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------------

class AddonPortal(xbmcgui.WindowXMLDialog):

    LIST, BTN_INSTALL, BTN_ALL = 100, 201, 202

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.catalog = kwargs.get('catalog') or _catalog()
        ids = {c[0] for c in self.catalog}
        self.checked = set(a for a in (kwargs.get('preselect') or ()) if a in ids)
        self.result = None           # list of (aid, name, repo) on Install

    def onInit(self):
        self.setProperty('portal_icon', PORTAL_ICON)
        lst = self.getControl(self.LIST)
        lst.reset()
        for aid, name, rid, remote in self.catalog:
            li = xbmcgui.ListItem(name)
            icon = _local_icon(aid, remote)
            li.setArt({'icon': icon, 'thumb': icon})
            li.setProperty('addonid', aid)
            li.setProperty('repo', REPO_NAMES.get(rid, rid))
            li.setProperty('installed', 'true' if _is_local(aid) else '')
            li.setProperty('status', T(30407) if _is_local(aid) else '')
            li.setProperty('checked', 'true' if aid in self.checked else '')
            lst.addItem(li)
        for cid, sid in ((9001, 30400), (9002, 30408),
                         (self.BTN_INSTALL, 30409)):
            try:
                self.getControl(cid).setLabel(T(sid))
            except Exception:
                pass
        self._refresh()
        for _ in range(10):
            self.setFocusId(self.LIST)
            if self.getFocusId() == self.LIST:
                break
            xbmc.sleep(100)

    def _refresh(self):
        try:
            self.getControl(9003).setLabel(T(30414) % len(self.checked))
            self.getControl(self.BTN_ALL).setLabel(
                T(30416) if len(self.checked) == len(self.catalog) else T(30415))
        except Exception:
            pass

    def _set(self, idx, on):
        aid = self.catalog[idx][0]
        li = self.getControl(self.LIST).getListItem(idx)
        if on:
            self.checked.add(aid)
        else:
            self.checked.discard(aid)
        li.setProperty('checked', 'true' if on else '')

    def onClick(self, control_id):
        if control_id == self.LIST:
            idx = self.getControl(self.LIST).getSelectedPosition()
            if 0 <= idx < len(self.catalog):
                self._set(idx, self.catalog[idx][0] not in self.checked)
                self._refresh()
        elif control_id == self.BTN_ALL:
            on = len(self.checked) != len(self.catalog)
            for i in range(len(self.catalog)):
                self._set(i, on)
            self._refresh()
        elif control_id == self.BTN_INSTALL:
            if not self.checked:
                xbmcgui.Dialog().notification(TITLE, T(30417), PORTAL_ICON, 2500)
                return
            self.result = [(a, n, r) for a, n, r, _i in self.catalog
                           if a in self.checked]
            self.close()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_NAV_BACK,
                               xbmcgui.ACTION_PREVIOUS_MENU):
            self.close()


def _patch_now():
    """Patch what was just installed right away (3.1.0.27) instead of waiting
    for the watchdog poll. Idempotent, never raises."""
    try:
        from resources.lib import patch_watchdog
        patch_watchdog.patch_after_install(reason='addon-portal')
    except Exception as e:
        _log('post-install patch failed: %s' % e)


def run(first_run=False, preselect=None):
    import time
    selection = None
    # A window closed in under 1.5 s with no choice was swallowed by a skin
    # reload / add-on rescan, not dismissed by the user: open it again.
    for attempt in range(3):
        started = time.time()
        win = AddonPortal('addon_portal.xml', ADDON_PATH, 'Default', '1080i',
                          preselect=preselect)
        win.doModal()
        selection = win.result
        del win
        if selection or time.time() - started > 1.5:
            break
        _log('portal closed instantly (attempt %d) - reopening' % (attempt + 1))
        xbmc.sleep(1500)
    if not selection:
        return False

    names = ', '.join(n for _a, n, _r in selection)
    if not xbmcgui.Dialog().yesno(TITLE, T(30418) % names):
        return False

    results = _install_selection(selection)
    ok = [n for n, good, _ in results if good]
    lines = []
    for name, good, note in results:
        mark = '[COLOR FF33D17A]OK[/COLOR]' if good else '[COLOR FFFF5555]X[/COLOR]'
        lines.append('%s  %s%s' % (mark, name, ('  - ' + note) if note else ''))
    xbmcgui.Dialog().textviewer(TITLE, '\n'.join(lines))

    # First-run applies patches as its own next step.
    if ok and not first_run:
        _patch_now()

    # Menus / widgets that point at the add-ons just installed come back.
    try:
        from resources.lib import menu_reconcile
        menu_reconcile.run(rebuild=True)
    except Exception as e:
        _log('menu reconcile failed: %s' % e, xbmc.LOGWARNING)

    if ok and not first_run:
        try:
            from resources.lib import origin_fix
            origin_fix.recommend_restart(message=T(30419))
        except Exception as e:
            _log('restart recommendation failed: %s' % e)
    return bool(ok)
