"""第二階段末段條列辨識；僅使用已確認的數字／英文編號。"""
RULE_VERSION = 'body-lists/1.0'
MARKER_PATTERN = r'(?P<dot>[0-9]{1,2}|[A-Za-z])\.|\((?P<paren>[0-9]{1,2}|[A-Za-z])\)|（(?P<wide>[0-9]{1,2}|[A-Za-z])）'
