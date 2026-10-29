"""第一階段定位比較規則；只影響比對，不改寫原文。"""
SELECTION_RULE_VERSION = 'local-selection/1.1'
NORMALIZATION_FORM = 'NFKC'
NOTES_REFERENCE_TERMS = ('請參閱', '參閱', '詳見', '請詳', '查核意見')
NON_NOTES_PAGE_HEADINGS = ('目錄', '會計師查核報告', '會計師查核報告書')
NOTES_HEADER_PATTERN = (
    r'^(?:[^<>。，；：:()]*?(?:公司|集團))?'
    r'合併財務(?:報告|報表)附註(?:\(續\))?(?:\(金額[^()]*\))?$'
)
