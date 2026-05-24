import xbmc
import xbmcaddon
import xbmcgui
import os
import sys
import binascii
import xbmcvfs
try:
    import json
except:
    import simplejson as json
from PIL import Image
from capture import capture_frame


ADDON = xbmcaddon.Addon()
ADDONID = ADDON.getAddonInfo('id')
ADDONVERSION = ADDON.getAddonInfo('version')

player_width = 0
player_height = 0
player_filename = ""
player_timecode = ""


def log(txt):
    if isinstance(txt, str):
        txt = txt.decode("utf-8")
        message = u'%s: %s\n' % (ADDONID, txt)
        xbmc.log(msg=message.encode("utf-8"), level=xbmc.LOGNOTICE)


def get_player_info():
    global player_width
    global player_height
    global player_filename
    global player_timecode
    player_width = int(xbmc.getInfoLabel(
        "Player.Process(VideoWidth)").replace(",", ""))
    player_height = int(xbmc.getInfoLabel(
        "Player.Process(VideoHeight)").replace(",", ""))
    player_filename = os.path.splitext(xbmc.getInfoLabel("Player.Filename"))[0]
    player_timecode = xbmc.getInfoLabel("Player.Time").replace(":", "_")


def adjust_capture_size():
    global player_height, player_width
    if player_width <= 3840:
        player_width = player_width // 2
        player_height = player_height // 2


def check_aspect():
    global player_width, player_height
    wanted_aspect = 16.0 / 9.0
    aspect = float(player_width) / float(player_height)
    log("Found Aspect: {0} Wanted Aspect: {1}".format(aspect, wanted_aspect))
    if (aspect == wanted_aspect):
        player_width = 1920
        player_height = 1080
        return
    player_width = 1920
    player_height = int(float(player_width) / aspect)


def check_capture_dir():
    if not xbmcvfs.exists("special://screenshots/" + player_filename):
        xbmcvfs.mkdir("special://screenshots/" + player_filename)


def main():
    global player_width
    global player_height
    global player_filename
    global player_timecode

    log("************************")
    log("Started...")

    get_player_info()

    log("Original Video Width: " + str(player_width))
    log("Original Video Height: " + str(player_height))

    check_aspect()

    # if player_width > 1920:
    #     adjust_capture_size()
    # if player_width < 1920:
    #     aspect = float(float(player_width) / float(player_height))
    #     log("Aspect: " + str(aspect))
    #     player_width = 1920
    #     player_height = int(player_width // aspect)

    log("Capture Width: " + str(player_width))
    log("Capture Height: " + str(player_height))
    log("Filename: " + player_filename)
    log("Player Time: " + player_timecode)

    check_capture_dir()

    img = Image.new("RGB", (player_width, player_height), 0x0)

    buffer = capture_frame(player_width, player_height)

    outbuf = [0] * (player_width * player_height)
    index = 0
    for o in xrange(player_width * player_height):
        outbuf[o] = (buffer[index], buffer[index+1], buffer[index+2])
        index += 3

    img.putdata(outbuf)

    log("Saving...")
    path = xbmc.translatePath("special://screenshots/" + player_filename)
    log("Path: " + path)
    filename = "/" + player_timecode + ".png"
    img.save(path + filename)
    log("Save complete")
    xbmcgui.Dialog().notification('Amlogic Capture',
                                  'Image saved.', xbmcgui.NOTIFICATION_INFO, 2000)


if (__name__ == "__main__"):
    main()
