"""使用者確認的疑似漏辨識表格門檻。"""
RULE_VERSION = 'suspected-table/1.1'
CANDIDATE_RUN_LENGTH = 5
BODY_RUN_LENGTH = 3
BODY_CHINESE_LENGTH = 20
START_TAG = '<cannotfindtable>'
END_TAG = '</cannotfindtable>'
NUMBER_PATTERN = r'(?:[+-]?\$?|\$[+-]?)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?'
