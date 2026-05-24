# script.tinyppi – Kodi Addon

A Kodi addon that displays detailed playback information in a custom overlay window during video playback. It provides real-time data on video, audio, HDR, system resources, and more — with special support for **Amlogic** hardware (e.g. CoreELEC devices).

---

## Installation

1. Copy the `script.tinyppi` folder into your Kodi addons directory:
   - **Linux:** `~/.kodi/addons/`
   - **Windows:** `%APPDATA%\Kodi\addons\`
   - **CoreELEC / LibreELEC:** `/storage/.kodi/addons/`
2. In Kodi: *Settings → Add-ons → Install from ZIP file* and activate the addon.

---

## Usage

### Launch via Python (from another addon or autostart)
```python
import xbmc
xbmc.executebuiltin('RunScript(script.tinyppi)')
```

### Launch via Kodi URL
```
plugin://script.tinyppi/
```

### Assign a keyboard shortcut
In your `keyboard.xml` (Kodi keymap):
```xml
<keymap>
  <global>
    <keyboard>
      <i>RunScript(script.tinyppi)</i>
    </keyboard>
  </global>
</keymap>
```

---

## Displayed Information

The overlay is divided into four sections:

### Video
| Field | Description |
|---|---|
| Display Mode | Active display output mode with normalized refresh rate (e.g. `1080p 23.976Hz`) |
| Video Mode | Resolution, scan type and frame rate (e.g. `1920x1080p 23.976FPS`) |
| Pixel Format | Color bit depth and chroma subsampling (e.g. `10-bit (YUV 4:2:0)`) |
| Aspect Ratio | Display aspect ratio from `Player.Process(videodar)` |
| Decoder | Active video decoder with HW/SW indicator |
| Codec | Video codec in use (e.g. `HEVC`, `AVC`) |
| Deinterlacing | Active deinterlace method |

### Processing
| Field | Description |
|---|---|
| HDR Type | Detected HDR format: `SDR`, `HDR10`, `HDR10+`, `HLG`, or `Dolby Vision Profile` |
| HDR Detail | Dolby Vision layer info with color-coded FEL (green) / MEL (orange) |
| Bitrate | Video stream bitrate in Mb/s |
| Mode | Amlogic EOFT/Gamut mode (first token) |
| Gamut | Amlogic EOFT/Gamut color gamut (second token) |
| Playback Time | Current position / total duration with progress percentage |

### System
| Field | Description |
|---|---|
| Memory Usage | RAM used in percent and absolute (used / total) |
| Processor | CPU temperature and per-core usage (e.g. `45°C \| 12 \| 08 \| 15 \| 10`) |
| System FPS | Kodi UI render rate in FPS |
| Player Cache | Current buffer/cache level in percent |

### Audio
| Field | Description |
|---|---|
| Codec | Human-readable audio codec name with channel layout and spatial flag (e.g. `Dolby TrueHD 7.1 (Atmos)`) |
| Bit Depth / Sample Rate | Audio bit depth and sample rate (e.g. `24-bit \| 48 kHz`) |
| Bitrate | Audio stream bitrate in Kb/s |
| Input | Raw audio input channel configuration |
| Output | `Passthrough` (if active) or decoded PCM channel layout |
| Audio Language | Active audio track language |
| Subtitle Language | Active subtitle language, or `Disabled` / `N/A` |

---

## Window Properties (playerprops.py)

The `playerprops.py` module computes and publishes the following `Window().Property()` values, which are referenced in the skin XML:

| Property | Description |
|---|---|
| `VideoDecoderVar` | `HW` or `SW` based on `Player.Process(videohwdecoder)` |
| `VideoPixelFormatVar` | Formatted pixel format from `amlogic.pixformat` |
| `DisplayModeVar` | Display mode string with normalized frame rate |
| `VideoResolutionVar` | Combined `WxH{scan} {fps}FPS` string |
| `VideoBitrateMBVar` | Video bitrate converted from kb/s to Mb/s |
| `AudioBitrateMBVar` | Audio bitrate converted from kb/s to Kb/s |
| `HdrTypeVar` | Normalized HDR label (`SDR`, `HDR10`, `HDR10+`, `HLG`, `Dolby Vision Profile`) |
| `HdrDetailVar` | Dolby Vision layer details with `[COLOR]` markup |
| `ModeVar` | First word from `amlogic.eoft_gamut` |
| `GamutVar` | Second word from `amlogic.eoft_gamut` |
| `AudioCodecVar` | Mapped human-readable codec name (e.g. `Dolby TrueHD`, `DTS-HD MA`) |
| `AudioCodecSpatialVar` | Spatial audio suffix: `(Atmos)`, `(IMAX)`, or empty |
| `AudioChannelsVar` | Channel layout string (e.g. `5.1`, `7.1`) |
| `AudioSampleRateVar` | Sample rate in kHz (e.g. `48 kHz`, `96 kHz`) |
| `SubtitleVar` | Active subtitle language; falls back to `SubtitlesLangEx` |
| `CpuUsageVar` | Per-core CPU usage as zero-padded values joined by ` \| ` |

These properties are updated by calling `update_properties(window)` from the addon's main `WindowXMLDialog` class — typically in `onInit()` and a polling loop.

---

## Skin Layout

The overlay XML (`script-tinyppi-main.xml`) is located at:
```
resources/skins/Default/1080i/script-tinyppi-main.xml
```

The window layout targets a **1920×1080** coordinate space and is organized as follows:

- A full-screen semi-transparent gradient background
- **Left column** (offset `x=30`):
  - Video section at top
  - Processing section at `y+300`
- **Right column** (offset `x=640`):
  - System section at top
  - Audio section at `y+300`

Each section has a header with an iconic font glyph and a bold uppercase label, followed by label-value pairs at 30px vertical intervals. Long values (audio channels sink, language) use `<scroll>true</scroll>` for marquee scrolling.

Window open/close uses a cubic ease-in/out fade animation (350 ms open, 150 ms close). On open, the fullscreen video OSD and seekbar dialogs are automatically closed.

---

## Notes

- The overlay is only intended to be used while media is actively playing.
- Close the window with `Backspace`, `Esc`, or any mapped close action.
- Amlogic-specific properties (`amlogic.pixformat`, `amlogic.displaymode`, `amlogic.eoft_gamut`) are only populated on Amlogic-based devices running CoreELEC with the appropriate driver support. On other platforms these fields will be empty.
- Font icons in section headers require the `font10_iconic_regular` font to be installed in the active Kodi skin.
- The Python property module is designed to be embedded in the addon and called from a `WindowXMLDialog` subclass. No standalone service process is required.
