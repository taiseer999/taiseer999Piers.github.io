import xbmc

class Logger:
    @staticmethod
    def info(message):
        xbmc.log(f"KodiAuthBackup: {message}", xbmc.LOGINFO)

    @staticmethod
    def error(message):
        xbmc.log(f"KodiAuthBackup ERROR: {message}", xbmc.LOGERROR)

logger = Logger()
