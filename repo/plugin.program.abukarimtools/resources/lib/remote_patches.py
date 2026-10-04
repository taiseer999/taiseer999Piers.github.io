# -*- coding: utf-8 -*-
"""
remote_patches.py - merge patches published in abukarim/patches.json with the
built-in PATCHES list, so a fix reaches every box without a tools release.

patches.json (schema 1):

{
  "schema": 1,
  "kill": ["redlight_fixes",                      # a toggle id
           "plugin.video.prism",                  # every patch for an add-on
           "script.tinyppi:resources/lib/ui/fonts.py"],   # one target file
  "toggles": [["seren_fix", "Seren: Some Fix"]],  # extra checklist entries
  "patches": [
    {
      "id": "seren-provider-timeout",             # free text, for logs
      "addon_id": "plugin.video.seren",
      "rel_path": "resources/lib/modules/providers.py",   # always '/'
      "old_b64": "...", "new_b64": "...",         # or "old" / "new" as text
      "description": "Seren: shorter provider timeout",
      "toggle": "seren_fix",
      "min_version": "3.4.0", "max_version": "3.4.99",   # target add-on version
      "target_sha256": ["<sha of the unpatched upstream file>", ...],
      "not_found_ok": true
    }
  ]
}

Safety:
  * a remote entry can only use the same data operations as a built-in one
    (string replace, regex replace, write a text file from base64). It cannot
    point inject_source at a local file and cannot escape the add-on folder.
  * target_sha256 / min_version / max_version make an entry inert on any file
    it was not written against: a patch for 3.4.x never touches 3.5.0.
  * a malformed entry is skipped and logged; it never breaks the built-ins.
"""

import base64
import hashlib
import os
import re
import xml.etree.ElementTree as ET

import xbmc

from resources.lib import remote_config

_ALLOWED_KEYS = {
    'addon_id', 'rel_path', 'rel_path_alternates', 'old', 'new', 'old_b64',
    'new_b64', 'description', 'toggle', 'already_patched_check',
    'already_patched_check_b64', 'not_found_ok', 'obsolete_if_contains',
    'skip_if_present', 'inject_file', 'inject_content_b64', 'replace',
    'fallback_pattern', 'fallback_repl', 'count', 'regex_dotall', 'base',
    'min_version', 'max_version', 'target_sha256', 'supersedes', 'id',
    'json_edit', 'once',
}

_cache = {'mtime': None, 'patches': [], 'toggles': [], 'kill': set()}


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools RemotePatches] %s' % msg, level)


def _safe_rel(rel):
    rel = (rel or '').replace('\\', '/')
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts) or rel.startswith('/'):
        raise ValueError('unsafe rel_path %r' % rel)
    return os.path.join(*parts)


def _text(e, key):
    if key + '_b64' in e:
        return base64.b64decode(e[key + '_b64']).decode('utf-8')
    return e.get(key, '')


def _convert(e):
    unknown = set(e) - _ALLOWED_KEYS
    if unknown:
        raise ValueError('unknown keys %s' % sorted(unknown))
    if not e.get('addon_id') or not re.match(r'^[A-Za-z0-9_.\-]+$', e['addon_id']):
        raise ValueError('bad addon_id')
    p = {
        'addon_id': e['addon_id'],
        'rel_path': _safe_rel(e['rel_path']),
        'old': _text(e, 'old'),
        'new': _text(e, 'new'),
        'description': e.get('description') or e.get('id') or 'remote patch',
        '_remote': e.get('id') or e['rel_path'],
    }
    if e.get('rel_path_alternates'):
        p['rel_path_alternates'] = [_safe_rel(x) for x in e['rel_path_alternates']]
    if 'already_patched_check' in e or 'already_patched_check_b64' in e:
        p['already_patched_check'] = _text(e, 'already_patched_check')
    for k in ('toggle', 'not_found_ok', 'obsolete_if_contains', 'replace',
              'fallback_pattern', 'fallback_repl', 'count', 'supersedes',
              'min_version', 'max_version'):
        if k in e:
            p[k] = e[k]
    if e.get('skip_if_present'):
        p['skip_if_present'] = [_safe_rel(x) for x in e['skip_if_present']]
    if e.get('target_sha256'):
        shas = e['target_sha256']
        p['target_sha256'] = [shas] if isinstance(shas, str) else list(shas)
    if e.get('regex_dotall'):
        p['regex_flags'] = re.DOTALL
    if e.get('base') == 'addon_data':
        p['base'] = 'addon_data'
    if e.get('once'):
        if not e.get('id'):
            raise ValueError('"once" needs an "id"')
        p['once'] = True
    if e.get('json_edit'):
        ops = e['json_edit']
        if not isinstance(ops, list) or not all(isinstance(o, dict) for o in ops):
            raise ValueError('json_edit must be a list of objects')
        p['json_edit'] = ops
    if e.get('inject_file'):
        p['inject_file'] = True
        p['inject_content_b64'] = e.get('inject_content_b64', '')
    return p


def _reload():
    path = remote_config._path('patches.json')
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    if mtime == _cache['mtime']:
        return
    _cache.update(mtime=mtime, patches=[], toggles=[], kill=set())
    data = remote_config.load('patches.json', {}) or {}
    _cache['kill'] = set(data.get('kill') or [])
    for t in data.get('toggles') or []:
        try:
            _cache['toggles'].append((str(t[0]), str(t[1])))
        except Exception:
            pass
    for e in data.get('patches') or []:
        try:
            _cache['patches'].append(_convert(e))
        except Exception as ex:
            _log('skipping remote entry %r: %s' % (e.get('id') if isinstance(e, dict) else e, ex),
                 xbmc.LOGWARNING)
    if mtime:
        _log('loaded %d remote patches, %d kill rules'
             % (len(_cache['patches']), len(_cache['kill'])))


def _killed(p, kill, toggle_of):
    if not kill:
        return False
    rel = (p.get('rel_path') or '').replace(os.sep, '/')
    return (p['addon_id'] in kill
            or (toggle_of(p) or '') in kill
            or ('%s:%s' % (p['addon_id'], rel)) in kill
            or (p.get('_remote') or '') in kill)


def merged(builtin, toggle_of):
    """Built-ins minus killed ones, plus remote ones."""
    try:
        _reload()
    except Exception as e:
        _log('remote patch load failed: %s' % e, xbmc.LOGWARNING)
        return list(builtin)
    kill = _cache['kill']
    out = [p for p in builtin if not _killed(p, kill, toggle_of)]
    out += [p for p in _cache['patches'] if not _killed(p, kill, toggle_of)]
    return out


def extra_toggles():
    try:
        _reload()
    except Exception:
        return []
    return list(_cache['toggles'])


# ---------------------------------------------------------------------------
# guards used by patcher._apply_patch
# ---------------------------------------------------------------------------

def _vtuple(v):
    out = []
    for part in re.split(r'[.\-+~]', str(v or '')):
        out.append((0, int(part), '') if part.isdigit() else (1, 0, part))
    return tuple(out)


def addon_version(addon_path):
    try:
        return ET.parse(os.path.join(addon_path, 'addon.xml')).getroot().get('version', '')
    except Exception:
        return ''


def version_ok(patch, addon_path):
    lo, hi = patch.get('min_version'), patch.get('max_version')
    if not lo and not hi:
        return True, ''
    v = addon_version(addon_path)
    if not v:
        return True, ''
    if lo and _vtuple(v) < _vtuple(lo):
        return False, v
    if hi and _vtuple(v) > _vtuple(hi):
        return False, v
    return True, v


def sha_ok(patch, target):
    shas = patch.get('target_sha256')
    if not shas:
        return True
    try:
        with open(target, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return True      # missing file is reported by the normal path
    return digest.lower() in {s.lower() for s in shas}


# ---------------------------------------------------------------------------
# json_edit (3.2.6)
# ---------------------------------------------------------------------------
#
# "json_edit": [
#   {"match": {"guid": "guid-65582629"}, "set": {"label": "Continue"}},
#   {"match": {"label": "Old"}, "unset": ["disabled"]},
#   {"remove": {"path": "plugin://plugin.video.gone/"}},
#   {"append": {"label": "New", "path": "...", "guid": "guid-abk-1"},
#    "unless": {"guid": "guid-abk-1"}},              # idempotent append
#   {"insert": {...}, "before": {"label": "Power"}, "unless": {...}},
#   {"move": {"label": "Reboot"}, "before": {"label": "Power"}}
# ]
#
# match / remove / unless / before select dict items anywhere in the file
# (any depth) whose fields equal ALL the given values; a value starting with
# "~" is a substring test ("~plugin.video.dexhub"). Every op is idempotent,
# the file is only rewritten when something changed, and a skinvariables node
# that changed gets its skin's templates rebuilt when that skin is active.

def _matches(item, cond):
    if not isinstance(item, dict) or not cond:
        return False
    for k, v in cond.items():
        cur = item.get(k)
        if isinstance(v, str) and v.startswith('~'):
            if not isinstance(cur, str) or v[1:] not in cur:
                return False
        elif cur != v:
            return False
    return True


def _walk_lists(node):
    """Yield every list in the document (the containers items live in)."""
    if isinstance(node, list):
        yield node
        for x in node:
            for l in _walk_lists(x):
                yield l
    elif isinstance(node, dict):
        for v in node.values():
            for l in _walk_lists(v):
                yield l


def _find(doc, cond):
    for lst in _walk_lists(doc):
        for i, item in enumerate(lst):
            if _matches(item, cond):
                yield lst, i, item


def _exists(doc, cond):
    return any(True for _ in _find(doc, cond)) if cond else False


def _top_list(doc):
    if isinstance(doc, list):
        return doc
    for lst in _walk_lists(doc):
        return lst
    return None


def _json_ops(doc, ops):
    changed = 0
    for op in ops:
        if 'match' in op:
            for _l, _i, item in list(_find(doc, op['match'])):
                for k, v in (op.get('set') or {}).items():
                    if item.get(k) != v:
                        item[k] = v
                        changed += 1
                for k in op.get('unset') or []:
                    if k in item:
                        del item[k]
                        changed += 1
        elif 'remove' in op:
            hits = list(_find(doc, op['remove']))
            for lst, i, _item in sorted(hits, key=lambda h: -h[1]):
                del lst[i]
                changed += 1
        elif 'append' in op or 'insert' in op:
            new = op.get('append') or op.get('insert')
            if _exists(doc, op.get('unless') or new):
                continue
            if op.get('before'):
                hit = next(_find(doc, op['before']), None)
                if hit:
                    hit[0].insert(hit[1], dict(new))
                    changed += 1
                    continue
            lst = _top_list(doc)
            if lst is not None:
                lst.append(dict(new))
                changed += 1
        elif 'move' in op and op.get('before'):
            src = next(_find(doc, op['move']), None)
            dst = next(_find(doc, op['before']), None)
            if src and dst and src[0] is dst[0] and src[1] != dst[1] - 1:
                item = src[0].pop(src[1])
                j = src[0].index(dst[2])
                src[0].insert(j, item)
                changed += 1
    return changed


def apply_json_edit(patch, target):
    """Called from patcher._apply_patch. Returns (ok, message)."""
    import json as _json
    aid = patch['addon_id']
    if not os.path.isfile(target):
        if patch.get('not_found_ok'):
            return True, '[%s] %s not present – skipping (optional).' % (aid, patch['rel_path'])
        return False, '[%s] Target file not found: %s' % (aid, patch['rel_path'])
    try:
        with open(target, 'r', encoding='utf-8') as f:
            doc = _json.load(f)
    except Exception as e:
        return False, '[%s] %s is not valid JSON: %s' % (aid, patch['rel_path'], e)
    n = _json_ops(doc, patch['json_edit'])
    if not n:
        return True, '[%s] Already patched – skipping.' % aid
    tmp = target + '.abk.part'
    with open(tmp, 'w', encoding='utf-8') as f:
        _json.dump(doc, f, ensure_ascii=False, indent=4)
    os.replace(tmp, target)
    _after_json_change(target)
    return True, '[%s] Patched OK (json, %d change(s)): %s' % (aid, n, patch['description'])


def _after_json_change(target):
    """skinvariables node of the ACTIVE skin -> rebuild its templates."""
    norm = target.replace(os.sep, '/')
    marker = '/script.skinvariables/nodes/'
    if marker not in norm:
        return
    skin = norm.split(marker, 1)[1].split('/', 1)[0]
    if skin != xbmc.getSkinDir():
        return
    xbmc.executebuiltin('RunScript(script.skinvariables,run_executebuiltin='
                        'special://skin/shortcuts/skinvariables-build-templates.json,'
                        'use_rules)')
    _log('skinvariables rebuild queued for %s' % skin)


# ---------------------------------------------------------------------------
# once (3.2.7)
# ---------------------------------------------------------------------------
# A remote entry with "once": true is applied a single time per box and then
# skipped forever, keyed by its "id". To push a newer version of the same fix,
# publish it under a new id.

def _once_path():
    return os.path.join(remote_config.PROFILE, 'patches_once.json')


def _once_state():
    import json as _json
    try:
        with open(_once_path(), 'r', encoding='utf-8') as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def once_done(patch):
    return (patch.get('_remote') or '') in _once_state()


def mark_once(patch):
    import json as _json
    import time as _time
    key = patch.get('_remote') or ''
    if not key:
        return
    st = _once_state()
    st[key] = int(_time.time())
    try:
        os.makedirs(remote_config.PROFILE, exist_ok=True)
        tmp = _once_path() + '.part'
        with open(tmp, 'w', encoding='utf-8') as f:
            _json.dump(st, f, indent=1)
        os.replace(tmp, _once_path())
    except OSError as e:
        _log('could not record once-patch %s: %s' % (key, e), xbmc.LOGWARNING)
