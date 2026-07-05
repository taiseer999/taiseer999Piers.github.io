# tools.tinyppi

Various tools required for the TinyPPI add-on.

---

## Included Files

- `tools/hdrprobe/hdrprobe` - hdrprobe binary for media analysis and media processing.
- `tools/fonts/Noto-Regular.ttf` - Noto Regular font.
- `tools/fonts/Noto-Bold.ttf` - Noto Bold font.
- `icon.jpg` - Kodi add-on icon.
- `fanart.jpg` - Kodi fanart.

---

## Usage in Kodi Add-ons

Other add-ons can resolve the installation path through the Kodi add-on API and derive the included tool paths from it.

```python
import os
import xbmcaddon

addon_path = xbmcaddon.Addon("tools.tinyppi").getAddonInfo("path")
hdrprobe_path = os.path.join(addon_path, "tools", "hdrprobe", "hdrprobe")
font_regular_path = os.path.join(addon_path, "tools", "fonts", "Noto-Regular.ttf")
font_bold_path = os.path.join(addon_path, "tools", "fonts", "Noto-Bold.ttf")
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
    |-- hdrprobe/
    |   `-- hdrprobe
    `-- fonts/
        |-- Noto-Bold.ttf
        `-- Noto-Regular.ttf
```

---

## Credits

- **hdrprobe** by [matthane](https://github.com/matthane/hdrprobe) — fast HDR, HDR10+, and Dolby Vision metadata inspector. Licensed under the MIT License.
- **Google Noto Fonts** by [Google](https://github.com/notofonts/notofonts.github.io) — the Noto font family, aiming to support all languages with a harmonious look and feel. Licensed under the SIL Open Font License 1.1.
