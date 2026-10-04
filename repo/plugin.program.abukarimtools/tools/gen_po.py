# -*- coding: utf-8 -*-
"""Generate resource.language strings.po files from strings_map.STRINGS.
Run from the addon root:  python3 tools/gen_po.py
"""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from resources.lib.strings_map import STRINGS

LANGS = {
    'en_gb': ('English (UK)', 'en', 0),   # (name, iso, tuple-index into value)
    'ar_sa': ('Arabic',       'ar', 1),
}

HEADER = '''msgid ""
msgstr ""
"Project-Id-Version: plugin.program.abukarimtools\\n"
"Report-Msgid-Bugs-To: ABUKARIM TOOLS\\n"
"Language-Team: %(name)s\\n"
"Language: %(iso)s\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

'''

def esc(s):
    return s.replace('\\\\', '\\\\\\\\').replace('"', '\\\\"').replace('\n', '\\\\n')

for code, (name, iso, idx) in LANGS.items():
    d = os.path.join('resources', 'language', 'resource.language.%s' % code)
    os.makedirs(d, exist_ok=True)
    out = io.StringIO()
    out.write(HEADER % {'name': name, 'iso': iso})
    for sid in sorted(STRINGS):
        en, ar = STRINGS[sid]
        val = (en, ar)[idx]
        out.write('msgctxt "#%d"\n' % sid)
        out.write('msgid "%s"\n' % esc(en))       # msgid is ALWAYS the English source
        out.write('msgstr "%s"\n\n' % (esc(val) if idx else ''))  # en_gb: empty msgstr = use msgid
    with open(os.path.join(d, 'strings.po'), 'w', encoding='utf-8') as f:
        f.write(out.getvalue())
    print('wrote %s (%d strings)' % (os.path.join(d, 'strings.po'), len(STRINGS)))
