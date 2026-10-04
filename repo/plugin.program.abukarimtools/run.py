# -*- coding: utf-8 -*-
"""
run.py — Manually trigger the ABUKARIM TOOLS first-run sequence.

This runs the SAME steps the service runs on first boot (Binary Installer ->
Restore popup -> Add-on Portal -> Patches -> Skin Installer), but on demand — it does NOT wait for the
home screen or any wizard. Use it whenever you want to (re)run setup without
rebooting.

How to launch it:
  • Favourite / keymap / shortcut:
        RunScript(plugin.program.abukarimtools, firstrun)
    or equivalently:
        RunScript(special://home/addons/plugin.program.abukarimtools/run.py)
"""

import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

# Make sure the addon root is importable so 'service' and 'resources.lib.*'
# resolve the same way they do when Kodi launches the service.
ADDON      = xbmcaddon.Addon('plugin.program.abukarimtools')
ADDON_ROOT = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
if ADDON_ROOT not in sys.path:
    sys.path.insert(0, ADDON_ROOT)

import service  # noqa: E402  (path set up above)


def _confirm():
    """Ask before running, so it isn't triggered by accident."""
    return xbmcgui.Dialog().yesno(
        'ABUKARIM TOOLS',
        'Run first-time setup now?\n\n'
        'This will install binaries, offer a backup restore, open the '
        'Add-on Portal, apply patches, then open the Skin Installer.',
        yeslabel='Run setup',
        nolabel='Cancel',
    )


def main():
    # Allow a silent mode: RunScript(..., firstrun, silent)
    args = [a.lower() for a in sys.argv[1:]]
    silent = 'silent' in args
    # 'force' = deliberate re-run from the Tools menu (clears a stale lock and
    # ignores the done marker), same as the old in-plugin path did.
    force = 'force' in args

    if not silent and not _confirm():
        return

    monitor = xbmc.Monitor()
    # remove_flag=True keeps it one-shot on the next boot too; the manual run
    # has effectively done first-run already.
    service.run_now(monitor, remove_flag=True, force=force)


if __name__ == '__main__':
    main()
