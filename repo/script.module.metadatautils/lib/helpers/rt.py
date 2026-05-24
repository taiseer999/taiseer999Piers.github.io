#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
    script.module.metadatautils
    rt.py
    Get metadata from rt
"""

import os, sys
from .utils import get_json, requests, try_parse_int, log_msg
import bs4 as BeautifulSoup
from simplecache import use_cache
import json

class Rt(object):
    """Info from rt (currently only top250)"""

    def __init__(self, simplecache=None, kodidb=None):
        """Initialize - optionaly provide simplecache object"""
        if not simplecache:
            from simplecache import SimpleCache
            self.cache = SimpleCache()
        else:
            self.cache = simplecache
        if not kodidb:
            from .kodidb import KodiDb
            self.kodidb = KodiDb()
        else:
            self.kodidb = kodidb
 
    def get_ratings_tv_rt(self, title):
        """get rt details by providing an tvshowtitle"""
        params = {"q": title, "t": "tvseries", "limit": "1"}
        title = title.replace(" ", "_").lower()
        result = {}
        headers = {'User-agent': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows Phone OS 7.0; Trident/3.1; \
                                IEMobile/7.0; LG; GW910)'}
        html = ''
        page = []
        html = requests.get("https://www.rottentomatoes.com/tv/%s" %
            title, headers=headers, timeout=5).text
        soup = BeautifulSoup.BeautifulSoup(html, features="html.parser")
        #log_msg("get_RT_soup - data from json %s ----->%s" %  (title, soup))
        for div in soup.find_all("script", type="application/ld+json"):
            for a_link in div:
                data = json.loads(a_link)
                if data and data.get("aggregateRating"):
                    data = data["aggregateRating"]
                    if data.get("ratingCount"):
                        result["tomatometerScoreAll.ratingCount"] = data.get("ratingCount")
                        if data.get("ratingValue"):
                            result["RottenTomatoes.Meter"] = data.get("ratingValue")
        return result
        