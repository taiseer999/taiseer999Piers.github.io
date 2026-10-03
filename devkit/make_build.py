#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_build.py - Piers build packager (ABUKARIM).

Turns a Kodi home folder (or an existing build zip) into a clean,
distributable build zip. Every rule below exists because it was found in a
real shipped build:

  * caches / state that must never travel between boxes
    (packages, temp, Thumbnails + Textures DB, Seren / TMDbHelper caches,
    ABUKARIM TOOLS lifecycle files, __pycache__, .DS_Store ...)
  * stale Kodi databases (MyVideos131 ... MyVideos149 -> only the newest)
  * sources.xml.<timestamp>.xml backups and sources pointing at the dev Mac
  * absolute dev-machine paths (/Users/<you>/Library/Application Support/Kodi/,
    raw, URL-encoded and '+'-encoded) -> special://home/
  * skinshortcuts *.hash files (they embed absolute paths; deleting them makes
    every skin rebuild its menu cleanly on the target box)
  * data for skins that are no longer offered in any skins.json catalog
  * menu items pointing at add-ons that are not shipped -> wrapped in
    System.HasAddon(<id>) so they hide instead of opening a dead plugin
  * personal credentials in settings.xml (API keys, passwords) -> blanked
  * file names double-encoded by a zip tool without the UTF-8 flag -> repaired
  * output zip written with UTF-8 names (CoreELEC extracts it correctly)

Optional --thin mode ships only what is NOT available from the bundled
repositories; ABUKARIM TOOLS installs the rest on first run (bootstrap.json).

Usage (macOS dev box):
  python3 make_build.py --src "~/Library/Application Support/Kodi" \
                        --out ~/Desktop/Piers-$(date +%Y%m%d).zip
  python3 make_build.py --src ALL.zip --out Piers.zip --thin
  python3 make_build.py --src ALL.zip --dry-run         # report only

Only the standard library is used.
"""

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

# ----------------------------------------------------------------------------
# configuration
# ----------------------------------------------------------------------------

SKIN_CATALOGS = [
    'https://raw.githubusercontent.com/taiseer999/taiseer999.github.io/master/skins.json',
    'https://raw.githubusercontent.com/taiseer999/taiseer999ce.github.io/master/skins.json',
    'https://raw.githubusercontent.com/taiseer999/taiseer999Piers.github.io/master/skins.json',
]

# Skins whose data is always kept even if no catalog lists them.
ALWAYS_KEEP_SKINS = {'skin.estuary', 'skin.estouchy'}

# Paths (relative to the build root, '/' separated, fnmatch syntax) never shipped.
EXCLUDE_GLOBS = [
    'addons/packages/*',
    'addons/temp/*',
    'userdata/Thumbnails/*',
    'userdata/Savestates/*',
    'userdata/Database/Textures*.db',
    'userdata/sources.xml.*',
    'userdata/guisettings.xml.*',
    'userdata/*.bak',
    'userdata/addon_data/plugin.program.abukarimtools/first_run.*',
    'userdata/addon_data/plugin.program.abukarimtools/last_build.id',
    'userdata/addon_data/plugin.program.abukarimtools/patch_state.json',
    'userdata/addon_data/plugin.program.abukarimtools/service_version.stamp',
    'userdata/addon_data/plugin.program.abukarimtools/remote_cache/*',
    'userdata/addon_data/plugin.program.abukarimtools/*.log',
    # Seren: keep settings + installed provider packages, drop every cache
    'userdata/addon_data/plugin.video.seren/*Cache.db*',
    'userdata/addon_data/plugin.video.seren/cache.db*',
    'userdata/addon_data/plugin.video.seren/search.db*',
    'userdata/addon_data/plugin.video.seren/traktSync.db*',
    'userdata/addon_data/plugin.video.seren/premiumize.db*',
    'userdata/addon_data/plugin.video.seren/animeMappings.db*',
    'userdata/addon_data/plugin.video.seren/mal_dub.json',
    # TMDbHelper: keep settings, nodes, players - drop the item database
    'userdata/addon_data/plugin.video.themoviedb.helper/database_*/*',
    # skinshortcuts hashes embed absolute paths of the dev machine
    'userdata/addon_data/script.skinshortcuts/*.hash',
    'userdata/addon_data/script.skinshortcuts/*.hashes',
    'userdata/gui_settings/script.skinshortcuts/*.hash',
    'userdata/gui_settings/script.skinshortcuts/*.hashes',
    'userdata/addon_data/script.skinvariables/log_request/*',
]

# Basenames dropped anywhere.
EXCLUDE_NAMES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', '__pycache__',
                 'kodi.log', 'kodi.old.log', '.git', '.gitignore', '.idea'}
EXCLUDE_NAME_GLOBS = ['._*', '*.pyc', '*.pyo', 'tmp*.tmp', '*.tmp', '*.swp']

# Kodi DB families: keep only the highest version of each.
DB_RE = re.compile(r'^([A-Za-z]+?)(\d+)\.db$')

# Setting ids treated as credentials (blanked unless --keep-secret <id>).
SECRET_ID_RE = re.compile(
    r'(^|[._\-])(api_?key|apikey|token|access_?token|refresh_?token|secret|'
    r'client_?secret|password|passwd|webserverpassword|pin_code|cookie)'
    r'($|[._\-])', re.I)
SECRET_ID_IGNORE_RE = re.compile(r'color|spinner|texture', re.I)

# Add-ons that are part of Kodi itself (never need a HasAddon guard).
CORE_PREFIXES = ('xbmc.', 'kodi.', 'skin.estuary', 'resource.language.')

# Add-ons the Add-on Portal installs on demand - always guarded.
PORTAL_ADDONS = {
    'plugin.video.dexhub', 'plugin.video.dplex', 'plugin.video.fenlight',
    'plugin.video.last_played', 'plugin.video.pov', 'plugin.video.redlight',
    'plugin.video.seren', 'plugin.video.umbrella', 'plugin.video.youtube',
}

# --thin: never stripped even if a repository carries them.
THIN_KEEP_PREFIXES = ('repository.',)
THIN_KEEP_IDS = {'plugin.program.abukarimtools', 'plugin.program.ABUKARIMwizard',
                 'script.skinshortcuts', 'script.skinvariables'}

ADDON_REF_RE = re.compile(
    r'(?:plugin://|RunScript\(|RunAddon\(|RunPlugin\(plugin://|'
    r'InstallAddon\(|Addon\.OpenSettings\()\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_\-]+)+)')

# Dev-machine Kodi home folders (raw form). Matched case-insensitively.
HOME_PATTERNS = [
    r'/Users/[^/"<>]+/Library/Application Support/Kodi/',
    r'/home/[^/"<>]+/\.kodi/',
    r'/storage/\.kodi/',
    r'[A-Za-z]:\\\\?Users\\\\?[^\\"<>]+\\\\?AppData\\\\?Roaming\\\\?Kodi\\\\?',
]

TEXT_EXT = {'.xml', '.json', '.properties', '.txt', '.py', '.ini', '.cfg',
            '.m3u', '.xsp', '.nfo'}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

class Report(object):
    def __init__(self):
        self.sections = {}

    def add(self, section, line):
        self.sections.setdefault(section, []).append(line)

    def count(self, section):
        return len(self.sections.get(section, []))

    def render(self, limit=40):
        out = []
        for sec, lines in self.sections.items():
            out.append('== %s (%d)' % (sec, len(lines)))
            for l in lines[:limit]:
                out.append('   ' + l)
            if len(lines) > limit:
                out.append('   ... %d more' % (len(lines) - limit))
        return '\n'.join(out)


def fix_mojibake(name):
    """Undo cp437 <-> utf-8 double encoding (up to 3 levels)."""
    cur = unicodedata.normalize('NFC', name)
    for _ in range(3):
        try:
            nxt = unicodedata.normalize(
                'NFC', cur.encode('cp437').decode('utf-8'))
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if nxt == cur:
            break
        cur = nxt
    return cur


def extract_zip(src, dest, report):
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):
                fixed = fix_mojibake(name)
                if fixed != name:
                    report.add('file names repaired', '%s -> %s' % (name, fixed))
                    name = fixed
            # Strip a single wrapping folder like "ALL/addons/..." if present.
            target = os.path.join(dest, *name.split('/'))
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            if len(os.path.basename(target).encode('utf-8')) > 250:
                report.add('skipped (name too long)', name)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as s, open(target, 'wb') as d:
                shutil.copyfileobj(s, d)
    # Normalise: allow a zip whose root is a single folder containing addons/.
    entries = [e for e in os.listdir(dest) if not e.startswith('__MACOSX')]
    if 'addons' not in entries and len(entries) == 1:
        inner = os.path.join(dest, entries[0])
        if os.path.isdir(os.path.join(inner, 'addons')):
            return inner
    return dest


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, '/')


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'piers-make-build'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'piers-make-build'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def addon_version(addon_dir):
    try:
        root = ET.parse(os.path.join(addon_dir, 'addon.xml')).getroot()
        return root.get('version', '')
    except Exception:
        return ''


def is_excluded(relpath):
    base = relpath.rsplit('/', 1)[-1]
    parts = relpath.split('/')
    if any(p in EXCLUDE_NAMES for p in parts):
        return True
    if any(fnmatch.fnmatch(base, g) for g in EXCLUDE_NAME_GLOBS):
        return True
    return any(fnmatch.fnmatch(relpath, g) for g in EXCLUDE_GLOBS)


# ----------------------------------------------------------------------------
# passes
# ----------------------------------------------------------------------------

def pass_exclude(root, report):
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        for d in list(dirnames):
            rp = rel(root, os.path.join(dirpath, d))
            if d in EXCLUDE_NAMES:
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
                dirnames.remove(d)
                report.add('removed', rp + '/')
        for f in filenames:
            p = os.path.join(dirpath, f)
            rp = rel(root, p)
            if is_excluded(rp):
                os.remove(p)
                report.add('removed', rp)


def pass_mojibake_names(root, report):
    """Repair names that are mojibake on disk; drop them if the real one exists."""
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            fixed = fix_mojibake(f)
            if fixed == f:
                continue
            src = os.path.join(dirpath, f)
            dst = os.path.join(dirpath, fixed)
            if os.path.exists(dst):
                os.remove(src)
                report.add('file names repaired', 'dropped duplicate %s' % rel(root, src))
            else:
                os.rename(src, dst)
                report.add('file names repaired', '%s -> %s' % (rel(root, src), fixed))


def pass_old_databases(root, report):
    dbdir = os.path.join(root, 'userdata', 'Database')
    if not os.path.isdir(dbdir):
        return
    fams = {}
    for f in os.listdir(dbdir):
        m = DB_RE.match(f)
        if m:
            fams.setdefault(m.group(1), []).append((int(m.group(2)), f))
    for fam, items in fams.items():
        items.sort()
        for _v, f in items[:-1]:
            os.remove(os.path.join(dbdir, f))
            report.add('stale databases removed', f)
    for f in os.listdir(dbdir):
        if f.endswith('.db'):
            p = os.path.join(dbdir, f)
            try:
                con = sqlite3.connect(p)
                ok = con.execute('PRAGMA integrity_check').fetchone()[0]
                if ok != 'ok':
                    report.add('DATABASE PROBLEMS', '%s: %s' % (f, ok))
                else:
                    before = os.path.getsize(p)
                    con.execute('VACUUM')
                    con.commit()
                    after = os.path.getsize(p)
                    if before - after > 4096:
                        report.add('databases compacted', '%s %dK -> %dK'
                                   % (f, before // 1024, after // 1024))
                con.close()
            except Exception as e:
                report.add('DATABASE PROBLEMS', '%s: %s' % (f, e))


ENC_HOME_PATTERNS = [
    r'%2fUsers%2f[^%"<>/&]+%2fLibrary%2fApplication(?:%20|\+)Support%2fKodi%2f',
    r'%2fhome%2f[^%"<>/&]+%2f\.kodi%2f',
    r'%2fstorage%2f\.kodi%2f',
]


def _home_regexes():
    out = [('raw', re.compile(p, re.I), 'special://home/') for p in HOME_PATTERNS]
    out += [('enc', re.compile(p, re.I), None) for p in ENC_HOME_PATTERNS]
    return out


def _home_scan_dirs(root):
    yield os.path.join(root, 'userdata')
    # ABUKARIM TOOLS ships settings templates (DPlex / Korean toggles) that are
    # written into skin settings - they must be portable too.
    yield os.path.join(root, 'addons', 'plugin.program.abukarimtools', 'resources', 'data')


def pass_home_paths(root, report):
    regs = _home_regexes()
    for dirpath, _d, filenames in (w for d in _home_scan_dirs(root) for w in os.walk(d)):
        for f in filenames:
            if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            p = os.path.join(dirpath, f)
            try:
                with open(p, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            orig = txt
            hits = 0
            for kind, rx, repl in regs:
                if kind == 'raw':
                    txt, n = rx.subn(repl, txt)
                else:
                    def _enc(m):
                        s = m.group(0)
                        upper = '%2F' in s
                        return 'special%3A%2F%2Fhome%2F' if upper else 'special%3a%2f%2fhome%2f'
                    txt, n = rx.subn(_enc, txt)
                hits += n
            if txt != orig:
                with open(p, 'w', encoding='utf-8') as fh:
                    fh.write(txt)
                report.add('dev-machine paths rewritten', '%s (%d)' % (rel(root, p), hits))


def pass_sources(root, report):
    p = os.path.join(root, 'userdata', 'sources.xml')
    if not os.path.isfile(p):
        return
    tree = ET.parse(p)
    changed = False
    for section in tree.getroot():
        for src in list(section.findall('source')):
            paths = [x.text or '' for x in src.findall('path')]
            if any(re.match(r'^(/Users/|/home/|[A-Za-z]:\\)', x) for x in paths):
                section.remove(src)
                changed = True
                report.add('sources.xml: personal sources removed',
                           '%s -> %s' % (src.findtext('name'), ', '.join(paths)))
    if changed:
        ET.indent(tree, '    ')
        tree.write(p, encoding='utf-8', xml_declaration=False)


def catalog_skin_ids(report):
    ids = set()
    for url in SKIN_CATALOGS:
        try:
            for item in fetch_json(url):
                if item.get('id'):
                    ids.add(item['id'])
        except Exception as e:
            report.add('WARNINGS', 'could not read %s (%s) - skin pruning skipped' % (url, e))
            return None
    return ids


def pass_unoffered_skins(root, report, offered):
    if offered is None:
        return
    keep = set(offered) | ALWAYS_KEEP_SKINS
    ad = os.path.join(root, 'userdata', 'addon_data')
    gs = os.path.join(root, 'userdata', 'gui_settings')
    skin_re = re.compile(r'^(skin\.[a-z0-9_.\-]+?)(?:-|\.DATA|\.properties|\.userdata|'
                         r'\.hash|-viewtypes|\.unsupported|$)', re.I)

    def known(sid):
        # Treat "skin.x.y" and its dotted prefixes as matches (skin.arctic.fuse.3.hashes)
        return any(sid == k or sid.startswith(k + '.') or sid.startswith(k + '-')
                   for k in keep)

    for base in (ad, gs):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if os.path.isdir(p) and name.startswith('skin.') and not known(name):
                shutil.rmtree(p)
                report.add('data for skins not offered anywhere', rel(root, p) + '/')
        for sub in ('script.skinshortcuts', 'script.skinvariables'):
            d = os.path.join(base, sub)
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                m = skin_re.match(name)
                if not m or known(name):
                    continue
                p = os.path.join(d, name)
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                report.add('data for skins not offered anywhere', rel(root, p))
            nodes = os.path.join(d, 'nodes')
            if os.path.isdir(nodes):
                for name in os.listdir(nodes):
                    if name.startswith('skin.') and not known(name):
                        shutil.rmtree(os.path.join(nodes, name))
                        report.add('data for skins not offered anywhere',
                                   rel(root, os.path.join(nodes, name)) + '/')


def shipped_addons(root):
    d = os.path.join(root, 'addons')
    return {n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, 'addon.xml'))}


def _needs_guard(aid, shipped):
    if aid.startswith(CORE_PREFIXES):
        return False
    return aid in PORTAL_ADDONS or aid not in shipped


def pass_guard_shortcuts(root, report, shipped):
    """Wrap skinshortcuts DATA.xml items in System.HasAddon(<id>)."""
    for base in ('addon_data', 'gui_settings'):
        d = os.path.join(root, 'userdata', base, 'script.skinshortcuts')
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.DATA.xml'):
                continue
            p = os.path.join(d, f)
            try:
                tree = ET.parse(p)
            except ET.ParseError as e:
                report.add('XML ERRORS', '%s: %s' % (rel(root, p), e))
                continue
            changed = False
            for sc in tree.getroot().iter('shortcut'):
                action = sc.findtext('action') or ''
                ids = []
                for m in ADDON_REF_RE.finditer(action):
                    aid = m.group(1)
                    if _needs_guard(aid, shipped) and aid not in ids:
                        ids.append(aid)
                if not ids:
                    continue
                vis = sc.find('visible')
                cur = (vis.text or '').strip() if vis is not None else ''
                add = [a for a in ids if 'System.HasAddon(%s)' % a not in cur]
                if not add:
                    continue
                cond = ' + '.join('System.HasAddon(%s)' % a for a in add)
                new = '%s + [%s]' % (cond, cur) if cur else cond
                if vis is None:
                    vis = ET.SubElement(sc, 'visible')
                vis.text = new
                changed = True
                report.add('menu items guarded with System.HasAddon',
                           '%s: %s -> %s' % (f, sc.findtext('label'), ', '.join(add)))
            if changed:
                ET.indent(tree, '\t')
                tree.write(p, encoding='utf-8', xml_declaration=False)


def scan_unguardable_refs(root, report, shipped):
    """JSON / settings references that can't carry a visible condition. They
    are handled at runtime by ABUKARIM TOOLS' menu reconciler; listed here
    so you know where they are."""
    for base in ('addon_data',):
        d = os.path.join(root, 'userdata', base)
        for dirpath, _dn, filenames in os.walk(d):
            for f in filenames:
                if not (f.endswith('.json') or f.endswith('.properties')
                        or f == 'settings.xml'):
                    continue
                if '/players' in dirpath.replace(os.sep, '/'):
                    continue    # TMDbHelper hides players whose plugin is missing
                p = os.path.join(dirpath, f)
                try:
                    txt = open(p, encoding='utf-8').read()
                except Exception:
                    continue
                ids = sorted({m.group(1) for m in ADDON_REF_RE.finditer(txt)
                              if _needs_guard(m.group(1), shipped)})
                if ids:
                    report.add('optional add-on references (runtime reconciled)',
                               '%s: %s' % (rel(root, p), ', '.join(ids)))


def pass_secrets(root, report, keep):
    rx = re.compile(r'(<setting\s+id="([^"]+)"([^>]*)>)([^<]+)(</setting>)')
    files = [os.path.join(root, 'userdata', 'guisettings.xml')]
    for dirpath, _d, filenames in os.walk(os.path.join(root, 'userdata', 'addon_data')):
        files += [os.path.join(dirpath, f) for f in filenames if f == 'settings.xml']
    for p in files:
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding='utf-8').read()

        def _sub(m):
            sid, attrs, val = m.group(2), m.group(3), m.group(4)
            if 'default="true"' in attrs or sid in keep:
                return m.group(0)
            if not SECRET_ID_RE.search(sid) or SECRET_ID_IGNORE_RE.search(sid):
                return m.group(0)
            if not val.strip() or val.strip().lower() in ('true', 'false', '0', '1'):
                return m.group(0)
            report.add('credentials blanked', '%s: %s (%s...)'
                       % (rel(root, p), sid, val[:3]))
            return m.group(1) + m.group(5)
        new = rx.sub(_sub, txt)
        if new != txt:
            open(p, 'w', encoding='utf-8').write(new)


def pass_validate(root, report):
    for dirpath, _d, filenames in os.walk(os.path.join(root, 'userdata')):
        for f in filenames:
            p = os.path.join(dirpath, f)
            if f.endswith('.xml'):
                try:
                    ET.parse(p)
                except ET.ParseError as e:
                    report.add('XML ERRORS', '%s: %s' % (rel(root, p), e))
            elif f.endswith('.json'):
                try:
                    json.load(open(p, encoding='utf-8'))
                except Exception as e:
                    report.add('JSON ERRORS', '%s: %s' % (rel(root, p), e))
    for a in sorted(os.listdir(os.path.join(root, 'addons'))):
        ax = os.path.join(root, 'addons', a, 'addon.xml')
        if os.path.isdir(os.path.join(root, 'addons', a)) and a not in ('packages', 'temp'):
            if not os.path.isfile(ax):
                report.add('WARNINGS', 'addons/%s has no addon.xml' % a)
                continue
            try:
                aid = ET.parse(ax).getroot().get('id')
                if aid != a:
                    report.add('WARNINGS', 'addons/%s declares id %s' % (a, aid))
            except ET.ParseError as e:
                report.add('XML ERRORS', 'addons/%s/addon.xml: %s' % (a, e))


def repo_inventory(root, report):
    """{addon_id: version} available from the bundled repositories."""
    avail = {}
    for a in sorted(os.listdir(os.path.join(root, 'addons'))):
        if not a.startswith('repository.'):
            continue
        try:
            r = ET.parse(os.path.join(root, 'addons', a, 'addon.xml')).getroot()
        except Exception:
            continue
        for info in r.iter('info'):
            url = (info.text or '').strip()
            if not url:
                continue
            try:
                xml = fetch_text(url)
                for ad in ET.fromstring(xml).findall('addon'):
                    avail.setdefault(ad.get('id'), (ad.get('version'), a))
            except Exception as e:
                report.add('WARNINGS', 'thin: cannot read %s from %s (%s)' % (url, a, e))
    return avail


def pass_thin(root, report):
    avail = repo_inventory(root, report)
    if not avail:
        report.add('WARNINGS', 'thin: no repository listings reachable - shipping full build')
        return
    # Keep the kept add-ons' own dependencies (recursively), so the tools and
    # the wizard work before the bootstrap has run.
    keep = {a for a in shipped_addons(root)
            if a in THIN_KEEP_IDS or a.startswith(THIN_KEEP_PREFIXES)}
    todo = list(keep)
    while todo:
        a = todo.pop()
        try:
            r = ET.parse(os.path.join(root, 'addons', a, 'addon.xml')).getroot()
        except Exception:
            continue
        for imp in r.findall('./requires/import'):
            dep = imp.get('addon') or ''
            if dep and dep not in keep and os.path.isdir(os.path.join(root, 'addons', dep)):
                keep.add(dep)
                todo.append(dep)
    boot = []
    for a in sorted(shipped_addons(root)):
        if a in keep:
            continue
        if a in avail:
            boot.append({'id': a, 'repo': avail[a][1],
                         'version': addon_version(os.path.join(root, 'addons', a))})
            shutil.rmtree(os.path.join(root, 'addons', a))
            report.add('thin: moved to first-run bootstrap', a)
    d = os.path.join(root, 'userdata', 'addon_data', 'plugin.program.abukarimtools')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'bootstrap.json'), 'w', encoding='utf-8') as f:
        json.dump({'schema': 1, 'created': int(time.time()), 'addons': boot},
                  f, indent=1)


def write_zip(root, out, report):
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for f in sorted(filenames):
            entries.append(os.path.join(dirpath, f))
        if not filenames and not dirnames and dirpath != root:
            entries.append(dirpath + os.sep)
    tmp = out + '.part'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in entries:
            arc = rel(root, p.rstrip(os.sep))
            if p.endswith(os.sep):
                zi = zipfile.ZipInfo(arc + '/', time.localtime()[:6])
                zi.external_attr = 0o40755 << 16
                zf.writestr(zi, b'')
                continue
            ext = os.path.splitext(p)[1].lower()
            # already-compressed media gains nothing from level 9 - use level 1
            fast = ext in ('.zip', '.mp4', '.mp3', '.xbt', '.webp', '.gz')
            zf.write(p, arc, compress_type=zipfile.ZIP_DEFLATED,
                     compresslevel=1 if fast else 9)
            # Python sets the UTF-8 flag (0x800) automatically for non-ASCII names.
    os.replace(tmp, out)
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit('zip self-test failed at %s' % bad)
    h = hashlib.sha256()
    with open(out, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return len(entries), os.path.getsize(out), h.hexdigest()


def dir_size(root):
    t = n = 0
    for dp, _d, fs in os.walk(root):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return t, n


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True, help='Kodi home folder or build zip')
    ap.add_argument('--out', help='output zip (omit with --dry-run)')
    ap.add_argument('--thin', action='store_true',
                    help='strip add-ons available from bundled repos; first run installs them')
    ap.add_argument('--keep-secret', action='append', default=[],
                    help='setting id to keep (repeatable), e.g. mdblist_api_key')
    ap.add_argument('--no-skin-prune', action='store_true',
                    help='keep data of skins not listed in any skins.json')
    ap.add_argument('--replace-addon', action='append', default=[], metavar='DIR',
                    help='swap in this add-on folder (e.g. a fresh plugin.program.abukarimtools)')
    ap.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    ap.add_argument('--keep-work', action='store_true', help='keep the staging folder')
    args = ap.parse_args()

    if not args.out and not args.dry_run:
        ap.error('--out is required unless --dry-run')

    report = Report()
    src = os.path.expanduser(args.src)
    work = tempfile.mkdtemp(prefix='piers_build_')
    try:
        print('staging ...')
        if os.path.isfile(src) and zipfile.is_zipfile(src):
            root = extract_zip(src, work, report)
        else:
            root = os.path.join(work, 'build')
            os.makedirs(root)
            for part in ('addons', 'media', 'userdata'):
                s = os.path.join(src, part)
                if os.path.isdir(s):
                    shutil.copytree(s, os.path.join(root, part), symlinks=False,
                                    ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
        if not os.path.isdir(os.path.join(root, 'addons')):
            raise SystemExit('no addons/ folder found in %s' % src)

        for d in args.replace_addon:
            d = os.path.abspath(os.path.expanduser(d)).rstrip(os.sep)
            dest = os.path.join(root, 'addons', os.path.basename(d))
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(d, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
            report.add('add-ons replaced', '%s %s' % (os.path.basename(d), addon_version(dest)))

        size0, n0 = dir_size(root)
        shipped = shipped_addons(root)

        print('cleaning ...')
        pass_mojibake_names(root, report)
        pass_exclude(root, report)
        pass_old_databases(root, report)
        pass_home_paths(root, report)
        pass_sources(root, report)
        if not args.no_skin_prune:
            pass_unoffered_skins(root, report, catalog_skin_ids(report))
        if args.thin:
            print('thin mode: reading repository listings ...')
            pass_thin(root, report)
            shipped = shipped_addons(root)
        pass_guard_shortcuts(root, report, shipped)
        scan_unguardable_refs(root, report, shipped)
        pass_secrets(root, report, set(args.keep_secret))
        pass_validate(root, report)

        size1, n1 = dir_size(root)
        print()
        print(report.render())
        print()
        print('before: %6.1f MB  %6d files' % (size0 / 1e6, n0))
        print('after : %6.1f MB  %6d files' % (size1 / 1e6, n1))

        if args.dry_run:
            return
        out = os.path.abspath(os.path.expanduser(args.out))
        print('writing %s ...' % out)
        count, zsize, sha = write_zip(root, out, report)
        meta = {
            'file': os.path.basename(out), 'size': zsize, 'sha256': sha,
            'entries': count, 'thin': bool(args.thin),
            'built': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'tools_version': addon_version(os.path.join(
                root, 'addons', 'plugin.program.abukarimtools')),
        }
        with open(out + '.json', 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=1)
        with open(out + '.report.txt', 'w', encoding='utf-8') as f:
            f.write(report.render(limit=100000))
        print('zip   : %6.1f MB  sha256 %s' % (zsize / 1e6, sha))
        print('meta  : %s.json   report: %s.report.txt' % (out, out))
    finally:
        if args.keep_work:
            print('staging kept at', work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
