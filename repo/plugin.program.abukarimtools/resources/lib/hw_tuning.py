# -*- coding: utf-8 -*-
"""
hw_tuning.py - size Kodi's video cache to the box it is running on.

3.2.8: since Kodi 21 the cache lives in the GUI settings (Settings > Services
> Caching: filecache.memorysize / filecache.readfactor / filecache.buffermode).
The <cache> block of advancedsettings.xml is IGNORED - the 2026-10-03 log of a
box whose advancedsettings asked for 200 MB / readfactor 20 shows
"Buffer Mode: 0, Memory Size: 256 MB, Read Factor: adaptive". So the values
are now written with JSON-RPC Settings.SetSettingValue, snapped to whatever
options/range this Kodi build offers for each setting.

    RAM >= 3.5 GB  -> 200 MB (never lowers a bigger current value), 20x
    RAM >= 1.8 GB  -> 100 MB, 10x
    otherwise      ->  50 MB, 4x

Buffer mode is left alone (Kodi's default already caches internet streams,
which is what every Piers video add-on plays).
"""

import json
import re

import xbmc
import xbmcgui

from resources.lib.i18n import T

TITLE = 'ABUKARIM – Device Tuning'
S_MEM = 'filecache.memorysize'
S_RF = 'filecache.readfactor'

TIERS = [
    (3500, 200, 20, 'high'),
    (1800, 100, 10, 'mid'),
    (0,     50,  4, 'low'),
]


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools HwTuning] %s' % msg, level)


def _rpc(method, params=None):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(req)))
    except Exception:
        return {}


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def ram_mb():
    m = re.search(r'MemTotal:\s+(\d+)\s*kB', _read('/proc/meminfo'))
    if m:
        return int(m.group(1)) // 1024
    lab = xbmc.getInfoLabel('System.Memory(total)') or ''
    m = re.search(r'([\d.]+)\s*([GM])B', lab, re.I)
    if m:
        v = float(m.group(1))
        return int(v * 1024) if m.group(2).upper() == 'G' else int(v)
    return 0


def soc():
    """Human readable board / CPU (best effort, never a raw label name)."""
    dt = _read('/proc/device-tree/model').strip('\x00 \n')
    if dt:
        return dt
    m = re.search(r'^Hardware\s*:\s*(.+)$', _read('/proc/cpuinfo'), re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r'^model name\s*:\s*(.+)$', _read('/proc/cpuinfo'), re.M)
    if m:
        return m.group(1).strip()
    for lab in ('System.CPUInfo', 'System.FriendlyName'):
        v = (xbmc.getInfoLabel(lab) or '').strip()
        if v and v.lower() != lab.lower() and v.lower() != 'busy':
            return v
    for cond, name in (('System.Platform.OSX', 'macOS'),
                       ('System.Platform.Android', 'Android'),
                       ('System.Platform.Windows', 'Windows'),
                       ('System.Platform.Linux', 'Linux')):
        if xbmc.getCondVisibility(cond):
            return name
    return '?'


def _setting_defs():
    """{id: definition} for the two cache settings, from this Kodi build."""
    res = _rpc('Settings.GetSettings', {'level': 'expert'})
    out = {}
    for s in ((res.get('result') or {}).get('settings') or []):
        if s.get('id') in (S_MEM, S_RF):
            out[s['id']] = s
    return out


def _snap(defn, want):
    """Nearest value Kodi accepts for this setting."""
    opts = defn.get('options')
    if isinstance(opts, list) and opts:
        vals = [o.get('value') for o in opts if isinstance(o.get('value'), int)]
        vals = [v for v in vals if v > 0] or vals
        if vals:
            return min(vals, key=lambda v: abs(v - want))
    lo, hi = defn.get('minimum'), defn.get('maximum')
    step = defn.get('step') or 1
    v = want
    if isinstance(lo, int):
        v = max(lo, v)
    if isinstance(hi, int):
        v = min(hi, v)
    if isinstance(lo, int) and step:
        v = lo + int(round((v - lo) / float(step))) * step
    return v


def _rf_scale(defn):
    """Kodi stores the read factor as x100 (400 = 4x); detect, default x100."""
    opts = defn.get('options') or []
    vals = [o.get('value') for o in opts if isinstance(o.get('value'), int)]
    if vals and max(vals) <= 50:
        return 1
    if isinstance(defn.get('maximum'), int) and defn['maximum'] <= 50:
        return 1
    return 100


def current():
    defs = _setting_defs()
    mem = (defs.get(S_MEM) or {}).get('value')
    rf_def = defs.get(S_RF) or {}
    rf = rf_def.get('value')
    scale = _rf_scale(rf_def) if rf_def else 100
    return mem, (rf / float(scale) if isinstance(rf, int) else None), defs


def recommend(mb=None, cur_mem=None):
    mb = ram_mb() if mb is None else mb
    for floor, size, rf, name in TIERS:
        if mb >= floor:
            if name == 'high' and isinstance(cur_mem, int) and cur_mem > size:
                size = cur_mem                 # never shrink a big box's cache
            return {'ram_mb': mb, 'memorysize': size, 'readfactor': rf, 'tier': name}
    return None


def _targets(rec, defs):
    t = {}
    if S_MEM in defs:
        t[S_MEM] = _snap(defs[S_MEM], rec['memorysize'])
    if S_RF in defs:
        t[S_RF] = _snap(defs[S_RF], rec['readfactor'] * _rf_scale(defs[S_RF]))
    return t


def apply(rec=None):
    """Write the recommendation. Returns True when a setting changed."""
    cur_mem, _cur_rf, defs = current()
    if not defs:
        _log('cache settings not exposed by this Kodi build - nothing done',
             xbmc.LOGWARNING)
        return False
    rec = rec or recommend(cur_mem=cur_mem)
    changed = False
    for sid, val in _targets(rec, defs).items():
        if defs[sid].get('value') == val:
            continue
        r = _rpc('Settings.SetSettingValue', {'setting': sid, 'value': val})
        if r.get('result') is True or r.get('result') == 'OK':
            changed = True
            _log('%s -> %s' % (sid, val))
        else:
            _log('%s -> %s refused: %s' % (sid, val, r.get('error')), xbmc.LOGWARNING)
    if changed:
        _log('cache tuned for %d MB RAM (%s tier)' % (rec['ram_mb'], rec['tier']))
    return changed


def auto():
    """Silent first-run step."""
    try:
        if apply():
            mem, _rf, _d = current()
            xbmcgui.Dialog().notification(
                TITLE, T(30540) % (mem or 0), xbmcgui.NOTIFICATION_INFO, 4000)
            return True
    except Exception as e:
        _log('auto tuning failed: %s' % e, xbmc.LOGWARNING)
    return False


def run():
    """Menu entry: show what was detected, apply on confirm."""
    cur_mem, cur_rf, defs = current()
    rec = recommend(cur_mem=cur_mem)
    tgt = _targets(rec, defs) if defs else {}
    scale = _rf_scale(defs[S_RF]) if S_RF in defs else 100
    t_mem = tgt.get(S_MEM, rec['memorysize'])
    t_rf = tgt.get(S_RF, rec['readfactor'] * scale) / float(scale)
    msg = T(30541) % (soc(), rec['ram_mb'], cur_mem or 0, int(round(cur_rf or 0)),
                      t_mem, int(round(t_rf)))
    if not defs:
        xbmcgui.Dialog().ok(TITLE, msg)
        return
    if all(defs[k].get('value') == v for k, v in tgt.items()):
        xbmcgui.Dialog().ok(TITLE, msg + '[CR][CR]' + T(30542))
        return
    if xbmcgui.Dialog().yesno(TITLE, msg):
        if apply(rec):
            try:
                from resources.lib import origin_fix
                origin_fix.recommend_restart(message=T(30543))
            except Exception:
                xbmcgui.Dialog().ok(TITLE, T(30543))
