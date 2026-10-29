# Code 程式解析與新對話交接

## 目前第四階段的閱讀入口

操作與完整規則請先讀[README的「第四階段：兩種切法與父子關係」](README.md#第四階段兩種切法與父子關係目前規則)，不要僅依下方日期紀錄推定目前行為。

- 共用解析及HD分界，原本模式一般文字不建Parent；父子模式一般附註文字也建Parent。一般HD遞迴門檻700、Parent分組上限1500、Child累積門檻300；畫面順序是Parent→一般門檻→Child，不是早期紀錄的順序。
- Parent按完整段落分組，Child累積達門檻才在段落結束切，末尾短段保留。完整表格及不可拆綁定可以超限，不硬截；一般長單段也可能超門檻，不能將1500／300當成硬截斷字數或token上限。
- content_direction延續到新HD／新說明；###以最近HD分組，包含中間表格；附表保持完整。這些共同語意範圍不因Child切分解除。
- 查核報告兩模式都維持一##一chunk，不建立一般文字父子關係。下游命中Child只讀直接Parent且同父去重，不往更上層擴展。
- JSON的chunks與parents分開，Markdown只渲染chunks；查完整父項應讀JSON。schema4.0及來源／年度／章節欄位依現有契約，不自行改名或把結構標籤塞回content。

維護順序：semantic_structure.py（共同結構）→strategies.py（策略）→hierarchical.py（契約組裝）→chunks.py／batch.py（驗證與輸出）。本次只是文件更新與程式核對，未改程式、Output或索引，也沒有重新執行下方歷史測試。

## 2026-10-25：介面顯示規則與滑桿

index.html已將進階參數／選取工具／已選路徑收合；補[hidden]{display:none!important}，消除toolbar覆蓋隱藏的問題。OCR網頁預設由config/web.py的DEFAULT_OCR_ENABLED=True經server模板注入，未改Settings.ocr_enabled（CLI預設）。第四階段順序Parent→一般門檻→Child，預設1500／700／300，滑桿上限3000／1500／1000由CHUNK_SLIDER_MAXIMA注入；數字輸入無此上限，超限值僅讓滑桿停在端點並提示，請求使用原輸入，不裁切。

statusPanel／cancel／openOutput依工作狀態顯示；初始無工作時隱藏空狀態，關閉服務會揭示訊息。Node前端契約測試及10項相關Python測試通過，已以暫存資料在實際瀏覽器核對，預覽已關閉；不代表執行了真實PDF或embedding。沒有改核心內容規則及Code_2。

## 2026-10-25：raw命名同步

BATCH_NAME_FORMAT已改Financial_raw_日期_時間；Code及Code_2的批次regex接受raw前綴並保留舊名相容。來源PDF／轉換規則／Record／檔名不變。3項局部測試及暫存raw→processed與取消白名單驗證通過，未執行Docling／OCR或真實財報轉換。

## 2026-10-25最新：後三階段新建時間批次

第二至第四階段每次執行建立Financial_processed／tagged／chunk_YYYYMMDD_HH-MM-SS，檔名維持年度_代號_階段。worker同次工作只建一次，將output_batch傳入各批次入口；CLI不指定output_batch時自行建立一次。多來源批次的文件可匯入同一新輸出，但同年度＋代號重複會在網頁開始前拒絕。同秒碰撞等下一秒重試一次，不覆寫或增加流水號。

export_output.stage_output_batch集中實驗批次建立；process_batch_local／tag_batch／chunking.batch只改輸出路徑與Record來源欄位，不改財報內容規則。Record.batch是新輸出批次、source_batch是原批次。OutputSession.set_output_batch接受各階段worker回報，取消白名單不再從來源名稱猜測。新舊名稱讀取規則在Code/config/output_layout.py；Code_2僅同步config/embedding.py名稱regex，未改embedding／檢索。第四階段模式子目錄仍保留，既有Output未移動。

本次輸出管理相關182項測試通過（175核心／取消／前處理＋7本機HTTP），另JS語法通過。僅使用暫存資料，未跑真實PDF／OCR／embedding／API或改既有Output。額外遇到舊第一階段2個mock不接受page_range的案例，未納入通過數，未更動第一階段；詳見README最新驗證紀錄。

## 2026-10-25最新交接：雙模式階層切塊4.0

已依使用者確認實作兩個互斥模式original／parent_child，及1500／300／700參數。請先讀README最新節；下方「模式未實作」「1000字延遲切分現行」等屬歷史，不能據此回退新版。

共用`semantic_structure.py`建立Atom／Node／Unit與說明、###、附表綁定；`strategies.py`只決定HD遞迴及兩模式的分組；`hierarchical.py`組裝4.0與來源／完整性診斷；公開`chunks.chunk_tagged`已接新版，顯式legacy函式只用歷史回歸。batch／集中實驗export及web UI已接mode。Code_2的prepare、metadata、load_prepared、paths、indexing及qa.pipeline相容，沒有從Code跨匯入同名functions。

使用者確認輸出同批下original／parent_child，前處理亦沿用，Record在各模式內。既有檔不覆寫或移動；新索引簽章隔離模式／參數／來源規則，不刪重建舊庫。content_direction採B綁所有後續段落至新HD／說明，Child300後遇段落結束切不解除Parent範圍。table_direction共用後遇新說明更新；年度、table_context取法沿用既有規則。整表及無安全切點語意可超Parent1500，明列診斷。

本次235項局部回歸通過；真實2024_2330記憶體兩模式202／224塊、20／173父項，126HTML表格逐字保留及source_spans重建通過，各有9超限父項／6未綁定結構標記。未跑新OCR、真實embedding／API、寫既有Output或重建索引。待後續人工核對年度與說明歸屬、真實token／檢索品質；不能把暫存假向量Chroma通過當成問答品質驗收。

2026-10-25最新tagged3.2：使用者要求content遇空行也結束。block_boundaries在一般空白行輸出既有CONTENT_END，保留原空行，下一非空正文重新開content；連續空白不造空區塊，表格／接續群／cannotfindtable／程式碼／註解內空白不改，Page本身不截斷。92項局部測試通過，第四階段參數／切法未改，新content_end可影響其原有切點。既有Output不自動更新。兩種切法按鈕及父子標題新方法仍未實作。

2026-10-25最新規則3.3：table_metadata.table_completeness以content含`<cannotfindtable>`回傳整數0，否則1；enrich_tables在完整父項及頁面子塊各自計算，文字不帶此欄，Markdown表格註解同步輸出。schema仍3.1、欄位驗證對表格要求新欄且與內容相符；Code_2對舊資料缺欄相容，新欄驗證整數及內容一致並保留到metadata／original_chunk。未改embedding_fields或索引，不代表疑似表格embedding已銜接。81項局部測試通過，真實2024_2330記憶體核對，既有Output未改。年度規則沿用下方3.2。

2026-10-25最新：表格說明／年度回查已實作，rule_version=heading-content-chunks/3.2，schema仍3.1。table_parents.preceding_heading只取最近hd／table_direction／content_direction（文字及表格略過、區域不跨越）；preceding_periods則遇正文／表格／hd／區域立即停止，略過空白及頁面邊界。table_metadata.table_years先用表頭年，沒有才取最近有年之前置標籤，最後文件年，不再把說明年度與表頭年度聯集。整段說明內找明列年，中文民國數字亦轉西元，years維持整數清單；格式／範圍集中config/table_metadata.py，year_sources保留原文與來源。

85項局部測試通過；2024_2330記憶體二→三→四223塊／90父項，西元年與Code_2 schema核對通過，有前置table_year／table_direction備援命中。未改既有Output、模型／API／索引，未作逐表人工年度驗收。Code_2無程式變更，輸入欄位相同。Note_Title已確認僅列hd2以下的動態路徑，空值允許，不另加階層欄。第二文字切法與fulltablestart特殊切法未實作。詳細新規則見README最新節，下方待討論屬歷史。

2026-10-25chunk3.1已完成新欄位：chunks／parents加main_section、sub_section、note_title清單，sections.chunk_section_fields由實際title樹取各葉路徑，查核空清單。Markdown改Main_Section／Sub_Section及逐路徑Note_Title（literal >），不再重列hd2／MAIN_TITLE；父子空欄保留。附表真實章節用title_context_before取得，appendix_id不變。Code_2驗證3.1與metadata支援，未更改欄位設定或索引。166測試、2024_2330記憶體223塊及9查核核對通過，未寫Output／未建庫。額外階層標籤意思正待確認；table_context、年度回查、第二切法仍待議。新欄位不再屬未完成，見README最新節。

2026-10-25chunk3.0已移除公司沿革限制：sections接主流程，查核##一標題一chunk、跨頁及長文不拆，到下一標題或note才結束；附註原切法保留，heading可null，Code_2新增3.0／null相容。使用者已確認查核##作Sub_Section、Note_Title空，目前仍暫存舊title結構；新欄名／多路徑輸出正等待本回合格式提案答覆，尚未全部完成。161項局部測試、2024_2330記憶體9查核標題→9塊及全部223塊核對通過，未寫Output／未建庫。待續：新欄位輸出、table_context、年度回查；第二切法另議。

2026-10-25查核報告最新決策：依保留##一標題一chunk，不是完全無標題。sections.py可辨識來源section與audit_heading，排除假標記並保留來源位置，2測試通過；尚未接主chunk函式，公司沿革限制仍在。待使用者回覆「查核##是否填Sub_Section、Note_Title留空」，之後還需確認／落實新欄位與Code_2相容；不要將解析工具當作完整切分實作。Output未改。

2026-10-25第四階段新欄位進行中：先完成文字Markdown顯示parent_id／part_index空欄，JSON原有null不變，20項chunk測試通過；未寫Output。使用者已要求刪公司沿革起點、納入查核報告、依原區域標記產Main_Section，hd2產Sub_Section、動態路徑產Note_Title；上述主改動尚未實作，正待回覆「查核報告無hd2時兩標題欄是否留空」。Code_2要求非空hd2，需新契約確認後相容；表格年度回查及第二種文字父子標題切法仍待討論。不要把需求當作已完成。

2026-10-25tagged3.1：cannotfindtable原文外加fulltablestart／table_end，原內層成對標記保留。_protected_lines新增可選full_table_ranges，block_boundaries將其納入表格流程，候選內不插content；普通表格保持table_start，接續群含候選用特殊起點，沿用換頁／接表／附表邊界。chunk parser／父子／Markdown僅格式相容、保留候選，不新增特殊切法或表格重建。132項局部測試及新增CRLF後9項專項通過；2024_2330記憶體3候選完整保留，未寫Output。README最新節詳列範圍與限制。

2026-10-25最新tagged3.0／heading1.15：第三階段不讀目錄或公司沿革備援，不產MAIN_TITLE；##中文頓號→hd2，原動態類型擴充英文點號／括號英文，編號優先於冒號。純年／年月日→成對table_year，多年度說明→table_direction，無編號冒號說明→content_direction，取代原##。三類標籤作content邊界、不改hd路徑，第四階段保留原文且不計正文字數，未實作表格年度／脈絡綁定。chunk仍從公司沿革hd2起，main_title空字串。第二階段末段移除##數字標題的-前綴，###及保護區不改。Record狀態統一tagged_needs_review，toc參數只供舊介面相容、批次不讀JSON；舊歷史模組未刪。114項局部測試通過，2024_2330記憶體串接成功（4／5／42個新標籤、210chunks），未寫Output／執行OCR或API／建庫。README最新節含規則、操作與限制；下方目錄／MAIN_TITLE備援屬歷史。

2026-10-25標題1.14：條列分類後重查未帶井號的- 1.類行，符合既有補標題條件才加##，已有###／保護區保持。recheck_dash_number_headings共用原規則，note_processing記final_dash_number_recheck計數、原raw行號，最後仍清頁尾。72項局部測試與2024_2330記憶體保留核對通過，未寫Output。見README最新說明。

2026-10-25標題1.13：附表改####，新增註＋中文編號改###；忽略辨識空白、保留原文、不限20字，表格等保護與note範圍不變。共用APPENDIX_MARKDOWN_PATTERN讓接表邊界／附表父項相容新版####和舊#，附表ID去空白、title不改。第三階段保留特殊井號，不轉hd。94項局部測試及2024_2330 raw記憶體保留核對通過（附表11／註24），未寫Output。詳見README最新節，舊單一#規則屬歷史。

2026-10-25標題1.12／頁尾1.2：附表比對去空白；20字上限不計編號後空白；Markdown標題允許井號後無空格／全形空白；帶橫線及符合原條件的純數字頁尾接受數字間空白。只改辨識／計數，原文空白保留，Page／控制標記／行首縮排規則及note／表格保護不變。72項局部測試與2024_2330 raw記憶體保留核對通過，未寫Output。詳見README最新節；舊1.11含空白計長度等敘述屬歷史。

2026-10-25 body-lists/1.0已接入note_processing末段：原補標題→條列###分類→清頁碼；只從非##內文起點判斷相鄰或首項前##冒號。##只回查首項／中間漏項／接續末項，整組##不改，不跳表格。支援-前綴、空格及1. A.內層英文；跳號寫processing_scope.body_list_classification.gaps，不補造。heading_line_origins將後段行號映回raw，變更可有同源行多次操作。config/body_lists.py集中版本與編號。66項局部測試、2024_2330 raw記憶體試算通過（28行，note前／HTML／Page保留），未寫Output。未改tagged／chunk；###不是hd階層。詳見README最新節。

2026-10-25疑似表格1.1：20個中文字以下文字及金額碎片行亦納入5行候選計數，空白忽略；觸發前長正文重設，觸發後沿用3長行停止，note及保護邊界保持。設定／報告改用CANDIDATE_RUN_LENGTH／candidate_run_length，trigger為5_consecutive_candidate_lines；完整數值共用分類不變。57項局部測試及2024_2330 PDF頁58原raw稅額片段記憶體驗證通過，未重寫Output。連續短正文也可能被包入，未作準確率驗收。見README最新說明；下方1.0為歷史。

2026-10-25標題1.11：補標題分支改用去空白字串比對編號，再映回原文取得內容，修正二十 、及( 一 )等漏補。保留輸出、20字計算、標點、note與表格保護。47項局部測試及2023_2330 raw記憶體核對通過，未重寫Output；###條列仍未實作。見README。

2026-10-25標題1.10：行首多年度（至少2個、及相連）＋說明不限字數／冒號／句尾，統一##；新增numeric_lines共用分類，純數值／金額／百分比在編號識別前排除，既有##去井號留原文。suspected_tables仍於補標題前執行，不將raw的##數值追溯重算。note／保護區優先、年月日規則保留。55項局部測試通過，Output未重產生。見README。

2026-10-25標題1.9：整行年月日（112 年 12 月 31 日）亦走PURE_YEAR_PATTERN加##並作冒號邊界，年月日原文保留；含敘述與點分日期不升格，未驗證曆法／轉metadata。保護區與note範圍仍優先，舊Output未重產生。見README最新節。

2026-10-25疑似表格suspected-table/1.0：config/suspected_tables.py門檻5數值／3長行／20中文字；note_processing在補標題前呼叫偵測器，包cannotfindtable成對標記並保護原文。短文字重設數值計數，空行忽略，3長正文行在第1行前截斷，取消偵測的標點條件；##／表格／Page等保護邊界立即截斷。line_map維持HeadingChange原始行號；processing_scope.suspected_table_detection保存原raw範圍、頁序、停止原因及EOF補換行註記。已標記內容冪等，錯誤標記拒絕。63項局部測試及5份台積電raw記憶體試算通過（候選1/2/0/1/0），未寫Output。沒有回PDF／LLM或第三四階段特殊消費，沒有重複HTML去重，5行門檻會漏每2個金額即穿插項目的例子。全檔空白清理仍待確認表格範圍，未實作。

2026-10-24第一階段local-selection/1.1：NFKC僅套比對字串；main原公司沿革迴圈改共用find_notes_in_body，加獨立附註主標備援，已知查核頁及目錄／引用／保護區不採。config/page_selection.py集中規則；Record新增版本、正規化方式及notes_heading_fallback來源，失敗也保留selection。13項局部測試通過，2021聯電真實Docling P2、P14定位14及刪公司沿革行的模擬主標備援通過；整份未重跑、Output未改。詳見README最新節。

2026-10-24第二階段1.8：_colon_paragraphs在中文句號處重設收集起點，flush保留前句，只將最後句號後文字收為##；支援同行分割，ASCII點號不分割。42項局部測試通過；舊Output未重產生。全檔空白清理仍未實作，待確認表格範圍。

2026-10-24第二階段1.7：_colon_paragraphs在遇現有行首編號時flush上一段，重設本項起點；本項換行可合併至冒號，不跨上一項。38項局部測試通過，未重寫Output。使用者要求整份清中文空白、英文單字空白保留，表格範圍尚未確認，空白清理未實作；不要將此需求套為其他規則的全檔範圍。

2026-10-24最新：使用者指定第一階段表格回復HTML，settings.py預設html。2303 P4開OCR／P42真實頁段試轉成功，P42含1張HTML表；下方「OCR仍封鎖」為之前實測，不代表本輪再次封鎖。整份未重跑，安全設定未改，也不能將信任變化歸因HTML格式。見README最新補充。

2026-10-24第二階段note-only/1.0：note_processing共用模組統一分段與原始行號偏移，process_batch_local與main.run_mark_headings皆使用；note標記及前段全文不變，缺標記／多標記拒絕該份。Record新增processing_scope，低階mark_missing_headings不自行套用範圍。load_source容許第一階段已定義章節標籤前綴，仍核對首個Page。47項局部測試通過，2303記憶體驗證前綴／表格／頁序保留；未重寫Output。詳見README最新節。

2026-10-24最新第二階段1.6：使用者指定純年度亦改##，mark_headings記year:double_hash，原####年度重處理會正規化##；冒號合併及英文限制維持1.5。未擴充年度metadata／table_context，既有Output未重寫；下方純年度####說明屬歷史。

2026-10-24最新第二階段1.5：英文A.／a.／(A)／(a)與全形配對括號加入MARKER_PATTERNS，UNLIMITED_LENGTH_MARKERS集中列英文類型；取消英文長度限制，保留非空／EXCLUDED_ENDINGS，既有英文##亦排除空白或指定句尾。使用者接受數字維持原限制；下方1.4待確認事項已解決。冒號段落合併維持；36項局部測試通過，未重寫Output。

2026-10-24第二階段1.4：mark_headings._colon_paragraphs定位冒號結尾的同段文字，合併一行加##；blank／保護區／獨立控制標籤／頁碼／附表及純年度為邊界。HeadingChange.original可含段落換行，line_number維持原始起行。英文不限字數已確認，數字及句尾標點是否解除仍待答覆，編號設定尚未更動；不可宣稱英文支線完成。33項局部測試通過，未重寫2303產物，頁碼清理仍1.1。

本輪驗證限制：獨立PDF環境排除sklearn後，真實Docling初始化及2303 P42轉換成功；P4 OCR在必需Shapely載入時遭Windows原則封鎖，舊環境亦相同。尚未恢復OCR／整份財報處理，安全設定未改，下一步需使用者決定信任／原則處理；不要再把環境安裝成功當作OCR成功。12項CLI切換及非HTTP網頁局部測試通過；報告見maintenance/pdf_environment_validation.json。

2026-10-24環境修復：Code改用`.venv_pdf`，原`.venv`保留給Code_2。main.ensure_project_python（也支援web_main重新啟動）、start-web.cmd及server worker皆使用config/runtime.py的PDF環境名稱；啟動cmd同名入口不變。直接依賴補SciPy1.17.1，完整鎖檔requirements.pdf.lock，舊requirements.lock不覆寫。Windows安全設定及第三方套件程式碼未改。操作、封鎖根因與驗證見README最新節；下方共享環境說明屬歷史。

2026-10-24第一階段更新：預設markdown管線表格、不保留封面，探測2／3頁而非1至3頁；section_markers.py在查核首頁前加`<會計師查核報告>`，附註首頁前加`<note>`及`<合併財務報告附註>`，不重編Page。pipe_tables.py共用辨識，目錄／保護／區塊及chunk父子年度已接管線相容。合併格依官方Markdown序列化展平並warn，無法修復漏表。MAIN_TITLE／chunk公司沿革起點／Code_2未改，見README最新節；本輪未跑真實模型、舊Output未改。

2026-10-24頁碼追加：page_cleanup.py版本1.1保留原橫線頁碼清理，另刪除每頁最後非空白行且數值等於Page實體頁序的純數字頁尾；保護表格／程式碼／註解、保留頁序註解。舊Output未改寫，參見README最新節。

2026-10-24：processed標題規則1.3移除無既有編號的一般##（文字保留）、純年度整行標####、行首附表中文編號標單一#。tagged2.10不再補附表#，只保留第二階段結果。編號補##、英文編號、相鄰條列及table_context擴充未改；中文年度轉換／新年度綁定仍待後續確認。詳見README最新節；舊Output未改寫，舊processed需要由raw重產生才能取得新規則。

2026-10-23資料選取追加：Code四階段均改為資料夾樹，可展開逐檔勾選或全選整個子樹，並保留搜尋／已選篩選。網頁傳檔案id，後三階段透過source_files子集呼叫原核心；批次CLI預設不變。selection.js處理樹與選取，batch_selection.py管理批次內來源。操作、命名、防覆寫及本輪驗證限制見README「資料夾與個別檔案」。Code_2選取介面不在此次修改範圍。

2026-10-23最新追加：tagged 2.9標出#附表，chunk 2.0包含完整parents及按頁搜尋子塊、table_context檢索脈絡與唯一years內容年度；Code_2已接prepared／index 2.0、years包含篩選及資料庫完整父項召回／去重。純文字用文件年，表格無明列年也用文件年；已有索引未重建，下方舊進度須以Code/README.md與Code_2/README.md最新章節為準。兩份真實processed在記憶體串接通過、HTML逐字保留；本機暫存Chroma用假向量驗證資料流程，不代表真實召回或年度語意已驗收。原同名產物防覆寫仍生效。

最新介面追加：Code 現有四階段已有本機網頁入口 `start-web.cmd`／`web_main.py`，可搜尋與複選 PDF／批次。程式在 `functions/web_ui/`，說明與驗證見 `README.md` 的「本機網頁介面」。既有演算法及 CLI 保留；關閉分頁不停止工作，閒置時按關閉服務。此次沒有重跑真實財報／OCR 或呼叫 Gemini。

整理日期：2026-10-22（更新原2026-10-21交接）。專案：`D:\桌面\完整財報分析器`。

同日追加：使用者指定既有 `Code_2/` 獨立開發前處理與BGE／Voyage＋Chroma建庫；目前已接入選單與欄位設定，Voyage真實API預設關閉。詳見本文件第13、14節及 `Code_2/README.md` 的最新實測紀錄；第13節「尚未向量化」是前輪階段狀態。

本文件針對目前實際程式、已確認規則、現存產物與未完成銜接整理，供下一個對話接續。沿用原文件的責任分工、操作表格、歷史與本次驗證區分方式；不是新的需求批准，也不代表整份財報品質通過。需求以使用者最新明確指示及USER_STORIES為準，不能只讀舊交接就實作。

## 1. 新對話先讀這裡

1. 先讀根目錄`USER_STORIES.md`與`AGENTS.md`，再讀`FLOWCHART.md`、`Code/README.md`、本文件及將修改的程式。需求文件前段有歷史描述，最新標籤與chunk決策見US-10、US-12、US-13及後續追加。
2. 目前仍為實驗階段，最終預計約100–200份財報；沒有執行整批、建立付費索引、部署或自動轉正式階段的授權。
3. PDF至chunk程式碼在`Code/`，入口`main.py`，功能`functions/`，設定`config/`，共用格式`schemas.py`，測試`tests/`。chunk結果與驗證在`functions/chunking/`，不要把目錄JSON schema當成chunk schema。新embedding前處理已依使用者指示改在`Code_2/`，有獨立入口與模組，不混用同名匯入。
4. `.env`由使用者自行填金鑰；不要讀取、顯示、複製其內容到聊天或交接文件，不把金鑰放入日誌或程式。
5. 不修改原PDF、Reference Sources或獨立MinerU網頁工具，不刪既有Output、模型快取或虛擬環境。沒有必要不重跑OCR或呼叫Gemini。
6. 不確定的規則先問；已確認的沿用。使用者要求每次修改都提供摘要。備援起點「公司沿革」是已確認的暫時規則，不是通用財報結構保證。

### 最重要的現況

| 功能 | 實際狀態 | 還不能宣稱的事 |
| --- | --- | --- |
| Docling PDF → Markdown | 完整轉換入口、HTML表格、Page實體頁序及同批目錄PDF抽頁已接上 | 所有頁面、表格、數字均正確 |
| MinerU必要OCR元件 | 已取代EasyOCR接入，CPU ch_lite、預設關閉、按區域執行 | 整份財報或真實混合頁品質通過 |
| raw → processed | 補漏抓標題、移除獨立頁尾頁碼、讀既有兩頁PDF交Gemini | Gemini每次成功或目錄語意完整 |
| Gemini目錄與重試 | 只擷取MAIN_TITLE；HTTP 503最多重試3次，等待5／10／20秒 | 429等也會重試、重試可保證成功 |
| processed → tagged | 新核心markdown-comment-tagging/2.8；JSON正常分支、暫時大標備援、跨頁內容與接表規則已實作 | 磁碟上的舊tagged已自動變成2.8、接表語意已逐項驗收 |
| tagged → chunk | 已輸出Markdown、JSON與Record；現有樣本176塊，Markdown已補繼承小標 | 完成embedding、向量索引或端到端RAG |
| embedding／檢索／回答 | 尚未實作目前資料管線的後續銜接 | 可直接用現有程式做正式財報問答 |

**目前最容易誤解的版本差異：** 程式已取消頁首重列hd2、空hd及重複的原##，但指定樣本的tagged檔仍是2.4，沒有覆寫。重複hd2是舊產物的格式，不是最新程式仍重列。chunk依來源Record辨識舊快照／空hd，只在記憶體相容處理，不回寫tagged。

## 2. 實際程式結構與責任

以下省略虛擬環境、快取與vendor內部大量檔案；只列已存在的主要模組，不替未來embedding建立空架構。

```text
Code/
├─ main.py                         # 選單、命令列、階段串接與狀態
├─ schemas.py                      # 共用結果、目錄schema、標籤結果
├─ CODE_HANDOFF.md                  # 本交接文件
├─ README.md                       # 操作、環境、實驗輸出與驗證
├─ requirements.txt / requirements.lock
├─ config/
│  ├─ settings.py                  # 根路徑、OCR、chunk與實驗寫檔開關
│  ├─ ocr.py                       # CPU ch_lite模型與參數
│  ├─ toc.py                       # Gemini模型、提示詞、503重試
│  ├─ output_layout.py             # Financial_台灣日期_時-分-秒批次
│  ├─ markdown_headings.py         # 補標記規則1.1
│  ├─ markdown_blocks.py           # content/table/page標記及接續詞
│  ├─ markdown_tagging.py          # 舊階層設定與TEMPORARY_FALLBACK
│  ├─ chunking.py                  # 1000字、寬限頁、句號、版本
│  ├─ markdown_files.py            # 年份／股票代號及檔名後綴
│  └─ markdown_scopes.py           # 舊XML相容入口範圍設定，不是新批次入口
├─ functions/
│  ├─ ingestion/
│  │  ├─ pdf_to_markdown.py        # Docling、原生文字／OCR、頁序序列化
│  │  └─ toc_pdf.py                # 抽實體2、3頁／載入既有PDF／目錄驗證
│  ├─ integrations/
│  │  ├─ docling_mineru_ocr.py / mineru_paddle.py
│  │  ├─ mineru_ocr_vendor/        # 必要元件、LICENSE與NOTICE
│  │  └─ gemini_toc.py             # 金鑰、官方HTTP、有限重試與attempt紀錄
│  ├─ markdown_processing/
│  │  ├─ load_source.py / file_identity.py
│  │  ├─ mark_headings.py          # ##補標記／冒號候選#
│  │  ├─ page_markers.py           # Page及舊PDF_PAGE解析
│  │  ├─ page_cleanup.py           # processed移除表格／程式碼外獨立頁碼
│  │  ├─ process_batch.py          # 第二階段批次與來源驗證
│  │  ├─ comment_tagging.py        # 新hd替換、MAIN_TITLE與暫時備援
│  │  ├─ temporary_main_title.py   # TEMPORARY_FALLBACK公司沿革整頁至EOF
│  │  ├─ block_boundaries.py       # 頁面與content/table獨立狀態
│  │  ├─ table_continuation.py     # 相鄰表格中間接續詞分組
│  │  ├─ heading_hierarchy.py      # 動態編號類型→層級堆疊
│  │  └─ tag_batch.py              # 第三階段批次，不呼叫API
│  ├─ chunking/
│  │  ├─ parser.py                # tagged解析、舊快照辨識、接續表格
│  │  ├─ chunks.py                # 階層樹、延遲切分、schema與來源覆蓋
│  │  └─ batch.py                 # 第四階段來源驗證與輸出串接
│  └─ experiments/
│     └─ export_output.py          # EXPERIMENT_ONLY集中寫檔
├─ maintenance/                    # 已有更名／OCR來源準備及獨立mineru_web
└─ tests/                          # 單元、模擬及另外的真實OCR驗證入口
```

`notes_scope.py`、`tag_markdown.py`、`classify_tag_heading.py`及舊`markdown-tagging/2.0`仍保留相容用途；不是目前選單4的主要流程。不要因看到`content`／`tableblock`舊常數，就把現行區塊標記改回去。

## 3. 環境與操作入口

使用專案`Code/.venv`的Python3.11。本次交接執行`--version`重新核對為3.11.9；未重新安裝依賴。入口在第三方套件匯入前會嘗試轉入此環境，避免系統Python3.14環境混用。

```powershell
# 在專案根目錄執行
& .\Code\.venv\Scripts\python.exe Code/main.py
```

| 選單 | 目前功能 | 命令列替代 |
| --- | --- | --- |
| 1 | 一次選一／多份完整PDF，建立同一raw批次 | `--pdf 路徑` |
| 2 | 切換按需OCR，預設關閉 | `--ocr`／`--no-ocr` |
| 3 | raw批次補標題、清頁碼並用Gemini解析已抽目錄PDF | `--process-batch 批次路徑` |
| 4 | processed批次加hd／區塊標籤，必要時啟用暫時備援 | `--tag-batch 批次路徑` |
| 5 | 獨立讀取單份原PDF實體2、3頁目錄 | `--toc-pdf PDF路徑` |
| 6 | tagged批次切chunk，輸出Markdown＋JSON | `--chunk-batch 批次路徑` |
| 0 | 離開 | 無 |

- `--mark-headings`是保留的只補標題／清頁碼入口；`--tag-markdown`是舊XML相容入口，不等同目前選單3／4。
- 7個處理模式參數互斥；各階段分開執行，沒有自動串成整個RAG。`--check-env`只檢查環境，不載入辨識模型。
- `Settings.export_enabled=False`集中停用實驗寫檔；processed、tagged、chunk、獨立目錄等入口可用`--no-export`。**凡流程含Gemini，--no-export仍會傳送目錄PDF及產生請求，不是離線測試。** tagged與chunk本身不呼叫API。
- 所有批次輸出沿用來源批次名，不新增處理流水號。既有目標MD／JSON／Record存在就提前阻擋，不能把防覆寫當成解析錯誤，也不要為了重跑隨便刪Output。
- 本文件的現有樣本已經有chunk產物，再執行選單6會被防覆寫阻擋；不需要為交接重新切同一份資料。

## 4. Docling與本機OCR

### 4.1 主流程

`pdf_to_markdown.py`的`validate_source()`限制來源在`Financial Statements/`；`create_converter()`建立CPU Docling；`convert_pdf()`執行轉換；`serialize_document()`產生HTML表格Markdown及實體頁序版。核心回傳`MarkdownDocument`與`MarkdownPage`，寫Output由入口委派實驗模組處理。

- Docling負責版面、表格、閱讀順序及Markdown輸出。
- 原生文字優先；OCR預設關閉。開啟後依Docling提出的區域處理，不能只因頁面有少量文字就一律跳過OCR。
- 已使用MinerU來源的PyTorch PaddleOCR必要元件，不是完整MinerU pipeline，也不需要安裝完整Paddle框架流程。
- OCR關閉／沒有區域時延後或不載入OCR模型；不默默回退EasyOCR。
- `result_cells()`負責圖片座標還原、crop偏移及Docling TextCell；區域文字、分數、空結果、低分與錯誤有診斷。
- 表格維持HTML、保留rowspan／colspan；不能靠替換OCR就保證表格欄位或閱讀順序修正。

### 4.2 已確認OCR設定

以`config/ocr.py`為準：ch_lite、CPU，scale=3（216 DPI）、rec_batch_num=1、drop_score=0.5、偵測框不合併、det_db_thresh=0.3、det_db_box_thresh=0.3、unclip=1.8、use_dilation=True、det_limit_side_len=960。無方向分類或公式識別。

模型來源`opendatalab/PDF-Extract-Kit-1.0`，revision `ed6b654c018d742e65a17671e379c5e6ecc87ec9`；模型檔為`ch_PP-OCRv5_det_infer.pth`與`ch_PP-OCRv5_rec_infer.pth`，SHA集中設定。快取在`Code/.cache/mineru_ocr/`，Docling快取在`Code/.cache/docling/`。必要來源授權與歸屬保留在vendor的LICENSE／NOTICE，後續散布須繼續核對授權要求，不刪聲明。

### 4.3 已有實測與限制

依`ocr_validation_results.md`的歷史紀錄，2025樣本實體第2、3頁掃描內容有觸發OCR，第15、50頁原生內容未觸發；另有合成原生文字＋中文圖片混合頁完成工程驗證。存在掃描錯字、印章雜字、日期順序錯亂及表格錯欄。真實混合財報仍缺樣本，未以新OCR驗證整份85頁或全部財務數字。

## 5. 漏抓標題補標記：規則1.1

輸入既有Markdown，不重跑PDF／OCR。核心`mark_missing_headings()`回傳`HeadingMarkResult`，修改紀錄包含原行、新行、行號及原因。

1. HTML `<table>...</table>`完整保持原樣，含表格的整行不補標記；跨行、同行表格可處理。異常邊界整次失敗，不輸出部分成果。
2. 既有`#`標題、註解與程式碼區塊保護，不清除舊標題層級。
3. 僅四類行首編號：中文數字＋頓號、括號中文、1–2位半形數字＋點、括號半形數字。中文限定「一二三四五六七八九十百」組合，不驗證數值；括號成對接受`()／（）`，拒絕混搭。
4. 判斷時略過單一行首`- `，輸出仍保留它；`-15-`／`- 15 -`等頁碼明確保護。
5. 編號後直到行尾視為整個候選，不依空白拆正文、不跨行合併。去頭尾空白後須1–20個字元；內部空白保留計長。
6. 通過長度後，行尾`:／：`補`# `；否則排除標點結尾維持原樣；其餘補`## `。既有行文字不改。
7. 排除標點完整清單為`，。；！？,;!?」』"')）]`，不含半形句點`.`。重跑不疊加前綴。

以上是補標題核心規則；獨立頁碼在此步驟先受保護，再由processed流程的`page_cleanup.py`移除表格與程式碼以外的獨立頁碼行。Page來源註解保留，不以頁尾數字重新推算頁序。

已知限制：這是規則判定而非語意辨識，`2.087`可能被當作`2.`加短內容；目前未獲批准加入小數排除規則。指定raw樣本1.1結果有8行補標記，104個HTML表格保持不變；人工抽查只涵蓋目錄與附註以後。詳見`heading_mark_validation.md`。

## 6. Markdown階層與區塊標籤：現行2.8

### 6.1 processed → tagged

`tag_processed_batch()`讀同批processed、Record與可用的tablerefer JSON；正常大標依JSON頂層與頁碼，未知不猜。完整正文在tagged仍保留；公司沿革前內容是到chunk階段才排除。

- 小標取自正文恰好`##`的中文數字＋頓號，允許編號、頓號與文字間有空白，例如`## 一 、 公司沿革`。
- 直接以`<hd2>一 、 公司沿革</hd2>`替換原標題行，不再另留同一行`##`；未辨識標題、表格、程式碼與註解不擅自改寫。
- 下層括號中文、數字點、括號數字依首次類型順序分到hd3起；同類回到已分配層級並清除同層／下層路徑；新hd2重置類型對應。
- MAIN_TITLE維持`<!-- MAIN_TITLE: ... -->`，不占hd層級。年份／股票代號有來源才填，公司名稱未知留空。
- 不輸出空白hd2／hd3，階層重置由內部處理；頁首不重列hd2，同大標跨頁延續階層。
- 原始頁序使用`<!-- Page: 2330_2025_P25 -->`，股票代號／年份／實體頁序依此識別。標籤入口可相容讀舊PDF_PAGE；chunk要求帶識別的新Page，不能猜舊頁碼的年份。

### 6.2 Gemini不可用時的暫時備援

僅目錄JSON缺失、無效或processed記錄Gemini失敗時啟用：定位正文真正`##`的「公司沿革」，忽略編號與空白，從該整頁到EOF使用使用者指定的大標**「合併財務報表附錄」**。這個名稱是使用者指定，勿自行改成其他近似名稱。

大標只在起始頁Page之前列一次：

```html
<page_end>
<!-- MAIN_TITLE: 合併財務報表附錄 -->
<!-- Page: 2330_2025_P15 -->
<page_start>
```

後續頁面不重列，但大標脈絡延續；前面不產生空大標。有效JSON仍走正常分支。找不到可靠公司沿革起點、來源批次或雜湊不符時，停止該份，不以備援掩蓋錯配。

隔離檔案為`temporary_main_title.py`，設定在`config/markdown_tagging.py`，可搜尋`TEMPORARY_FALLBACK`，目前開啟；規則`company-history-page/1.0`。只在記憶體建立備援頁範圍，不假造Gemini目錄JSON。Record記錄原因、起訖頁、來源行及狀態`tagged_temporary_fallback_needs_review`；這是暫時方法，之後修改須依使用者決定。

### 6.3 content、table與page各自追蹤

標記拼法依使用者確認，保留非對稱寫法：

| 用途 | 開始 | 結束 |
| --- | --- | --- |
| 內文 | `<content_start>` | `</content_end>` |
| 表格 | `<table_start>` | `<table_end>` |
| 頁面 | `<page_start>` | `<page_end>` |

- Page先列，再列page_start；上一頁page_end在下一個Page之前輸出。
- content遇真正標題、大標變更、表格或EOF才結束；換頁、空行及相同大標不結束content。
- page與content／table為獨立狀態，可以交錯跨頁，不能以普通HTML嚴格巢狀解析。Page與page_end／page_start可能出現在仍開啟的content／table內。
- 相鄰兩個外層HTML表格之間，只要文字含「接次頁」或「承前頁」任一個，忽略空白後即共用一組table邊界，可接續多頁。沒有詞就不合併；表格內、註解與程式碼中的接續詞不作依據。
- 各段完整HTML、中間文字、頁序與重複表頭保留，不拼接欄列或刪除內容。這是使用者指定的文字規則，不代表已人工驗證所有合併語意。
- `block_counts.table`計接續後區塊數，不等於HTML片段數；`table_continuation_joins`記錄原片段序號、命中詞與策略；`boundary_added_newlines`記錄為標記獨立成行補上的換行。

## 7. Gemini目錄JSON與503重試

### 7.1 兩個入口及呼叫鏈

- 第一階段只用pypdfium2抽原PDF實體第2、3頁到同批`Financial_Table/`，不呼叫Gemini。
- 第二階段選單3核對原紀錄、路徑及PDF雜湊後，直接讀已抽兩頁PDF交`generate_toc()`；不重跑Docling／OCR、不傳正文。
- 獨立選單5／`--toc-pdf`仍可從單份原PDF抽2、3頁送Gemini，結果在`Output/json/`舊式獨立時間目錄。
- 目錄不在2、3頁、來源不足或無法辨識時，不自動掃其他頁或切換模型。

### 7.2 模型、金鑰與重試

| 設定 | 目前值 |
| --- | --- |
| 模型 | gemini-3.1-flash-lite |
| 請求 | 官方generateContent REST v1beta，Python urllib inlineData PDF |
| 輸出上限 | 8192 tokens |
| socket timeout | 每次120秒，非整體硬性總時限 |
| 503 | 首次失敗後最多再試3次，依序等待5、10、20秒；最多4次請求 |
| 其他錯誤 | 429、其他HTTP、逾時、連線失敗、空／錯誤／截斷回覆不自動重試 |

重試只重送同一兩頁PDF，不重做前階段；可以Ctrl+C中止。Record／獨立manifest的`gemini_attempts`保存各次狀態與等待結果；HTTP body不回顯。逾時可能服務端已處理，不自行重送；失敗用量未知不能當成0或宣稱免費。

金鑰優先取非空環境變數GEMINI_API_KEY，否則僅讀專案根目錄.env；不搜尋父目錄、不展開變數、不載入其他欄位。金鑰讀取使用python-dotenv==1.2.4；缺值回報，不顯示內容。拒絕HTTP重新導向，不改模型端點。

### 7.3 現行目錄schema及失敗處理

`financial-toc/2.0`、提示詞`toc-main-titles/2.0`，API schema為`TOC_MAIN_RESPONSE_SCHEMA`。只擷取MAIN_TITLE頂層大標與印刷頁碼，不再輸出公司沿革等子項目；`parent_id`與`note_numbers`必須空字串。大標缺頁碼時，可取其子項實際明列頁碼的聯集，不填補不連續區間空缺。`source_pdf_page`為目錄證據所在原PDF第2或3頁，不是正文頁碼。

舊`financial-toc/1.0`嵌套目錄仍可供標籤讀取頂層與後代明列頁碼聯集；不能把舊schema直接冒充新API輸出。使用者已確認目錄頁碼直接對應目前Page實體頁序；不另從頁尾推算。

完成原因非STOP、錯誤JSON、缺欄位、無目錄／無法辨識均有失敗或待確認狀態。Gemini失敗時第二階段仍保存補標題及清頁碼後的完整processed正文，不輸出有效tablerefer JSON；單份失敗繼續其他文件，使用者中止停止後續。結構驗證不是辨識語意驗收。

### 7.4 現存紀錄與歷史紀錄

- 本次交接讀到目前批次`Financial_20261022_01-23-16`的processed Record為`processed_toc_failed`，停在gemini，錯誤為`Gemini HTTP 503；共嘗試4次，已停止`。這是現存紀錄，不是本次重送PDF。
- 10/21曾有獨立目錄run成功紀錄`toc_20261021_195003_434745`：26項舊目錄、總3369 tokens。屬歷史成功，不代表目前大標專用提示詞或所有財報都成功；本次不重驗該舊目錄、不重呼叫API。
- 舊qwen_*產物屬已停用實驗，不因舊檔存在而恢復Qwen。

## 8. 批次產物、chunk規則與指定樣本

### 8.1 目前輸出配置

新批次名為台灣24小時制`Financial_YYYYMMDD_HH-MM-SS`，例`Financial_20261022_01-23-16`；同批後續階段沿用原名，歷史流水號名仍可讀。不是每份財報一個多層docling時間目錄；同秒碰撞停止，不補流水號或覆寫。

```text
Output/
├─ markdown_raw/Financial_20261022_01-23-16/
│  ├─ 2025_2330_raw.md
│  ├─ Financial_Table/2025_2330_table.pdf
│  └─ Record/2025_2330_reocrd 與 2025_2330_reocrd.ocr
├─ markdown_processed/Financial_20261022_01-23-16/
│  ├─ 2025_2330_processed.md
│  ├─ 2025_2330_tablerefer.json       # 僅目錄成功時存在；此樣本缺少
│  └─ Record/2025_2330_reocrd
├─ markdown_tagged/Financial_20261022_01-23-16/
│  ├─ 2025_2330_tagged.md
│  └─ Record/2025_2330_reocrd
└─ markdown_chunk/Financial_20261022_01-23-16/
   ├─ 2025_2330_chunk.md
   ├─ 2025_2330_chunk.json
   └─ Record/2025_2330_reocrd
```

- 檔名`reocrd`為使用者指定，勿自行改正拼字；Record內容為UTF-8 JSON。新raw紀錄在批次內，不在raw根目錄；舊根目錄Record只作受來源／批次驗證的讀取相容，不移動或刪除。
- 新`_raw.md`是保留Page的完整Markdown，不再輸出另一份無頁序序列化版。舊raw／document雙版本與多層歷史資料仍保留，不能套用新檔名語意。
- 公司／年度檔名不帶季度；只有目前使用者指定的chunk doc_id固定Q4，不把比較年度當報告年度，不自行推定其他季別。

### 8.2 tagged → chunk

`chunk_tagged_batch()`核對tagged Record、同批身分與雜湊後，`parse_tagged()` → `chunk_tagged()` → schema及正文來源覆蓋驗證 → Markdown／JSON集中輸出。

1. 只從真正hd2「公司沿革」開始，中文編號與空白可有；之前的封面、目錄、會計師報告、四大報表不納入chunk。找不到起點停止，不猜配別的章節。
2. hd2強制切開前塊；hd3起的下層小節未滿1000字可合併，用堆疊保存每段祖先及子標題。大標變更亦避免混成同一章節。
3. 1000是正文字數等待門檻，不是硬上限。正文文字、數字、標點計數，空白、標題及HTML／自訂標籤不計；HTML實體依解碼字元計數。達門檻後等content_end才切。
4. 若P35達1000而未等到content_end，P37（達上限頁+2）起遇下一個中文「。」才強制切。半形小數點不切；沒有句號就等後續content_end、hd2、表格或EOF，尾段保留。
5. 表格獨立完整一塊，不受1000字或跨頁句號限制；讀取舊每頁獨立table包裝時，也依兩表之間任一接續詞忽略空白合併。所有HTML片段與中間原文保留，不去重表頭或重排欄列。
6. 最低支援2.4 hd格式來源；依Record版本略過舊頁首hd2快照與空hd，不把快照當新章節。只在記憶體解讀，不回寫tagged或猜舊XML。
7. 未辨識Markdown標題仍保留、不計正文字數；若它是表格前僅有的說明，可形成正文數0但內容非空的文字塊，避免丟失「各期別發行主要條件如下」等說明。

### 8.3 JSON與Markdown呈現

JSON schema=`financial-chunks/1.0`，切分規則=`heading-content-chunks/1.0`，Markdown呈現=`chunk-markdown/1.1`。後者記錄於Record，不為此次顯示修正增加JSON欄位。

| 欄位 | 目前意義 |
| --- | --- |
| chunk_id | 例如2025Q4_2330_Financial_Report__c00001；文件內順序號 |
| doc_id | 使用者指定：年份Q4_股票代號_Financial_Report，本輪固定Q4 |
| years | Page中報告年份整數清單，不依內文提到往年改寫 |
| page | chunk涵蓋的實際PDF頁序清單；table且多頁可辨識跨頁表格 |
| title | main_title及以hd2為根的heading樹，節點有level、text、children |
| data_tags | 先空清單，不自行產生會計項目標籤 |
| content_type / content | text／table與內容，完整表格不截斷 |
| body_char_count / cut_reason | 正文字數及實際切點原因 |
| source_spans | 原tagged Unicode字元[start,end)來源區間，不是byte或PDF座標 |

JSON根另有schema_version、rule_version、source_sha256、excluded_prefix_end與chunks，與目錄JSON不同。使用者問過維護欄位用途；已說明，但**尚未批准刪欄位、搬到Record或改名**。`children`只是樹狀資料常用的「下一層子標題」名稱，不是模型專用詞；目前名稱保留。

Markdown每塊第一行是hd2。新塊若延續小節，補上當時繼承的小標：文字塊放content內、表格塊放table_start前；不提前搬動後面才出現的標題，不重列原content已有的新標題。這是chunk輸出整理，沒有把tagged的下層hd搬進content；JSON結構與content也未因這次Markdown呈現修正而改變。

同一來源與同一切分規則重跑ID可重現；改內容／規則後序號可能位移，不能當跨版本永久索引ID。後續embedding欄位、模型、向量庫、索引去重與更新策略均尚未批准。

### 8.4 指定樣本的目前結果

本次交接從磁碟重新核對：

| 階段 | 目前記錄 |
| --- | --- |
| raw | converted_needs_review；Page正文、兩頁PDF與批次內Record均存在 |
| processed | processed_toc_failed；503共嘗試4次，保留processed，無tablerefer JSON |
| tagged | tagged_temporary_fallback_needs_review；仍為2.4舊產物，未覆寫 |
| chunk | chunked_needs_review；176塊＝92文字＋84表格，Markdown呈現1.1 |

chunk涵蓋P15至P85，doc_id=`2025Q4_2330_Financial_Report`，納入範圍的96個HTML表格片段保留於84個表格塊；原全檔其餘8個表格在公司沿革前，按需求排除。最長文字塊1677字，符合等待content_end而不是硬切1000的規則。本樣本未觸發P35→P37句號強切，該分支以合成測試驗證。

本次交接重新驗證tagged檔SHA與其Record相同、chunk MD／JSON SHA與chunk Record相同。前輪已驗證的HTML逐字、正文來源覆蓋及字數保留，不冒稱本次又重做所有品質驗證。

## 9. 實驗輸出隔離

`functions/experiments/export_output.py`集中處理raw／processed／tagged／chunk／獨立目錄及保留的舊相容輸出，呼叫與模組可搜尋EXPERIMENT_ONLY。

| 新批次 | 寫檔入口與主要呼叫 |
| --- | --- |
| raw | markdown_run_paths／export_markdown_run，main.run_markdown呼叫 |
| processed | processed_run_paths／export_processed_run，process_batch.py呼叫 |
| tagged | comment_tag_paths／export_comment_tags，tag_batch.py呼叫 |
| chunk | chunk_run_paths／export_chunks，chunking/batch.py呼叫 |

核心回傳記憶體結果（MarkdownDocument、HeadingMarkResult、CommentTagResult、TocResult、ChunkResult等），停用寫檔不移除解析與切分。批次重載Output是目前實驗操作，不構成未來正式問答依賴Output的決定。

chunk MD／JSON來源同一結果，整批先檢查碰撞；若成對寫入失敗／中止，只清理本次剛建立的半份檔案並記錄失敗，不動來源或既有有效產物。未獲授權，不刪Output或重建付費索引。正式移除實驗輸出時，依README清單調整呼叫及設定，不把核心能力一起刪除。

## 10. 驗證紀錄：歷史、前輪與本次分開

| 紀錄 | 範圍 | 限制 |
| --- | --- | --- |
| OCR指定2／3／15／50頁與合成混合頁 | 歷史真實本機推論，有錯字／錯欄 | 未代表整份或真實混合頁品質通過，本次未重跑 |
| 補標記1.1指定raw | 歷史8行補標記、104表格不變 | 規則結果，不是全文語意驗收 |
| Gemini歷史成功與目前503失敗 | 磁碟上已有的服務紀錄 | 本次沒有重新呼叫API；失敗不代表目錄辨識本身已執行 |
| 前輪全套167項通過 | 已執行單元／模擬測試，含chunk與Markdown小標補齊 | 本次只更新交接，不把前輪結果冒充本次重跑 |
| 前輪實際chunk輸出 | 176塊；96個納入表格、正文覆蓋、字數與來源核對 | 人工標題／跨頁接表語意仍待確認 |
| 本次交接核對 | 閱讀程式、設定、文件、現有Record；Python3.11.9；來源與輸出雜湊核對 | 未重跑完整測試、OCR、PDF轉換、Gemini或重新產生chunk |

需要修改程式時再執行適合的驗證；純文件更新不為湊紀錄重跑模型。可用的本機／模擬測試指令：

```powershell
& .\Code\.venv\Scripts\python.exe -X utf8 -m unittest discover -s Code/tests -q
& .\Code\.venv\Scripts\python.exe -X utf8 -m unittest discover -s Code/tests -p 'test_chunks.py' -q
```

`tests/validate_ocr_pages.py`、`create_mixed_fixture.py`是真實模型或fixture驗證入口，不當純單元測試隨意執行。`maintenance/mineru_web/`仍屬獨立工具。

## 11. 下一個對話建議順序（尚非實作授權）

1. 先閱讀現有chunk Markdown及JSON，人工抽查公司沿革起點、hd2／子標題、接續表格是否符合預期，不重複呼叫Gemini。
2. 若使用者再問頁首hd2，先核對來源Record版本與chunk讀取相容，不把舊2.4檔誤說成最新2.8的輸出。使用者尚未要求覆寫舊tagged，勿擅自重產。
3. JSON目前含層級樹與追溯欄位。若要精簡／改名，先確認哪些留主要JSON、哪些移Record；不要把先前建議當批准。
4. 公司沿革大標備援是暫時規則；改更可靠目錄／附註定位前，確認方法及可靠證據。現有接續詞規則只有字面證據，人工發現誤接時先討論，不自行加未確認條件。
5. 若要再往embedding走，先確認embedding文字欄位（含HTML如何表達）、模型／維度、服務與資料外傳／費用限制、向量庫、來源識別與更新去重策略，再規劃批次與驗證。這些尚未批准，不直接把整份JSON序列化送模型。
6. 100–200份只是目標規模，不能由此推定並行數、預算、時限或獲准整批處理。正式問答、檢索／重排序與回答評估仍需需求與證據設計。

## 12. 相關文件與歷史衝突提醒

- `Code/README.md`：目前操作、依賴、實驗清單及歷次驗證；第四階段含chunk規則與實際產物。
- `Code/ocr_integration_plan.md`、`Code/ocr_validation_results.md`：OCR來源、授權、參數與歷史小範圍品質。
- `Code/heading_mark_validation.md`：補標記歷史樣本及限制。
- `Code/markdown_tagging_prompt.md`、`Code/markdown_tagging_plan.md`：舊討論，不能整份當現行2.8規格；舊notes_scope／excluded／tableblock不等於新批次入口。
- `Code/toc_validation.md`：目錄、schema、抽頁及歷史模擬／既有服務紀錄；模型提示詞已改大標專用，重試不再是0。
- `USER_STORIES.md`、`FLOWCHART.md`前段亦保留歷史狀態；遇到「chunk尚未實作」「目錄未接標籤」「EasyOCR現用」「每份多層docling資料夾」等字樣，要對照最新追加、實際版本與本交接辨別，不能自行覆蓋其他文件歷史。

目前沒有改JSON children命名／精簡維護欄位的批准，也沒有embedding／正式部署的批准。交接只記錄現有進度，不能當成新的執行授權。


## 13. Code_2 embedding前處理追加（2026-10-22）

使用者確認沿用現有空Code_2/，本次新增獨立main、config/embedding.py、functions/embedding（batch、prepare、table_text、metadata）、functions/experiments/export_output.py、tests與README。Code原有程式未改；僅同步其文件。新階段不匯入Code的同名functions/config，不移動或改動Reference Sources。

輸入markdown_chunk的Financial批次與Record，檢查JSON schema、識別／檔名／批次、來源與輸出雜湊。純記憶體prepare_document另外建立embedding_text、有型別metadata及完整original_chunk，不改原chunk；多子節以清楚標示的小節索引表示，不把最後一個子節當整塊標題。表格轉成pipe，合併格按使用者確認展開複製原值，真正空白不推填。跨頁表格仍為一個完整chunk，保留其所有表段及中間文字。

輸出沿用來源Financial批次，在Output/embedding_prepared/保存年度_股票代號_prepared.json、_prepared.md、Record/年度_股票代號_reocrd。獨立EXPERIMENT_ONLY寫檔可用Settings.export_enabled或--no-export停用；整批防覆寫，單份失敗只留紀錄，寫檔中止／失敗清理僅本次新建半份檔案。原始Code輸出、PDF與模型不變。

本次重新執行22項測試通過，指定2025_2330樣本176個chunk已輸出；96段HTML、994列及所有原chunk逐筆保留，有型別metadata、數字出現次數、來源／輸出雜湊核對通過。c00056原HTML9881字元，prepared含標題5821字元；未計算tokens，不能把字元差宣稱為token差。操作與唯讀樣本驗證指令見Code_2/README.md。

狀態是prepared_needs_review，不是已完成向量化。模型／tokenizer／向量庫未選，token_count為null、token_check_status為pending_model_selection；尚未下載模型、呼叫API、執行上限判定或產生多搜尋向量。完整metadata樹與清單不是已經通過特定向量庫的寫入格式。後續需使用者確認模型與超長表格策略後再做。


## 14. 可選BGE／Voyage與欄位配置（US-15，本輪）

使用者已確認：BGE-M3＋Chroma以CPU執行，Voyage使用voyage-finance-2；本次不真實呼叫Voyage。任一chunk超限即該模型該份整份停止並回報chunk_id、tokens、limit，不截斷。欄位設定採Code_2/config/embedding_fields.txt，四模式embedding、metadata、both、ignore；兩模型資料庫在VectorStore/chroma/bge、voyage。

Code_2/main.py選單1前處理、2選模型建庫、3查看最近操作清冊。新增fields.py（嚴格欄位模式）、load_prepared.py（同批Record／雜湊驗證）、providers.py（BGE／Voyage）、keys.py（僅VOYAGE_API_KEY）、indexing.py（整份token預檢與批次向量）、store.py（Chroma與提交清冊）。原Code程式、來源PDF、參考程式及既有prepared保持不變。

已安裝鎖定版本ST6.2.0、Chroma1.5.9、Voyage0.5.0，pip check通過；Code_2/requirements.lock為共享Code/.venv完整版本快照，不覆寫Code原鎖檔。BGE鎖定revision5617a9f61b028005a4858fdac845db406aefb181，快取Code_2/.cache/embedding。第一次Xet權重下載停滯，停止本次下載程序後改一般HTTP；此開關集中hf_disable_xet，不修改系統開機或登入設定。

每份先計全部token；查完符合上限才產生向量，全部向量就緒後寫入Chroma與SQLite提交清冊。完整原chunk／HTML、所選文字與有型別metadata存資料庫payload，payload JSON本身不送embedding。空清單不當Chroma篩選欄位，完整值仍保留。必要索引與attempts清冊不是可移除的實驗Output；--no-export只適用前處理，建庫只檢查用--check-only。只有提交文件可被store.search召回。

相同來源重跑驗證後跳過、不重新算向量；同文件改版時拒絕覆寫，等待使用者確認更新／移除。不同模型、欄位或規則隔離collection。失敗只清理本次run，不重設整庫；中止或崩潰殘留的未提交資料不可召回，重跑要求先確認恢復方式。

本次48項單元／模擬與實際Chroma暫存庫測試通過。BGE實際tokenizer核對指定176個chunk：最大3987、總63329，皆低於8192。真實完整BGE建庫及單題取回的本輪結果另記Code_2/README.md；Voyage只有模擬與停用閘門驗證，無真實服務或品質結論。100–200份的整批成本與時間仍需代表性多文件測量，未執行整批。


US-15下載與驗證追加：原下載器停滯後，新增Code_2/functions/embedding/model_download.py及maintenance/download_bge.py入口，按公開Range下載並核對官方SHA；可恢復的暫存不冒充完整模型，不清除舊快取。52項本機Windows測試通過，含4項下載保護測試。舊48項是該新增之前的狀態；最新真實BGE模型／取回驗證結果以Code_2/README.md為準。
