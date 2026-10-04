# -*- coding: utf-8 -*-
"""
presets.py - one question at the start of setup instead of nine checkboxes.

A preset pre-ticks the Add-on Portal and can pre-set the patch checklist.
The list comes from abukarim/presets.json when published, else DEFAULTS:

{
  "schema": 1,
  "presets": [
    {"id": "full", "name": ["Full", "كامل"], "desc": ["...", "..."],
     "addons": ["plugin.video.seren", ...],          # "*" = whole catalog
     "patches_off": ["tinyppi_classic"]}              # optional toggle ids
  ]
}
The user can still change the ticks in the portal; "custom" ticks nothing.
"""

import os

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

DEFAULTS = [
    {'id': 'full', 'name': ['Full', 'كامل'],
     'desc': ['Every video add-on in the portal - the complete Piers experience.',
              'كل إضافات الفيديو - تجربة بيرز الكاملة.'],
     'addons': ['*']},
    {'id': 'lite', 'name': ['Lite', 'خفيف'],
     'desc': ['Fen Light+, YouTube and Last Played only - fastest boot, least to maintain.',
              'فن لايت+ ويوتيوب وآخر ما شوهد فقط - أسرع إقلاع وأقل صيانة.'],
     'addons': ['plugin.video.fenlight', 'plugin.video.youtube', 'plugin.video.last_played']},
    {'id': 'plex', 'name': ['Plex / Emby', 'بلكس / إمبي'],
     'desc': ['For your own media server: DPlex and Dex Hub plus Last Played.',
              'لسيرفر الوسائط الخاص بك: DPlex و Dex Hub مع آخر ما شوهد.'],
     'addons': ['plugin.video.dplex', 'plugin.video.dexhub', 'plugin.video.last_played']},
    {'id': 'custom', 'name': ['Custom', 'مخصص'],
     'desc': ['Nothing pre-selected - pick each add-on yourself.',
              'بدون تحديد مسبق - اختر كل إضافة بنفسك.'],
     'addons': []},
]

STATE = os.path.join(xbmcvfs.translatePath(
    'special://profile/addon_data/plugin.program.abukarimtools/'), 'preset.txt')


def _arabic():
    return 'ar' in (xbmc.getLanguage(xbmc.ISO_639_1) or '').lower()


def _pick(pair):
    if isinstance(pair, (list, tuple)):
        return pair[1] if _arabic() and len(pair) > 1 else pair[0]
    return pair or ''


def presets():
    try:
        from resources.lib import remote_config
        data = remote_config.load('presets.json', {}) or {}
        lst = [p for p in data.get('presets') or [] if p.get('id')]
        if lst:
            return lst
    except Exception:
        pass
    return DEFAULTS


def choose():
    """Ask once. Returns the preset dict, or None when the dialog was backed out
    (setup then continues with nothing pre-selected)."""
    lst = presets()
    items = []
    for p in lst:
        li = xbmcgui.ListItem(_pick(p.get('name')) or p['id'], _pick(p.get('desc')))
        items.append(li)
    from resources.lib import dialog_guard
    idx = dialog_guard.select(T(30580), items, useDetails=True)
    if idx < 0:
        return None
    p = lst[idx]
    try:
        with open(STATE, 'w', encoding='utf-8') as f:
            f.write(p['id'])
    except OSError:
        pass
    off = p.get('patches_off')
    if off:
        try:
            from resources.lib import patcher
            patcher._save_disabled(set(patcher._load_disabled()) | set(off))
        except Exception:
            pass
    return p


def addon_selection(preset):
    """Set of addon ids to pre-tick in the portal for this preset."""
    if not preset:
        return set()
    want = preset.get('addons') or []
    if '*' in want:
        from resources.lib import addon_portal
        return {c[0] for c in addon_portal._catalog()}
    return set(want)
