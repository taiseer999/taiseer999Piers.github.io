# -*- coding: utf-8 -*-
"""
icons_toggle.py  –  ABUKARIM TOOLS

Switch the Arctic Fuse 3 node icons (genres / networks / my-lists) between the
colored set and the monochrome set. It is a live TOGGLE, not a patch: no Kodi
restart. It copies the chosen set over the live folder and reloads the skin so
the change shows at once.

The node JSONs hardcode special://skin/extras/icons/<name>.png and are read by
TMDbHelper, not the skin engine, so a Skin.HasSetting cannot redirect them and
colordiffuse cannot recolor multi-tone PNGs. The skin therefore ships both sets
as sibling folders inside extras/:

    extras/icons/          <- live set the nodes actually read
    extras/icons_color/    <- colored master
    extras/icons_bw/       <- monochrome master

This toggle copies icons_color/  or  icons_bw/  over icons/. Only the node
icon filenames are touched; every other UI icon in extras/icons/ is left alone.
State is remembered in the skin string NodeIcons.Mode ('color' | 'mono').
"""

import os
import shutil

import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs

from resources.lib.i18n import T

ADDON      = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_NAME = 'ABUKARIM TOOLS'
SUPPORTED_SKINS = ('skin.arctic.fuse.3', 'skin.arctic.zephyr.rounded')

DIALOG = xbmcgui.Dialog()

# The node icon filenames, and only these, are swapped.
NAMES = [
    '1001.png', '4k.png', 'ADTV.png', 'AE.png', 'Action.png', 'Adventure.png',
    'Animation.png', 'Anime.png', 'Aptv.png', 'Comedy.png', 'Crime.png', 'Dc.png',
    'Documentary.png', 'Drama.png', 'Family.png', 'Fantasy.png', 'History.png',
    'Horror.png', 'Mar.png', 'Mf.png', 'Mystery.png', 'OSN.png', 'Rakuten.png',
    'Remux4K.png', 'Romance.png', 'SHAHID.png', 'Science Fiction.png', 'Superhero.png',
    'Thriller.png', 'Ts.png', 'War.png', 'Western.png', 'awardbp.png', 'boxsets1.png',
    'br.png', 'collection.png', 'couchmoney.png', 'dd.png', 'disc.png', 'disney.png',
    'dv1.png', 'fel7.png', 'food.png', 'fx.png', 'genre.png', 'hbo.png', 'hd2.png',
    'his.png', 'hulu.png', 'imdbtv.png', 'inprogresse.png', 'kdramaw.png', 'likedlist.png',
    'ma.png', 'mag.png', 'money-bill-trend-up.png', 'mostwatched.png', 'movie-icon.png',
    'moviesl.png', 'netflix1.png', 'new2.png', 'paramount.png', 'pea.png', 'popular.png',
    'prime.png', 'random2.png', 'recentlywatched.png', 'recommended.png', 'rt.png',
    'shutup.png', 'starz.png', 'tod.png', 'trend.png', 'tv-channels.png', 'tv2.png',
    'tva.png', 'tvsort.png', 'unkownmovies.png', 'watchlist.png', 'ww.png',
]


def _log(msg):
    xbmc.log('[AbukarimTools IconsToggle] %s' % msg, xbmc.LOGINFO)


def _active_skin():
    sk = xbmc.getSkinDir()
    return sk if sk in SUPPORTED_SKINS else None


def _skin_root(skin_id):
    return xbmcvfs.translatePath('special://home/addons/%s/' % skin_id)


def _extras(skin_id):
    return os.path.join(_skin_root(skin_id), 'extras')


def _current_mode(color_dir, bw_dir, live_dir):
    """Return 'color' / 'mono' / None by matching the live Action.png against
    each master (skin string is authoritative when AF3 is active)."""
    m = xbmc.getInfoLabel('Skin.String(NodeIcons.Mode)')
    if m in ('color', 'mono'):
        return m
    probe = 'Action.png'
    live = os.path.join(live_dir, probe)
    try:
        with open(live, 'rb') as f:
            live_bytes = f.read()
    except OSError:
        return None
    for mode, d in (('mono', bw_dir), ('color', color_dir)):
        try:
            with open(os.path.join(d, probe), 'rb') as f:
                if f.read() == live_bytes:
                    return mode
        except OSError:
            pass
    return None


def _apply(src_dir, live_dir):
    copied = 0
    for n in NAMES:
        src = os.path.join(src_dir, n)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, os.path.join(live_dir, n))
                copied += 1
            except OSError as e:
                _log('copy failed %s: %s' % (n, e))
    return copied



def _bust_texture_cache(live_dir):
    """Remove cached thumbnails for the swapped icons so Kodi re-reads the new
    files without a full restart. Kodi caches by source path in Textures13.db
    plus a copy under special://thumbnails; we clear both the DB rows and the
    cached files for our icon paths, then let ReloadSkin repopulate them."""
    import sqlite3
    import glob

    prof = xbmcvfs.translatePath('special://masterprofile/')
    dbdir = os.path.join(prof, 'Database')
    thumbs = xbmcvfs.translatePath('special://thumbnails/')

    # Build the list of source URLs Kodi would have cached (skin-relative).
    urls = ['special://skin/extras/icons/%s' % n for n in NAMES]

    # Find the newest Textures*.db
    dbs = sorted(glob.glob(os.path.join(dbdir, 'Textures*.db')))
    if not dbs:
        return
    db = dbs[-1]
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        for u in urls:
            cur.execute("SELECT id, cachedurl FROM texture WHERE url = ?", (u,))
            for tid, cached in cur.fetchall():
                # delete the cached image file
                if cached:
                    fp = os.path.join(thumbs, cached)
                    try:
                        if os.path.isfile(fp):
                            os.remove(fp)
                    except OSError:
                        pass
                cur.execute("DELETE FROM sizes WHERE idtexture = ?", (tid,))
            cur.execute("DELETE FROM texture WHERE url = ?", (u,))
        con.commit()
        con.close()
    except sqlite3.Error as e:
        _log('cache bust failed: %s' % e)


def run():
    skin_id = _active_skin()
    if not skin_id:
        DIALOG.ok(ADDON_NAME, T(30346))
        return

    extras    = _extras(skin_id)
    live_dir  = os.path.join(extras, 'icons')
    color_dir = os.path.join(extras, 'icons_color')
    bw_dir    = os.path.join(extras, 'icons_bw')

    for d in (live_dir, color_dir, bw_dir):
        if not os.path.isdir(d):
            DIALOG.ok(ADDON_NAME, T(30340) % d)
            return

    state = _current_mode(color_dir, bw_dir, live_dir)
    if state == 'mono':
        state_lbl = T(30343)   # Monochrome
    elif state == 'color':
        state_lbl = T(30342)   # Colored
    else:
        state_lbl = T(30344)   # Unknown

    # 0 = Colored, 1 = Monochrome
    choice = DIALOG.select(
        T(30341) % state_lbl,
        [T(30342), T(30343)],
        preselect=1 if state == 'mono' else 0)
    if choice == -1:
        return

    mono = (choice == 1)
    if (mono and state == 'mono') or (not mono and state == 'color'):
        return  # already there, nothing to do

    src = bw_dir if mono else color_dir
    n = _apply(src, live_dir)
    _log('applied %s set: copied %d/%d icons into %s' % ('mono' if mono else 'color', n, len(NAMES), live_dir))

    xbmc.executebuiltin(
        'Skin.SetString(NodeIcons.Mode,%s)' % ('mono' if mono else 'color'))
    xbmc.sleep(200)

    DIALOG.notification(
        ADDON_NAME,
        T(30345) % (T(30343) if mono else T(30342), n),
        xbmcgui.NOTIFICATION_INFO, 3000)

    # Bust cached thumbnails for the swapped icons, then reload the skin so
    # the nodes repaint with the new files (no full restart needed).
    _bust_texture_cache(live_dir)
    xbmc.sleep(300)
    xbmc.executebuiltin('ReloadSkin()')
