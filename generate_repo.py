#!/usr/bin/env python3
"""
generate_repo.py — Kodi repository generator for GitHub Pages.

Layout expected (run this from the repo root):

    repo-root/
      generate_repo.py
      plugin.program.abukarimtools/
          addon.xml
          ...files...
      script.tinyppi/
          addon.xml
      script.module.acctmgr/
          addon.xml
      skin.arctic.fuse.3/          (any addon folder with an addon.xml)
          addon.xml

Produces at repo root:
    addons.xml
    addons.xml.md5
    zips/<addon-id>/<addon-id>-<version>.zip     (+ copies icon/fanart/addon.xml alongside)

Point your repository.* addon at:
    <info>...github.io/addons.xml</info>
    <checksum>...github.io/addons.xml.md5</checksum>
    <datadir zip="true">...github.io/zips/</datadir>
"""

import hashlib
import os
import shutil
import zipfile
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
ZIPS_DIR = os.path.join(ROOT, "zips")

# Folders that are never addons
SKIP = {".git", ".github", "zips", "__pycache__"}


def find_addon_dirs():
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path) or name in SKIP or name.startswith("."):
            continue
        if os.path.isfile(os.path.join(path, "addon.xml")):
            yield name, path


def read_addon_meta(addon_path):
    """Return (id, version) parsed from addon.xml."""
    tree = ET.parse(os.path.join(addon_path, "addon.xml"))
    root = tree.getroot()
    return root.get("id"), root.get("version")


def build_addons_xml(addon_dirs):
    """Concatenate every <addon> element into one addons.xml."""
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<addons>"]
    for _, path in addon_dirs:
        with open(os.path.join(path, "addon.xml"), "r", encoding="utf-8") as f:
            content = f.read()
        # strip any XML declaration inside the individual file
        content = "\n".join(
            ln for ln in content.splitlines() if not ln.strip().startswith("<?xml")
        ).strip()
        lines.append(content)
    lines.append("</addons>\n")
    return "\n".join(lines)


def write_md5(text, out_path):
    m = hashlib.md5(text.encode("utf-8")).hexdigest()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(m)
    return m


def zip_addon(addon_id, version, src_path):
    dest_dir = os.path.join(ZIPS_DIR, addon_id)
    os.makedirs(dest_dir, exist_ok=True)
    zip_name = f"{addon_id}-{version}.zip"
    zip_path = os.path.join(dest_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, _, files in os.walk(src_path):
            for fn in files:
                full = os.path.join(folder, fn)
                # arcname MUST start with the addon id as top folder
                rel = os.path.relpath(full, ROOT)
                zf.write(full, rel)

    # copy metadata assets next to the zip (Kodi reads these for the repo listing)
    for asset in ("addon.xml", "icon.png", "fanart.jpg", "changelog.txt"):
        a = os.path.join(src_path, asset)
        if os.path.isfile(a):
            shutil.copy2(a, os.path.join(dest_dir, asset))

    return zip_path


def main():
    addon_dirs = list(find_addon_dirs())
    if not addon_dirs:
        print("No addon folders (with addon.xml) found next to this script.")
        return

    xml_text = build_addons_xml(addon_dirs)
    with open(os.path.join(ROOT, "addons.xml"), "w", encoding="utf-8") as f:
        f.write(xml_text)
    md5 = write_md5(xml_text, os.path.join(ROOT, "addons.xml.md5"))

    print(f"addons.xml written  ({len(addon_dirs)} addons)")
    print(f"addons.xml.md5      {md5}")

    for name, path in addon_dirs:
        aid, ver = read_addon_meta(path)
        if aid != name:
            print(f"  ! folder '{name}' != addon id '{aid}' — Kodi needs them to match")
        z = zip_addon(aid, ver, path)
        print(f"  zipped {aid}-{ver}  ->  {os.path.relpath(z, ROOT)}")

    print("\nDone. Commit and push: addons.xml, addons.xml.md5, zips/")


if __name__ == "__main__":
    main()
