# -*- coding: utf-8 -*-
"""
qr_view.py - full-screen "scan this" dialog: a QR code plus a block of text.

Used by the log sharer and the remote-access screen. 3.2.0 field fix: the
first version drew its own xbmcgui.WindowDialog with ControlImage; on Kodi 22
the labels rendered but the images (backdrop + QR) did not, so the previous
screen's last frame stayed visible underneath. It is now a WindowXMLDialog
(resources/skins/Default/1080i/abk_qr.xml) built like the Add-on Portal, with
the add-on's own white.png for the backdrop and the QR passed as a property.

The QR PNG is made with segno (vendored in resources/lib/vendor) and kept in
the add-on's profile folder rather than special://temp.
"""

import hashlib
import os
import sys
import time

import xbmc
import xbmcgui
import xbmcvfs

ADDON_ID = 'plugin.program.abukarimtools'
ADDON_PATH = xbmcvfs.translatePath('special://home/addons/%s/' % ADDON_ID)
QR_DIR = os.path.join(xbmcvfs.translatePath(
    'special://profile/addon_data/%s/' % ADDON_ID), 'qr')


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log('[AbukarimTools QR] %s' % msg, level)


def make_qr(data):
    seg_dir = os.path.join(ADDON_PATH, 'resources', 'lib', 'vendor')
    if seg_dir not in sys.path:
        sys.path.insert(0, seg_dir)
    import segno
    os.makedirs(QR_DIR, exist_ok=True)
    # keep the folder small: drop codes older than a day
    now = time.time()
    for f in os.listdir(QR_DIR):
        p = os.path.join(QR_DIR, f)
        try:
            if now - os.path.getmtime(p) > 86400:
                os.remove(p)
        except OSError:
            pass
    name = 'qr_%s.png' % hashlib.sha1(data.encode('utf-8')).hexdigest()[:16]
    path = os.path.join(QR_DIR, name)
    if not os.path.isfile(path):
        # old vendored segno: default black-on-white, no colour kwargs
        segno.make(data, error='m').save(path, scale=12, border=3)
    return path


class _QRDialog(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._props = kwargs.get('props') or {}

    def onInit(self):
        for k, v in self._props.items():
            self.setProperty(k, v)
        try:
            self.setFocusId(9100)
        except Exception:
            pass

    def onClick(self, control_id):
        self.close()

    def onAction(self, action):
        # any real key closes; ignore mouse-move noise
        if action.getId() not in (0, 107):
            self.close()


def _wait_clear(timeout_s=10):
    """Do not open on top of another dialog (it would be torn down / overlap)."""
    mon = xbmc.Monitor()
    waited = 0.0
    while waited < timeout_s and not mon.abortRequested():
        if not xbmc.getCondVisibility('System.HasModalDialog') and \
                not xbmc.getCondVisibility('Window.IsActive(busydialog)'):
            return
        xbmc.sleep(250)
        waited += 0.25


def show(title, text, data, hint='OK / BACK'):
    try:
        qr = make_qr(data)
    except Exception as e:
        _log('segno failed: %s' % e, xbmc.LOGWARNING)
        xbmcgui.Dialog().ok(title, text)
        return
    _wait_clear()
    props = {'title': title, 'text': text, 'qr': qr, 'hint': hint}
    for attempt in range(3):
        started = time.time()
        dlg = _QRDialog('abk_qr.xml', ADDON_PATH, 'Default', '1080i', props=props)
        dlg.doModal()
        del dlg
        # closed by a skin reload / add-on rescan, not by the user: reopen
        if time.time() - started > 1.5:
            break
        _log('QR dialog closed instantly (attempt %d) - reopening' % (attempt + 1))
        xbmc.sleep(1500)
