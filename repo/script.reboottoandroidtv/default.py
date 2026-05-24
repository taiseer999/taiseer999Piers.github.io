# -*- coding: utf-8 -*-
# check for script and reboot to nand if present
import xbmc, xbmcgui
import os
import subprocess

def main():
    nandscript = '/usr/sbin/rebootfromnand'
    
    if os.path.exists(nandscript):
        xbmcgui.Dialog().notification('Success!', 'Reboot to Android TV!', xbmcgui.NOTIFICATION_INFO)
        subprocess.call([nandscript])
        xbmc.sleep(300)
        xbmc.executebuiltin('Reboot')
    else:
        xbmcgui.Dialog().notification('Error!', 'rebootfromnand not available!', xbmcgui.NOTIFICATION_ERROR)

if __name__ == '__main__':
    main()