# Piers devkit (ABUKARIM TOOLS 3.2)

## Folder layout

```
devkit/
  make_build.py        builds a clean build zip from your Kodi folder or an existing zip
  export_profiles.py   generates per-skin profile zips + updates skins.json
  repo_validate.py     validates/fixes the repo (same file as repo-files/tools/)
repo-files/            copy these as-is to the root of taiseer999Piers.github.io
  abukarim/            patches.json, portal.json, presets.json, config.json
  profiles/            skin.*-profile.zip
  skins.json           now includes sha256/size/companions/profile
  tools/repo_validate.py
  .github/workflows/validate.yml
plugin.program.abukarimtools-3.2.0.0.zip
```

## 1) Building the build (on your Mac)

```bash
python3 make_build.py --src "~/Library/Application Support/Kodi" --out ~/Desktop/Piers.zip
# دايماً جرّب أول:
python3 make_build.py --src "~/Library/Application Support/Kodi" --dry-run
# نسخة خفيفة (~130MB بدل ~460MB) — الباقي ينزل من الريبوهات بأول تشغيل:
python3 make_build.py --src ... --out Piers-thin.zip --thin
# لو بدك تخلي مفتاح معيّن:
python3 make_build.py ... --keep-secret mdblist_api_key
```
Next to the zip you get `.json` (sha256 + size) and `.report.txt` (everything that was removed or changed).

## 2) The repo

1. Copy everything in `repo-files/` to the repo root and push.
2. After that, the CI runs on every push: if you upload a new skin version, it updates skins.json (zip + sha256 + size) on its own and commits.
3. To check locally: `python3 tools/repo_validate.py` (or `--fix`).

### abukarim/patches.json: a patch without a new release
```json
{"schema": 1,
 "kill": ["redlight_fixes"],
 "toggles": [["seren_fix", "Seren: Fix X"]],
 "patches": [{
   "id": "seren-x", "addon_id": "plugin.video.seren",
   "rel_path": "resources/lib/modules/x.py",
   "old": "TIMEOUT = 30", "new": "TIMEOUT = 10",
   "toggle": "seren_fix", "max_version": "3.4.99",
   "target_sha256": ["<sha256 of the original file>"]
 }]}
```
- `kill` disables a built-in patch: by toggle id, add-on id, or `addon:path`.
- Without `target_sha256` or `max_version`, the validator gives a warning (the patch could hit a version you didn't intend).
- Devices pull the file at boot (at most every 6 hours), or right away from: Patching > Update Online Fixes.

### Optional new fields in skins.json
| field | what it does |
|---|---|
| `sha256`, `size` | the tools verify the download (written automatically by CI) |
| `companions` | add-ons installed along with the skin (replaces the hardcoded map) |
| `min_kodi`, `max_kodi` | Kodi major version; incompatible skins are hidden |
| `platforms` | `coreelec`, `android`, `linux`, `osx`, `windows` |
| `profile`, `profile_sha256` | Piers profile (settings + menus + widgets) applied before the skin is activated |

To make a new profile from a device: Skin Profiles > Export Current Skin Profile, upload the zip to `profiles/`, and paste the snippet it shows you.

### config.json
- `min_tools_version`: devices running an older version get an update notification.
- `notice` `{id, en, ar}`: a notification shown once to all devices; change the `id` to send a new one.

## Notes
- The CE catalog has a broken entry: "Estuary MOD V2 Omega Cpm" has id `skin.avdvplus.estuary`, but the zip contains `skin.estuary.modv2cpm` inside a folder named `skin.estuary.modv2/`. The installer can never activate it. Fix: repackage the zip with the folder named `skin.estuary.modv2cpm/` and set the id in skins.json to `skin.estuary.modv2cpm`.
