# -*- coding: utf-8 -*-
"""
remote_config.py - data that used to be hardcoded, served from the Piers repo.

Files live in the GitHub Pages repo under abukarim/ :

    abukarim/patches.json   extra / replacement patches + kill switches
    abukarim/portal.json    Add-on Portal catalog (ids, names, repos, icons)
    abukarim/presets.json   first-run presets (Full / Lite / ...)
    abukarim/config.json    misc flags (min tools version, notices ...)

Design rules (learned the hard way on Kodi 22 / Python 3.14):

  * load() NEVER touches the network. It reads the on-disk cache only, so it
    is safe from the patch watchdog, menu sweeps and any GUI code path.
  * refresh() is the only network call. It is run once per boot from the
    service thread (short timeout) and on demand from the Tools menu.
  * Every file has a built-in fallback in the caller, so an offline box, a
    404 or a broken JSON push simply means "use the shipped defaults".
  * A cached file is only replaced when the new download parses and its
    "schema" is one this version understands.
"""

import json
import os
import time
import urllib.error
import urllib.request

import xbmc
import xbmcvfs

BASE_URL = ('https://raw.githubusercontent.com/taiseer999/'
            'taiseer999Piers.github.io/master/abukarim/')

FILES = ('patches.json', 'portal.json', 'presets.json', 'config.json')
SUPPORTED_SCHEMA = 1
MAX_AGE = 6 * 3600            # refresh at most every 6 h unless forced

PROFILE = xbmcvfs.translatePath(
    'special://profile/addon_data/plugin.program.abukarimtools/')
CACHE_DIR = os.path.join(PROFILE, 'remote_cache')


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools Remote] %s' % msg, level)


def _path(name):
    return os.path.join(CACHE_DIR, name)


def load(name, default=None):
    """Cached copy of a remote file (dict) or `default`. No network."""
    try:
        with open(_path(name), 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get('schema', 1) <= SUPPORTED_SCHEMA:
            return data
    except Exception:
        pass
    return default


def age(name):
    try:
        return time.time() - os.path.getmtime(_path(name))
    except OSError:
        return None


def _fetch(name, timeout):
    url = BASE_URL + name + '?t=%d' % int(time.time() // 300)   # bust CDN cache every 5 min
    req = urllib.request.Request(url, headers={'User-Agent': 'AbukarimTools'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('not a JSON object')
    if int(data.get('schema', 1)) > SUPPORTED_SCHEMA:
        raise ValueError('schema %s newer than supported %d'
                         % (data.get('schema'), SUPPORTED_SCHEMA))
    return data


def refresh(force=False, timeout=6):
    """Download every remote file. Returns {name: 'updated'|'cached'|'missing'|error}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    result = {}
    for name in FILES:
        a = age(name)
        if not force and a is not None and a < MAX_AGE:
            result[name] = 'cached'
            continue
        try:
            data = _fetch(name, timeout)
            tmp = _path(name) + '.part'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _path(name))
            result[name] = 'updated'
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Not published (yet): drop any stale cache so defaults apply.
                try:
                    os.remove(_path(name))
                except OSError:
                    pass
                result[name] = 'missing'
            else:
                result[name] = 'http %s' % e.code
        except Exception as e:
            result[name] = 'error: %s' % e
    _log('refresh: %s' % result)
    return result


def flag(key, default=None):
    """Convenience accessor for config.json values."""
    cfg = load('config.json', {}) or {}
    return cfg.get(key, default)


def _vtuple(v):
    import re
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', str(v or '0')))


def boot_notices():
    """config.json consumers, called once per boot after refresh():

      "min_tools_version": "3.2.0.0"   -> nag (once per version) when older
      "notice": {"id": "2026-10-a", "en": "...", "ar": "..."}  -> shown once
    Notifications only - never a blocking dialog at boot.
    """
    import xbmcaddon
    import xbmcgui
    cfg = load('config.json', {}) or {}
    seen_path = os.path.join(PROFILE, 'notices_seen.json')
    try:
        with open(seen_path, 'r', encoding='utf-8') as f:
            seen = json.load(f)
    except Exception:
        seen = {}
    changed = False
    try:
        mine = xbmcaddon.Addon('plugin.program.abukarimtools').getAddonInfo('version')
    except Exception:
        mine = ''
    want = cfg.get('min_tools_version')
    if want and mine and _vtuple(mine) < _vtuple(want) and seen.get('min') != want:
        xbmcgui.Dialog().notification(
            'ABUKARIM TOOLS', 'Update available: %s -> %s' % (mine, want),
            xbmcgui.NOTIFICATION_WARNING, 8000)
        seen['min'] = want
        changed = True
    n = cfg.get('notice') or {}
    if n.get('id') and seen.get('notice') != n['id']:
        ar = 'ar' in (xbmc.getLanguage(xbmc.ISO_639_1) or '').lower()
        text = (n.get('ar') if ar else n.get('en')) or n.get('en') or n.get('ar')
        if text:
            xbmcgui.Dialog().notification('ABUKARIM TOOLS', text,
                                          xbmcgui.NOTIFICATION_INFO, 10000)
        seen['notice'] = n['id']
        changed = True
    if changed:
        try:
            os.makedirs(PROFILE, exist_ok=True)
            with open(seen_path, 'w', encoding='utf-8') as f:
                json.dump(seen, f)
        except OSError:
            pass
