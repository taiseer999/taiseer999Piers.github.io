import zipfile, json
from pathlib import Path, PurePosixPath
import shutil
import xml.etree.ElementTree as ET
from .config import KODI
from .logger import logger
from .accounts import KEYWORDS

def _safe_member_parts(member):
    path = PurePosixPath(member)
    if path.is_absolute() or any(part in ("", "..") for part in path.parts):
        return None
    return path.parts

def list_backup_addons(zip_file):
    addons = set()

    with zipfile.ZipFile(zip_file, 'r') as z:
        for member in z.namelist():
            parts = _safe_member_parts(member)
            if parts and len(parts) >= 3 and parts[0] == "addon_data":
                addons.add(parts[1])

    return sorted(addons)

def _is_auth_setting(setting_id):
    setting_id = (setting_id or "").lower()
    return any(keyword in setting_id for keyword in KEYWORDS)

def _decode_xml(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="ignore")

def _setting_value(setting):
    if "value" in setting.attrib:
        return setting.attrib.get("value"), "value"
    return setting.text or "", "text"

def _extract_auth_settings(xml_text):
    values = {}
    root = ET.fromstring(xml_text)

    for setting in root.findall("setting"):
        setting_id = setting.get("id")
        if not _is_auth_setting(setting_id):
            continue

        value, storage = _setting_value(setting)
        if value:
            values[setting_id.lower()] = {
                "id": setting_id,
                "value": value,
                "storage": storage
            }

    return values

def _accounts_fallback(z):
    try:
        raw = z.read("accounts.json")
    except KeyError:
        return {}

    try:
        return json.loads(_decode_xml(raw))
    except Exception:
        return {}

def _backup_auth_settings(z, addon, fallback_accounts):
    member = "addon_data/{}/settings.xml".format(addon)

    try:
        return _extract_auth_settings(_decode_xml(z.read(member)))
    except Exception:
        pass

    values = {}
    for setting_id, value in fallback_accounts.get(addon, {}).items():
        values[setting_id.lower()] = {
            "id": setting_id,
            "value": value,
            "storage": "text"
        }
    return values

def _merge_auth_settings(z, addon, fallback_accounts):
    auth_values = _backup_auth_settings(z, addon, fallback_accounts)
    if not auth_values:
        return False

    target = KODI / "addon_data" / addon / "settings.xml"
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        try:
            tree = ET.parse(str(target))
            root = tree.getroot()
        except Exception:
            root = ET.Element("settings")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("settings")
        tree = ET.ElementTree(root)

    current = {}
    for setting in root.findall("setting"):
        setting_id = setting.get("id")
        if setting_id:
            current[setting_id.lower()] = setting

    changed = False
    for setting_key, backup_setting in auth_values.items():
        setting = current.get(setting_key)
        if setting is None:
            setting = ET.SubElement(root, "setting", {"id": backup_setting["id"]})
            current[setting_key] = setting

        if "value" in setting.attrib or backup_setting["storage"] == "value":
            if setting.attrib.get("value") != backup_setting["value"]:
                setting.set("value", backup_setting["value"])
                changed = True
        elif setting.text != backup_setting["value"]:
            setting.text = backup_setting["value"]
            changed = True

    if changed:
        tree.write(str(target), encoding="utf-8", xml_declaration=True)

    return changed

def run_restore(zip_file, mode="full", selected=None, auth_only=False, settings_only=False):
    logger.info(f"Restore start: {zip_file}")
    selected = set(selected or [])

    with zipfile.ZipFile(zip_file,'r') as z:
        if auth_only:
            addons = selected or set(list_backup_addons(zip_file))
            fallback_accounts = _accounts_fallback(z)
            for addon in addons:
                _merge_auth_settings(z, addon, fallback_accounts)

            logger.info("Auth-only restore done")
            return

        for member in z.namelist():
            if member == "accounts.json" or member.endswith("/"):
                continue

            parts = _safe_member_parts(member)
            if not parts:
                continue

            if mode == "partial":
                if len(parts) < 3 or parts[0] != "addon_data" or parts[1] not in selected:
                    continue

            if settings_only:
                if len(parts) < 3 or parts[0] != "addon_data" or parts[2] != "settings.xml":
                    continue

            target = KODI.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target,'wb') as dst:
                shutil.copyfileobj(src,dst)

    logger.info("Restore done")
