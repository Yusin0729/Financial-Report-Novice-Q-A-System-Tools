# PDF目錄JSON：實作與驗證（2026-10-21）

本次僅本機及模擬測試，未呼叫Gemini、未上傳PDF、未產生API費用。功能尚未通過真實服務或目錄辨識品質驗證。

## 輸入與輸出

選單5或`--toc-pdf`接受Financial Statements內單一PDF。用既有pypdfium2 5.13.0的PdfDocument.new／import_pages（零起算[1,2]）／save抽出新PDF；來源唯讀。核心TocPdf含兩頁PDF bytes、來源與抽頁SHA256、總頁數及實體頁序映射；TocResult含驗證結果與原始回答。無需透過Output傳遞，也不載入Docling、OCR或額外模型。

模型gemini-3.1-flash-lite；官方generateContent REST v1beta，使用Python標準庫urllib、inlineData的application/pdf，無Files API長期檔案ID。8192 maxOutputTokens，網路等待逾時120秒（urllib socket timeout，並非整個流程硬性總時限），重試0。其他生成參數未覆寫，依服務端模型設定；實際modelVersion及usageMetadata保存於manifest，不預估成實際費用。

目錄schema financial-toc/1.0，提示詞toc-pdf/1.0。模型只回傳pages與entries：

- pages：source_pdf_page（原PDF2／3）、classification（toc／not_toc／unreadable）、issues。
- entries：唯一id、parent_id（頂層空字串；父項須先出現）、含編號的title、printed_pages原字串、note_numbers原字串、source_pdf_page。
- 欄位空白保留空字串；例如15、79～84不轉數值範圍。外層由本機補schema_version、source_sha256、source_pages、status。不產生附註範圍候選或正文JSON。

JSON型別、額外／缺少欄位、實體頁序、重複id、未知父項、非目錄頁有項目、空目錄及完成原因皆檢查。MAX_TOKENS即使回答能解析也拒絕當成功。extracted_needs_review僅代表結構有效，incomplete_needs_review代表有無法辨識頁；no_toc_found不視為完成目錄擷取。無法保證模型未漏列、誤讀或捏造，仍須人工對照。

## 本次實際本機核對

指定2025Q4_2330_Financial_Report.pdf共85頁，來源SHA256：68daa6d9ba02d71efe0838f2a9b0e135af26a2d1bddbaa62a06d3eb3501dacb2。

抽出第2、3頁為867516 bytes的兩頁PDF（僅記憶體，不建立正式實驗run）。抽出頁分別與原PDF相同頁以scale=1渲染，尺寸與RGB像素完全相同；來源檔案雜湊未變。另檢視預覽，第2頁為目錄、第3頁為關係企業合併財務報告聲明書；後者不得當目錄。預覽檔僅供本次檢查，完成後移除。

## 模擬測試

Code/tests/test_toc.py新增18項，不連網，以合成PDF與明確模擬回覆測試：抽頁、來源不變、不足頁數、欄位型別／頁序／階層、保留印刷頁碼、非目錄與無法辨識、截斷／阻擋／空回答、缺金鑰先停止、請求只含抽頁bytes、HTTP429／逾時／斷線不重試、停用寫檔、命名與來源／用量、失敗診斷、不覆寫、拒絕批次選取、命令列／選單串接及來源中途變更。這些結果不替代真實API測試。

本次完整執行`python -m unittest discover -s Code/tests -p 'test_*.py' -q`：85項通過（含新增18項與原有67項），exit code 0。既有OCR測試為介面／模擬檢查，本次未重新執行真實OCR推論。

## 依賴與參考

初次實作無新增安裝套件；後續依使用者選擇加入根目錄.env讀取，將環境及requirements.lock已有的python-dotenv==1.2.4列為requirements.txt直接依賴，未另行安裝，鎖定版本不變。使用現有Python3.11與pypdfium2；Google API為外部服務，必須由使用者在本機.env或既有環境變數提供金鑰。非空環境值優先，只讀指定.env且不做變數展開／環境寫入。程式不輸出金鑰，不把金鑰放URL或manifest，拒絕HTTP重新導向，錯誤不輸出服務端body。

.env追加驗證：本次只以暫存假金鑰執行test_toc*.py共25項通過，包含原18項及新增7項金鑰讀取檢查。未讀專案真實金鑰或呼叫Gemini，也未重跑全部85項。支援UTF-8／BOM、引號及註解；檢查環境優先、空值錯誤、編碼錯誤不洩漏內容、指定專案檔、修改後重讀、不展開其他環境變數及不改寫os.environ。新增.env與.env.example皆空白金鑰，.gitignore排除私人.env、保留範本。

閱讀Reference Sources/Financial_RAG_Core/Function/markdown_pdf_parser.py的build_toc_mapping：舊方法以Markdown正規表示式匹配並順次配頁，會正規化中文及推算起訖。本功能不重用該程式碼，不採上述配頁策略；參考版本／commit及遠端網址未知，原檔不修改。

官方API參考（2026-10-21核對）：

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/document-processing
- https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite

尚待真實Gemini呼叫確認REST schema相容性、實際用量／8192上限是否足夠、目錄完整性與頁碼辨識；未驗證100–200份報告成本或效能，未執行整批。目錄JSON不自動用於標籤邊界判定。

## 交接時核對既有完成紀錄（2026-10-21）

後續整理交接文件時發現已有`Output/json/2025Q4_2330_Financial_Report/toc_20261021_195003_434745/`。以現存manifest為依據：模型gemini-3.1-flash-lite、status=extracted_needs_review、stage=complete，promptTokenCount=1371、candidatesTokenCount=1998、totalTokenCount=3369。這不是整理時新呼叫的API，也不把既有紀錄當作本次重新驗證傳輸。

本次讀取該run的2025_2330_toc.json，以validate_toc重新檢查結構通過，共26項；第2頁toc、第3頁not_toc，issues空白。這筆紀錄顯示已有一次回覆完成、未因8192上限截斷，但仍待逐項對照原PDF核對文字／父子關係／頁碼／附註編號，不能宣稱整批額度或辨識品質通過。此追加紀錄取代先前「尚無真實服務完成結果」的現況解讀，保留先前開發時未呼叫服務的歷史事實。
