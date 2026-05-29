from pathlib import Path
import xbmcaddon
from .config import KODI

EXCLUDE = ["cache","temp","metadata","log","thumbnails"]

def detect_addons():
    base = KODI / "addon_data"
    results = []
    for f in base.iterdir():
        if f.is_dir() and not any(x in f.name.lower() for x in EXCLUDE):
            if (f/"settings.xml").exists():
                results.append(f.name)
    return sorted(results)


def get_addon_name(addon_id):
    try:
        a = xbmcaddon.Addon(id=addon_id)
        return a.getAddonInfo("name")
    except:
        return addon_id
