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
import shutil

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
    options = ["Kodi 21.3 Repository", "CoreELEC 21.3 \"NG\" Repository", "Piers and Kodi 22 \"NO\" Repository"]
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
    Stream the zip to a native temp file (avoids xbmcvfs write truncation on
    slow/embedded storage).  Shows a byte-accurate progress bar.
    Returns the local path on success, None on failure/cancel.
    """
    if not xbmcvfs.exists(PACKAGES_PATH):
        xbmcvfs.mkdirs(PACKAGES_PATH)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="portal_dl_")

    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Connecting…")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kodi"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 65536
            downloaded = 0

            with os.fdopen(tmp_fd, "wb") as fh:
                tmp_fd = None           # fdopen owns the fd now
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
                # fh flushed + closed here

        # Verify integrity before accepting
        progress.update(100, "Verifying download…")
        if not zipfile.is_zipfile(tmp_path):
            error_dialog(
                "Download incomplete or corrupt.\n"
                "The file is not a valid ZIP archive.\nPlease try again."
            )
            return None

        zip_path = os.path.join(PACKAGES_PATH, "%s.zip" % addonid)
        try:
            os.replace(tmp_path, zip_path)
        except OSError:
            shutil.copy2(tmp_path, zip_path)
            os.remove(tmp_path)
        tmp_path = None

        progress.close()
        return zip_path

    except urllib.error.URLError as e:
        progress.close()
        error_dialog("Download failed (network):\n%s" % e.reason)
    except Exception as e:
        progress.close()
        error_dialog("Download failed:\n%s" % str(e))
    finally:
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
    Extract *zip_path* safely using a staging folder.

    Key fix for the Kodi 22 SIGBUS / font-folder crash:
    -------------------------------------------------------
    Kodi's font renderer (CGUIFontTTF) maps font files directly into memory
    (mmap).  When our addon extracts a skin zip that contains a Fonts/ folder,
    the old approach wrote files directly into the live addons directory.  If
    Kodi's skin system picked up the new addon path mid-extraction — which it
    can do as soon as UpdateLocalAddons fires — it would mmap a partially-
    written font file and crash with SIGBUS (bus error on unaligned/invalid
    memory access).

    The fix:
      1. Extract everything into a private temp directory (staging).
      2. Run a CRC integrity check + per-file size verification there.
      3. Only once the staging tree is complete and verified, atomically
         move each top-level addon folder into the live addons directory.
      4. Call UpdateLocalAddons / ReloadSkin only AFTER the move is done.

    This guarantees Kodi's renderer never sees a half-written font file.
    """
    progress = xbmcgui.DialogProgress()
    progress.create(DIALOG_TITLE, "Preparing extraction…")

    # Use a staging directory next to the addons folder to maximise the
    # chance that os.rename() is atomic (same filesystem).
    staging_parent = os.path.join(ADDONS_PATH, ".portal_staging")
    staging_dir    = None

    try:
        os.makedirs(staging_parent, exist_ok=True)
        staging_dir = tempfile.mkdtemp(dir=staging_parent, prefix="extract_")

        with zipfile.ZipFile(zip_path, "r") as zf:

            # ── CRC integrity check before touching the filesystem ────────
            progress.update(0, "Checking archive integrity…")
            bad = zf.testzip()
            if bad is not None:
                progress.close()
                error_dialog(
                    "ZIP integrity check failed.\n"
                    "First bad file: %s\n\nPlease try downloading again." % bad
                )
                return False

            members    = zf.infolist()
            total_bytes = sum(m.file_size for m in members) or 1
            extracted_bytes = 0

            # ── extract every member into staging ────────────────────────
            for info in members:
                if progress.iscanceled():
                    progress.close()
                    notify("Extraction cancelled.", xbmcgui.NOTIFICATION_WARNING)
                    return False

                zf.extract(info, staging_dir)

                # Per-file size verification
                if not info.filename.endswith("/"):
                    dest = os.path.join(staging_dir, info.filename)
                    actual = os.path.getsize(dest) if os.path.exists(dest) else -1
                    if actual != info.file_size:
                        progress.close()
                        error_dialog(
                            "Extraction error: size mismatch for\n%s\n"
                            "(expected %d B, got %d B).\n\n"
                            "Please try again." % (info.filename, info.file_size, actual)
                        )
                        return False

                extracted_bytes += info.file_size
                pct = int(extracted_bytes * 100 / total_bytes)
                progress.update(pct, "Extracting: %s" % os.path.basename(info.filename))

        # ── atomic move from staging → live addons directory ─────────────
        # This is the critical step: Kodi only sees complete, fsync'd files.
        progress.update(99, "Installing…")

        for top_name in os.listdir(staging_dir):
            src  = os.path.join(staging_dir, top_name)
            dest = os.path.join(ADDONS_PATH, top_name)

            # Remove any existing (possibly partial) installation first
            if os.path.exists(dest):
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                else:
                    os.remove(dest)

            try:
                os.rename(src, dest)          # atomic on same filesystem
            except OSError:
                shutil.copytree(src, dest)    # cross-fs fallback

        progress.update(100, "Done.")
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
        # Always clean up the staging tree
        if staging_dir and os.path.exists(staging_dir):
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass
        # Clean up the staging parent if it's now empty
        try:
            if os.path.exists(staging_parent) and not os.listdir(staging_parent):
                os.rmdir(staging_parent)
        except Exception:
            pass

    # Zip is removed only after a successful, verified extraction
    try:
        xbmcvfs.delete(zip_path)
    except Exception:
        try:
            os.remove(zip_path)
        except Exception:
            pass

    # Let Kodi re-scan now that all files are fully in place
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
        self.items      = kwargs.get("items", [])
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

        # Fix: only set focus if the panel has items — avoids the
        # "Control 100 asked to focus but it can't" error logged on Kodi 22
        # when the list is empty or not yet rendered.
        if self.items:
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
