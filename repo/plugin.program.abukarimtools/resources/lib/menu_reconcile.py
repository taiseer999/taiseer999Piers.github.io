# -*- coding: utf-8 -*-
"""
menu_reconcile.py - hide menu items / widgets whose add-on is not installed,
and bring them back the moment it is.

The build ships one set of menus for every skin, but the video add-ons are
optional (Add-on Portal / presets). A menu entry or widget that points at a
missing plugin shows an empty row or an "add-on not found" error.

  * skinshortcuts DATA.xml items get a static System.HasAddon(<id>) visible
    condition at build time (make_build.py) - nothing to do at runtime.
  * skinshortcuts v3 <skin>.userdata.json (Arctic Zephyr Rounded) items have
    a "visible" field: System.HasAddon(<id>) is added there once (idempotent,
    survives later menu edits, no runtime toggling needed).
  * skinvariables nodes (Arctic Fuse 2/3) have no visibility field, so this
    module flips their "disabled" flag ('True' / removed) instead.

Only items this module disabled itself are ever re-enabled: it tags them with
"abk_hidden": [<missing ids>]. An item the user disabled by hand is never
touched. Every write is content-compared, so a settled box writes nothing.
"""

import json
import os
import re

import xbmc
import xbmcvfs

ADDON_DATA = xbmcvfs.translatePath('special://profile/addon_data/')
SV_NODES = os.path.join(ADDON_DATA, 'script.skinvariables', 'nodes')
SS_DIR = os.path.join(ADDON_DATA, 'script.skinshortcuts')

_REF_RE = re.compile(
    r'(?:plugin://|RunScript\(|RunAddon\(|InstallAddon\(|Addon\.OpenSettings\()'
    r'\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_\-]+)+)')
_CORE = ('xbmc.', 'kodi.', 'resource.language.')
_TAG = 'abk_hidden'
_STRING_KEYS = ('path', 'target', 'action', 'onclick', 'widget_path', 'widgetPath')


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools MenuReconcile] %s' % msg, level)


def addon_present(aid):
    """Installed AND enabled.

    3.2.4: not System.HasAddon() for mixed-case ids - Kodi lowercases
    condition strings, so 'plugin.program.ABUKARIMwizard' never matched and
    the AF3 power tray's Force Close was hidden although the wizard is
    installed (same root cause as wizard_runner 3.1.3). JSON-RPC keeps case.
    """
    if aid == aid.lower():
        return bool(xbmc.getCondVisibility('System.HasAddon(%s)' % aid))
    try:
        req = {'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddonDetails',
               'params': {'addonid': aid, 'properties': ['enabled']}}
        res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
        addon = (res.get('result') or {}).get('addon')
        if addon is not None:
            return bool(addon.get('enabled', True))
    except Exception:
        pass
    return False


def _installed(aid, cache):
    if aid not in cache:
        cache[aid] = addon_present(aid)
    return cache[aid]


def _refs(item):
    """Add-on ids referenced by THIS item's own fields (not nested children)."""
    texts = []
    for k, v in item.items():
        if isinstance(v, str) and (k in _STRING_KEYS or 'plugin://' in v):
            texts.append(v)
    for a in item.get('actions') or []:
        if isinstance(a, dict):
            texts += [v for v in a.values() if isinstance(v, str)]
        elif isinstance(a, str):
            texts.append(a)
    ids = []
    for t in texts:
        for m in _REF_RE.finditer(t):
            aid = m.group(1)
            if not aid.startswith(_CORE) and aid not in ids:
                ids.append(aid)
    return ids


def _is_off(v):
    return v is True or (isinstance(v, str) and v.lower() == 'true')


def _walk_visible(node, stats):
    """skinshortcuts v3: AND System.HasAddon(<id>) into each item's visible."""
    if isinstance(node, list):
        for x in node:
            _walk_visible(x, stats)
        return
    if not isinstance(node, dict):
        return
    if 'name' in node:
        # mixed-case ids can't be expressed as a skin condition (Kodi
        # lowercases it and it would never match) - leave those unguarded
        ids = [a for a in _refs(node) if a == a.lower()]
        cur = node.get('visible') or ''
        add = [a for a in ids if 'System.HasAddon(%s)' % a not in cur]
        if add:
            cond = ' + '.join('System.HasAddon(%s)' % a for a in add)
            node['visible'] = '%s + [%s]' % (cond, cur) if cur else cond
            stats['hidden'] += 1
    for v in node.values():
        if isinstance(v, (list, dict)):
            _walk_visible(v, stats)


def _walk(node, cache, stats):
    if isinstance(node, list):
        for x in node:
            _walk(x, cache, stats)
        return
    if not isinstance(node, dict):
        return
    ids = _refs(node)
    if ids:
        missing = sorted(a for a in ids if not _installed(a, cache))
        tagged = node.get(_TAG)
        # 3.2.3: the tag MUST be a plain string. skinvariables hands every
        # field of an item to ListItem.setProperties(), which only accepts
        # str - the list stored by 3.2.0-3.2.2 made the whole menu fail
        # ("Skin Variables error", 0 items; log 2026-10-03 09:40). Old list
        # tags are rewritten here.
        if isinstance(tagged, list):
            tagged_set = set(tagged)
            legacy = True
        elif isinstance(tagged, str):
            tagged_set = set(t for t in tagged.split(',') if t)
            legacy = False
        else:
            tagged_set, legacy = None, False
        tag_value = ','.join(missing)
        if missing:
            if tagged_set is None and not _is_off(node.get('disabled')):
                node['disabled'] = 'True'          # skinvariables do_toggle style
                node[_TAG] = tag_value
                stats['hidden'] += 1
            elif tagged_set is not None and (legacy or tagged_set != set(missing)):
                node[_TAG] = tag_value
                stats['touched'] += 1
        elif tagged_set is not None:
            node.pop(_TAG, None)
            node.pop('disabled', None)
            stats['shown'] += 1
    for v in node.values():
        if isinstance(v, (list, dict)):
            _walk(v, cache, stats)


def _process(path, cache):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        data = json.loads(raw)
    except Exception:
        return None
    stats = {'hidden': 0, 'shown': 0, 'touched': 0}
    if path.endswith('.userdata.json'):
        _walk_visible(data, stats)
    else:
        _walk(data, cache, stats)
    if not any(stats.values()):
        return None
    tmp = path + '.abk.part'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)
    return stats


def _targets():
    """[(skin_id, path)] for every file we manage."""
    out = []
    if os.path.isdir(SV_NODES):
        for skin in os.listdir(SV_NODES):
            d = os.path.join(SV_NODES, skin)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith('.json'):
                        out.append((skin, os.path.join(d, f)))
    if os.path.isdir(SS_DIR):
        for f in os.listdir(SS_DIR):
            if f.endswith('.userdata.json'):
                out.append((f[:-len('.userdata.json')], os.path.join(SS_DIR, f)))
    return out


def _rebuild_current(changed_skins):
    skin = xbmc.getSkinDir()
    if skin not in changed_skins:
        return False
    tpl = xbmcvfs.translatePath('special://skin/shortcuts/skinvariables-build-templates.json')
    if os.path.isfile(tpl):
        xbmc.executebuiltin('RunScript(script.skinvariables,run_executebuiltin='
                            'special://skin/shortcuts/skinvariables-build-templates.json,'
                            'use_rules)')
        _log('skinvariables rebuild queued for %s' % skin)
        return True
    # skinshortcuts: drop the hash so the menu is regenerated on next load
    for f in os.listdir(SS_DIR) if os.path.isdir(SS_DIR) else []:
        if f.startswith(skin) and (f.endswith('.hash') or f.endswith('.hashes')):
            try:
                os.remove(os.path.join(SS_DIR, f))
            except OSError:
                pass
    _log('skinshortcuts hash cleared for %s (rebuilds on next skin load)' % skin)
    return True


def run(rebuild=False):
    """Reconcile every managed file. Returns {'hidden','shown','files','skins'}."""
    cache = {}
    total = {'hidden': 0, 'shown': 0, 'files': 0, 'skins': set()}
    for skin, path in _targets():
        try:
            st = _process(path, cache)
        except Exception as e:
            _log('%s: %s' % (path, e), xbmc.LOGWARNING)
            continue
        if st:
            total['files'] += 1
            total['hidden'] += st['hidden']
            total['shown'] += st['shown']
            total['skins'].add(skin)
    if total['files']:
        _log('hidden %(hidden)d / restored %(shown)d items in %(files)d files' % total)
        if rebuild:
            _rebuild_current(total['skins'])
    return total
