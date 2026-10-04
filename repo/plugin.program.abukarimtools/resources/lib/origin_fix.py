# -*- coding: utf-8 -*-
"""
Origin Fix – repairs the 'origin' column in Kodi's Addons database.

Add-ons installed by staged extraction (skin portal / wizard builds) or from a
zip file are registered with an EMPTY origin. Kodi 19+ only auto-updates an
add-on from the repository recorded as its origin, so an empty origin means
the add-on never receives updates and never shows as repo-installed.

This tool looks each such add-on up in the cached repository listings inside
the same database (repo / addonlinkrepo / addons tables) and, when a repo is
found that carries it, writes that repo's id into installed.origin.

Safety rules:
  * only add-ons physically present under special://home/addons are touched
    (system/binary add-ons that live in the read-only OS image are skipped,
    so CoreELEC binaries can never be pointed at repository.xbmc.org)
  * only rows whose origin is currently empty are modified
  * nothing is ever deleted; the change is a single UPDATE per add-on

Note: Kodi keeps origins in memory, so a restart is needed before the new
origins take effect for update checks. The interactive runner offers one.
"""

import os
import re
import sys
import sqlite3

import xbmc
import xbmcgui
import xbmcvfs

TITLE = 'ABUKARIM – Origin Fix'

ADDONS_PATH   = xbmcvfs.translatePath('special://home/addons/')
DATABASE_PATH = xbmcvfs.translatePath('special://database/')

# When several repos carry the same add-on id, prefer these (compared
# case-insensitively, first match wins), otherwise fall back to the
# alphabetically-first candidate so the result is deterministic.
PREFERRED_REPOS_22 = [
    'repository.taiseerKODI22',   # Piers / Kodi 22 repo
    'repository.taiseerCE',       # CoreELEC NG repo
    'repository.taiseer',         # Kodi 21 repo
]
PREFERRED_REPOS_21 = [
    'repository.taiseer',         # Kodi 21 repo
    'repository.taiseerCE',       # CoreELEC NG repo
    'repository.taiseerKODI22',   # Piers / Kodi 22 repo - last below Kodi 22
]


def _kodi_major():
    try:
        return int(re.match(r'\d+', xbmc.getInfoLabel('System.BuildVersion')).group(0))
    except Exception:
        return 22


PREFERRED_REPOS = PREFERRED_REPOS_22 if _kodi_major() >= 22 else PREFERRED_REPOS_21

# Never rewrite the origin of these ids even if a repo carries them.
SKIP_IDS = set()


def _log(msg):
    xbmc.log('[AbukarimTools OriginFix] %s' % msg, xbmc.LOGINFO)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _find_addons_db():
    """Return the path of the newest AddonsNN.db, or None."""
    best_ver, best_path = -1, None
    try:
        for name in os.listdir(DATABASE_PATH):
            m = re.fullmatch(r'Addons(\d+)\.db', name)
            if m and int(m.group(1)) > best_ver:
                best_ver = int(m.group(1))
                best_path = os.path.join(DATABASE_PATH, name)
    except OSError as e:
        _log('cannot list Database dir: %s' % e)
    return best_path


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def _tables(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cur.fetchall()}


def _vkey(v):
    """Sortable key for Kodi version strings (5.10.18, 100.0.30i, 2.0.2.2.1)."""
    out = []
    for tok in re.findall(r'\d+|[A-Za-z]+', str(v or '')):
        out.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
    return tuple(out)


def _installed_version(addon_id):
    """Version attribute of the local addon.xml, or ''."""
    try:
        with open(os.path.join(ADDONS_PATH, addon_id, 'addon.xml'),
                  'r', encoding='utf-8', errors='replace') as f:
            head = f.read(4096)
        m = re.search(r'<addon\b[^>]*?\bversion="([^"]+)"', head, re.S)
        return m.group(1) if m else ''
    except Exception:
        return ''


_HAS_VERSION_COL = {}


def _repo_candidates(cur, addon_id):
    """[(repo_id, cached_version), ...] for every repository whose cached
    listing carries addon_id. cached_version is '' when unknown."""
    key = id(cur.connection)
    if key not in _HAS_VERSION_COL:
        try:
            cur.execute('PRAGMA table_info(addons)')
            _HAS_VERSION_COL[key] = any(r[1] == 'version' for r in cur.fetchall())
        except Exception:
            _HAS_VERSION_COL[key] = False
    col = 'a.version' if _HAS_VERSION_COL[key] else "''"
    cur.execute(
        'SELECT r.addonID, %s '
        'FROM repo r '
        'JOIN addonlinkrepo l ON l.idRepo = r.id '
        'JOIN addons a       ON a.id     = l.idAddon '
        'WHERE a.addonID = ?' % col, (addon_id,))
    best = {}
    for rid, ver in cur.fetchall():
        if not rid:
            continue
        if rid not in best or _vkey(ver) > _vkey(best[rid]):
            best[rid] = ver or ''
    return sorted(best.items())


def _pick_repo(candidates, installed_version=''):
    """Choose the origin among [(repo, cached_version)].

    3.1.11: (1) repositories that carry AT LEAST the installed version win -
    linking AF3 5.10.18 to a repo that only has 5.5.25 means it never updates;
    (2) PREFERRED_REPOS is now really case-insensitive (the old code lowercased
    the candidates but not the preferences, so repository.taiseerKODI22 /
    repository.taiseerCE could never match and repository.taiseer always won).
    """
    if not candidates:
        return None
    pool = candidates
    if installed_version:
        ok = [c for c in candidates
              if c[1] and _vkey(c[1]) >= _vkey(installed_version)]
        if ok:
            pool = ok
    lower = {c[0].lower(): c[0] for c in pool}
    for pref in PREFERRED_REPOS:
        if pref.lower() in lower:
            return lower[pref.lower()]
    # otherwise the repo with the newest cached version, then alphabetical
    return sorted(pool, key=lambda c: (_vkey(c[1]), c[0]), reverse=True)[0][0] \
        if any(c[1] for c in pool) else sorted(c[0] for c in pool)[0]


def _covers(candidates, repo_id, installed_version):
    """True when repo_id carries at least installed_version."""
    for rid, ver in candidates:
        if rid.lower() == (repo_id or '').lower():
            return (not installed_version or not ver
                    or _vkey(ver) >= _vkey(installed_version))
    return False


def _locally_installed(addon_id):
    """True when the add-on physically lives in the writable addons dir."""
    return os.path.isdir(os.path.join(ADDONS_PATH, addon_id))


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

# Kodi's built-in origin id for add-ons bundled with Kodi (ORIGIN_SYSTEM).
ORIGIN_SYSTEM = 'b6a50484-93a0-4afb-a01c-8d17e059feda'


def fix_addons(addon_ids=None):
    """Repair empty origins.

    addon_ids: iterable of ids to fix, or None to scan every installed row
    with an empty origin.

    Returns a dict:
        {'fixed': {addonID: repoID, ...},
         'unmatched': [addonID, ...],   # empty origin but not in any repo
         'error': str or None}
    """
    result = {'fixed': {}, 'unmatched': [], 'error': None}

    db_path = _find_addons_db()
    if not db_path:
        result['error'] = 'No Addons database found.'
        _log(result['error'])
        return result
    _log('using database: %s' % db_path)

    conn = None
    try:
        conn = _connect(db_path)
        cur = conn.cursor()

        need = {'installed', 'repo', 'addonlinkrepo', 'addons'}
        missing = need - _tables(cur)
        if missing:
            result['error'] = ('Database schema unexpected '
                               '(missing: %s)' % ', '.join(sorted(missing)))
            _log(result['error'])
            return result

        if addon_ids is None:
            cur.execute("SELECT addonID FROM installed "
                        "WHERE origin IS NULL OR origin = ''")
            targets = [row[0] for row in cur.fetchall()]
        else:
            targets = list(addon_ids)

        updates = []
        for addon_id in targets:
            if not addon_id or addon_id in SKIP_IDS:
                continue
            if not _locally_installed(addon_id):
                continue  # bundled/system add-on – never touch

            cur.execute('SELECT origin FROM installed WHERE addonID = ?',
                        (addon_id,))
            row = cur.fetchone()
            if row is None or (row[0] or '') != '':
                continue  # not registered yet, or already has an origin

            inst = _installed_version(addon_id)
            cands = _repo_candidates(cur, addon_id)
            repo_id = _pick_repo(cands, inst)
            if repo_id:
                updates.append((repo_id, addon_id))
                if not _covers(cands, repo_id, inst):
                    result.setdefault('stale', []).append(addon_id)
            else:
                result['unmatched'].append(addon_id)

        for repo_id, addon_id in updates:
            cur.execute('UPDATE installed SET origin = ? '
                        "WHERE addonID = ? AND (origin IS NULL OR origin = '')",
                        (repo_id, addon_id))
            if cur.rowcount:
                result['fixed'][addon_id] = repo_id
                _log('origin set: %s -> %s' % (addon_id, repo_id))

        # Correction pass (3.1.11): an origin that points at a repository
        # which does NOT carry the installed version (e.g. AF3 5.10.18 linked
        # to repository.taiseer, which only has 5.5.25, by the old
        # preference bug) is moved to a repository that does. Origins Kodi set
        # itself always carry the installed version, so they are left alone.
        if addon_ids is None:
            cur.execute("SELECT addonID, origin FROM installed "
                        "WHERE origin IS NOT NULL AND origin != ''")
            for addon_id, origin in cur.fetchall():
                if not addon_id or addon_id in SKIP_IDS or addon_id in result['fixed']:
                    continue
                # 3.2.0: Kodi's ORIGIN_SYSTEM marks add-ons that ship with Kodi
                # itself. Kodi puts it back on every scan, so "correcting" it
                # rewrote the same 9 rows every 15 s (log 2026-10-03 09:04-09:07).
                if (origin or '').lower() == ORIGIN_SYSTEM:
                    continue
                if not _locally_installed(addon_id):
                    continue
                inst = _installed_version(addon_id)
                if not inst:
                    continue
                cands = _repo_candidates(cur, addon_id)
                if not cands or _covers(cands, origin, inst):
                    continue
                better = _pick_repo(cands, inst)
                if not (better and _covers(cands, better, inst)):
                    # nothing cached carries the installed version yet ->
                    # the caller refreshes the repositories and retries
                    result.setdefault('stale', []).append(addon_id)
                    continue
                if better.lower() != origin.lower():
                    cur.execute('UPDATE installed SET origin = ? WHERE addonID = ?',
                                (better, addon_id))
                    result['fixed'][addon_id] = better
                    result.setdefault('corrected', []).append(addon_id)
                    _log('origin corrected: %s %s -> %s (installed %s)'
                         % (addon_id, origin, better, inst))
        conn.commit()

    except sqlite3.DatabaseError as e:
        result['error'] = 'Database error: %s' % e
        _log(result['error'])
        try:
            if conn:
                conn.rollback()
        except sqlite3.Error:
            pass
    finally:
        try:
            if conn:
                conn.close()
        except sqlite3.Error:
            pass

    return result


def snapshot_origins():
    """{addonID: origin} for every locally installed add-on that HAS an origin.

    Taken by the Addons33 rebuild (phase 1) from the old, still-working
    database so the links can be written back verbatim afterwards - a fresh
    Addons33.db has no repository listings cached, so fix_addons() alone
    cannot match anything right after a rebuild.
    """
    out = {}
    db_path = _find_addons_db()
    if not db_path:
        return out
    conn = None
    try:
        conn = _connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT addonID, origin FROM installed "
                    "WHERE origin IS NOT NULL AND origin != ''")
        for aid, origin in cur.fetchall():
            if aid and origin and _locally_installed(aid):
                out[aid] = origin
    except sqlite3.DatabaseError as e:
        _log('snapshot_origins db error: %s' % e)
    finally:
        try:
            if conn:
                conn.close()
        except sqlite3.Error:
            pass
    _log('snapshot_origins: %d origin(s) saved' % len(out))
    return out


def restore_origins(mapping):
    """Write a snapshot_origins() mapping back, in ONE transaction.

    Only fills rows whose origin is currently empty and whose add-on is local
    (never overrides what Kodi set itself). Returns {'fixed': {id: origin},
    'pending': [ids not registered yet], 'error': str|None}.
    """
    result = {'fixed': {}, 'pending': [], 'error': None}
    if not mapping:
        return result
    db_path = _find_addons_db()
    if not db_path:
        result['error'] = 'No Addons database found.'
        return result
    conn = None
    try:
        conn = _connect(db_path)
        cur = conn.cursor()
        for aid, origin in sorted(mapping.items()):
            if not aid or not origin or aid in SKIP_IDS:
                continue
            if not _locally_installed(aid):
                continue
            cur.execute('SELECT origin FROM installed WHERE addonID = ?', (aid,))
            row = cur.fetchone()
            if row is None:
                result['pending'].append(aid)
                continue
            if (row[0] or '') != '':
                continue
            cur.execute("UPDATE installed SET origin = ? "
                        "WHERE addonID = ? AND (origin IS NULL OR origin = '')",
                        (origin, aid))
            if cur.rowcount:
                result['fixed'][aid] = origin
        conn.commit()
    except sqlite3.DatabaseError as e:
        result['error'] = 'Database error: %s' % e
        try:
            if conn:
                conn.rollback()
        except sqlite3.Error:
            pass
    finally:
        try:
            if conn:
                conn.close()
        except sqlite3.Error:
            pass
    _log('restore_origins: %d restored, %d not registered yet%s'
         % (len(result['fixed']), len(result['pending']),
            (', error: %s' % result['error']) if result['error'] else ''))
    return result


def repo_cache_empty():
    """True when no repository listing is cached yet (fresh Addons33.db)."""
    db_path = _find_addons_db()
    if not db_path:
        return True
    conn = None
    try:
        conn = _connect(db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM addonlinkrepo')
        return (cur.fetchone() or [0])[0] == 0
    except sqlite3.DatabaseError:
        return True
    finally:
        try:
            if conn:
                conn.close()
        except sqlite3.Error:
            pass


def relink_with_repo_refresh(monitor=None, origins=None, budget=180, step=15):
    """Link empty origins, refreshing the repositories first when needed.

    1. restore a phase-1 snapshot (origins) verbatim, if given;
    2. fix_addons() from the cached repo listings (incl. the correction pass);
    3. if add-ons are still unmatched, or only matched a repo with an OLDER
       version than installed ("stale" - an out-of-date cached listing), run
       UpdateAddonRepos and retry every `step` s for up to `budget` s while
       Kodi refreshes the listings.
    Returns {'fixed': {...}, 'unmatched': [...], 'stale': [...]} (cumulative).
    """
    fixed = {}
    if origins:
        fixed.update(restore_origins(origins)['fixed'])
    res = fix_addons(None)
    fixed.update(res.get('fixed') or {})
    unmatched = list(res.get('unmatched') or [])
    stale = list(res.get('stale') or [])
    if not unmatched and not stale:
        return {'fixed': fixed, 'unmatched': [], 'stale': []}

    _log('%d unmatched, %d only in an out-of-date listing - refreshing '
         'repositories and retrying.' % (len(unmatched), len(stale)))
    xbmc.executebuiltin('UpdateAddonRepos')
    waited = 0
    while (unmatched or stale) and waited < budget:
        if monitor is not None:
            if monitor.waitForAbort(step):
                break
        else:
            xbmc.sleep(step * 1000)
        waited += step
        if origins:
            fixed.update(restore_origins(origins)['fixed'])
        res = fix_addons(None)
        fixed.update(res.get('fixed') or {})
        unmatched = [a for a in (res.get('unmatched') or []) if a not in fixed]
        stale = list(res.get('stale') or [])
    _log('relink done: %d linked, %d still without a repository, %d only in '
         'an older listing.' % (len(fixed), len(unmatched), len(stale)))
    return {'fixed': fixed, 'unmatched': unmatched, 'stale': stale}


def fix_addons_silent(addon_ids):
    """Targeted, exception-proof variant for use right after an install.
    A best-effort helper: failures are logged, never raised."""
    try:
        res = fix_addons(addon_ids)
        if res['error']:
            _log('silent fix skipped: %s' % res['error'])
        return res
    except Exception as e:  # noqa: BLE001 – must never break an install
        _log('silent fix crashed: %s' % e)
        return {'fixed': {}, 'unmatched': list(addon_ids), 'error': str(e)}


def set_origin(addon_id, repo_id):
    """Deterministically write installed.origin for a single add-on.

    Unlike fix_addons(), this does NOT require the repository's listing to be
    cached in addonlinkrepo/addons — the caller already knows which repo the
    add-on came from (e.g. the skin portal knows the user picked Kodi/CE/Piers),
    so we write that repo id straight into the origin column. This is the
    robust path for portal/zip installs where the repo listing may never have
    been fetched, which otherwise leaves origin empty and blocks all updates.

    Only touches a row whose origin is currently empty and whose add-on is
    physically present in the writable addons dir. Returns True on write.
    """
    if not addon_id or not repo_id:
        return False
    if not _locally_installed(addon_id):
        _log('set_origin skipped (not local): %s' % addon_id)
        return False

    db_path = _find_addons_db()
    if not db_path:
        _log('set_origin: no Addons database found')
        return False

    conn = None
    try:
        conn = _connect(db_path)
        cur = conn.cursor()
        if 'installed' not in _tables(cur):
            _log('set_origin: no installed table')
            return False
        cur.execute('SELECT origin FROM installed WHERE addonID = ?',
                    (addon_id,))
        row = cur.fetchone()
        if row is None:
            _log('set_origin: %s not yet registered' % addon_id)
            return False
        if (row[0] or '') != '':
            _log('set_origin: %s already has origin %s' % (addon_id, row[0]))
            return False
        cur.execute("UPDATE installed SET origin = ? "
                    "WHERE addonID = ? AND (origin IS NULL OR origin = '')",
                    (repo_id, addon_id))
        conn.commit()
        if cur.rowcount:
            _log('set_origin: %s -> %s' % (addon_id, repo_id))
            return True
        return False
    except sqlite3.DatabaseError as e:
        _log('set_origin db error: %s' % e)
        try:
            if conn:
                conn.rollback()
        except sqlite3.Error:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except sqlite3.Error:
            pass


def set_origin_silent(addon_id, repo_id):
    """Exception-proof wrapper for set_origin — never raises."""
    try:
        return set_origin(addon_id, repo_id)
    except Exception as e:  # noqa: BLE001
        _log('set_origin crashed: %s' % e)
        return False


# ---------------------------------------------------------------------------
# Interactive runner (menu entry)
# ---------------------------------------------------------------------------

def _is_coreelec():
    if os.path.isdir('/etc/coreelec'):
        return True
    try:
        with open('/etc/os-release') as f:
            return any('coreelec' in line.lower() for line in f)
    except OSError:
        return False


def _is_macos():
    try:
        return sys.platform == 'darwin'
    except Exception:
        return False


WIZARD_ID = 'plugin.program.ABUKARIMwizard'


def force_restart(reason=''):
    """3.2.16: every ABUKARIM restart goes through ABUKARIM Wizard >
    Maintenance > Force Close (plugin mode 18 = os._exit). A clean Quit /
    RestartApp hung on Kodi 22: shutdown waits for every Python script and
    the add-on services (ours included) did not stop within its timeout, so
    Kodi sat on "Stopping the application..." forever (log 2026-10-04 12:14).
    CoreELEC's systemd brings Kodi straight back after the exit; on macOS /
    desktop Kodi closes and is reopened by hand.
    If the wizard is missing or does not act within 5 s, exit directly - the
    same thing the wizard does.
    """
    _log('Force restart%s via ABUKARIM Wizard > Maintenance > Force Close'
         % (' (%s)' % reason if reason else ''))
    if not _is_coreelec():
        _notify_quit()
    xbmc.sleep(1500)          # let Kodi write pending settings / the notification show
    wiz = xbmcvfs.translatePath('special://home/addons/%s/addon.xml' % WIZARD_ID)
    if os.path.isfile(wiz):
        xbmc.executebuiltin('RunPlugin(plugin://%s/?mode=18)' % WIZARD_ID)
        xbmc.sleep(5000)
        _log('wizard Force Close did not exit Kodi - exiting directly')
    os._exit(1)


def _restart_kodi():
    """Kept for callers: now always the wizard force restart."""
    force_restart()


def _notify_quit():
    """Best-effort heads-up so a bare quit isn't mistaken for a crash."""
    try:
        xbmc.executebuiltin(
            'Notification(%s, %s, 4000)'
            % (TITLE, 'Closing Kodi to finish — please reopen it.'))
    except Exception:
        pass


def recommend_restart(message=None, title='ABUKARIM TOOLS',
                      yeslabel=None, nolabel=None):
    """Recommend — but never force — a restart so pending changes take effect.

    Used after repo linking, an in-place tools update, or a portal skin
    install. The repo linking is already written to the Addons DB by the time
    this is called, so declining loses nothing: Kodi reads the new origins on
    its next normal start, and the service re-applies linking on every boot as
    a safety net (see origin_fix.fix_addons run from service.py). Shows a
    dialog and restarts ONLY if the user agrees. Returns True only if the user
    accepted and a restart was triggered.
    """
    if message is None:
        message = ('A restart is recommended so the changes take effect.\n'
                   'يُنصح بإعادة التشغيل حتى تصبح التغييرات فعّالة.')
    if yeslabel is None:
        yeslabel = 'Restart now / أعد التشغيل الآن'
    if nolabel is None:
        nolabel = 'Later / لاحقاً'
    try:
        agreed = xbmcgui.Dialog().yesno(title, message,
                                        yeslabel=yeslabel, nolabel=nolabel)
    except Exception as e:
        _log('recommend_restart dialog failed: %s' % e)
        return False
    if not agreed:
        _log('Restart recommended — user chose Later.')
        return False
    _log('Restart recommended — user accepted.')
    xbmc.sleep(300)
    _restart_kodi()
    return True


def run():
    dialog = xbmcgui.Dialog()
    if not dialog.yesno(
            TITLE,
            'Scan for add-ons installed without a repository origin\n'
            '(zip / portal installs) and link them back to their repo\n'
            'so they show as installed and receive updates again?',
            yeslabel='Scan && fix', nolabel='Cancel'):
        return

    if repo_cache_empty():
        # Fresh Addons33.db: no repository listing cached yet, so nothing
        # could match. Refresh the repos and retry while Kodi fetches them.
        pd = xbmcgui.DialogProgress()
        pd.create(TITLE, 'Refreshing repositories... / تحديث المستودعات...')
        try:
            r = relink_with_repo_refresh(None, budget=120, step=10)
        finally:
            pd.close()
        res = {'fixed': r['fixed'], 'unmatched': r['unmatched'], 'error': None}
    else:
        res = fix_addons(None)

    if res['error']:
        dialog.ok(TITLE,
                  'Could not complete the fix:\n%s\n\n'
                  'If the database is corrupt, rebuild it first '
                  '(stop Kodi, delete Addons*.db, restart).' % res['error'])
        return

    fixed, unmatched = res['fixed'], res['unmatched']

    if not fixed and not unmatched:
        dialog.ok(TITLE, 'Nothing to fix – every locally installed add-on '
                         'already has a repository origin.')
        return

    lines = []
    if fixed:
        lines.append('[B]Linked to a repository (%d):[/B]' % len(fixed))
        lines += ['%s  →  %s' % (a, r) for a, r in sorted(fixed.items())]
    if unmatched:
        lines.append('')
        lines.append('[B]No repository carries these (%d) – left as-is:[/B]'
                     % len(unmatched))
        lines += sorted(unmatched)
    dialog.textviewer(TITLE, '\n'.join(lines))

    if fixed:
        # Kodi only uses the repaired origins for update checks after a
        # restart. Recommend one (don't force it) — the origins are already on
        # disk, so they take effect on the next normal start regardless.
        recommend_restart(
            message=('Repository links were repaired.\n'
                     'A restart is recommended so updates become active.\n'
                     'تم إصلاح روابط المستودعات.\n'
                     'يُنصح بإعادة التشغيل حتى تصبح التحديثات فعّالة.'))
