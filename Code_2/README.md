# Embedding 前處理、向量建庫與財報問答

## 2026-10-29：最新四份77題重排報告改名

依使用者要求，舊四索引跑新版77題的最新重排目錄改為 `Output/reponse_rerank/BGE 父子250`、`BGE 原始`、`Voyage 父子250`、`Voyage 原始`。僅移動這四份完成報告，不變更證據、分數、索引或其他歷史資料。網頁報告辨識除既有qa時間名稱外，明確接受這四個名稱，沿用來源目錄與檔案路徑檢查；新執行仍產生qa時間目錄，不覆寫這四份。既有網站程序需重新載入程式才套用辨識規則。


## 2026-10-28：單題不產生測報

依使用者要求，單題查詢（檢索、重排序、回答；含CLI及多索引單題）只回傳畫面／終端結果，不建立qa目錄或寫result.json、answer.md、ID_*分題檔，不受export_enabled勾選影響。問題向量題庫快取沿用。網頁保存測報選項只在Excel批次模式顯示；批次九頁Excel與分題輸出不變。既有歷史報告與舊報告重排的明確另存入口保留，不刪既有資料。


## 2026-10-28：九頁作圖報表與分題模型輸入（已實作）

使用者已確認報告應可直接用於作圖與報告：results.xlsx固定九頁，包含作圖說明；檢索方法與題型、TopK曲線、五筆增量、逐題對照；重排前後比較、TopK曲線、逐題差異、成本效益。中文欄名、表頭、凍結、篩選及百分比顯示；不含chunk全文或逐候選除錯紀錄。不同模型設定、題庫、召回K、標題父項設定及評分版本分群；群內以共同可評題計算，pending／執行失敗不算0分。表格、文字、混用各列，整體每題一次，類型由題庫提供而非由檢索成功者反推。沒有重排結果的表保留欄名，不填假數字。

EXPERIMENT_ONLY模組report_tables.py由eval_run.excel_report與web.comparison呼叫；多索引Excel測試另存跨方法比較表並提供下載。也可離線執行 `python -m Code_2.functions.experiments.report_tables <result.json路徑> [其他result.json路徑...]`，另存於新的Output/reponse_embedding/qa_日期時間，不覆寫來源；比較報告的result.json是來源清冊（financial-report-tables/1.0），不是可再次重排的完整批次候選。

TopK沿用來源保存的有效名次（同必回父項去重），不是重新查詢各K；排名扣分仍固定原召回K。原始／加權分開作圖，未命中0分計平均，待確認不計分。每五筆增量顯示趨平情形，不自行設定最佳K門檻。重排以同題、同版、同Top10範圍配對，資料不足／版本不同不計提升；未保存子項重排評分者只提供既有證據／父項階段，不假造子項曲線。API用量與內容token估算區分，缺少用量／耗時留白，不猜費用。

批次分題輸出改由model_input_reports.py處理：ID_*.json只包含問題、原始候選子項與重排結果，供模型輸入，不包含Answer／reference／scores；新查詢保存retrieved_children以避免事後讀取索引。舊報告只從SHA相符的chunk檔還原，不能還原時明示returned候選，不能猜子項或名次。ID_*.md只含問題與前10個檢索子項所對應的證據，必回父項去重、不補選，原始切法不帶標題父項。重排使用已保存的選中證據；完整分數、參數、用量與全文保留總result.json。單題舊入口相容。

完整JSON先保存，Excel或其他衍生報告失敗時標partial並保留完整資料，可離線重匯出。實驗集中停用仍沿用EvaluationSettings.enabled與export_enabled，不增加正式問答依賴。


## 2026-10-28：G9重跑與報告匯出修正

依使用者要求重跑BGE父子250、文字與表格完整標籤G9，使用88題必要數字測試集、Top50、只檢索、新版數字唯一評分。移除逐候選numeric_checks除錯輸出，Excel只存整題各數字目標缺漏，避免單格超過32767字；必要數字首次來源、完整召回全文與評分保留。


## 2026-10-28：必要數字作唯一評分標準（已確認、已實作）

使用者最新要求：有Required_Numbers的題目只核對必要原始數字，不再以股號、年度metadata、章節標題或頁碼限制得分。版本為numbers-only/1.0；既有年度×標題僅作數字標準的分組識別，不是命中門檻。各組必要數字可跨召回chunk補齊，首次補齊全部數字的有效名次用於排名加權；原始各組等額配分、按自身配分比例扣分、同必回父項去重均保留。正負號、百分比與完整數值邊界仍區分，不以Excel Answer比對。

查詢的Years／股號篩選不變；這次只改實驗評分。pending仍保留但不計平均；無Required_Numbers的歷史題型仍明示使用舊章節規則。舊測報及曲線不覆寫，不能將舊分數視為新規則結果。數字相同即可能命中，此分數不代表年度、科目、單位語意已驗證。

前一版已依使用者要求移除年度metadata問題題70、81、84、101，另存88題必要數字Excel，原ID不重編，目前使用檔已更新並備份；77題ready、11題pending。先前92題檔及歷史測報保留。本次未重跑模型或改動索引與問題向量題庫。


## 2026-10-28：新版排名加權公式

年度×標題目標數為N、原始召回數為K時，每項配分10/N，每晚於理想名次一名扣(10/N)/K；每項得分=max(0,10/N－(10/N)/K×max(0,有效名次－理想名次))。原始分數、命中條件、理想名次及去重不變。N=4、K=50每名扣0.05，N=2扣0.1，N=1扣0.2。版本為year-title-dual/3.2／year-title-numbers/1.1，適用新檢索與重排評分。

新圖表使用已保存的各項貢獻；跨題扣分率不同時rank_penalty為null，rank_penalties列各率，勿將null當0。歷史報告／圖表不自動重算。從舊測報重排時，來源檢索分數與版本保留，重排另採新公式。JSON、Markdown、Excel與網頁圖表入口已同步相容新舊版本；正式問答和背景建庫不受影響。44項Python與Node介面測試通過，均為本機／假服務。

## 2026-10-28：必要數字評分入口

最新定案：已依使用者答覆補齊第10、30、48、60題章節，並更新目前使用的`Output/question_sets/畢業專題測試題目_2024_證據類型.xlsx`，原檔已備份於archive。可交付副本為outputs的`畢業專題測試題目_2024_92題_必要數字.xlsx`。92題均有數字資料，81題ready；11題pending（7、25、33、39、48、50、61、63、111、119、123）不計分，原因在備註欄。下文78題／14題是草稿階段。尚未執行新檢索。

數字標準Excel草稿：`outputs/01a15e66-1116-7881-9e46-db24b17ce42b/畢業專題測試題目_2024_92題_必要數字_草稿.xlsx`。92題填入資料，其中78題ready、14題pending；目前使用的測試集未覆寫。Required_Numbers_Status=pending會保留題目但分數為null、不計入平均；備註及來源另存Required_Numbers_Note／Required_Numbers_Source，每題報告保留。原題ID、問題、答案與年度未改。章節補齊與原先疑點題的計分決策待使用者答覆。

Excel可選欄`Required_Numbers`使用JSON陣列，例如`[{"year":2023,"title":"二一、營業收入","numbers":["934,768,625","69,482,307"]},{"year":2024,"title":"二一、營業收入","numbers":["1,476,890,566","59,486,924"]}]`。數字必須用字串，保留負號、小數、百分比。每組對應一個原有年度×標題目標，同一候選必須符合股號、該年度及標題，並包含全部必要數字才命中；各目標可由不同chunk提供。原始／加權公式及必回父項去重沿用；父項召回階段使用父項全文。Page不擋分。

此欄只留實驗reference，不送模型。無此欄仍採舊年度×標題規則，有此欄但目標不齊則顯示無法計分；不從Answer或92題草稿自動猜年度／數字綁定。尚未將92題全部補完，因此新網站查詢不會自動把舊題宣稱為數字驗證結果。每題JSON、Markdown、Excel另列評分版本、必要數字與缺漏；混合批次須依逐題版本解讀。

EXPERIMENT_ONLY模組`functions/experiments/numeric_evidence.py`由eval_workbook解析、eval_scoring呼叫；輸出由既有eval_run／question_reports處理。32項本機合成資料測試通過，涵蓋錯年度／股號／標題、不同chunk數字不能拼湊、負值／百分比／千分位、資料未補齊不計分及舊題相容；未呼叫API。實際第1題離線核對見`Output/number_evidence_check_20261028/ID_001.md`。移除此功能須同時移除解析、評分和報告欄位引用，不影響核心檢索。

## 2026-10-28：離線標準證據清單草稿

`functions/experiments/fact_checklist.py`（EXPERIMENT_ONLY）可將逐題稽核JSON與其來源chunk JSON轉成不依賴chunk_id的標準證據清單草稿。CLI：`python -m Code_2.functions.experiments.fact_checklist --audit <稽核JSON> --chunks <來源chunk JSON> --output <新資料夾> --exclude 23 54`。只讀本機資料，不查向量庫、不呼叫API；未串接正式查詢或原年度×標題評分。

本輪92題產物在`Output/standard_evidence_92_20261028/標準證據清單_草稿.md`及同名JSON。必要值分組沿用人工稽核，原文片段只供核對；尚未逐項確認年度、科目、單位及條件，因此正式證據分數保持null，不把既有錨點共現當作已完成的答案證據命中判定。移除此獨立實驗模組及本節不影響核心流程。

本次本機驗證：92題及排除題號、證據ID唯一、命中chunk_id更換不改證據ID、未確認時不產生正式分數均通過。未驗證92題全自動語意辨識或全部原PDF數值。

## 2026-10-28：獨立批次測報

新執行的Excel批次檢索／重排序／回答在各自的`Output/reponse_*/qa_日期時間/`內，除`result.json`、`answer.md`、`results.xlsx`及逐題`ID_*.md／json`，另存`測試分析報告.md`。這份獨立Markdown列設定、評分口徑、階段平均與逐題缺漏／名次；分題檔保存各階段原始與排名加權分數、逐項貢獻、候選、證據及用量。舊報告重排序的前兩階段分數標為來源基準，僅重排序階段重新計分；K沿用來源向量召回數。完整證據需連同分題檔供外部LLM核對，總測報不嵌入所有財報全文。沒有標準標題者無法評分；未標註跨頁維持unknown；既有報告不回填。實驗報告由`experiments/analysis_guide.py`與`question_reports.py`產生，呼叫處為`eval_run.export_batch`；集中停用實驗輸出後核心查詢仍運作。

## 2026-10-28：問題向量題庫與依階段分題輸出

單題／Excel查詢現在共用持久問題向量題庫；新報告依模式輸出至reponse_embedding、reponse_rerank、reponse_answer，並每題另存JSON及Markdown。原始切法不帶標題父項。設定、限制、輸出清單及本輪驗證見[QUESTION_BANK.md](QUESTION_BANK.md)。以下舊章節中的Output/Response是歷史位置，仍可讀取。

測試集可加入`Evidence_Type`及`Cross_Page_Table`作標準證據分類，檢索／重排／回答報告顯示，模型與分數不讀這兩欄。新版可上傳副本：`Output/question_sets/畢業專題測試題目_2024_證據類型.xlsx`；跨頁未核對者標`unknown`。詳見[QUESTION_BANK.md](QUESTION_BANK.md)。

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

統一網站的第五階段已移除「查看／選擇欄位標籤」按鈕、欄位選項API及其動態欄位提交。建庫沿用固定`Code/config/embedding_fields.txt`，其角色設定仍是索引資料契約的一部分；既有索引不變更。此變更只移除瀏覽器中的欄位檢視／選擇流程。

## 2026-10-27：四份舊報告先子項重排再帶回父項（最新確認）

使用者更正順序：舊報告的50個命中子項→Voyage rerank-3-lite選Top10子項→帶回必回內文／表格父項，同父項合併一次、不往後補選。可選標題父項不額外召回。原始切法保留其本來的跨頁表格父項規則。此更新針對舊報告重排序，不偷偷替換一般ask流程。先前本頁「已帶回父項才重排」是舊版，現入口已改成candidate_unit=child；returned模式僅保留相容。

使用者確認沿用舊報告50個命中ID，從input_sha256相符的chunk JSON還原子項文字，不重新embedding或查向量庫。因舊報告只記前20筆原排名，重排輸入依chunk_id固定排序，candidate_input_order不當作原檢索排名；其餘source_retrieval_rank為null。輸出JSON保存50個原子項輸入、Top10子項、合併後完整證據與對應關係。

使用者確認年度、股票代號、Main_Section、Sub_Section、Note_Title及去年度的說明只補在報告，不新增到送給Voyage的text。source JSON可驗證時沿用既有context_prefix規則生成report_text與report_metadata；不重判年份或說明。Markdown逐筆列Top10子項及最終證據全文，JSON保留text原樣與report_text；父項分數標明來自首個命中子項，不假稱父項直接重排。

授權執行BGE父子250、BGE原始、Voyage父子250、Voyage原始四份各118題，保留Top10，確認完成／失敗與JSON／Markdown保存後停止，不追加品質分析。9項專用假服務／HTTP測試通過，含同父項合併不補選、未知原排名、標籤不進重排輸入；四份逐題本機還原118×50通過。實際API結果另以本次執行紀錄為準，不把本機測試寫成外部成功。

EXPERIMENT_ONLY：child_candidates.py負責還原子項及重排後父項合併，evidence_report.py僅補輸出標籤；由saved_rerank.py呼叫。停用沿用EvaluationSettings.enabled；來源及舊報告不覆寫。

## 舊報告讀取／只做重排序（2026-10-27）

在統一網站「執行紀錄」點選原始報告，於「舊報告重排序」選Voyage重排序設定、保留證據數，展開題目清單勾選要跑的題目，按「使用此報告開始重排序」。Excel可勾「製作原始／加權圖表與統計表」。候選是舊報告保存、已帶回父項並去重的全文；不是把整份Markdown當成一篇文件。只呼叫重排序，不重送問題embedding、不查索引、不呼叫Gemini／GPT。即使原索引已不在，也不會回查或猜補。

支援單題financial-qa/1.1、Excel financial-evaluation/1.0的3.0／3.1年度×標題評分報告。缺候選全文、評分metadata不符、失敗題或not_run會標不可用；只有曲線的統計報告不可當原始檢索報告。僅讀本機Output/Response內固定名稱的result.json，不開放任意路徑或上傳憑證。一次一份來源，來源128MB上限，保留數1～來源召回數；實際候選不足時依既有Voyage介面取min。

報告每次另存，保存source_run與來源SHA256；來源在預覽至執行前變動則拒絕API。JSON保留原候選與原排序，另有選中證據、rerank_rank、rerank_score及API用量。Excel新報告保存原檢索／回傳分數基準，加上重排分數、平均與可選曲線；評分仍用來源標準、原始retrieve_k（如50則每名扣0.2），不是以保留數10改成每名扣1。單題保存answer.md／result.json，批次另有results.xlsx；圖表在網站顯示並記於JSON／Excel，SVG另存仍使用既有事後製圖功能。失敗保留已完成階段與候選，後續題不執行，不自動重試。700先前23題與95題仍是兩份來源，沒有暗中合併。

EXPERIMENT_ONLY輸出清單：saved_rerank.py呼叫reserve_qa_run、export_batch／export_qa_run；history面板及saved-rerank.js只負責預覽／設定／提交，核心不依賴這些報告。集中以EvaluationSettings.enabled停用；正式移除需連同service.py的rerank-report分支、server.py的預覽／資產路由、worker進度名稱、history入口及來源說明移除，原ask保持正常。

驗證：Code_2完整176項回歸通過；專用7項含HTTP／假重排服務測試通過（與完整套件重疊6項），合成DOM驗證固定候選重排專用請求與勾選、兩份JS語法檢查通過。七份真實報告可讀，瀏覽器入口及設定確認。未呼叫真實重排序API，不宣稱重排品質。程式：functions/experiments/saved_rerank.py；tests/test_saved_rerank.py、test_saved_rerank_ui.js。

## 2026-10-27：自訂索引名稱與管線表格相容

補充本輪完整實檔驗證：2024台積電目錄維持Docling後，查核P4～P7、附註P16～P124共113頁，98.476秒成功輸出，P4／P7回退Docling，來源SHA256不變。完整raw再經processed→tagged→original700（207chunk／14父項）、parent_child250（258／42）、parent_child700（220／33）及建庫前處理全部通過。這是結構／契約驗證，沒有全表逐格人工驗收或真實embedding／LLM。可讀紀錄：Output/pdf_parser_comparison/full_stage1_20261027_122001/validation.md。第一次目錄錯配13頁的產物另存品質失敗紀錄，不當成成功驗收。另12項問答模式及pip check通過，瀏覽器已核對新選單與名稱欄。

第五階段仍由Code負責，新增「新建索引／加入既有索引」。新索引以隨機實驗ID隔離，相同設定也能分次建立；名稱保存在signature.experiment.name，catalog另提供display_name。Code_2單選／複選查詢與比較按鈕顯示名稱，實際仍以backend＋collection唯一定位，各集合獨立執行、不合併候選。舊索引沒有名稱時顯示原collection，不需重建或搬移。完整簽章用canonical JSON比較，避免欄位tuple／list序列化差異造成既有索引無法加入。新增索引只能使用同一模型、欄位、切法、字數與處理版本；同資料略過，不同版本拒絕覆寫。同名索引仍獨立，請用旁邊collection核對。

Code第一階段可選inspector的|表格，兩種chunk切法及建庫前處理已用真實P40／57／71驗證；Code_2既有檢索／重排／回答沿用embedding_text與原始chunk契約，不因HTML／管線格式新增另一套檢索流程。這不代表已驗證回答正確率；原表格合列、錯序不能由格式相容測試證明已修復。沒有在真實索引執行模型／付費API。47項相關索引／多索引比較／統一網站／集合管理與5組Node介面檢查通過。

## 2026-10-27：表格民國年度下限100年

使用者確認表格可採113年度、113年12月31日、112年等明列年度，民國未滿100年不列入（100可採，90／99不可）。ROC_YEAR_RANGE集中改為100～288，西元1900～2199與其他格式維持。此限制套用表頭及表格前置標籤的共用年度解析器；小於100不轉換、不補足，1至3年等短期年限不再成為1912／1914。表頭無有效年度時繼續讀範圍內前置標籤，最後才依既有規則使用文件年度；不調整表頭優先順序、不改一般文字年度。

第四階段parent_child規則更新bounded-parent-child/5.4、original更新content-end-original/1.2，schema不變。新規則與舊索引隔離；舊chunk／向量不自動修正。套用既有文件需重跑第四階段，並於第五階段選新版JSON建庫，尚未替使用者執行或重建索引；不需重新OCR。原始chunk_id標註／表格文字命中分析仍暫停。

## 2026-10-27：多標題邊界解析修正

同一Excel格內逗號（含中文逗號／頓號）後接新章節編號時，拆成獨立標題，再依既有規則去掉編號、比對完整名稱。原有分號／換行仍支援；不切開「不動產、廠房及設備」等標題本身的頓號或英文逗號。沒有新編號的含糊字串如「二二、營業收入 、資產總計」保留原樣待確認，不擅自猜成兩個標準。新報告year-title-dual/3.1，舊2.0／3.0報告保持原始解析與分數，事後製圖仍保留來源版本。原測試Excel與歷史Output不改寫，不重跑模型；類型標註功能仍暫停。

## 2026-10-27：跨財報內容年度及無編號標題評分（最新）

使用者確認只要股號、chunk內容年度及標題符合，即使來源為2025財報也可對2024項目得分。Doc_Id僅供股號識別，不再限制來源財報年度；Page只保留覆蓋／缺漏顯示供核對，不再擋得分，Page空白亦可計分。所有要求年度×標題仍分項給分，原始／加權及去重扣分不變；來源索引只預檢是否含該股號，不再因標準財報年份不存在而跳過。標題忽略每層開頭中文／阿拉伯編號及空白、全半形差異，對照Sub_Section或Note_Title各層的完整語意名稱；保留IFRS、指標中的數字及其他語意，不採模糊字串猜測。指定完整多層路徑時仍需整條名稱對上，不能只同上層就算命中。

新報告year-title-dual/3.0；舊2.0報告及其圖表保留舊分數，不暗中重算或改標版本，事後製圖支援2.0／3.0並沿用來源規則。新規則不需重建向量庫，網站閒置時重新啟動後套用。正式檢索問題與API資料傳輸不變，僅調整實驗評分。

使用者同時提出從完整語料找原始chunk_id、勾選確認答案類型以比較表格／文字命中率；已明確要求此部分先暫停。尚未實作候選標註工具、標準答案類型或類型命中率，不以召回結果自行推定標準、不擅自產生確定gold chunk_id，也不改原測試集。


本次驗證：跨財報同股號／內容年度給分、異股號與異內容年度零分、標題忽略開頭編號、保留IFRS17與IFRS9差異、Page空白／不同頁仍能計分等局部測試通過；圖表維持來源2.0或3.0規則說明，不替舊報告改分。Code_2全套169項中168項通過、1項受環境阻擋：test_openai_answer的假測試載入Voyage依賴uuid_utils DLL時，被Windows應用程式控制原則拒絕（ImportError），不是本輪評分斷言失敗；未繞過政策或修改依賴。未進行真實模型或API測試。

## 2026-10-27：多索引獨立比較與事後製圖（最新）

使用者確認多索引各自執行，不合併證據；事後圖表另存新報告、保留原結果。問答頁勾「複選索引，各自執行並比較」後列出全部已提交集合（模型／切法／字數／文件數），可跨切法選擇；相同問題、篩選、召回與服務設定依序各跑一次，每個集合各自重排序與回答，API成本分別計算。單題及Excel都支援；全部先核對集合，最多20個不重複索引；模型／API或保存失敗後未執行的索引明確標示not_run，不自動重試。各索引各自保存原問答或Excel報告，結果區可切換檢視，各自列平均及可評分題數；原始切法不支援標題父項時，多選共用開關停用。

Excel預設未勾「執行後製作原始／加權圖表與統計表」，未勾不呼叫曲線計算。完成後可按「開始製作圖表並另存統計報告」；只讀既有年度×標題雙分數貢獻與排名，不重查索引、不送問題或候選給模型。已保存者從固定source_run讀取；未保存者只提交精簡分數，不含chunk正文。圖表另存新的qa_時間資料夾：answer.md、result.json、results.xlsx、charts.svg，保留source_run；舊版缺少原始分數報告拒絕假填。已勾執行前製圖或事後製圖完成時，圖表直接展開，仍可取消勾選隱藏。

EXPERIMENT_ONLY：chart_report.py負責來源驗證、曲線及另存圖表統計；make-charts工作與既有evaluation.js入口沿用EvaluationSettings.enabled，移除時刪服務分支及入口；正式單題多索引執行comparison.py不依賴評分模組。原報告不覆寫，原始PDF與向量庫不改動。需網站閒置時重新啟動載入新後端，未替使用者執行真實檢索／API或中止背景建庫。


本次驗證：Code_2完整168項Python測試及3項Node介面契約通過；涵蓋多選索引同問題依序獨立跑、重複索引拒絕、失敗後not_run、製圖前後勾選、來源驗證、SVG／Excel／Markdown／JSON另存、原報告位元組不變與兩次worker驗證後來源追溯。皆為假查詢／暫存檔與合成DOM；未執行真實API、未開啟使用者測試集、未重啟網站或檢查背景建庫。

## 2026-10-27：執行前選擇是否製圖（部分完成，後續待確認）

Excel輸入新增未勾選的「執行後製作原始／加權圖表與統計表」；generate_charts必須為布林值，預設False。未勾選只做檢索／評分與一般保存，不呼叫build_curves，勾選才產生原始／加權曲線及統計。

使用者另要求查詢／回答可複選向量索引一次跑完，以及未先製圖時可在結果旁事後製圖。待確認多索引獨立結果或合併證據、事後圖表是否另存報告；這些部分尚未完成，不把草案當作實作。背景建庫不停止、不重啟。

## 2026-10-27：結果圖表改為勾選顯示

批次結果預設呈現檢索／逐題結果，曲線區新增「顯示圖表與統計表」未勾選核取方塊；勾選後才建立原始／排名加權折線、逐K表及5筆區塊分析，取消即隱藏，再勾不重複建立。每次呈現新結果預設不勾選；無曲線的舊報告不顯示空控制。此選項只控制畫面，既有計分、平均及Excel／Markdown匯出不變。EXPERIMENT_ONLY沿用evaluation.js與集中停用設定。

## 2026-10-27：年度×標題雙分數（最新，取代僅標題計分）

使用者最終確認兩年度、兩標題拆成4個給分項目，每項2.5分；單個chunk可同時滿足多年度與標題。原始分數=10×已命中組合數／總組合數，部分命中按比例；排名加權則同組合各占10/N，依各組合首次有效排名及既有理想排名扣10/retrieve_k。年度以chunk.years確認，Years空白不猜年度而每標題一項；查詢Years仍採OR，完整度由評分逐項核對。文件／同chunk標準頁碼、Sub_Section或Note_Title比對、必回父項去重維持；不額外放寬文件與頁碼。

新報告year-title-dual/2.0，score及mean_score保留為加權相容欄，另外保存raw_score、weighted_score及各自平均、年度×標題命中數、缺項與Top。原始曲線raw_curves用於觀察召回到幾段，加權curves用於切法比較；兩種皆固定同批可評分題、分階段呈現、含逐K及每5筆區塊表。網頁原始／加權各有獨立折線圖，Excel各有曲線與區塊工作表，Markdown兩套數據亦保留。不重新計算歷史報告、不呼叫API或重建向量；閒置時重啟網站後新批次套用。

本次驗證：Code_2完整164項Python測試通過；另驗證網頁同時產生原始／加權兩張SVG與雙平均顯示。合成資料核對4項命中3項=原始7.5分、雙年度同chunk、缺年度、去重與原始累積曲線；Excel及Markdown雙分數／雙曲線輸出契約通過。未呼叫真實API、未重跑使用者測試集、未改寫既有索引或報告。

## 2026-10-27：累積平均得分折線圖與區塊分析

已確認固定以原始retrieve_k決定扣分，僅改變取前K筆的截點；Top50時畫有效Top1～50，全部固定每名扣0.2。同必回父項去重沿用，三階段分開，曲線固定同一批可評分題數，0分計入、失敗與無法評分不計。每5筆統計增分（最後不足5筆仍保留），標出增分最多區塊及首次達本次完整平均分的最小K；全零不建議截點。這是同次候選截取分析，不代表重新呼叫模型的品質或耗時測量，也不宣稱跨測試集最優。

EXPERIMENT_ONLY模組eval_curve.py由eval_run.py在匯出前呼叫；網頁evaluation.js以SVG畫折線及表格，JSON存curves，Markdown與Excel新增各階段曲線／區塊表。正式停用沿用EvaluationSettings.enabled，無新增依賴、無額外API呼叫，舊報告不回填。重啟網站後新批次產生曲線。

## 2026-10-27：依向量召回數調整評分（最新）

使用者指定每名扣分為10/K，K採向量檢索設定retrieve_k，而非實際回傳數或重排序保留數；Top50扣0.2、Top20扣0.5。有效評分範圍隨K，不再固定20；去重、多標題10/N與理想排名、同chunk文件／年度／頁碼及跨層級標題條件維持。重排序階段沿用檢索K。網頁／Markdown可讀全部評分候選，Excel保留前20個chunk_id欄及完整命中排名／缺漏與分數。新報告page-title-rank/1.2，舊報告不改寫；重啟網站後套用。

## 2026-10-27：批次平均得分

測試結果畫面顯示平均得分及計入題數；Markdown報告同步顯示，Excel新增「總覽」工作表保存數值型平均與題數。沿用每題最終評分階段的平均，0分題計入；失敗、未執行、缺語料或無法評分題不計入，沒有可評分題時顯示無法計分。既有報告不覆寫。

## 2026-10-27：測試標題跨層級比對（最新）

使用者確認：Excel的Evidence_Note_Title對照同一chunk的sub_section或note_title，任一欄位在忽略空白及全半形差異後完整相符即可；不讀Evidence_Sub_Section作判斷，也不增加Main_Section比對。文件、年度與至少一個標準頁碼仍須在該chunk符合，去重及排名扣分不變。同一目標出現在兩欄只算一次。新報告scoring_rule為page-title-rank/1.1；既有報告保留當時規則與分數，不自動覆寫。程式更新後需於網站閒置時重啟，讓後續測試載入新規則。


驗證：13項本機評分／批次契約測試通過，涵蓋跨欄位標題命中、同目標不重複給分、錯頁／錯年／錯文件仍零分及原排名例子。以qa_20261027_01-53-56_645989第一題保存的候選與對應第四階段chunk在記憶體重算，原始檢索及父項召回後均為Top3、頁碼1/1、標題1/1、9分。沒有重新檢索、呼叫模型／API或改寫原報告。

## 2026-10-27：獨立Excel批次證據測試（已實作，真實檢索待建庫）

問答系統新增「單題輸入／Excel批次測試」。xlsx上傳只送到同一個localhost站點，不保存原始工作簿；可選工作表、勾題目、展開看Question、篩選與參考答案。ID／Question必填，重複ID與輸入公式阻擋；Years／Doc_Id可空，多年度OR，Doc_Id只抽股號作查詢篩選。Answer／標準頁與標題絕不送到模型。既有排除26、88、95、102、113保留。新版123題的真實上傳及清單預覽已確認118題有效，未執行題目集。

頁碼只要包含於chunk.page即算（[49,50]可命中P50），並核對來源文件與年度；標題命中必須在同一chunk也命中至少一個標準頁碼。Main_Section及Sub_Section不作判斷／計分。Note_Title以分號／換行分多個目標；空白、全半形正規化後完整比對，不做模糊猜測。年度不符0分，多年度OR，空Years不限制。文件以年度＋股號對照所選集合中的唯一doc_id，缺少或多份對應標為corpus_unavailable，不猜季度、文件或來源；參考Page亦保留自身文件年度與股號。

同必回內文／表格父項的子項只留第一筆並壓縮有效排名，可選標題父項不把不同內文群組合成同一命中。有效前20筆內，顯示頁碼／標題找到數（1/2等）、缺漏項與首個命中Top。N個標題各10/N分，第i個命中若在有效r名則max(0,10/N-0.5*max(0,r-i))；缺項0分。符合使用者確認的兩標題Top1＋2=10、Top1＋3=9.5、Top2＋3=9。缺Page或Note_Title仍可查詢，相應總分為null並說明無法計分，不假填0。

分開保存原始檢索子項、父項召回後、重排序結果；重排序只取實際evidence_k，不自動提高請求數或花費。若要重排Top20，請在詳細設定把保留數量設20且retrieve_k至少20。每題可展開讀證據與排名；大量明細按需建立，已顯示報告不每秒重送。保存沿用Output/Response/qa_日期時間，單批answer.md／result.json／results.xlsx。Excel每題一個直欄，列為ID、問題、分數、命中／缺漏、命中Top、有效Top1至20的chunk_id、tokens、耗時；另表保留未去重原始Top20便於核對。分數是Excel數值型別，不是文字。

用量：記錄實際問題embedding／rerank／回答API回傳用量，未知不猜。比較用內容tokens使用同一個本機BGE tokenizer、無special tokens；只讀已快取tokenizer，不為統計下載模型，缺快取標未知，不把它當供應商計費tokens。記錄每題與query_embedding／retrieval／parent_expansion／rerank／answer階段耗時，第一題標cold_query，模型在同一批重用。題目執行失敗時保存已完成階段並停止後續題目，避免重複外部費用；文件不在索引則標語料未備妥，不把未執行當成功。平均分僅計可評分且未執行失敗題，另列缺語料／失敗／未執行數，不以此冒充完整118題準確率。

EXPERIMENT_ONLY隔離：Code_2/config/evaluation.py集中enabled、top_k、總分、扣分、排除ID與上傳限制；Code_2/functions/experiments/eval_workbook.py／eval_scoring.py／eval_run.py負責讀檔、評分、執行及唯一export_batch寫檔呼叫；static/evaluation.js及HTML入口只處理實驗UI。正式環境設EvaluationSettings.enabled=False並重啟，即隱藏入口且拒絕預覽及批次，單題問答正常。移除時刪實驗模組／腳本、service.py中evaluate分支、server.py實驗預覽與資產路由及HTML入口即可；既有Output不自動刪除。一般pipeline只新增可選observer觀測與多年度OR，沒有Excel／評分依賴。export_enabled=False集中停用保存，核心查詢評分仍可執行。

本輪Code_2完整158項Python測試通過；3項Node驗證一般答案、標題開關及Excel FileReader／DOM資料隔離通過。合成批次／假模型驗證給分例子、相同chunk頁與標題、首個子項去重、錯年／文件0分、缺項與失敗、匯出／停用、固定下載與token保護。另用獨立openpyxl唯讀驗證程式匯出的xlsx可讀、每題直欄與9.5分保持float，未新增應用程式依賴。真實題目集上傳預覽成功（原生選檔首次因頁面變動中斷，後續成功），未送真實模型／重排序／LLM，依使用者要求等建庫完成才測；未宣稱真實召回品質通過。

建庫安全停止是Code的核心操作功能，見Code/README.md最新章節；不受Excel實驗enabled開關影響。

## 2026-10-26：parent_child檔名字數後綴與索引隔離（最新）

使用者要求父子切法檔名附設定字數。第四階段parent_child輸出2025_2330_chunk_700.json／.md；設定1000則為_chunk_1000.json／.md。對應Record為Record/2025_2330_700_reocrd，不同字數可在同批次並存。original檔名、doc_id及chunk_id格式不變，舊產物不改名。

第五階段網站清單、直接建庫及舊前處理相容入口支援新舊檔名；新字數後綴必須與JSON的parent_child／recursive_threshold相符，錯配於來源預檢失敗，不呼叫模型。以JSON實際設定建立索引，不靠改名變更切法。既有索引簽章已含chunking及來源規則，700與1000使用不同Chroma collection，與模型／模式隔離共同作用；底層仍可共用同模型的Chroma儲存目錄，檢索只讀所選集合，不合併兩種字數。資料庫與問答選單既有參數顯示可辨識字數。

舊Code_2 prepared實驗入口同步接受帶字數來源並分開保存其檢查產物／Record；新第五階段仍只在記憶體前處理，不新增prepared檔。實作為Code/functions/chunking/filenames.py、experiments/export_output.py、web_ui/catalog.py、embedding/direct.py、embedding/load_prepared.py及Code_2/functions/embedding/batch.py。

本輪80項相關Python測試通過：模式IO／字數共存、暫存Chroma建庫與隔離、舊前處理、父項、第五階段HTTP、父子切分及QA模式／選單。HTTP初次受沙箱WinError10013限制，允許本機測試後5項全通過。700／1000同doc_id分集合且各自檢索、錯後綴不呼叫模型均以暫存庫及假向量驗證；舊檔仍可建庫。未呼叫真實API或模型、未改寫Output或操作使用者索引。

目前已開啟的網站需閒置後關閉服務，重新由start-web.cmd開啟以載入新的來源清單程式（僅重整分頁無法更新常駐內部程序）。接著重跑第四階段產生新檔名，並用第五階段選取所需字數版本建庫；既有檔案與索引保留。

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


## 整集合移除狀態相容（2026-10-26）

Code資料庫管理新增整集合移除。中途失敗時，清冊保留collection_deletions，索引仍可列出並標記collection_deletion_pending；共用ChromaStore會拒絕建庫與檢索，請回Code重新預覽完成移除。這不是零證據成功回覆，不會自動清庫或改選別的集合。重新啟動Code_2以載入最新共用核心。移除功能及確認入口仍只在Code，未新增問答流程。


## 搬移後啟動與路徑（2026-10-26）

若搬移後介面回傳「檔案不存在」或新啟動失敗，請先關閉仍在舊位置執行的Code_2服務；舊服務可能持有原路徑並占用8765埠。從新位置重啟並重新整理頁面即可。本次已清除確認閒置的舊程序，首頁及必要API六項GET驗證200；未重建受損索引。

專案已移到D:/Financial_RAG。從新位置執行Code_2/start_gui.cmd即可；入口依腳本自身位置找Code/.venv，與Code共用的Settings依設定檔位置推導向量庫、快取、Output與密鑰位置，不需要寫死新根路徑。歷史來源紀錄不改寫，既有受損collection不因搬移自動恢復。搬移驗證見Code/maintenance/relocation_20261026.md。


第四階段2026-10-26新增最後清除chunk空白行，來源規則更新為bounded-parent-child/5.1及hierarchical-semantic-chunks/4.1-compact，schema與父子關係欄位不變。建庫及問答沿用現有契約；來源規則不同會隔離索引，舊資料不改寫。

## parent_child 5.0與檢索時的標題父項開關（目前版本）

Code第四階段新parent_child為financial-chunks/5.0／bounded-parent-child/5.0，Code第五階段已接受並保存強制內文／表格父項及可選標題父項；original及舊3.1／4.0／4.1仍相容。新版chunks才做向量，parents全部另存SQLite，不直接參與向量排名。parent_id／parent_relation表示必回父項，heading_parent_id表示可選標題父項；包含文字與表格的heading_parent可為mixed，但不是搜尋向量。

重新啟動Code_2/start_gui.cmd。選擇使用新版chunk建立的索引後，可在查詢介面勾「檢索後額外帶回標題父項」，預設不帶。開關只影響檢索時的脈絡展開，不改第四階段資料、索引或原始分數；必回的完整內文／表格父項保留，啟用時額外加入標題父項，兩者各依父ID去重並記錄matched_chunk_ids。這兩種父項可能包含重疊正文，回答前的token預檢仍會阻擋超長輸入，不默默截斷。

CLI在--ask時加--include-heading-parent；新索引的實驗終端選單亦有當題選項。未儲存此類關係的舊索引會停用畫面選項，API／CLI若要求則明確回報需用Code第五階段建新版索引。原向量檢索top_k仍代表向量命中數，啟用標題父項後展開的候選證據數可能較多；原向量距離不重算，也不能當作標題父項自身的向量分數。Markdown／JSON紀錄保存開關，證據保留父項關係類型。

搜尋、重複匯入及提交都檢查兩類父項；缺失／來源不符時報錯，不回傳不完整的假成功。完整父項跟向量及文件清冊同次提交，既有文件刪除流程也會同步清除它們。此來源規則使用獨立collection，不混搜舊切法；本次沒有重建或改寫任何使用者索引。

本次Code_2全套140項（模擬服務及真實暫存Chroma）通過，含雙父項保存／重複匯入／缺父阻擋、查詢及HTTP傳參；另有Node檢索開關契約測試。Code相關121項及真實raw二→三→四→前處理記憶體核對見Code/maintenance/parent_child_v5_validation.md；沒有真實模型／API品質驗收。下方「只讀直接Parent、不支援標題展開」限舊格式，不再代表新版功能未完成。

## 2026-10-26：接受第四階段content首行4.1

最新來源規則升hierarchical-semantic-chunks/4.2-context：生成content首行的說明會移除年度片段，年度依原years表示；來源metadata及正文不改。schema仍4.1，舊首行仍可驗證。Code_2沿用首行，不另行移除年度或重推years；新產物依來源規則版本隔離索引，不自動重建舊索引。本輪相關本機測試合計120項通過（含QA模擬63項），沒有真實模型測試。

Code第四階段parent_child現在輸出financial-chunks/4.1：每個chunk／Parent的content本身包含年度、股票代號、章節及適用說明首行；content_prefix標記並驗證該生成首行。Code第五階段前處理及Code_2回答證據不再重複補相同章節／說明，HTML表格仍轉為可讀文字。父子核對只移除通過欄位重算驗證的首行，然後比對來源正文；頁序及來源位置保持。original及舊版4.0維持原組合方式。

年度與說明沿用既有第四階段判斷，Code_2不重新推算。新規則版本會產生不同索引簽章，需自行用Code第五階段建立所選新產物的索引；本次未改寫或重建既有索引。QA模擬63項、前處理24項及Code相關30項共117項局部測試通過；另有真實tagged唯讀記憶體來源核對，沒有真實模型／API品質驗收。新700字切分與可選標題父項召回尚未實作。

## Gemini／GPT、API金鑰與可略過重排序（2026-10-26最新）

重新啟動Code_2/start_gui.cmd，右上角「API設定／金鑰」可新增／刪除設定及key，與Code第五階段共用。操作與檔案清單見Code/README最新「API設定與金鑰管理」。自訂名稱會出現在對應選單，key不會顯示或保存於Response。API key只決定身份與權限；模型ID由使用者指定。GPT填入帳號可用、支援Responses及Structured Outputs的gpt-模型ID，不自動選定GPT版本或探測帳號。

目前只支援BGE-M3／voyage-finance-2向量檢索、Voyage重排序，以及Gemini／GPT回答；沒有BGE reranker。先選Embedding模型、切法、索引；Voyage檢索再選其API設定。到重排序模式選Voyage設定；完整回答另選Gemini或GPT的LLM設定。只有設定完整且有key的項目可選；刪除選中設定後需重新選擇，不自動換另一服務。檢索仍用與索引相同的embedding模型，換LLM或key不重建向量。

完整回答勾選「完整回答前使用Voyage重排序」時沿用50→10→LLM；取消則取向量檢索排名前evidence_k份完整證據→LLM，不呼叫重排序／不讀其key。證據數量仍可調整且不得超過召回數量，超長仍停止、不切表。BGE＋略過重排只需LLM key；Voyage檢索依舊需要embedding key。到重排序模式不允許關閉重排；只檢索不執行後續服務。

### 實作與報告

QASettings新增answer_provider、answer_profile、rerank_profile及rerank_enabled（預設True）；Settings.embedding_profile保存查詢向量用的設定ID。執行時再解析ID到key，key不進入工作參數、模型簽章或Response；模式不需要的服務不讀key。CLI／既有Python呼叫無指定profile時保留原.env相容行為，網頁使用明確的profile選單。

functions/qa/openai_answer.py使用標準庫HTTPS呼叫固定OpenAI Responses端點，無新增SDK。把共用Gemini樣式schema轉成小寫JSON Schema，各object設additionalProperties=false；先以完整instructions／input／text schema送responses/input_tokens預檢，超過32000成本預算停止，其後生成一次max_output_tokens=4096、store=false、truncation=disabled，不跟隨重新導向、不自動重試、不加工具。拒答、非completed、無效JSON或不預期輸出會停止，保留已取得用量；模型不支援介面時回報錯誤，不切換版本。

GPT與Gemini共用既有evidence、引用逐字核對與Decimal計算驗證。Response Markdown／JSON保存實際provider、model、model_version、設定ID、token用量及完成階段；略過重排明確標示，沒有虛構rerank排名、分數或費用。GPT output_tokens包含服務回報的推理等輸出，不把它全算成可見答案；未知仍標未知。提示詞版本與回答schema未改，不因換provider新增外部搜尋或投資建議。

官方依據（本次已搜尋並開啟）：[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)、[Counting tokens](https://developers.openai.com/api/docs/guides/token-counting)。參考資料另核對Reference Sources/EMBEDDING/evaluate_retrieval.py的BGE／Voyage分工；未搬入其CSV／pickle或執行參考程式。其副本GitHub commit／授權未知，不宣稱重現成果。

### 本輪實際驗證

Code_2全套139項通過，含新增5項GPT／可略過重排測試與1項真實loopback、合成key新增／刪除HTTP測試；Code設定8項、HTTP／程序11項及三份Node測試通過，詳見Code/README。涵蓋完整證據及嚴格schema、token超限不生成、拒答／不完整／壞JSON停止、HTTP429不洩漏body／key且不重試、略過重排只讀LLM key並沿用引用驗證。Python編譯及JS語法檢查通過。這些是模擬API與本機測試，沒有真實金鑰、真實GPT／Gemini／Voyage生成品質或額度驗收，也未更動既有向量索引。

## 2026-10-25最新分工：Code建庫，Code_2查詢問答

使用者已確認前處理與建庫核心移入Code，成為其網頁第五階段；直接選chunk JSON並在記憶體前處理，不另存prepared。操作見`Code/README.md`最新「第五階段」。下方關於Code_2前處理／建庫選單、四頁籤、prepared批次輸入與Code_2欄位設定的內容為歷史，不再作為目前入口。

Code_2繼續負責檢索、Voyage rerank-3-lite重排序及Gemini回答；GUI現在提供「查詢與問答」「執行紀錄」。三種模式皆先選Embedding模型→切分模式→索引集合；集合標籤含識別、文件數、chunk數及切分參數。舊索引沒有模式資料時列在「舊版／未記錄」，不自動視為original或改寫版本。舊索引規則仍可能不符合目前QA驗證，需用Code第五階段建立新索引；本次未自動重建。

重新啟動`Code_2/start_gui.cmd`，沿用Code/.venv。CLI --ask、--list-indexes與互動問答保留；舊--prepare-batch／--embed-batch明確回報已移至Code，不執行建庫。問答仍保存Output/Response的Markdown及JSON，未變更為GPT，沒有新增問題重寫。

模型、欄位、儲存契約權威設定是`Code/config/embedding.py`與`embedding_fields.txt`，Code_2/config/embedding.py只轉接。同名舊embedding模組轉接到Code的唯一實作；問答核心依舊在Code_2/functions/qa。資料庫仍在VectorStore/chroma，快取仍沿用Code_2/.cache/embedding；既有Output與索引未搬動。舊實驗prepared寫檔模組保留，不是新流程必要輸入。

文件瀏覽與刪除在Code第五階段下方資料管理；只作用於當下集合，依doc_id整份刪除，不影響其他模型或切法。刪除中標記會被共用儲存層排除於新檢索之外，失敗需回管理頁重試。驗證記錄見Code/README最新節；本輪Code_2全套133項已執行，1項Windows暫存Chroma清理鎖錯誤單獨重跑通過，不宣稱該次全套一次零錯誤。新索引選單Node測試、Python編譯與JS語法檢查通過；真實API／問答品質尚未驗收。

## 兩種切法的建庫與回傳（目前規則）

本節依現有程式整理，作為Code第四階段與Code_2的銜接說明；下方日期紀錄保留歷史背景。切分細節見[Code第四階段說明](../Code/README.md#第四階段兩種切法與父子關係目前規則)。Code_2讀取已切好的結果，不在這裡重新切段或自行建立更高層Parent。

### 輸入與前處理位置

第四階段產生新`Financial_chunk_日期_時間`批次。Code_2接受整個批次或其中一個模式目錄，讀取`年度_代號_chunk.json`，不把chunk Markdown當成建庫資料來源。模式子目錄與JSON內chunking.mode必須一致。

```text
Output/markdown_chunk/Financial_chunk_20261025_16-08-10/
  parent_child/2025_2330_chunk.json
        ↓ 前處理，保留來源批次及模式
Output/embedding_prepared/Financial_chunk_20261025_16-08-10/
  parent_child/2025_2330_prepared.json
  parent_child/2025_2330_prepared.md
  parent_child/Record/2025_2330_reocrd
```

original模式同理。同次所選批次若包含兩種模式，可一起前處理，也可選單一模式。舊平面批次及舊命名仍可讀；相同prepared產物已存在時仍拒絕覆寫，不自動建立新前處理時間批次。來源Record僅供追溯核對，缺失不單憑此阻擋有效JSON；內容格式、來源識別或父子關係錯誤仍會停止。

可用既有選單1，或從專案根目錄執行以下命令（範例路徑需換成實際存在的批次）：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --prepare-batch "Output/markdown_chunk/Financial_chunk_20261025_16-08-10/parent_child"
```

### 哪些內容會做embedding

|來源資料|前處理與建庫用途|檢索回傳用途|
|---|---|---|
|chunks內沒有parent_id的項目|建立搜尋文字及向量|直接回傳自身|
|chunks內有parent_id的Child|建立搜尋文字及向量，保留parent_id及part_index|取回其直接Parent|
|parents內完整父項|完整保留，不另外建立父項向量|供Child命中後讀回|

這套處理同時適用兩種切法：original的一般文字通常直接回傳，特殊綁定可帶parent_id；parent_child的一般附註文字也有父子關係。查核報告依Code現有規則直接以chunk回傳。Code_2依資料的parent_id判斷，不只看到模式名稱就把所有項目都當Child，也不把parents再併入搜尋列表。

### 搜尋文字與原文分開保存

前處理為每個搜尋chunk建立embedding_text：依既有title樹加入大標與各層標題，再加入不重複的directions說明及table_context，最後接轉換後正文。HTML表格轉為可讀的管線表示；既有管線表格與cannotfindtable候選也支援，但候選不會因此還原成正確欄列。

original_chunk保存完整原chunk，prepared的parents保存完整父項；組合搜尋文字不會改寫它們。HD／說明控制標籤不直接塞回原始content。table_year原文保留於metadata，不額外插入搜尋語境；表頭或正文原本已有年度文字仍會保留。years沿用第四階段的西元年度清單，Code_2不另猜年度。

`Code/config/embedding_fields.txt`決定實際送給模型的欄位。現有設定是embedding_text做embedding；stock_code、years、page、content_type等作metadata。統一網站沒有欄位用途選擇器；若維護者修改專案設定，仍須保留必要來源及original_chunk。不要直接把整份JSON序列化當搜尋文字。

### Metadata不等於所有欄位都已能篩選

prepared metadata保留章節、年度、頁碼、table_context等資料，新格式另有parent_id、part_index、table_year、directions、table_ids及適用時的table_completeness。原始來源區間、完整年度來源等仍可從original_chunk／父項追溯。

真正寫成Chroma可篩選欄位的內容，取決於embedding_fields.txt的metadata或both設定；不因prepared多了欄位就自動啟用篩選。沒有配置的資訊仍可能保存在原始payload。保留純量及同型別清單，不把所有metadata轉成字串；空值或空清單不寫入Chroma篩選欄，但原值保留於payload並記錄省略欄位。複雜結構不得直接當篩選值。

### Parent保存與命中後回傳

搜尋向量、選定的篩選metadata及原chunk payload進入對應索引；完整Parent另存同庫`ingestion.sqlite3`的`table_parents`資料表。名稱沿用歷史設計，實際也可保存文字Parent。父項以collection、run_id及parent_id區分，同一份文件提交時保存一次，不靠實驗Output供正式檢索讀回。

`store.search`取得Child後讀回對應父項，`qa.pipeline.evidence_rows`核對文件識別、內容及頁序再建立回傳證據。Child沒有可靠Parent時回報錯誤，不假裝回傳成功。只讀直接Parent，不再往上取完整章節；同父命中去重，matched_chunk_ids保留所有命中的Child識別碼。沒有parent_id的一般chunk直接成為證據。

例如Child 1、Child 2都屬於Parent A，另外命中獨立Chunk B，回傳為Parent A及Chunk B兩筆；Parent A使用完整內容、頁碼及來源區間。其後是否重排序／生成答案依所選入口，不因完成建庫或父項讀回就宣稱所有問答階段已執行。

### 模式、參數及索引隔離

新格式索引簽章包含embedding模型、欄位用途、前處理規則、chunking模式、parent_limit／recursive_threshold／child_target／document_period及來源切分規則。因此original與parent_child，或不同切塊參數，使用不同collection，不在同一檢索範圍混用。僅移動／改名資料夾不能改變已存的切法；參數修改後需重新切chunk、前處理並建庫，不能只改JSON版本號。

重複建庫核對已提交內容與父項，父項遺失不當作完整成功。更新同collection內文件沿用既有提交與回滾機制；不因新增模式自動刪除舊collection，檢索時要選對已完成的索引。

### 長表及token超限

Parent1500、Child300是字數設定，不是模型token限制。完整表格或不可拆綁定可能超限，HTML轉管線也不保證符合模型長度。建庫先對所選模型計算整份文件全部搜尋chunk的tokens；任一超過限制，回報blocked_token_limit，列出chunk_id、tokens與limit，該份不產生向量、不提交資料。前處理成功不代表已通過token檢查。

完整Parent即使不做embedding，回傳後仍可能超過重排序或回答模型的輸入限制，沿用既有檢查並明確失敗，不默默截表。本次沒有新增摘要模型、裁表或其他降級方案。

### 維護入口與本次範圍

- `functions/embedding/paths.py`及batch.py：模式目錄、來源／輸出、來源報告核對。
- prepare.py／metadata.py／table_text.py：契約驗證、搜尋語境、metadata與表格文字。
- fields.py及`config/embedding_fields.txt`：欄位用途與可篩選型別。
- indexing.py／store.py：token前檢、簽章、向量與完整父項保存。
- `functions/qa/pipeline.py`：來源核對、直接父項替換及去重。

本次僅核對程式並更新本文件，沒有改程式、欄位設定、資料或索引，也沒有執行模型／API／重新建庫。下方歷史測試紀錄不是本次重新驗證，不能據此宣稱目前真實檢索品質或整批100–200份已驗收。

## 2026-10-25：raw前綴相容

批次名稱比對同步接受Financial_raw_日期_時間及舊格式；僅命名相容，沒有新增處理raw來源或改動embedding／檢索。

## 2026-10-25：新階段批次名稱相容

Code第二至第四階段改為每次新建Financial_階段_YYYYMMDD_HH-MM-SS。Code_2此次僅擴充config/embedding.py的BATCH_PATTERN，接受新名稱及原舊名稱；chunk的original／parent_child子目錄、前處理、模型、metadata及檢索規則不改。前處理仍沿用所選chunk批次名稱。未搬移Output或重建索引。

## 2026-10-25：雙模式chunk4.0串接（最新）

接受新financial-chunks/4.0及原1.0／2.0／3.0／3.1，不修改原檔版本號。新資料須有chunking模式及三項參數、directions／table_year來源記錄、table_ids；既有章節、年度、頁碼、父子及來源驗證仍有效。

讀取`Output/markdown_chunk/<Financial批次>/original/`或`parent_child/`，前處理對應輸出`Output/embedding_prepared/<同批次>/<同模式>/年度_股票_prepared.json`，同模式有自己的Record。同批外層可選兩模式一起前處理，或選單一模式；CLI與網頁清單顯示相對模式路徑。舊平面批次仍支援，不移動既有產物；模式資料夾與JSON模式不符會拒絕，不猜測來源。相關路徑解析集中`functions/embedding/paths.py`。

新content不含HD／說明控制標籤。`prepare.embedding_context`依既有標題樹、directions及table_context組合embedding語境，原始content完整保存在original_chunk。table_year僅保存在metadata，不自行加入embedding語境；表內本有年度文字仍保留。HTML→管線表示沿用原轉換，同時接受管線表格及cannotfindtable候選；候選不重建欄列、不宣稱辨識成功。

metadata另承接parent_id、part_index、table_year、directions、table_ids；保留原years／章節及table_completeness。預設embedding_fields.txt未改，因此新增欄位不代表已自動成為向量庫可篩選欄位。索引簽章納入chunking模式、Parent／Child／HD門檻及來源切分規則，模式或參數變更會使用不同collection，避免不同切法在同一檢索範圍混合。未重建／刪除原索引。

普通chunk直接回傳；有parent_id則讀同一索引的直接Parent，同父去重，不向上擴展整章。父項沿用正式SQLite保存機制（歷史資料表名table_parents同樣能保存文字父項），不依賴Output。原始父表／子塊不因轉換搜尋文字被裁切，token超限仍整份停止並列出。

Code四階段使用PDF環境；本目錄操作仍用`Code/.venv/Scripts/python.exe`，不要混用兩邊頂層functions模組。本次235項相關局部測試通過，包含71項索引／檢索及新模式簽章隔離、直接Parent回傳去重；實際暫存Chroma使用假向量，未呼叫真實Voyage／BGE／回答API。2024_2330的兩模式202／224個chunk在記憶體前處理及schema驗證通過，未寫正式Output或建庫。真實模型token數與檢索品質尚未驗收。

2026-10-25新增選用metadata欄位table_completeness：承接Code切分規則3.3（schema仍3.1），表格content含`<cannotfindtable>`為整數0，否則1。新欄存在時驗證型別、表格類型與內容一致；舊chunk缺此欄仍可讀，不補造結果。build_metadata保留該值，original_chunk／parents仍完整保存來源。未改預設embedding_fields、模型或索引，欄位尚未自動加入既有向量庫篩選；本次也未實作疑似表格的全文embedding轉換。81項Code及Code_2局部測試通過，包含普通表格前處理保真與候選的metadata／輸入驗證；不宣稱疑似表格全文建庫成功。

2026-10-25新增chunk3.1支援：接受原有1.0／2.0／3.0及新3.1；3.1必須有main_section、sub_section字串與note_title路徑清單，且與既有title階層一致。前處理metadata保留三新欄位（原main_title／hd2_title暫留相容），old chunk沒有新欄時維持原metadata，因此不擅改舊prepared。需要自行配置時可使用metadata.main_section、metadata.sub_section、metadata.note_title等欄位路徑；本輪沒有更動預設embedding_fields.txt，所以不會自動改既有欄位用途或向量庫。

166項Code及Code_2局部測試包含新欄位前處理保真通過；2024_2330的223塊Code_2輸入schema核對成功，查核9塊note_title皆[]。沒有前處理該份全文／執行模型／API／索引；新特殊表格與說明標籤的全文embedding處理仍須後續銜接，不可將schema通過當作可直接完成整批建庫。

2026-10-25輸入相容調整：prepare.validate_document新增接受Code的financial-chunks/3.0（查核報告已納入、公司沿革起點已取消），3.0可有title.heading=null，前處理標題與metadata不造假hd2；舊1.0／2.0仍要求原有效標題樹。24項既有及新增前處理測試包含在本輪161項局部測試中通過。新Main_Section／Sub_Section／Note_Title欄位命名／多路徑尚待使用者確認，此刻仍讀既有title結構；新說明標籤、疑似表格embedding策略尚未完整銜接，不能據此宣稱整批新chunk可建庫。沒有執行真實模型／API／索引或改既有資料庫。

2026-10-24環境分工：Code四階段已另用`Code/.venv_pdf/`，Code_2仍沿用原`Code/.venv/`與本文件啟動指令。本輪未修改Code_2套件或驗證其模型／檢索，不把Code的修復當成Code_2的成功。BGE／Chroma依賴請勿裝進PDF專用環境；PDF環境鎖檔為Code/requirements.pdf.lock，背景見Code/README.md最新節。

## 2026-10-23：父表召回與唯一years標籤（現行規則）

- 新prepared為financial-embedding-prepared/2.0，前處理與索引規則2.0。讀新financial-chunks/2.0的chunks＋parents，完整父表只保存一次；支援舊chunk 1.0前處理，但舊內容沒有新附表分組／年度判定，需從tagged重新切塊才有新結果。舊prepared需重新前處理，不直接改版本號。
- metadata只有years作年度標籤／篩選，移除report_year。純文字用文件年；表格可有多個年度，沒有明列年則用文件年；文件年份仍在doc_id。前置標題table_context加入embedding文字，並保留章節路徑；不是正式表名。year_sources原文與來源留在original_chunk。
- --year 2024查years是否包含2024，--report-year仍為相容別名；網頁／CLI標示「內容年度」。網頁請求report_year為舊介面欄位名稱，實際查years。選2024可以命中2025財報內含2024／2025比較資料的表格，但不會命中僅標2025的文字塊。歷史回答紀錄保留原篩選語意。
- 子塊做embedding及Chroma向量；完整父項在同庫ingestion.sqlite3的table_parents表以collection、run_id及parent_id保存，不依賴Output。父項與子塊在同一文件提交，失敗回滾；缺父項不能假成功。重複匯入亦核對完整父表是否仍存在。
- 召回子塊後讀完整父表，matched_chunk_ids保留命中的子塊，同父項去重，再交重排序／回答。回傳來源以父項完整頁序與來源區間為準。完整父項可能較長，仍遵守重排序不截斷及回答輸入token檢查，超限會明確失敗，不默默裁表。
- 新規則及欄位設定隔離到新collection；既有索引沒有重建或刪除，舊索引會明確提示不支援新規則。實際使用需重新產生tagged／chunk、前處理與建庫；原同名Output防覆寫仍生效。
- 本次以假向量＋實際暫存Chroma驗證多年度contains篩選、完整父表讀回、同父項去重、父項遺失及寫入失敗回滾；未呼叫Voyage／Gemini或重新計算真實BGE索引。真實年度辨識／檢索品質仍待人工核對。

下方report_year及「完整表格一律單一向量」等說明為歷史版本；現行行為以上節為準。

目前是實驗階段。依使用者確認在現有 `Code_2/` 獨立開發，讀取 `Code/` 產生的chunk，不改既有PDF、tagged或chunk。需求見 [USER_STORIES.md](../USER_STORIES.md) 的US-14，規範見 [AGENTS.md](../AGENTS.md)。

2026-10-23 更新：前處理直接驗證 chunk JSON 的 schema、文件識別、必要欄位與內容，建庫直接驗證 prepared JSON；同批 `Record/*_reocrd` 改為可選的執行／來源核對報告，缺失或雜湊不一致會記 `source_record_issue`，不單憑報告阻擋有效資料。來源檔在處理期間變更、資料本身格式錯誤或文件識別不符仍停止。前處理 23 項、建庫 22 項本機測試通過；全套 Code_2 測試在此環境的本機 HTTP 案例遭 Windows `WinError 10013` 阻擋，模型下載的暫存檔更名測試有時遭 `WinError 5` 阻擋。既有索引未重建，也沒有呼叫真實 Voyage API。

現在支援獨立前處理、BGE-M3＋Chroma與Voyage Finance 2＋Chroma。使用者已確認本機CPU、兩模型分庫、欄位文字設定、超限整份停止；本次不呼叫真實Voyage API。下方「前處理」段落記錄US-14的行為與歷史驗證，建庫行為以本節為準。

2026-10-22追加：已加入選單4的單題問答；採用原始問題、不重寫，Voyage rerank-3-lite重排序及Gemini gemini-3.1-flash-lite回答。以下建庫驗證與歷史紀錄不能當成本次問答品質驗收，問答操作與驗證見文件末段。

## 建庫操作（US-15）

啟動方式不變：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py
```

| 選單 | 功能 |
| --- | --- |
| 1 | chunk JSON前處理，保留既有使用方式 |
| 2 | 選prepared批次，再選BGE、Voyage或兩者依序執行 |
| 3 | 查看最近十筆各模型建庫紀錄，包含失敗及超限chunk |
| 4 | 選已提交索引、可選股票代號／報告年度，再輸入單題問答；會使用API |
| 0 | 離開 |

預設模型在config/embedding.py的default_backend，可設bge、voyage或both；CPU batch=1、threads=2，Voyage batch最多16筆及120000 tokens、每次逾時120秒、零自動重試，參數集中在同檔。本機約15.7 GiB RAM，沒有據此宣稱整批速度足夠；本程式依序處理單份文件，不啟動並行模型。

```powershell
# 先檢查整份的token數；BGE首次只下載tokenizer，不下載完整權重。
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --embed-batch "Output/embedding_prepared/Financial_20261022_01-23-16" --backend bge --check-only

# 真正建庫：將產生向量並寫VectorStore。
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --embed-batch "Output/embedding_prepared/Financial_20261022_01-23-16" --backend bge
```

Voyage預設關閉，程式在讀金鑰或建立client前阻擋。不會因為選了both就偷偷啟用雲端；BGE成功與Voyage被阻擋會分別回報。之後使用者要實際外傳財報時，須自行明確啟用（本次開發未執行以下命令）：

```powershell
# 此命令會向Voyage傳送所選embedding欄位，可能計費。
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --embed-batch "Output/embedding_prepared/Financial_20261022_01-23-16" --backend voyage --allow-voyage-api
```

VOYAGE_API_KEY由非空環境變數優先，否則只解析專案根目錄.env的該欄位，不載入其他欄位、不展開變數、不顯示金鑰；依.env.example另加空白欄位後由使用者填入，不改使用者現有.env。

`--no-export`只適用前處理的實驗檢查檔；不代表建庫不寫資料庫，也不代表API不計費。建庫要只檢查請用`--check-only`，它不產生向量、不建立資料庫／操作清冊。Voyage仍須明確啟用才能建立其client；其count_tokens使用本機tokenizer，首次可能下載公開tokenizer。

## 欄位設定文字檔

開啟 `Code_2/config/embedding_fields.txt`。每行左邊是prepared JSON中單一chunks項目的實際欄位路徑，右邊是模式：

```ini
[FIELDS]
embedding_text = embedding
metadata.stock_code = metadata
metadata.report_year = both
metadata.page = metadata
original_chunk.content = ignore
```

| 模式 | 行為 |
| --- | --- |
| embedding | 只參與向量文字 |
| metadata | 只保留為篩選標籤 |
| both | 同時參與向量文字及篩選 |
| ignore | 不參與這兩種用途 |

目前預設embedding_text單獨向量化，metadata各欄只作標籤；上方both是修改示範，不是預設。其他被選文字依設定順序加入，以欄位名稱標示其值。embedding_text已有標題與正文，額外再選title或content可能重複，程式不擅自去重或更改選擇。

- 不存在的路徑、重複設定、未知模式、沒有embedding欄位會在載入模型前失敗；缺設定檔不猜預設。
- `original_chunk.content`選embedding時先轉為乾淨文字／pipe表格；`original_chunk.title`選embedding時轉成可讀標題索引，不直接序列化整棵JSON。
- 複雜物件不能直接作Chroma篩選欄位，可選`original_chunk.title.main_title`等文字子欄位。標籤名稱使用路徑最後一段，例如page；兩條路徑同名時拒絕，避免覆寫。
- Chroma接受的純量及非空同型別清單保留原型別；空清單或null不寫入其篩選metadata，欄位名列於omitted_filter_fields。完整所選metadata與original_chunk仍在資料庫payload，不轉成字串冒充清單。
- 即使設定ignore，必要來源識別與完整原chunk固定保存；不能移除`_sys_`開頭的內部識別欄位。這些內部欄位不參與embedding。
- `--fields 路徑`可改讀另一份文字設定。模式、順序或模型版本改變會使用不同collection；只改註解不改設定內容時仍可重用既有索引。

## 長度、完整性與索引儲存

每份先計算全部chunk的實際模型token數；任一超限，整份回報blocked_token_limit，列出chunk_id、tokens、limit，該次不寫入該份向量。BGE原生上限8192，未沿用舊程式1024截斷；Voyage Finance 2上限32000，計數包含document前綴，請求使用input_type=document、truncation=False。

模型向量在單份文件全部成功後才寫入；不同批次的其他文件可繼續。遇中止則停止後續。程式不替換模型、不切表、不摘要、不自動重試API。API失敗仍可能已計費，未提交只代表資料庫未完成，不代表零費用。是否以多個搜尋向量處理超長表格仍未實作。

```text
VectorStore/chroma/
├─ bge/       # BGE Chroma檔案＋ingestion.sqlite3
└─ voyage/    # Voyage Chroma檔案＋ingestion.sqlite3
```

模型、版本、維度、欄位規則與前處理規則產生collection簽章，兩模型不混存。每筆Chroma documents存完整JSON payload（含embedding_text、有型別metadata、原chunk與原HTML），但傳給模型的只有設定所選的文字；不把這份儲存JSON當embedding輸入。檢索端因此能取回原文，不需再讀Output。

必要索引清冊ingestion.sqlite3保存已提交文件及attempts操作紀錄，不存金鑰或財報全文。此清冊是正式儲存的一部分，與可停用的實驗Output分開。相同來源與設定重複匯入會驗證既有筆數後回報already_indexed，跳過向量計算。相同doc_id來源改版時明確拒絕，更新／移除策略仍需使用者確認，不自行刪除舊索引。

只有已寫入且提交清冊成功的文件才可由ChromaStore.search召回；失敗時只清理該次run新增資料。強制終止／斷電可能留未提交點，程式不讓它們參與檢索，重跑時明確要求確認恢復方式，不自動清空。Windows用公開client.close釋放檔案鎖。

## 新增依賴與重現

本次安裝sentence-transformers==6.2.0、chromadb==1.5.9、voyageai==0.5.0；沿用Python 3.11.9與Code/.venv，既有torch==2.14.0、transformers==5.17.0及python-dotenv==1.2.4。pip check通過，完整共享環境版本另記Code_2/requirements.lock，Code既有鎖檔保留原狀。

```powershell
& .\Code\.venv\Scripts\python.exe -m pip install -r Code_2/requirements.txt
```

BGE鎖定公開revision `5617a9f61b028005a4858fdac845db406aefb181`，首次權重可能約數GB，下載到Code_2/.cache/embedding，不發送財報。後續優先讀完整本機快取；不要求使用者設定HF金鑰。快取與VectorStore已加入Git忽略，未刪舊快取。Voyage API名稱不是不可變權重commit，不能宣稱鎖定其服務端實作。

官方介面依據：[BGE-M3模型卡](https://huggingface.co/BAAI/bge-m3)、[Sentence Transformers](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)、[Chroma](https://docs.trychroma.com/docs/collections/add-data)、[Voyage embedding](https://docs.voyageai.com/docs/embeddings)。另閱讀了實際安裝SDK的方法簽章與tokenizer／client.close行為，未照抄舊API假設。

## 建庫驗證（本次）

52項單元／模擬及真實Chroma暫存庫測試通過（本機Windows執行），包含型別篩選、原文取回、重複匯入、規則隔離、失敗清理、未提交資料不可召回、整份token預檢、Voyage關閉／錯誤訊息保護。模擬向量只用於暫存測試庫，不放進正式VectorStore。未呼叫真實Voyage。新增4項公開權重下載模擬測試，包含連續片段恢復、SHA不符拒絕、錯誤Range拒絕及不覆寫不符的既有權重。

指定176個chunk已以BGE tokenizer真實計數：最大3987、總計63329 tokens，皆低於8192。這只驗證目前設定與這份樣本，不能當作100–200份的統計或保證。

## 前處理使用方式（US-14）

在專案根目錄啟動，使用既有Python 3.11環境：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py
```

選「1」，再選 `markdown_chunk` 批次。選「0」返回／離開。命令列也可直接指定批次：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --prepare-batch "Output/markdown_chunk/Financial_20261022_01-23-16"
```

若該批次已經有prepared產物，再執行會阻擋覆寫。只想檢查，可加 `--no-export`：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --prepare-batch "Output/markdown_chunk/Financial_20261022_01-23-16" --no-export
```

`Settings.export_enabled=False` 亦可集中停用寫檔；命令列未傳 `--no-export` 時沿用此設定。前處理本身無外部請求，因此此入口不外傳資料；建庫請依前面的模型說明操作。

## 檔案分工與環境

```text
Code_2/
├─ main.py                         # 獨立選單／命令列
├─ config/embedding.py             # 路徑、版本、實驗寫檔開關
├─ functions/embedding/
│  ├─ batch.py                     # 批次與同批Record驗證
│  ├─ prepare.py                   # schema檢查、標題脈絡、記憶體結果
│  ├─ table_text.py                # HTML表格解析、合併格展開與pipe表格
│  ├─ metadata.py                  # 有型別的中立metadata
│  ├─ fields.py / load_prepared.py  # 欄位模式與同批來源驗證
│  ├─ providers.py / keys.py       # 模型適配與指定密鑰讀取
│  ├─ model_download.py            # 公開權重分段下載與SHA驗證
│  └─ indexing.py / store.py       # 整份預檢、向量化、提交與查詢
├─ functions/experiments/
│  └─ export_output.py             # EXPERIMENT_ONLY集中輸出
└─ tests/test_preparation.py
```

前處理核心僅使用Python標準庫；建庫新增的依賴與版本見上方，仍共享既有虛擬環境。為避免與 `Code/config`、`Code/functions` 同名，程式明確使用 `Code_2.*` 套件路徑，不匯入Code內部模組。從其他工作目錄開啟main.py也能定位專案；命令列相對輸入路徑仍依工作目錄解析。

參考來源為本機 `Reference Sources/EMBEDDING/Embedding/data_loader.py`、`embedding_bge_chroma.py`、`embedding_voyage_chroma.py` 的職責分離概念；已閱讀，沒有複製原始碼或載入其模型。該本機副本的GitHub網址、commit與授權資訊未取得，不能宣稱重現其檢索效果。

## 輸入輸出

只讀 `Output/markdown_chunk/<Financial批次>/*_chunk.json` 與同批 `Record/年度_股票代號_reocrd`。驗證schema、文件與檔名識別、Record成功狀態、批次、檔名、來源雜湊、筆數及JSON雜湊；不掃入目錄JSON。新時間格式與既有流水號批次均可讀。

```text
Output/embedding_prepared/Financial_20261022_01-23-16/
├─ 2025_2330_prepared.json
├─ 2025_2330_prepared.md
└─ Record/2025_2330_reocrd
```

JSON根版本 `financial-embedding-prepared/1.0`、規則 `embedding-prepare/1.0`。每個prepared chunk包含：

| 欄位 | 用途 |
| --- | --- |
| chunk_id | 沿用原chunk，不建立新切分編號 |
| embedding_text | 標題脈絡＋正文或pipe表格，未做token截斷 |
| metadata | 股票代號字串、report_year整數、years／page整數清單、content_type與大／小標字串、空data_tags清單 |
| original_chunk | 完整原chunk，包含原HTML、title樹及來源位置，不改寫 |
| preparation | 原內容／向量化文字字元數、HTML片段數、待確認的token檢查狀態 |

原始來源JSON檔案雜湊保存在 `input_sha256`；上游tagged雜湊仍是 `source_sha256`，不可混用。Markdown是embedding_text檢查版，不是原HTML副本；完整原文在JSON的original_chunk及原始chunk檔。

年份／股票代號由來源doc_id核對檔名與Page，不推論公司名稱、比較年度或財報季別。沿用來源page欄位；舊chunk可能含相鄰頁的純空白邊界註解，不把它新增成正文頁碼。非空文字頁與metadata不符仍拒絕。

prepared的metadata是中立格式；目前由fields.py做Chroma型別適配，空陣列不作篩選但完整值仍保存。完整title樹存於original_chunk，不把樹全部轉字串。

## 文字與表格規則

- 搜尋用文字移除Page註解與content／table／page控制語法，保留正文和下層標題文字。主標、hd2放前面；多個下層章節以明確的「本塊小節索引」列出葉節路徑，不把最後一個子節當整塊的唯一標題。正文中的標題仍留在原位置。
- 每段HTML table轉成一張pipe表格；同一跨頁chunk內可有多張，仍為同一完整chunk。中間「接次頁／承前頁」文字、重複表頭及數字保留，不重新決定是否接表。
- rowspan／colspan覆蓋的格子填入原儲存格文字；真正空白不推填，不展開「同上」的語意。列寬不足僅補空欄以符合pipe語法，首列照原內容作顯示分隔，不猜財務欄名。
- `|`轉義、儲存格內換行以 `<br>` 保留；HTML實體解碼。一般水平空白壓為單一空格，保留負號、括號、小數、百分比、幣別與單位。沒有修正Docling原有錯欄或OCR錯字。
- 空表格、巢狀表格、合併格重疊／跨越實際列數、未閉合表格、未知HTML標記會明確失敗，不能輸出半份成功資料。這不是通用網頁HTML修復器。
- 既有prepared保持前處理階段的`token_count=null`及`pending_model_selection`，不回寫舊產物。建庫已選模型、獨立計算tokens並記錄於索引操作清冊；多搜尋向量仍未實作，不截斷長表格。

## 實驗輸出與失敗

`functions/experiments/export_output.py` 是Code_2自己的獨立實驗模組，不更動Code既有寫檔程式。呼叫在embedding/batch.py；開關是Settings.export_enabled／--no-export；產物如上。正式移除時移除該呼叫與output_dir設定，保留prepare_document的記憶體介面。

整批開始前檢查既有目標，任一衝突即停止；單份資料失敗只寫failed Record，繼續其他文件。Ctrl+C則記錄interrupted並停止後續。成對輸出寫入失敗，清理僅本次建立的半份檔案，嘗試記錄失敗；無法寫Record時直接回報例外。強制終止程序／斷電不能保證清理，殘留檔不當成有效成功，下次不自動刪除。

## 本次驗證（2026-10-22）

測試指令：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 -m unittest discover -s Code_2/tests -q
```

本次22項測試通過，含合併格展開、空白／符號／數值保留、異常表格、標題樹、有型別metadata、長表格不截斷、雜湊錯配、批次繼續／中止、半份寫檔清理、防覆寫、獨立main啟動與停用寫檔。這是本次重新執行，未重跑Code的PDF／OCR／Gemini。

實際既有 `Financial_20261022_01-23-16/2025_2330_chunk.json` 已完成一次輸出；176個chunk（92文字、84表格）、96段HTML表格與994列轉成1090行pipe表格（含96行語法分隔列）。prepared的original_chunk逐筆與來源相等；來源與輸出SHA一致，有型別的年份及頁碼已核對。原文字節未改。

另用獨立HTML可見文字解析器比對數字出現次數，沒有減少；這只能檢查遺失，不能保證欄位語意或Docling原有辨識正確。重新執行同批輸出已驗證會以FileExistsError阻擋。

第41–43頁應付公司債 `c00056`：原content含HTML為9881字元，prepared含標題為5821字元。這是前處理的字元比較，不宣稱為相同比例的token差；本輪BGE token計數另見上方，完整原HTML仍保留。

可唯讀重驗既有樣本，不重跑前處理、不覆寫：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/tests/validate_prepared_sample.py "Output/markdown_chunk/Financial_20261022_01-23-16/2025_2330_chunk.json" "Output/embedding_prepared/Financial_20261022_01-23-16/2025_2330_prepared.json"
```

前處理歷史驗證不等於建庫驗證。仍待人工核對合併格展開與原錯欄、Voyage真實服務與品質、超長表格搜尋片段、檢索評估及100–200份的總時間／資源評估；建庫目前狀態見本文件前段與後續本次實測紀錄。


### 首次權重下載遇到停滯

本機首下載曾在Hugging Face的Xet及整檔HTTP通道停滯，改採公開HTTP Range下載同一鎖定權重。一般建庫缺少權重時會自動使用functions/embedding/model_download.py；它每次16 MiB、最多4個公開下載請求，按順序寫連續前綴，與財報批次並行無關。失敗保留本次連續暫存，可繼續；正式權重只有在官方SHA256核對通過後才建立，不使用舊下載器留下的未知片段。

也可只補齊快取：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/maintenance/download_bge.py
```

下載只讀公開模型，不用金鑰、不傳財報、不刪原有快取。超時與分段參數集中config/embedding.py；已有權重SHA不符時回報，不覆寫。之後使用本機快取不再下載權重。若模型下載或本機記憶體不足，仍需依真實錯誤回報，不能把token預檢通過當成推論成功。


### 長表格token比較（同一BGE tokenizer）

c00056在相同標題脈絡下，原HTML及原有跨頁控制語法為6522 tokens，prepared pipe文字為3987 tokens。此比較僅針對該份表格與鎖定BGE tokenizer；不是Voyage計費用量，亦不代表所有表格具有相同比例。原HTML在payload完整保留，沒有因這項節省而截斷。

## 財報問答（US-16，2026-10-22）

啟動方式不變，執行`Code_2/main.py`後選4。選一個已建好的BGE或Voyage collection，再選股票代號／報告年度（Enter不限），最後輸入問題。原始問題原樣使用，不呼叫參考專案的重寫、分流或agent系統；本輪為單題，不把前次對話當成隱含條件。未輸入篩選時搜尋所選collection全部文件，年度篩選是報告年度，不保證內文只含該年度數值。

### 金鑰放哪裡

專案根目錄`.env`：填入`VOYAGE_API_KEY=`及`GEMINI_API_KEY=`等號後。已有Gemini金鑰可沿用，勿覆寫或重複新增同名欄位。`.env.example`提供空白範本。金鑰只讀指定欄位，非空環境變數優先，不搜尋其他目錄、不展開變數、不載入其他欄位、不印出或寫入資料庫。程式不要求將金鑰貼到聊天。

Voyage金鑰取得入口：https://dash.voyageai.com/；Gemini：https://aistudio.google.com/api-keys 。最新模式：只排序不傳片段給重排／回答服務；到重排序將原題與最多50個可讀候選傳Voyage、取最多10個；完整回答再將這最多10個完整證據傳Gemini。選Voyage索引時，所有模式均需以voyage-finance-2的input_type=query產生問題向量；BGE索引則在CPU算問題向量，與原索引profile核對，不混用模型。

**免費層不是程式參數。** 使用Gemini免費方案專案的金鑰，並在AI Studio核對用量及方案；若金鑰所屬專案已啟用付費，這支程式的同一API請求仍可能計費，程式不能強制免費或驗證帳務。免費方案內容可能用於改善Google產品，付費方案依官方條款。429／503／逾時等皆停止本題，零自動重試、不切模型、不重建索引；服務失敗不代表未處理或零費用。免費／付費及額度規則見[官方價格](https://ai.google.dev/gemini-api/docs/pricing)、[用量限制](https://ai.google.dev/gemini-api/docs/rate-limits)。

選單4或`--ask`是明確開始API問答的操作，無須建庫用的`--allow-voyage-api`；該旗標繼續僅控制建庫。只列索引用以下命令，不讀金鑰、不呼叫模型API、不建立新庫：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --list-indexes

# 此命令會發送問題／片段至API，請先設定金鑰與確認所屬方案：
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --ask "2025年公司沿革記載的成立時間？" --backend bge --stock-code 2330 --report-year 2025
```

有多個相同backend的collection時，命令列須以`--collection`指定列出的名稱，不自動挑新舊版本。選單可直接選。索引不存在、沒有已提交文件或簽章不符時明確阻擋，不建立空庫。問答直接從Chroma payload取完整original_chunk，不讀Output；嵌入時即使忽略正文欄位，回答階段仍從完整原文轉出標題及pipe表格，維持原HTML在資料庫內不變。

### 檢索、回答與計算邊界

`config/qa.py`集中問答設定：最新先召回50塊、重排序取最多10塊、模型名稱、每次120秒socket timeout、輸出上限4096 tokens、輸入預算32000 tokens及問題長度防護。原20→5已由最新決定取代。32000是本輪單題成本控制預算，不是Gemini模型原生上限；10個證據若超預算仍停止，不減塊、切表或放寬預算。數量未宣稱已找到最佳參數。

- Voyage重排序使用`truncation=False`，送完整標題與正文／表格，由服務端檢查實際模型上限；超限失敗不默默截斷或跳過長表格。SDK本機rerank tokenizer未載入，不以BGE token數代替Voyage token數。實際重排序token用量採回傳欄位，缺值未知。
- Gemini先以官方countTokens計算包含提示詞、schema與完整證據的請求。超出設定預算停止，不裁切證據；這一步本身也會將該題與片段送Google。其後generateContent只呼叫一次；MAX_TOKENS、拒答、錯誤JSON、非STOP都不交付部分答案。
- 回答以claims列事實、推論或程式計算；每項必須引用實際召回的S編號及連續原文摘錄。未知來源、假摘錄及引文不存在的數字會被拒絕；程式引用表補上doc_id、chunk_id、實體頁序。cosine距離及rerank分數分開記錄，不當成答案正確率，也不使用未校準門檻保證有答案。
- 計算由受限AST及Decimal執行，模型只提出x0等來源變數算式，不使用eval。來源輸入須有完整數字、期間與單位的引文；不接受未知單位、除零、單位不相容或任意程式。支援加減、同單位比值及純數乘除；結果為純數的比率不自動轉百分比。完整輸入、公式、期間、結果及28位有效數字限制保存在回傳結果，畫面顯示公式。不能可靠取值、單位換算、多步複雜財務公式尚無通用支援，會停止或說明證據不足，不猜算。
- 最新確認：每題預設保存原題、召回片段、重排序、答案、引用與可取得用量，依所選模式記錄實際完成的階段，位置為下述Output/Response。核心`ask`仍只回傳記憶體；寫檔由`qa/run.py`呼叫EXPERIMENT_ONLY集中輸出，支援停用。最新回傳`financial-qa/1.1`包含mode、completed_stages、不同尺度排名／分數及錯誤階段，不把整份JSON當成embedding輸入；舊1.0紀錄不改寫。

模組責任：`qa/catalog.py`列已提交索引；`qa/pipeline.py`串接與來源驗證；`qa/services.py`兩項服務；`qa/answers.py`引用、計算及畫面；`config/qa.py`參數／提示詞／回覆schema。`embedding/keys.py`共用兩種指定金鑰讀取；`VoyageProvider.embed_query`與建庫document模式分開。未修改Code的PDF至chunk流程。

參考閱讀：本機`Reference Sources/EMBEDDING/evaluate_retrieval.py`的BGE／Voyage查詢職責；未複製原碼、不沿用其1024截斷、pickle或CSV自動寫檔。該副本commit／授權未知，不宣稱重現。服務介面已核對安裝的voyageai 0.5.0方法及[官方reranker](https://docs.voyageai.com/docs/reranker)、[Gemini generateContent](https://ai.google.dev/api/generate-content)、[countTokens](https://ai.google.dev/api/tokens)。本次無新增依賴，沿用原鎖定環境。

### 本次實際驗證及限制

新增30項問答測試通過，Code_2全套82項通過。測試使用假API／假向量及真實Chroma暫存庫，包含原題保留、股票代號前導0／年度型別、索引選擇、孤立未提交點不可召回、模型錯配、來源錯配、無答案、重排序失敗、完整長表格不截斷、429／MAX_TOKENS、引用／數字驗證、跨期差額、單位不符／除零及安全金鑰讀取。完整來源引用通過只代表ID及摘錄存在，不保證模型理解、數字欄位選擇或論述支持完全正確，仍須人工評估。

首次全套在系統sandbox暫存區有1項既有下載更名測試WinError 5；單獨重跑同樣失敗。改將暫存區指定到專案`Code_2/.cache/qa_test_temp`後82項全通過，未修改下載程式。重現本次全套方式（不需要真實金鑰）：

```powershell
@'
import tempfile, unittest
from pathlib import Path
p = Path('Code_2/.cache/qa_test_temp').resolve()
p.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(p)
r = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('Code_2/tests'))
raise SystemExit(not r.wasSuccessful())
'@ | & .\Code\.venv\Scripts\python.exe -X utf8 -
```

本次以`--list-indexes`核對既有BGE collection `financial_5f2112aa5e20f022407f470b`，1份／176塊。未重建索引、未重新跑完整BGE推論、PDF／OCR／Gemini目錄，亦未呼叫真實Voyage或Gemini問答。尚待真實API連線與單題品質驗收，以及跨文件、無答案、不同公司／年度、計算取值的實測評估；無準確率或延遲結論。100–200份財報的成本與時間需以實際問題數、候選長度、硬體及API限制評估，本次未整批處理。

### 問答保存與部分回答追加確認（2026-10-22）

使用者明確要求暫不測試真實API；本次僅做以下程式、本機及模擬測試，不讀取真實金鑰、不發送Voyage或Gemini請求。使用者另確認要保存問答，且需要可直接閱讀的Markdown。

每題預設另存到台北時間獨立目錄（秒後為微秒），不覆寫：

```text
Output/Response/qa_YYYYMMDD_HH-MM-SS_ffffff/
├─ answer.md       # 使用者主要閱讀這份：答案、缺少資料、來源與整個檢索過程
└─ result.json     # 程式核對用的完整結構化紀錄
```

`answer.md`包含原題、答案與來源、執行設定、股票代號／報告年度篩選、初排完整候選片段、重排排名與分數、模型版本及已取得用量。以中文說明流程；不要求使用者讀JSON，兩份內容來自同一問答結果。紀錄含財報片段，保留在本機供實驗核對，不自動清理或作為正式問答必要輸入；不保存金鑰、HTTP錯誤body或未驗證的原始模型回覆。

部分問題有證據時，`claims`保留支持部分，status維持`insufficient_evidence`，reason列出缺少資料。畫面與Markdown先顯示「有證據支持的部分」，再顯示「缺少的資料／尚無法確認的部分」及引用；完全無資料時明說證據不足。提示詞版本更新為`evidence-answer/1.1`，回覆JSON schema不變。範圍不符、無效引文或錯誤計算仍阻擋，不能用部分回答掩蓋驗證錯誤。

寫檔模組與移除清單：

| 模組／位置 | 責任與移除影響 |
| --- | --- |
| config/embedding.py：Settings.response_dir、export_enabled | 路徑及集中開關；移除實驗輸出時一起調整，不影響向量庫 |
| functions/experiments/export_output.py：reserve_qa_run／export_qa_run | EXPERIMENT_ONLY：保留唯一時間目錄、UTF-8 Markdown／JSON集中寫入；不混入核心 |
| functions/qa/run.py：run_question | EXPERIMENT_ONLY呼叫位置；先保留目錄防碰撞，再呼叫ask並保存；移除時直接回傳ask即可 |
| functions/qa/answers.py：render_qa_report | 純記憶體的人可讀報告，不寫檔 |
| main.py：選單4／--ask | 呼叫run_question、回報實際保存位置及保存失敗 |

`Settings.export_enabled=False`或`--no-export`可停用實驗寫檔，核心照常回傳及顯示。**問答搭配--no-export仍會呼叫API，不是離線測試模式。** 此旗標對建庫的限制不變，建庫只檢查仍用--check-only。

API前先建立本題新目錄，已知的目錄碰撞／權限錯誤不啟動問答。缺金鑰、索引錯誤、重排或生成失敗／中止，都保存已完成的資料與失敗階段；生成失敗前已取得的token預檢與服務用量也保留，未知不當0。Markdown與JSON成對寫入失敗時只移除本次新建的半份檔案，畫面明確回報保存失敗，已得答案仍在記憶體／畫面，不宣稱已保存；磁碟無法寫入、強制終止或斷電無法保證保存。未成功寫入的本題時間目錄可能保持空白，不刪既有紀錄。

本次追加13項測試（部分回答、候選及生成預檢保留3項，輸出與入口10項），問答相關共43項、Code_2全套95項通過；沿用上方專案內暫存區的全套指令。涵蓋人可讀Markdown與完整JSON一致、部分回答、失敗階段／已完成資料、台北時間、碰撞、停用後核心仍執行、半份輸出清理及不覆寫。全部API回覆與向量均為合成／模擬，Chroma測試使用暫存庫，未建立看似真實的問答成果、未改既有Output或索引；真實問答品質仍待後續明確授權。

### 三種執行模式（最新確認：50 → 10 → Gemini）

後續追加：50／10保留為已確認的預設值；互動選單現在可對每題手動設定數量，詳細隔離及移除方式見本文件末段。

選單4現在先選以下模式，再選索引及輸入問題。命令列用`--qa-mode`，未指定時維持原有完整回答行為，不讓舊命令默默改成只檢索。

| 選項 | --qa-mode | 完成內容 | 需要金鑰 |
| --- | --- | --- | --- |
| 1 只排序 | retrieve | 同模型問題向量、Chroma排序前50塊 | BGE不需API金鑰；Voyage索引仍需Voyage查詢向量金鑰 |
| 2 到重排序 | rerank | 先取50塊，再以Voyage取前10塊 | 只需Voyage，不讀Gemini金鑰或建立Gemini服務 |
| 3 完整回答 | answer | 50→10後交Gemini，驗證引用並呈現答案 | Voyage與Gemini |

實際候選不足50或10時只回傳實際筆數，不補造資料。索引範圍與模型簽章保護沿用；主動停在前兩種模式是正常完成，不是失敗，也不假造Gemini答案或用量。空候選以no_results記錄（完整回答沿用insufficient_evidence），不把未進行的重排標為成功。

```powershell
# BGE只排序：在本機計算問題向量，且預設保存Response；不呼叫Voyage或Gemini。
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --ask "公司成立時間？" --backend bge --qa-mode retrieve

# 以下兩種會使用API，不是離線測試；本次未實際執行：
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --ask "公司成立時間？" --qa-mode rerank
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/main.py --ask "公司成立時間？" --qa-mode answer
```

Response位置及檔名不變，仍是每題`answer.md`與`result.json`。Markdown增加中文模式、執行摘要與階段狀態表，列出「已完成」「所選模式不執行」「無候選不執行」或失敗狀態；只排序列完整前50候選，到重排列前10重排結果及原召回排名，完整模式另有Gemini答案、部分回答與缺少資料。模型設定與實際完成的階段分開標示；未執行服務用量標示不適用，不偽裝成API失敗或0用量。

問答JSON更新`financial-qa/1.1`：mode為retrieve／rerank／answer，completed_stages依序記錄query_embedding、retrieval、rerank、answer中實際完成的項目；新狀態retrieved／reranked代表所選停止點已完成，no_results代表完成檢索但沒有候選。只有完整回答具有answer物件；失敗保留實際已完成階段、候選、模型及可取得用量。舊1.0檔案不覆寫，Markdown渲染仍可讀舊格式。

實驗保存、--no-export、停用寫檔不影響核心、錯誤不重試及不截斷完整表格的規則不變；只排序若選Voyage仍會對問題呼叫query embedding，不能統稱離線模式。先前20→5及95項測試屬前輪；本輪新增10項三模式測試，全套105項通過，驗證50→10→回答、服務與金鑰隔離、模式選單／命令列、無候選及各模式MD／JSON。全部為本機、模擬服務及暫存Chroma測試，未讀實際金鑰、呼叫真實Voyage／Gemini、重建索引或覆寫Output；100–200份的真實成本／延遲與答案品質仍待授權實測。

### 暫時手動選單與未來正式呼叫（2026-10-22追加）

使用者確認實驗時可自行設定所有選單條件：執行模式、索引、公司（股票代號）、報告年度、向量檢索數量、Voyage重排序保留數量。選單4依此逐項詢問；公司／年度Enter不限，檢索數量Enter明確沿用50，重排Enter沿用10。只排序不詢問不會執行的重排數量。原題中的公司／年度仍不自動提取，不新增公司名稱對照或猜測股票代號。

參數只保留於本次記憶體，不回寫config、改索引或改下題預設；Response MD／JSON記錄當次真正使用的數量、股票代號、年度及模式。檢索數量沿用既有1–1000保護上限，設定集中QASettings.max_retrieve_k；重排數量須在1至當次檢索數量間。若檢索設5而預設重排10，選單要求明確輸入1–5，不自動改為5；輸入0可取消且不啟動API，無效數量重新詢問，不用預設掩蓋錯誤。只排序時不因未使用的重排設定10大於檢索數量而阻擋。

互動操作集中`functions/experiments/qa_menu.py`，模組與呼叫均有EXPERIMENT_ONLY。它只整理輸入，透過當次`QASettings`與股票代號／年度呼叫既有`run_question`，不實作檢索或模型。`main.interactive_qa`只是延後載入的薄入口；核心`qa.pipeline.ask`不匯入選單、不呼叫input。

日後依使用者指示移除這個暫時選單時，只調整`main.interactive_qa`及選單4分支，再移除`experiments/qa_menu.py`與對應選單測試；保留核心ask、參數設定、引用驗證、模型、索引及命令列一次呼叫能力。不要刪除整個experiments目錄，其他集中寫檔功能仍有既有職責。選單與Output寫檔是兩項獨立實驗功能，移除其中一項不代表刪除另一項或資料。

已確認的正式環境方向：由外部一次傳入原題及必要參數，直接執行完整回答，不逐項顯示實驗選單。既有核心已支援一次傳入`stock_code`、`report_year`、`qa=QASettings(...)`並以`mode='answer'`執行；命令列`--ask`預設也是完整回答。正式前端參數來源、公司／年度缺漏策略及是否移除實驗寫檔仍須依後續需求確認；本次沒有切換正式階段、部署服務、刪除選單／Output或實作自動條件提取。

本次新增10項驗證：手動條件及前導0、Enter明示預設、無效數量／重排大於檢索的重新詢問、取消不執行、只排序省略無用參數、當次QASettings不回寫、7→3傳至搜尋／重排序／回答與報告，以及移除選單模組仍可走無input的一次呼叫。問答相關63項、Code_2全套115項通過（使用前述專案內暫存區）；105項是前輪紀錄。本次均本機／模擬，未讀實際金鑰、呼叫真實API、重建向量或改寫既有Output，無新增依賴。

## Code_2 本機圖形介面

在檔案總管雙擊 `Code_2/start_gui.cmd`，會沿用 `Code/.venv` 並開啟瀏覽器。或從專案根目錄執行：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 Code_2/gui.py --open-browser
# 連接埠被使用時可加 --port 8766
```

預設網址 `http://127.0.0.1:8765`。服務設定集中 `config/web.py`，僅綁定本機，不是公開網站；不新增套件。保持啟動視窗開啟，按 Ctrl+C 關閉；若有工作，會等待工作安全結束，不強制中止。關閉瀏覽器分頁不會取消工作。

四個頁籤：

| 頁籤 | 操作及資料來源 |
| --- | --- |
| 查詢與問答 | 已提交索引、三模式、股票代號／報告年度、數量及保存開關；預設50→10→Gemini。來源可展開閱讀，結果有摘要、召回、重排、用量頁籤。 |
| 資料前處理 | 選 `Output/markdown_chunk` 有效批次及保存開關，呼叫原 `prepare_batch`；不改原始 chunk。停用保存僅在記憶體完成，不會產生可供下一次建庫選用的 prepared 批次。 |
| 向量建庫 | 選 prepared 批次、模型、config內有效欄位txt、只檢查及Voyage啟用。預設只檢查；取消後才建庫。右方展示預設 embedding_fields.txt，其他欄位檔請直接開檔核對。 |
| 執行紀錄 | 最近100份既有問答 Markdown，可閱讀並下載MD／JSON；最近建庫清冊依模型顯示，詳細token等可展開。沒有保存就不會出現在歷史列表。 |

進階模型、逾時、批次及路徑沿用 `config/embedding.py`、`config/qa.py`；不在網頁另外持久保存條件。欄位檔不接受任意系統路徑；CLI `--fields` 保留原有能力。API金鑰仍放根目錄 `.env` 的 `VOYAGE_API_KEY`、`GEMINI_API_KEY`，網頁不顯示或提供金鑰編輯。

同時只允許一項工作，包括跨分頁送出；忙碌回報409，不排隊、不自動重試。獨立worker使用共享Python環境，避免UI與模型stdout混用；UI顯示實際階段或逐批向量化筆數，不估計百分比。每次工作在新程序載入模型，BGE查詢可能較CLI連續操作慢；目前沒有模型常駐服務。只記憶最近工作，重整網頁可取回，重啟服務後不恢復；歷史仍來自原有問答輸出與建庫清冊。`--check-only` 沿用原程式不保存持久建庫紀錄。

啟動及瀏覽頁籤不啟動模型、不讀金鑰、不呼叫外部API；送出查詢才依模式執行。Voyage只排序仍有query embedding，完整回答會傳問題／證據至Voyage及Google。Voyage建庫／token檢查須另勾啟用；BGE首次操作可能下載公開模型。既有不截斷、超限停止、引用驗證、失敗回報與不自動重試規則均沿用。

介面拆分：`gui.py` 為入口；`functions/web/server.py` 固定HTTP路由；`service.py` 驗證參數與呼叫既有核心；`jobs.py` 管理單一工作；`worker.py` 處理獨立程序與安全進度；`static/` 為無建置步驟前端。JSON只作本機介面傳輸，不是另一份財報schema。資料庫和模型核心未搬入網頁程式。Host／Origin與每次啟動隨機token限制同來源操作；固定靜態檔及紀錄檔白名單，禁止任意檔案讀取、路徑穿越及symlink跳脫。Markdown只用文字節點呈現，不執行原文HTML／腳本。

實驗保存清單追加：網頁query／prepare的 `export_enabled` 參數只傳給既有 `qa/run.py`／`embedding/batch.py`，實際輸出仍集中 `experiments/export_output.py`（EXPERIMENT_ONLY）；沒有增加第二套寫檔器或job日誌。日後移除手動UI可停用 `gui.py`／`start_gui.cmd` 入口並移除 `functions/web`，不影響CLI、核心或既有資料；移除Output保存仍須處理先前列出的核心呼叫，不可只刪GUI開關。

本次驗證（2026-10-22）：新增12項網頁測試，Code_2全套127項通過；最後追加無效JSON型別與錯誤設定檔防護後，12項網頁測試再跑通過。涵蓋單一工作互斥、獨立worker實際程序協定（無效請求在模型前停止）、模擬query參數傳遞、失敗不洩漏原始例外內容、進度日誌白名單、紀錄路徑穿越防護、實際loopback HTTP靜態路由／token／Origin及模擬送出。JavaScript以現有Node 24.16.0做語法檢查，不新增Node依賴。

瀏覽器核對四個頁籤、現有BGE索引1份176塊、50／10預設、只排序停用重排數量、Voyage明確啟用欄位、設定檔選單及歷史清冊。沒有真實已保存問答可供此次瀏覽器閱讀驗證；報告路徑及讀取採暫存模擬資料測試。瀏覽器按下送出查詢的測試被自動安全審核拒絕，原因是驗證失效時可能觸發真實API，故未執行，不能視為已完成真實問答端到端驗收。本次未讀實際金鑰、呼叫Voyage／Gemini、執行真實前處理／建庫或修改既有Output；未評估100–200份的實際耗時／費用／答案品質。前述115項為前輪紀錄。


## 2026-10-29：連續階段與 Colab GPU 補充

- 前處理可選起始／結束階段，例如2→5，依序銜接本次產物；失敗即停止。
- 連續流程可勾「只保留最終階段產物」：全部成功後才清理本次中間檔，保留 Record；失敗／取消不清理。只檢查 token 時不可啟用此選項。
- `FINANCIAL_RAG_DEVICE=auto|cpu|cuda` 控制 Docling、BGE-M3 與 BGE 重排序。
- Colab 設定 `FINANCIAL_RAG_RUNTIME_PYTHON=current`；Windows 未設定時仍使用既有雙環境。
- Notebook 與操作細節見 [colab/README.md](../colab/README.md)，目前設定摘要見 [AGENTS.md](../AGENTS.md)。
- 本次沒有在真實 Colab GPU 上執行模型；安裝相容性與 GPU 效能仍待實測。
