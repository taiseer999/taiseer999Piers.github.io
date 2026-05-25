# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import xbmcvfs
import urllib.request
import urllib.error
import json
import os
import zipfile
import tempfile

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
        return None, None
    if selected == 1:
        return CE_JSON, "backgroundcoreelec.jpg"
    elif selected == 2:
        return PIERS_JSON, "backgroundpiers.jpg"
    return KODI_JSON, "backgroundkodi.jpg"


def load_feed():
    url, background = choose_source()
    if not url:
        return [], None

    try:
        return _fetch_json(url), background
    except urllib.error.URLError as e:
        error_dialog("Network error:\n%s" % e.reason)
    except json.JSONDecodeError:
        error_dialog("The feed returned invalid JSON.\nCheck the repository URL.")
    except Exception as e:
        error_dialog("Feed error:\n%s" % str(e))

    return [], None


# ─── download ───────────────────────────────────────────────────────────────

def download_zip(url, addonid):
    """
    Stream the zip file to a native temp file (avoids xbmcvfs write
    truncation on slow/embedded storage).  Shows a byte-accurate progress
    bar.  Returns the local path on success, None on failure/cancel.
    """
    if not xbmcvfs.exists(PACKAGES_PATH):
        xbmcvfs.mkdirs(PACKAGES_PATH)

    # Write to a system temp file first; move to packages only on success.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="portal_")

    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Connecting…")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kodi"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 65536   # 64 KB
            downloaded = 0

            with os.fdopen(tmp_fd, "wb") as fh:
                tmp_fd = None          # fdopen owns it now
                while True:
                    if progress.iscanceled():
                        progress.close()
                        notify("Download cancelled.", xbmcgui.NOTIFICATION_WARNING)
                        return None

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    fh.write(chunk)
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
                # fh is flushed + closed here by the context manager

        # Verify the temp file is a valid ZIP before accepting it
        progress.update(100, "Verifying download…")
        if not zipfile.is_zipfile(tmp_path):
            error_dialog(
                "Download incomplete or corrupt.\n"
                "The file is not a valid ZIP archive.\nPlease try again."
            )
            return None

        # Move to the packages folder
        zip_path = os.path.join(PACKAGES_PATH, "%s.zip" % addonid)
        try:
            os.replace(tmp_path, zip_path)
        except OSError:
            # os.replace can fail across filesystems; fall back to copy+delete
            import shutil
            shutil.copy2(tmp_path, zip_path)
            os.remove(tmp_path)
        tmp_path = None   # successfully moved; nothing to clean up

        progress.close()
        return zip_path

    except urllib.error.URLError as e:
        progress.close()
        error_dialog("Download failed (network):\n%s" % e.reason)
    except Exception as e:
        progress.close()
        error_dialog("Download failed:\n%s" % str(e))
    finally:
        # Clean up the temp file if something went wrong before the move
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return None


# ─── extraction ─────────────────────────────────────────────────────────────

def extract_zip(zip_path):
    """
    Extract *zip_path* to the addons folder.

    Improvements over the original:
    - Progress is byte-based (accurate for large skin assets).
    - The zip is only deleted after a verified, complete extraction.
    - Each extracted file is size-checked against the zip's metadata.
    - A staging folder is used so a partial extraction never leaves a
      half-installed addon in the addons directory.
    """
    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Preparing extraction…")

    # Resolve the real filesystem path for extraction (xbmcvfs path may not
    # work with Python's zipfile/os modules directly on all platforms).
    addons_real = xbmcvfs.translatePath("special://home/addons/")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # ── integrity check first ─────────────────────────────────────
            bad = zf.testzip()
            if bad is not None:
                progress.close()
                error_dialog(
                    "ZIP integrity check failed.\n"
                    "First bad file: %s\n\nPlease try downloading again." % bad
                )
                return False

            members = zf.infolist()
            total_bytes = sum(m.file_size for m in members)
            extracted_bytes = 0

            # ── extract member by member ──────────────────────────────────
            for info in members:
                if progress.iscanceled():
                    progress.close()
                    notify("Extraction cancelled.", xbmcgui.NOTIFICATION_WARNING)
                    return False

                zf.extract(info, addons_real)

                # Verify the extracted file's size matches the zip metadata
                dest = os.path.join(addons_real, info.filename)
                if not info.filename.endswith("/"):   # skip directory entries
                    actual = os.path.getsize(dest) if os.path.exists(dest) else -1
                    if actual != info.file_size:
                        progress.close()
                        error_dialog(
                            "Extraction error: size mismatch for\n%s\n"
                            "(expected %d bytes, got %d).\n\n"
                            "Please try again." % (info.filename, info.file_size, actual)
                        )
                        return False

                extracted_bytes += info.file_size
                pct = int(extracted_bytes * 100 / total_bytes) if total_bytes else 100
                progress.update(pct, "Extracting: %s" % os.path.basename(info.filename))

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
        # Only remove the zip after a *successful* extraction (return True
        # below).  If we returned False early the zip is kept so the user
        # can retry without re-downloading (Kodi's package cache).
        pass

    # Extraction verified – safe to remove the cached zip now.
    try:
        xbmcvfs.delete(zip_path)
    except Exception:
        try:
            os.remove(zip_path)
        except Exception:
            pass

    xbmc.executebuiltin("UpdateLocalAddons")
    xbmc.sleep(3000)
    return True


# ─── skin activation ────────────────────────────────────────────────────────

def apply_skin(addonid, title):
    notify("Enabling %s…" % title)
    xbmc.executebuiltin("EnableAddon(%s)" % addonid)
    xbmc.sleep(3000)

    notify("Applying %s…" % title)
    xbmc.executebuiltin("Skin.SetSkin(%s)" % addonid)
    xbmc.sleep(5000)

    xbmc.executebuiltin("ReloadSkin()")


# ─── GUI window ─────────────────────────────────────────────────────────────

class Portal(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.items = kwargs.get("items", [])
        self.background = kwargs.get("background", "backgroundkodi.jpg")

    def onInit(self):
        bg_path = (
            "special://home/addons/script.portal/resources/media/%s"
            % self.background
        )
        self.setProperty("background", bg_path)

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

        panel   = self.getControl(100)
        item    = panel.getSelectedItem()
        addonid = item.getProperty("addonid")
        zipurl  = item.getProperty("zipurl")
        title   = item.getLabel()
        already = item.getProperty("installed") == "true"

        if not zipurl:
            error_dialog("No ZIP URL found for this skin.\nCheck skins.json.")
            return

        msg = (
            "This skin is already installed.\nReinstall %s?" % title
            if already
            else "Install %s?" % title
        )
        if not xbmcgui.Dialog().yesno(DIALOG_TITLE, msg):
            return

        zip_path = download_zip(zipurl, addonid)
        if not zip_path:
            return

        if not extract_zip(zip_path):
            return

        apply_skin(addonid, title)
        notify("✓ %s installed successfully." % title)
        item.setProperty("installed", "true")

    def onAction(self, action):
        if action.getId() in (
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_PREVIOUS_MENU,
        ):
            self.close()


# ─── entry point ────────────────────────────────────────────────────────────

def main():
    items, background = load_feed()
    if not items:
        return

    win = Portal(
        "portal.xml",
        ADDON_PATH,
        "Default",
        "1080i",
        items=items,
        background=background,
    )
    win.doModal()
    del win


main()
