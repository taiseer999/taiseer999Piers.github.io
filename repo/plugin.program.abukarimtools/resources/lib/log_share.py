# -*- coding: utf-8 -*-
"""
log_share.py - one-click "send my log to Abukarim".

Uploads kodi.log (or kodi.old.log, i.e. the session before a crash/restart)
to paste.kodi.tv - the paste service run by Team Kodi for exactly this - and
shows the link as a QR code the user can scan and send on WhatsApp.

Before upload the log is scrubbed: API keys, tokens, passwords, bearer
headers, e-mail addresses, debrid download links and public IP addresses are
replaced with ***. LAN addresses are kept (they help debugging).
"""

import json
import os
import re
import urllib.request

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

PASTE_URL = 'https://paste.kodi.tv/documents'
VIEW_URL = 'https://paste.kodi.tv/%s'
MAX_BYTES = 900 * 1024          # paste.kodi.tv rejects very large bodies
HEAD_LINES = 60                 # keep the system-info header when trimming
TITLE = 'ABUKARIM – Share Log'

_REDACT = [
    # key=value in URLs / query strings / settings dumps
    (re.compile(r'(?i)\b((?:api_?key|apikey|access_?token|refresh_?token|token|'
                r'client_?secret|secret|password|passwd|pass|auth|apitoken|'
                r'x-api-key)\s*[=:]\s*["\']?)([^\s&"\'<>,;]{4,})'), r'\1***'),
    # JSON "token": "...."
    (re.compile(r'(?i)("(?:[a-z_]*token|[a-z_]*key|secret|password|client_secret)"\s*:\s*")'
                r'([^"]{4,})(")'), r'\1***\3'),
    (re.compile(r'(?i)(authorization:\s*(?:bearer|basic)\s+)\S+'), r'\1***'),
    (re.compile(r'(?i)(bearer\s+)[a-z0-9._\-]{12,}'), r'\1***'),
    (re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}'), '***@***'),
    # debrid / premium direct links
    (re.compile(r'(?i)https?://[^\s"\']*(?:real-debrid|alldebrid|premiumize|torbox|'
                r'debrid-link|offcloud)[^\s"\']*'), 'https://***debrid-link***'),
    # trakt / tmdb style 32-64 hex keys anywhere
    (re.compile(r'\b[a-f0-9]{32,64}\b'), '***'),
    # user:pass@host in URLs
    (re.compile(r'(?i)(\b[a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@'), r'\1***:***@'),
]
_IP = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')


def _private(a, b):
    return a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) \
        or (a == 169 and b == 254) or a == 0


def scrub(text):
    for rx, repl in _REDACT:
        text = rx.sub(repl, text)

    def _ip(m):
        try:
            a, b = int(m.group(1)), int(m.group(2))
        except ValueError:
            return m.group(0)
        return m.group(0) if _private(a, b) or a > 255 else '***.***.***.***'
    return _IP.sub(_ip, text)


def _trim(text):
    data = text.encode('utf-8')
    if len(data) <= MAX_BYTES:
        return text
    lines = text.splitlines()
    head = '\n'.join(lines[:HEAD_LINES])
    budget = MAX_BYTES - len(head.encode('utf-8')) - 200
    tail = data[-budget:].decode('utf-8', 'ignore')
    tail = tail[tail.find('\n') + 1:]
    return head + '\n\n[... trimmed by ABUKARIM TOOLS ...]\n\n' + tail


def upload(text, timeout=30):
    req = urllib.request.Request(PASTE_URL, data=text.encode('utf-8'), method='POST',
                                 headers={'User-Agent': 'AbukarimTools',
                                          'Content-Type': 'text/plain; charset=utf-8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        key = json.loads(r.read().decode('utf-8'))['key']
    return VIEW_URL % key


def _log_path(old=False):
    base = xbmcvfs.translatePath('special://logpath/')
    return os.path.join(base, 'kodi.old.log' if old else 'kodi.log')


def run():
    choices = [T(30560), T(30561)]
    idx = xbmcgui.Dialog().select(TITLE, choices)
    if idx < 0:
        return
    path = _log_path(old=(idx == 1))
    if not os.path.isfile(path):
        xbmcgui.Dialog().ok(TITLE, T(30562) % path)
        return
    prog = xbmcgui.DialogProgress()
    prog.create(TITLE, T(30563))
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        build = ''
        try:
            import xbmcaddon
            build = 'ABUKARIM TOOLS %s | skin %s\n' % (
                xbmcaddon.Addon('plugin.program.abukarimtools').getAddonInfo('version'),
                xbmc.getSkinDir())
        except Exception:
            pass
        text = build + _trim(scrub(text))
        prog.update(50, T(30564))
        url = upload(text)
    except Exception as e:
        prog.close()
        xbmc.log('[AbukarimTools LogShare] upload failed: %s' % e, xbmc.LOGWARNING)
        xbmcgui.Dialog().ok(TITLE, T(30565) % e)
        return
    prog.close()
    xbmc.log('[AbukarimTools LogShare] uploaded: %s' % url, xbmc.LOGINFO)
    from resources.lib import qr_view
    qr_view.show(TITLE, T(30566) % url, url)
