import unittest

import parameterized

import xbmcext


class PluginTest(unittest.TestCase):
    @parameterized.parameterized.expand([
        ['plugin://plugin.video.example/event/2023'],
        ['plugin://plugin.video.example/video/vi3337078041/'],
        ['plugin://plugin.video.example/'],
        ['plugin://plugin.video.example/title/tt5180504'],
        ['plugin://plugin.video.example/video/search'],
        ['plugin://plugin.video.example/video/search?q="Stranger"'],
        ['plugin://plugin.video.example/pressroom/bio']
    ])
    def test_call(self, url):
        plugin = xbmcext.Plugin(0, url)

        @plugin.route('/event/{id:int}')
        def event(id):
            self.assertEqual(url, 'plugin://plugin.video.example/event/2023')
            self.assertEqual(id, 2023)

        @plugin.route(r'/video/{:re("vi\d{10}")}')
        def video():
            self.assertEqual(url, 'plugin://plugin.video.example/video/vi3337078041/')

        @plugin.route('/')
        def home():
            self.assertEqual(url, 'plugin://plugin.video.example/')

        @plugin.route(r'/title/{id:re("tt\d{7}")}')
        def title(id):
            self.assertEqual(url, 'plugin://plugin.video.example/title/tt5180504')
            self.assertEqual(id, 'tt5180504')

        @plugin.route('/video/search')
        def search():
            self.assertEqual(url, 'plugin://plugin.video.example/video/search')

        @plugin.route('/video/search')
        def search(q):
            self.assertEqual(url, 'plugin://plugin.video.example/video/search?q="Stranger"')
            self.assertEqual(q, 'Stranger')

        @plugin.route('/pressroom/{}')
        def pressroom():
            self.assertEqual(url, 'plugin://plugin.video.example/pressroom/bio')

        plugin()

    def test_redirect(self):
        plugin = xbmcext.Plugin(0, 'plugin://plugin.video.example/')

        @plugin.route('/')
        def home():
            pass

        @plugin.route('/video/{videoId}')
        def video(videoId, listId):
            self.assertEqual(videoId, 'vi4275684633')
            self.assertEqual(listId, 53181649)

        plugin.redirect('/video/vi4275684633', listId=53181649)
