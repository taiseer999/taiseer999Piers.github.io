# -*- coding: utf-8 -*-
"""Stand-alone launcher for the AF3 auto-trailers engine (ABUKARIM TOOLS 3.1.17).

Kodi does not always start this add-on's xbmc.service (some boots it simply
never runs, see default._ensure_service), and the trailer engine used to live
only inside that service. This script runs the engine by itself, in its own
Python invocation, for the rest of the session. It is started:
  * by Arctic Fuse 3's Home window onload (patched in while the feature is on)
    whenever Window(Home).Property(abukarimtools.trailers.engine) is empty;
  * by the Toggles entry when the feature is turned on.
A second copy exits at once (the engine property guards it).

    RunScript(special://home/addons/plugin.program.abukarimtools/trailers.py)
"""
import sys

import xbmc
import xbmcvfs

ROOT = xbmcvfs.translatePath('special://home/addons/plugin.program.abukarimtools/')
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from resources.lib.af3_trailers import engine  # noqa: E402

if __name__ == '__main__':
    origin = sys.argv[1] if len(sys.argv) > 1 else 'launcher'
    engine.run_here(xbmc.Monitor(), origin)
