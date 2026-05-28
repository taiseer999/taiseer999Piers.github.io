import xbmcgui
import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')


class SettingsDialog(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def onInit(self):
        pass

    def onClick(self, controlId):
        if controlId == 1001:
            self.close()
            from default import open_tinyppi
            open_tinyppi()

    def onAction(self, action):
        if action.getId() in (
            xbmcgui.ACTION_PREVIOUS_MENU,
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_STOP,
        ):
            self.close()


def open_dialog():
    win = SettingsDialog(
        'script-tinyppi-dialog.xml',
        ADDON_PATH,
        'Default',
        '1080i'
    )
    win.doModal()
    del win
