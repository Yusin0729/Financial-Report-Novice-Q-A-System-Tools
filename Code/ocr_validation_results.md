# MinerU OCR 小範圍驗證（2026-10-21）

結論：自訂 OCR 接入可執行，指定樣本完成；尚未通過整份財報品質驗收。未執行整批財報，也未修改來源 PDF、舊產物、參考原檔或獨立 MinerU 網頁。

## 本次實測

18 項無模型自動測試重新通過：四點座標與非整數裁切尺寸、財務符號、低信心／空結果、非法回傳、失敗回報、模擬混合內容去重、未觸發時延後初始化、OCR 開關與 factory 註冊、既有頁序及 HTML 表格。它們不能代替真實辨識品質測試。

真實來源 2025Q4_2330_Financial_Report.pdf（85 頁），SHA-256：68daa6d9ba02d71efe0838f2a9b0e135af26a2d1bddbaa62a06d3eb3501dacb2；測前測後未變更。

|實體頁序|結果|OCR 區域／保留 OCR 框|HTML 表格|秒數|
|---|---|---|---|---|
|2 掃描目錄|success，需品質核對|3／84（另1框低分）|1|34.265（含初始化）|
|3 掃描聲明|success，需品質核對|4／22（另8框低分）|0|6.724|
|15 原生正文|success，未觸發 OCR|0／0|1|3.290|
|50 原生財務表格|success，未觸發 OCR|0／0|2|12.768|

四頁樣本區域框均通過座標驗證，部分原生交疊計數為0；視覺抽查第2、3頁覆圖對齊文字。這不代表所有旋轉、裁切及混合文件均通過。程序抽樣 RSS 峰值約1.245 GiB，Windows private 峰值約2.525 GiB；不是整機RAM需求，也不保證整份文件峰值相同。

實測產物：`../Output/markdown_raw/2025Q4_2330_Financial_Report/ocr_validation_20261021_021627_550198/`，含逐頁 Markdown、OCR 座標覆圖與 manifest（區域文字、四點座標、分數、狀態、模型參數、版本及記憶體抽樣）。先前 factory 註冊失敗的紀錄保留於 ocr_validation_20261021_021151_771855；修正為與 Docling 一致的 keyword factory 呼叫後重跑成功，不抹除失敗紀錄。

## 合成混合頁（工程驗證，非真實混合財報）

人工建立原生英文財務文字＋中文掃描圖片，完整 Docling 處理完成，1個 OCR 區域、2個框均保留；原生 `NATIVE: USD (1,234.50) -6.00 100% FY2025` 僅出現1次。掃描文字 `掃描區域 新臺幣仟元`、`114年度 (9,876.50) -12.5%` 均保留。覆圖框與圖片文字對齊。耗時10.686秒（含初始化），RSS峰值約0.971 GiB、private約2.056 GiB。

產物：`../Output/markdown_raw/synthetic_mixed/ocr_validation_20261021_021657_885417/`；人工預期文字另放 `synthetic_mixed_fixture/expected.json`，沒有冒充 OCR 結果。目前沒有真實混合財報樣本，品質驗收仍缺此項。

## 人工抽查與舊 EasyOCR 同頁比較

- 文字辨識：第2頁目錄標題將裝飾符號辨成 `8目 錄S`；第3頁原圖「財務報表聲明書」辨成「財務報告聲明書」，並有印章雜字。不能視為文字全對。
- 閱讀順序：第3頁日期框有辨出 `民／國／115／年／2／月／10／日`，但 Markdown 順序錯亂，屬排序／版面問題，應與錯字分開。
- 表格：第2頁 OCR 框分別定位標題、頁次及附註編號，但 HTML 表頭仍出現「目頁」「次附註编號」跨欄錯配。第15頁日期與準則名稱仍錯欄。第50頁特別盈餘公積三個數字仍擠同格，負號括號、小數與幣別存在，不代表欄位對應正確。
- 舊 EasyOCR 第2頁存在「公司沿革」等空白標題格；新結果有該文字。舊第3頁正文多處缺漏，新版正文較完整，但兩版標題都有報表→報告錯字、日期順序問題。只做具體樣本比較，未建立逐字標準答案，不報準確率或整體改善結論。
- 舊 OCR OFF／EasyOCR ON 與本次第50頁均有相同錯欄，本次沒有在該頁執行OCR，故不能歸因為新OCR辨識錯誤。

## 實作與參數

`config/ocr.py` 固定 CPU ch_lite：PP-OCRv5 det＋lite rec，216 DPI、rec batch1、drop_score0.5、det box0.3、det thresh0.3、unclip1.8、dilation True、det960/max、不合併框、不做方向／公式分類。沿用Docling CPU threads2、stage batch1、PDFium、HTML表格，OCR預設關閉。

權重repo opendatalab/PDF-Extract-Kit-1.0，revision ed6b654c018d742e65a17671e379c5e6ecc87ec9；兩檔共47,117,877 bytes，SHA-256驗證通過，存Code/.cache/mineru_ocr。具體雜湊見config/ocr.py。已安裝的必要套件可直接使用，本次未安裝完整MinerU、PaddlePaddle、OmegaConf或loguru，未移除舊環境套件或快取。

`functions/integrations/mineru_paddle.py` 僅初始化 det/rec；`docling_mineru_ocr.py` 註冊自訂 stage、換算座標、使用 Docling PDF-aware 區域與 PDF_FIRST 去重並記錄部分交疊風險；`mineru_ocr_vendor/` 保留必要來源、字典、AGPL授權、Apache標頭、NOTICE及來源SHA紀錄。`ingestion/pdf_to_markdown.py` 接線及序列化選定實體頁；`experiments/export_output.py` 集中寫檔；停用export時不阻斷核心記憶體資料流。

## 執行

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py
& .\Code\.venv\Scripts\python.exe Code/main.py --ocr
& .\Code\.venv\Scripts\python.exe -m unittest discover -s Code/tests -q
& .\Code\.venv\Scripts\python.exe Code/tests/validate_ocr_pages.py --pdf "Financial Statements/2025Q4_2330_Financial_Report.pdf" --pages 2 3 15 50
```

新環境使用Python3.11及requirements.lock；既有環境不用重建。首次模型下載需網路，但不傳送文件；推論在本機。驗證入口支援 `--no-export`，主流程由Settings.export_enabled控制。合成PDF建立使用bundled reportlab/Pillow，非轉換程式必要依賴。

## 限制

未重跑完整85頁或其他年份；未驗證真實混合頁、所有掃描財務數字及跨頁表格。部分原生/OCR框相交時，Docling可能移除整個OCR框，本版記錄風險、不自行分割。空白及低分結果記為ocr_no_text／low_confidence，仍需人工區分真空白。必要區域來自Docling版面偵測，漏偵測的文字區域不保證會OCR。品質問題未自動修正，也未變更參數或擴增流程。


2026-10-21命名更新：既有真實財報Markdown已改為年份_股票代號前綴；本文件前述舊檔名為歷史紀錄，現名請依同資料夾manifest.markdown_files及filename_migration查詢。檔案正文不變。現行metadata以檔名前綴取得report_year／stock_code，不推定季度或公司。
