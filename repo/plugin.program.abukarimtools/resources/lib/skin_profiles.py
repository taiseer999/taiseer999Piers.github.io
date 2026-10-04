# -*- coding: utf-8 -*-
"""
skin_profiles.py - per-skin "Piers profile" packages.

A profile is a small zip that carries everything that makes a skin look like
the Piers build: skin settings, skinshortcuts menus, skinvariables nodes and
view types. It is referenced from skins.json:

    {"id": "skin.arctic.fuse.3", ..., "profile": "https://.../af3-profile.zip",
     "profile_sha256": "<sha256 of that zip>"}

Layout inside the zip (paths relative to userdata/):

    profile.json                                   {"skin": id, "created": .., "tools": ..}
    addon_data/<skin>/settings.xml                 (and anything else in that folder)
    addon_data/script.skinshortcuts/<skin>*        (DATA.xml, .properties, .userdata.json)
    addon_data/script.skinvariables/nodes/<skin>/*
    addon_data/script.skinvariables/<skin>-viewtypes.json

Nothing outside those paths is ever written. Before overwriting, the current
files are saved to addon_data/plugin.program.abukarimtools/profile_backups/.

export_current() builds such a zip from the box you are sitting at (with
dev-machine paths rewritten to special://home/), ready to upload to the repo.
"""

import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.request
import zipfile

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

USERDATA = xbmcvfs.translatePath('special://profile/')
ADDON_DATA = os.path.join(USERDATA, 'addon_data')
TOOLS_DATA = os.path.join(ADDON_DATA, 'plugin.program.abukarimtools')
STATE_FILE = os.path.join(TOOLS_DATA, 'profiles_applied.json')
BACKUP_DIR = os.path.join(TOOLS_DATA, 'profile_backups')
EXPORT_DIR = os.path.join(TOOLS_DATA, 'profile_exports')
TITLE = 'ABUKARIM – Skin Profiles'

_HOME_RAW = [
    re.compile(r'/Users/[^/"<>]+/Library/Application Support/Kodi/', re.I),
    re.compile(r'/home/[^/"<>]+/\.kodi/', re.I),
    re.compile(r'/storage/\.kodi/', re.I),
    re.compile(r'[A-Za-z]:\\\\?Users\\\\?[^\\"<>]+\\\\?AppData\\\\?Roaming\\\\?Kodi\\\\?', re.I),
]
_HOME_ENC = [
    re.compile(r'%2fUsers%2f[^%"<>/&]+%2fLibrary%2fApplication(?:%20|\+)Support%2fKodi%2f', re.I),
    re.compile(r'%2fhome%2f[^%"<>/&]+%2f\.kodi%2f', re.I),
    re.compile(r'%2fstorage%2f\.kodi%2f', re.I),
]


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools Profiles] %s' % msg, level)


# ---------------------------------------------------------------------------
# path policy
# ---------------------------------------------------------------------------

def _allowed(member, skin_id):
    """True when a zip member may be written for this skin."""
    m = member.replace('\\', '/')
    if m.startswith('/') or '..' in m.split('/'):
        return False
    if m == 'profile.json':
        return True
    pre = (
        'addon_data/%s/' % skin_id,
        'addon_data/script.skinvariables/nodes/%s/' % skin_id,
    )
    if m.startswith(pre):
        return True
    if m == 'addon_data/script.skinvariables/%s-viewtypes.json' % skin_id:
        return True
    if m.startswith('addon_data/script.skinshortcuts/'):
        base = m.rsplit('/', 1)[-1]
        return '/' not in m[len('addon_data/script.skinshortcuts/'):] and \
            base.startswith(skin_id) and not base.endswith(('.hash', '.hashes'))
    return False


def _owned_files(skin_id):
    """Absolute paths of the files that make up this skin's profile on the box."""
    out = []
    d = os.path.join(ADDON_DATA, skin_id)
    if os.path.isdir(d):
        for dp, _dn, fns in os.walk(d):
            out += [os.path.join(dp, f) for f in fns]
    d = os.path.join(ADDON_DATA, 'script.skinvariables', 'nodes', skin_id)
    if os.path.isdir(d):
        for dp, _dn, fns in os.walk(d):
            out += [os.path.join(dp, f) for f in fns]
    vt = os.path.join(ADDON_DATA, 'script.skinvariables', '%s-viewtypes.json' % skin_id)
    if os.path.isfile(vt):
        out.append(vt)
    ss = os.path.join(ADDON_DATA, 'script.skinshortcuts')
    if os.path.isdir(ss):
        for f in os.listdir(ss):
            if f.startswith(skin_id) and not f.endswith(('.hash', '.hashes')):
                out.append(os.path.join(ss, f))
    return [p for p in out if os.path.isfile(p)]


def _rel(p):
    return os.path.relpath(p, USERDATA).replace(os.sep, '/')


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def _state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st):
    try:
        os.makedirs(TOOLS_DATA, exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f, indent=1)
    except Exception as e:
        _log('state save failed: %s' % e, xbmc.LOGWARNING)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _download(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'AbukarimTools'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _backup(skin_id):
    files = _owned_files(skin_id)
    if not files:
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, '%s-%s.zip' % (skin_id, time.strftime('%Y%m%d-%H%M%S')))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, _rel(p))
    # keep the 5 newest per skin
    olds = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(skin_id + '-'))
    for f in olds[:-5]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except OSError:
            pass
    return path


def _clear_shortcut_hashes(skin_id):
    ss = os.path.join(ADDON_DATA, 'script.skinshortcuts')
    if not os.path.isdir(ss):
        return
    for f in os.listdir(ss):
        if f.startswith(skin_id) and f.endswith(('.hash', '.hashes')):
            try:
                os.remove(os.path.join(ss, f))
            except OSError:
                pass


def apply_from_bytes(skin_id, payload, source='', ask=True):
    """Install a profile zip (bytes) for skin_id. Returns True on success."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        _log('profile for %s is not a zip' % skin_id, xbmc.LOGWARNING)
        return False
    members = [i for i in zf.infolist() if not i.is_dir()]
    allowed = [i for i in members if _allowed(i.filename, skin_id)]
    rejected = [i.filename for i in members if i not in allowed]
    if rejected:
        _log('profile %s: ignored %d member(s) outside the skin scope: %s'
             % (skin_id, len(rejected), rejected[:5]), xbmc.LOGWARNING)
    if not [i for i in allowed if i.filename != 'profile.json']:
        _log('profile %s: nothing to install' % skin_id, xbmc.LOGWARNING)
        return False
    if ask and _owned_files(skin_id):
        if not xbmcgui.Dialog().yesno(TITLE, T(30530) % skin_id):
            return False
    bk = _backup(skin_id)
    if bk:
        _log('backed up current %s profile to %s' % (skin_id, bk))
    for info in allowed:
        if info.filename == 'profile.json':
            continue
        dest = os.path.join(USERDATA, *info.filename.split('/'))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + '.abk.part'
        with zf.open(info) as s, open(tmp, 'wb') as d:
            d.write(s.read())
        os.replace(tmp, dest)
    _clear_shortcut_hashes(skin_id)
    st = _state()
    st[skin_id] = {'sha256': hashlib.sha256(payload).hexdigest(),
                   'source': source, 'applied': int(time.time())}
    _save_state(st)
    _log('profile applied for %s (%d files)' % (skin_id, len(allowed)))
    return True


def apply_for_item(item, first_run=False):
    """Called by the Skin Installer after a skin was extracted.

    item is the skins.json entry. Does nothing when it has no "profile".
    Skips a profile that is already applied (same sha256) unless the user's
    files are gone.
    """
    url = (item or {}).get('profile')
    skin_id = (item or {}).get('id')
    if not url or not skin_id:
        return False
    want = (item.get('profile_sha256') or '').lower()
    prev = _state().get(skin_id, {})
    if want and prev.get('sha256') == want and _owned_files(skin_id):
        _log('profile for %s already applied' % skin_id)
        return True
    try:
        payload = _download(url)
    except Exception as e:
        _log('profile download failed for %s: %s' % (skin_id, e), xbmc.LOGWARNING)
        return False
    if want and hashlib.sha256(payload).hexdigest() != want:
        _log('profile sha256 mismatch for %s - refusing' % skin_id, xbmc.LOGERROR)
        return False
    return apply_from_bytes(skin_id, payload, source=url, ask=not first_run)


def _skin_of(payload, fallback_name=''):
    """Skin id a profile zip belongs to: profile.json, else its members."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        return None
    try:
        meta = json.loads(zf.read('profile.json').decode('utf-8'))
        if meta.get('skin'):
            return meta['skin']
    except Exception:
        pass
    for n in zf.namelist():
        m = re.match(r'^addon_data/(skin\.[^/]+)/', n) or \
            re.match(r'^addon_data/script\.skinvariables/nodes/(skin\.[^/]+)/', n)
        if m:
            return m.group(1)
    m = re.match(r'^(skin\.[A-Za-z0-9_.]+?)-(?:profile|\d{8})', os.path.basename(fallback_name))
    return m.group(1) if m else None


def _read_any(path):
    """Bytes of a local or VFS (smb://, nfs://, usb ...) file."""
    if os.path.isfile(path):
        with open(path, 'rb') as f:
            return f.read()
    f = xbmcvfs.File(path)
    try:
        return bytes(f.readBytes())
    finally:
        f.close()


def restore_backup():
    """Menu: put a profile back - an automatic backup, one of your exports,
    or any profile zip picked from a folder / USB / network share.

    3.2.8: the first version only listed profile_backups/ (made automatically
    before a profile is applied), so a profile you had just exported never
    showed up and the screen said "no backups" (video 2026-10-03 20:46)."""
    entries = [(T(30537), None)]
    for folder, tag in ((EXPORT_DIR, T(30538)), (BACKUP_DIR, T(30539))):
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder), reverse=True):
                if f.endswith('.zip'):
                    entries.append(('%s  %s' % (tag, f), os.path.join(folder, f)))
    idx = xbmcgui.Dialog().select(TITLE, [e[0] for e in entries])
    if idx < 0:
        return
    path = entries[idx][1]
    if path is None:
        path = xbmcgui.Dialog().browse(1, T(30537), 'files', '.zip')
        if not path:
            return
    try:
        payload = _read_any(path)
    except Exception as e:
        _log('cannot read %s: %s' % (path, e), xbmc.LOGWARNING)
        xbmcgui.Dialog().ok(TITLE, T(30533))
        return
    skin_id = _skin_of(payload, path)
    if not skin_id:
        xbmcgui.Dialog().ok(TITLE, T(30533))
        return
    if not xbmcgui.Dialog().yesno(TITLE, T(30530) % skin_id):
        return
    ok = apply_from_bytes(skin_id, payload, source=path, ask=False)
    xbmcgui.Dialog().notification(TITLE, T(30532) if ok else T(30533))
    if ok and xbmc.getSkinDir() == skin_id:
        xbmc.executebuiltin('ReloadSkin()')


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def _portable(data):
    """Rewrite dev-machine Kodi paths to special://home/ in text files."""
    try:
        txt = data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    for rx in _HOME_RAW:
        txt = rx.sub('special://home/', txt)
    for rx in _HOME_ENC:
        txt = rx.sub(lambda m: 'special%3A%2F%2Fhome%2F' if '%2F' in m.group(0)
                     else 'special%3a%2f%2fhome%2f', txt)
    return txt.encode('utf-8')


def export_current():
    skin_id = xbmc.getSkinDir()
    files = _owned_files(skin_id)
    if not files:
        xbmcgui.Dialog().ok(TITLE, T(30534) % skin_id)
        return None
    os.makedirs(EXPORT_DIR, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M')
    name = '%s-profile-%s.zip' % (skin_id, stamp)
    path = os.path.join(EXPORT_DIR, name)
    try:
        import xbmcaddon
        tools_ver = xbmcaddon.Addon('plugin.program.abukarimtools').getAddonInfo('version')
        skin_ver = xbmcaddon.Addon(skin_id).getAddonInfo('version')
    except Exception:
        tools_ver = skin_ver = ''
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('profile.json', json.dumps(
            {'skin': skin_id, 'skin_version': skin_ver, 'tools': tools_ver,
             'created': time.strftime('%Y-%m-%dT%H:%M:%S')}, indent=1))
        for p in sorted(files):
            with open(p, 'rb') as f:
                zf.writestr(_rel(p), _portable(f.read()))
    with open(path, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    snippet = ('"profile": "https://raw.githubusercontent.com/taiseer999/'
               'taiseer999Piers.github.io/master/profiles/%s",\n'
               '"profile_sha256": "%s"' % (name, sha))
    # Optionally copy somewhere reachable (USB, SMB share ...).
    dest = xbmcgui.Dialog().browse(3, T(30535), 'files', '', False, False, '')
    if dest:
        try:
            xbmcvfs.copy(path, os.path.join(dest, name) if '://' not in dest
                         else dest.rstrip('/') + '/' + name)
        except Exception as e:
            _log('copy to %s failed: %s' % (dest, e), xbmc.LOGWARNING)
    xbmcgui.Dialog().textviewer(
        TITLE, T(30536) % (len(files), path, snippet))
    return path
