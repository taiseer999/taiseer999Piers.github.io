# -*- coding: utf-8 -*-

import xbmc
import xbmcaddon
import xbmcgui
import time
import simplejson
import xbmcvfs
import sys

import xml.etree.ElementTree as ET



__addon__    = xbmcaddon.Addon()
__addonid__  = __addon__.getAddonInfo('id')
__version__  = __addon__.getAddonInfo('version')
__language__ = __addon__.getLocalizedString
__cwd__      = __addon__.getAddonInfo('path')

my_skin_addon = xbmcaddon.Addon('skin.aczg')


def log(txt):
    if isinstance(txt,str):
        if sys.version_info.major == 2:# Python 2
            txt = txt.decode('utf-8')
        else:# Python 3
            txt = txt
    if sys.version_info.major == 2:# Python 2
        message = u'%s: %s' % (__addonid__, txt)
        xbmc.log(msg=message.encode('utf-8'), level=xbmc.LOGDEBUG)
    else:# Python 3
        message = str(u'%s: %s' % (__addonid__, txt))
        xbmc.log(msg=message, level=xbmc.LOGDEBUG)



class MyPlayer(xbmc.Player):
    
    def __init__(self,*args,**kwargs):
        xbmc.Player.__init__(self)
        self.videoFinishedPercentage = 80
        
        
        
        self.BuildVersionStr = str(xbmc.getInfoLabel('System.BuildVersion'))
        self.BuildVersionIsBetterUI = self.BuildVersionStr.find('BetterUI') >= 0
        
        
        
        self.videolibrary_itemseparator_default          = ' / ' if not self.BuildVersionIsBetterUI else ' · '
        self.videolibrary_itemseparator_advancedsettings = self.videolibrary_itemseparator_default
        
        self.videolibrary_itemseparator_fallback         = ' / ' if self.BuildVersionIsBetterUI else ''
        
        
        
        # check for potential advancedsettings.xml user value of 'videolibrary.itemseparator'
        
        xmlpath = 'special://userdata/advancedsettings.xml'
        if sys.version_info.major == 2:# Python 2
            xmlfile = xbmc.translatePath(xmlpath).decode('utf-8')
        else:
            xmlfile = xbmcvfs.translatePath(xmlpath)
        
        if xmlfile and xbmcvfs.exists(xmlfile):
            try:
                tree = ET.parse(xmlfile)
                root = tree.getroot()
                
                if tree and root:
                    for itemseparator in root.findall('./videolibrary/itemseparator'):
                        if itemseparator.text:
                            self.videolibrary_itemseparator_advancedsettings = str(itemseparator.text)
                            break
            except:
                log('advancedsettings.xml parsing error')
        
        
        
        self.startTimer = time.time()
        self.endTimer = time.time()
        
        self.percentageTimer = time.time()
        self.playerPercentage = 0
        
        self.idleCheckIntervalTimer = time.time()
        
        self.VideoPlayerIsMovie = False
        self.VideoPlayerDbId = -1
        self.VideoPlayerIsMovieInDb = False
        self.PlayerAudioOnly = False
        
        self.movieHasPostCreditsScene = False
        self.nearEndPreReached = False
        self.nearEndReached = ''
        
        self.skinIsACZG = xbmc.getSkinDir() == 'skin.aczg'
        
        self.KodiLanguage = str(xbmc.getInfoLabel('System.Language'))
        
        
        
        self.isKodi18plus = not self.BuildVersionStr.find('17.') == 0
        self.isKodi21plus = self.isKodi18plus and not self.BuildVersionStr.find('18.') == 0 and not self.BuildVersionStr.find('19.') == 0 and not self.BuildVersionStr.find('20.') == 0
        self.isKodi22plus = self.isKodi21plus and not self.BuildVersionStr.find('21.') == 0
        
        if self.isKodi18plus:
            xbmcgui.Window(10000).setProperty('CH.Kodi18+', 'True')
        if self.isKodi21plus:
            xbmcgui.Window(10000).setProperty('CH.Kodi21+', 'True')
        if self.isKodi22plus:
            xbmcgui.Window(10000).setProperty('CH.Kodi22+', 'True')
        
        
        
        if self.skinIsACZG:
            
            # Modify Skin language strings for 'System' section
            modifySettingsLanguageStringsStartNow()
            
            # Convert some Kodi language strings
            LocalizeStringsPropertiesStartNow()
            
            # 24p check
            do24pCheck()
        
        
        
        xbmcgui.Window(10000).setProperty('CinemaHelper.System.Language', str(xbmc.getInfoLabel('System.Language')))
        xbmcgui.Window(10000).setProperty('CinemaHelper.getSkinDir', str(xbmc.getSkinDir()))
    
    
    
    def onPlayBackEnded(self):
        self.onPlayBackStopped()
    
    def onPlayBackStopped(self):
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.DBID')
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.nearEndPreReached')
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.nearEndReached')
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.movieHasPostCreditsScene')
        
        self.movieHasPostCreditsScene = False
        self.nearEndPreReached = False
        self.nearEndReached = ''
        
        self.endTimer = time.time()
        
        
        if not self.PlayerAudioOnly:
            xbmcgui.Window(10000).setProperty('PlayBackJustEnded', 'True')
        
        self.VideoPlayerIsMovie = False
        self.VideoPlayerDbId = -1
        self.PlayerAudioOnly = False
        
        # studio
        for x in range(1, 11):
            # clear all
            xbmcgui.Window(10000).clearProperty('CinemaHelper.player.studio.'+str(x)+'')
        
        if self.VideoPlayerIsMovieInDb:
            self.VideoPlayerIsMovieInDb = False
            
            CinemaPostPlaybackDialogType = int(xbmc.getInfoLabel('Skin.String(CinemaPostPlaybackDialogType)')) if xbmc.getInfoLabel('Skin.String(CinemaPostPlaybackDialogType)') else 0
            
            if self.skinIsACZG and CinemaPostPlaybackDialogType > 0 and self.playerPercentage > self.videoFinishedPercentage:
                
                self.playerPercentage = 0
                
                myPlaylist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                playlistSize = myPlaylist.size()
                playlistPosition = myPlaylist.getposition()
                
                CinemaPostPlaybackDBID = xbmcgui.Window(10000).getProperty('CinemaPostPlaybackDBID')
                
                if CinemaPostPlaybackDBID != '' and playlistSize <= 1 and playlistPosition <= 0:
                    
                    if CinemaPostPlaybackDialogType > 0:
                        
                        xbmcgui.Window(10000).setProperty('CinemaPostPlaybackDialogOpensNow', 'True')
                        
                        xbmc.executebuiltin('ActivateWindow(1190)')
                        
                        if CinemaPostPlaybackDialogType == 1:
                            
                            xbmc.sleep(500)
                            
                            xbmc.executebuiltin('SetFocus(43260)')
                            
                            xbmc.sleep(500)
                        
                            xbmc.executebuiltin('Action(Info)')
                        
                            xbmc.sleep(500)
                        
                            xbmc.executebuiltin('Dialog.Close(1190,true)')

    # onPlayBackStarted Kodi 17 | onAVStarted Kodi 18+
    def onAVStarted(self):
        
        xbmcgui.Window(10000).setProperty('PlayBackJustStarted', 'True')
        
        self.VideoPlayerIsMovie = False
        self.VideoPlayerDbId = -1
        self.playerPercentage = 0
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.DBID')
        
        self.startTimer = time.time()
        
        xbmcgui.Window(10000).setProperty('CinemaPostPlaybackDBID', '')
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.nearEndPreReached')
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.nearEndReached')
        
        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.movieHasPostCreditsScene')
        
        self.movieHasPostCreditsScene = False
        self.nearEndPreReached = False
        self.nearEndReached = ''
        
        
        # studio
        for x in range(1, 11):
            # clear all
            xbmcgui.Window(10000).clearProperty('CinemaHelper.player.studio.'+str(x)+'')
        
        
        if not self.isKodi18plus:
            # Kodi 17 onPlayBackStarted needs a medium wait so player properties can get populated and don't come back empty
            xbmc.sleep(1000)
        else:
            # Kodi 18+ very short wait just to be sure (most likely not needed if Kodi 18+ onAVStarted works as advertised)
            xbmc.sleep(25)
        
        
        self.VideoPlayerIsMovie = xbmc.getCondVisibility('VideoPlayer.Content(Movies)')
        
        self.VideoPlayerDbId = int(xbmc.getInfoLabel('VideoPlayer.DBID')) if xbmc.getInfoLabel('VideoPlayer.DBID') else -1
        self.VideoPlayerIsMovieInDb = self.VideoPlayerIsMovie and self.VideoPlayerDbId > 0 and xbmc.getCondVisibility('VideoPlayer.HasInfo')
        self.PlayerAudioOnly = xbmc.getCondVisibility('Player.HasMedia') and xbmc.getCondVisibility('Player.HasAudio') and not xbmc.getCondVisibility('Player.HasVideo')
        
        if self.VideoPlayerDbId > 0:
            xbmcgui.Window(10000).setProperty('CinemaHelper.player.DBID', str(self.VideoPlayerDbId))
        
        if self.VideoPlayerIsMovieInDb:
            
            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid":'+str(playerMonitor.VideoPlayerDbId)+',"properties":["title","tag"]}, "id": 1}')
            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
            jsonQuery = simplejson.loads(jsonQuery)
            
            tmpHasKeyCheck = 'result' in jsonQuery and 'moviedetails' in jsonQuery['result'] and 'tag' in jsonQuery['result']['moviedetails']
            
            if tmpHasKeyCheck:
                if 'aftercreditsstinger' in jsonQuery['result']['moviedetails']['tag'] or 'duringcreditsstinger' in jsonQuery['result']['moviedetails']['tag']:
                    self.movieHasPostCreditsScene = True
                    xbmcgui.Window(10000).setProperty('CinemaHelper.player.movieHasPostCreditsScene', 'True')
            
            xbmcgui.Window(10000).setProperty('CinemaPostPlaybackDBID', str(self.VideoPlayerDbId))
            
            VideoPlayerStudio = str(xbmc.getInfoLabel('VideoPlayer.Studio'))
            if VideoPlayerStudio:
                if not self.videolibrary_itemseparator_default == self.videolibrary_itemseparator_advancedsettings and self.videolibrary_itemseparator_advancedsettings in VideoPlayerStudio:
                    splitString = VideoPlayerStudio.split(self.videolibrary_itemseparator_advancedsettings)
                else:
                    if self.videolibrary_itemseparator_default in VideoPlayerStudio or not self.videolibrary_itemseparator_fallback:
                        splitString = VideoPlayerStudio.split(self.videolibrary_itemseparator_default)
                    else:
                        splitString = VideoPlayerStudio.split(self.videolibrary_itemseparator_fallback)
                if splitString:
                    indexNo = 1
                    for item in splitString:
                        xbmcgui.Window(10000).setProperty('CinemaHelper.player.studio.'+str(indexNo), str(item))
                        indexNo += 1
                        if indexNo > 10:
                            break

#/class







def do24pCheck():
    # 24p check
    success_file = '/24p_check/24p_check_SUCCESS'
    if sys.version_info.major == 2:
        check_24p_file = xbmc.translatePath('special://xbmc' + success_file).decode('utf-8')
    else:
        check_24p_file = xbmcvfs.translatePath('special://xbmc' + success_file)
    
    check_24p_file_ok = xbmcvfs.exists(check_24p_file)
    if check_24p_file_ok:
        xbmcgui.Window(10000).setProperty('CinemaHelper.24p', 'True')
    else:
        xbmcgui.Window(10000).clearProperty('CinemaHelper.24p')






def modifySettingsLanguageString(myLanguageStringId):
    
    clearString = False
    
    if myLanguageStringId:
        
        if xbmcgui.Window(10000).getProperty('CH.Kodi22+'):
            myLanguageString = my_skin_addon.getLocalizedString(myLanguageStringId).encode('utf-8') if sys.version_info.major == 2 else my_skin_addon.getLocalizedString(myLanguageStringId)# Python 2/3
        else:
            myLanguageString = xbmc.getLocalizedString(myLanguageStringId).encode('utf-8') if sys.version_info.major == 2 else xbmc.getLocalizedString(myLanguageStringId)# Python 2/3
        
        if myLanguageString:
            
            myLanguageStringSplit = myLanguageString.split('[CR][CR]')
            
            if myLanguageStringSplit and len(myLanguageStringSplit) == 2:
                
                if myLanguageStringId != 31412:
                    myLanguageString = myLanguageStringSplit[1]
                else:
                    myLanguageString = myLanguageStringSplit[0]
                
                if xbmcgui.Window(10000).getProperty('CinemaHelper.Language.Modified.'+str(myLanguageStringId)) != myLanguageString:
                    xbmcgui.Window(10000).setProperty('CinemaHelper.Language.Modified.'+str(myLanguageStringId), str(myLanguageString))
            
            else:
                clearString = True
        else:
            clearString = True
    
    
    if clearString:
        if xbmcgui.Window(10000).getProperty('CinemaHelper.Language.Modified.'+str(myLanguageStringId)):
            xbmcgui.Window(10000).clearProperty('CinemaHelper.Language.Modified.'+str(myLanguageStringId)+'')

def modifySettingsLanguageStringsStartNow():
    modifySettingsLanguageString(31430)
    modifySettingsLanguageString(31431)
    modifySettingsLanguageString(31002)
    modifySettingsLanguageString(31432)
    modifySettingsLanguageString(31433)
    modifySettingsLanguageString(31434)
    modifySettingsLanguageString(31436)
    modifySettingsLanguageString(31435)
    
    modifySettingsLanguageString(31412)






def LocalizeStringsPropertiesCheck(myLanguageStringId):
    
    clearString = False
    
    if myLanguageStringId:
        
        myLanguageString = xbmc.getLocalizedString(myLanguageStringId).encode('utf-8') if sys.version_info.major == 2 else xbmc.getLocalizedString(myLanguageStringId)# Python 2/3
        
        if myLanguageString:
            
            myLanguageStringLastChar = myLanguageString[-1]
            
            # strip potential space at the end of the string
            if myLanguageStringLastChar == ' ':
                myLanguageString = myLanguageString[:-1]
            
            myLanguageStringCharCount = len(myLanguageString)
            
            if myLanguageStringCharCount:
                
                # Close 15067 # <= 5
                # Play 208 # <= 5
                # Browse 1024 # <= 6
                # Watched 16102 # <= 5/2
                # Set 36910 # <=  5
                
                short = ""
                supershort = ""
                
                if "English" in str(xbmc.getInfoLabel('System.Language')):
                    
                    if myLanguageStringId == 15067 or myLanguageStringId == 208 or myLanguageStringId == 16102 or myLanguageStringId == 36910:
                        if myLanguageStringCharCount <= 5:
                            short = "True"
                    if myLanguageStringId == 1024:
                        if myLanguageStringCharCount <= 6:
                            short = "True"
                    if myLanguageStringId == 16102:
                        if myLanguageStringCharCount <= 2:
                            supershort = "True"
                
                
                if xbmcgui.Window(10000).getProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)) != myLanguageString:
                    xbmcgui.Window(10000).setProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId), str(myLanguageString))
                    xbmcgui.Window(10000).setProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)+'.charCount', str(myLanguageStringCharCount))
                    xbmcgui.Window(10000).setProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)+'.short', str(short))
                    xbmcgui.Window(10000).setProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)+'.supershort', str(supershort))
            
            else:
                clearString = True
        else:
            clearString = True
    
    
    if clearString:
        if xbmcgui.Window(10000).getProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)):
            xbmcgui.Window(10000).clearProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)+'')
            xbmcgui.Window(10000).clearProperty('CinemaHelper.Language.Properties.'+str(myLanguageStringId)+'.charCount')

def LocalizeStringsPropertiesStartNow():
    
    # Close
    LocalizeStringsPropertiesCheck(15067)# detect length: short=5chars
    
    # Play
    LocalizeStringsPropertiesCheck(208)# detect length: short=5chars
    #Browse
    LocalizeStringsPropertiesCheck(1024)# detect length: short=6chars
    
    # Watched
    LocalizeStringsPropertiesCheck(16102)# detect length: short=5chars supershort=2chars
    
    # Cast
    LocalizeStringsPropertiesCheck(206)
    # Plot
    LocalizeStringsPropertiesCheck(207)
    
    # Trailer
    LocalizeStringsPropertiesCheck(20410)
    
    # Director
    LocalizeStringsPropertiesCheck(20339)
    
    # Set
    LocalizeStringsPropertiesCheck(36910)# detect length: short=5chars
    
    # Versions
    LocalizeStringsPropertiesCheck(40000)
    # Extras
    LocalizeStringsPropertiesCheck(40211)












playerMonitor = MyPlayer()

monitor = xbmc.Monitor()

xbmcgui.Window(10000).setProperty('PlayBackJustStarted', '')
xbmcgui.Window(10000).setProperty('PlayBackJustEnded', '')




TimerInterval_2_Enabled = True
TimerInterval_3_Enabled = True

TimerInterval_2_ResetSec = float(0.995)
TimerInterval_3_ResetSec = float(4.00)

TimerInterval_2 = time.time()
TimerInterval_3 = time.time()



nearEndPreReached_Minutes = 30
nearEndReached_Minutes    = 10



lastContainerPath = ''
lastWindowAndContainerPath = ''
nearEndReachedTimeOutDurationCount = 0

TimerInterval_2_FirstRunDone = -1

showParentDirItems = False



ResetPlayerProgressCH = False






if sys.version_info.major == 2:# Python 2
    checkAbortRequested = xbmc.abortRequested
else:# Python 3
    checkAbortRequested = monitor.abortRequested()

while not checkAbortRequested:
    if monitor.waitForAbort(0.2):
        break
    
    timeNow = time.time()
    
    
    # INTERVAL DEFAULT
    
    if TimerInterval_2_FirstRunDone == 2:
        
        
        if playerMonitor.skinIsACZG:
            
            
            
            # --------------------------------------------------------------------------------
            # Language Change Checker
            # --------------------------------------------------------------------------------
            
            if xbmc.getCondVisibility('Window.IsActive(InterfaceSettings)') or xbmc.getCondVisibility('Window.IsActive(Settings)'):
                NewKodiLanguage = str(xbmc.getInfoLabel('System.Language'))
                if playerMonitor.KodiLanguage and NewKodiLanguage and playerMonitor.KodiLanguage != NewKodiLanguage:
                    
                    playerMonitor.KodiLanguage = NewKodiLanguage
                    
                    xbmc.sleep(1000)#wait after potential language change so the language strings can get populated and don't come back empty
                    
                    modifySettingsLanguageStringsStartNow()
            
            
            
            # --------------------------------------------------------------------------------
            # AutoComplete Helper
            # --------------------------------------------------------------------------------
            
            # Control(311) = (DialogKeyboard) Header
            # Control(312) = (DialogKeyboard) Input field
            # Control(313) = (DialogKeyboard) Input field (foreign languages without AutoComplete)
            
            # LOCALIZE
            
            # 16017 'Enter search string'
            # 24121 'Enter search string'
            # 137   'Search'
            
            if xbmc.getCondVisibility('Window.IsActive(VirtualKeyboard)'):
                
                if xbmc.getCondVisibility('!System.HasHiddenInput') and xbmc.getCondVisibility('!Control.IsVisible(313)') and xbmc.getCondVisibility('Control.IsVisible(311)') and xbmc.getCondVisibility('!String.IsEmpty(Control.GetLabel(311))') and ( xbmc.getCondVisibility('String.IsEqual(Control.GetLabel(311),$LOCALIZE[16017])') or xbmc.getCondVisibility('String.IsEqual(Control.GetLabel(311),$LOCALIZE[24121])') or xbmc.getCondVisibility('String.IsEqual(Control.GetLabel(311),$LOCALIZE[137])') or xbmc.getCondVisibility('String.Contains(Control.GetLabel(311),$LOCALIZE[137])') or (xbmc.getCondVisibility('Window.IsActive(MediaFilter)') and xbmc.getCondVisibility('String.IsEqual(Control.GetLabel(311),$LOCALIZE[556])')) ) and xbmc.getCondVisibility('!String.IsEmpty(Control.GetLabel(312).index(1))'):
                    AutoCompleteInputString = xbmc.getInfoLabel('Control.GetLabel(312).index(1)')
                    xbmcgui.Window(10000).setProperty('CinemaHelper.AutoCompleteInputString', str(AutoCompleteInputString))
            elif xbmcgui.Window(10000).getProperty('CinemaHelper.AutoCompleteInputString'):
                xbmcgui.Window(10000).clearProperty('CinemaHelper.AutoCompleteInputString')
            
            
            
            
            
            
            # --------------------------------------------------------------------------------
            # CH.Player.Progress and current streams (active player)
            # --------------------------------------------------------------------------------
            
            if xbmc.getCondVisibility('Player.HasMedia') and (xbmc.getCondVisibility('Player.HasVideo') or xbmc.getCondVisibility('Player.HasAudio')):
                
                IsScrolling = xbmc.getCondVisibility('Container.Scrolling') or xbmc.getCondVisibility('Container.OnPrevious') or xbmc.getCondVisibility('Container.OnNext') or xbmc.getCondVisibility('Container.OnScrollPrevious') or xbmc.getCondVisibility('Container.OnScrollNext')
                
                # Only update when not scrolling
                # Do not reset IF scrolling, just wait for next cycle and when not scrolling
                if not IsScrolling:
                    
                    jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}')
                    jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                    jsonQuery = simplejson.loads(jsonQuery)
                    
                    tmpHasKeyCheck = jsonQuery and 'result' in jsonQuery and len(jsonQuery['result']) > 0 and 'playerid' in jsonQuery['result'][0]
                    
                    activePlayerId = ''
                    if tmpHasKeyCheck:
                        TmpValue = int(jsonQuery['result'][0]['playerid'])
                        if TmpValue == 0 or TmpValue == 1:
                            activePlayerId = str(TmpValue)
                    
                    
                    if activePlayerId != '':
                        
                        jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Player.GetProperties", "params": {"properties":["percentage","currentaudiostream","currentvideostream","currentsubtitle"],"playerid":'+str(activePlayerId)+'}, "id": 1}')
                        jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                        jsonQuery = simplejson.loads(jsonQuery)
                        
                        tmpHasKeyCheck = jsonQuery and 'result' in jsonQuery and 'percentage' in jsonQuery['result']
                        
                        if tmpHasKeyCheck:
                            
                            activePlayerPercentage = round(jsonQuery['result']['percentage'],1)+0.0#normalize negative zero
                            if activePlayerPercentage < 0.0:
                                activePlayerPercentage = 0.0
                            elif activePlayerPercentage > 100.0:
                                activePlayerPercentage = 100.0
                            xbmcgui.Window(10000).setProperty('CH.Player.Progress', str(activePlayerPercentage))
                            
                            try:
                                xbmcgui.Window(10000).setProperty('CH.Player.Audio.ID', str(jsonQuery['result']['currentaudiostream']['index']))
                            except:
                                if xbmcgui.Window(10000).getProperty('CH.Player.Audio.ID') != '':
                                    xbmcgui.Window(10000).clearProperty('CH.Player.Audio.ID')
                            try:
                                xbmcgui.Window(10000).setProperty('CH.Player.Video.ID', str(jsonQuery['result']['currentvideostream']['index']))
                            except:
                                if xbmcgui.Window(10000).getProperty('CH.Player.Video.ID') != '':
                                    xbmcgui.Window(10000).clearProperty('CH.Player.Video.ID')
                            try:
                                xbmcgui.Window(10000).setProperty('CH.Player.Subtitle.ID', str(jsonQuery['result']['currentsubtitle']['index']))
                            except:
                                if xbmcgui.Window(10000).getProperty('CH.Player.Subtitle.ID') != '':
                                    xbmcgui.Window(10000).clearProperty('CH.Player.Subtitle.ID')
                            
                        else:
                            ResetPlayerProgressCH = True
                    else:
                        ResetPlayerProgressCH = True
            else:
                    ResetPlayerProgressCH = True
            
            
            
            if ResetPlayerProgressCH:
                ResetPlayerProgressCH = False
                
                if xbmcgui.Window(10000).getProperty('CH.Player.Progress') != '':
                    xbmcgui.Window(10000).clearProperty('CH.Player.Progress')
                
                if xbmcgui.Window(10000).getProperty('CH.Player.Audio.ID') != '':
                    xbmcgui.Window(10000).clearProperty('CH.Player.Audio.ID')
                if xbmcgui.Window(10000).getProperty('CH.Player.Video.ID') != '':
                    xbmcgui.Window(10000).clearProperty('CH.Player.Video.ID')
                if xbmcgui.Window(10000).getProperty('CH.Player.Subtitle.ID') != '':
                    xbmcgui.Window(10000).clearProperty('CH.Player.Subtitle.ID')
            
            
            
            
            
            # --------------------------------------------------------------------------------
            # TvShowTotalSeasons
            # --------------------------------------------------------------------------------
            
            if xbmc.getCondVisibility('Container.Content(TvShows)'):
                
                TvShowDBID = xbmc.getInfoLabel('Control.GetLabel(12201)')
                
                if TvShowDBID and TvShowDBID != xbmcgui.Window(10000).getProperty('CinemaHelper.ListItem.TvShowDBID'):
                    
                    TvShowTitle = xbmc.getInfoLabel("Control.GetLabel(12202)").replace("'","\'").replace('"','\\"')#keep double quotes "" here (exception)
                    TvShowTotalSeasons = xbmc.getInfoLabel('Control.GetLabel(12203)')
                    xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowDBID', str(TvShowDBID))
                    xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTitle', str(TvShowTitle))
                    xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTotalSeasons', str(TvShowTotalSeasons))
            
            
            
            # --------------------------------------------------------------------------------
            # set_focus_now
            # --------------------------------------------------------------------------------
            
            set_focus_now = xbmcgui.Window(10000).getProperty('set_focus_now')
            set_focus_now_delay = xbmcgui.Window(10000).getProperty('set_focus_now_delay')
            
            if set_focus_now:
                set_focus_now_child = xbmcgui.Window(10000).getProperty('set_focus_now_child')
            
            if set_focus_now:
                
                xbmcgui.Window(10000).clearProperty('set_focus_now')
                xbmcgui.Window(10000).clearProperty('set_focus_now_child')
                xbmcgui.Window(10000).clearProperty('set_focus_now_delay')
                
                if set_focus_now_delay:
                    time.sleep(int(set_focus_now_delay)/1000)
                
                if not set_focus_now_child:
                    xbmc.executebuiltin('SetFocus('+set_focus_now+')')
                else:
                    xbmc.executebuiltin('SetFocus('+set_focus_now+','+set_focus_now_child+')')
            
            # --------------------------------------------------------------------------------
            # set_focus_now_2
            # --------------------------------------------------------------------------------
            
            set_focus_now_2 = xbmcgui.Window(10000).getProperty('set_focus_now_2')
            set_focus_now_2_delay = xbmcgui.Window(10000).getProperty('set_focus_now_2')
            
            if set_focus_now_2:
                set_focus_now_2_child = xbmcgui.Window(10000).getProperty('set_focus_now_2_child')
            
            if set_focus_now_2:
                
                xbmcgui.Window(10000).clearProperty('set_focus_now_2')
                xbmcgui.Window(10000).clearProperty('set_focus_now_2_child')
                xbmcgui.Window(10000).clearProperty('set_focus_now_2_delay')
                
                if set_focus_now_2_delay:
                    time.sleep(int(set_focus_now_2_delay)/1000)
                
                if not set_focus_now_2_child:
                    xbmc.executebuiltin('SetFocus('+set_focus_now_2+')')
                else:
                    xbmc.executebuiltin('SetFocus('+set_focus_now_2+','+set_focus_now_2_child+')')
        
        
        
        
        
        
        CurrentWindow = str(xbmcgui.getCurrentWindowId())
        lastContainerPathCompare = xbmc.getInfoLabel('Container.FolderPath')
        
        lastWindowAndContainerPathCompare = CurrentWindow + '_' + lastContainerPathCompare
        
        
        if lastWindowAndContainerPath != lastWindowAndContainerPathCompare:
            
            
            # always clear TvShowTotalSeasonsCalculated
            xbmcgui.Window(10000).clearProperty('CinemaHelper.ListItem.TvShowTotalSeasonsCalculated')
            VideoLibraryShowAllItems = xbmc.getCondVisibility('System.GetBool(videolibrary.showallitems)')
            
            
            playerMonitor.skinIsACZG = xbmc.getSkinDir() == 'skin.aczg'
            
            showParentDirItems = xbmc.getCondVisibility('System.GetBool(filelists.showparentdiritems)')
            
            lastContainerPathWasEmpty = True if lastContainerPath == '' else False
            
            lastContainerPath = lastContainerPathCompare
            lastWindowAndContainerPath = CurrentWindow + '_' + lastContainerPathCompare
            
            
            
            if playerMonitor.skinIsACZG:
                
                
                
                ForcePresetViewsDisable = xbmc.getCondVisibility('Skin.HasSetting(ForcePresetViewsDisable)')
                
                
                
                xbmc.sleep(10)#short wait 10-25ms to let Kodi populate properties like Container.PluginName which are otherwise wrongly empty leading to detection issues (Container.FolderPath maybe also affected)
                
                
                
                IsAddon = xbmc.getInfoLabel('Container.PluginName') or lastContainerPathCompare.startswith('plugin://')
                
                
                
                # --------------------------------------------------------------------------------
                # TvShowTotalSeasonsCalculated
                # --------------------------------------------------------------------------------
                
                if not IsAddon and xbmc.getCondVisibility('Container.Content(Seasons)'):
                    
                    SeasonsContainerNumItems = xbmc.getInfoLabel('Container.NumItems')
                    
                    # Internal notes:
                    # NumItems returns 0 when no seasons and showallitems on/off
                    # Only a '..' entry is then visible
                    # showallitems '* All seasons' counts as +1 if shown
                    # '..' does never count
                    
                    if SeasonsContainerNumItems != '' and int(SeasonsContainerNumItems) >= 0:
                        
                        SeasonsContainerNumItems = int(SeasonsContainerNumItems)
                        
                        if SeasonsContainerNumItems == 0:
                            xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTotalSeasonsCalculated', str(SeasonsContainerNumItems))
                        elif SeasonsContainerNumItems == 1:
                            xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTotalSeasonsCalculated', str(SeasonsContainerNumItems))
                        elif SeasonsContainerNumItems > 1 and not VideoLibraryShowAllItems:
                            xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTotalSeasonsCalculated', str(SeasonsContainerNumItems))
                        elif SeasonsContainerNumItems > 1 and VideoLibraryShowAllItems:
                            xbmcgui.Window(10000).setProperty('CinemaHelper.ListItem.TvShowTotalSeasonsCalculated', str(int(SeasonsContainerNumItems-1)))
                
                
                
                #################################
                # OOB Experience for View Modes #
                #################################
                
                if not ForcePresetViewsDisable and not IsAddon:
                    
                    #################################
                    # View Modes CONFIG             #
                    #################################
                    
                    # MOVIES
                    
                    ForcePresetViewsMoviesCategory_A = 500
                    ForcePresetViewsMoviesCategory_B = 508
                    ForcePresetViewsMoviesCategory_C = 508
                    ForcePresetViewsMoviesCategory_D = 500
                    
                    try:
                        ForcePresetViewsMoviesCategories = str(xbmc.getInfoLabel('Skin.String(ForcePresetViewsMoviesCategories)'))
                        if ForcePresetViewsMoviesCategories:
                            ForcePresetViewsMoviesCategoriesArr = ForcePresetViewsMoviesCategories.split(',',4)
                            
                            if int(ForcePresetViewsMoviesCategoriesArr[0]) > 0:
                                ForcePresetViewsMoviesCategory_A = int(ForcePresetViewsMoviesCategoriesArr[0])
                            if int(ForcePresetViewsMoviesCategoriesArr[1]) > 0:
                                ForcePresetViewsMoviesCategory_B = int(ForcePresetViewsMoviesCategoriesArr[1])
                            if int(ForcePresetViewsMoviesCategoriesArr[2]) > 0:
                                ForcePresetViewsMoviesCategory_C = int(ForcePresetViewsMoviesCategoriesArr[2])
                            if int(ForcePresetViewsMoviesCategoriesArr[3]) > 0:
                                ForcePresetViewsMoviesCategory_D = int(ForcePresetViewsMoviesCategoriesArr[3])
                            
                    except:
                        pass
                    
                    # TV SHOWS
                    
                    ForcePresetViewsTvShowsCategory_A = 508
                    ForcePresetViewsTvShowsCategory_B = 508
                    ForcePresetViewsTvShowsCategory_C = 509
                    ForcePresetViewsTvShowsCategory_D = 510
                    ForcePresetViewsTvShowsCategory_E = 52
                    
                    try:
                        ForcePresetViewsTvShowsCategories = str(xbmc.getInfoLabel('Skin.String(ForcePresetViewsTvShowsCategories)'))
                        if ForcePresetViewsTvShowsCategories:
                            ForcePresetViewsTvShowsCategoriesArr = ForcePresetViewsTvShowsCategories.split(',',5)
                            
                            if int(ForcePresetViewsTvShowsCategoriesArr[0]) > 0:
                                ForcePresetViewsTvShowsCategory_A = int(ForcePresetViewsTvShowsCategoriesArr[0])
                            if int(ForcePresetViewsTvShowsCategoriesArr[1]) > 0:
                                ForcePresetViewsTvShowsCategory_B = int(ForcePresetViewsTvShowsCategoriesArr[1])
                            if int(ForcePresetViewsTvShowsCategoriesArr[2]) > 0:
                                ForcePresetViewsTvShowsCategory_C = int(ForcePresetViewsTvShowsCategoriesArr[2])
                            if int(ForcePresetViewsTvShowsCategoriesArr[3]) > 0:
                                ForcePresetViewsTvShowsCategory_D = int(ForcePresetViewsTvShowsCategoriesArr[3])
                            if int(ForcePresetViewsTvShowsCategoriesArr[4]) > 0:
                                ForcePresetViewsTvShowsCategory_E = int(ForcePresetViewsTvShowsCategoriesArr[4])
                            
                    except:
                        pass
                    
                    # MUSIC / PICTURES
                    
                    ForcePresetViewsMusicPicturesCategory_A = 500
                    ForcePresetViewsMusicPicturesCategory_B = 588
                    ForcePresetViewsMusicPicturesCategory_C = 500
                    
                    try:
                        ForcePresetViewsMusicPicturesCategories = str(xbmc.getInfoLabel('Skin.String(ForcePresetViewsMusicPicturesCategories)'))
                        if ForcePresetViewsMusicPicturesCategories:
                            ForcePresetViewsMusicPicturesCategoriesArr = ForcePresetViewsMusicPicturesCategories.split(',',3)
                            
                            if int(ForcePresetViewsMusicPicturesCategoriesArr[0]) > 0:
                                ForcePresetViewsMusicPicturesCategory_A = int(ForcePresetViewsMusicPicturesCategoriesArr[0])
                            if int(ForcePresetViewsMusicPicturesCategoriesArr[1]) > 0:
                                ForcePresetViewsMusicPicturesCategory_B = int(ForcePresetViewsMusicPicturesCategoriesArr[1])
                            if int(ForcePresetViewsMusicPicturesCategoriesArr[2]) > 0:
                                ForcePresetViewsMusicPicturesCategory_C = int(ForcePresetViewsMusicPicturesCategoriesArr[2])
                            
                    except:
                        pass
                    
                     # GLOBAL / MISC
                    
                    ForcePresetViewsGlobalMiscCategory_A = 500
                    ForcePresetViewsGlobalMiscCategory_B = 500
                    ForcePresetViewsGlobalMiscCategory_C = 500
                    ForcePresetViewsGlobalMiscCategory_D = 500
                    ForcePresetViewsGlobalMiscCategory_E = 500
                    
                    try:
                        ForcePresetViewsGlobalMiscCategories = str(xbmc.getInfoLabel('Skin.String(ForcePresetViewsGlobalMiscCategories)'))
                        if ForcePresetViewsGlobalMiscCategories:
                            ForcePresetViewsGlobalMiscCategoriesArr = ForcePresetViewsGlobalMiscCategories.split(',',5)
                            
                            if int(ForcePresetViewsGlobalMiscCategoriesArr[0]) > 0:
                                ForcePresetViewsGlobalMiscCategory_A = int(ForcePresetViewsGlobalMiscCategoriesArr[0])
                            if int(ForcePresetViewsGlobalMiscCategoriesArr[1]) > 0:
                                ForcePresetViewsGlobalMiscCategory_B = int(ForcePresetViewsGlobalMiscCategoriesArr[1])
                            if int(ForcePresetViewsGlobalMiscCategoriesArr[2]) > 0:
                                ForcePresetViewsGlobalMiscCategory_C = int(ForcePresetViewsGlobalMiscCategoriesArr[2])
                            if int(ForcePresetViewsGlobalMiscCategoriesArr[3]) > 0:
                                ForcePresetViewsGlobalMiscCategory_D = int(ForcePresetViewsGlobalMiscCategoriesArr[3])
                            if int(ForcePresetViewsGlobalMiscCategoriesArr[4]) > 0:
                                ForcePresetViewsGlobalMiscCategory_E = int(ForcePresetViewsGlobalMiscCategoriesArr[4])
                            
                    except:
                        pass
                    
                    
                    
            
                    
                    
                    
                    
                    
                    
                    
                    # GLOBAL
                    
                    ForcePresetViewsGlobalCategory_A = ForcePresetViewsGlobalMiscCategory_A#500#global root + fallback
                    ForcePresetViewsGlobalCategory_B = ForcePresetViewsGlobalMiscCategory_B#500#actors + artists
                    
                    # VIDEOS
                    
                    ForcePresetViewsVideosCategory_A = ForcePresetViewsGlobalCategory_A#videos root + fallback
                    ForcePresetViewsVideosCategory_B = ForcePresetViewsGlobalMiscCategory_C#52#files
                    
                    # ADDONS
                    
                    ForcePresetViewsAddonsCategory_A = ForcePresetViewsGlobalCategory_A#addons root + fallback
                    ForcePresetViewsAddonsCategory_B = ForcePresetViewsGlobalMiscCategory_D#500#addons
                    
                    # MUSIC
                    
                    ForcePresetViewsMusicCategory_A = ForcePresetViewsGlobalCategory_A#music root + fallback
                    ForcePresetViewsMusicCategory_B = ForcePresetViewsMusicPicturesCategory_A#500#albums + music videos
                    ForcePresetViewsMusicCategory_C = ForcePresetViewsMusicPicturesCategory_B#588#songs
                    
                    # PICTURES
                    
                    ForcePresetViewsPicturesCategory_A = ForcePresetViewsGlobalCategory_A#pictures root + fallback
                    ForcePresetViewsPicturesCategory_B = ForcePresetViewsMusicPicturesCategory_C#500#pictures
                    
                    # GAMES
                    
                    ForcePresetViewsGamesCategory_A = ForcePresetViewsGlobalMiscCategory_E#games
                    
                    
                    
                    
                    
                    
                    #################################
                    # View Modes SET switchToView   #
                    #################################
                    
                    switchToView = False
                    
                    
                    
                    IsMusicWindow = xbmc.getCondVisibility('Window.IsActive(Music)') and xbmc.getCondVisibility('Window.Is(Music)')
                    IsPicturesWindow = xbmc.getCondVisibility('Window.IsActive(Pictures)') and xbmc.getCondVisibility('Window.Is(Pictures)')
                    
                    IsAddonBrowserWindow = xbmc.getCondVisibility('Window.IsActive(AddonBrowser)') and xbmc.getCondVisibility('Window.Is(AddonBrowser)')
                    
                    IsContainerContentAddons = xbmc.getCondVisibility('Container.Content(Addons)') or xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,androidapp://sources/apps/)')
                    
                    IsWindowGames = xbmc.getCondVisibility('Window.IsActive(Games)')
                    IsFolderPathEmpty = xbmc.getCondVisibility('String.IsEmpty(Container.FolderPath)')
                    
                    
                    # MUSIC
                    
                    if (IsMusicWindow and not xbmc.getCondVisibility('Container.Content(Genres)') and not xbmc.getCondVisibility('Container.Content(Songs)') and not xbmc.getCondVisibility('Container.Content(Years)') and not xbmc.getCondVisibility('Container.Content(Addons)') and not xbmc.getCondVisibility('Container.Content(Files)') and not xbmc.getCondVisibility('Container.Content(Directors)') and not xbmc.getCondVisibility('Container.Content(Studios)') and not xbmc.getCondVisibility('Container.Content(Tags)')) and not (xbmc.getCondVisibility('Container.Content(MusicVideos)') or xbmc.getCondVisibility('Container.Content(Albums)')):
                        switchToView = ForcePresetViewsMusicCategory_A
                    
                    if xbmc.getCondVisibility('Container.Content(MusicVideos)') or xbmc.getCondVisibility('Container.Content(Albums)'):
                        switchToView = ForcePresetViewsMusicCategory_B
                    
                    if xbmc.getCondVisibility('Container.Content(Songs)'):
                        switchToView = ForcePresetViewsMusicCategory_C
                    
                    if xbmc.getCondVisibility('Container.Content(Artists)'):
                        switchToView = ForcePresetViewsGlobalCategory_B
                    
                    # PICTURES
                    
                    if IsPicturesWindow and not IsContainerContentAddons and not xbmc.getCondVisibility('Container.Content(Images)'):
                        switchToView = ForcePresetViewsPicturesCategory_A
                    
                    if xbmc.getCondVisibility('Container.Content(Images)'):
                        switchToView = ForcePresetViewsPicturesCategory_B
                    
                    # ADDONS
                    
                    if IsAddonBrowserWindow and not IsContainerContentAddons:
                        switchToView = ForcePresetViewsAddonsCategory_A
                    
                    if IsContainerContentAddons and not IsWindowGames:
                        switchToView = ForcePresetViewsAddonsCategory_B
                    
                    # GAMES
                    
                    if IsWindowGames:
                        if IsFolderPathEmpty:
                            switchToView = ForcePresetViewsGlobalCategory_A
                        else:
                            switchToView = ForcePresetViewsGamesCategory_A
                    
                    
                    
                    IsVideoLibraryView = xbmc.getCondVisibility('Window.IsActive(Videos)') and xbmc.getCondVisibility('Window.Is(Videos)')
                    
                    if IsVideoLibraryView:
                        
                        IsVideoDb = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://)')
                        IsFilesContent = xbmc.getCondVisibility('Container.Content(Files)') or xbmc.getCondVisibility('Container.Content(Mixed)')
                        
                        # actors
                        IsActorsContent = xbmc.getCondVisibility('Container.Content(Actors)')
                        
                        # music videos
                        IsMusicVideosContent = xbmc.getCondVisibility('Container.Content(MusicVideos)')
                        
                        # addons
                        IsAddonsContent = xbmc.getCondVisibility('Container.Content(Addons)')
                        
                        # movies
                        IsMovieContent = xbmc.getCondVisibility('Container.Content(Movies)')
                        IsSetsContent = xbmc.getCondVisibility('Container.Content(Sets)')
                        
                        #tv shows
                        IsTvShowsContent = xbmc.getCondVisibility('Container.Content(TvShows)')
                        IsSeasonsContent = xbmc.getCondVisibility('Container.Content(Seasons)')
                        IsEpisodesContent = xbmc.getCondVisibility('Container.Content(Episodes)')
                        
                        #genres
                        IsGenresContent = xbmc.getCondVisibility('Container.Content(Genres)')
                        
                        IsSpecialList = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/)') and xbmc.getCondVisibility('String.Contains(Container.FolderPath,- Special Lists)')
                        
                        #folder path movies
                        IsSetsMoviesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://movies/sets/)')
                        IsGenresMoviesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://movies/genres/)')
                        IsRecentlyAddedMoviesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://recentlyaddedmovies/)')
                        IsMyListMoviesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/Movies - Special Lists/_mylist_movies.xsp)')
                        #unused for now:
                        IsRecentlyWatchedMoviesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/Movies - Special Lists - Special Lists/movies_by_recently_played.xsp)')
                        
                        #folder path tv shows
                        IsGenresTvShowsFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://tvshows/genres/)')
                        IsMyListTvShowsFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/TV shows - Special Lists/_mylist_tvshows.xsp)')
                        IsRecentlyAddedEpisodesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,videodb://recentlyaddedepisodes/)')
                        IsRecentlyWatchedEpisodesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/TV shows - Special Lists/episodes_by_recently_played.xsp)')
                        IsMyListEpisodesFolderPath = xbmc.getCondVisibility('String.StartsWith(Container.FolderPath,special://skin/Special Lists/TV shows - Special Lists/_mylist_episodes.xsp)')
                        
                        #switchToView = False
                        
                        # 901 = 'Text'
                        #  52 = 'Modern'
                        # 500 = 'Wall 2X'
                        # 908 = 'Wall 3X'
                        # 909 = 'Wall 4X'
                        # 910 = 'Wall 5X'
                        # 508 = 'Fanart'
                        # 509 = 'Seasons'
                        # 510 = 'Episodes'
                        
                        
                        # standard video files without db entries
                        if IsFilesContent and not IsVideoDb:
                            switchToView = ForcePresetViewsVideosCategory_B
                        
                        
                        # global movies
                        if IsMovieContent and not IsSetsMoviesFolderPath and not IsGenresMoviesFolderPath and not IsRecentlyAddedMoviesFolderPath and not IsSpecialList and not IsMyListMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_A#CAT A   'Wall 2X'
                        if IsMovieContent and not IsSetsMoviesFolderPath and not IsGenresMoviesFolderPath and not IsRecentlyAddedMoviesFolderPath and IsSpecialList and not IsMyListMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_A#CAT A   'Wall 2X'
                        
                        # actors
                        if IsActorsContent:
                            switchToView = ForcePresetViewsGlobalCategory_B
                        
                        # movies: 'my list'
                        if IsMovieContent and IsMyListMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_C#CAT C   'Fanart'
                        
                        # movie genres: list movies of selected genre
                        if IsMovieContent and IsGenresMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_A#CAT A   'Wall 2X'
                        
                        # movie sets: list sets
                        if IsSetsContent:
                            switchToView = ForcePresetViewsMoviesCategory_D#CAT D   'Wall 2X'
                        
                        # movie sets: list movies of set
                        if IsMovieContent and IsSetsMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_B#CAT B   'Fanart'
                        
                        # recently added movies
                        if IsRecentlyAddedMoviesFolderPath:
                            switchToView = ForcePresetViewsMoviesCategory_C#CAT C   'Fanart'
                        
                    
                        # global tv shows
                        if (IsTvShowsContent and not IsGenresTvShowsFolderPath and not IsSpecialList and not IsMyListTvShowsFolderPath) or (IsTvShowsContent and not IsMyListTvShowsFolderPath and IsSpecialList):
                            switchToView = ForcePresetViewsTvShowsCategory_A#CAT J   'Fanart'
                        
                        # global tv show seasons
                        if IsSeasonsContent and not IsGenresTvShowsFolderPath:
                            switchToView = ForcePresetViewsTvShowsCategory_C# 'Seasons' view is best ######
                        
                        # tv shows genres: list shows in selected genre
                        if IsTvShowsContent and IsGenresTvShowsFolderPath:
                            switchToView = ForcePresetViewsTvShowsCategory_A#CAT J     'Fanart'
                        
                        # tv show seasons: list seasons in selected genre
                        if IsSeasonsContent and IsGenresTvShowsFolderPath:
                            switchToView = ForcePresetViewsTvShowsCategory_C# 'Seasons' view is best ######
                        
                        # tv shows: list shows in 'my list'
                        if IsTvShowsContent and IsMyListTvShowsFolderPath:
                            switchToView = ForcePresetViewsTvShowsCategory_B#CAT K
                        
                        
                        # episodes: recently added
                        if IsEpisodesContent and IsVideoDb and IsRecentlyAddedEpisodesFolderPath:
                            switchToView = ForcePresetViewsTvShowsCategory_E
                        
                        # episodes: recently watched
                        if IsEpisodesContent and not IsVideoDb and (IsRecentlyWatchedEpisodesFolderPath or IsMyListEpisodesFolderPath):
                            switchToView = ForcePresetViewsTvShowsCategory_E
                        
                        # episodes
                        if IsEpisodesContent and not IsRecentlyAddedEpisodesFolderPath and not IsRecentlyWatchedEpisodesFolderPath and not IsMyListEpisodesFolderPath:
                            
                            switchToView = ForcePresetViewsTvShowsCategory_D
                            
                            isSortMethodEpisode = xbmc.getCondVisibility('String.IsEqual(Container.SortMethod,$LOCALIZE[20359])')#20359='Episode'
                            
                            ForceFirstEpisodeItemFocus = not xbmc.getCondVisibility('Skin.HasSetting(ForceFirstEpisodeItemFocusDisable)') and not lastContainerPathWasEmpty
                            
                            finalFirstPageActions = 0
                            
                            if ForceFirstEpisodeItemFocus:
                                xbmc.executebuiltin('Action(firstpage)')
                            
                            if not isSortMethodEpisode and not lastContainerPathWasEmpty:
                                finalFirstPageActions = 1
                                xbmc.executebuiltin('Container.SetSortMethod(23)')#23=Episode (conflicting Forum+Wiki Info about this. 23 works for Krypton)
                                if ForceFirstEpisodeItemFocus:
                                    xbmc.executebuiltin('Action(firstpage)')
                                xbmc.sleep(25)#short wait before SortDirection check
                            else:
                                if ForceFirstEpisodeItemFocus:
                                    xbmc.executebuiltin('Action(firstpage)')
                            
                            if xbmc.getCondVisibility('Container.SortDirection(descending)') and not lastContainerPathWasEmpty:
                                finalFirstPageActions = 1
                                xbmc.executebuiltin('Container.SetSortDirection()')
                                if ForceFirstEpisodeItemFocus:
                                    xbmc.executebuiltin('Action(firstpage)')
                            else:
                                if ForceFirstEpisodeItemFocus:
                                    xbmc.executebuiltin('Action(firstpage)')
                            
                            if finalFirstPageActions and ForceFirstEpisodeItemFocus:
                                xbmc.sleep(25)#short wait before final firstpage actions (making sure first item is always selected when viewing episodes)
                                for x in range(finalFirstPageActions):
                                    xbmc.executebuiltin('Action(firstpage)')
                        
                        
                        if not switchToView and not xbmc.getCondVisibility('Container.Content(Genres)') and not xbmc.getCondVisibility('Container.Content(Years)') and not xbmc.getCondVisibility('Container.Content(Directors)') and not xbmc.getCondVisibility('Container.Content(Studios)') and not xbmc.getCondVisibility('Container.Content(Countries)') and not xbmc.getCondVisibility('Container.Content(Tags)') and not IsAddonsContent and not IsAddon:
                            switchToView = ForcePresetViewsVideosCategory_A
                    
                    
                    
                    if switchToView:
                        viewLabelCompare = ''
                        if switchToView == 500:
                            viewLabelCompare = 'Wall 2X'
                        if switchToView == 908:
                            viewLabelCompare = 'Wall 3X'
                        if switchToView == 909:
                            viewLabelCompare = 'Wall 4X'
                        if switchToView == 910:
                            viewLabelCompare = 'Wall 5X'
                        if switchToView == 508:
                            if playerMonitor.isKodi22plus:
                                viewLabelCompare = my_skin_addon.getLocalizedString(31029)#'Fanart'
                            else:
                                viewLabelCompare = xbmc.getLocalizedString(31029)#'Fanart'
                        if switchToView == 901:
                            viewLabelCompare = 'Text'
                        if switchToView == 509:
                            viewLabelCompare = 'Seasons'
                        if switchToView == 510:
                            viewLabelCompare = 'Episodes'
                        if switchToView == 52:
                            viewLabelCompare = 'Modern'
                        
                        #ViewsVideoLibrary
                        if switchToView == 50:
                            viewLabelCompare = xbmc.getLocalizedString(535)#'List'
                        if switchToView == 51:
                            viewLabelCompare = 'List Wide'
                        if switchToView == 503:
                            viewLabelCompare = xbmc.getLocalizedString(544)+' 2'#'Media info 2'
                        if switchToView == 504:
                            viewLabelCompare = xbmc.getLocalizedString(544)#'Media info'
                        if switchToView == 515:
                            viewLabelCompare = xbmc.getLocalizedString(544)+' 3'#'Media info 3'
                        
                        #ViewsFileMode
                        if switchToView == 505:
                            viewLabelCompare = xbmc.getLocalizedString(539)#'Wide'
                        
                        #ViewsMusicLibrary
                        if switchToView == 588:
                            viewLabelCompare = 'Songs'
                        
                        currentView = xbmc.getInfoLabel('Container.ViewMode')
                        
                        
                        
                        if currentView != viewLabelCompare:
                            xbmc.executebuiltin('Container.SetViewMode('+str(switchToView)+')')
                            if (switchToView == 508 or switchToView == 509) and showParentDirItems:
                                # if we just switched to fanart view (508)
                                # wait a bit before proceeding to ParentFolder Item skip
                                xbmc.sleep(25)
                        
                        
                        if showParentDirItems:
                            # Move-Skip ParentFolderItem for Fanart View (on content load)
                            FanartViewHasFocus = xbmc.getCondVisibility('Control.HasFocus(508)')
                            if FanartViewHasFocus:
                                ListItemIsParentFolder = xbmc.getCondVisibility('Container(508).ListItem.IsParentFolder')
                                if ListItemIsParentFolder:
                                    xbmc.executebuiltin('Control.Move(508,1)')
                            SeasonsViewHasFocus = xbmc.getCondVisibility('Control.HasFocus(509)')
                            if SeasonsViewHasFocus:
                                ListItemIsParentFolder = xbmc.getCondVisibility('Container(509).ListItem.IsParentFolder')
                                if ListItemIsParentFolder:
                                    xbmc.executebuiltin('Control.Move(509,1)')
    
    
    
    
    
    
    # INTERVAL 2
    
    if TimerInterval_2_Enabled and (timeNow - TimerInterval_2) > TimerInterval_2_ResetSec:
        
        
        if TimerInterval_2_FirstRunDone == 1:
            TimerInterval_2_FirstRunDone = 2
        elif TimerInterval_2_FirstRunDone < 1:
            TimerInterval_2_FirstRunDone = 1
        
        
        TimerInterval_2 = time.time()
        
        IsScrolling = xbmc.getCondVisibility('Container.Scrolling') or xbmc.getCondVisibility('Container.OnPrevious') or xbmc.getCondVisibility('Container.OnNext') or xbmc.getCondVisibility('Container.OnScrollPrevious') or xbmc.getCondVisibility('Container.OnScrollNext')
        
        if not IsScrolling:
            
            
            
            
            
            tmpKodiIdleTime = xbmc.getGlobalIdleTime()
                
            # only execute if Kodi is not idle
            if tmpKodiIdleTime < 7:
                
                getSkinDir = xbmc.getSkinDir()
                SystemLanguage = xbmc.getInfoLabel('System.Language')
                
                if getSkinDir and SystemLanguage:
                    
                    
                    RunStandardLanguageCheck = False
                    RunLocalizeStringsPropertiesStartNow = False
                    
                    
                    if getSkinDir == 'skin.aczg':
                        
                        
                        
                        if xbmcgui.Window(10000).getProperty('CinemaHelper.LocalizeStringsPropertiesStartNow'):
                            LocalizeStringsPropertiesStartNow()
                            
                            xbmcgui.Window(10000).clearProperty('CinemaHelper.LocalizeStringsPropertiesStartNow')
                        
                        
                        
                        
                        ExperimentalOptions = xbmc.getCondVisibility('Skin.HasSetting(ExperimentalOptions)')
                        DevCodesFonts = xbmc.getInfoLabel('Skin.String(DevCodes)') and 'FONTS' in xbmc.getInfoLabel('Skin.String(DevCodes)')
                        FontAddon = xbmc.getCondVisibility('System.HasAddon(resource.font.aczg)')
                        
                        if ExperimentalOptions and DevCodesFonts and FontAddon:
                            
                            OpenDialogsDetected = xbmc.getCondVisibility('Window.IsVisible(YesNodialog)') or xbmc.getCondVisibility('Window.IsVisible(Notification)') or xbmc.getCondVisibility('Window.IsVisible(StartUp)') or xbmc.getCondVisibility('Window.IsVisible(LoginScreen)') or xbmc.getCondVisibility('Window.IsVisible(1180)') or xbmc.getCondVisibility('Window.IsVisible(1181)') or xbmc.getCondVisibility('Window.IsVisible(1182)') or xbmc.getCondVisibility('Window.IsVisible(1112)') or xbmc.getCondVisibility('Window.IsVisible(1111)')
                            
                            if not OpenDialogsDetected:
                                
                                CinemaHelperSystemLanguage = xbmcgui.Window(10000).getProperty('CinemaHelper.System.Language')
                                CinemaHelperGetSkinDir = xbmcgui.Window(10000).getProperty('CinemaHelper.getSkinDir')
                                
                                if CinemaHelperSystemLanguage and CinemaHelperGetSkinDir and ((CinemaHelperSystemLanguage != SystemLanguage) or (CinemaHelperGetSkinDir != getSkinDir)):
                                    
                                    KodiFont = xbmc.getInfoLabel('Skin.Font')
                                    
                                    if KodiFont:
                                        
                                        DefaultFontName               = 'SKINDEFAULT'
                                        DefaultFontNameTrueString     = 'Default'
                                        
                                        ArabicHebrewFontName          = 'Arabic · Hebrew  (Experimental)'
                                        
                                        ChineseSimpleFontName         = 'Chinese (Simple)  (Experimental)'
                                        ChineseTraditionalFontName    = 'Chinese (Traditional)  (Experimental)'
                                        JapaneseFontName              = 'Japanese  (Experimental)'
                                        KoreanFontName                = 'Korean  (Experimental)'
                                        
                                        HindiFontName                 = 'Hindi (Devanagiri)  (Experimental)'
                                        ThaiFontName                  = 'Thai  (Experimental)'
                                        
                                        SystemLanguageIsArabicHebrew  = SystemLanguage == 'Arabic' or SystemLanguage == 'Hebrew'
                                        
                                        SystemLanguageIsChineseSimple         = SystemLanguage == 'Chinese (Simple)'
                                        SystemLanguageIsChineseTraditional    = SystemLanguage == 'Chinese (Traditional)'
                                        SystemLanguageIsJapanese              = SystemLanguage == 'Japanese'
                                        SystemLanguageIsKorean                = SystemLanguage == 'Korean'
                                        
                                        
                                        SystemLanguageIsHindi                 = SystemLanguage == 'Hindi (Devanagiri)'
                                        SystemLanguageIsThai                  = SystemLanguage == 'Thai'
                                        
                                        if SystemLanguageIsArabicHebrew and KodiFont != ArabicHebrewFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+ArabicHebrewFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsChineseSimple and KodiFont != ChineseSimpleFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+ChineseSimpleFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsChineseTraditional and KodiFont != ChineseTraditionalFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+ChineseTraditionalFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsJapanese and KodiFont != JapaneseFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+JapaneseFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsKorean and KodiFont != KoreanFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+KoreanFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsHindi and KodiFont != HindiFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+HindiFontName+'"}, "id": 1}')
                                            
                                        elif SystemLanguageIsThai and KodiFont != ThaiFontName:
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+ThaiFontName+'"}, "id": 1}')
                                            
                                        elif not (SystemLanguageIsArabicHebrew or SystemLanguageIsChineseSimple or SystemLanguageIsChineseTraditional or SystemLanguageIsJapanese or SystemLanguageIsKorean or SystemLanguageIsHindi or SystemLanguageIsThai) and (KodiFont == ArabicHebrewFontName or KodiFont == ChineseSimpleFontName or KodiFont == ChineseTraditionalFontName or KodiFont == JapaneseFontName or KodiFont == KoreanFontName or KodiFont == HindiFontName or KodiFont == ThaiFontName):
                                            
                                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.font","value":"'+DefaultFontName+'"}, "id": 1}')
                                        
                                        
                                        xbmcgui.Window(10000).setProperty('CinemaHelper.System.Language', str(SystemLanguage))
                                        xbmcgui.Window(10000).setProperty('CinemaHelper.getSkinDir', str(getSkinDir))
                                        
                                        RunLocalizeStringsPropertiesStartNow = True
                        else:
                            
                            RunStandardLanguageCheck = True
                            
                    else:
                        
                        RunStandardLanguageCheck = True
                    
                    
                    
                    
                    
                    if RunStandardLanguageCheck:
                        
                        CinemaHelperSystemLanguage = xbmcgui.Window(10000).getProperty('CinemaHelper.System.Language')
                        CinemaHelperGetSkinDir = xbmcgui.Window(10000).getProperty('CinemaHelper.getSkinDir')
                        
                        if CinemaHelperSystemLanguage and CinemaHelperGetSkinDir and ((CinemaHelperSystemLanguage != SystemLanguage) or (CinemaHelperGetSkinDir != getSkinDir)):
                            xbmcgui.Window(10000).setProperty('CinemaHelper.System.Language', str(SystemLanguage))
                            xbmcgui.Window(10000).setProperty('CinemaHelper.getSkinDir', str(getSkinDir))
                            
                            RunLocalizeStringsPropertiesStartNow = True
                    
                    
                    if RunLocalizeStringsPropertiesStartNow:
                        xbmcgui.Window(10000).setProperty('CinemaHelper.LocalizeStringsPropertiesStartNow', 'True')
            
            
            
            
            
            # --------------------------------------------------------------------------------
            # Get System.ProfileName Initials
            # --------------------------------------------------------------------------------
            SystemProfileName = xbmc.getInfoLabel('System.ProfileName')
            ProfileNameInitial = SystemProfileName[:1] if SystemProfileName else ''
            if ProfileNameInitial != xbmcgui.Window(10000).getProperty('CinemaHelper.ProfileNameInitial'):
                xbmcgui.Window(10000).setProperty('CinemaHelper.ProfileNameInitial', ProfileNameInitial)
            
            # --------------------------------------------------------------------------------
            # Move-Skip ParentFolderItem for Fanart View (on Idle)
            # --------------------------------------------------------------------------------
            if playerMonitor.skinIsACZG and showParentDirItems:
                # Move-Skip ParentFolderItem for Fanart View (on Idle)
                FanartViewHasFocus = xbmc.getCondVisibility('Control.HasFocus(508)')
                if FanartViewHasFocus:
                    FanartViewListItemIsParentFolder = xbmc.getCondVisibility('Container(508).ListItem.IsParentFolder')
                    tmpKodiIdleTime = xbmc.getGlobalIdleTime()
                    if FanartViewListItemIsParentFolder and tmpKodiIdleTime > 1:
                        xbmc.executebuiltin('Control.Move(508,1)')
            
            
            # --------------------------------------------------------------------------------
            # Clear PlayBackJustStarted / PlayBackJustEnded after X seconds
            # --------------------------------------------------------------------------------
            PlayBackJustStarted = xbmcgui.Window(10000).getProperty('PlayBackJustStarted')
            
            if PlayBackJustStarted == 'True':
                tmpTimerDifference = timeNow - playerMonitor.startTimer
                if tmpTimerDifference > float(0.80):
                    xbmcgui.Window(10000).setProperty('PlayBackJustStarted', '')
            
            PlayBackJustEnded = xbmcgui.Window(10000).getProperty('PlayBackJustEnded')
            
            if PlayBackJustEnded == 'True':
                tmpTimerDifference = timeNow - playerMonitor.endTimer
                if tmpTimerDifference > float(0.80):
                    xbmcgui.Window(10000).setProperty('PlayBackJustEnded', '')
            
            
            
            PlayerHasMedia = xbmc.getCondVisibility('Player.HasMedia')
            PlayerHasVideo = xbmc.getCondVisibility('Player.HasVideo')
            PlayerHasAudio = xbmc.getCondVisibility('Player.HasAudio')
            
            playingVideo = PlayerHasMedia and PlayerHasVideo
            playingAudio = PlayerHasMedia and PlayerHasAudio and not PlayerHasVideo
            
            
            # --------------------------------------------------------------------------------
            # Auto Close VideoOSD/MusicOSD when Idle
            # --------------------------------------------------------------------------------
            if (playingVideo or playingAudio):
                tmpTimerDifference = timeNow - playerMonitor.idleCheckIntervalTimer
                
                if tmpTimerDifference > float(2.50):
                    
                    if playerMonitor.skinIsACZG:
                        
                        tmpKodiIdleTime = xbmc.getGlobalIdleTime()
                        
                        # Only process when very idle and OSD is open
                        if tmpKodiIdleTime > 6 and (xbmc.getCondVisibility('Window.IsActive(VideoOSD)') or xbmc.getCondVisibility('Window.IsActive(MusicOSD)')):
                            
                            # Only auto close if subtitle search and similar windows/dialogs are not open
                            
                            
                            # Check for open windows/dialogs on all Kodi versions
                            checkForOpenDialogsPassed1 = not xbmc.getCondVisibility('Window.IsVisible(OsdVideoSettings)') and not xbmc.getCondVisibility('Window.IsVisible(OsdAudioSettings)') and not xbmc.getCondVisibility('Window.IsVisible(SubtitleSearch)') and not xbmc.getCondVisibility('Window.IsVisible(VideoBookmarks)') and not xbmc.getCondVisibility('Window.IsVisible(SelectDialog)') and not xbmc.getCondVisibility('Window.IsVisible(YesNoDialog)') and not xbmc.getCondVisibility('Window.IsVisible(ProgressDialog)')
                            checkForOpenDialogsPassed2 = not xbmc.getCondVisibility('Window.IsActive(OsdVideoSettings)')  and not xbmc.getCondVisibility('Window.IsActive(OsdAudioSettings)')  and not xbmc.getCondVisibility('Window.IsActive(SubtitleSearch)')  and not xbmc.getCondVisibility('Window.IsActive(VideoBookmarks)')  and not xbmc.getCondVisibility('Window.IsActive(SelectDialog)')  and not xbmc.getCondVisibility('Window.IsActive(YesNoDialog)')  and not xbmc.getCondVisibility('Window.IsActive(ProgressDialog)')
                            checkForOpenDialogsPassed3 = not xbmc.getCondVisibility('Window.Is(OsdVideoSettings)')        and not xbmc.getCondVisibility('Window.Is(OsdAudioSettings)')        and not xbmc.getCondVisibility('Window.Is(SubtitleSearch)')        and not xbmc.getCondVisibility('Window.Is(VideoBookmarks)')        and not xbmc.getCondVisibility('Window.Is(SelectDialog)')        and not xbmc.getCondVisibility('Window.Is(YesNoDialog)')        and not xbmc.getCondVisibility('Window.Is(ProgressDialog)')
                            
                            checkForOpenDialogsPassed = checkForOpenDialogsPassed1 and checkForOpenDialogsPassed2 and checkForOpenDialogsPassed3
                            
                            
                            # Check for OsdSubtitleSettings on Kodi 18+
                            if playerMonitor.isKodi18plus:
                                checkForOpenKodi18DialogsPassed1 = not xbmc.getCondVisibility('Window.IsVisible(OsdSubtitleSettings)')
                                checkForOpenKodi18DialogsPassed2 = not xbmc.getCondVisibility('Window.IsActive(OsdSubtitleSettings)')
                                checkForOpenKodi18DialogsPassed3 = not xbmc.getCondVisibility('Window.Is(OsdSubtitleSettings)')
                            
                            checkForOpenKodi18DialogsPassed = not playerMonitor.isKodi18plus or (checkForOpenKodi18DialogsPassed1 and checkForOpenKodi18DialogsPassed2 and checkForOpenKodi18DialogsPassed3)
                            
                            
                            # Check for Kodi 21+
                            if playerMonitor.isKodi21plus:
                                checkForOpenKodi21DialogsPassed1 = not xbmc.getCondVisibility('Window.IsVisible(1189)')
                                checkForOpenKodi21DialogsPassed2 = not xbmc.getCondVisibility('Window.IsActive(1189)')
                                checkForOpenKodi21DialogsPassed3 = not xbmc.getCondVisibility('Window.Is(1189)')
                            
                            checkForOpenKodi21DialogsPassed = not playerMonitor.isKodi21plus or (checkForOpenKodi21DialogsPassed1 and checkForOpenKodi21DialogsPassed2 and checkForOpenKodi21DialogsPassed3)
                            
                            
                            # Check for DialogSelectVideo DialogSelectAudio DialogSelectSubtitle on Kodi 22+
                            if playerMonitor.isKodi22plus:
                                checkForOpenKodi22DialogsPassed1 = not xbmc.getCondVisibility('Window.IsVisible(DialogSelectVideo)') and not xbmc.getCondVisibility('Window.IsVisible(DialogSelectAudio)') and not xbmc.getCondVisibility('Window.IsVisible(DialogSelectSubtitle)')
                                checkForOpenKodi22DialogsPassed2 = not xbmc.getCondVisibility('Window.IsActive(DialogSelectVideo)')  and not xbmc.getCondVisibility('Window.IsActive(DialogSelectAudio)')  and not xbmc.getCondVisibility('Window.IsActive(DialogSelectSubtitle)')
                                checkForOpenKodi22DialogsPassed3 = not xbmc.getCondVisibility('Window.Is(DialogSelectVideo)')        and not xbmc.getCondVisibility('Window.Is(DialogSelectAudio)')        and not xbmc.getCondVisibility('Window.Is(DialogSelectSubtitle)')
                            
                            checkForOpenKodi22DialogsPassed = not playerMonitor.isKodi22plus or (checkForOpenKodi22DialogsPassed1 and checkForOpenKodi22DialogsPassed2 and checkForOpenKodi22DialogsPassed3)
                            
                            
                            if checkForOpenDialogsPassed and checkForOpenKodi18DialogsPassed and checkForOpenKodi21DialogsPassed and checkForOpenKodi22DialogsPassed:
                                
                                if xbmc.getCondVisibility('Window.IsActive(VideoOSD)'):
                                    xbmc.executebuiltin('Dialog.Close(VideoOSD)')
                                if xbmc.getCondVisibility('Window.IsActive(MusicOSD)'):
                                    xbmc.executebuiltin('Dialog.Close(MusicOSD)')
                        
                        
                        playerMonitor.idleCheckIntervalTimer = time.time()
            
            
            # --------------------------------------------------------------------------------
            # Save Player DB Movie progress %
            # --------------------------------------------------------------------------------
            if playingVideo and playerMonitor.VideoPlayerIsMovieInDb:
                
                tmpTimerDifference = timeNow - playerMonitor.percentageTimer
                
                if tmpTimerDifference > float(5.00):
                    
                    jsonQuery = xbmc.executeJSONRPC('{"jsonrpc":"2.0", "method": "Player.GetProperties", "params": {"playerid":1,"properties":["percentage"]}, "id": 1}')
                    jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                    jsonQuery = simplejson.loads(jsonQuery)
                    
                    tmpHasKeyCheck = 'result' in jsonQuery and 'percentage' in jsonQuery['result']
                    if tmpHasKeyCheck:
                        playerMonitor.playerPercentage = int(jsonQuery['result']['percentage'])
                    
                    playerMonitor.percentageTimer = time.time()


            # --------------------------------------------------------------------------------
            # CinemaHelper.UserRating
            # --------------------------------------------------------------------------------
            UserRatingPROCESS = bool(xbmcgui.Window(10000).getProperty('CinemaHelper.UserRating.PROCESS'))
            
            if UserRatingPROCESS:
                UserRatingDbId   = int(xbmcgui.Window(10000).getProperty('CinemaHelper.UserRating.DbId'))
                UserRatingDbType = str(xbmcgui.Window(10000).getProperty('CinemaHelper.UserRating.DbType'))
                UserRatingAction = str(xbmcgui.Window(10000).getProperty('CinemaHelper.UserRating.Action'))
                
                UserRatingIsMovie = UserRatingDbType == 'movie'
                UserRatingIsEpisode = UserRatingDbType == 'episode'
                UserRatingIsTvShow = UserRatingDbType == 'tvshow'
                
                if UserRatingAction and UserRatingDbId and (UserRatingIsMovie or UserRatingIsEpisode or UserRatingIsTvShow):
                    
                    if UserRatingAction == 'WatchListAdd':
                        
                        if UserRatingIsMovie:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid":'+str(UserRatingDbId)+',"userrating":1}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        
                        if UserRatingIsEpisode:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid":'+str(UserRatingDbId)+',"userrating":1}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        
                        if UserRatingIsTvShow:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetTvShowDetails", "params": {"tvshowid":'+str(UserRatingDbId)+',"userrating":1}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                    
                    if UserRatingAction == "WatchListRemove":
                        
                        if UserRatingIsMovie:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid":'+str(UserRatingDbId)+',"userrating":0}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        
                        if UserRatingIsEpisode:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid":'+str(UserRatingDbId)+',"userrating":0}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        
                        if UserRatingIsTvShow:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetTvShowDetails", "params": {"tvshowid":'+str(UserRatingDbId)+',"userrating":0}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                
                
                xbmcgui.Window(10000).clearProperty('CinemaHelper.UserRating.PROCESS')
            
            
            # --------------------------------------------------------------------------------
            # CinemaHelper.WatchedState
            # --------------------------------------------------------------------------------
            WatchedStatePROCESS = bool(xbmcgui.Window(10000).getProperty('CinemaHelper.WatchedState.PROCESS'))
            
            if(WatchedStatePROCESS):
                WatchedStateDbId   = int(xbmcgui.Window(10000).getProperty('CinemaHelper.WatchedState.DbId'))
                WatchedStateDbType = str(xbmcgui.Window(10000).getProperty('CinemaHelper.WatchedState.DbType'))
                WatchedStateAction = str(xbmcgui.Window(10000).getProperty('CinemaHelper.WatchedState.Action'))
                
                WatchedStateIsMovie = WatchedStateDbType == 'movie'
                WatchedStateIsEpisode = WatchedStateDbType == 'episode'
                
                if WatchedStateAction and WatchedStateDbId and (WatchedStateIsMovie or WatchedStateIsEpisode):
                    
                    if WatchedStateAction == 'SetWatched':
                        if WatchedStateIsMovie:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid":'+str(WatchedStateDbId)+',"playcount":1,"lastplayed":""}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        if WatchedStateIsEpisode:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid":'+str(WatchedStateDbId)+',"playcount":1,"lastplayed":""}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                    
                    if WatchedStateAction == 'SetNotWatched':
                        if WatchedStateIsMovie:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid":'+str(WatchedStateDbId)+',"playcount":0,"lastplayed":""}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                        if WatchedStateIsEpisode:
                            jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid":'+str(WatchedStateDbId)+',"playcount":0,"lastplayed":""}, "id": 1}')
                            jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                            jsonQuery = simplejson.loads(jsonQuery)
                
                xbmcgui.Window(10000).clearProperty('CinemaHelper.WatchedState.PROCESS')
    
    
    
    
    
    
    # INTERVAL 3
    
    if TimerInterval_3_Enabled and (timeNow - TimerInterval_3) > TimerInterval_3_ResetSec:
        TimerInterval_3 = time.time()
        
        IsScrolling = xbmc.getCondVisibility('Container.Scrolling') or xbmc.getCondVisibility('Container.OnPrevious') or xbmc.getCondVisibility('Container.OnNext') or xbmc.getCondVisibility('Container.OnScrollPrevious') or xbmc.getCondVisibility('Container.OnScrollNext')
        
        if not IsScrolling:
            
            if playerMonitor.skinIsACZG:
                
                # --------------------------------------------------------------------------------
                # Get lookandfeel.skinzoom
                # --------------------------------------------------------------------------------
                if playerMonitor.skinIsACZG:
                    jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.GetSettingValue", "params": {"setting":"lookandfeel.skinzoom"}, "id": 1}')
                    jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                    jsonQuery = simplejson.loads(jsonQuery)
                    
                    tmpHasKeyCheck = 'result' in jsonQuery and 'value' in jsonQuery['result']
                    if tmpHasKeyCheck:
                        SkinZoomValue = str(jsonQuery['result']['value'])
                        if SkinZoomValue and SkinZoomValue != xbmcgui.Window(10000).getProperty('CinemaHelper.GetSettingValue.lookandfeel.skinzoom'):
                            xbmcgui.Window(10000).setProperty('CinemaHelper.GetSettingValue.lookandfeel.skinzoom', str(SkinZoomValue))
                    elif xbmcgui.Window(10000).getProperty('CinemaHelper.GetSettingValue.lookandfeel.skinzoom'):
                        xbmcgui.Window(10000).clearProperty('CinemaHelper.GetSettingValue.lookandfeel.skinzoom')
                
                
                
                # --------------------------------------------------------------------------------
                # Get videolibrary.flattentvshows
                # --------------------------------------------------------------------------------
                jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.GetSettingValue", "params": {"setting":"videolibrary.flattentvshows"}, "id": 1}')
                jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                jsonQuery = simplejson.loads(jsonQuery)
                
                tmpHasKeyCheck = 'result' in jsonQuery and 'value' in jsonQuery['result']
                if tmpHasKeyCheck:
                    xbmcgui.Window(10000).setProperty('CinemaHelper.GetSettingValue.videolibrary.flattentvshows', str(jsonQuery['result']['value']))
                elif xbmcgui.Window(10000).getProperty('CinemaHelper.GetSettingValue.videolibrary.flattentvshows'):
                    xbmcgui.Window(10000).clearProperty('CinemaHelper.GetSettingValue.videolibrary.flattentvshows')
                
                
                
                
                
                
                # Check and synchronize UI color scheme with skin themes and skin colors
                
                uiColorVariant = xbmc.getInfoLabel('Skin.String(uiColorVariant)')
                
                jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.GetSettingValue", "params": {"setting":"lookandfeel.skintheme"}, "id": 1}')
                jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                jsonQuery = simplejson.loads(jsonQuery)
                lookandfeelSkintheme = jsonQuery['result']['value'] if 'result' in jsonQuery and 'value' in jsonQuery['result'] else ''
                
                jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.GetSettingValue", "params": {"setting":"lookandfeel.skincolors"}, "id": 1}')
                jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                jsonQuery = simplejson.loads(jsonQuery)
                lookandfeelSkincolors = jsonQuery['result']['value'] if 'result' in jsonQuery and 'value' in jsonQuery['result'] else ''
                
                
                if lookandfeelSkintheme and lookandfeelSkincolors:
                    if uiColorVariant == '':
                        if lookandfeelSkintheme != 'SKINDEFAULT':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skintheme","value":"SKINDEFAULT"}, "id": 1}')
                        if lookandfeelSkincolors != 'SKINDEFAULT':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skincolors","value":"SKINDEFAULT"}, "id": 1}')
                    elif uiColorVariant == '1':
                        if lookandfeelSkintheme != 'Perfect Pink':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skintheme","value":"Perfect Pink"}, "id": 1}')
                        if lookandfeelSkincolors != 'Perfect Pink':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skincolors","value":"Perfect Pink"}, "id": 1}')
                    elif uiColorVariant == '2':
                        if lookandfeelSkintheme != 'Electric Violet':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skintheme","value":"Electric Violet"}, "id": 1}')
                        if lookandfeelSkincolors != 'Electric Violet':
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"lookandfeel.skincolors","value":"Electric Violet"}, "id": 1}')
                
                
                
                
                
                
                
                
                AllowShowParentDirItems = xbmc.getCondVisibility('Skin.HasSetting(AllowShowParentDirItems)')
                
                if showParentDirItems and not AllowShowParentDirItems:
                    jsonQuery = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Settings.SetSettingValue", "params": {"setting":"filelists.showparentdiritems","value":false}, "id": 1}')
                    jsonQuery = unicode(jsonQuery, 'utf-8', errors='ignore') if sys.version_info.major == 2 else jsonQuery# Python 2/3
                    jsonQuery = simplejson.loads(jsonQuery)
            
            
            
            if playerMonitor.VideoPlayerIsMovieInDb and playerMonitor.movieHasPostCreditsScene and playerMonitor.isPlayingVideo():
                
                timeremaining = (playerMonitor.getTotalTime() - playerMonitor.getTime()) // 60
                
                if timeremaining < nearEndPreReached_Minutes:
                    if not playerMonitor.nearEndPreReached:
                        playerMonitor.nearEndPreReached = True
                        xbmcgui.Window(10000).setProperty('CinemaHelper.player.nearEndPreReached', 'True')
                else:
                    if playerMonitor.nearEndPreReached:
                        playerMonitor.nearEndPreReached = False
                        xbmcgui.Window(10000).clearProperty('CinemaHelper.player.nearEndPreReached')
                
                if timeremaining < nearEndReached_Minutes:
                    if playerMonitor.nearEndReached == '':
                        playerMonitor.nearEndReached = 'True'
                        xbmcgui.Window(10000).setProperty('CinemaHelper.player.nearEndReached', 'True')
                        nearEndReachedTimeOutDurationCount = 0
                
                if playerMonitor.nearEndReached == 'True':
                    if not playerMonitor.nearEndReached == 'TrueAndTimeOut':
                        if nearEndReachedTimeOutDurationCount == 2:
                            playerMonitor.nearEndReached = 'TrueAndTimeOut'
                            xbmcgui.Window(10000).setProperty('CinemaHelper.player.nearEndReached', 'TrueAndTimeOut')
                        else:
                            nearEndReachedTimeOutDurationCount += 1
    
    
    
    
    
    
#/while

