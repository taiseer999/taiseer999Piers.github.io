#!/usr/bin/python
# -*- coding: utf-8 -*-
from tmdbhelper.lib.files.dbdata import Database
from tmdbhelper.lib.items.database.tabledef import (
    BASEITEM_COLUMNS,
    MOVIE_COLUMNS,
    TVSHOW_COLUMNS,
    EPISODE_GROUP_COLUMNS,
    EPISODE_GROUP_SEASON_COLUMNS,
    EPISODE_GROUP_SEASON_EPISODE_COLUMNS,
    SEASON_COLUMNS,
    EPISODE_COLUMNS,
    BELONGS_COLUMNS,
    COLLECTION_COLUMNS,
    RATINGS_COLUMNS,
    PERSON_COLUMNS,
    CERTIFICATION_COLUMNS,
    VIDEO_COLUMNS,
    GENRE_COLUMNS,
    LANGUAGE_COLUMNS,
    LANGUAGES_COLUMNS,
    COUNTRY_COLUMNS,
    COUNTRIES_COLUMNS,
    STUDIO_COLUMNS,
    NETWORK_COLUMNS,
    COMPANY_COLUMNS,
    BROADCASTER_COLUMNS,
    CREWMEMBER_COLUMNS,
    CASTMEMBER_COLUMNS,
    CUSTOM_COLUMNS,
    PROVIDER_COLUMNS,
    SERVICE_COLUMNS,
    ART_COLUMNS,
    FANART_TV_COLUMNS,
    DEFAULT_ART_COLUMNS,
    USER_ART_COLUMNS,
    UNIQUE_ID_COLUMNS,
    TRANSLATION_COLUMNS,
    SIMPLECACHE_COLUMNS,
    LACTIVITIES_COLUMNS,
)


class ItemDetailsDatabase(Database):
    cache_filename = 'ItemDetails.db'

    # -- TMDbHelper genre language refresh v2 (by ABUKARIM TOOLS) --
    # Genre rows carry no language and are never overwritten, so after a
    # language change they stay in the old language. Clear them once and
    # expire their items so they are refetched in the current language.
    def create_database(self):
        connection = super().create_database()
        try:
            self._abk_genre_language_refresh()
        except Exception as error:
            self.kodi_log(f'CACHE: ABK genre language refresh failed: {error}', 1)
        return connection

    def _abk_genre_language_refresh(self):
        import sqlite3
        from tmdbhelper.lib.addon.plugin import get_language
        language = get_language() or 'en-US'
        con = sqlite3.connect(self._db_file, timeout=self._db_timeout)
        try:
            with con:
                con.execute('CREATE TABLE IF NOT EXISTS abk_meta(key TEXT PRIMARY KEY, value TEXT)')
                row = con.execute("SELECT value FROM abk_meta WHERE key='genre_language_v2'").fetchone()
                if row and row[0] == language:
                    return
                con.execute('UPDATE baseitem SET expiry=0 WHERE id IN (SELECT parent_id FROM genre)')
                cleared = con.execute('DELETE FROM genre').rowcount
                con.execute("INSERT OR REPLACE INTO abk_meta(key, value) VALUES ('genre_language_v2', ?)", (language, ))
        finally:
            con.close()
        self.kodi_log(f'CACHE: ABK genre language refresh -> {language} ({cleared} genre rows cleared)', 1)

    def __init__(self):
        super().__init__(filename=self.cache_filename)

    def create_database_execute(self, connection):
        with connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            result = super().create_database_execute(connection)
            if version and version < 51:
                self.migrate_next_episode_activities(connection)
            return result

    @staticmethod
    def migrate_next_episode_activities(connection):
        # Run after table creation: upgrades through version 50 rebuild lactivities.
        connection.execute(
            'DELETE FROM lactivities WHERE id IN (?, ?, ?)',
            ('show.trakt.nextup', 'show.trakt.all_next_episodes', 'show.mdblist.all_next_episodes'),
        ).close()

    # DB version must be max of table_version
    database_version = 51

    database_changes = {
        21: (),
        22: (),
        23: (),
        24: (),
        25: (),
        26: (),
        27: (),
        28: (),
        29: (),
        30: (),
        31: (),
        32: (),
        33: (),
        34: (),
        35: (),
        36: (),
        37: (),
        38: (),
        39: (),
        40: (),
        41: (),
        42: (),
        43: (),
        44: (),
        45: (),
        46: (),
        47: (),
        48: (),
        49: (),
        50: (
            # Rebuild cached details with episode counts and independent user artwork.
            'DROP TABLE IF EXISTS episode_group_season_episodes',
            'DROP TABLE IF EXISTS episode_group_seasons',
            'DROP TABLE IF EXISTS episode_groups',
            'DROP TABLE IF EXISTS episode',
            'DROP TABLE IF EXISTS season',
            'DROP TABLE IF EXISTS tvshow',
            'DROP TABLE IF EXISTS belongs',
            'DROP TABLE IF EXISTS collection',
            'DROP TABLE IF EXISTS movie',
            'DROP TABLE IF EXISTS ratings',
            'DROP TABLE IF EXISTS person',
            'DROP TABLE IF EXISTS genre',
            'DROP TABLE IF EXISTS language',
            'DROP TABLE IF EXISTS languages',
            'DROP TABLE IF EXISTS country',
            'DROP TABLE IF EXISTS countries',
            'DROP TABLE IF EXISTS studio',
            'DROP TABLE IF EXISTS company',
            'DROP TABLE IF EXISTS network',
            'DROP TABLE IF EXISTS broadcaster',
            'DROP TABLE IF EXISTS video',
            'DROP TABLE IF EXISTS certification',
            'DROP TABLE IF EXISTS crewmember',
            'DROP TABLE IF EXISTS castmember',
            'DROP TABLE IF EXISTS provider',
            'DROP TABLE IF EXISTS service',
            'DROP TABLE IF EXISTS custom',
            'DROP TABLE IF EXISTS art',
            'DROP TABLE IF EXISTS fanart_tv',
            'DROP TABLE IF EXISTS default_art',
            'DROP TABLE IF EXISTS user_art',
            'DROP TABLE IF EXISTS unique_id',
            'DROP TABLE IF EXISTS translation',
            'DROP TABLE IF EXISTS simplecache',
            'DROP TABLE IF EXISTS lactivities',
            'DROP TABLE IF EXISTS baseitem',
        ),
        51: (),  # Activity migration runs after tables have been created.
    }

    baseitem_columns = BASEITEM_COLUMNS
    movie_columns = MOVIE_COLUMNS
    tvshow_columns = TVSHOW_COLUMNS
    episode_groups_columns = EPISODE_GROUP_COLUMNS
    episode_group_seasons_columns = EPISODE_GROUP_SEASON_COLUMNS
    episode_group_season_episodes_columns = EPISODE_GROUP_SEASON_EPISODE_COLUMNS
    season_columns = SEASON_COLUMNS
    episode_columns = EPISODE_COLUMNS
    belongs_columns = BELONGS_COLUMNS
    collection_columns = COLLECTION_COLUMNS
    ratings_columns = RATINGS_COLUMNS
    person_columns = PERSON_COLUMNS
    certification_columns = CERTIFICATION_COLUMNS
    video_columns = VIDEO_COLUMNS
    genre_columns = GENRE_COLUMNS
    language_columns = LANGUAGE_COLUMNS
    languages_columns = LANGUAGES_COLUMNS
    country_columns = COUNTRY_COLUMNS
    countries_columns = COUNTRIES_COLUMNS
    studio_columns = STUDIO_COLUMNS
    network_columns = NETWORK_COLUMNS
    company_columns = COMPANY_COLUMNS
    broadcaster_columns = BROADCASTER_COLUMNS
    crewmember_columns = CREWMEMBER_COLUMNS
    castmember_columns = CASTMEMBER_COLUMNS
    custom_columns = CUSTOM_COLUMNS
    provider_columns = PROVIDER_COLUMNS
    service_columns = SERVICE_COLUMNS
    art_columns = ART_COLUMNS
    fanart_tv_columns = FANART_TV_COLUMNS
    user_art_columns = USER_ART_COLUMNS
    default_art_columns = DEFAULT_ART_COLUMNS
    unique_id_columns = UNIQUE_ID_COLUMNS
    translation_columns = TRANSLATION_COLUMNS
    simplecache_columns = SIMPLECACHE_COLUMNS
    lactivities_columns = LACTIVITIES_COLUMNS

    @property
    def database_tables(self):
        return {
            'baseitem': self.baseitem_columns,
            'belongs': self.belongs_columns,
            'collection': self.collection_columns,
            'movie': self.movie_columns,
            'tvshow': self.tvshow_columns,
            'episode_groups': self.episode_groups_columns,
            'episode_group_seasons': self.episode_group_seasons_columns,
            'episode_group_season_episodes': self.episode_group_season_episodes_columns,
            'season': self.season_columns,
            'episode': self.episode_columns,
            'ratings': self.ratings_columns,
            'person': self.person_columns,
            'genre': self.genre_columns,
            'language': self.language_columns,
            'languages': self.languages_columns,
            'country': self.country_columns,
            'countries': self.countries_columns,
            'studio': self.studio_columns,
            'company': self.company_columns,
            'network': self.network_columns,
            'broadcaster': self.broadcaster_columns,
            'video': self.video_columns,
            'certification': self.certification_columns,
            'crewmember': self.crewmember_columns,
            'castmember': self.castmember_columns,
            'provider': self.provider_columns,
            'service': self.service_columns,
            'custom': self.custom_columns,
            'art': self.art_columns,
            'fanart_tv': self.fanart_tv_columns,
            'default_art': self.default_art_columns,
            'user_art': self.user_art_columns,
            'unique_id': self.unique_id_columns,
            'translation': self.translation_columns,
            'simplecache': self.simplecache_columns,
            'lactivities': self.lactivities_columns,
        }
