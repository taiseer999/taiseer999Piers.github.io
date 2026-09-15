# -*- coding: utf-8 -*-
from apis import mediafusion_api
from modules import source_utils
from modules.native_torrents import filter_and_build_sources, scrape_expiry, scrape_timeout
from modules.settings import mediafusion_scrape_active
from modules.kodi_utils import logger


class source:
	def __init__(self):
		self.scrape_provider = 'mediafusion'
		self.sources = []

	def results(self, info):
		try:
			if not mediafusion_scrape_active():
				return source_utils.internal_results(self.scrape_provider, self.sources)
			imdb_id = info.get('imdb_id')
			if not imdb_id:
				return source_utils.internal_results(self.scrape_provider, self.sources)
			streams = mediafusion_api.search_streams(
				imdb_id, info.get('media_type'), info.get('season'), info.get('episode'),
				timeout=scrape_timeout(info), expiration=scrape_expiry(info))
			self.sources = filter_and_build_sources(self.scrape_provider, streams, info)
		except Exception as e:
			logger('mediafusion scraper Exception', str(e))
		source_utils.internal_results(self.scrape_provider, self.sources)
		return self.sources
