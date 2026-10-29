"""使用者確認的補標記規則；英文不限字數，保留句尾標點排除。"""
RULE_VERSION = 'markdown-headings/1.15'
LIST_PREFIX_PATTERN = r'^[ \t\u3000]*-[ \t\u3000]+'
PAGE_NUMBER_PATTERN = r'^[ \t\u3000]*-[ \t\u3000]*[0-9](?:[ \t\u3000]*[0-9])*[ \t\u3000]*-[ \t\u3000]*$'
MAX_CANDIDATE_LENGTH = 20
UNLIMITED_LENGTH_MARKERS = frozenset(('english_dot', 'parenthesized_english'))
EXCLUDED_ENDINGS = frozenset('，。；！？,;!?」』"\')）]')
COLON_ENDINGS = (':', '：')
CN_NUMERALS = '一二三四五六七八九十百'
APPENDIX_PREFIX_PATTERN = rf'^附表(?P<number>[{CN_NUMERALS}]+)'
NOTE_PREFIX_PATTERN = rf'^註[{CN_NUMERALS}]+'
# 新版####與舊版#均可作附表邊界；不把一般###當附表標記。
APPENDIX_MARKDOWN_PATTERN = (
    rf'^ {{0,3}}(?:####|#)[ \t]+(?P<title>附[ \t\u3000]*表[ \t\u3000]*'
    rf'(?P<number>[{CN_NUMERALS}](?:[ \t\u3000]*[{CN_NUMERALS}])*)[^\r\n]*)$'
)
PURE_YEAR_PATTERN = (r'^(?:(?:中華民國|民國)\s*)?'
                     r'(?:[0-9]{2,4}|[〇零○一二三四五六七八九十百]{2,4})\s*年'
                     r'(?:度|[0-9]{1,2}月[0-9]{1,2}日)?$')
_YEAR_ITEM = r'(?:(?:中華民國|民國))?(?:[0-9]{2,4}|[〇零○一二三四五六七八九十百]{2,4})'
MULTI_YEAR_DESCRIPTION_PATTERN = (
    rf'^{_YEAR_ITEM}(?:年(?:度)?)?(?:及{_YEAR_ITEM}(?:年(?:度)?)?)*'
    rf'及{_YEAR_ITEM}年(?:度)?.*$'
)
MARKER_PATTERNS = (
    ('chinese_comma', rf'[{CN_NUMERALS}]+、'),
    ('parenthesized_chinese', rf'(?:\([{CN_NUMERALS}]+\)|（[{CN_NUMERALS}]+）)'),
    ('number_dot', r'[0-9]{1,2}\.'),
    ('parenthesized_number', r'(?:\([0-9]{1,2}\)|（[0-9]{1,2}）)'),
    ('english_dot', r'[A-Za-z]\.'),
    ('parenthesized_english', r'(?:\([A-Za-z]\)|（[A-Za-z]）)'),
)
