import json
import xml.etree.ElementTree as ET
from pathlib import Path
from .config import KODI

KEYWORDS = ["token", "api", "key", "auth", "secret", "username", "password"]

def extract_tokens(xml_text):
    result = {}

    try:
        root = ET.fromstring(xml_text)

        for setting in root.findall("setting"):
            sid = setting.get("id", "").lower()
            value = setting.get("value") if "value" in setting.attrib else setting.text

            if not value:
                continue

            if any(k in sid for k in KEYWORDS):
                result[sid] = value

    except Exception as e:
        pass

    return result


def export_accounts(addons):
    data = {}

    for addon in addons:
        f = KODI / "addon_data" / addon / "settings.xml"

        if not f.exists():
            continue

        try:
            text = f.read_text(encoding="utf-8")
        except:
            text = f.read_text(encoding="latin-1", errors="ignore")

        tokens = extract_tokens(text)

        if tokens:
            data[addon] = tokens

    return data


def save_accounts(data, dest):
    path = Path(dest) / "accounts.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path
