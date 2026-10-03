#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_profiles.py - build "Piers profile" zips for every skin straight from a
build folder or build zip (no Kodi needed), for the repo's profiles/ folder.

    python3 export_profiles.py --src Piers.zip --out ./profiles \
        --skins-json ../taiseer999Piers.github.io/skins.json

Each zip contains exactly what ABUKARIM TOOLS' skin_profiles.py will accept
(addon_data/<skin>/, the skin's skinshortcuts files, its skinvariables nodes
and view types) with dev-machine paths rewritten to special://home/. With
--skins-json the matching entries get "profile" + "profile_sha256" written.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_build as mb  # noqa: E402

RAW_BASE = ('https://raw.githubusercontent.com/taiseer999/'
            'taiseer999Piers.github.io/master/profiles/')


def skin_files(ud, skin):
    ad = os.path.join(ud, 'addon_data')
    out = []
    for base in (os.path.join(ad, skin),
                 os.path.join(ad, 'script.skinvariables', 'nodes', skin)):
        if os.path.isdir(base):
            for dp, _d, fs in os.walk(base):
                out += [os.path.join(dp, f) for f in fs]
    vt = os.path.join(ad, 'script.skinvariables', '%s-viewtypes.json' % skin)
    if os.path.isfile(vt):
        out.append(vt)
    ss = os.path.join(ad, 'script.skinshortcuts')
    if os.path.isdir(ss):
        out += [os.path.join(ss, f) for f in os.listdir(ss)
                if f.startswith(skin) and not f.endswith(('.hash', '.hashes'))]
    return sorted(p for p in out if os.path.isfile(p))


def portable(data):
    try:
        txt = data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    for kind, rx, repl in mb._home_regexes():
        if kind == 'raw':
            txt = rx.sub(repl, txt)
        else:
            txt = rx.sub(lambda m: 'special%3A%2F%2Fhome%2F' if '%2F' in m.group(0)
                         else 'special%3a%2f%2fhome%2f', txt)
    return txt.encode('utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--skins-json', help='skins.json to update with profile fields')
    ap.add_argument('--base-url', default=RAW_BASE)
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix='piers_prof_')
    try:
        src = os.path.expanduser(args.src)
        if os.path.isfile(src):
            root = mb.extract_zip(src, work, mb.Report())
        else:
            root = src
        ud = os.path.join(root, 'userdata')
        ad = os.path.join(ud, 'addon_data')
        skins = sorted(d for d in os.listdir(ad) if d.startswith('skin.'))
        os.makedirs(args.out, exist_ok=True)
        made = {}
        for skin in skins:
            files = skin_files(ud, skin)
            if not files:
                continue
            name = '%s-profile.zip' % skin
            path = os.path.join(args.out, name)
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('profile.json', json.dumps(
                    {'skin': skin, 'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
                     'source': 'export_profiles.py'}, indent=1))
                for p in files:
                    arc = os.path.relpath(p, ud).replace(os.sep, '/')
                    zf.writestr(arc, portable(open(p, 'rb').read()))
            sha = hashlib.sha256(open(path, 'rb').read()).hexdigest()
            made[skin] = (name, sha)
            print('%-32s %3d files  %s' % (skin, len(files), sha[:16]))
        if args.skins_json:
            items = json.load(open(args.skins_json, encoding='utf-8'))
            for it in items:
                if it.get('id') in made:
                    name, sha = made[it['id']]
                    it['profile'] = args.base_url + name
                    it['profile_sha256'] = sha
            with open(args.skins_json, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
                f.write('\n')
            print('updated', args.skins_json)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
