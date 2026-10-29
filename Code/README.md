# 完整財報 PDF 轉 Markdown

## 2026-10-30：chunk首行改為脈絡路徑

第四階段兩種切法、文字及表格皆套用：full為「目錄小標 > 小標題各層 > 說明」，description只有說明原文（去掉年度片段），body不加首行。不再印Sub_Section／Note_Title／說明欄位名，不加「本表為」或推定的新敘述。標題移除開頭中文／阿拉伯／字母列表編號，保留IFRS、金額與有意義的數字；metadata、來源正文、說明原欄位不變。相鄰同名標題及與標題完全相同的說明省略重複項目；沒有值不留分隔符。
新chunk含content_prefix_format=path-v1，原始切法規則1.5／父子5.7，確保新舊索引隔離。舊chunk沒有格式標記時，仍依舊首行驗證與建庫，不悄悄改變舊embedding。需重新跑第四、第五階段才影響既有資料。


## 2026-10-29：第四階段每個chunk補齊檔案年度（更正）

使用者更正並確認：不是只有years為空才補，而是只要years不含檔案年度就追加，保留原有年度並排序去重。例如2024_2330的[2022,2023]變成[2022,2023,2024]；已含2024不重複新增。original及parent_child的文字、表格、子項及父項均適用。僅修改metadata，不新增content／embedding前綴；表頭與前置標籤仍照既有規則判讀，再追加檔案年度。補入值代表財報檔案年度，不宣稱是表內期間。

核心為table_metadata.with_document_year，由hierarchical.make_item共用；year_sources保留原來源，原本無年度時記document_year_fallback，有其他年度但缺檔案年度時記document_year_included。parent_child規則5.6、original規則1.4，schema不變。只改程式，不重跑既有chunk或索引；常駐網站重新載入後，新執行第四階段才套用。驗證範圍：檔案年度存在／缺少／重複、保留表頭年度、兩種切法與前處理契約，以及實際2024台積電三種切法的正文與來源不變。


## 2026-10-28：問答題庫與輸出更新

統一網站的單題／Excel查詢新增持久問題向量題庫及三類分題輸出，實作位於Code_2，規則與驗證見[Code_2/QUESTION_BANK.md](../Code_2/QUESTION_BANK.md)。Code共用Settings新增question_bank_path；PDF至chunk及建庫向量未改。原始切法查詢不再提供標題父項召回，跨頁父表仍必回。

## 2026-10-27：API金鑰介面簡化為三個用途

依使用者要求，統一網站與Code共用的API設定頁只保留三區：Voyage embedding（voyage-finance-2）、Voyage rerank（沿用已設定模型，預設rerank-3-lite）、LLM（Gemini／OpenAI GPT二選一，明確指定模型ID）。各區只有一個金鑰輸入及儲存／更新、刪除按鈕；移除自訂名稱、共用金鑰選單、模型設定清單及已保存金鑰清單。BGE本機功能仍不需要API金鑰。

manage新增save-slot／delete-slot；api_profiles.json可選slots欄位記錄各用途目前設定或明確清空狀態，不保存密鑰。金鑰仍只存.env。留空保存同服務商現有金鑰；LLM切換服務商時必須輸入對應金鑰。儲存後同用途只顯示目前設定，建庫與問答選單同步更新；刪除已清空的用途不會自動復活舊預設。舊設定保留相容，不自動大量刪除；既有金鑰可直接顯示已設定狀態而不回傳秘密。若舊Voyage金鑰同時供embedding及rerank使用，清除單一用途時保留另一用途仍需的金鑰。外部環境提供的金鑰不假稱能從介面刪除。寫入失敗恢復原.env內容。

驗證：29項暫存假金鑰／本機HTTP測試及Node介面契約檢查通過，含用途相容、替換／保留金鑰、服務商切換、共用舊金鑰刪除、秘密不進回應／JSON與失敗復原。未用真實key呼叫模型，未改現有索引。

## 2026-10-27：批次建立獨立索引（已實作）

第五階段「索引操作」新增batch／批次建立獨立索引。一次選多份chunk JSON，輸入索引名稱前綴並選一個BGE或Voyage設定。先預檢全部來源，按plan_key（前處理版本、來源規則、完整chunking參數及文字／表格embedding_context_modes）分組，依組順序處理；同組不同doc_id共用索引，同組重複doc_id在載入模型前拒絕。支援九組或27組，不會合併不同脈絡向量。

每組建立獨立隨機experiment ID，顯示名稱為前綴＋G序號＋切法／字數＋文字／表格模式；總長80字時縮短前綴。每次批次執行均為新索引，重跑不自動接續或覆寫舊索引。模型provider在本次工作只建立一次，各組依序使用。保留單一新建與加入既有索引功能；check_only只檢查、不建立集合或匯入紀錄。來源失敗列明錯誤並繼續有效來源，沒有成功文件的集合不當成已提交索引。

介面會顯示預檢進度、目前索引組／總組數、逐份結果及每組完成／部分失敗／未全部執行狀態。原本文件邊界停止功能沿用，停止後保留已提交資料，後續組不執行。選batch時顯示全部切法來源，仍可篩選切法後只勾九份。CLI：Code/vector.py --batch-index-prefix 名稱 --backend bge --source <相對chunk路徑>（可重複指定source）。Voyage仍須明確啟用API。

驗證：34項相關Python測試及Node介面契約檢查通過，使用假向量、暫存Chroma及本機HTTP；涵蓋27組／28份分組、provider僅載入一次、同組文件共用索引、重複防護、API接線、只檢查、錯誤與停止。既有2024年的27份JSON亦核對為27個不同設定。未呼叫真實模型或重建現有索引。

## 2026-10-27：第四階段選擇文字／表格的embedding脈絡（最新）

本輪驗證：90項相關測試通過（49項模式／切分回歸，41項輸出／Record／向量庫／網站測試）。2025台積電tagged在250字門檻下，original 202個chunk、parent_child 269個chunk，分別測full/full、body/full、description/body三組，切分區間一致且prepared契約通過；僅記憶體執行，來源未變。網站重啟後已核對第四階段兩個模式選單；未執行付費embedding或重建既有索引。

使用者更正：設定位於第四階段切chunk，original及parent_child均支援。文字與表格各自選body（純正文）、description（正文＋說明）、full（正文＋Sub_Section＋Note_Title＋說明），預設full。完整模式不額外加入Main_Section、年度或股號；原正文及表頭中的年度保留。說明沿用table_context／directions，去掉說明年度並去重。metadata仍完整保存，切分邊界及字數算法不變。

每份chunk JSON新增embedding_context_modes記錄兩項選擇；搜尋chunk及父項各有embedding_context_mode，content_prefix依模式生成，正文保留來源映射。新輸出檔名例如2025_2330_chunk_250_text-body_table-full.json，Markdown及Record同步命名。舊版檔名及沒有模式的新舊schema資料繼續相容；既有Output及索引不自動更動。

第五階段移除脈絡選單，直接沿用chunk設定；不接受建庫請求覆寫。prepare_document、prepared驗證及索引簽章保存模式，加入其他模式索引會拒絕。索引清單顯示文字／表格模式供檢索時選擇。檢索當下無法改變既有向量；要改實驗設定，先重新產生chunk，再建立獨立索引。原本任意欄位角色選擇器仍維持移除。

入口：前處理→第四階段切chunk→文字／表格chunk的embedding脈絡。CLI：Code/main.py --chunk-batch <批次> --text-embedding-mode body|description|full --table-embedding-mode body|description|full。核心為content_context.py及embedding/context_modes.py；未呼叫付費模型或重建既有索引。

## 2026-10-27：移除網頁欄位選擇器

第五階段不再顯示或接受「查看／選擇欄位標籤」；建庫固定讀取`Code/config/embedding_fields.txt`，欄位用途仍由此設定檔決定，網頁不再傳送動態欄位規則。移除欄位選項API及其前端腳本；既有索引與其向量內容未變更。若要調整欄位用途，需修改專案設定檔後建立相應新索引。

## 2026-10-27：新建命名索引與pdf-inspector選項

補充本輪完整實檔驗證：2024台積電目錄維持Docling後，查核P4～P7、附註P16～P124共113頁，98.476秒成功輸出，P4／P7回退Docling，來源SHA256不變。完整raw再經processed→tagged→original700（207chunk／14父項）、parent_child250（258／42）、parent_child700（220／33）及建庫前處理全部通過。這是結構／契約驗證，沒有全表逐格人工驗收或真實embedding／LLM。可讀紀錄：Output/pdf_parser_comparison/full_stage1_20261027_122001/validation.md。第一次目錄錯配13頁的產物另存品質失敗紀錄，不當成成功驗收。另12項問答模式及pip check通過，瀏覽器已核對新選單與名稱欄。

第五階段先選「新建索引」、輸入1～80字名稱，再選同一模型／切法／字數的chunk JSON，按「新建索引並開始建庫」。每次新建有獨立隨機ID，相同名稱／設定也不會合併。名稱只供顯示，不當檔名或Chroma集合名稱。若要補文件，改選「加入既有索引」、更新清單並選集合；完整設定須符合，相同檔案不重算embedding，不同版本不覆寫。新索引要至少成功提交一份財報才出現在已提交清單；失敗不假列成功。混合不同切法、字數或處理版本須分開建立。舊集合不遷移、不改名。CLI新增`Code/vector.py --index-name 名稱`或`--collection financial_...`；未指定則保留舊自動分組相容行為，--check-only不建立索引。

第一階段新增「PDF解析器」選單，預設Docling，或選pdf-inspector試驗模式。後者整頁抽原生文字與|表格，目錄第2～3頁先沿用Docling結構解析，其餘使用`extract_pages_markdown`一次快取原PDF各頁；沿用既有查核／附註選頁與原實體頁序，未選內容不寫raw。當頁needs_ocr或無文字時，OCR勾選才回退既有Docling；OCR未勾選則明確失敗，不輸出空白成功。回退頁可含HTML，後續兩種格式並存支援。已有非空但錯欄／合列的結果不會自動被辨識修正，必須核對。Record的inspector.page_provenance列實際引擎／回退原因；原生階段執行緒數不可由既有Docling設定推定，cpu_threads留未知、fallback_cpu_threads記Docling設定。

依賴鎖定`pdf-inspector==1.25.2`，已加入requirements.txt與requirements.pdf.lock並安裝於既有.venv_pdf。不用另外安裝inspector自己的OCR模型／ONNX Runtime；回退沿用現有Docling／MinerU整合。CLI可用`Code/main.py --pdf-parser inspector --ocr --pdf <來源PDF>`；--no-export仍集中停用檢查產物。移除此選項需同步調整inspector_pdf.py、create_converter／convert_pdf分支、Settings／request_settings與GUI／CLI選單；不影響預設Docling。原試驗執行器及測試產物仍獨立保留，不是正式資料依賴。

驗證：原PDF第40／57／71頁經processed→tagged→original／parent_child250→prepare共6組通過，P40標題對應正確；inspector本身的合列／錯序仍保留。本輪已另做上述單份完整選頁與OCR回退；未呼叫真實embedding或LLM、未修改原PDF／舊產物／索引。局部47項索引與網站、22項PDF與管線測試及5組Node檢查通過（Python組別有重疊）。中間產物見Output/pdf_parser_comparison/integration_20261027_120805，實驗寫檔仍由export_enabled集中控制。

## 2026-10-27：獨立PDF解析比較（已實測，正式流程未替換）

依使用者要求，比較既有Docling 2.140.0與pdf-inspector 1.25.2，抽2024台積電財報PDF實體頁15、35、36、37、39、40、41、57、64、70、71、124共12頁。Docling沿用核心converter，CPU8／批次1／accurate／HTML／OCR啟用，僅使用離線快取；inspector原生文字每頁三次。新報告與逐頁輸出：Output/pdf_parser_comparison/comparison_20261027_111815/report.md及measurements.json。P40、57、71另人工對照原PDF渲染，不把其他頁的輸出成功當作品質驗收。

inspector改善P40與57章節被吃進表格，但有明細／小計合在同格、P71表頭錯序；P15輸出空白，逐頁API明列needs_ocr=True，需回退。Docling本輪重現P40、57合表，P39另有異常2×1023表格網格及文字cell丟棄警告。inspector各頁三次中位數相加32.179秒，Docling逐頁單次共186.607秒、另匯入與converter建立39.394秒；樣本與OCR／時間邊界不同，未宣稱等品質加速倍數、200份效能或答案準確率。

EXPERIMENT_ONLY：.runtime/pdf_inspector_trial/run_compare.py是獨立執行器，沒有正式呼叫位置；不執行即停用。公開wheel只下載／安裝至該目錄，未修改正式requirements／環境，未啟用inspector OCR或送財報至外部API。原PDF與舊raw已核對SHA256不變，未重建chunk或索引、未改網站。沒有新增正式流程／混合回退規則；後續替換待另確認。

## 2026-10-27：表格民國年度下限100年

使用者確認表格可採113年度、113年12月31日、112年等明列年度，民國未滿100年不列入（100可採，90／99不可）。ROC_YEAR_RANGE集中改為100～288，西元1900～2199與其他格式維持。此限制套用表頭及表格前置標籤的共用年度解析器；小於100不轉換、不補足，1至3年等短期年限不再成為1912／1914。表頭無有效年度時繼續讀範圍內前置標籤，最後才依既有規則使用文件年度；不調整表頭優先順序、不改一般文字年度。

第四階段parent_child規則更新bounded-parent-child/5.4、original更新content-end-original/1.2，schema不變。新規則與舊索引隔離；舊chunk／向量不自動修正。套用既有文件需重跑第四階段，並於第五階段選新版JSON建庫，尚未替使用者執行或重建索引；不需重新OCR。原始chunk_id標註／表格文字命中分析仍暫停。

本次驗證：年度優先序10、parent_child切分15、original切分6、表格父子6、QA模式12，共49項測試通過。2024台積電既有c00216表格在記憶體重算，由[1912,1914,1916]修正為[2024]，來源為preceding_table_year的113年12月31日；原檔位元組與既有向量未改寫，未執行OCR、embedding或外部API。

## 2026-10-27：建庫完成目前／指定文件後停止（已實作，現行批次保留舊程序）

使用者要求正在執行的2021至2025建庫只做到2024，不建2025，並在向量資料庫頁增加結束工作。新工作由App.start建立隨機工作ID與.runtime/vector_jobs下的核心控制檔（路徑集中Code/config/runtime.py）；可選「完成目前文件後停止」或「完成指定文件後停止」。停止請求只在文件邊界讀取，已開始的文件仍完成所有embedding及持久提交，不kill程序、不刪除向量，不啟動後續文件。工作結束回stopped、已處理數與skipped清單，不把未執行文件列成失敗或成功；控制檔於程序退出後清理。此功能是正式操作能力，不是EXPERIMENT_ONLY。

程式：Code/functions/embedding/job_control.py、direct.py、Code/vector.py、web_ui/server.py／bridge.py／index.html及兩種Settings的vector_job_dir。網頁停止操作沿用既有token與同來源驗證，工作仍busy至目前文件結束；停止按鈕不走前四階段的立即取消。已開始的舊版工作沒有控制ID，介面會明示需本批完成後重新啟動網站，不擅自中斷持久索引。

本次現行工作於00:55啟動、沒有控制通道。唯讀核對當時2021已提交、正在2022且2025未開始；唯一2025_2330_chunk_700.json位於Financial_chunk_20261027_00-29-48/parent_child。依使用者要求暫時改名為.json.skip-current-build-ed4eb769fec54290a5d2d1c6c6725cc9，原始PDF與檔案位元組不變；預檢後核心會在讀2025來源時失敗，先於模型呼叫，故本次舊工作可能顯示2025來源讀取失敗，不能把它描述成新控制的stopped事件。未刪除任何索引。

一次性還原助手PID33528只等待該次建庫PID26728／7412及原建立時間結束，再核對SHA256 f0864b8f53682dcc9d1865a9b989eb20512b1fb03bb51b046e88dd13883d3285，且原路徑不存在才還原；不覆寫檔案。助手與狀態記錄在系統暫存目錄，manifest為financial_rag_skip_ed4eb769fec54290a5d2d1c6c6725cc9.json。若需人工核對，先讀manifest與程序狀態，確認本批已結束後才還原；不要在本批仍執行時把2025放回原名稱。本次尚未宣稱真實2024已提交或助手已還原。

驗證：安全停止5、建庫9、既有立即取消2共16項，以及第五階段HTTP6、前處理HTTP7共13項，合計29項Python測試通過；Node介面實際停止位置請求及資料庫樹狀回歸通過。暫存Chroma與假向量驗證建到2024只提交4份、2025未呼叫embedding、目前文件完整提交、開始前停止不載入模型／不建立向量庫；初次控制檔原子更名被沙箱拒絕，在允許暫存檔原子操作及localhost後通過。Code_2完整158項回歸通過。沒有替使用者重建索引、啟動題目集或呼叫付費API；使用者本來執行中的建庫持續運作。

## 2026-10-27：第四階段新檔名與常駐程序版本不一致（已處理）

網站8765的內部程序從2026-10-26 15:28啟動，早於當晚新增_chunk_字數檔名。舊程序已匯入chunk_run_paths，仍以舊檔名規劃OutputSession白名單；新worker載入新版並要求新後綴，因此被拒絕，2021至2025五份均回ValueError且該批Output沒有成功產物／Record。這不是財報文字或切分上限造成的核心失敗。未修改核心來繞過輸出授權。

確認主網站及工作區皆閒置後，已透過正式shutdown API關閉，再以隱藏窗口啟動同一8765網站。health正常、工作區idle；舊55074網址當時未回應。2021至2025現有tagged在記憶體parent_child700驗證全部通過（271、280、278、279、236個chunk），來源不改寫；未替使用者輸出整批或建庫。

新增test_chunk_mode_io中的網頁execute與OutputSession／output_observer串接驗證，700及1000後綴JSON、Markdown與Record皆能通過實際白名單寫入暫存目錄；該模組5項測試通過。使用者可重新執行第四階段。修改檔名後常駐程序需重啟，重新整理頁面不會重載Python匯入模組。

## 2026-10-26：parent_child檔名字數後綴與索引隔離（最新）

使用者要求父子切法檔名附設定字數。第四階段parent_child輸出2025_2330_chunk_700.json／.md；設定1000則為_chunk_1000.json／.md。對應Record為Record/2025_2330_700_reocrd，不同字數可在同批次並存。original檔名、doc_id及chunk_id格式不變，舊產物不改名。

第五階段網站清單、直接建庫及舊前處理相容入口支援新舊檔名；新字數後綴必須與JSON的parent_child／recursive_threshold相符，錯配於來源預檢失敗，不呼叫模型。以JSON實際設定建立索引，不靠改名變更切法。既有索引簽章已含chunking及來源規則，700與1000使用不同Chroma collection，與模型／模式隔離共同作用；底層仍可共用同模型的Chroma儲存目錄，檢索只讀所選集合，不合併兩種字數。資料庫與問答選單既有參數顯示可辨識字數。

舊Code_2 prepared實驗入口同步接受帶字數來源並分開保存其檢查產物／Record；新第五階段仍只在記憶體前處理，不新增prepared檔。實作為Code/functions/chunking/filenames.py、experiments/export_output.py、web_ui/catalog.py、embedding/direct.py、embedding/load_prepared.py及Code_2/functions/embedding/batch.py。

本輪80項相關Python測試通過：模式IO／字數共存、暫存Chroma建庫與隔離、舊前處理、父項、第五階段HTTP、父子切分及QA模式／選單。HTTP初次受沙箱WinError10013限制，允許本機測試後5項全通過。700／1000同doc_id分集合且各自檢索、錯後綴不呼叫模型均以暫存庫及假向量驗證；舊檔仍可建庫。未呼叫真實API或模型、未改寫Output或操作使用者索引。

目前已開啟的網站需閒置後關閉服務，重新由start-web.cmd開啟以載入新的來源清單程式（僅重整分頁無法更新常駐內部程序）。接著重跑第四階段產生新檔名，並用第五階段選取所需字數版本建庫；既有檔案與索引保留。

## 2026-10-26：第一階段表格改回HTML（最新）

使用者指定第一階段表格改回HTML。Code/config/settings.py的table_format恢復html，沿用既有HTMLTableSerializer，保留rowspan／colspan、表題、表下注與財務符號；CPU執行緒8、批次1及accurate表格辨識不變。此節取代先前預設Markdown管線表格的決定，管線表格讀取能力仍保留。

再次確認第四階段original及parent_child的content_start／content_end僅是控制邊界，不寫入chunk或父項正文，無須另改解析規則。網頁下一次第一階段工作啟動新worker即讀取HTML設定；執行中工作不切換，既有raw與後續產物不改寫。要取得HTML來源需自行重跑所需文件第一階段。

本次test_markdown與test_parent_child_v5共21項：20通過、1失敗；HTML合併欄位、財務符號、表下注及父子切分測試通過。失敗為舊test_export_disabled_returns_memory_without_output使用三頁模擬文件，其第2頁無文字，未配合目前先讀目錄的新流程，因而於read_local_toc失敗；未擴大修改此舊測試或目錄處理。另直接驗證預設html／CPU8／批次1及兩模式chunk與父項不含content邊界標籤。沒有重跑真實OCR或PDF辨識，沒有API、建庫或改寫使用者Output。

## 2026-10-26：parent_child先合併相鄰content（最新）

使用者確認：同一完整HD標題路徑（含標題出現位置）內，相鄰content先全部合併，再依recursive_threshold（預設700個非空白正文字符）判斷切分；年度／說明標籤不阻斷合併。遇新HD標題、表格、###特殊群組或文件結尾先收尾，不跨不同標題。既有會計師查核報告例外保留。

合併後不超700字為一個普通chunk；超過時沿用N/k無條件捨去目標、目標後空行優先、中文句點次之、最後按字數的切分規則，建立完整content_parent。檢索命中任一子項必定返回完整內文父項，與可選heading_parent分開。表格獨立、跨頁table_parent、###整組保留及original模式均沿用原規則。年度與說明metadata合併保留來源、首行去年度／去重與最後空行清理不變；不把控制標籤寫入正文。

新規則bounded-parent-child/5.3，schema仍為financial-chunks/5.0；來源規則參與既有索引簽章，與舊5.2隔離。既有Output及索引不改寫。網頁下一次第四階段工作會啟動新worker載入程式；選parent_child重跑所需tagged，若要檢索新切法，再由第五階段建新版索引。已啟動的工作或舊CLI常駐程序不熱切換。

本輪58項Code切分／來源／模式IO／首行／管線表測試及56項Code_2父項／QA／模式／選單測試通過，共114項。既有2025_2330兩版tagged只讀記憶體驗證：05-46來源parent_child為236個chunk（4個content_parent、11個table_parent、40個heading_parent），13-18來源為65個chunk（1個content_parent、1個table_parent、14個heading_parent）。兩來源雙模式皆通過prepared、逐字來源重建與最後空行檢查；所有強制父項子項逐一模擬命中皆返回對應父項。05-46來源IASB小標題原201字及356字已合併為557字一塊。沒有重寫來源或Output、OCR、真實embedding、API呼叫或使用者索引操作；不能視為真實問答品質驗收。

## 2026-10-26：第一階段預設輸出Markdown管線表格（最新）

使用者要求第一階段表格直接輸出「|」Markdown，不再預設HTML。Code/config/settings.py的table_format改為markdown，沿用已存在的Docling MarkdownTableSerializer及表題／表下注序列化；CPU執行緒仍為8、批次大小1、table_mode仍為accurate，沒有關閉或更換表格結構辨識。含合併儲存格時保留既有展平警告，不能把改輸出格式宣稱為已加速或已通過真實財報辨識品質驗收。

本次5項既有管線表格測試通過，並以合成資料確認original／parent_child可串接至prepared、表頭年度與負值保留；未執行真實OCR／表格辨識，沒有速度量測。

既有raw、processed、tagged、chunk及索引不改寫。後續來源仍可讀取原HTML或管線表格。下次第一階段新工作會由獨立worker讀取新設定，執行中的工作不切換格式；若使用舊版獨立CLI常駐程序，重新啟動後讀取新設定。


## 2026-10-26：第一階段運算設定更新

使用者指定PDF→Markdown的CPU執行緒改為8、批次大小改為1，設定為Code/config/settings.py的pdf_cpu_threads與pdf_batch_size。只改第一階段；OCR、版面及表格管線沿用同一批次設定，不更改第五階段embedding設定。已讀回確認設定值，未執行PDF轉換；已啟動的網站需重新啟動才會載入新Settings，執行中的工作仍使用原先設定。


## 2026-10-26：original僅表格與###保留父子例外（最新）

使用者再次確認：original一般文字不建立任何父子關係，包括不建立可選的heading_parent。本節取代上一節original沿用標題父項的敘述。一般文字仍在同一hd2累積至700字後的content_end切分，長content整段保留；補標題的content首行與metadata照常保留，補標題不代表建立標題父項。

表格仍獨立chunk，跨頁表格建立強制table_parent；###前文／整組條列沿用其既有特殊父子規則，不表示所有表格或所有###一定建立父項。parent_child模式不變，保留其內文、表格及可選標題父項。新original規則content-end-original/1.1與先前1.0隔離；舊1.0資料及既有索引保留原關係與可選召回，新1.1在網頁／CLI不提供標題父項召回。

本次50項切分／輸出與55項索引／QA／選單測試，共105項Python測試及1項Node契約通過。2025台積電既有tagged記憶體驗證取得29個chunk、1個table_parent、0個heading_parent，prepared驗證通過；無模型／API呼叫，未改寫既有Output或索引。需重跑所選文件第四階段才會套用1.1，檢索需另用第五階段建立新版索引。


## 2026-10-26：original改為content_end累積切分（最新）

使用者已確認original保留hd2邊界，忽略hd3以下標題作為一般文字切點。同一hd2內依完整content累積，非空白正文達recursive_threshold（預設700）後在該content_end切開；例如400＋400為800一塊，單一1000字content保留1000字，不因超長建立內文父子層。未達門檻遇新hd2、表格、###特殊群組或文件結束時收尾，不跨hd2補足字數。生成首行及空白不納入門檻，表格／條列例外沿用既有規則。

兩模式共用嚴格content/table解析、表格單獨chunk、跨頁table_parent、###前文與整組條列、標題父項、井號清理、Sub_Section／Note_Title／說明首行、來源驗證及最後空行清理。original合併低層標題時保存本塊涉及的全部標題路徑，不只保留第一個；可選標題父項與強制表格父項保持分離。這是使用者所稱「其他規則都一樣」，取代original舊版HD遞迴拆分、說明綁成超大父項及沒有首行的行為。

新版original為financial-chunks/5.0，規則content-end-original/1.0；parent_child仍為5.0／bounded-parent-child/5.2。模式及規則參與索引簽章，兩模式分集合，舊版4.0／舊索引繼續可讀，不自動改寫。prepared驗證保留source_rule_version；網頁與CLI均能辨識新original的標題父項選項。第四階段兩模式都只顯示有效的一般字數門檻，Parent／Child舊參數欄位保留於schema供相容，但不再影響新切法。

本輪50項切分／來源／模式輸出測試、Code_2全套146項及Code HTTP12項通過，共208項Python測試；4項Node畫面契約通過。2024與2025台積電既有tagged各做雙模式唯讀記憶體驗證，首行、來源重建、空行與第五階段prepared契約均通過。這不是重新OCR、真實embedding或回答品質驗收；沒有重寫使用者Output、建庫、刪索引或呼叫外部API。重跑所選文件第四階段才會產生新格式，要檢索新版需再用第五階段建新索引。


## 2026-10-26：chunk首行移除年度、股票代號與main_section（最新）

使用者要求這三項不再加入content的生成首行。新版parent_child首行只保留「Sub_Section｜Note_Title｜說明」，空欄省略；若三者皆空，不產生空白首行。years、文件股票識別及main_section等metadata繼續保存，正文與表頭原本出現的年度、股票代號及文字不刪除。說明原有去年度、去重與來源規則維持。original模式不變。

規則更新為bounded-parent-child/5.2，schema仍為financial-chunks/5.0；新索引依source_rule_version與舊版隔離。content_body以來源欄位重算驗證新／舊首行，仍可讀取先前含年度、股票代號及大標的產物，不改寫歷史Output／向量。第五階段embedding_context及Code_2證據對有content_prefix的chunk不另補章節，因此不重新加入這三項。

程式為Code/functions/content_context.py與chunking/parent_child.py。新設定需重新執行所需文件的第四階段，再由第五階段建立新索引；本次沒有重寫既有Output、重建或刪除索引，沒有模型／API呼叫。41項局部測試通過，涵蓋新首行、metadata保留、父子及來源完整性、舊首行相容與下游不重加。


## 統一網站（2026-10-26，取代歷史雙網站入口）

現在雙擊專案根目錄 `start-web.cmd` 即可，也可沿用 `Code/start-web.cmd` 或 `Code_2/start_gui.cmd`；都開啟同一個以Code_2為主的本機網站。預設網址 `http://127.0.0.1:8765/`。命令列仍可用 `Code/.venv/Scripts/python.exe -X utf8 Code_2/gui.py --open-browser`，或加 `--port` 選其他埠。已啟動相同網站時，啟動器重用既有網站；若被其他程式占用則回報，不停止其他程式。

側邊選單：

| 選單 | 功能 |
| --- | --- |
| 前處理 | 原第一至第四階段，保留檔案／資料夾選取、OCR與切塊參數、取消、逐檔時間及結果。 |
| 向量資料庫 | 第五階段從chunk JSON建庫；下方沿用模型→切法→集合→財報勾選、篩選、內容瀏覽、刪除預覽與完整集合移除。 |
| API 金鑰 | 同頁新增／共用／刪除key及模型設定；換頁清空尚未保存的key輸入。金鑰不回顯、不呼叫服務驗證。 |
| 問答系統 | 問題在上方；詳細設定可展開，三模式與50／10預設保留；引用可展開文件、PDF實體頁序及證據。 |
| 執行紀錄 | 原問答Markdown／JSON下載與最近建庫紀錄。 |

只需保留這一個網站服務。問答、前處理、建庫、資料庫操作與金鑰修改在同站互斥；忙碌回409，不排隊、不自行重試。關閉分頁不取消工作。前四階段仍可在工作面板取消，第五階段與問答等安全結束。右上「關閉服務」僅閒置可用；若直接關閉啟動程序，程式會等待已啟動工作，請勿用工作管理員強制終止。此互斥不控制另外手動啟動的CLI。

實作邊界：

- `Code_2/functions/web/server.py`：唯一HTTP入口、固定同來源資產、權杖、互斥與Windows獨占連接埠。`/api/health`供啟動器辨認既有網站，不含設定或key。
- `workspace.py`：延後啟動Code/.venv_pdf內的內部JSON管道；`Code/functions/web_ui/bridge.py`只串接既有App、catalog及vector.py，沒有另外開HTTP站。失去管道時回報未知狀態並阻擋新工作，不自動重啟／重跑。
- `workspace_page.py`：從原Code工作面板抽出固定HTML／CSS／JS資產，同來源嵌入統一版型；`static/workspace.js`及`.css`只處理頁面切換、高度、狀態與樣式。兩邊的頂層config/functions不混匯。
- `Code/functions/web_ui/api-settings.js`及`.html`繼續共用，支援原獨立對話框與新網站內頁。沒有新增密鑰儲存或API供應商。
- 問答、建庫、索引簽章、實驗輸出與取消清理核心未替換。原Code HTTP模組留供相容及測試，但啟動器不再啟動第二個網站。

驗證：本輪39項Python測試及5項Node契約通過。Python指令為Code/.venv執行 `-m unittest Code_2.tests.test_unified_web Code_2.tests.test_web Code.tests.test_api_settings`（27項），Code/.venv_pdf執行 `-m unittest Code.tests.test_web_ui Code.tests.test_vector_web`（12項）。Node執行Code_2/tests/test_query_display.js、test_heading_parent_ui.js及Code/tests/test_api_form.cjs、test_ui_controls.js、test_database_tree.js。內部管道只做真實來源清單及閒置狀態讀取，其他工作／API用合成測試；瀏覽器核對版型與功能切換。未執行真實模型、OCR、付費API、建庫或刪除真實資料；結果顯示驗證不代表回答品質已完成驗收。


## 樹狀資料庫清單與損壞集合移除（2026-10-26）

第五階段下方「資料庫管理」直接列「模型→切法→索引集合→財報」，可勾單份、集合、切法或模型群組，顯示半選及份數；不同集合同名財報各自計算。可展開／收合，並篩選doc_id、股票及內容年度。群組選取只作用目前篩選清單；「更新清單」會清除篩選與勾選。清單以提交清冊建立，因此受損集合也看得到；股票／內容年度篩選及查看內容仍需能讀HNSW。

正常刪單份：勾選→「預覽刪除所選財報」→核對各集合及向量筆數→「確認刪除所選財報」。勾選或篩選變更即作廢舊預覽。跨集合逐一刪除，中途失敗明示已完成範圍，不自動回復。

HNSW損壞時：先清除篩選，勾選完整集合→「預覽移除整個集合」→核對集合及其全部財報→「確認移除整個集合」。此操作不先讀向量，使用Chroma原生集合刪除；預覽向量數只依清冊，亦會移除集合內未提交向量。原PDF、Output、其他集合與歷史匯入嘗試保留；無法透過本介面還原。只勾部分財報時不允許整組移除。集合沒有已提交清冊、或SQLite本身不可讀，仍會明確拒絕，不提供任意磁碟刪除。

移除中失敗會保留collection_deletions及deletions狀態，阻擋新建庫及召回；清單仍顯示待完成集合，重新勾整組預覽後重試。原生集合已刪但清冊尚未清完也可重試。不需要刪整個VectorStore資料夾。模組為embedding/collection_management.py，frontend為web_ui/database.js，沿用既有同來源、token、建庫互斥及預覽快照檢查。重啟Code介面載入新後端，Code_2亦建議重啟載入共用待移除狀態處理。詳見maintenance/database_tree_validation.md。


## 每份檔案的執行時間與設定（2026-10-26）

重啟Code/start-web.cmd並重新整理後，第一至第五階段每個檔案完成或失敗，結果都會顯示耗時、CPU執行緒設定與批次大小。第一階段保留OCR速度及細部計時，顯示PDF管線設定；第二至四階段沒有模型平行／批次參數，標不適用。第五階段依本次模型：BGE顯示cpu_threads／bge_batch_size，Voyage執行緒不適用、批次取voyage_batch_size。批次是每次上限，不代表最後一批或受token限制的請求一定用滿；失敗紀錄中的設定不表示該階段已執行成功。

第一階段Record既有settings保存PDF參數；第二至四階段Record及第五階段ingestion.sqlite3的attempt新增runtime_config。介面使用既有elapsed_seconds，外層例外補單檔計時；舊資料缺設定／時間顯示未取得。時間不包含先前階段，也不是單獨模型encode的精確耗時。這些操作紀錄不加入chunk的content或embedding_text，因此不增加embedding token。實作為web_ui/worker.py、index.html、embedding/direct.py及第二至四階段批次Record。


## 專案搬移與動態路徑（2026-10-26）

目前專案位置為D:/Financial_RAG。核心Settings以設定檔所在位置推導project_root，Output、VectorStore與快取依此組合，不必修改Python中的磁碟代號。start-web.cmd使用自身所在目錄定位，兩環境activate.bat亦改為動態定位。可從檔案總管開啟Code/start-web.cmd；命令列套件操作優先用對應環境的python -m pip。

本次搬移已更新既有環境的生成式工具啟動器與pyvenv.cfg；這些Python環境內部仍有絕對路徑，未承諾未來再搬移時可完全免調整。歷史Output/Record保存當時來源路徑，不批次改寫。舊受損Chroma索引需另行恢復／重建，僅搬移無法補回缺檔。完整核對見maintenance/relocation_20261026.md。


## 第四階段空行清理（2026-10-26）

original及parent_child都在切分完成後移除content正文空白行，包括僅有空格、Tab的行；非空行內空白及換行保留。切分時仍可使用空行作邊界。完整父項同步重建，source_spans維持來源追溯，文件removed_blank_line_spans記錄移除位置。Markdown各chunk之間的顯示間隔不屬於正文。清理模組functions/chunking/blank_lines.py；目前規則為bounded-parent-child/5.1／hierarchical-semantic-chunks/4.1-compact，schema維持5.0／4.0。重啟Code介面後重新執行第四階段才會套用，舊Output及索引不改寫。


## 第四階段parent_child新規則5.0（目前版本）

本節取代下方「700字新切法、表格獨立、###整組、標題父項尚未完成」及parent_child沿用1500／300裝箱的舊狀態。重新啟動Code/start-web.cmd，第四階段選parent_child，進階設定調整一般內文字數上限（預設700）；Parent／Child舊參數不適用新版所以收起。original維持4.0原切法與參數。

新版在HD階層內依content_start／content_end及table邊界處理：一般內文超限以floor(N/k)計算子項目標，先找目標後上限內可用的空行、再找中文句點，最後按字數切；末段超限會增加分項數，半形句點不作語意切點。HTML實體不切半。完整正文作content_parent，搜尋子項固定帶回完整正文。查核報告沿用一原##範圍一塊；###前段分項，後續編碼項目整組一個Child，使用者明確指定即使超過700仍保留並記錄list_group_exceeds_limit_by_design。

每個表格邊界獨立；接次頁／承前頁合併的邏輯表按可靠PDF實體Page分子項，完整表作table_parent，命中任何頁子項固定讀回完整表。表格年度及說明仍依原規則，所有頁沿用完整表的判定；不因頁面缺少表頭而回退到錯誤文件年。若頁界不可靠，保留完整內容並在issues列unresolved_table_page_boundary，未假造頁面或切開HTML儲存格。

標題分組取Note_Title去掉最後一層後的真實路徑，無可比較前綴時用Sub_Section；來源位置不同的同名標題不混組。有至少兩個原始單位才另外建立heading_parent。此類父項可含文字與表格，只有非向量heading_parent允許content_type=mixed，搜尋chunks仍只為text／table。階段四只保存關聯，不提供檢索召回設定。

JSON為financial-chunks/5.0、規則bounded-parent-child/5.0。每個項目新增node_type（chunk／content_parent／table_parent／heading_parent）、parent_relation（content／table／null）及heading_parent_id。parent_id與part_index仍指向必回完整內文／表格父項；heading_parent_id獨立表示可選標題父項。chunks做向量，parents不做向量；Markdown列出各搜尋chunk的兩種關係，完整父項在JSON的parents中。

content首行沿用年度、股票代號、章節及去年度片段的說明。正文移除第二階段結構井號，HTML／程式碼字面井號保留，來源位置排除生成首行及移除的標記；文件removed_markup_spans記錄移除範圍。父子關係、來源重建、完整覆蓋與字數均經驗證，不把metadata或財報全文JSON直接當embedding文字。第五階段已接受5.0並保存兩種完整父項，Code_2在檢索時選擇是否額外帶回標題父項。

程式分工：chunking/parent_child.py組裝新版、slicing.py安全切分及來源映射、semantic_structure.py共用解析；functions/parent_relations.py提供建庫／召回共用驗證。舊original仍走strategies.py及hierarchical.py原規則。CLI可用既有--chunk-mode parent_child、--chunk-threshold 700，--no-export集中停用實驗輸出。來源規則納入索引簽章，請用第五階段建立新版產物的新索引，舊Output／索引不自動覆寫。

本次Code相關114項、Code HTTP7項、Code_2全套140項及兩項Node介面測試通過；真實樣本記憶體核對與限制見[驗證紀錄](maintenance/parent_child_v5_validation.md)。不包含真實模型API／embedding品質或新OCR辨識驗收。

## 第二階段cannotfindtable內清理（2026-10-26最新）

第二階段完成候選標記、標題與頁碼處理後，會對note後有效cannotfindtable區塊移除空白字元及空白行，非空行之間仍保留原換行（含CRLF），不跨行合併金額碎片。只清候選內文字，候選外正文、正常表格及空行不受此新增規則影響；既有全文件中文字符間空白清理另行執行。候選內對齊Tab／空格會清理，HTML屬性、完整HTML表格、註解及fenced code保護保留。原始raw唯讀，重新跑第二階段會建立新processed批次，不自動改寫舊產物。

程式為functions/markdown_processing/suspected_table_spaces.py，由note_processing.py最後階段呼叫；偵測門檻與候選原始行號不變。Record的processing_scope.suspected_table_whitespace_cleanup記錄suspected-table-whitespace/1.0、block_count、changed_block_count、removed_whitespace_count、removed_blank_lines。此為既有EXPERIMENT_ONLY第二階段Record的一部分，不增加寫檔模組；--no-export時核心仍完成清理並回傳scope，不另存副本。移除實驗寫檔不應移除清理功能。

本輪35項局部測試通過；2024_2303 raw記憶體驗證11個候選，移除79空白字元、265空白行，候選外內容、HTML、Page、候選內非空白字元及非空行數保持，重跑一致。未寫既有Output／索引或呼叫API。另跑舊test_process_batch.py有8項測試／12個錯誤，因測試仍引用已移除generate_toc與舊批次路徑，未在本次擴大整理；本輪不是全套測試通過。下方候選空白全部保留的舊紀錄由本節取代。

## content首行說明移除年度（2026-10-26最新）

第四階段parent_child的文字／表格首行均維持「年度years｜股票代號｜Main_Section｜Sub_Section｜Note_Title｜說明」。說明在生成首行時移除明列年度，例如112及111年度各產品營收如下→各產品營收如下；金額、百分比、股票代號及耐用年限10年等期間保留，日期只去掉年份部分而保留月日。空說明省略。只改生成首行，原始directions／table_context／year_sources及正文、表格不改，years也不重算。表格仍保留表頭年度優先及既有標籤回查界線；文字仍使用文件年度。

程式在functions/content_context.py，schema仍4.1、規則升hierarchical-semantic-chunks/4.2-context。重啟網頁並重新執行第四階段才產生新版，舊產物不覆寫。舊4.1首行仍可驗證，original模式不變。120項本機相關測試通過，另有2025_2330既有tagged唯讀記憶體來源核對（194搜尋chunk／165父項／96段HTML表格不變），未呼叫API或重建索引。

新700字切分、表格獨立及跨頁按頁Child、###整組分項／移除符號、標題父項及可選召回尚未完成；本節只補完說明移除年度，不代表第四階段整體改造完成。第二階段空白清理程式已存在，本次未另行重新驗證。

## 第三階段：恢復content結構邊界（tagged3.3，2026-10-26最新）

使用者要求取消空行／段落結束content。`block_boundaries.normal`已移除空白行flush；普通空行、空白字元行、CRLF原樣保留，content可跨空行及頁面，直到既有標題／HD／說明標籤、變更大標、表格或EOF等結構邊界才收尾；同名大標及page_start／page_end不單獨截斷。表格、候選、程式碼及註解的保護規則不變。版本為markdown-comment-tagging/3.3，下方3.2按空行結束段落的說明僅供歷史參考。

重新執行第三階段才會產生新版tagged，既有Output不自動更新。第四階段核心與格式未改；它目前以content_end等事件形成文字單位，所以新版tagged的普通多段文字可能合為較大的atom，700門檻遞迴／1500 Parent分組／300 Child累積仍不在此單位內硬截斷。例如400字、空行、400字在parent_child可形成同一個800字Child。這不是本次新增的第四階段演算法；跨頁表格按頁父子需求與混合chunk外層table包裝問題仍未修復。

本輪79項本機測試通過，涵蓋空行／空白／CRLF、跨頁、標題及表格邊界、候選／程式碼保護、來源保真、第三→第四串接。原第四階段依賴段落的單元測試改為明確content邊界，與第三階段是否自動標記空行分開驗證；另有新測試確認真實新版800字不拆的行為。2024_2330既有processed僅在記憶體試算，content由364降157，page=113、table=91（含full_table=3）不變；126個HTML表格及113個Page標記原樣保留，來源檔案未變，沒有寫Output、重跑OCR／模型／API或改動索引。

## 第二階段中文字符間空白清理（2026-10-26）

`process_note_content`完成標題補標、獨立頁碼清理後，對整份processed Markdown（含`<note>`之前）移除同一行中兩個中文字之間的水平空白，例如`台 積 電`→`台積電`。不移除空白行，不改中文字與英文／數字／標點之間的空白，也不改數字中的空白。掃描保留HTML tag／屬性、HTML註解、Markdown inline code及fenced code；表格只改`td`／`th`文字節點，`tr`、儲存格數量、rowspan／colspan及真正空儲存格均保留。原始raw唯讀，清理只寫入新processed結果；清理版本與移除數量列入Record的`processing_scope.intercharacter_space_cleanup`。

程式位於`functions/markdown_processing/intercharacter_spaces.py`，由`note_processing.py`在Stage 2既有規則後呼叫。此變更尚未執行測試或真實文件驗證；既有Output不會自動更新。後續階段直接使用processed文字，不重複清理。

## API設定與金鑰管理（2026-10-26最新）

重新啟動Code/start-web.cmd後，右上角按「API設定／金鑰」。Code與Code_2使用同一個管理介面與儲存，修改不需重寫程式。新增時填名稱→用途→服務商→模型ID→輸入新key或共用該服務商已保存key。保存不會呼叫API、測試額度或自動下載模型。

支援範圍：BGE-M3本機與voyage-finance-2做embedding／檢索；只有Voyage做重排序；Gemini與OpenAI GPT做回答。Embedding模型固定finance-2以保護既有1024維索引契約，其他API模型ID須屬對應服務且由帳號提供權限。GPT模型ID要自行填入（以gpt-開頭），且需支援Responses／Structured Outputs；不從key推測版本，不替使用者選預設GPT版本。第五階段下拉顯示已保存且有key的Embedding設定；BGE永久保留，無需key。

「刪除設定」只刪模型選項，保留可能共用的key；下方「刪除金鑰」會列出使用它的所有設定，確認後從本機.env移除key，連同其所有設定一起移除。索引、Output、模型快取與原始PDF不受影響。同模型換key不需重建向量。不是呼叫服務商撤銷金鑰；已送出的請求不會自動取消。其他已開介面按更新清單／重新整理後反映最新選項；被刪的設定執行前會拒絕，不換其他key或模型。

### 儲存及維護

- 秘密：專案根目錄.env。新增key以FINRAG_KEY_加唯一識別命名；不覆寫其他key或無關行，保留原有UTF-8 BOM及換行。欄位為密碼輸入，保存／關閉後清空，不回傳key、寫入URL、localStorage、模型設定JSON或工作狀態。
- 非秘密設定：Code/config/api_profiles.json，version=1，credentials只含ID／名稱／provider／環境變數名稱，profiles含名稱／用途／服務商／模型ID／credential_id。透過嚴格結構驗證，不接受任意附加秘密欄位。
- 多程序設定寫入鎖：Code/config/api_settings.lock.sqlite3，只作SQLite互斥鎖，沒有秘密或金鑰SQL。檔案更新使用同目錄暫存與原子取代；新增模型設定保存失敗會移除該次新增key。刪除若磁碟失敗可能留下「key缺少」的參照，可在介面重試刪除，不宣稱跨兩檔原子交易。
- 既有VOYAGE_API_KEY／GEMINI_API_KEY提供相容預設；OPENAI_API_KEY可共用，但須另建明確GPT模型設定。若由外部環境變數提供則顯示不可刪，請在啟動環境移除後重啟；程式不假稱能永久刪除父程序環境。
- 核心Code/functions/embedding/api_settings.py；共用畫面functions/web_ui/api-settings.html及.js；Code經獨立Code/vector.py程序存取，Code_2使用同一核心。兩個HTTP入口皆保留同來源／權杖及大小限制，不提供任意讀.env路由。金鑰管理不建立問答輸出或模型工作紀錄。

### 本次驗證及限制

8項純本機設定測試通過，涵蓋key只存.env、共用與刪除、保留無關行及BOM、舊key相容、外部環境不得假刪、缺key／錯用途／錯服務商拒絕、JSON不洩密及保存失敗回復。Code本機HTTP／程序相關11項通過，Code_2全套139項通過（含假key的HTTP新增刪除及模擬GPT、略過重排）。Node的test_api_form.cjs、test_ui_controls.js、Code_2/tests/test_index_selector.cjs通過，核對實際表單函式、GPT選項、共用key、刪除事件、第五階段請求及刪除選中項目後不換BGE。Python編譯與JS語法檢查通過。

全部使用暫存.env、合成金鑰、假API及暫存Chroma，沒有讀取／修改真實.env、刪除現有索引、呼叫真實Voyage／Gemini／OpenAI或重新OCR。沒有宣稱服務權限、免費額度、真實模型品質、100–200份效能已驗收；HTTP在核准的loopback測試下執行，沒有停用來源保護。

## 第五階段：直接建庫與資料庫管理（2026-10-25最新）

重新啟動`Code/start-web.cmd`。第五階段先選切法original／parent_child，再勾選第四階段的chunk JSON、選BGE-M3或voyage-finance-2並執行。欄位用途固定由`Code/config/embedding_fields.txt`設定，網站不提供欄位檢視／選擇器；模型／路徑／批次等設定改為`Code/config/embedding.py`。前處理、表格轉換、長度檢查及提交沿用原核心，不截斷表格。

第五階段在記憶體完成前處理，不另產生prepared JSON、Markdown、Record或新Output批次。每份結果顯示成功、已存在、超限或失敗階段。勾選「只檢查token」不建向量；Voyage檢查亦須明確啟用API。一般建庫必要匯入紀錄仍在資料庫的ingestion.sqlite3，不受實驗Output開關控制。

建庫入口`Code/vector.py`使用現有`Code/.venv`，前四階段仍用`.venv_pdf`，沒有新增依賴或要求重裝PDF環境。跨環境以stdin/stdout JSON事件傳遞選取與狀態；不靠同名頂層模組互相匯入。命令列可從專案根目錄使用：

```powershell
# 來源路徑相對於Output/markdown_chunk；此範例僅示範，請換成實際來源。
& .\Code\.venv\Scripts\python.exe -X utf8 Code/vector.py --source "Financial_chunk_20261025_12-00-00/original/2025_2330_chunk.json" --backend bge --check-only
# 移除--check-only才會實際建庫。Voyage另需--backend voyage --allow-voyage-api。
```

API金鑰仍由專案根目錄`.env`或環境變數的VOYAGE_API_KEY讀取；畫面不顯示金鑰。模型快取沿用`Code_2/.cache/embedding`，不搬移／刪除已有權重；資料庫仍為`VectorStore/chroma/bge`及`voyage`。不同模型、模式、參數與規則產生各自collection。檢索／重排序／回答繼續使用Code_2。

### 瀏覽與刪除

第五階段下方「資料庫管理」：更新索引→選模型→切法→索引集合→按doc_id部分字串、股票代號、內容年度years篩選→套用篩選。doc_id例如2025Q4_2330_Financial_Report，沿用原識別。點「查看內容」分頁閱讀原chunk、年度及PDF實體頁序；原HTML作文字呈現，不執行。舊索引切法未知時選「舊版／未記錄」，不推測其模式。

勾選文件後按「預覽刪除所選財報」，畫面列出集合、doc_id、文件與向量數；確認後只刪該集合的整份文件、父項和有效文件清冊。年度篩選是文件任一chunk符合years，不是只刪某一年度chunk。原始PDF、Output、其他集合及歷史attempts保留；刪除成功後可再次匯入同doc_id。

刪除先保存deletions標記停止後續召回，再刪向量，最後移除父項及有效清冊。失敗可重新預覽後重試；不把部分刪除當完成。SQLite與Chroma不是跨庫原子交易，斷電可能留下待完成狀態，需在管理頁核對；匯入會阻擋這些文件。資料管理與Code建庫互斥；建庫不能強制取消，避免套用前四階段Output清理破壞持久索引。仍可切頁查看，等待目前工作完成。

### 模組與舊入口

`functions/embedding/direct.py`接chunk→prepare_document→build_document；`management.py`負責篩選、分頁、刪除快照；`catalog.py`列提交索引；其他embedding模組由Code_2遷入，沒有重寫模型演算法。舊Code_2.embedding匯入只轉接到Code，同一份實作供問答產生查詢向量與讀庫。Code_2舊實驗前處理及Output保留，但不再出現在可執行GUI／CLI入口；本次沒有刪除既有資料。

### 本次驗證

本輪新增8項第五階段／真實暫存Chroma測試及3項網頁／程序測試通過；前四階段相關23項回歸測試通過。涵蓋直接讀chunk且不寫prepared、不同模型／模式／參數隔離、重複匯入、token超限、單份JSON失敗後繼續、瀏覽原文、篩選、過期預覽拒絕、刪除失敗停止召回及重試、父項同步清理、只刪指定集合、刪除後重匯入、HTTP權杖及忙碌互斥、.venv獨立程序事件。Node的test_ui_controls.js與Code_2/tests/test_index_selector.cjs通過，檢查第五階段模式選取／實際請求、無Output按鈕、索引模型／切法隔離；Python編譯及JS語法檢查通過。

Code_2全套133項已執行，功能斷言通過；最後一輪有1項既有父表測試在Windows清理暫存Chroma時遇WinError 32，該項單獨重跑通過，未將此輪描述為一次全套無錯誤。更早的階層索引測試亦遇相同清理時序，已加入有限等待並單獨通過。原discover會因Code與Code_2同名測試匯入衝突而停止，已改相關跨目錄測試為完整套件匯入。本機HTTP測試曾受sandbox WinError 10013阻擋，經核准在限制外執行同一測試通過；沒有改服務來源保護。

測試使用合成文件、假API／向量、暫存Chroma及本機HTTP，沒有重新跑OCR、載入真實BGE推論、讀取金鑰、呼叫Voyage／Gemini、建庫實際財報或刪除現有索引；沒有宣稱新流程的真實問答品質或100–200份效能已驗收。未用真實財報在瀏覽器按下建庫／刪除。沒有新增依賴：第五階段與問答沿用Code/.venv，鎖定版本見Code_2/requirements.lock；PDF環境仍依Code/requirements.pdf.lock。

可從根目錄用Code/.venv執行`-m unittest Code.tests.test_vector_stage`，Code/.venv_pdf執行`-m unittest Code.tests.test_vector_web`。完整Code_2仍可用unittest discover；Windows遇暫存清理鎖時須如實區分斷言與清理失敗，不忽略錯誤。

## 第四階段：兩種切法與父子關係（目前規則）

本節依目前程式整理，供操作及維護時優先閱讀；下方日期紀錄保留歷史變更。第四階段輸入tagged，輸出chunk Markdown及JSON，不執行embedding或呼叫LLM。兩種模式共用解析、HD階層、段落及特殊綁定，再分別建立搜尋chunk與完整父項。

### 操作與參數

網頁選第四階段、勾選來源並選「原本切法」或「父子切法」；參數在預設收合的「進階設定」。

|畫面順序|設定名稱|預設|滑桿上限|用途|
|---|---|---:|---:|---|
|1|parent_limit|1500|3000|一般Parent的分組上限|
|2|recursive_threshold|700|1500|一般HD範圍是否往下層繼續切分|
|3|child_target|300|1000|有Parent時，Child累積字數的切分門檻|

切塊預設集中於`config/chunking.py`，滑桿上限集中於`config/web.py`。滑桿上限不是內容或手動輸入的硬上限；例如輸入4000會採用4000。三值須為正整數，Child不能大於Parent。字數使用可見、非空白內容計算，不計HD／控制標籤或另存的說明metadata；不是模型token數。

### 共用分界與原本切法

先依HD階層與同級／更高級標題界定內容範圍。一般未綁定的HD範圍不超過700字時保留；超過且有下層HD時往下遞迴，沒有下層時依完整段落分組。700不是直接在第700字截斷。含特殊綁定的範圍先按其分界處理，不任意與其他內容混併；不跨不相關章節補足字數。

`original`模式的一般文字直接形成搜尋及回傳chunk，不建立一般文字Parent。特殊綁定內容不超700字時也直接回傳，超過才建立完整Parent及Child。

### 父子切法

`parent_child`模式沿用共同HD分界，一般附註文字也建立Parent。需要按段落分組時，將完整段落依序累積，加入下一段會超過1500便先結束目前Parent；不拆開段落來湊滿1500。較短範圍也可建立Parent，不保證每個Parent都接近1500。

在每個Parent內累積至少300字，遇到原有段落結束才形成Child；不在第300字硬切。最後不足300字的餘段仍保留，不跨Parent借內容。完整表格作為整個單位加入Child，不因Child門檻切碎表格，所以Child也可能遠超300字。

例如：同一最下層HD沒有特殊綁定，有四段各400字，使用預設參數：

```text
Parent 1：前三段，共1200字
  Child 1：第一段400字
  Child 2：第二段400字
  Child 3：第三段400字
Parent 2：第四段，共400字
  Child 4：第四段400字
```

下游以Child做embedding及檢索；命中Child 2時讀回Parent 1。多個Child命中同一Parent只回傳一次，不再向上擴展完整章節。第四階段只建立這些資料與關聯；實際建庫由Code第五階段負責，檢索及父項回傳由Code_2負責。

### 特殊綁定與例外

- `content_direction`：說明與後續所有段落綁定，到下一個HD、新說明或文件結尾停止；空行、content_end及換頁不解除完整Parent範圍，Child仍可按段落分開。
- `table_direction`：同一範圍內可供後續表格共用，新說明取代之前說明。table_context仍取最近的hd／table_direction／content_direction，不用table_year當說明。
- `###`：從同一最近HD內的條列建立完整群組，保留項目、後續說明及中間表格，不混入下一HD的群組。
- 附表：每份附表維持完整語意範圍，含多張表及說明，不因內部HD或字數限制拆散。
- 完整表格、附表及其他不可安全拆分綁定允許超過Parent上限並記錄診斷；一般超長單段也不硬切。保留完整內容不代表embedding一定符合token限制，後續仍可能回報超限。
- 會計師查核報告：兩模式都保留原規則，一個`##`對應一個chunk，不套用一般附註文字的Parent／Child切法。無對應標題不補造。

### 輸出與維護位置

每次執行建立`Output/markdown_chunk/Financial_chunk_YYYYMMDD_HH-MM-SS/`，同次多份財報共用新批次；本次選取模式位於`original/`或`parent_child/`，檔名仍為`年度_代號_chunk.md`及`.json`，Record在模式內。

JSON的`chunks`是搜尋單位，`parents`保存完整回傳父項；Child的parent_id及part_index對應直接Parent與順序，沒有父項時兩欄為null。Markdown列出chunks及父子註解，完整Parent請查看JSON的parents，不把父項再重複列成搜尋塊。

HD／年度／說明控制標籤移至title、章節、table_year、directions等metadata，原始content不重列；保留years、page、source_spans及表格來源。原始查核##、正文###及附表####仍可保留於content。來源追溯、表格完整性及年度判定沿用既有規則。

程式分工：`semantic_structure.py`建立共同結構及綁定，`strategies.py`規劃兩模式，`hierarchical.py`組裝chunks／parents及診斷，`chunks.py`公開入口、驗證及Markdown，`batch.py`串接來源與集中實驗輸出。歷史`chunk_tagged_legacy`只供相容回歸，不是第三種網頁模式。本次僅更新文件並核對程式，沒有重跑轉換、embedding或檢索；下方過往測試數不代表本次重新執行。

## 2026-10-25：精簡網頁與字數滑桿（最新）

重新啟動Code/start-web.cmd後使用。網頁OCR初始預設開啟，可自行取消；僅需要辨識影像文字時沿用現有OCR流程，不改成每頁強制OCR。第一階段的OCR倍率／表格模式在「進階設定」，關閉OCR便不顯示倍率。第二、三階段沒有OCR與切塊設定。第四階段先選模式，再視需要展開進階設定。

|參數順序|預設值|滑桿上限|
|---|---|---|
|Parent字數上限|1500|3000|
|一般Chunk切分門檻|700|1500|
|Child目標字數|300|1000|

可拖滑桿或輸入數字；手動4000／2000／1200等超出範圍仍採用原輸入，不裁成滑桿最大值，且保留正整數及Child不大於Parent的檢查。畫面顯示超出滑桿範圍的提示。滑桿上限與網頁OCR預設集中在config/web.py的CHUNK_SLIDER_MAXIMA／DEFAULT_OCR_ENABLED；切塊預設值仍在config/chunking.py。本次僅調整網頁OCR初始選取，不改CLI既有OCR預設。

全選及取消選取保留在主區，進一步篩選／展開操作收進「更多選取操作」，已選檔案路徑收在明細。工作未開始時隱藏空狀態／進度；只有執行中顯示取消，完成後僅該階段顯示輸出按鈕。CSS的hidden優先於toolbar顯示樣式，避免不適用控制項露出。關閉服務仍會顯示已關閉訊息。

本次7項本機HTTP測試與3項切塊介面／前處理串接測試通過；Node測試`Code/tests/test_ui_controls.js`核對狀態切換、超限輸入實際請求、全選及服務關閉，語法檢查通過。另以瀏覽器操作暫存假資料驗證四階段切換、OCR開關、進階收合、滑桿同步及4000輸入保留，沒有執行真實轉換。預覽服務已關閉；未改財報、模型、向量庫或Code_2。

## 2026-10-25：第一階段命名補充（最新）

第一階段現在也輸出到`Output/markdown_raw/Financial_raw_YYYYMMDD_HH-MM-SS/`，同次多份PDF共用一個批次，檔名與Record位置維持。其餘三階段分別為Financial_processed／tagged／chunk。既有無階段名稱／流水號批次仍可讀，不搬動或改名。只改命名及讀取規則，未改PDF、OCR或轉換參數。3項命名／來源清單／選單批次測試通過，另以暫存raw驗證第二階段讀取及取消白名單相容；未重新轉換PDF。下方「第一階段原命名不變」由本節取代。重啟既有服務後生效。

## 2026-10-25：新批次輸出命名（最新）

第二到第四階段每次執行建立新批次，不再沿用來源批次名稱。同次選取的多份財報放在同一新批次中，包括從不同來源批次勾選的檔案；檔名不改。以下為例：

```text
Output/markdown_processed/Financial_processed_20261025_16-01-30/
  2025_2330_processed.md
  2025_2303_processed.md
  Record/
Output/markdown_tagged/Financial_tagged_20261025_16-05-20/
  2025_2330_tagged.md
  2025_2303_tagged.md
  Record/
Output/markdown_chunk/Financial_chunk_20261025_16-08-10/
  original/（或本次選取的parent_child/）
    2025_2330_chunk.md、2025_2330_chunk.json
    2025_2303_chunk.md、2025_2303_chunk.json
    Record/
```

再次執行同一來源會建立另一時間批次，舊產物與舊失敗Record不覆寫。同秒已有批次時等待下一秒再建立，不加流水號；第二次仍撞名則明確停止。新批次內仍禁止同名覆寫：同次選取若有相同年度＋代號，開始前回報重複，請分開執行。原始PDF、檔名及補標題／加標籤／切塊核心規則不變。

第一階段現已使用Financial_raw_日期_時間。第二至第四階段CLI與網頁共用`experiments/export_output.stage_output_batch`；網頁worker只建立一次再傳給逐檔入口，避免每檔一個資料夾。Record的batch記新輸出、source_batch記原來源；上下游核對仍讀來源批次內Record。取消白名單改用worker回報的新批次，只清理本次未完成檔案。停用實驗輸出不建立批次。

新舊名稱皆可出現在來源清單。Code_2只更新config/embedding.py的批次名稱比對，讓下游認得新chunk資料夾，既有模式目錄及embedding規則不變。既有Output不搬移、不刪除。使用前關閉既有網頁服務，再重新雙擊Code/start-web.cmd。

本次實際驗證：175項相關核心／批次／取消／前處理測試及7項本機HTTP介面測試通過，共182項；包含跨來源批次的兩份財報合併、重跑新批次、來源／舊成果不變、Record對應、取消清理、停用輸出與新名稱下游前處理。JavaScript語法檢查通過。未執行實際Docling／OCR、真實embedding或付費API，未改既有Output／索引。額外跑到舊第一階段test_batch_output的兩個模擬案例時，其convert測試替身不接受既有page_range參數而失敗；本次未修改或修復第一階段，這兩例未計入上述通過數，也未據此判定真實PDF轉換失敗。

下方「沿用來源批次」「重跑一定因舊檔而拒絕」屬歷史，以本節為準。

## 2026-10-25：來源全選

網頁新增「全選資料夾」按鈕，選取目前階段清單內全部有效檔案（包含所有子資料夾與篩選外資料），不自動執行，執行中停用。原單資料夾勾選及「勾選篩選結果」維持。第二到第四階段現在每次建立新批次；新命名及重跑方式見本文件最上方最新節。

## 2026-10-25：階層切塊4.0與兩種模式（最新）

本節為目前實作；下方3.x切法／「模式待實作」屬歷史。前3階段及轉換參數不因本次修改而改變。第四階段入口仍為本機介面：雙擊`Code/start-web.cmd`，既有服務須關閉後重開以載入新版。使用`Code/.venv_pdf/`，下方舊`.venv`啟動說明以此為準。

第四階段先選tagged批次／檔案，再點「原本切法」或「父子標題切法」模式按鈕，最後執行。依序可調Parent上限1500、一般HD遞迴門檻700、Child累積門檻300；集中設定在`config/chunking.py`的ChunkSettings。Child不可大於Parent。兩模式共用解析及語意範圍，不維護兩份Markdown處理規則。

|模式|一般附註文字|特殊說明／###／表格／附表|
|---|---|---|
|original|≤700保留HD範圍，超過則往下層HD遞迴，無下層按完整段落分組，不建一般父項|綁定內容>700建直接Parent，否則直接回傳一般chunk|
|parent_child|沿用HD分界，安全段落依1500組Parent，Child累積至少300後遇段落結束切|完整語意單位作Parent及Child，不因字數裁表|

查核報告在兩模式均維持一個##一塊，無標題不補造。content_direction延續至新HD／新說明；table_direction可共用於後續表格，遇新說明更新。###包含同最近HD下的項目、說明及中間表格；不同HD不混組。附表保持完整，不因內部HD拆散。普通長段落與不可拆綁定可超出門檻，Record列出診斷，避免硬切破壞語意。完整表格仍為原子單位，不新增模型摘要。最後不足300的Child仍保存。

輸出（EXPERIMENT_ONLY既有集中寫檔機制）：

```text
Output/markdown_chunk/Financial_chunk_日期_時間/
  original/2025_2330_chunk.md、2025_2330_chunk.json、Record/
  parent_child/2025_2330_chunk.md、2025_2330_chunk.json、Record/
```

同模式同名產物仍拒絕覆寫，選另一模式不覆蓋；既有平面資料不移動。停用實驗輸出用既有`--no-export`，核心可獨立記憶體執行。

```powershell
& .\Code\.venv_pdf\Scripts\python.exe -X utf8 Code/main.py --chunk-batch "Output/markdown_tagged/Financial_tagged_日期_時間" --chunk-mode original --parent-limit 1500 --child-target 300 --chunk-threshold 700
# 同一來源切另一模式：改為 --chunk-mode parent_child。
```

新JSON為`financial-chunks/4.0`／規則`hierarchical-semantic-chunks/4.0`。保留既有章節、years、page、source_spans、year_sources、parent_id及part_index；新增table_year／directions來源記錄與table_ids。HD及說明控制標籤不重列於content，改由title、章節及說明metadata承接，Markdown以註解顯示。查核原##及正文###／附表####保留。沒有綁到內容的年度／說明不猜配，issues保存原文及來源位置。表格table_completeness既有0／1規則不變。父項不作搜尋向量，Child命中僅回傳直接Parent並去重。

實作分工：`semantic_structure.py`共用IR／綁定；`strategies.py`兩種分組；`hierarchical.py`組裝4.0；`chunks.py`公開入口、契約及Markdown；`batch.py`串接來源核對；`experiments/export_output.py`集中模式寫檔；`web_ui/request_settings.py`及index.html／server.py控制介面參數。歷史`chunk_tagged_legacy`只供3.x相容回歸，不是第三種UI模式。

本次235項局部測試通過：157項核心／前處理／輸出回歸、7項本機HTTP介面、71項Code_2索引／檢索。Chroma測試使用實際暫存庫及假向量，未執行付費API或真實embedding。2024_2330既有raw在記憶體完成二→三→四及前處理：original202塊／20父項、parent_child224塊／173父項，126個HTML表格逐字一致，各chunk均可由source_spans重建。兩模式各有9筆不可拆父項超限、6筆未綁定結構標記，仍需人工核對。未重跑PDF、覆寫Output或重建真實索引；未做逐表年度人工驗收。

長表完整保存仍可能超出embedding token上限，沿用該份停止並明列超限chunk；本次沒有新增付費摘要或默默截斷策略。一般文字超長單段亦保留並列待核對。現有Output不會自動變成新版，需重新執行第四階段及Code_2前處理／建庫才能使用新規則。

## 2026-10-25：空行結束正文（tagged3.2）

`block_boundaries.normal`新增一般正文空行處理：關閉當前content，輸出`</content_end>`後原樣保留空行，遇下一段非空文字再開content_start。僅空格、Tab或全形空白的行同樣算空行；連續空行不產生空區塊。HTML／管線表格、cannotfindtable、接續表群內、程式碼及註解維持保護，內部空行不截斷；Page／page_end本身仍不結束正文，其他標題／表格收尾規則不變。tagging版本升markdown-comment-tagging/3.2。第四階段1000字等參數未改，會依新的content_end邊界執行原有延遲切塊規則。既有tagged／chunk需重新執行對應階段才更新，不自動覆寫。

92項局部測試通過，包括空行／空白行／CRLF／表格及疑似表格保護、跨頁、既有chunk與年度欄位回歸。2024_2330既有raw記憶體二→三→四得到364個content區塊、223個chunk／90父項，HTML表格與Page序列原樣保留；未寫Output、重新執行PDF或模型／API。

## 2026-10-25：table_completeness（切分規則3.3）

表格chunks及parents新增整數`table_completeness`：自己的content含`<cannotfindtable>`則0，否則1；Markdown對應`<!-- table_completeness: 0 -->`或1。文字不輸出此欄。跨頁父表含候選為0，各子塊依各自內容判定，因此同父表下可有1和0。此欄只反映候選標記存在，1不是人工品質保證，原特殊表格標記與切法未變。驗證器拒絕布林／字串及與內容不符的值。schema仍3.1、rule_version升3.3；Code_2選用欄位向後相容，metadata及original_chunk保留，未重建索引或改embedding_fields。

81項局部測試通過，涵蓋普通／疑似／混合跨頁父子與下游欄位保留。真實2024_2330在記憶體產生223個chunk／90父項；128個表格子塊中125個為1、3個為0，父項87個為1、3個為0，文字無該欄，Code_2輸入契約核對通過。未寫既有Output、呼叫OCR／API或建庫。疑似表格全文embedding轉換仍屬原已記錄的待銜接範圍，本次僅新增標籤與契約相容。

## 2026-10-25：表格脈絡與年度（切分規則3.2）

第四階段`table_parents.py`分開取得表格說明與年度。`table_context`維持原欄名，向上取最近hd／table_direction／content_direction的文字；略過普通文字、其他表格與table_year，遇查核／附註區域切換停止。附表從第一張實際表的位置查找，附表識別仍用appendix_id。

年度先讀表內既有可辨識欄名（HTML第一列及th、管線表格標頭），有年就不混入前置文字的年份。沒有時，向上掃描table_year／table_direction／content_direction，從整段文字找年，採最近可取得年度的標籤；遇正文、其他表格、hd或區域切換停止，空白／Page／內容結束邊界不阻止。仍找不到用文件年。year_sources保存辨識依據；文字chunk使用文件年。

`config/table_metadata.py`集中明列格式及沿用的年度範圍；支援中文數字民國年、阿拉伯年、年月日及點／斜線日期，不把任意裸數字金額當年度。years一律西元整數清單，例如民國一一四年度及一一三年度→[2024,2025]。無法從表頭可靠辨識的年仍會走備援，並非掃描全表任意交易日期。

JSON schema仍financial-chunks/3.1、Markdown版本不變，rule_version改heading-content-chunks/3.2。使用既有第四階段入口重新處理指定tagged才會有新產物；既有Output／prepared／向量庫不自動更新。Code_2輸入欄位與型別未變，本輪未修改其程式或欄位設定。

驗證：85項相關局部測試（含Code_2前處理回歸）通過；2024_2330既有raw在記憶體串接二→三→四，223個chunk／90個父項，西元年型別及Code_2輸入schema通過，前置table_year／table_direction各有命中。未寫Output、重新OCR、執行模型／API或建庫，也未逐表人工核對年度。本節取代下方年度／table_context待實作的歷史狀態；Note_Title只含hd2以下路徑，不另加階層欄位。

## 2026-10-25：章節新欄位已完成（chunk3.1）

JSON的chunks及parents皆新增`main_section`、`sub_section`字串、`note_title`字串清單。來源仍是明確區域標記及實際標題樹：查核##為sub_section且note_title=[]；附註hd2為sub_section，動態標題樹的每條下層葉路徑各一個note_title，使用` > `連接，不包含已獨立保存的hd2。無對應標題時空字串／空清單，既有title樹保留供結構及舊介面使用，兩者一致性會驗證。附表的章節改取開始位置的實際hd2／動態路徑，不以附表名稱假造hd2，附表名仍在appendix_id／原文與table_context。

Markdown每個chunk前列chunk_id／doc_id／years／page，再列Main_Section／Sub_Section；每條Note_Title各列一行，空清單列空Note_Title。`>`在註解內原樣顯示，不轉&gt;。每塊前的舊hd2／MAIN_TITLE輸出已由新章節欄取代；正文內實際出現或需要繼承的動態hd仍按原切法保留，查核##也保留。parent_id／part_index仍固定顯示，無關係時空欄。例：

```markdown
<!-- Main_Section: 合併財務報告附註 -->
<!-- Sub_Section: 四、重大會計政策 -->
<!-- Note_Title: (一) 金融工具 > 1. 金融資產 -->
<!-- Note_Title: (一) 金融工具 > 2. 金融負債 -->
```

資料／切分／Markdown版本3.1，Code_2驗證器接受1.0／2.0／3.0／3.1，新3.1需有三章節欄並與title一致；前處理metadata保留新欄位，未更改既有embedding_fields及向量庫。166項局部測試通過，2024_2330 raw記憶體串接223塊、9查核note_title空清單，新欄位及Code_2輸入schema核對成功。未寫Output／未前處理全文／未呼叫OCR、API或建庫；舊資料不自動變新版。

使用者另提「增加階層關係標籤」，尚在釐清是Note_Title路徑本身或另一欄位，未新增額外欄位。table_context新回查、表格年度新規則與第二種文字父子切法亦未實作。本節取代下方「新欄位仍待確認」的歷史狀態。

## 2026-10-25：已納入查核報告，chunk3.0（新欄位呈現待完成）

chunk_tagged已取消公司沿革篩選，excluded_prefix_end固定0；sections.py已接入，依會計師查核報告／note來源標記辨識區域，控制標記不算正文。查核##標題各自開始一塊，到下一個##或note區域變化結束；不因1000字、content_end或換頁切查核正文。查核##原文保留，標題作為該塊章節，沒有動態Note_Title。附註沿用原hd2／字數／結束標記／表格切法，文字與表格仍可有空父子欄位。表格先沿用既有獨立及父子規則，未新增混合文字表格切法。

目前章節仍暫存在既有title.main_title及title.heading，尚未完成Main_Section／Sub_Section／Note_Title新欄名與多路徑輸出，正待確認格式；不可把切分完成當成所有新欄位完成。沒有標題的可追溯正文亦保留，heading為null，不建立假hd2；原始##查核標題有值時，title.heading使用其實際Markdown二級標題及空children。資料／切分／Markdown版本升3.0，Code_2驗證器已相容3.0與null heading，舊1.0／2.0非空標題驗證仍保留。

161項局部測試通過，包含更新的取消公司沿革限制測試、查核按##跨頁長文切法及Code_2前處理。2024_2330 raw記憶體二→三→四串接，查核9個##對應9塊、順序一致，含附註共223塊，未寫Output。Code_2只做新輸入結構相容，並未宣稱所有新標籤／疑似表格前處理及索引完成；新table_context、年度回查、第二種文字父子切法待後續需求。舊Output不自動更新。

2026-10-25查核報告調整進行中：已確認依查核區域保留的##切分，每個標題一個chunk；sections.py及test_chunk_sections.py新增明確區域／查核標題事件辨識，2項局部測試通過。工具尚未接入主切分函式、公司沿革起點尚未移除；待確認查核##的Sub_Section填法後繼續欄位與切分契約。沒有寫Output，不可宣稱已納入查核報告。

2026-10-25第四階段欄位調整進行中：Markdown所有chunk已固定輸出parent_id及part_index，無關係時留空（JSON仍是原有null）。20項chunk測試通過，既有Output未改。使用者要求納入查核報告及新增Main_Section／Sub_Section／Note_Title等欄位，但公司沿革起點限制此刻尚未刪除；正在確認無hd2查核報告的空值處理，後續須同步處理JSON及Code_2輸入契約。新表格年度回查及文字父子標題切法尚未實作，不應宣稱新chunk格式全部完成。

## 2026-10-25：疑似表格專用邊界（tagged3.1）

`config/markdown_blocks.py`新增FULL_TABLE_START=`<fulltablestart>`。第三階段`block_boundaries`收集有效成對cannotfindtable原始字元區間，與已辨識HTML／管線表格一起套用區塊流程；先關閉前面的content，候選內不插content標記，原文與cannotfindtable標記不移除、不重排、不還原欄列。格式：

```html
<fulltablestart>
<cannotfindtable>
疑似漏辨識表格的原文
</cannotfindtable>
<table_end>
```

`_protected_lines`可選回傳full_table_ranges，沿用原配對檢查，程式碼／HTML表格／註解內的假候選不採用，未閉合／巢狀／多餘結束標記拒絕；候選若含HTML，以候選外層包裝，避免重複區塊。正常表格仍table_start，兩表之間有接次頁或承前頁則沿用原合併條件（忽略空格、附表為邊界）；同一接續群只要有候選就用fulltablestart，不抹去不確定性。頁序與page標籤處理同普通表格，不因換頁拆區塊。Record的block_counts.table包含特殊表格，full_table只在存在候選表格時額外記其群組數。

第四階段僅必要相容：parser接受fulltablestart／table_end，不把候選當一般正文拆散；沿用既有表格父子及按頁子塊流程，候選原文保存於JSON，Markdown輸出含候選的表格子塊仍用fulltablestart。尚未新增候選的特殊切塊／PDF回查／LLM還原，等待後續需求；不能把此相容稱為已正確識別表格結構，年度仍用既有可得證據或文件年度備援。

132項局部測試通過，涵蓋新專項8項及原第三／四階段相關測試；另補CRLF相容後專項9項全部通過。2024_2330 raw在記憶體串接二→三→四成功，3個候選原文均在fulltablestart區塊中，原HTML、Page保留；統計113頁／91表格群（含3特殊群）。無Output寫入、OCR／API或建庫。需重跑第三階段產生新版tagged，原防覆寫維持。

## 2026-10-25：第三階段正文分類3.0（最新）

第三階段不再讀*_tablerefer.json或依公司沿革備援決定大標，不輸出MAIN_TITLE，不因缺少目錄／公司沿革拒絕第三階段；仍須可靠Page、來源識別及完整表格邊界。tag_comments保留toc參數僅相容舊呼叫，參數內容不影響結果；歷史目錄工具與備援模組未作資料刪除。批次Record仍可核對來源，但不是必需輸入；狀態統一tagged_needs_review，main_title_source=disabled、temporary_fallback=false，無toc讀取／雜湊欄位。CLI與網頁階段說明同步更新。

|processed格式|tagged格式|
|---|---|
|## 一、公司沿革|<hd2>一、公司沿革</hd2>|
|## (一)、1.、(1)、A.／a.、(A)／(a)的標題|依型別首次出現順序分配hd3起；返回上層清下層，新hd2重置|
|## 民國一一四年度／112 年 12 月 31 日|成對table_year包住原文|
|## 112及111年度及後續說明|成對table_direction包住原文|
|無編號、##說明如下：|成對content_direction包住原文|

成對形式例如`<table_year>民國一一四年度</table_year>`；HTML特殊字元安全跳脫，不改實際文字。分類優先：年度／日期、多年度說明、編號hd、其餘冒號說明；使用者已確認編號與冒號同時符合時編號優先。比對忽略編號內空白，也接受##後無空格。沒有上層hd2的動態標題仍保留##並回報dynamic_heading_without_section，不猜造父層。無法分類的其他##保留，###與####不進入動態階層，表格／cannotfindtable／程式碼／註解等保護維持。

第二階段heading1.15在末段重查後移除##數字點號及括號數字標題的單一-前綴；保留編號、文字與其他空白，已有###條列不改，note前與表格內不改。scope.final_dash_number_recheck計數包含此清理；HeadingChange以number_heading:remove_list_prefix記錄原始位置。第三階段三種新說明標籤與hd同為正文區塊分界，不加入動態層級、不因換頁重新輸出。

第四階段只做必要相容：新說明標籤原文可保存至chunk，沿用原標題不計正文字數的行為；仍以公司沿革hd2作chunk起點，缺少時停止。MAIN_TITLE取消後chunk JSON的既有main_title欄位保持空字串，不補猜。尚未使用table_year／table_direction／content_direction自動推算表格年度或table_context，本次並未變更Code_2／向量庫。

本輪114項局部測試通過（第三階段新分類、更新的取消目錄／備援測試、區塊、階層、頁碼、chunk、父子表、資料夾勾選、Record獨立、末段-清理等）；未驗證整個舊專案全測試。2024_2330 raw記憶體二→三→四串接成功，table_year4／table_direction5／content_direction42，210個chunk，HTML、Page與控制標記保留，無MAIN_TITLE。無Output寫入、OCR／API／建庫；既有processed及tagged不自動更新，需重跑對應階段，既有防覆寫規則仍適用。介面需重新啟動才載入新程式。本節取代下方歷史第三階段目錄／備援／MAIN_TITLE敘述。

2026-10-25標題1.14：note_processing在條列分類後、頁尾清理前呼叫mark_headings.recheck_dash_number_headings，只針對未有井號的- 1.類數字點號列表行，重用mark_missing_headings判斷。20字不計空白、句尾排除及純數值排除照舊，符合才加##，原文保留；已有##／###不再判斷，不新增括號／英文列表範圍，所有既有保護區仍優先。此步是重查，正常首次補標題已完成時可能沒有新增變更，不宣稱一定修復其他漏判。

Record的processing_scope.final_dash_number_recheck.changed_count記新增修改數，新增HeadingChange的reason為dash_number:final_heading_recheck並映回原始raw行號。72項局部測試通過（heading44含新增4、條列9、note3、疑似表格10、冒號6）；2024_2330 raw記憶體驗證note前、HTML與Page保留，未寫Output／未執行OCR或API。既有processed須重跑第二階段才套用。

## 2026-10-25：附表####、註###（標題1.13）

第二階段mark_headings新增NOTE_PREFIX_PATTERN（註＋中文編號）；附表改####，註改###。例如附 表 一：說明→#### 附 表 一：說明，註 二、說明→### 註 二、說明。比對時去空白，原文空白／後續文字保留，匹配行首即可，不套一般20字及句尾排除。只支援既有中文數字集合，不新增註1或正文中間的引用；已帶其他井號也統一。兩者皆作冒號回收邊界，避免和前文合併。note範圍、表格／cannotfindtable等保護維持；###除條列外，現在也表示此類註標記，並非hd層級。

APPENDIX_MARKDOWN_PATTERN集中定義新版####／舊#附表及空白辨識；第三階段原樣保留####／###，table_continuation以附表為停止接表邊界，第四階段table_metadata／table_parents接受兩種標記，附表ID去空白、標題保存原文。故不需改寫舊tagged，附表一與二仍分開父項。其他chunk規則未變。

94項局部測試通過（heading40、附表父子6、冒號6、條列9、note3、疑似表格10、chunk20）。新增檢查註長文字／空白／保護、附表新舊標記與跨表接續邊界。2024_2330 raw記憶體試算11個附表、24個註變更，原HTML、Page及note前綴保留；未寫Output／執行OCR或API，未完成人工辨識準確率驗收。須重跑第二階段及後續需要更新的階段才產生新版結果。

## 2026-10-25：標題1.12與頁尾清理1.2

僅改四項：附表前綴比對先去空白，附 表 一／附表 一可升單一#並作冒號回收邊界；一般編號標題20字以編號後非空白字元計算，原英文不限長與句尾排除保留；頁尾數字可有內部半形空格／Tab／全形空格，- 5 1 -按帶橫線獨立頁碼清理，純5 1仍須位於可靠Page頁段最後非空白行且等於該PDF頁序；既有Markdown標題接受##後無空格或全形空白。附表與頁尾本來無20字上限，沒有新增限制。

Page與控制標記格式、行首4空格／Tab程式碼保護保持，note前與表格等保護區不改。只在比對／計數時忽略空白，輸出文字不做全域去空格；既有##一、公司沿革能辨識且保留原樣，##普通正文會依既有無編號規則去井號。規則版本markdown-headings/1.12、standalone-page-cleanup/1.2，條列body-lists/1.0不改。

本輪72項局部測試通過（heading39、頁碼5、冒號6、條列9、note3、疑似表格10），涵蓋空白附表、20／21字界線、無空格標題、拆開的頁尾數字與既有保護。2024_2330既有raw記憶體試算，note前、HTML及Page逐項保留；未重跑PDF／OCR／API、未寫Output，既有processed須重新執行第二階段才套用。

## 2026-10-25：第二階段末段條列分類

`config/body_lists.py`定義body-lists/1.0與數字／英文編號；`functions/markdown_processing/body_lists.py`以補標題後的非##內文作起點，依同型相鄰（空白行忽略）或首項1/a前一個非空白行是##冒號標題建立群組。已產生###只用於維持重跑結果。數字與英文、大小寫及括號／點號類型分開，不把純數值當條列；單一-列表前綴、編號內空格及1. A.內層英文可識別，文字與編號原樣保留。

已有##只由內文起點回查：中間缺項、首項##1/a（另須核對前冒號標題）、末項下一個##的同型接續編號。整組都是##不主動分類。非接續編號的##／其他標題、HTML／管線表格、cannotfindtable、頁序／控制標記及程式碼為邊界，不跳過表格續找。成立後各項改###；群組可有中間說明段。找不到的編號寫跳號紀錄，不生成不存在的內容。

`note_processing`順序為限定note→疑似表格→原補標題→條列分類→清頁碼。Record的processing_scope.body_list_classification記version、changed_count、gaps；gap.line_number及新增HeadingChange映回原raw行號。前段補標題與後段條列可能對同一原行分別記錄兩次變更，表示處理順序；冒號合併／拆行映回原變更起行。cannotfindtable已保護的區塊不參與分類，短行先被候選包入時不會再標###。此階段的###表示條列正文分類，不代表新的hd階層，未修改tagged／chunk。

66項局部測試通過（條列9、heading38、疑似表格10、note3、冒號6），涵蓋首中末項回查、跳號不補造、內層英文、表格邊界、note範圍與冒號合併後原行號。2024_2330 raw記憶體試算28行改###，note前綴、HTML與Page保留，行號映射長度一致。未寫Output、未跑OCR／API，未完成人工分類準確率驗收；舊processed須重新執行第二階段才套用。

2026-10-25疑似表格最新1.1：連續5個候選行觸發，候選包含20個中文字以下的非空行、完整數值及金額碎片（獨立$、逗號、小數點、括號、負號、百分號）。空白行不計數也不中斷，觸發前超過20中文字重設計數；觸發後沿用連續3長正文行停止。原有##／表格／Page等保護邊界優先，仍只處理note後。不拼接碎片、不改數值及原文，共用is_numeric_line仍嚴格辨識完整數值，避免影響標題規則。

config改用CANDIDATE_RUN_LENGTH；Record報告欄位改為candidate_run_length，trigger改為5_consecutive_candidate_lines，以version=suspected-table/1.1區分歷史報告，Record仍不是核心輸入。短正文、日期、英文行在未超過20中文字時也會計數，候選不保證是表格。57項局部測試（疑似表格10、heading38、note3、冒號6）通過；2024_2330 raw原始1752–1809行（PDF頁58）稅額片段已在記憶體包入且note前綴一致。未寫Output／執行OCR或API，重新跑第二階段才更新產物；下方1.0敘述為歷史。

2026-10-25最新標題1.11：mark_missing_headings補標題分支比照既有##，忽略編號中的空白辨識；以非空白字元位置映回原文截取編號後內容，故原文、內容字數及句尾規則不變。例如「二十 、 權 益」「( 一 ) 普通 股 股本」會補##。仍限note後且保護表格等區域，未實作討論中的###條列分類。38項heading、6項冒號及3項note測試通過；2023_2330 raw記憶體驗證上述兩行已補上且note前保持一致。既有Output未重產生，使用第二階段重新處理才套用。

2026-10-25最新標題1.10：MULTI_YEAR_DESCRIPTION_PATTERN接受行首至少兩個以「及」相連的年度（112及111年度、112年度及111年度、民國一一四年度及一一三年度）及後續說明，整行加##，不要求冒號、不限字數／句尾標點。原年月日、純年度分類保持。冒號段落仍先處理，換行的多年度＋冒號說明可照原規則合併。

純數值排除在編號分類之前執行：只有數值、金額或百分比時不補##；已有恰兩個井號的Markdown標題則去除井號，保留數值／空白／換行。4.375%不再被拆成4.編號，但4.現金仍按既有編號規則。numeric_lines.py提供共用分類，suspected_tables引用同一函式。仍受note範圍及表格／疑似表格等保護限制；純年度及年月日因含年／月／日不屬純數值，依年度規則標##。偵測疑似表格仍在補標題之前，原raw已有##的數值行不會追溯納入本輪5行計數。55項局部測試通過，舊Output未重產生。

2026-10-25最新標題1.9：PURE_YEAR_PATTERN新增整行年月日形式，例如`112 年 12 月 31 日`、`民國112年12月31日`、`2023年12月31日`，與純年度同樣標##。比對時去空白，輸出日期字樣／空白保持；含敘述或點分日期不由此規則升格，未新增曆法合理性檢查。日期行也是冒號回收邊界，避免與下一段冒號說明合併。note範圍及表格／疑似表格保護仍優先，未擴充years／table_context。舊Output未重產生。

## 2026-10-25：第二階段疑似漏表格標記

`config/suspected_tables.py`集中5個數值行觸發、3個長正文行停止、20中文字及標記字串，規則版本suspected-table/1.0。`note_processing.process_note_content`先限定note後，再呼叫`functions/markdown_processing/suspected_tables.py`偵測，之後才補標題及清頁碼；批次CLI／網頁／單檔入口共用。

數值行須整行為數值及受支援金額符號，可有千分位逗號、$、括號負值、正負號、小數或百分比；英文敘述及混合文字不算。空白行不計數、不重設；非數值文字重設連續數值計數。達5行後連同前面的短項目／日期上下文開始包區塊。連續3個非空白行各自超過20個中文字時，在第一個長正文行之前結束；前後不作標點判定。短行／數值會重設長正文計數。只有1或2個長正文行、或英文長句，可能仍在候選內，不能視為精確PDF表格範圍。

遇##開頭、既有HTML／管線表格、Page／控制標記、註解、程式碼或可辨識頁尾立即結束，頁序保持且不跨頁累計。已存在的合法cannotfindtable區塊整段保護、不重複包，未閉合／多餘／巢狀標記拒絕處理。mark_headings._protected_lines將候選列為保護區，後續補標題及頁碼清理不改其原文；不將候選冒充正常table_start區塊。

輸出範例：

```text
<cannotfindtable>
疑似漏辨識表格的原文
</cannotfindtable>
```

Record位於既有實驗輸出位置，processing_scope.suspected_table_detection保存版本、門檻、candidate_count及candidates；各候選start_line／end_line為原始raw行號（含邊界內空白行），pdf_pages為已知原PDF實體頁序，另有trigger、stop_reason、added_eol。只在無EOF換行時補獨立結束標記所需換行，原文數值與內容保留。補標題變更行號透過偵測器line_map回到原始raw；removed_page_lines仍依補標題後（含新標記）的內容行號加note前綴偏移，不能與原始raw行號混用。

不增加外部依賴／API或模型呼叫；本偵測只是本機候選規則。後續依候選回PDF擷取、LLM辨識、跨頁疑似區塊串接及第三／四階段特別處理尚未實作。數值每2行就被項目名打斷的例子不觸發5行門檻，原本一列3金額的小表也不保證命中。尚未加入HTML重複內容去重。

驗證：63項局部測試通過，涵蓋分類、空白／短文字計數、三行長正文、保護邊界、note範圍、冪等與原始行號。台積電2021～2025既有raw記憶體處理成功，候選分別1／2／0／1／0（頁40；頁41與54；無；頁42；無）；HTML與Page及note前文均保留。未重跑PDF／OCR／API、未覆寫或新增使用者Output；這不是人工表格範圍或召回品質驗收。

最新第一階段選頁1.1（2026-10-24）：config/page_selection.py集中NFKC正規化方式、版本與主標比對規則；page_selection._compact僅在比對時轉換相容字元及移除空白，serialize原文不改。目錄可用時依頁碼；缺附註起頁則find_notes_in_body讀取正文，公司沿革可正規化命中，亦接受獨立合併財務報告／報表附註主標（可帶公司前綴、續、金額括註）。先跳過已知查核範圍；不採目錄／查核標題頁、受保護區或參閱／詳見句中的主標。無明確依據仍失敗，不使用其他章節組合猜測。OCR開關及原PDF頁序保持；每頁沿用既有轉換快取。Record新增selection_rule_version與comparison_normalization，selection.notes_source區分local_toc、company_history_fallback、notes_heading_fallback；定位失敗也保留已得selection資訊。

13項局部測試通過；真實2021聯電P2／P14用Docling試轉後，目錄及正文均定位14。以真實P14移除公司沿革行的模擬也通過主標備援；未重新跑整份財報、無新raw產物，舊失敗Record保留。

最新標題規則1.8：冒號收集除了空白行、編號及保護邊界，也停止於最近中文句號`。`，包括同一行。句號前文字依原編號／正文規則處理並保留，只將其後內容合併一行加##；必要時於句號後新增換行。ASCII點號（含1.、A.、1.5）不作此邊界。Record的單次冒號變更modified可能含前句與新增換行，原文及起行仍可追溯。42項標題、冒號及note範圍局部測試通過，尚未重寫使用者產物。

最新第二階段1.7：冒號段落不得跨編號項目合併。遇到現有行首中文／數字／英文編號時重新開始本項（辨識時略過單一-前綴及排版空白）；本項可以換行，收集至冒號，但不回收上一編號項。空白行、表格與其他保護邊界仍適用。標題規則版本1.7、note範圍1.0、頁碼清理1.1；38項局部測試通過。舊Output未重產生。整份文件空白清理仍在確認表格範圍，目前尚未實作。

本輪OCR核對：P4診斷為recognized_needs_review，實際辨識15個OCR區域；已成功載入並使用先前受阻的OCR元件。此結果不代表OCR文字或整份財報品質已人工核對。

2026-10-24最新表格設定：依使用者要求Settings.table_format由markdown回復html。2303原PDF P4開OCR頁段轉換成功，P42轉換成功且輸出1個HTML表格；本輪沿用.venv_pdf及本機快取、未改安全設定。這是局部試跑，整份未重跑、舊Output未改；不能斷言HTML更換是Windows不再封鎖的原因。下文預設管線格式是先前紀錄，相容讀取仍保留。

第二階段範圍（2026-10-24，note-only/1.0）：批次CLI／網頁及單檔--mark-headings統一由note_processing.process_note_content分段，只有唯一有效獨立`<note>`後套用標題規則1.6及頁碼清理1.1。標記及前綴原樣保留，查核報告頁尾也不清理；Page標記全保留。表格／程式碼／註解內的假note不作起點。缺失或重複標記會停止該份，批次只寫失敗Record，不產生Markdown，其他文件繼續；不得無標記時退回整份處理。Record新增processing_scope（版本、原始marker_line、first_content_line、prefix_preserved）；HeadingChange行號換回原始全文位置，removed_page_lines仍是補標題後內容的行號並加前綴偏移。load_source接受第一階段既有章節控制標籤出現在第一個Page之前，仍要求可靠頁序。

本輪47項局部測試通過；2303既有raw記憶體處理核對note前綴及95個HTML表格、81個Page完整保留。未重跑PDF／OCR／API，也未重寫既有Output。

最新第二階段1.6（2026-10-24）：整行純年度統一`##`（含舊####輸入），取代下方舊版純年度####。年度＋說明結尾冒號仍合併同段一行加##；附表單一#及表格／頁序保護維持。只調整標記，不擴充表格years或table_context綁定。既有Output尚未重產生。

## 2026-10-24：第二階段冒號段落及英文編號（1.5，現行）

行尾為`：`／`:`時，收集同段前方文字至空白行，去掉段內既有`##`前綴，多行用一個空格合併，整段前加`##`，不限制字數或要求編號。同段有多個冒號結尾時，合併至最後一個冒號行；其後普通文字保留。表格、程式碼、註解、獨立控制標籤／頁碼及附表／純年度特殊標題均為保護邊界。附表仍單一`#`、純年度依最新1.6使用`##`，Page標記完整保留。Record變更以原始Markdown起行、含內部換行的original及合併後modified記錄。

英文編號A.／a.／(A)／(a)（也接受全形配對括號）已加入，取消20字限制，仍要求編號後有內容且句尾不在EXCLUDED_ENDINGS。既有英文##若內容空白或以排除標點結尾，移除井號保留文字；數字／中文維持原處理方式及限制，未擴充1、或相鄰條列判斷。單一-列表前綴只在判定時略過、輸出保留。冒號段落優先，附表／純年度各自沿用特殊規則。

本輪36項標題與冒號局部測試通過。先前1.4以2303既有raw記憶體處理完成，41處冒號段落變更、95個HTML表格及81個Page原樣保留；該紀錄不代替本輪1.5驗證。未重新寫出2303輸出或呼叫模型、OCR、API，既有Output保留。

## 2026-10-24：Code與Code_2環境分開（現行）

**本輪實測結果：環境分離完成，OCR仍受Windows封鎖。** 新環境pip check、Transformers匯入與Docling真實版面／表格模型載入通過；2303第42頁實轉成功，38.543秒，8行管線表格，0個OCR區域。第4頁真正啟動OCR時，Shapely的lib.cp311-win_amd64.pyd遭原則0283ac0f-fff1-49ae-ada1-8a933130cad6封鎖。原環境同一Shapely檔亦無法匯入，且新舊SHA256一致；沒有改安全設定或替換OCR引擎。環境隔離只排除選用sklearn，不能解除Windows對必需Shapely的封鎖，因此不宣稱整份財報／OCR恢復。細節在maintenance/pdf_environment_validation.json。

CLI切換與網頁非HTTP局部測試12項通過；本輪未做真實瀏覽器操作、未重跑完整財報、未修改歷史Output。網頁與CLI入口已指向新環境，但OCR開啟時仍可能在上述必要元件停止。

- Code的四階段使用`Code/.venv_pdf/`（Python3.11.9）。`start-web.cmd`、網頁worker及CLI自動切換皆已改讀新環境；入口仍是原本`Code/start-web.cmd`。既有網頁服務需先關閉再重開，避免舊Python／已載入程式繼續使用。
- 原`Code/.venv/`及Code_2入口不改；本輪沒有卸載原套件，也沒有修改Windows安全設定。Code_2仍可能遇到原環境的scikit-learn封鎖，不能把PDF環境修復視為Code_2已驗證。
- 根因：Docling版面模型經Transformers的AutoModelForObjectDetection→generation→candidate_generator，探測到選用scikit-learn後匯入roc_curve，觸發Windows封鎖。PDF專用環境只安裝必要依賴，不安裝scikit-learn／sentence-transformers，不修改第三方套件或偽造套件可用性。
- 直接依賴見`requirements.txt`；新增SciPy1.17.1供Docling OCR區域偵測。`requirements.pdf.lock`是獨立PDF環境完整快照；舊`requirements.lock`保留為共享環境歷史版本。下方舊指令若寫`Code/.venv`，執行Code功能時改用`.venv_pdf`；Code_2指令仍用`.venv`。
- 重建時使用Python3.11建立隔離環境，不用`--system-site-packages`；模型快取沿用Code/.cache，不重複建立或刪除。

```powershell
py -3.11 -m venv Code/.venv_pdf
& .\Code\.venv_pdf\Scripts\python.exe -X utf8 -m pip install -r Code/requirements.pdf.lock --only-binary=:all:
& .\Code\.venv_pdf\Scripts\python.exe -X utf8 -m pip check
& .\Code\.venv_pdf\Scripts\python.exe -X utf8 Code/main.py --check-env
```

新raw Record的runtime_environment保存實際Python路徑，方便辨識來源。不要把Code_2依賴安裝到PDF環境，以免再次帶入非必要的scikit-learn。

## 2026-10-24：第一階段管線表格與章節標記（現行）

- 預設`Settings.table_format='markdown'`，由Docling官方MarkdownTableSerializer輸出`|`表格；HTML相容格式仍可讀。這是序列化格式更換，不會重建未辨識成功的表格。
- 不再保留或辨識原PDF第1頁封面；初始目錄探測只讀第2、3頁。輸出只含已判定查核報告範圍、附註起頁到末頁，來源Page保持PDF原始頁序，不重編。
- 查核報告首個Page前單獨寫`<會計師查核報告>`；附註起始Page前依序寫`<note>`、`<合併財務報告附註>`。標籤各自只寫一次，起頁沿用第一階段已確認的目錄／正文備援判定，不另猜範圍。例：`<note>`→`<合併財務報告附註>`→`<!-- Page: 2303_2025_P14 -->`。
- 目錄選頁支援HTML及管線表格。共用pipe_tables.py辨識表頭＋分隔列＋資料列；第二階段保護管線表格，第三階段包table_start／table_end，第四階段支援年度欄名、跨頁接表、完整父表及頁面子塊。只接受可辨識的表格語法，不把散落數字猜成表格。
- 管線表格沒有原生rowspan／colspan；Docling會按官方方式展平表頭／儲存格。含合併儲存格時Record的warnings提醒核對PDF。原始Docling結構仍在當次記憶體結果中，不新增長期結構檔；舊HTML產物保留。
- 此次未改第三階段MAIN_TITLE策略、第四階段公司沿革起點或Code_2索引；新raw章節標記不代表查核報告已納入chunk。執行前重啟既有介面；新輸出仍防覆寫，舊raw不會自動轉換。
- 本輪驗證含官方序列化（無模型）、模擬第一階段選頁與標籤，以及processed→tagged→chunk跨頁管線表格。未跑真實Docling／OCR，不能當作第42頁表格已修復。

## 2026-10-24：第二階段標題分類（現行）

頁碼清理追加（standalone-page-cleanup/1.1）：除原先獨立`- 15 -`外，也清除每頁最後一個非空白行中、純阿拉伯數字且等於該頁PDF實體頁序的行。頁序取自Page／舊PDF_PAGE標記；表格、程式碼及註解內、非頁尾數字、不相符頁碼與無可靠標記均保留。最後一頁同樣處理；不刪除來源Page註解。既有Output不自動更新，重新第二階段仍遵守防覆寫。

- processed規則markdown-headings/1.3：保護區外，無四種既有編號的一般`##`移除井號、保留文字；既有編號`##`保留，編號判定忽略排版空白。未變更原先補`##`的20字、標點、編號類型等規則，未加入英文編號或相鄰條列排除。
- 整行只有年度（例如`民國一一四年度`、`2025年度`），有無原始標題標記皆統一為`####`。含年度的說明句不適用；此標記不轉為hd章節。中文年度轉換及新的表格年度／table_context取法尚未在本輪擴充，不能把標記完成當成年度metadata已完成。
- 行首「附表＋中文編號」統一為單一`#`，不限20字；從第三階段移到第二階段。tagged 2.10只保留既有附表標記，舊processed若尚未有附表`#`，須重新由raw產生processed。表格、程式碼、註解原樣保護。
- 輸出命名、Record及防覆寫沿用原操作；未覆寫歷史Output。版本1.2／tagged2.9下方說明是歷史行為，以本節為準。本輪使用合成／暫存資料驗證，未重跑使用者財報或OCR。

2026-10-23 標題規則更新：markdown-headings/1.2對符合四類編號、非空、20字及標點規則的行補##，包含冒號結尾；已有Markdown標題不改。tagged 2.9另將保護區外行首「附表＋中文編號」標成單一#，完整保留長標題，不受20字限制；表格、程式碼與註解內不動。此節取代下方歷史colon_review規則。真實Docling／OCR未重跑，歷史產物不改寫。

## 最新chunk 2.0：附表父子與內容年度（2026-10-23）

- 入口、批次／檔名及防覆寫沿用原操作。需重新由processed產生tagged 2.9，再切chunk，才能取得新附表標記；原來沒有#的舊附表文字不猜識別。同批同名產物已存在會阻擋，不自動覆寫。
- JSON版本financial-chunks/2.0：chunks是供embedding的文字塊與表格頁面子塊；parents保存完整表／完整附表。新增parent_id、part_index、table_context、appendix_id、year_sources；一般文字的parent_id為null。父項識別為doc_id__t00001，子塊維持doc_id__c00001。Markdown按子塊顯示，列父項識別；完整父項內容在JSON parents，不額外重複整張表。
- 由#附表一開始至下一個不同編號的#附表標題，所有表格、說明與單位歸同一父項；同號跨頁重列仍歸原父項。不同附表不合併。一般表格維持接次頁／承前頁任一詞忽略空白判接續；附表標記優先阻止跨附表接表。父項按可靠Page分子塊，不拆HTML列；沒有可靠分界則保留整段並在JSON issues與Record回報unresolved_page_boundary。
- table_context為檢索說明，並非正式表名：往前跳過表格、頁碼、控制標記及空白；第一個標題（hd或Markdown）作脈絡；先遇正文就停止留空。表格內／程式碼內標題不當脈絡。原章節樹仍保留。
- years是唯一內容年度清單：文字用文件年；含表格用前置標題與HTML首列／th明列的期間，民國年轉西元，保存原文與判定來源；沒有則回到文件年。不是掃描全表任意金額或正文交易日期。表格子塊沿用完整父表年度；附表純文字子塊用文件年度。years不是把表格各欄金額自動對應年度的能力。
- functions/chunking/table_metadata.py管理年度與附表標題辨識，table_parents.py管理前置脈絡、父項及按頁子塊；chunks.py保留文字切分與來源覆蓋驗證，batch.py紀錄父項數及待核對問題。原Reference Sources/Financial_RAG_Core/Function/chunk_hierarchy.py只有章節堆疊／年度脈絡概念；本次未匯入或複製，原來源commit未知。
- 記憶體實際樣本：2330得到183子塊／83父表／7附表，2379得到167子塊／79父表／8附表；範圍內96／86個HTML表格逐字保留，接Code_2前處理通過。同步修正chunk起點接受已確認的「公司沿革與業務範圍」，以及正文中的下層標題跨頁時保存其頁序。未寫歷史Output、未執行OCR或真實embedding／API；年度與接表語意仍待人工核對。
- 可用 `Code/.venv/Scripts/python.exe -X utf8 Code/tests/validate_parent_samples.py` 重跑上述兩份唯讀記憶體核對；不寫Output或啟用模型。局部測試與限制見USER_STORIES本節，後續舊版chunk 1.x說明為歷史行為，以此2.0章節為準。

## 本機網頁介面（四階段）

在檔案總管雙擊本目錄的 `start-web.cmd`，會使用既有 `Code/.venv` 啟動服務並開啟預設瀏覽器，不需操作命令視窗。不新增套件，不設定開機啟動。也可執行 `Code/.venv/Scripts/python.exe -X utf8 Code/web_main.py`。

1. 選擇 PDF → Markdown、整理 Markdown、加上標籤、切分 chunk 其中一頁。
2. 四個階段都可展開資料夾勾選個別檔案，或勾資料夾全選所有子資料夾的有效來源。半勾表示部分選取；可搜尋名稱、只看已選／未選、勾選或取消篩選結果。搜尋會自動展開相符路徑。資料夾全選包含被搜尋隱藏的後代；「勾選篩選結果」只套用符合篩選的檔案。切階段及更新清單保留仍存在的已選項目；重新載入頁面會重設選取。
3. 確認「已選」清單後按執行。PDF 頁提供既有 OCR 開關，預設關閉；其餘模型、命名、來源驗證、防覆寫及處理參數沿用既有程式。
4. 第一階段本機讀第 2 頁及可能的第 3 頁目錄，選出首頁、會計師查核報告及附註至最後一頁；第二階段只在本機補標題、清頁碼，不呼叫 Gemini。錯誤按同批 Record 保存，`needs_review` 仍需人工核對。工作程序異常退出可能沒有新 Record，不能把殘留產物當成功。
5. PDF → Markdown 會同時顯示所選批次的檔案進度與 Docling 回報的逐頁進度，包含目前第幾份 PDF、完成頁數、目前處理頁及頁面成功／失敗狀態。每份財報完成後另顯示處理耗時、PDF 頁數／分鐘、OCR 區域數、OCR 區域／分鐘，以及實際使用 OCR 的 PDF 實體頁序（該頁至少有一個 OCR 區域）；兩種速率皆以該份總處理耗時為分母。OCR 關閉時標示未啟用，診斷資料未取得時不以 0 代替。未完整完成的檔案只顯示已取得耗時，不計算整份速率。其他階段按檔案／批次顯示進度。完成後按「開啟本階段輸出資料夾」，查看既有輸出與各批 Record。
6. 關閉分頁或重新整理不會停止服務／轉換。使用完請按「關閉服務」；執行中會阻擋關閉，須等工作結束。本版沒有強制中止按鈕。不終止其他 Python 程序。

同一服務一次執行一個工作，所選資料依序處理，四階段各自啟動，不自動串接到下一階段。請勿重複雙擊另開多個服務同時處理相同資料。介面只綁定 `127.0.0.1`，埠由系統分配，具來源清單驗證、請求權杖及 Origin／Host 檢查；不是公開網站。

維護：`web_main.py` 為入口；`config/web.py` 管理網頁參數；`functions/web_ui/catalog.py` 管理清單與來源白名單；`server.py` 管理本機請求與單工狀態；`worker.py` 在獨立 Python 程序呼叫既有四階段入口；`index.html` 與 `selection.js` 提供資料夾樹及選取介面。網頁不自行寫 Output；worker 的 raw 批次配置標記 `EXPERIMENT_ONLY`，實際產物仍由既有 `functions/experiments/export_output.py` 寫入。

### 資料夾與個別檔案（2026-10-23）

- PDF資料夾放在`Financial Statements/`內，按「更新清單」，用箭頭展開或直接勾資料夾。後三階段來源仍是相應`Output/markdown_raw`、`markdown_processed`、`markdown_tagged`下合法Financial批次，批次內可以含子資料夾。只列該階段後綴的Markdown，Record不列為來源；不提供任意電腦路徑選取或檔案上傳。
- 可用「展開全部資料夾／收合全部資料夾」，收合不取消選取；已選清單列完整相對路徑。資料夾的半勾表示部分子檔案被選；執行進度及數量以檔案計。空資料夾或沒有本階段來源的資料夾不顯示。
- 後三階段呼叫既有核心的`source_files`子集入口，只處理勾選檔案；未選檔案及它的既有輸出不影響本次。輸出仍沿用Financial批次名稱與年度_代號命名，不改成按子資料夾建立另一套輸出。相同批次若所選年度＋代號重複會先拒絕，既有有效輸出仍防覆寫。
- `functions/markdown_processing/batch_selection.py`共用來源篩選；CLI未指定source_files時沿用原批次第一層的全部來源。第三階段需要的既有目錄JSON從processed檔案同目錄配對，不新增Gemini呼叫。程式不建立新資料傳遞用Record。
- 本次Python局部測試及Node頁面render／事件測試通過，含嵌套資料夾、勾選子集的真實本機三階段、未選輸出不阻擋、同批撞名拒絕及篩選下資料夾全選。Node測試不等於真實瀏覽器視覺驗收；本輪未啟動OCR、API或轉換使用者PDF。

本機介面沿用 Docling `page_completed` 回呼顯示實際頁面事件。選頁後 Docling 分段處理，進度分母代表目前頁段，不代表全 PDF。每份 raw 結果彙整 `elapsed_seconds`、實際保留頁數及 OCR 診斷中的區域總數，計算頁數／分鐘與區域／分鐘；速率採總處理耗時，不代表 OCR 模型本身的純推論速度。OCR 關閉或診斷缺失分別標示未啟用／未取得。

### 2026-10-23 本機選頁流程（新產物；舊批次不改寫）

第一階段先用 Docling 處理 PDF 第 1～3 頁以辨認目錄是否只有第 2 頁或延續到第 3 頁。從目錄表格頁碼欄取得會計師查核報告的連續範圍與附註起頁；附註主列沒有頁碼時取目錄中「公司沿革」的起頁。目錄不可用則從可能的目錄頁後尋找正文首次「公司沿革」。查核範圍不可用時依序找正文查核報告標題至資產負債表前、再找勤業／資誠／安永／安侯首次至末次命中頁，後者須人工核對。備援搜尋在 OCR 開啟時由 Docling 按需辨識候選頁；OCR 關閉時只讀 PDF 原生文字，必要頁沒有原生文字、範圍不明或重疊就讓該份失敗且不輸出 raw Markdown。

保留首頁、完整查核報告範圍及附註起頁至 PDF 最末頁。新的 raw 保留原 PDF 實體頁序標記，不重編；同批 Record 的 `selection` 記目錄頁、判定來源、查核範圍、附註起頁與保留頁。第一階段不再輸出新 `Financial_Table/*_table.pdf`，第二階段不再產生新 `*_tablerefer.json` 或呼叫 Gemini。舊的檔案與參考模組仍留存，既有批次不自動遷移。第三階段在無目錄 JSON 時沿用公司沿革的暫時大標備援；需人工核對標題語意。舊版目錄／Gemini 詳述在下方屬歷史紀錄，並非現行入口。

本次已用既有 2025 年 2330、2379 raw Markdown 模擬 Docling 頁段回傳：分別得到目錄第 2 頁／第 2～3 頁、查核第 4～7 頁／第 5～8 頁、附註從第 15 頁開始，保留 76／70 頁。未重新跑真實 Docling 或 OCR；效能、特殊版面與安侯建業樣本仍待實測。

目前本機選頁 3 項單元測試與網頁不要求 Gemini 確認的測試通過；整套舊測試尚未調整完畢，仍有測試預期原先 Gemini／固定抽頁流程。另有本機 HTTP 測試遭 Windows `WinError 10013` 阻擋，不能把整套測試稱為通過。

### 2026-10-23 Record 與階段資料契約

第二階段直接讀 raw Markdown 的檔名與遞增 PDF 頁序，補標題、清頁碼；第一階段 Record 的 `selection` 僅作選頁來源報告。沒有 `selection` 的舊 raw 可處理，processed Record 的 `selection_status=unverified_legacy_raw` 明確表示未驗證新版選頁。沒有相應 Record、紀錄損壞或紀錄雜湊不一致時會記 `source_record_issue`，不直接當成正文錯誤；無效頁序與資料格式仍失敗。若同名目標只剩一份同來源失敗紀錄且沒有有效 Markdown／目錄 JSON，會封存該失敗紀錄再輸出；已存在有效產物仍不覆寫。

第三階段從 processed Markdown 產生 tagged，新 tagged 第一行含 `<!-- TAGGING_VERSION: markdown-comment-tagging/2.8 -->`；chunk 以此判定相容處理，舊無版本 tagged 則依實際空 hd 與頁首重列標題辨識舊格式。第三、四階段 Record 僅用於可選的來源核對與人工追溯。既有目錄 JSON 若提供仍會經結構驗證；其與舊 Record 的 PDF 雜湊不同時記 `toc_record_issue` 供核對，不把舊報告當成唯一來源契約。

既有 `Financial_20261023_17-27-05` 的 2379 raw 已完成本機第二階段，輸出 `Output/markdown_processed/Financial_20261023_17-27-05/2025_2379_processed.md`；Record 顯示 `processed_needs_review`、`unverified_legacy_raw`，輸出雜湊吻合。這份仍保留舊 raw 全頁內容，並非重新執行第一階段選頁。針對性 3 項 Record 獨立性測試、chunk 20 項、tagging 18 項通過；全套 Code 舊測試仍含已停用 Gemini／固定抽頁預期，未全過。

本機介面先前驗證：新增 `tests/test_web_ui.py` 的 5 項測試通過，涵蓋來源越界、批次清單、請求權杖／Origin、工作中禁止關閉、四階段模擬串接、OCR 設定傳遞、部分失敗及防覆寫回報。實際瀏覽器已核對四頁清單、搜尋後勾選與清除搜尋仍保留選取。沒有呼叫真實 Gemini、執行完整 PDF／OCR 或重寫既有成果；這是新介面驗證，不宣稱重新驗證財報轉換品質。

2026-10-22：新embedding前處理依使用者指示獨立放在[Code_2](../Code_2/README.md)。本目錄繼續負責PDF至chunk，不匯入Code_2或更換既有參數。

專題想法、需求與待確認事項見 [USER_STORIES.md](../USER_STORIES.md)，功能流程圖見 [FLOWCHART.md](../FLOWCHART.md)，AI 開發規範見 [AGENTS.md](../AGENTS.md)。本文件記錄實際操作、環境與驗證；流程摘要不取代需求文件。

目前第一、二階段主流程：完整 PDF 作為唯讀來源 → 本機 Docling 讀取目錄並選出首頁、查核報告與附註頁 → 保留原 PDF 頁序的 raw Markdown → 本機補標題與清理頁碼 → 人工檢查。後續標籤與 chunk 仍是獨立階段；本流程不呼叫目錄 Gemini。

## 第四階段：tagged → chunk Markdown／JSON（2026-10-22）

正常啟動後選「6」，再選tagged批次；也可使用：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code/main.py --chunk-batch "Output/markdown_tagged/Financial_20261022_01-23-16"
```

輸出位置（沿用來源批次名）：

```text
Output/markdown_chunk/Financial_20261022_01-23-16/
├─ 2025_2330_chunk.md
├─ 2025_2330_chunk.json
└─ Record/2025_2330_reocrd
```

- 從hd2公司沿革開始，前段不輸出；只整理chunk，不改tagged。缺起點、識別不符、缺Record或來源雜湊不符時只留待確認紀錄。相同目標已存在會阻擋，不能直接覆寫；本次實際樣本已輸出，勿把再次執行被阻擋視為解析失敗。
- Markdown呈現chunk-markdown/1.1：新塊若從既有小節中間開始，補上當時繼承的hd3／hd4等祖先；文字塊放content起點內，表格塊放table_start之前，不改表格HTML。後面才出現的子標不移到前面，原content已含的新小標不重列。JSON schema／欄位／content與切分結果不變，額外呈現脈絡只在記憶體交給render_chunks，不增加JSON欄位；Record記錄markdown_format_version。
- 本次呈現修正167項測試通過，涵蓋跨切點祖先補齊、不提前子標與不重複新標題。既有176塊Markdown已更新並同步Record雜湊，JSON逐位元保持相同、tagged來源雜湊保持相同；所有原content仍包含於Markdown，HTML本體未改。此次未呼叫API或重做切分。
- hd2放每塊Markdown第一行，強制切開前塊；下層hd放進content，未滿1000字不因下層標題切開。表格獨立完整一塊，不受文字上限影響；接次頁／承前頁任一詞忽略空白後觸發相鄰表格接續，多頁table保存全部HTML及中間原文，不拼接欄列或刪表頭。
- 達1000個正文可見字元後，等content_end再切。若達門檻頁是P35，直到P37仍未結束，才在其後第一個中文「。」切；半形小數點不切。無句號仍等後續content_end、hd2、表格或EOF。1000是觸發門檻，實際chunk可超過1000；標題／空白／標籤不計，HTML實體解碼計字。
- JSON根有schema_version、rule_version、doc_id、source_sha256、excluded_prefix_end與chunks；每塊有chunk_id、doc_id、years、page、title、data_tags、content_type、content、body_char_count、source_spans、cut_reason。title.main_title保存大標；title.heading是level=2的根節點，text與children遞迴表示子標題。當切點位於小節內，JSON仍保存當時祖先路徑，不把最後一個小標誤當整塊標題。
- doc_id依本次使用者指定為年度Q4_代號_Financial_Report；years來自Page年份，不從內文提及年度改寫。page是PDF實體頁序清單；source_spans是原tagged文字的Unicode字元[start,end)位置，不是UTF-8 byte或PDF座標。data_tags先空清單。chunk_id為doc_id__c00001順序號，相同來源與規則重跑可重現；變更文件／規則後編號可能位移。
- 舊2.4／2.5頁首快照與空hd按Record版本在記憶體辨識，不當新章節；chunk端可把舊tagged分開包裝的接續表格合回同一塊。tagged最低支援2.4，頁碼需有股票代號與年份；不猜舊XML或沒有識別資訊的PDF_PAGE。來源檔不改寫。
- 未辨識Markdown標題保留，不計字數；單獨表格說明可保留為字數0但內容非空的文字chunk。正文來源覆蓋檢查可攔截遺漏，表格各片段均有來源區間；metadata不當財務正文。未建立embedding，也未把整份JSON當embedding內容。
- `--no-export`可合用，只回傳記憶體，不建立chunk目錄；核心chunks.py與parser.py不依賴Output。已有有效成對產物不覆寫；單份失敗繼續其他文件，中止停止後續。成對檔案寫入失敗／中止會清除僅本次建立的半份檔案，Record標示失敗，不能當成功。

維護分工：config/chunking.py集中門檻、頁數與句號設定；functions/chunking/parser.py解析頁／內容獨立狀態與舊格式；chunks.py追蹤堆疊、切塊及schema驗證；batch.py驗證來源與串接。schema為financial-chunks/1.0，規則為heading-content-chunks/1.0。參考本機Reference Sources/Financial_RAG_Core/chunk.py與Function/chunk_hierarchy.py、chunk_parser.py、chunk_results.py、chunk_form.py的分工／堆疊原理重新實作；未複製舊碼、未改參考原檔，原GitHub網址／commit未知。

EXPERIMENT_ONLY清單追加：export_output.py的chunk_run_paths／export_chunks，呼叫位於chunking/batch.py；設定Settings.export_enabled與markdown_chunk_output_dir；產物為上述MD／JSON／Record。日後移除實驗寫檔時調整batch呼叫與輸出設定，保留parse_tagged／chunk_tagged的記憶體結果；目前不刪除任何既有實驗資料。

本次166項測試通過，含實際抽頁等既有測試及chunk合成測試；新chunk測試涵蓋標題樹、1000字等待、P35→P37中文句號、半形小數點、跨頁表格、來源錯配、舊快照、雙檔與Record、防覆寫、停用寫檔、中止與失敗。實際讀取既有2.4 tagged，已輸出176塊（92文字、84表格），P15至P85，共96個納入範圍的原HTML表格逐字核對相同；其他8個HTML表格在公司沿革前，按已確認範圍排除。最長文字塊1677字，符合等待content_end規則；本樣本未觸發跨頁句號切點，該路徑以合成P35／P36／P37測試驗證。非空正文來源覆蓋、正文字數、MD／JSON來源與輸出雜湊均已核對。未改tagged／processed、未呼叫API／OCR或執行embedding；標題語意與接表正確性仍待人工核對。

## 第一階段批次輸出（2026-10-21 更新）

2026-10-22 `Output/markdown_chunk/`已接上本機切塊，輸出同批Markdown／JSON與Record；操作與驗證見下方第四階段。

本節取代下方歷史說明中的 docling 時間戳目錄與雙 Markdown 輸出安排。一次單選／多選為一批；同批先後處理，並非平行執行。

```text
Output/markdown_raw/
└─ Financial_20261022_16-01-35/
   ├─ 2025_2330_raw.md
   ├─ 2025_2317_raw.md
   ├─ Financial_Table/
   │  ├─ 2025_2330_table.pdf
   │  └─ 2025_2317_table.pdf
   └─ Record/
      ├─ 2025_2330_reocrd
      ├─ 2025_2330_reocrd.ocr
      ├─ 2025_2317_reocrd
      └─ 2025_2317_reocrd.ocr
```

- 批次名稱採開始時的台灣日期與24小時制時間，例如`Financial_20261022_16-01-35`，格式為`Financial_YYYYMMDD_HH-MM-SS`，不再產生流水號。跨午夜仍沿用同批名稱；同一秒目標已存在時明確停止，不覆寫、不補流水號。processed、tagged沿用來源批次名稱，不另取各自執行時間；舊流水號來源仍能讀取、原名保留。
- 命名格式與新舊名稱讀取規則集中於`Code/config/output_layout.py`；固定`Financial_Table`與`Record`子目錄名稱不變。既有獨立目錄／舊相容入口本來就是時間命名，本次不遷移或改寫其歷史資料。
- 此次命名更新後123項測試通過，覆蓋台灣時區與午夜換日、秒數命名、同秒碰撞不覆寫、新舊名稱清單辨識，以及新名稱來源到processed／tagged的串接。未重跑真實Docling或呼叫API，未改名歷史資料。
- `_raw.md` 為原先 `_document.md` 的頁序檢查版，保留 HTML 表格及 `PDF_PAGE`；不再輸出另一份無頁序 Markdown，核心記憶體仍保留原始序列化資料。
- 頁序格式最新更新：有可靠檔名識別的財報，第一階段直接輸出 `<!-- Page: 2330_2025_P2 -->`（股票代號_年份_P實體頁序），後續 processed、tagged 原樣保留。讀取入口同時接受新格式與歷史 `<!-- PDF_PAGE: 2 -->`，不改寫舊產物。這是實體頁序，不是印刷頁碼。
- 此格式更新後全套111項測試通過，新增三項覆蓋Docling序列化的新格式、來源識別核對、raw選單與tagged保留新標記。使用合成Docling結構，未重跑完整財報OCR；舊輸出不因格式更新而重寫。
- `Financial_Table/` 只保存原 PDF 實體第 2、3 頁；不在第一階段呼叫 Gemini，不產生目錄 JSON，也未確認抽出的頁面一定是目錄。PDF 不足 3 頁時明確失敗。
- Record 兩種檔案皆為 UTF-8 JSON，`reocrd` 為指定拼字；執行紀錄保存批次路徑、來源雜湊、狀態及頁序，診斷檔在有收集到欄位時才輸出。
- 2026-10-22修正：raw執行紀錄與OCR診斷改到批次內Record，output_layout為financial-batch/1.1。同一份財報可在不同時間批次各自保存紀錄，不再被外層舊Record的同名檔阻擋；同批既有結果仍不覆寫。
- 此次修正125項測試通過，新增回歸案例涵蓋同財報跨兩個時間批次各自保留紀錄／OCR診斷、舊共用紀錄不阻擋新轉換、同批重跑防覆寫、優先讀批次內Record及舊位置回退時拒絕錯批次。使用合成PDF與模擬Docling／Gemini，未呼叫真實API或重跑完整財報，未刪除歷史紀錄。
- 單份失敗仍可保存抽頁與失敗紀錄，但不產生假成功 Markdown；使用者中止時，後續批次停止。底層程序崩潰仍可能來不及保存紀錄。
- 舊輸出未搬移或刪除；後續選單支援舊 document 與新有頁序 raw，舊無頁序 raw 不會因此被自動列入。多份結果的資料夾需要明確選擇檔案。
- EXPERIMENT_ONLY 清單追加：`create_markdown_batch`、`markdown_run_paths`、`check_markdown_paths`、`export_markdown_run` 及 main 中批次配置／寫檔呼叫；集中停用 `export_enabled` 後不建立上述目錄，核心仍回傳 Markdown 與本機抽頁結果處理狀態。
- raw、processed、tagged現在皆在各自Financial批次內保存Record。歷史外層raw Record保留原狀；processed優先讀同批Record，只有新位置不存在才相容讀取外層舊Record，仍核對batch_dir、狀態、來源與PDF雜湊，錯批次不傳送API。紀錄中origin_record可核對實際來源。

本次驗證：`Code/.venv/Scripts/python.exe -X utf8 -m unittest discover -s Code/tests -q`，95 項通過。新增驗證使用合成三頁 PDF 真實抽出第 2、3 頁，Docling 轉換以記憶體結構模擬；涵蓋同批多份、跨日流水號、原始 PDF 未變、頁序 raw 原文不變、集中紀錄防覆寫、舊格式載入及中止後停止後續文件。未執行真實 Docling／OCR 全文辨識，未呼叫 Gemini；既有 Gemini 測試使用模擬服務。

## 第二階段批次補標題與目錄解析（2026-10-21）

正常啟動後選「3」，再選一個 `markdown_raw/Financial_日期_時-分-秒/` 批次。所有 `_raw.md` 依序處理，完整正文保留、不刪除會計師報告與四大報表。補標題規則不變，HTML 表格原文保留。

頁碼清理已移至此階段：補標題後移除表格／程式碼以外獨立成行的 `- 1 -` 等頁碼，保留新 Page 與舊 PDF_PAGE 來源標記及財務數值。`page_cleanup.py` 為純記憶體核心，processed Record 保存 `page_cleanup_version` 與 `removed_page_lines`；因補標題不增減行數，刪除行號仍對應來源 raw。Gemini失敗仍輸出已清理的 processed。舊 --mark-headings 也套用此清理。tagged 1.2 起不再清頁碼，未清理的歷史 processed 不會被偷偷改動；需依授權的重跑方式處理，既有檔案與紀錄不覆寫。

此次調整完整113項測試通過，包括新舊來源頁序、表格／程式碼保護、財務負值、CRLF行尾、清理重跑無新增刪除、Gemini模擬失敗仍保存清理結果，以及tagged不再刪頁碼。未呼叫真實API、未改寫歷史產物。

```text
Output/markdown_processed/
└─ Financial_20261022_16-01-35/
   ├─ 2025_2330_processed.md
   ├─ 2025_2330_tablerefer.json
   ├─ 2025_2317_processed.md
   ├─ 2025_2317_tablerefer.json
   └─ Record/
      ├─ 2025_2330_reocrd
      └─ 2025_2317_reocrd
```

也可指定批次：

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py --process-batch "Output/markdown_raw/Financial_20261022_16-01-35"
```

- 每份只將同批 `Financial_Table/年度_股票代號_table.pdf` 送至既有 Gemini 3.1 Flash-Lite 介面，先驗證 raw 階段 Record 的批次、成功狀態、來源頁序與 PDF SHA-256。來源紀錄缺失／不符則不傳送，不猜配其他批次、不重新抽原始 PDF。
- 2026-10-22 起Gemini僅擷取目錄大標MAIN_TITLE，新提示詞toc-main-titles/2.0、新JSON financial-toc/2.0並標記extraction_mode=main_titles。parent_id、note_numbers一律留空；不輸出公司沿革等子項。大標未列頁碼時，允許從所屬子項實際頁碼取聯集，不填補不連續頁碼的空缺。原始回覆仍需人工核對。
- 使用既有 `.env`／環境變數金鑰規則、8192 輸出 token 上限、120 秒逾時；HTTP 503最多重試3次，依序等待5、10、20秒，連同首次最多4次請求。不外傳正文 Markdown。
- 重試只重送已抽出的同一份PDF，不重跑Docling／OCR；429、其他HTTP錯誤、逾時、連線失敗、錯誤JSON或辨識不完整不重試。Gemini回應收到不等於目錄驗證成功。`config/toc.py`集中設定重試上限、間隔與503狀態碼；將retries設0可停用。
- `gemini_attempts`保存每次請求結果與等待狀態，寫入processed同批Record；獨立選單5則寫入manifest。Ctrl+C可中止等待，processed保留補標題Markdown並停止後續文件，不留下假成功JSON。132項測試通過，重試等待及HTTP均為模擬，未讀取真實金鑰、未呼叫真實API。
- 本次自動重試針對當次執行；已存在的失敗批次仍不會被覆寫，也未新增重跑失敗批次的入口。
- 目錄只做既有 schema 驗證，不推算附註正文邊界。只有 `extracted_needs_review` 才輸出 `tablerefer.json`，仍需人工核對。
- API 失敗或缺金鑰：畫面顯示「Gemini 呼叫失敗」及原因，紀錄 `processed_toc_failed`，已補標題的 Markdown 仍保存。未找到目錄、截斷或無法辨識也保留 Markdown，記錄具體狀態，不產生假成功 JSON。
- 單份失敗繼續其他文件；Ctrl+C 記錄 `interrupted`，保留已完成補標題並停止後續文件。若補標題本身失敗或來源 Markdown 中途改變，則不輸出該份處理結果。
- 同批次內 `Record/年度_股票代號_reocrd` 為 UTF-8 JSON，包含變動、來源與輸出雜湊、設定、提示詞版本、API 原始回覆、用量、模型版本、耗時及錯誤。缺少有效 API 回覆時該欄位為空，不寫入金鑰。此追加調整只影響 processed，raw 的 Record 仍位於 markdown_raw 下。
- 已存在 processed、tablerefer 或集中紀錄時，在整批開始前停止，避免已知覆寫與額外費用；失敗後的重跑／覆寫策略尚待另行決定。
- `--no-export` 可與 `--process-batch` 合用，只停用寫檔，仍會呼叫 Gemini。核心回傳補標題與目錄記憶體結果。
- 舊 `--mark-headings` 保持單純本機補標題，仍使用舊輸出方式；選單 5 保留獨立的舊目錄流程。舊 raw 輸出不自動遷移，新選單 3 僅接受新批次與來源紀錄。
- EXPERIMENT_ONLY 清單追加：`processed_run_paths`、`export_processed_run` 及 `process_raw_batch` 中的呼叫；輸出可集中停用。`process_batch.py` 負責新階段串接，`load_prepared_toc_pdf` 驗證既有兩頁 PDF。

本次全套 `unittest discover -s Code/tests -q` 共 102 項通過，其中新增第二階段 6 項串接測試及既有抽頁載入驗證 1 項。測試使用合成 PDF 與模擬 Gemini，涵蓋成功、失敗後保留 Markdown／繼續其他文件、截斷、無目錄、無法辨識、抽頁被改動、中止、防覆寫及停用實驗寫檔。未呼叫真實 Gemini、未執行整批財報或重跑 OCR，不能當成真實目錄品質通過。

## 第三階段：單行註解標籤（2026-10-21）

正常啟動選「4」，再選 processed 的 Financial 批次；或使用：

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py --tag-batch "Output/markdown_processed/Financial_20261021_002"
```

讀取同批 `_processed.md`、`_tablerefer.json` 及 Record 來源驗證，輸出至 `Output/markdown_tagged/同名Financial批次/年度_股票代號_tagged.md`，紀錄放該批次 `Record/年度_股票代號_reocrd`。不使用 LLM、OCR 或網路。

暫時備援（markdown-comment-tagging/2.3）：Gemini失敗（processed_toc_failed）、目錄JSON缺失或無效時，選單4／--tag-batch仍可執行。只從正文##找公司沿革（允許中文編號及空白），該頁整頁至文件結尾沿用大標；最新2.7僅在起始頁的Page之前輸出一次 `<!-- MAIN_TITLE: 合併財務報表附錄 -->`，前段不輸出空白大標、後續不重列。上一頁先page_end閉合，再列MAIN_TITLE、Page、page_start，避免大標落入上一頁。有效JSON的正常大標輸出規則維持原樣。hd2、動態下層及表格／內文／頁面標籤不變。表格、程式碼與註解不參與定位；找不到起點或來源不符則只記待確認，不輸出tagged。不呼叫Gemini，也不補寫tablerefer JSON。

維護：`Code/functions/markdown_processing/temporary_main_title.py`及其呼叫以TEMPORARY_FALLBACK標記；開關、標題文字及規則版本集中`Code/config/markdown_tagging.py`，停用TEMPORARY_MAIN_FALLBACK_ENABLED即回到無目錄時待確認。後續替換規則只需調整該模組與comment_tagging呼叫，保留JSON正常分支。Record狀態為`tagged_temporary_fallback_needs_review`，另記fallback_reason／main_title_source，issues記錄起訖頁與來源行；CLI與選單會區分正常及備援結果。既有輸出仍不覆寫。

本次136項測試通過，涵蓋整頁起點、空白編號、保護區、不誤配來源與缺起點。最新失敗批次Financial_20261022_01-23-16另以記憶體實測，定位實體第15頁至第85頁，104個HTML表格原樣保留、來源未變；未寫入歷史Output、未呼叫API，實際語意範圍仍需人工核對。


```markdown
<!-- REPORT_YEAR: 2025 -->
<!-- STOCK_CODE: 2330 -->
<!-- COMPANY_NAME:  -->
<!-- PDF_PAGE: 15 -->
<page_start>
<!-- MAIN_TITLE: 九、合併財務報告附註 -->
<hd2>一 、 公司沿革</hd2>
<content_start>
原始正文……
</content_end>
<hd3>(一) 編製基礎</hd3>
<content_start>
編製基礎的說明……
</content_end>
<table_start>
<table><tr><td>表格內容</td></tr></table>
<table_end>
<page_end>
```

- 每行一個標籤；MAIN_TITLE與其他metadata維持註解，小標使用hd2、動態下層從hd3起。不再把整份 path JSON 塞進 HTML 屬性，不產生大量 `&quot;`。tagged 2.4直接以hd取代已辨識的##行，標題文字保留在hd內；其餘正文、頁碼行與HTML表格不刪改；獨立頁碼清理由前一個 processed 階段負責。
- 2.7驗證：141項測試通過；確認暫時備援大標位於上一頁閉合之後、起始Page之前，後續不重列。最新2025_2330純記憶體核對MAIN_TITLE只出現1次且緊接第15頁Page之前，104表格與processed來源保持不變；未呼叫API、未覆寫既有產物，重新產生tagged才套用。
- 2.6更新與驗證：頁首不再重列hd2，換頁時保留內部動態層級。每頁先輸出原Page（兼容PDF_PAGE）再輸出page_start；上一頁page_end位於下一個Page之前。140項測試通過，涵蓋跨頁hd4／hd5延續、空頁及無換行的末頁標記。最新2025_2330純記憶體核對85頁皆為Page→page_start，104表格原樣保留，公司沿革與會計政策hd2各只出現一次；未改processed或覆寫歷史tagged、未呼叫API。既有tagged需重新產生才會套用。
- 2.5移除空白hd標籤：進入新小標或大標時，內部堆疊照常重置，但不輸出空白hd3；目前無小標時不輸出空白hd2。最新2.6取消頁首重列hd2，同大標跨頁仍延續內部階層。138項測試通過，涵蓋重置後不沿用舊路徑、動態類型重新分配及無空hd。最新2025_2330純記憶體核對空hd為0、104表格原樣保留、processed來源未變；未呼叫API或覆寫既有tagged，須重新產生才套用新格式。
- 2.4本次驗證：137項測試通過，涵蓋hd2至hd5直接取代、未辨識標題與保護區保留、跨頁及暫時備援。最新2025_2330僅在記憶體核對，「公司沿革」原##已由hd2取代，85個來源頁序與104個HTML表格原樣保留；processed來源未變，未覆寫歷史tagged、未呼叫API。Record的heading_policy記錄替換策略。新格式需重新由processed產生；已存在的目標仍受防覆寫保護。
- 2.2格式更新：`<hd2>一、會計政策</hd2>`取代SUB_TITLE註解，HEADING_1／2依序改成hd3／hd4。最新2.4改為以hd取代已辨識的原始##行，MAIN_TITLE註解不變；最新2.6取消跨頁小標快照；最新2.5移除空白hd2與hd3，無小標不輸出hd，階層重置留在內部堆疊。標題中的&、<、>轉成HTML實體，讀取時需還原；表格與程式碼不改。hd行放在content之外；已含新舊章節標籤的來源拒絕重複處理。
- 本次2.2驗證：128項測試通過（Gemini模擬，未呼叫真實API）；涵蓋hd2至hd5、跨頁快照、重置、特殊字元、表格／程式碼／註解保護與content邊界。既有2025_2330僅在記憶體處理，85個來源頁序與104個HTML表格原樣保留，得到85頁／104表／263內文區塊；來源檔未變，歷史tagged未覆寫。真實標題語意仍待人工核對。
- 2.1新增每行一個區塊標記：`<content_start>`與`</content_end>`表示內文、`<table_start>`與`<table_end>`表示表格、`<page_start>`與`<page_end>`表示整頁，拼字與斜線照使用者確認。不使用tablest_end。
- 最新2.8：content僅在正文標題（含未追蹤層級的Markdown標題）、大標變更、表格或EOF結束；換頁、空行及重列相同MAIN_TITLE不結束。頁面與content／table是獨立狀態，可交錯跨頁，不能用嚴格HTML巢狀解析；Page→page_start順序保持，頁碼及page_end／page_start可以出現在尚未結束的content／table內。文件層年份／股票代號仍在page之外；EOF收尾。
- 2.8接續表格：相鄰外層HTML表格之間出現「接次頁」或「承前頁」任一個，忽略所有空白後匹配，即共用一組table_start／table_end，可串接多段。保留各段完整HTML、中間文字、頁碼及頁面標記；不拼接HTML欄列或刪除重複表頭。純換頁與表格內部／註解／程式碼的接續詞不觸發合併。規則常數集中config/markdown_blocks.py，區間分組在table_continuation.py。Record新增table_continuation_joins，記錄原始HTML表格序號（由1起算）、命中詞及策略；block_counts.table改計接續後的區塊數，不等於HTML表格數。此為使用者指定的文字規則，合併語意仍待人工核對。
- 2.8本次驗證：147項測試通過，涵蓋任一接續詞、半形／全形空白、連續接表、不以換頁單獨合併、註解與程式碼假接續詞、跨頁content、大標變更及合併紀錄輸出。既有2025_2330的processed正文另直接送入純記憶體核心核對：104個HTML表格逐字相同、85個Page保持原順序，依規則分為89個表格區塊（15次相鄰接合，其中13個區塊含跨頁標記）與176個內文區塊。未重新執行OCR／API，未寫出或覆寫歷史產物；這是核心保留與規則驗證，不代表人工確認全部接表語意或批次來源驗證。新格式需從processed重新產生tagged，既有防覆寫維持。
- `block_boundaries.py`精確按外層HTML表格字元範圍插入標記，同行多表、前後文字與程式碼分開處理。若原文片段沒有換行，為使邊界獨立成行會補分隔換行；不改表格原始內容。Record新增`block_counts`（page／table／content）及`boundary_added_newlines`。標籤常數集中於`Code/config/markdown_blocks.py`。
- 區塊標記更新後122項測試通過，新增六項驗證巢狀、空頁、空行、同行多表、程式碼假標籤、EOF收尾與重複標記拒絕。實際2025_2330僅做記憶體驗證，得到85頁／104表／263內文區塊，104個表格原文及85個來源頁序標記保持相同；為獨立標記補104個分隔換行。未覆寫歷史成果，未呼叫API。
- 使用者已確認目錄頁碼直接對應 PDF_PAGE。大標／小標依 JSON parent_id 與頁碼取得；沒有頁碼的父項採後代已明列頁碼聯集，無頁碼葉項保持未知。
- 2026-10-22 起（markdown-comment-tagging/2.0）：MAIN_TITLE只依JSON的大標與頁碼；SUB_TITLE來自正文恰好##的中文數字頓號標題，允許`一 、`、`十 一 、`等空白，標題文字保留於hd中。JSON中的小標名稱不再輸出SUB_TITLE，正文也不必與目錄同名。
- SUB_TITLE下方的三類編號沿用HeadingHierarchy動態類型順序，但輸出由hd3開始（HEADING_1→hd3、HEADING_2→hd4，以此類推），SUB_TITLE輸出為hd2。遇新SUB_TITLE在內部清空下層，不輸出空白hd；遇hdN清除>=N舊路徑。同大標跨頁延續內部SUB_TITLE及動態路徑，頁首不重列hd2，新大標範圍清空前一小標及下層；尚無SUB_TITLE的下層標題保留原文並記錄問題。
- 同頁兩個SUB_TITLE按正文##位置切換，不需目錄小標分界。讀取舊JSON時只用頂層與後代明列頁碼聯集提供MAIN_TITLE；新JSON只含大標，沒有子項。沒有可靠頁碼的大標記錄未知，不補造。
- 本次更新後116項測試通過，涵蓋Gemini大標專用schema與模擬回覆、各種中文編號空白、同頁小標切換及動態重置。另對既有2025_2330資料做純記憶體核對，確認SUB_TITLE取自正文、104個HTML表格與來源不變，未寫出新檔、未呼叫真實Gemini。歷史tagged仍是舊版內容，不會隨程式修改自動更新；既有目標若存在，原有防覆寫仍會阻擋重跑。
- 不再使用舊規則2.0的人工 notes_scope 及 excluded／notes 包裝；本階段保留完整正文。公司名稱仍未知，不從文字猜填。
- JSON缺少或無效改用上述暫時備援；來源雜湊不符、頁序異常或備援無起點等，只輸出待確認紀錄，不產生該份tagged，繼續其他文件；Ctrl+C 停止後續。無頁碼葉項保留未知並記錄，不從正文補猜。既有輸出不覆寫，不刪舊產物。
- `--no-export` 可停用實驗寫檔，仍回傳記憶體結果。舊 `--tag-markdown` 是保留的 XML 標籤相容入口，新格式請使用選單4或 --tag-batch。
- EXPERIMENT_ONLY 清單追加 `comment_tag_paths`、`export_comment_tags` 與 `tag_processed_batch` 中的呼叫；核心格式處理在 `comment_tagging.py`。

歷史驗證：新增六項合成文字／JSON測試，當時完整套件 108 項通過。頁碼移除當時位於tagged，現已依新要求移至processed；當前測試分別檢查processed清理、tagged原文保留。

使用者確認後已改為 markdown-comment-tagging/1.1，只依JSON列目錄標籤，不使用同名分界或 note_numbers。108項測試通過，實際2025_2330已寫出至 `Output/markdown_tagged/Financial_20261021_002/2025_2330_tagged.md`，移除82行獨立頁碼；104個HTML表格逐段核對相同，85個歷史 PDF_PAGE 標記原樣保留，processed來源雜湊未變。紀錄兩項問題：目錄「重大之期後事項」無頁碼，及正文 ## 2.087 在第一個中文章節之前，未猜測階層。此歷史樣本仍用舊頁序；新第一階段才使用 Page 股票代號_年份_P頁序。未呼叫Gemini，尚未人工核對全份標題語意。

## MinerU OCR 接入（已實作，小範圍驗證）

第二階段已整合（2026-10-21），詳見前節；先前僅完成抽頁載入驗證的紀錄為歷史狀態。

已依確認方案切換為必要 MinerU PyTorch PP-OCRv5 元件。18項無模型測試與指定四頁＋合成混合頁實跑完成；仍有錯字、閱讀順序與表格錯欄，未宣稱整份品質通過。完整模型參數、檔案用途、操作、產物、授權與限制見 [本次驗證紀錄](ocr_validation_results.md)。

## 執行

### 程式目錄

```text
Code/
├─ main.py                   # 執行入口、選單與流程串接
├─ schemas.py                # 共用資料格式
├─ config/
│  └─ settings.py            # 設定與參數
├─ functions/
│  ├─ ingestion/             # PDF 轉換功能
│  ├─ experiments/           # EXPERIMENT_ONLY 實驗輸出
│  └─ integrations/          # Docling OCR adapter、必要 det/rec 元件與來源授權
├─ tests/                    # 自動測試
├─ README.md
├─ requirements.txt
└─ requirements.lock
```

各 Python 套件另含 `__init__.py`；`.venv/` 與 `.cache/` 維持原位置。模組引用以 Code 為起點，例如 `config.settings`、`functions.ingestion.pdf_to_markdown`；啟動方式不變。

在專案根目錄執行 PowerShell：

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py
```

入口在匯入第三方套件前，會確認專案 `.venv` 與 Python 3.11。若從其他可正常啟動的 Python 執行 `Code/main.py`，會轉接至專案環境，保留原命令列參數；不修改系統預設 Python，也不自動安裝套件。

主選單顯示目前 OCR 狀態：`1` 選擇 PDF 轉換、`2` 切換 OCR、`3` raw批次補標題＋Gemini解析目錄、`4` 加階層標籤、`5` 舊獨立目錄解析、`0` 離開。OCR 預設關閉；切換影響這次程序後續選擇的所有財報，不修改設定檔，下次啟動仍按預設值。

選擇「完整 PDF 轉 Markdown」，系統會遞迴列出 `Financial Statements/` 下的所有財報（包含子資料夾）。
可輸入單一編號、以逗號分隔多選（例如 `1, 3`），或輸入 `A` 全選批次處理。輸入 0 返回或離開，Ctrl+C 中止。
命令列可指定 OCR 開關；省略旗標時使用 `Settings.ocr_enabled=False`：

```powershell
# OCR 預設關閉
& .\Code\.venv\Scripts\python.exe Code/main.py
# 開啟按需 OCR
& .\Code\.venv\Scripts\python.exe Code/main.py --ocr
# 明確關閉 OCR
& .\Code\.venv\Scripts\python.exe Code/main.py --no-ocr
```

亦可直接指定檔案（請換成實際存在的來源路徑）：

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py --pdf "Financial Statements/2330/2025Q4_2330_Financial_Report.pdf"
& .\Code\.venv\Scripts\python.exe Code/main.py --check-env
& .\Code\.venv\Scripts\python.exe -X utf8 -m unittest discover -s Code/tests -v
```

新環境使用 Python 3.11、venv＋pip：

```powershell
py -3.11 -m venv Code/.venv
& .\Code\.venv\Scripts\python.exe -m pip install -r Code/requirements.lock
```

以上為新環境建立方式，已有專案環境不需重建。若 `py -3.11` 無法找到安裝，請以實際 Python 3.11 執行檔的完整路徑取代 `py -3.11`，勿用版本未確認的系統 `python` 建立環境。

程式根目錄依 `config/settings.py` 的位置向上定位至專案根目錄，可隨專案資料夾改名。功能移動後仍使用既有財報、Output、venv 與模型快取位置。
直接呼叫 venv 的 python.exe；搬動 venv 後若啟用腳本或其他套件的命令入口仍指向舊位置，應在新位置重新建立 venv，套件依鎖定清單還原。模型快取與 Output 不需刪除。

## 本機處理與設定

`config/settings.py` 集中設定：Python 3.11 專案環境、CPU、`ocr_enabled=False`、`config/ocr.py` 的 CPU `ch_lite` 及 HTML 表格。
OCR 關閉時 `do_ocr=False`，不載入 OCR 辨識模型或下載 OCR 權重；仍使用 Docling 的版面及表格模型。開啟時才使用繁中／英文按需 OCR，不強制整頁辨識。
掃描頁、圖片文字或轉成外框的文字在 OCR 關閉時可能沒有文字結果，會保留頁序及 `no_text_extracted` 狀態，不自動開啟 OCR。
CPU 執行緒 10、各階段 batch 1、佇列容量 1。執行緒數會傳給 Docling 與（OCR 開啟時）OCR；不代表同時處理 10 份 PDF 或 10 頁，也不保證速度按比例增加。記憶體不足時仍可能影響轉換。
首次會下載 Docling 版面／表格模型，開啟 OCR 時另下載固定 revision 的 PP-OCRv5 det/rec 到 `Code/.cache/mineru_ocr/`，實際推論於本機，不上傳 PDF、圖片或文字。
沒有雲端 token 費用；Docling 的遠端服務與外部插件均關閉。

安裝的是官方 `docling-slim[format-pdf,models-local]==2.140.0`，必要 OCR 直接依賴另列於 requirements.txt。
本機實測預設 docling-parse 後端在中文專案路徑找不到實際存在的 glyph 資源，因此改用 Docling 官方 PDFium 後端，並補上其需要的 `rtree`；本次另依確認方案更換 OCR 元件。
完整套件版本記錄於 `requirements.lock`，每次轉換另外記錄相關版本與實際 pipeline 設定。

## 頁序與轉換品質

- `document.md` 使用 `<!-- PDF_PAGE: 2 -->` 等標記對應原 PDF 第 2 頁。它不是 Markdown 行號，也不是文件的印刷頁碼。
- 每一個 PDF 頁序都保留；沒有擷取到文字時加入 `NO_TEXT_EXTRACTED`，並在 manifest 記錄 `no_text_extracted`，不認定是成功辨識的空頁。
- `raw.md` 是同一份 Docling 結構直接序列化的整份版本，沒有本專案新增的頁序標記。它不是 PDF 內嵌文字的逐字複本，可能含 OCR 辨識結果。
- `document.md` 按來源頁重新序列化，清單上下文可能與 raw.md 不同。跨頁項目完整呈現在 Docling 的首個來源頁，其他來源頁保留項目識別碼；不猜測如何拆開表格、段落或列。
- 表格保存辨識出的 HTML `rowspan`、`colspan` 及表下注；仍需人工檢查欄列與金額是否辨識正確。
- 不清理負號、括號負值、小數、百分比、幣別、單位或期間，不預先刪除四大報表或會計師報告。
- 核心回傳 `MarkdownDocument`，含完整原始 Docling 結構、整份 Markdown、逐頁 Markdown 與來源項目參照，後續可直接使用記憶體物件，不必從 Output 讀回。
- 狀態 `converted_needs_review` 代表技術轉換完成、等待人工核對，不代表 RAG 品質合格。Docling 部分成功、失敗、缺頁、整份無文字或中止均不能當成整份完成。

先檢查原 PDF 第 2、3 頁的標記區塊，再核對代表性的正文與財務表格。目錄解析及附註正文邊界尚未實作。

## 實驗輸出清單（EXPERIMENT_ONLY）

初始轉換每次獨立保存到 `Output/markdown_raw/<財報檔名>/docling_<台北時間>/`，不覆寫既有產物：

| 產物 | 用途 |
| --- | --- |
| `document.md` | 含原 PDF 頁序與無文字／跨頁提醒的逐頁檢查版 |
| `raw.md` | 未按頁重新序列化的整份對照版 |
| `manifest.json` | 狀態、來源 SHA-256、原始頁數、原檔未變更檢查、設定（含實際 OCR 開關）、版本、耗時、錯誤與各頁項目參照 |

轉換未產生文件時只輸出 manifest，不製造看似成功的 Markdown。
寫檔集中於 `functions/experiments/export_output.py:export_markdown_run`，呼叫在 `main.py:run_markdown`，開關為 `Settings.export_enabled`；模組與呼叫都有 `EXPERIMENT_ONLY` 標記。
停用後仍回傳記憶體結果；移除輸出功能時同步調整呼叫、設定與本清單，保留核心轉換。
程式目前不跨程序保存原始 Docling 結構或做失敗續跑；需要重新處理時須從原始 PDF 重做，已下載模型可重用。

### Markdown 三階段目錄

| 路徑 | 設定 | 用途與現況 |
| --- | --- | --- |
| `Output/markdown_raw/` | `Settings.markdown_output_dir` | PDF 初始轉換；既有轉換入口寫入此處 |
| `Output/markdown_processed/` | `Settings.markdown_processed_output_dir` | US-09 標題補標記與修改紀錄；其他處理未實作 |
| `Output/markdown_tagged/` | `Settings.markdown_tagged_output_dir` | 預留給加標籤結果；標籤內容與格式待確認 |

原 `Output/markdown/` 改名為 `Output/markdown_raw/`，保留既有結果及歷史紀錄內容；歷史紀錄中的舊路徑如有存在，僅代表當時位置，不用來判定本次輸出位置。
三個階段不覆寫前一階段。初始 `document.md` 的 PDF 頁序標記仍保留，不代表第三階段的標籤功能已完成。
processed 本次由 `export_heading_run` 集中寫入（見下方說明）；tagged 仍只有預留路徑，沒有輸出呼叫。

## 驗證紀錄與限制

- 2026-10-20 本次 Python／OCR 調整：12 項測試通過（原 6 項結構測試與新增 6 項版本／開關測試）。實際建立 Docling converter 核對 OCR 開／關參數，並在禁止匯入 EasyOCR 的情況下驗證停用的 OCR stage 不建立 reader；未載入辨識權重或執行整份 PDF。
- 實測以本機 Python 3.14 執行 `Code/main.py --check-env`，成功轉接至專案 Python 3.11.9，退出碼 0；3.14 自身仍印出 `Could not find platform independent libraries <prefix>` 提醒。直接使用專案 Python 3.11 無此轉接需求。
- 環境檢查的預設 OCR 為 false，`--ocr --check-env` 為 true；選單「關→開→關→離開」實測通過。完整財報轉換、OCR 關閉後的真實文件品質與速度，留由使用者自行試跑，沒有以結構測試宣稱完成。

以下為先前調整的歷史紀錄：

- 2026-10-20 程式目錄整理：功能移入 `functions/`、設定移入 `config/`，同步更新程式及測試引用。環境檢查、模組載入、專案／原始財報／Output／模型快取路徑檢查通過；未重新執行 OCR。既有測試仍為 4 項通過、2 項因缺少指定財報 PDF 而出錯，與整理前相同。
- 2026-10-20 三階段目錄調整：設定路徑與資料夾一致；原目錄內 1 個檔案改名搬移前後 SHA-256 相同。暫存目錄的輸出路徑檢查通過，未執行 PDF 轉換或產生後兩階段內容。
- 本次重跑既有 6 項測試：4 項通過，2 項因測試指定的 `Financial Statements/2025Q4_2330_Financial_Report.pdf` 不存在而出錯。未修改測試或原始財報，也不將本次結果宣稱為全數通過；以下保留先前環境與轉換紀錄。
- 專案 venv 已安裝依賴；`pip check` 通過。
- 6 項 Markdown 結構／錯誤測試通過。
- 新測試用人工建立的 Docling 結構檢查空頁、缺頁、合併欄位、財務符號、表下注、跨頁參照與關閉輸出。這些不是實際 OCR 辨識結果。
- 專案繼續使用原資料夾名稱。預設解析器的資源載入失敗有保存 manifest；使用 PDFium 後可正常開啟真實 2025 年 85 頁財報。
- 2026-10-20 實跑已下載 OCR、版面與表格模型，完成第 1 頁後程序意外退出。Windows 同一時間記錄虛擬記憶體不足（事件 2004）與本次 Python 的 c10.dll 存取違規（事件 1000，0xc0000005）。當時本次程序約使用 3.2 GiB，另兩個 Python 程序約占 8.8 GiB、3.2 GiB；未完成整份轉換，也沒有完整 Markdown 產物。
- 上述底層程序崩潰無法由 Python 的例外處理保證捕捉，因此該次未產生結束 manifest。完整轉換及 OCR 品質仍待記憶體足夠後重新實跑核對，不以結構測試冒充辨識完成。

## 參考與歸屬

本機 `Reference Sources/MinerU_Protago-master/demo/demo.py` 已閱讀，理解其分開解析及輸出 Markdown 的做法；該來源為 AGPL-3.0，本階段未重用其程式碼，也未整合 MinerU。
本次依官方 Docling 與 docling-core API 撰寫轉接，使用其公開套件，沒有搬入參考儲存庫程式碼：

- [Docling 文件轉換 API](https://docling-project.github.io/docling/reference/document_converter/)
- [Docling OCR／pipeline 設定](https://docling-project.github.io/docling/reference/pipeline_options/)
- [Docling 原始結構與來源資訊](https://docling-project.github.io/docling/reference/docling_document/)
- [官方 Markdown 序列化器](https://github.com/docling-project/docling-core/blob/main/docling_core/transforms/serializer/markdown.py)
- [官方 HTML 表格序列化器](https://github.com/docling-project/docling-core/blob/main/docling_core/transforms/serializer/html.py)
- [EasyOCR](https://github.com/JaidedAI/EasyOCR)

實際 API 已以安裝的 docling-slim 2.140.0、docling-core 2.103.0 原始碼核對；來源 main 分支之後可能改變。

本次新增 EXPERIMENT_ONLY 產物：export_markdown_run 的 ocr_diagnostics.json；export_ocr_validation 的逐頁 Markdown、框覆圖及 manifest，由 tests/validate_ocr_pages.py 呼叫，受 export_enabled／--no-export 控制；export_synthetic_mixed_fixture 只建立人工合成測試資產，不納入語料。移除寫檔須同步移除其呼叫，核心記憶體轉換保留。


## 既有 Markdown 漏抓標題補標記（US-09）

選單 `3` 列出 markdown_raw 下的 document.md，選一份即可獨立處理。命令列也可明確選 raw.md 或其他既有UTF-8 .md，不必重跑PDF；傳入資料夾時讀取其中document.md。

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py --mark-headings "Output/markdown_raw/2025Q4_2330_Financial_Report/docling_20261021_083601_105762/2025_2330_raw.md"
# 停用實驗寫檔，仍執行處理並回傳記憶體結果
& .\Code\.venv\Scripts\python.exe Code/main.py --mark-headings "來源.md" --no-export
```

輸出至 `Output/markdown_processed/<來源相對路徑去副檔名>/headings_<台北時間>/document.md` 與 manifest.json。markdown_raw來源相對於markdown_raw；其他專案來源相對專案根，外部來源使用檔名，完整路徑記於manifest。時間戳記子目錄不覆寫既有結果。manifest的行號是Markdown行號，含原文、新文、編號類型及missing_heading／colon_review原因；JSON僅為實驗修改紀錄，不是正文JSON。

| 模組 | 職責 |
| --- | --- |
| config/markdown_headings.py | 規則版本、20字元、編號及行尾排除標點 |
| functions/markdown_processing/mark_headings.py | 純記憶體補標記與保護區域／table邊界驗證 |
| functions/markdown_processing/load_source.py | UTF-8原樣載入與來源雜湊 |
| schemas.py | HeadingChange、HeadingMarkResult，共用輸出格式 |
| main.py | 選單3、--mark-headings、run_mark_headings串接 |
| functions/experiments/export_output.py | EXPERIMENT_ONLY export_heading_run，集中輸出Markdown及修改紀錄 |
| tests/test_heading_marks.py | 合成核心與入口／寫檔驗證，不載入模型 |

`Settings.export_enabled=False` 或 `--mark-headings ... --no-export` 可停用實驗產物，結果仍由run_mark_headings回傳。移除寫檔時調整其main呼叫；不要移除核心補標記功能或把Output當唯一傳遞管道。table邊界異常時錯誤退出，不產生部分處理檔。

本次35項自動測試通過（含17項新增）；指定raw樣本6行補標記、104個HTML表格完全不變，來源檔保留。使用者只要求人工核對目錄及附註章以後。本功能不改原標題層級，不做目錄解析、章節刪除、正文JSON、切分或embedding；小數等短內容可能誤標。詳細樣本、結果與限制見 [heading_mark_validation.md](heading_mark_validation.md)。純標準庫、無新增安裝依賴／LLM API費用，未執行100–200份批次。


US-09 規則1.1追加確認（2026-10-21）：辨識時忽略行首單一 `- ` 列表前綴，輸出保留原行，例如 `## - (1) 透過損益按公允價值衡量之金融資產`。頁碼（如 `- 15 -`）明確保護，其他編號／長度／標點／表格規則不變。本次38項測試通過，指定raw樣本8行補標記；詳細結果與新產物見Code/heading_mark_validation.md（README內同目錄檔）。


## Markdown 加標籤（US-10，現行規則2.0）

選單4／--tag-markdown讀markdown_processed，另存markdown_tagged。前段及附註後段包excluded，整份附註僅一組notes；附註主標不占層級，中文編號##為hd1，下層按類型首次出現順序從hd2分配。無編號##與後置主標保留且不更新堆疊；不使用LLM／目錄解析。

標題hd數字即邏輯層級；段落content、表格外tableblock，path屬性保存完整路徑。scope標籤及區塊各有generator／version，能還原所有原文並比對SHA；重跑不重複包notes或hd。舊markdown-tagging/1.0可還原後重新標記，不能直接沿用其階層。規則2.0不輸出正文JSON或chunk。

**每份文件須先確認NotesScope範圍**，包含起訖Markdown行、原文SHA及確認依據；設定集中config/markdown_scopes.py。未知文件或內容變更時拒絕猜測，不以固定頁碼／第一個一、作通用起點。notes_scope.py負責載入確認資料，tag_markdown.py驗證範圍、包裝與安全還原；本機核心API可顯式傳入NotesScope。若已是合法2.0標籤結果，可重用其中已記錄範圍。表格邊界不可被範圍切開。

目前67項自動測試通過。尚未將真實樣本起訖寫入設定，因此選單4對未確認來源會回報錯誤。待使用者確認「一、公司沿革到檔尾含附表」後才執行真實2.0試跑；既有1.0結果保留，不能當成新規則已驗收。

## Markdown 檔名（US-11，現行規則）

財報Markdown使用年份_股票代號前綴，不帶季度，例如：2025_2330_raw.md、2025_2330_document.md、2025_2330_processed.md、2025_2330_tagged.md；逐頁檔2025_2330_page_2.md。PDF與既有目錄保持原名，執行時間仍在子目錄，避免覆寫。合成／未知來源測試檔不補造前綴。

年份及股票代號從來源Markdown檔名解析，記入report_year、stock_code；股票代號保留前導0。公司名稱與季度／report_period仍空白，不從比較年度或目錄名稱猜測。先前產物中的空metadata不因改名而改寫，下次加標籤才會寫入新metadata。

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py
# 只驗證來源與標籤，不寫檔
& .\Code\.venv\Scripts\python.exe Code/main.py --tag-markdown "Output/markdown_processed/2025Q4_2330_Financial_Report/docling_20261021_083601_105762/raw/headings_20261021_130403_680398/2025_2330_processed.md" --no-export
```

資料夾載入可辨識新命名；有多個候選時要求明確檔案，不猜。Settings.export_enabled與--no-export繼續適用。現行實際檔名以各run的manifest.markdown_files為準，本文較早的raw.md／document.md說明屬先前名稱。

本次更名14個既有Markdown，內容SHA完全不變；同步更新manifest來源路徑，filename_migration保留舊名、SHA及引用調整。64項自動測試通過；實際來源引用有效、重跑更名0檔，指定新檔名的年份2025／代號2330解析通過。未重跑PDF或批次轉換。

維護工具：`Code/maintenance/rename_markdown_filenames.py`預設只列計畫，--apply執行。改名與紀錄寫入集中在EXPERIMENT_ONLY的export_output.migrate_markdown_filenames；先檢查碰撞及路徑範圍，不覆寫目標，例外時回復本次改動。config/markdown_files.py集中命名規則，functions/markdown_processing/file_identity.py負責解析／生成檔名；無新增依賴。

## 獨立Gemini PDF目錄階段（2026-10-21）

已實作選單5／--toc-pdf，只抽原PDF實體第2、3頁傳給Google Gemini；不啟動Docling、OCR或接續標籤。原PDF不變。這是目前已授權外傳的兩頁，不傳整份；現有本機Docling流程不受影響。本次只完成程式／本機驗證，未實際呼叫API。

沿用Code/.venv的Python3.11及pypdfium2 5.13.0，使用標準庫urllib呼叫官方REST。2026-10-21依使用者選擇加入專案根目錄.env讀取；python-dotenv==1.2.4原已安裝且列於requirements.lock，現明列於requirements.txt直接依賴，無需此次額外安裝。僅讀指定專案.env的GEMINI_API_KEY，不搜尋其他憑證檔、不展開環境變數或載入其他欄位，不顯示金鑰、不寫入Output。既有非空GEMINI_API_KEY環境變數優先；沒有環境值才讀.env。缺金鑰先停止，不抽頁或建立Output。

日常使用只設定一次：開啟專案根目錄的`.env`，在`GEMINI_API_KEY=`等號後填入自己的金鑰並儲存。例如結構如下（不要把示意文字當成金鑰）：

```dotenv
GEMINI_API_KEY=你的金鑰
```

之後直接執行以下程式並選5，不必每次輸入金鑰。程式用專案位置找到.env，與啟動時的工作目錄無關。根目錄已有空白.env與.env.example；若.env不存在，可從.env.example複製。`.gitignore`排除.env及.env.*，保留空白.env.example範本；本專案目前未初始化Git，此設定供後續版本管理使用。

```powershell
& .\Code\.venv\Scripts\python.exe Code/main.py
# 選5，再選單一PDF。或直接指定：
& .\Code\.venv\Scripts\python.exe Code/main.py --toc-pdf 'Financial Statements/2025Q4_2330_Financial_Report.pdf'
```

上面互動／命令列二擇一，不必兩個都跑，避免重複API費用。每次執行都會重新呼叫服務，不自動重用舊結果。若先前在同一視窗設定過GEMINI_API_KEY、現在想改用.env，可用`Remove-Item Env:GEMINI_API_KEY`移除該視窗舊值，或重新開啟未設定該變數的視窗。程式不會替你修改系統環境設定；.env儲存變更後下次執行會重新讀取。

模型與參數集中config/toc.py：gemini-3.1-flash-lite、8192 maxOutputTokens、網路逾時120秒、僅HTTP 503重試3次（等待5、10、20秒）。8192是輸出上限，不含PDF輸入；實際用量含服務端回報的思考等欄位，以usageMetadata為準，未實測足夠性。網路timeout是socket等待限制，並非整個流程硬性總時限；超時後服務端仍可能已處理／計費，逾時不自動補送。

輸出至`Output/json/原PDF檔名/toc_台北時間/`，含`pages_2_3.pdf`、`2025_2330_toc.json`（依來源命名）、`response.txt`、`raw_response.json`、`manifest.json`。來源命名無法可靠取得年份／代號時使用toc.json，不猜metadata。每次新建目錄，保留雜湊、頁序映射、模型／提示詞版本、參數、實際用量及狀態；失敗只保存已取得的診斷，不產生有效目錄檔。文件抽頁不代表正文頁碼與目錄印刷頁碼相同。

核心functions/ingestion/toc_pdf.py回傳記憶體TocPdf／TocResult，JSON schema在schemas.py；functions/integrations/gemini_toc.py僅負責HTTP。寫檔集中EXPERIMENT_ONLY的export_output.export_toc_run，由main.run_toc呼叫；停用Settings.export_enabled或搭配`--toc-pdf ... --no-export`不建立Output，**仍會傳送兩頁並呼叫付費／免費額度API**。移除實驗輸出時調整該呼叫與toc_output_dir，核心不依賴檔案。

目錄只保留原有標題、父子關係、印刷頁碼、附註編號；缺值空字串，不推算附註範圍。非目錄頁不輸出項目；沒有目錄、無法辨識、結構有效待人工核對及失敗分別記錄。截斷MAX_TOKENS、空回答、錯誤JSON與異常頁序／階層明確報錯。結構檢查不等於辨識正確，也不自動解決標籤notes起點。

本次真實PDF僅本機抽頁：指定2025樣本第2、3頁抽出共867516 bytes，分別與原頁渲染RGB完全一致，來源SHA不變；人工檢視第2頁目錄、第3頁聲明。Gemini回覆及網路錯誤均僅模擬，尚待真實API、逐項文字／頁碼品質及8192額度驗證。詳細紀錄見[toc_validation.md](toc_validation.md)。

本次完整回歸85項通過，包含新增18項目錄測試；未執行真實Gemini或重新跑OCR。

後續.env調整本次執行25項目錄相關測試通過（原18項＋新增7項金鑰測試），只用暫存假金鑰，未讀專案實際金鑰或連線Gemini；沒有重跑全部85項。涵蓋UTF-8／BOM、引號註解、環境變數優先、不擴張／寫入其他環境欄位、缺值／編碼錯誤、修改後重讀及指定專案路徑。

```powershell
# 僅本機及模擬測試，不需要金鑰，不連Gemini：
& .\Code\.venv\Scripts\python.exe -m unittest discover -s Code/tests -p test_toc.py -q
```

## 新對話交接文件

目前Code架構、功能責任、執行方式、測試範圍、指定樣本及待完成事項已整理於[CODE_HANDOFF.md](CODE_HANDOFF.md)（2026-10-21）。此整理未重新跑模型或API，也未讀.env內容。

交接核對另外發現既有`Output/json/2025Q4_2330_Financial_Report/toc_20261021_195003_434745/`完成紀錄：manifest為extracted_needs_review／complete，模型gemini-3.1-flash-lite，用量1371輸入、1998輸出、3369總tokens；目錄26項，第2頁toc、第3頁not_toc。此次只重驗該JSON結構通過，尚未逐項人工品質核對，也未新發送請求；前述未呼叫API為開發測試時的歷史狀態。
## 2026-10-26：parent_child的content首行（最新）

重新啟動Code網頁後，第四階段選parent_child並重新執行，會另存新批次的4.1 chunk JSON／Markdown；原有Output不會自動更新。original仍輸出4.0，切分規則本次不變。每個搜尋chunk及完整Parent的content先列一行脈絡，再接正文／原HTML表格：

```text
年度：2025｜股票代號：2330｜Main_Section：合併財務報告附註｜Sub_Section：一、營業收入｜Note_Title：(一)主要產品｜說明：相關說明原文
原正文或HTML表格
```

空欄省略，多年度用「、」，多條Note_Title路徑用「；」。資料均沿用既有解析：年度取years，股票代號取已核對Page的文件identity，章節取main_section／sub_section／note_title。表格說明只取table_context，不再重印directions；文字取適用directions，同字文字只列一次。table_direction仍可同時供年度與說明，table_year只供年度；表頭年度優先及所有回查邊界不變。原始來源紀錄仍存在metadata。

JSON為financial-chunks/4.1，規則hierarchical-semantic-chunks/4.1-context。新增content_prefix欄位記錄生成首行，驗證時依來源欄位重算；不另存一份正文。body_char_count與source_spans仍只對應來源正文，父子內容完整性移除驗證過的首行後核對。實作為functions/content_context.py；hierarchical.py組裝後加入，chunks.py驗證，Code/functions/embedding/prepare.py及Code_2/functions/qa/pipeline.py相容新版且不重複加脈絡。下方「content不含任何生成脈絡」的敘述只適用舊格式與original。

本輪117項局部測試通過，涵蓋雙模式回歸、年度回查、前處理及QA模擬。既有2025_2330 tagged唯讀記憶體串接取得194個搜尋chunk／165個Parent，96段HTML表格及來源正文逐字核對，359個首行通過驗證。沒有呼叫API、重跑OCR、寫Output或建庫。新切分算法與標題父項召回開關仍未完成，不因首行改版宣稱已實作。



## 2026-10-29：連續階段與 Colab GPU 補充

- 前處理可選起始／結束階段，例如2→5，依序銜接本次產物；失敗即停止。
- 連續流程可勾「只保留最終階段產物」：全部成功後才清理本次中間檔，保留 Record；失敗／取消不清理。只檢查 token 時不可啟用此選項。
- `FINANCIAL_RAG_DEVICE=auto|cpu|cuda` 控制 Docling、BGE-M3 與 BGE 重排序。
- Colab 設定 `FINANCIAL_RAG_RUNTIME_PYTHON=current`；Windows 未設定時仍使用既有雙環境。
- Notebook 與操作細節見 [colab/README.md](../colab/README.md)，目前設定摘要見 [AGENTS.md](../AGENTS.md)。
- 本次沒有在真實 Colab GPU 上執行模型；安裝相容性與 GPU 效能仍待實測。
