#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repo_validate.py - checks (and optionally fixes) a taiseer999*.github.io repo.

Run from the repository root:

    python3 tools/repo_validate.py            # check only, exit 1 on errors
    python3 tools/repo_validate.py --fix      # also rewrite skins.json +
                                              # addons.xml.md5 in place

What it checks
  repo/zips/addons.xml        well-formed, md5 file matches
  every <addon> in it         zip exists at repo/zips/<id>/<id>-<ver>.zip,
                              passes CRC test, top folder == id,
                              <id>/addon.xml declares the same id + version
  skins.json                  valid list; each zip URL resolves to a file in
                              this repo; the zip's addon id == entry id;
                              version == the one in addons.xml (else: lagging)
                              optional fields typed correctly
  abukarim/*.json             schema, patch entries (keys, base64, safe paths),
                              portal entries, presets
  profiles referenced         exist, sha256 matches

--fix
  * points every skins.json zip at the version listed in addons.xml
  * writes sha256 + size for every skin zip (ABUKARIM TOOLS verifies them)
  * writes profile_sha256 for local profiles
  * regenerates repo/zips/addons.xml.md5
Only the standard library is used.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

RAW_RE = re.compile(r'^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$')
PATCH_KEYS = {
    'addon_id', 'rel_path', 'rel_path_alternates', 'old', 'new', 'old_b64',
    'new_b64', 'description', 'toggle', 'already_patched_check',
    'already_patched_check_b64', 'not_found_ok', 'obsolete_if_contains',
    'skip_if_present', 'inject_file', 'inject_content_b64', 'replace',
    'fallback_pattern', 'fallback_repl', 'count', 'regex_dotall', 'base',
    'min_version', 'max_version', 'target_sha256', 'supersedes', 'id',
}
SKIN_KEYS = {'name', 'description', 'screenshot', 'id', 'zip', 'version', 'sha256',
             'size', 'companions', 'min_kodi', 'max_kodi', 'platforms', 'profile',
             'profile_sha256'}
PLATFORMS = {'coreelec', 'android', 'linux', 'osx', 'windows', 'ios', 'tvos'}


class Out(object):
    def __init__(self):
        self.errors, self.warnings, self.fixes = [], [], []

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    def fix(self, m):
        self.fixes.append(m)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def safe_rel(p):
    p = (p or '').replace('\\', '/')
    return bool(p) and not p.startswith('/') and '..' not in p.split('/')


def local_path(root, url, repo_names):
    m = RAW_RE.match(url or '')
    if not m:
        return None
    owner, repo, _branch, rest = m.groups()
    if repo.lower() not in repo_names:
        return None
    return os.path.join(root, *rest.split('/'))


def zip_addon(path):
    """(top_folder, id, version) of an add-on zip."""
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError('CRC failure at %s' % bad)
        tops = {n.split('/', 1)[0] for n in zf.namelist() if '/' in n}
        cand = [n for n in zf.namelist() if n.count('/') == 1 and n.endswith('/addon.xml')]
        if not cand:
            raise ValueError('no <folder>/addon.xml')
        root = ET.fromstring(zf.read(cand[0]))
        return cand[0].split('/')[0], root.get('id'), root.get('version'), tops


def check_repo(root, o, fix):
    zips = os.path.join(root, 'repo', 'zips')
    ax = os.path.join(zips, 'addons.xml')
    if not os.path.isfile(ax):
        o.warn('no repo/zips/addons.xml - repository checks skipped')
        return {}
    raw = open(ax, 'rb').read()
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as e:
        o.err('addons.xml: %s' % e)
        return {}
    md5p = ax + '.md5'
    md5 = hashlib.md5(raw).hexdigest()
    cur = open(md5p).read().split()[0] if os.path.isfile(md5p) else ''
    if cur != md5:
        if fix:
            open(md5p, 'w').write(md5)
            o.fix('addons.xml.md5 regenerated')
        else:
            o.err('addons.xml.md5 is %s, should be %s' % (cur or 'missing', md5))
    versions = {}
    for ad in tree.findall('addon'):
        aid, ver = ad.get('id'), ad.get('version')
        if aid in versions:
            o.err('addons.xml lists %s twice' % aid)
        versions[aid] = ver
        zp = os.path.join(zips, aid, '%s-%s.zip' % (aid, ver))
        if not os.path.isfile(zp):
            o.err('%s %s: zip missing (%s)' % (aid, ver, os.path.relpath(zp, root)))
            continue
        try:
            top, zid, zver, tops = zip_addon(zp)
        except Exception as e:
            o.err('%s: bad zip: %s' % (aid, e))
            continue
        if top != aid or zid != aid:
            o.err('%s: zip folder %r / addon id %r do not match' % (aid, top, zid))
        if zver != ver:
            o.err('%s: addons.xml says %s, zip says %s' % (aid, ver, zver))
        if len(tops) > 1:
            o.warn('%s: zip has extra top-level entries %s' % (aid, sorted(tops - {top})))
    return versions


def check_skins(root, o, fix, versions, repo_names):
    p = os.path.join(root, 'skins.json')
    if not os.path.isfile(p):
        o.warn('no skins.json')
        return
    try:
        items = json.load(open(p, encoding='utf-8'))
    except Exception as e:
        o.err('skins.json: %s' % e)
        return
    if not isinstance(items, list):
        o.err('skins.json must be a list')
        return
    changed = False
    seen = set()
    for i, it in enumerate(items):
        tag = 'skins.json[%d] %s' % (i, it.get('id'))
        for k in ('name', 'id', 'zip'):
            if not it.get(k):
                o.err('%s: missing "%s"' % (tag, k))
        unknown = set(it) - SKIN_KEYS
        if unknown:
            o.warn('%s: unknown keys %s' % (tag, sorted(unknown)))
        if it.get('id') in seen:
            o.err('%s: duplicate id' % tag)
        seen.add(it.get('id'))
        if it.get('companions') is not None and not (
                isinstance(it['companions'], list) and all(isinstance(x, str) for x in it['companions'])):
            o.err('%s: companions must be a list of ids' % tag)
        for k in ('min_kodi', 'max_kodi'):
            if k in it and not isinstance(it[k], int):
                o.err('%s: %s must be an integer (Kodi major)' % (tag, k))
        if 'platforms' in it and not set(it['platforms']) <= PLATFORMS:
            o.err('%s: platforms must be from %s' % (tag, sorted(PLATFORMS)))

        lp = local_path(root, it.get('zip'), repo_names)
        if lp is None:
            o.warn('%s: zip is hosted elsewhere - not verified' % tag)
            continue
        aid = it.get('id')
        latest = versions.get(aid)
        m = re.search(r'-([^/]+)\.zip$', it['zip'])
        listed = m.group(1) if m else None
        if latest and listed != latest:
            if fix:
                new_url = re.sub(r'/[^/]+/[^/]+\.zip$', '/%s/%s-%s.zip' % (aid, aid, latest), it['zip'])
                o.fix('%s: zip %s -> %s' % (tag, listed, latest))
                it['zip'] = new_url
                lp = local_path(root, new_url, repo_names)
                changed = True
            else:
                o.warn('%s: points at %s but the repo has %s' % (tag, listed, latest))
        if not os.path.isfile(lp):
            o.err('%s: zip not in repo (%s)' % (tag, os.path.relpath(lp, root)))
            continue
        try:
            top, zid, zver, _t = zip_addon(lp)
        except Exception as e:
            o.err('%s: bad zip: %s' % (tag, e))
            continue
        if zid != aid:
            o.err('%s: zip contains add-on id %r - the installer will never activate it'
                  % (tag, zid))
        if top != zid:
            o.err('%s: zip folder %r differs from its add-on id %r' % (tag, top, zid))
        digest, size = sha256(lp), os.path.getsize(lp)
        if it.get('sha256') != digest or it.get('size') != size:
            if fix:
                it['sha256'], it['size'] = digest, size
                o.fix('%s: sha256/size updated' % tag)
                changed = True
            elif it.get('sha256'):
                o.err('%s: sha256 does not match the zip' % tag)
        if it.get('profile'):
            pp = local_path(root, it['profile'], repo_names)
            if pp and os.path.isfile(pp):
                ps = sha256(pp)
                if it.get('profile_sha256') != ps:
                    if fix:
                        it['profile_sha256'] = ps
                        o.fix('%s: profile_sha256 updated' % tag)
                        changed = True
                    else:
                        o.err('%s: profile_sha256 does not match' % tag)
                try:
                    with zipfile.ZipFile(pp) as zf:
                        for n in zf.namelist():
                            if not safe_rel(n):
                                o.err('%s: profile has unsafe path %s' % (tag, n))
                except zipfile.BadZipFile:
                    o.err('%s: profile is not a zip' % tag)
            elif pp:
                o.err('%s: profile not in repo (%s)' % (tag, os.path.relpath(pp, root)))
    if changed:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.write('\n')


def check_remote(root, o):
    d = os.path.join(root, 'abukarim')
    if not os.path.isdir(d):
        o.warn('no abukarim/ folder - ABUKARIM TOOLS will use built-in defaults')
        return
    for name in sorted(os.listdir(d)):
        if not name.endswith('.json'):
            continue
        p = os.path.join(d, name)
        try:
            data = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            o.err('abukarim/%s: %s' % (name, e))
            continue
        if not isinstance(data, dict) or not isinstance(data.get('schema', 1), int):
            o.err('abukarim/%s: must be an object with an integer "schema"' % name)
            continue
        if data.get('schema', 1) > 1:
            o.warn('abukarim/%s: schema %s - tools <= 3.2 will ignore it' % (name, data['schema']))
        if name == 'patches.json':
            for i, e in enumerate(data.get('patches') or []):
                tag = 'patches.json[%d] %s' % (i, e.get('id'))
                bad = set(e) - PATCH_KEYS
                if bad:
                    o.err('%s: unknown keys %s (entry would be skipped)' % (tag, sorted(bad)))
                if not e.get('addon_id') or not e.get('rel_path'):
                    o.err('%s: addon_id and rel_path are required' % tag)
                for v in [e.get('rel_path')] + list(e.get('rel_path_alternates') or ()):
                    if v and not safe_rel(v):
                        o.err('%s: unsafe path %r' % (tag, v))
                for k in ('old_b64', 'new_b64', 'already_patched_check_b64', 'inject_content_b64'):
                    if k in e:
                        try:
                            base64.b64decode(e[k], validate=True).decode('utf-8')
                        except Exception:
                            o.err('%s: %s is not base64 utf-8' % (tag, k))
                if not e.get('inject_file') and not (e.get('old') or e.get('old_b64')
                                                     or e.get('fallback_pattern')):
                    o.err('%s: needs old/old_b64 or fallback_pattern' % tag)
                if not (e.get('target_sha256') or e.get('max_version')):
                    o.warn('%s: no target_sha256 / max_version guard' % tag)
                if e.get('fallback_pattern'):
                    try:
                        re.compile(e['fallback_pattern'])
                    except re.error as ex:
                        o.err('%s: bad regex: %s' % (tag, ex))
        elif name == 'portal.json':
            for i, e in enumerate(data.get('addons') or []):
                if not e.get('id') or not e.get('repo'):
                    o.err('portal.json[%d]: id and repo are required' % i)
        elif name == 'presets.json':
            for i, e in enumerate(data.get('presets') or []):
                if not e.get('id') or not isinstance(e.get('addons', []), list):
                    o.err('presets.json[%d]: id and an addons list are required' % i)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default='.', help='repository root')
    ap.add_argument('--fix', action='store_true')
    ap.add_argument('--repo-name', action='append', default=[],
                    help='GitHub repo name(s) whose raw URLs map to --root '
                         '(default: the root folder name)')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    names = {n.lower() for n in (args.repo_name or [os.path.basename(root)])}
    o = Out()
    versions = check_repo(root, o, args.fix)
    check_skins(root, o, args.fix, versions, names)
    check_remote(root, o)
    for m in o.fixes:
        print('FIXED  ', m)
    for m in o.warnings:
        print('WARNING', m)
    for m in o.errors:
        print('ERROR  ', m)
    print('\n%d error(s), %d warning(s), %d fix(es)'
          % (len(o.errors), len(o.warnings), len(o.fixes)))
    sys.exit(1 if o.errors else 0)


if __name__ == '__main__':
    main()
