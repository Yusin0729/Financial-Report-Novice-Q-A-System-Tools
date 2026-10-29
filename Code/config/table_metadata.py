"""表格年度的明列格式；沿用既有民國／西元範圍，不推測裸金額。"""
ROC_YEAR_OFFSET = 1911
ROC_YEAR_RANGE = (100, 288)  # 使用者指定：民國100年以前不列入表格年度。
GREGORIAN_YEAR_RANGE = (1900, 2199)
YEAR_DIGITS = '0-9〇零○一二三四五六七八九十百'
YEAR_TOKEN = r'(?:[0-9]{1,4}|[〇零○一二三四五六七八九十百]{1,7})'
YEAR_PREFIX = r'(?:(?:中華民國|民國))?'
YEAR_CONNECTOR = r'[、及與和～~至/\-]'
YEAR_ITEM = YEAR_PREFIX + YEAR_TOKEN
EXPLICIT_PERIOD_PATTERN = (
    rf'(?<![{YEAR_DIGITS}])(?:{YEAR_ITEM}(?:年度?)?{YEAR_CONNECTOR})*{YEAR_ITEM}年度?'
)
EXPLICIT_DATE_PATTERN = (
    rf'(?<![{YEAR_DIGITS}]){YEAR_PREFIX}(?P<year>{YEAR_TOKEN})'
    r'(?P<separator>[./])(?:0?[1-9]|1[0-2])(?P=separator)(?:0?[1-9]|[12][0-9]|3[01])(?!\d)'
)
