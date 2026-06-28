"""
utils.py – Generic Kodi API wrappers used throughout TinyPPI.
"""

import xbmc


def _cond(condition: str) -> bool:
    """Return True when the given Kodi condition string is satisfied."""
    return xbmc.getCondVisibility(condition)


def _info(label: str) -> str:
    """Return the current value of a Kodi InfoLabel (never None)."""
    return xbmc.getInfoLabel(label)


def _info_safe(label: str) -> str:
    """
    Like ``_info`` but returns ``""`` when Kodi cannot resolve the InfoLabel
    and echoes the request string back instead of a value.

    On some platforms (e.g. the AM6B VTB decode path), unsupported labels such
    as ``Player.Process(amlogic.displaymode)`` or ``VideoPlayer.SubtitleCodec``
    are returned verbatim. Treat any result that still looks like the request
    token (contains ``Player.Process(`` / ``VideoPlayer.`` / ``System.`` or
    equals the bracketed argument) as unavailable.
    """
    val = xbmc.getInfoLabel(label)
    if not val:
        return ""

    stripped = val.strip()

    # Exact echo of the full label, e.g. "Player.Process(amlogic.pixformat)".
    if stripped == label.strip():
        return ""

    # Echo of just the bracketed argument, e.g. "amlogic.pixformat".
    if "(" in label and ")" in label:
        arg = label[label.find("(") + 1 : label.rfind(")")].strip()
        if arg and stripped == arg:
            return ""

    # Generic guard: result still carries an unresolved InfoLabel namespace.
    lowered = stripped.lower()
    for token in ("player.process(", "videoplayer.", "system."):
        if token in lowered:
            return ""

    return val


def _clean(val) -> str:
    """Strip commas that Kodi inserts as thousands separators."""
    if val is None:
        return ""
    return str(val).replace(",", "")
