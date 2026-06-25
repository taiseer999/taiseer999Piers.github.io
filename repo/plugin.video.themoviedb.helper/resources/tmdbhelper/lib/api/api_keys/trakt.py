from tmdbhelper.lib.addon.permissions import __access__
from tmdbhelper.lib.api.api_keys.tokenhandler import TokenHandler

if __access__.has_access('internal'):
    CLIENT_ID = 'ce7457fe1e42f09919b57171e9196109717474bad5b13b2a70959aef2f8e5624'
    CLIENT_SECRET = '004d641c35178c7d3c5798313919bec181e9a162bc84f16a2e78dc82a37150db'
    USER_TOKEN = TokenHandler('trakt_token', store_as='setting')

elif __access__.has_access('trakt'):
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    USER_TOKEN = TokenHandler('trakt_token', store_as='setting')

else:
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    USER_TOKEN = TokenHandler()
