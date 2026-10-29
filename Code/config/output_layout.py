"""批次輸出名稱：台灣日期與24小時制時間；保留舊流水號讀取相容。"""
BATCH_NAME_FORMAT = 'Financial_raw_%Y%m%d_%H-%M-%S'
BATCH_NAME_PATTERN = r'Financial_(?:(?:raw|processed|tagged|chunk)_)?\d{8}_(?:(?:[01]\d|2[0-3])-[0-5]\d-[0-5]\d|\d{3,})'
STAGE_BATCH_FORMAT = 'Financial_{stage}_%Y%m%d_%H-%M-%S'
