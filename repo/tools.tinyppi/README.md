# tools.tinyppi

Various tools required for the TinyPPI add-on.

---

## Included Files

- `tools/ffmpeg/ffmpeg` - FFmpeg binary for media analysis and media processing.
- `tools/mediainfo/mediainfo` - MediaInfo binary for media analysis and media processing.
- `tools/dovi/dovi_tool` - dovi_tool binary for Dolby Vision related processing.
- `tools/fonts/Inter-Regular.ttf` - Inter Regular font.
- `tools/fonts/Inter-Bold.ttf` - Inter Bold font.
- `icon.jpg` - Kodi add-on icon.
- `fanart.jpg` - Kodi fanart.

---

## Usage in Kodi Add-ons

Other add-ons can resolve the installation path through the Kodi add-on API and derive the included tool paths from it.

```python
import os
import xbmcaddon

addon_path = xbmcaddon.Addon("tools.tinyppi").getAddonInfo("path")
ffmpeg_path = os.path.join(addon_path, "tools", "ffmpeg", "ffmpeg")
mediainfo_path = os.path.join(addon_path, "tools", "mediainfo", "mediainfo")
dovi_tool_path = os.path.join(addon_path, "tools", "dovi", "dovi_tool")
font_regular_path = os.path.join(addon_path, "tools", "fonts", "Inter-Regular.ttf")
font_bold_path = os.path.join(addon_path, "tools", "fonts", "Inter-Bold.ttf")
```

---

## Project Structure

```text
tools.tinyppi/
|-- addon.xml
|-- fanart.jpg
|-- icon.jpg
|-- LICENSE
|-- README.md
`-- tools/
    |-- dovi/
    |   `-- dovi_tool
    |-- ffmpeg/
    |   `-- ffmpeg
    |-- mediainfo/
    |   `-- mediainfo
    `-- fonts/
        |-- Inter-Bold.ttf
        `-- Inter-Regular.ttf
```
