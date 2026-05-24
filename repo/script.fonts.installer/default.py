import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import os
import shutil
import xml.etree.ElementTree as ET

addon = xbmcaddon.Addon()
addon_name = addon.getAddonInfo('name')
addon_icon = xbmcvfs.translatePath(addon.getAddonInfo('icon'))
addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
font_source = os.path.join(addon_path, 'resources', 'fonts')
font_dest = os.path.join(xbmcvfs.translatePath('special://home/media/Fonts'))
fontcache_path = os.path.join(font_source, 'fontcache.xml')
fontcache_dest = os.path.join(font_dest, 'fontcache.xml')

def install_fonts():
    if not os.path.exists(font_dest):
        try:
            os.makedirs(font_dest)
        except Exception:
            pass

    try:
        tree = ET.parse(fontcache_path)
        root = tree.getroot()
        for font in root.findall('font'):
            filename = font.find('filename').text
            if filename:
                src = os.path.join(font_source, filename)
                dest = os.path.join(font_dest, filename)
                if os.path.isfile(src):
                    try:
                        shutil.copy(src, dest)
                    except Exception:
                        pass

        if os.path.isfile(fontcache_path):
            shutil.copy(fontcache_path, fontcache_dest)
    except Exception:
        pass

def uninstall_fonts():
    if not os.path.exists(fontcache_path):
        return

    try:
        tree = ET.parse(fontcache_path)
        root = tree.getroot()
        for font in root.findall('font'):
            filename = font.find('filename').text
            if filename:
                dest = os.path.join(font_dest, filename)
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass

        if os.path.exists(fontcache_dest):
            try:
                os.remove(fontcache_dest)
            except Exception:
                pass
    except Exception:
        pass

def fonts_exist():
    if not os.path.exists(fontcache_path):
        return False

    try:
        tree = ET.parse(fontcache_path)
        root = tree.getroot()
        for font in root.findall('font'):
            filename = font.find('filename').text
            if filename:
                dest = os.path.join(font_dest, filename)
                if not os.path.exists(dest):
                    return False
        return os.path.exists(fontcache_dest)
    except Exception:
        return False

def refresh_fonts():
    try:
        xbmc.executebuiltin('ReloadSkin()')
        xbmc.executebuiltin('ReloadSettings("subtitles")')
    except Exception:
        pass

if __name__ == '__main__':
    if fonts_exist():
        uninstall_fonts()
        refresh_fonts()
        xbmcgui.Dialog().notification(addon_name, "Fonts removed successfully!", addon_icon, 5000)
    else:
        install_fonts()
        refresh_fonts()
        xbmcgui.Dialog().notification(addon_name, "Fonts installed successfully!", addon_icon, 5000)
