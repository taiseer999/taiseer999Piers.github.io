# -*- coding: utf-8 -*-
"""
webserver_secure.py - per-box credentials for Kodi's web server / remote API.

Every box built from the same image used to share one web server password
(and authentication was off), so anyone on the same network - or anyone who
had ever owned a Piers box - could control the player and read the library.
First-run now gives each box its own random password and turns
authentication on. The credentials are shown once (with a QR code for phone
remote apps) and can be shown again or rotated from the Tools menu.
"""

import json
import os
import re
import secrets
import socket

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.i18n import T

PROFILE = xbmcvfs.translatePath('special://profile/addon_data/plugin.program.abukarimtools/')
MARKER = os.path.join(PROFILE, 'webserver_secured')
TITLE = 'ABUKARIM – Remote Access'
_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'     # no 0/o/1/l/i


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools WebServer] %s' % msg, level)


def _rpc(method, params=None):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
    try:
        res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
        return res.get('result')
    except Exception:
        return None


def _get(setting):
    r = _rpc('Settings.GetSettingValue', {'setting': setting}) or {}
    return r.get('value')


def _set(setting, value):
    return _rpc('Settings.SetSettingValue', {'setting': setting, 'value': value}) is not None


def _new_password(n=8):
    return ''.join(secrets.choice(_ALPHABET) for _ in range(n))


_IPV4 = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


def _local_ip():
    """LAN address of this box.

    3.2.1 field bug: Network.IPAddress read from Python returned the
    placeholder "Busy" (Kodi had not evaluated the label yet), so the screen
    showed http://Busy:8080. Ask the OS first (UDP "connect" sends nothing),
    then fall back to the info label, retrying while it says Busy.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if _IPV4.match(ip) and not ip.startswith('127.'):
            return ip
    except Exception:
        pass
    for _ in range(20):
        ip = (xbmc.getInfoLabel('Network.IPAddress') or '').strip()
        if _IPV4.match(ip) and not ip.startswith('127.'):
            return ip
        xbmc.sleep(250)
    return '<box-ip>'


def credentials():
    ip = _local_ip()
    port = _get('services.webserverport') or 8080
    return {
        'enabled': bool(_get('services.webserver')),
        'auth': bool(_get('services.webserverauthentication')),
        'user': _get('services.webserverusername') or 'kodi',
        'password': _get('services.webserverpassword') or '',
        'url': 'http://%s:%s' % (ip, port),
    }


def rotate():
    pw = _new_password()
    ok = (_set('services.webserverusername', 'kodi')
          and _set('services.webserverpassword', pw)
          and _set('services.webserverauthentication', True))
    if ok:
        try:
            os.makedirs(PROFILE, exist_ok=True)
            open(MARKER, 'w').close()
        except OSError:
            pass
        _log('web server credentials rotated')
    return ok


def _show(c):
    text = T(30550) % (c['url'], c['user'], c['password'] or '-')
    try:
        from resources.lib import qr_view
        # Kore / Yatse can scan a kodi:// style URL; plain http works for browsers.
        qr_view.show(TITLE, text, 'http://%s:%s@%s' % (
            c['user'], c['password'], c['url'].split('://', 1)[-1]))
    except Exception as e:
        _log('qr view failed (%s) - text only' % e, xbmc.LOGWARNING)
        xbmcgui.Dialog().ok(TITLE, text)


def first_run():
    """Silent unless something changed: secure once per box."""
    if os.path.exists(MARKER):
        return False
    c = credentials()
    if not c['enabled']:
        try:
            open(MARKER, 'w').close()
        except OSError:
            pass
        return False
    if rotate():
        _show(credentials())
        return True
    return False


def run():
    """Menu entry."""
    c = credentials()
    opts = [T(30551), T(30552), T(30553) if c['enabled'] else T(30554)]
    idx = xbmcgui.Dialog().select(TITLE, opts)
    if idx == 0:
        if not c['enabled']:
            xbmcgui.Dialog().ok(TITLE, T(30555))
        else:
            _show(c)
    elif idx == 1:
        if rotate():
            _set('services.webserver', True)
            _show(credentials())
    elif idx == 2:
        if c['enabled']:
            _set('services.webserver', False)
            xbmcgui.Dialog().notification(TITLE, T(30556))
        else:
            if not c['auth'] or not c['password']:
                rotate()
            _set('services.webserver', True)
            _show(credentials())
