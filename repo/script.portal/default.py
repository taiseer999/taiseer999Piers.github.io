# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import xbmcvfs
import urllib.request
import urllib.error
import json
import os
import zipfile

ADDON_PATH    = xbmcvfs.translatePath("special://home/addons/script.portal")
PACKAGES_PATH = xbmcvfs.translatePath("special://home/addons/packages/")
ADDONS_PATH   = xbmcvfs.translatePath("special://home/addons/")

KODI_JSON = (
    "https://raw.githubusercontent.com/taiseer999/"
    "taiseer999.github.io/master/skins.json"
)
CE_JSON = (
    "https://raw.githubusercontent.com/taiseer999/"
    "taiseer999ce.github.io/master/skins.json"
)

PIERS_JSON = (
    "https://raw.githubusercontent.com/taiseer999/"
    "taiseer999Piers.github.io/master/skins.json"
)

DIALOG_TITLE = "Skin Selection"


# ─── helpers ────────────────────────────────────────────────────────────────

def notify(msg, icon=xbmcgui.NOTIFICATION_INFO, ms=3000):
    xbmcgui.Dialog().notification(DIALOG_TITLE, msg, icon, ms)


def error_dialog(msg):
    xbmcgui.Dialog().ok(DIALOG_TITLE, msg)


def _fetch_json(url, timeout=15):
    """Download *url* and return parsed JSON, or raise on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "Kodi"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _skin_installed(addonid):
    """Return True when the skin folder already exists on disk."""
    return xbmcvfs.exists(os.path.join(ADDONS_PATH, addonid, ""))


# ─── source / feed ──────────────────────────────────────────────────────────

def choose_source():
    options = ["KODI Repository", "CoreELEC Repository", "Piers Repository"]
    selected = xbmcgui.Dialog().select("Select Repository", options)
    if selected == -1:
        return None
    if selected == 1:
        return CE_JSON
    elif selected == 2:
        return PIERS_JSON
    return KODI_JSON


def load_feed():
    url = choose_source()
    if not url:
        return []

    try:
        return _fetch_json(url)
    except urllib.error.URLError as e:
        error_dialog("Network error:\n%s" % e.reason)
    except json.JSONDecodeError:
        error_dialog("The feed returned invalid JSON.\nCheck the repository URL.")
    except Exception as e:
        error_dialog("Feed error:\n%s" % str(e))

    return []


# ─── download ───────────────────────────────────────────────────────────────

def download_zip(url, addonid):
    """
    Stream the zip file to disk while showing a progress dialog.
    Returns the local path on success, None on failure.
    """
    if not xbmcvfs.exists(PACKAGES_PATH):
        xbmcvfs.mkdirs(PACKAGES_PATH)

    zip_path = os.path.join(PACKAGES_PATH, "%s.zip" % addonid)

    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Connecting…")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kodi"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 65536          # 64 KB
            downloaded = 0
            chunks = []

            while True:
                if progress.iscanceled():
                    progress.close()
                    notify("Download cancelled.", xbmcgui.NOTIFICATION_WARNING)
                    return None

                chunk = resp.read(chunk_size)
                if not chunk:
                    break

                chunks.append(chunk)
                downloaded += len(chunk)

                if total:
                    pct = int(downloaded * 100 / total)
                    progress.update(
                        pct,
                        "Downloading… %d / %d KB"
                        % (downloaded // 1024, total // 1024),
                    )
                else:
                    progress.update(0, "Downloading… %d KB" % (downloaded // 1024))

        progress.update(100, "Saving…")
        data = b"".join(chunks)
        f = xbmcvfs.File(zip_path, "wb")
        f.write(bytearray(data))
        f.close()

        progress.close()
        return zip_path

    except urllib.error.URLError as e:
        progress.close()
        error_dialog("Download failed (network):\n%s" % e.reason)
    except Exception as e:
        progress.close()
        error_dialog("Download failed:\n%s" % str(e))

    return None


# ─── extraction ─────────────────────────────────────────────────────────────

def extract_zip(zip_path):
    """Extract *zip_path* to the addons folder. Cleans up the zip afterwards."""
    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Extracting…")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            total = len(members)

            for i, member in enumerate(members, 1):
                if progress.iscanceled():
                    progress.close()
                    notify("Extraction cancelled.", xbmcgui.NOTIFICATION_WARNING)
                    return False

                zf.extract(member, ADDONS_PATH)
                progress.update(int(i * 100 / total), "Extracting: %s" % member)

        progress.close()

    except zipfile.BadZipFile:
        progress.close()
        error_dialog("The downloaded file is not a valid ZIP archive.")
        return False
    except Exception as e:
        progress.close()
        error_dialog("Extraction failed:\n%s" % str(e))
        return False
    finally:
        # always remove the cached zip to keep the packages folder tidy
        try:
            xbmcvfs.delete(zip_path)
        except Exception:
            pass

    xbmc.executebuiltin("UpdateLocalAddons")
    xbmc.sleep(3000)
    return True


# ─── skin activation ────────────────────────────────────────────────────────

def apply_skin(addonid, title):
    notify("Enabling %s…" % title)

    # enable the freshly installed skin addon first
    xbmc.executebuiltin('EnableAddon(%s)' % addonid)
    xbmc.sleep(3000)

    notify("Applying %s…" % title)

    # apply the skin
    xbmc.executebuiltin("Skin.SetSkin(%s)" % addonid)
    xbmc.sleep(5000)

    # refresh UI state
    xbmc.executebuiltin("ReloadSkin()")


# ─── GUI window ─────────────────────────────────────────────────────────────

class Portal(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.items = kwargs.get("items", [])

    def onInit(self):
        panel = self.getControl(100)
        panel.reset()

        for item in self.items:
            li = xbmcgui.ListItem(item.get("name", ""))
            li.setArt({
                "thumb": item.get("screenshot", ""),
                "icon":  item.get("screenshot", ""),
            })
            li.setProperty("addonid", item.get("id", ""))
            li.setProperty("zipurl",  item.get("zip", ""))
            li.setProperty("version", item.get("version", ""))

            if _skin_installed(item.get("id", "")):
                li.setProperty("installed", "true")

            panel.addItem(li)

        self.setFocusId(100)

    def onClick(self, controlId):
        if controlId != 100:
            return

        panel  = self.getControl(100)
        item   = panel.getSelectedItem()
        addonid = item.getProperty("addonid")
        zipurl  = item.getProperty("zipurl")
        title   = item.getLabel()
        already = item.getProperty("installed") == "true"

        if not zipurl:
            error_dialog("No ZIP URL found for this skin.\nCheck skins.json.")
            return

        # ── confirm install / reinstall ──────────────────────────────────
        msg = (
            "This skin is already installed.\nReinstall %s?" % title
            if already
            else "Install %s?" % title
        )

        if not xbmcgui.Dialog().yesno(DIALOG_TITLE, msg):
            return

        # ── download ─────────────────────────────────────────────────────
        zip_path = download_zip(zipurl, addonid)
        if not zip_path:
            return

        # ── extract ──────────────────────────────────────────────────────
        if not extract_zip(zip_path):
            return

        # ── apply ────────────────────────────────────────────────────────
        apply_skin(addonid, title)

        notify("✓ %s installed successfully." % title)

        # refresh the installed badge on the panel item
        item.setProperty("installed", "true")

    def onAction(self, action):
        # allow Back / Escape to close the window
        if action.getId() in (
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_PREVIOUS_MENU,
        ):
            self.close()


# ─── entry point ────────────────────────────────────────────────────────────

def main():
    items = load_feed()
    if not items:
        return

    win = Portal(
        "portal.xml",
        ADDON_PATH,
        "Default",
        "1080i",
        items=items,
    )
    win.doModal()
    del win


main()
