# -*- coding: utf-8 -*-
import os, time
import json
import ssl
import xbmc
import xbmcaddon
import xbmcvfs

try:
    from urllib.parse import quote, unquote
    import urllib.request
    python="3"
except ImportError:
    from urllib import quote, unquote
    import urllib2
    python="2"

addon = xbmcaddon.Addon()
enable_debug = addon.getSetting('enable_debug')
if addon.getSetting('custom_path_enable') == "true" and addon.getSetting('custom_path') != "":
    txtpath = addon.getSetting('custom_path')
else:
    txtpath = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    if not os.path.exists(txtpath):
        os.makedirs(txtpath)
txtfile = txtpath + "lastPlayed.json"
starmovies = addon.getSetting('starmovies')
lang = addon.getLocalizedString

class LP:
    title = ""
    year = ""
    thumbnail = ""
    fanart = ""
    showtitle = ""
    season = ""
    episode = ""
    DBID = ""
    type = ""
    file=""
    video=""
    artist=""
    vidPos=1
    vidTot=1000

lp=LP()

player_monitor = xbmc.Monitor()

def getRequest2(url):
    try:
        context = ssl._create_unverified_context()
        request = urllib2.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib2.urlopen(request, context=context)
        return response
    except:
        pass

def getRequest3(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return(response.read())
    except:
        pass
        
# Builds JSON request with provided json data
def buildRequest(method, params, jsonrpc='2.0', rid='1'):
    request = { 'jsonrpc' : jsonrpc, 'method' : method, 'params' : params, 'id' : rid }
    return request

# Checks JSON response and returns boolean result
def checkReponse(response):
    result = False
    if ( ('result' in response) and ('error' not in response) ):
        result = True
    return result

# Executes JSON request and returns the JSON response
def JSexecute(request):
    request_string = json.dumps(request)
    response = xbmc.executeJSONRPC(request_string)
    if ( response ):
        response = json.loads(response)
    return response

# Performs single JSON query and returns result boolean, data dictionary and error string
def JSquery(request):
    result = False
    data = {}
    error = ''
    if ( request ):
        response = JSexecute(request)
        if ( response ):
            result = checkReponse(response)
            if ( result ):
                data = response['result']
            else: error = response['error']
    return (result, data, error)

def send2starmovies(line):
    if enable_debug	== "true": xbmc.log("<<<plugin.video.last_played (starmovies) "+str(line), 3)
    if LP.vidPos/LP.vidTot<0.8: return
    wid = 0
    if line["id"]!="": wid = int(line["id"])
    if line["type"]=="movie": typ="M"
    elif line["type"]=="episode": typ="S"
    elif line["type"]=="song": typ="P"
    else: typ="V"
    if enable_debug	== "true": xbmc.log("<<<plugin.video.last_played (starmovies) "+str(addon.getSetting('smovies')), 3)

    if typ=="M" and addon.getSetting('smovies') != "true": return
    if typ=="S" and addon.getSetting('stv') != "true": return
    if typ=="V" : return
    if typ=="P" : return

    imdbId = ""
    tvdbId = ""
    orgTitle = ""
    showTitle = line["show"]
    season = line["season"]
    episode = line["episode"]
    thumbnail = line["thumbnail"]
    fanart = line["fanart"]

    if enable_debug	== "true": xbmc.log("<<<plugin.video.last_played (starmovies) "+str(wid), 3)
    if wid>0:
        if typ=="M":
            request = buildRequest('VideoLibrary.GetMovieDetails', {'movieid' : wid, 'properties' : ['imdbnumber', 'originaltitle']})
            result, data = JSquery(request)[:2]
            if ( result and 'moviedetails' in data ):
                imdbId = data['moviedetails']["imdbnumber"]
                orgTitle = data['moviedetails']["originaltitle"]
        elif typ=="S":
            request = buildRequest('VideoLibrary.GetEpisodeDetails', {'episodeid' : wid, 'properties' : ['tvshowid', 'season', 'episode']})
            result, data = JSquery(request)[:2]
            if ( result and 'episodedetails' in data ):
                season = data['episodedetails']["season"]
                episode = data['episodedetails']["episode"]
                request = buildRequest('VideoLibrary.GetTvShowDetails', {'tvshowid' : data['episodedetails']["tvshowid"], 'properties' : ['imdbnumber', 'originaltitle']})
                result, data = JSquery(request)[:2]
                if ( result and 'tvshowdetails' in data ):
                    showTitle = data['tvshowdetails']["label"]
                    orgTitle = data['tvshowdetails']["originaltitle"]
                    tvdbId = data['tvshowdetails']["imdbnumber"]

    xvideo = line["file"]
    if "video" in line and line["video"]!="": xvideo = line["video"]
    url = "https://www.starmovies.org/WebService.asmx/kodiWatch?tmdbId="
    url = url + "&tvdbId=" + tvdbId
    url = url + "&imdbId=" + imdbId
    url = url + "&kodiId=" + str(wid)
    url = url + "&title=" + quote(line["title"].encode("utf-8"))
    url = url + "&orgtitle=" + quote(orgTitle.encode("utf-8"))
    url = url + "&year=" + str(line["year"])
    url = url + "&source=" + quote(line["source"].encode("utf-8"))
    url = url + "&type=" + typ
    url = url + "&usr=" + quote(addon.getSetting('TMDBusr').encode("utf-8"))
    url = url + "&pwd=" + addon.getSetting('TMDBpwd')
    url = url + "&link=" + quote(xvideo.encode("utf-8"))
    url = url + "&thumbnail=" + quote(line["thumbnail"].encode("utf-8"))
    url = url + "&fanart=" + quote(line["fanart"].encode("utf-8"))
    url = url + "&showtitle=" + quote(showTitle.encode("utf-8"))
    url = url + "&season=" + str(season)
    url = url + "&episode=" + str(episode)
    url = url + "&version=1.22"
    url = url + "&date=" + line["date"]
    if enable_debug	== "true": xbmc.log("<<<plugin.video.last_played (starmovies) "+url, 3)
    if python=="3":
        response = getRequest3(url)
    else:
        response = getRequest2(url)
    if enable_debug	== "true": xbmc.log("<<<plugin.video.last_played (starmovies) response:"+str(response), 3)


# ---------------------------------------------------------------------------
# -- Last Played capture engine (by ABUKARIM TOOLS) --
# Works for ANY video add-on (direct or launched from TMDbHelper widgets).
# The stock service read the item once in onPlayBackStarted and only wrote the
# list when playback stopped. On Kodi 21/22 with internet add-ons that rarely
# produced an entry:
#   * TMDbHelper first plays a dummy.mp4 and stops it, which fired the stop
#     callback with the dummy's empty data;
#   * the real stream's info is not settled at onPlayBackStarted, and items
#     whose type came back as anything but movie/episode were silently dropped
#     (the "videos" setting is off by default);
#   * the saved "file" was the debrid link, which is dead by the next day.
# Now: capture on onAVStarted (info is final), ignore dummy.mp4 and the AF3
# background trailers, classify internet items by their TMDb/IMDb ids, save
# straight away (so a crash or power-off still records it) and store a
# replayable link: the add-on item the user actually clicked (tracked while
# browsing, matched to the playing title/ids), else a TMDbHelper play link
# built from the ids, else the raw stream.
# ---------------------------------------------------------------------------
import threading

_lock = threading.Lock()
TMDBH = 'plugin.video.themoviedb.helper'
_state = {'launcher': '', 'launcher_t': 0.0, 'current': None, 'clicked': []}


def _setting(key):
    try:
        return xbmcaddon.Addon().getSetting(key)
    except Exception:
        return addon.getSetting(key)


def _log(msg, always=False):
    if always or _setting('enable_debug') == 'true':
        xbmc.log('[plugin.video.last_played] %s' % msg, xbmc.LOGINFO)


def _list_file():
    path = txtpath
    if not xbmcvfs.exists(path):
        try:
            xbmcvfs.mkdirs(path)
        except Exception:
            pass
    if not xbmcvfs.exists(path):
        # custom path from another box (build restored on a new device)
        path = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        if not os.path.exists(path):
            os.makedirs(path)
        _log('custom path missing, using %s' % path, always=True)
    if not path.endswith(('/', '\\')):
        path += '/'
    return path + 'lastPlayed.json'


def _load(fn):
    if not xbmcvfs.exists(fn):
        return []
    f = xbmcvfs.File(fn)
    try:
        data = json.loads(f.read() or '[]')
    except Exception:
        data = []
    f.close()
    return data if isinstance(data, list) else []


def _save(fn, lines):
    f = xbmcvfs.File(fn, 'w')
    f.write(json.dumps(lines))
    f.close()


def _rpc(method, params):
    try:
        r = json.loads(xbmc.executeJSONRPC(json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
        return r.get('result') or {}
    except Exception:
        return {}


def _addon_name(aid):
    try:
        return xbmcaddon.Addon(aid).getAddonInfo('name') or aid
    except Exception:
        return aid


def _plugin_id(url):
    if url.startswith('plugin://'):
        return url[9:].split('/')[0].split('?')[0]
    return ''


def _is_dummy(path):
    p = (path or '').replace('\\', '/').lower()
    return p.endswith('/dummy.mp4') or p == 'dummy.mp4'


def _is_trailer(path):
    if xbmc.getInfoLabel('Window(Home).Property(abk.trailer)'):
        return True
    p = (path or '').lower()
    return ('plugin.video.youtube' in p or 'googlevideo.com' in p
            or 'youtube.com/' in p or 'imdb-video' in p)


def _tmdbh_link(kind, ids, season, episode):
    """TMDbHelper play URL - survives expired debrid links."""
    if not xbmc.getCondVisibility('System.HasAddon(%s)' % TMDBH):
        return ''
    tmdb, imdb = ids.get('tmdb'), ids.get('imdb')
    if kind == 'movie':
        if tmdb:
            return 'plugin://%s/?info=play&tmdb_type=movie&tmdb_id=%s' % (TMDBH, tmdb)
        if imdb:
            return 'plugin://%s/?info=play&tmdb_type=movie&imdb_id=%s' % (TMDBH, imdb)
    if kind == 'episode' and season not in ('', None, -1) and episode not in ('', None, -1):
        if tmdb:
            return ('plugin://%s/?info=play&tmdb_type=tv&tmdb_id=%s&season=%s&episode=%s'
                    % (TMDBH, tmdb, season, episode))
    return ''


def _norm(t):
    return ''.join(ch for ch in str(t or '').lower() if ch.isalnum())


def _track_focus():
    """Remember the last focused playable add-on item (polled while idle).

    Most video add-ons play through their own source picker / resolver, so by
    the time the stream starts the focused item is gone and the playing path
    is a temporary link. The item the user clicked is the one worth saving.
    """
    path = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    if not path.startswith('plugin://') or xbmc.getCondVisibility('ListItem.IsFolder'):
        return
    if path.startswith('plugin://plugin.video.last_played'):
        return
    hist = _state['clicked']
    for c in hist:
        if c['path'] == path:
            c['t'] = time.time()
            hist.remove(c)
            hist.insert(0, c)
            return
    gi = xbmc.getInfoLabel
    hist.insert(0, {
        'path': path, 't': time.time(),
        'title': gi('ListItem.Title') or gi('ListItem.Label'),
        'show': gi('ListItem.TVShowTitle'), 'year': gi('ListItem.Year'),
        'season': gi('ListItem.Season'), 'episode': gi('ListItem.Episode'),
        'tmdb': gi('ListItem.UniqueID(tmdb)'), 'imdb': gi('ListItem.IMDBNumber'),
    })
    del hist[8:]


def _match_ids(c, show, season, episode, ids):
    if ids.get('imdb') and c['imdb'] and ids['imdb'] == c['imdb']:
        return not show or (str(season) == c['season'] and str(episode) == c['episode']) \
            or not c['season']
    if ids.get('tmdb') and c['tmdb'] and str(ids['tmdb']) == c['tmdb']:
        return not show or (str(season) == c['season'] and str(episode) == c['episode'])
    return False


def _match_title(c, title, show, year, season, episode):
    if show:
        return (_norm(show) == _norm(c['show']) and str(season) == c['season']
                and str(episode) == c['episode'])
    a, b = _norm(title), _norm(c['title'])
    if a and a == b:
        return not year or not c['year'] or str(year) == c['year']
    return False


def _clicked_for(title, show, year, season, episode, ids):
    """Recently-focused add-on item that is the thing now playing.

    Id matches win over title matches, so a "sources as folder" entry focused
    after the title (no ids, label like "[RD] 2160p Dune.mkv") never replaces
    the real item.
    """
    now = time.time()
    recent = [c for c in _state['clicked'] if now - c['t'] <= 1800]
    for c in recent:
        if _match_ids(c, show, season, episode, ids):
            return c
    for c in recent:
        if _match_title(c, title, show, year, season, episode):
            return c
    return None


def _capture(player):
    try:
        if not player.isPlaying():
            return
        playing = player.getPlayingFile() or ''
    except RuntimeError:
        return
    fullpath = xbmc.getInfoLabel('Player.FilenameAndPath') or playing

    if _is_dummy(playing):
        # TMDbHelper splash: remember what the user actually clicked
        for cand in (fullpath, xbmc.getInfoLabel('Player.Folderpath')):
            if cand.startswith('plugin://%s/' % TMDBH) and 'info=play' in cand:
                _state['launcher'], _state['launcher_t'] = cand, time.time()
        _log('dummy start ignored (launcher=%s)' % _state['launcher'])
        return
    if _is_trailer(playing):
        _log('trailer ignored: %s' % playing)
        return

    is_video = xbmc.getCondVisibility('Player.HasVideo')
    pid = 1 if is_video else 0
    props = ['title', 'year', 'art', 'thumbnail', 'fanart', 'showtitle', 'season',
             'episode', 'file', 'uniqueid', 'artist', 'imdbnumber']
    item = (_rpc('Player.GetItem', {'playerid': pid, 'properties': props}) or {}).get('item') or {}

    tag = None
    try:
        tag = player.getVideoInfoTag() if is_video else None
    except Exception:
        tag = None

    def tg(fn, default=''):
        try:
            return getattr(tag, fn)() if tag is not None else default
        except Exception:
            return default

    xtype = (item.get('type') or '').lower()
    if xtype in ('', 'unknown'):
        xtype = (tg('getMediaType') or '').lower()
    title = item.get('title') or tg('getTitle') or item.get('label') or ''
    year = item.get('year') or tg('getYear', 0) or ''
    show = item.get('showtitle') or tg('getTVShowTitle') or ''
    season = item.get('season', -1)
    episode = item.get('episode', -1)
    if season in (-1, None) and tag is not None:
        season = tg('getSeason', -1)
    if episode in (-1, None) and tag is not None:
        episode = tg('getEpisode', -1)
    dbid = item.get('id') or tg('getDbId', -1) or -1
    ids = dict(item.get('uniqueid') or {})
    for k in ('tmdb', 'imdb', 'tvdb'):
        if not ids.get(k) and tag is not None:
            try:
                v = tag.getUniqueID(k)
            except Exception:
                v = ''
            if v:
                ids[k] = v
    if not ids.get('imdb'):
        imdb = item.get('imdbnumber') or tg('getIMDBNumber') or ''
        if imdb.startswith('tt'):
            ids['imdb'] = imdb

    # internet items: decide movie / episode from the metadata itself
    if xtype not in ('movie', 'episode', 'musicvideo', 'song'):
        try:
            s_ok = int(season) >= 0 and int(episode) > 0
        except (TypeError, ValueError):
            s_ok = False
        if show and s_ok:
            xtype = 'episode'
        elif ids.get('tmdb') or ids.get('imdb') or (year and title):
            xtype = 'movie'
        elif not xtype or xtype == 'unknown':
            xtype = 'video' if is_video else 'song'

    art = item.get('art') or {}
    thumb = (art.get('poster') or art.get('tvshow.poster') or art.get('thumb')
             or item.get('thumbnail') or xbmc.getInfoLabel('Player.Art(poster)') or '')
    fanart = (art.get('fanart') or art.get('tvshow.fanart') or item.get('fanart')
              or xbmc.getInfoLabel('Player.Art(fanart)') or '')

    # replay link: TMDbHelper item that launched it > add-on item the user
    # clicked > TMDbHelper link built from ids > library/plugin path > stream
    replay, src_aid = '', ''
    if _state['launcher'] and time.time() - _state['launcher_t'] < 900:
        replay = _state['launcher']
    _state['launcher'] = ''
    try:
        dbnum = int(dbid)
    except (TypeError, ValueError):
        dbnum = -1
    clicked = None
    if not replay and dbnum <= 0:
        clicked = _clicked_for(title, show, year, season, episode, ids)
        if clicked:
            replay = clicked['path']
    if not replay and fullpath.startswith('plugin://'):
        replay = fullpath
    if not replay and dbnum <= 0:
        replay = _tmdbh_link(xtype, ids, season, episode)
        recent = [c for c in _state['clicked'] if time.time() - c['t'] < 1800]
        if recent:
            src_aid = _plugin_id(recent[0]['path'])
    xfile = item.get('file') or fullpath or playing
    if replay:
        xfile = replay

    # source shown in the list / used by the "play with" menu
    if dbnum > 0:
        source = {'movie': lang(30002), 'episode': lang(30003),
                  'musicvideo': lang(30004)}.get(xtype, xtype)
    else:
        aid = src_aid or _plugin_id(xfile) or _plugin_id(fullpath)
        source = _addon_name(aid) if aid else 'player'
    _log('replay=%s (clicked=%s)' % (xfile, bool(clicked)))

    _state['current'] = {
        'source': source, 'title': title, 'year': year,
        'artist': ', '.join(item.get('artist') or []) if isinstance(item.get('artist'), list) else (item.get('artist') or ''),
        'file': xfile.strip(), 'video': xfile.strip() if replay else playing.strip(),
        'id': dbnum if dbnum > 0 else '', 'type': xtype,
        'thumbnail': unquote(thumb).replace('image://', '').rstrip('/'),
        'fanart': unquote(fanart).replace('image://', '').rstrip('/'),
        'show': show, 'season': season if season not in (None, -1) else '',
        'episode': episode if episode not in (None, -1) else '',
        'tmdb': ids.get('tmdb', ''), 'imdb': ids.get('imdb', ''),
    }
    LP.vidPos, LP.vidTot = 0, 1000
    _record(_state['current'])


def _allowed(line):
    xtype, source, title = line['type'], line['source'], line['title']
    if xtype == 'movie' and _setting('movies') != 'true':
        return False
    if xtype == 'episode' and _setting('tv') != 'true':
        return False
    if xtype == 'song' and _setting('music') != 'true':
        return False
    if xtype not in ('movie', 'episode', 'song') and _setting('videos') != 'true':
        return False
    blk = _setting('blackadddon').lower()
    aid = (_plugin_id(line['file']) or source).lower()
    if blk and aid and aid in blk:
        return False
    for d in [x.strip() for x in _setting('blackfolder').lower().split(',') if x.strip()]:
        if d in source.lower() or d in line['file'].lower():
            return False
    for v in [x.strip() for x in _setting('blackvideo').lower().split(',') if x.strip()]:
        if v in title.lower():
            return False
    return True


def _same(a, b):
    if a.get('file') and a.get('file') == b.get('file'):
        return True
    if a.get('type') != b.get('type') or not a.get('title'):
        return False
    if a.get('type') == 'episode':
        return (a.get('show') == b.get('show') and str(a.get('season')) == str(b.get('season'))
                and str(a.get('episode')) == str(b.get('episode')))
    return a.get('title') == b.get('title') and str(a.get('year')) == str(b.get('year'))


def _record(entry, final=False):
    if not entry or not entry.get('title'):
        return
    if not _allowed(entry):
        _log('not kept (type=%s source=%s): %s' % (entry['type'], entry['source'], entry['title']))
        return
    with _lock:
        fn = _list_file()
        lines = _load(fn)
        line = dict(entry)
        for old in list(lines):
            if _same(old, line):
                lines.remove(old)
                for k in ('thumbnail', 'fanart'):
                    if not line.get(k) and old.get(k):
                        line[k] = old[k]
        line['date'] = time.strftime('%Y-%m-%d')
        line['time'] = time.strftime('%H:%M:%S')
        lines.insert(0, line)
        del lines[100:]
        _save(fn, lines)
    if not final:
        _log('recorded: %s (%s, %s)' % (line['title'], line['type'], line['source']), always=True)
    if final and starmovies == 'true':
        try:
            send2starmovies(line)
        except Exception:
            pass


def _finish():
    cur, _state['current'] = _state['current'], None
    if cur:
        _record(cur, final=True)   # refresh date/time + Starmovies hand-off


class KodiPlayer(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self)

    def onAVStarted(self):
        try:
            _capture(self)
        except Exception as e:
            _log('capture failed: %s' % e, always=True)

    def onPlayBackEnded(self):
        _finish()

    def onPlayBackStopped(self):
        _finish()

    def onPlayBackError(self):
        _state['current'] = None


player = KodiPlayer()
while not player_monitor.abortRequested():
    try:
        if player.isPlayingVideo() or player.isPlayingAudio():
            LP.vidPos = player.getTime()
            LP.vidTot = player.getTotalTime() or 1000
        # keep tracking while browsing - also over AF3's windowed trailers
        if not xbmc.getCondVisibility('Window.IsActive(fullscreenvideo)'):
            _track_focus()
    except RuntimeError:
        pass
    if player_monitor.waitForAbort(1):
        break
del player
