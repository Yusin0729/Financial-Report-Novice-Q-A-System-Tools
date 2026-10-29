"""使用者確認：Markdown以年份_股票代號開頭，不帶季度。"""
FILENAME_PREFIX_PATTERN = r'^(?P<year>[0-9]{4})_(?P<stock>[0-9]+)_'
PDF_STEM_PATTERN = r'^(?P<year>[0-9]{4})(?:Q[1-4])?_(?P<stock>[0-9]+)_Financial_Report$'
MARKDOWN_ROLE_SUFFIXES = ('_document.md', '_processed.md', '_tagged.md')
