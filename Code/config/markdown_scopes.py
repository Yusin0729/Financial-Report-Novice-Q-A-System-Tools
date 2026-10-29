"""逐份確認的附註範圍；鍵為processed原文SHA，不用檔名／公司猜起訖。

行號僅定位該份Markdown，不是PDF頁碼。範圍未確認或內容改變時拒絕猜測。
"""
CONFIRMED_NOTES_SCOPES: dict[str, tuple[int, int, str]] = {}
