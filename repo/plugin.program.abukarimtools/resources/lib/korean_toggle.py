# -*- coding: utf-8 -*-
"""Korean Media tab on/off – thin wrapper around tab_toggle."""
from resources.lib import tab_toggle


def run():
    tab_toggle.run(key='korean', slot='1103', label='Korean Media')
