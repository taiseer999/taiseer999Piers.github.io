
# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import xbmcvfs
import urllib.request
import json
import os
import zipfile

ADDON_PATH = xbmcvfs.translatePath(
    "special://home/addons/script.portal"
)

PACKAGES_PATH = xbmcvfs.translatePath(
    "special://home/addons/packages/"
)

ADDONS_PATH = xbmcvfs.translatePath(
    "special://home/addons/"
)

KODI_JSON = "https://raw.githubusercontent.com/taiseer999/taiseer999.github.io/master/skins.json"
CE_JSON = "https://raw.githubusercontent.com/taiseer999/taiseer999ce.github.io/master/skins.json"

def notify(msg):

    xbmcgui.Dialog().notification(
        "Skin Selection",
        msg,
        xbmcgui.NOTIFICATION_INFO,
        3000
    )

def choose_source():

    options = [
        "KODI Repository",
        "CoreELEC Repository"
    ]

    selected = xbmcgui.Dialog().select(
        "Select Repository",
        options
    )

    if selected == -1:
        return None

    if selected == 1:
        return CE_JSON

    return KODI_JSON

def load_feed():

    url = choose_source()

    if not url:
        return []

    try:

        req = urllib.request.Request(
            url,
            headers={"User-Agent":"Kodi"}
        )

        response = urllib.request.urlopen(
            req,
            timeout=15
        )

        data = response.read().decode("utf-8")

        return json.loads(data)

    except Exception as e:

        xbmcgui.Dialog().ok(
            "Skin Selection",
            "Feed Error:\\n%s" % str(e)
        )

        return []

def download_zip(url, addonid):

    try:

        if not xbmcvfs.exists(PACKAGES_PATH):
            xbmcvfs.mkdirs(PACKAGES_PATH)

        zip_path = os.path.join(
            PACKAGES_PATH,
            "%s.zip" % addonid
        )

        notify("Downloading package...")

        req = urllib.request.Request(
            url,
            headers={"User-Agent":"Kodi"}
        )

        response = urllib.request.urlopen(
            req,
            timeout=30
        )

        data = response.read()

        f = xbmcvfs.File(zip_path, 'wb')
        f.write(data)
        f.close()

        return zip_path

    except Exception as e:

        xbmcgui.Dialog().ok(
            "Skin Selection",
            "Download failed:\\n%s" % str(e)
        )

        return None

def extract_zip(zip_path):

    try:

        notify("Extracting package...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ADDONS_PATH)

        xbmc.executebuiltin("UpdateLocalAddons")

        xbmc.sleep(4000)

        return True

    except Exception as e:

        xbmcgui.Dialog().ok(
            "Skin Selection",
            "Extraction failed:\\n%s" % str(e)
        )

        return False

def apply_skin(addonid, title):

    notify("Applying %s..." % title)

    xbmc.executebuiltin(
        "Skin.SetSkin(%s)" % addonid
    )

    xbmc.sleep(5000)

class Portal(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):

        super().__init__()

        self.items = kwargs.get("items", [])

    def onInit(self):

        panel = self.getControl(100)

        panel.reset()

        for item in self.items:

            li = xbmcgui.ListItem(
                item.get("name", "")
            )

            li.setArt({
                "thumb": item.get("screenshot", ""),
                "icon": item.get("screenshot", "")
            })

            li.setProperty(
                "addonid",
                item.get("id", "")
            )

            li.setProperty(
                "zipurl",
                item.get("zip", "")
            )

            panel.addItem(li)

        self.setFocusId(100)

    def onClick(self, controlId):

        if controlId != 100:
            return

        panel = self.getControl(100)

        item = panel.getSelectedItem()

        addonid = item.getProperty("addonid")
        zipurl = item.getProperty("zipurl")
        title = item.getLabel()

        if not zipurl:

            xbmcgui.Dialog().ok(
                "Skin Selection",
                "Missing ZIP URL in skins.json"
            )

            return

        yes = xbmcgui.Dialog().yesno(
            "Skin Selection",
            "Install this skin silently?",
            title
        )

        if not yes:
            return

        zip_path = download_zip(
            zipurl,
            addonid
        )

        if not zip_path:
            return

        success = extract_zip(zip_path)

        if not success:
            return

        apply_skin(
            addonid,
            title
        )

        notify("Installation completed")

items = load_feed()

if items:

    win = Portal(
        "portal.xml",
        ADDON_PATH,
        "Default",
        "1080i",
        items=items
    )

    win.doModal()

    del win
