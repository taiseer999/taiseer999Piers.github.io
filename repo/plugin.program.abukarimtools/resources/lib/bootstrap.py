# -*- coding: utf-8 -*-
"""
bootstrap.py - finish a THIN build on first run.

make_build.py --thin leaves out every add-on that the bundled repositories
can serve and records them in
addon_data/plugin.program.abukarimtools/bootstrap.json. This installs them
from those repositories (so they arrive linked to their repo and keep
updating), then renames the file to bootstrap.done.json with the result.
Anything that failed stays listed and is retried from Tools > Setup.

A full (non-thin) build has no bootstrap.json and this step is a no-op.
"""

import json
import os

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

PROFILE = xbmcvfs.translatePath('special://profile/addon_data/plugin.program.abukarimtools/')
PENDING = os.path.join(PROFILE, 'bootstrap.json')
DONE = os.path.join(PROFILE, 'bootstrap.done.json')
TITLE = 'ABUKARIM – Build Install'


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools Bootstrap] %s' % msg, level)


def pending():
    try:
        with open(PENDING, 'r', encoding='utf-8') as f:
            data = json.load(f)
        from resources.lib.menu_reconcile import addon_present
        return [a for a in data.get('addons', [])
                if a.get('id') and not addon_present(a['id'])]
    except Exception:
        return []


def run(interactive=True):
    todo = pending()
    if not todo:
        return True
    from resources.lib import addon_portal as ap
    _log('%d add-ons to install' % len(todo))
    prog = xbmcgui.DialogProgress()
    prog.create(TITLE, T(30570) % len(todo))
    failed, done = [], []
    try:
        repos = sorted({a.get('repo') for a in todo if a.get('repo')})
        for r in repos:
            ap._enable(r, timeout_ms=4000)
        xbmc.executebuiltin('UpdateAddonRepos')
        ap._wait_repo_listings(repos)
        for i, a in enumerate(todo):
            if prog.iscanceled():
                failed += [x['id'] for x in todo[i:]]
                break
            prog.update(int(i * 100 / len(todo)), T(30571) % (i + 1, len(todo), a['id']))
            ok = False
            if a.get('repo'):
                url, _ver = ap._resolve_zip_in_repo(a['repo'], a['id'])
                if url:
                    ok = ap._install_zip(url)
                    if ok:
                        for dep in ap._required_imports(a['id']):
                            if not ap._has_addon(dep):
                                ap._kodi_install(dep)
            if not ok:
                ok = ap._kodi_install(a['id'])
            if ok:
                xbmc.executebuiltin('UpdateLocalAddons')
                xbmc.sleep(800)
                ap._enable(a['id'], timeout_ms=5000)
                if a.get('repo'):
                    ap._force_origin(a['id'], a['repo'])
                done.append(a['id'])
            else:
                failed.append(a['id'])
    finally:
        prog.close()
    left = [a for a in todo if a['id'] in failed]
    try:
        if left:
            with open(PENDING, 'w', encoding='utf-8') as f:
                json.dump({'schema': 1, 'addons': left}, f, indent=1)
        else:
            os.replace(PENDING, DONE)
    except OSError:
        pass
    _log('installed %d, failed %d: %s' % (len(done), len(failed), failed))
    if interactive and failed:
        xbmcgui.Dialog().ok(TITLE, T(30572) % ', '.join(failed))
    return not failed
