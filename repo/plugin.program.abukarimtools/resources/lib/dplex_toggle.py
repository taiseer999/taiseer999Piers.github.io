# -*- coding: utf-8 -*-
"""DPlex tab on/off – thin wrapper around tab_toggle."""
from resources.lib import tab_toggle


def run():
    tab_toggle.run(key='dplex', slot='1104', label='DPlex')
