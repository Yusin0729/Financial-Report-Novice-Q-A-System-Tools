> 更新：使用者已確認第10節全部建議，已實作並完成指定小範圍測試；以下保留決策時的調查方案，現況與限制見 [ocr_validation_results.md](ocr_validation_results.md)。

# Docling × MinerU OCR 整合方案（待確認，尚未切換）

日期：2026-10-21。此文件是程式與本機來源核對後的修改方案，不是完成整合或 OCR 品質通過報告。

## 1. 本次邊界

保留 Docling 的 PDFium 後端、版面、表格、閱讀順序、PDF 實體頁序及 HTML Markdown 輸出。只替換 OCR stage 的辨識引擎，使用本機 MinerU 的 PytorchPaddleOCR 元件，不啟動 MinerU pipeline、版面模型、表格模型、公式模型或網頁。

維持 OCR 開關預設關閉，開啟後按區域補文字；CPU、本機處理，不外傳文件、圖片或文字。此次不修改 Code/maintenance/mineru_web/，也不修改「pdf轉成markdown」獨立工具或 Reference Sources 原檔。既有環境、模型快取與 Output 保留。

## 2. 已核對的實際來源

### 環境

| 項目 | 本次讀取的版本 |
| --- | --- |
| Python | 專案原有 Python 3.11 環境 |
| docling-slim | 2.140.0 |
| docling-core | 2.103.0 |
| torch / torchvision | 2.14.0 / 0.29.1 |
| numpy / opencv-python-headless | 2.4.6 / 5.0.0.93 |
| PyYAML / shapely / pyclipper | 6.0.3 / 2.2.0 / 1.4.0 |
| mineru、paddleocr、paddlepaddle | 未安裝於專案 venv |
| loguru、omegaconf、modelscope | 未安裝於專案 venv |

沒有因此安裝、更新套件或載入模型。讀取當下可用 RAM 約 4.07 GiB，會隨其他程序變動。

### MinerU 來源

本機根目錄：`Reference Sources/MinerU_Protago-master/`。

- `mineru/version.py`：2.6.5；來源儲存庫網址見 pyproject：<https://github.com/opendatalab/MinerU>。本機沒有 .git，原始 commit 未知，不能將上游目前版本冒充本機版本。
- `mineru/model/ocr/pytorch_paddle.py`：PytorchPaddleOCR 建構、CPU 自動切語言、偵測與辨識、信心分數篩選。SHA-256：`707313979b0aca7e01636db4efeec643879997d05051cb39b9cc70fcd15ecc82`。
- `mineru/backend/pipeline/model_init.py`：只參考 OCR 的參數；不能匯入這個模組當入口，因為頂層還匯入 YOLO、公式與表格等元件。
- `mineru/model/utils/tools/infer/{predict_system,predict_det,predict_rec,pytorchocr_utility}.py`：OCR 元件、縮放還原、架構讀取、辨識批次。
- `mineru/model/utils/pytorchocr/`：模型架構、前／後處理及資源；實作時只取選定模型的必要依賴，不整包搬入。
- `.../utils/resources/models_config.yml`、`arch_config.yaml`、`dict/ppocrv5_dict.txt`：模型對照、架構與字典。
- `mineru/utils/{config_reader,models_download_utils,ocr_utils,enum_class}.py`：裝置、自動下載、框處理與模型路徑。

### Docling 介面

已讀安裝環境內的：

- `docling/models/base_ocr_model.py`：BaseOcrModel、get_ocr_rects、post_process_cells。
- `docling/models/factories/{__init__,base_factory,ocr_factory}.py`：get_ocr_factory(False) 是快取的 factory，公開 register(cls, plugin_name, plugin_module_name) 可註冊本專案 stage。
- `docling/models/stages/ocr/easyocr_model.py`：現有區域渲染與 TextCell 輸出的範例。
- `docling/backend/pypdfium2_backend.py`：裁切圖先以較高倍率渲染，再縮成 round(crop_width × scale)、round(crop_height × scale)。
- `docling/pipeline/standard_pdf_pipeline.py`：OCR stage 與失敗頁處理。

可用自訂 OcrOptions＋BaseOcrModel，透過明確的 register 註冊，不必修改 site-packages、不必開啟外部插件自動發現。

## 3. PytorchPaddleOCR 的真實行為

這是 PaddleOCR 模型的 PyTorch 實作，不是 PaddlePaddle 執行引擎；不應直接以安裝 paddleocr／paddlepaddle 取代它。

原呼叫形態：

```python
engine = PytorchPaddleOCR(lang="ch_lite", ...)
results = engine.ocr(image_bgr, det=True, rec=True)
# 單張圖片：[[[四點座標, (文字, 信心分數)], ...]]
# 沒辨識到內容時可能是 [None]。
```

- 輸入採 OpenCV 的 BGR 影像；Docling 渲染的 PIL RGB 圖必須明確轉換。
- det 內部依 det_limit_side_len 縮放，後處理會還原至「傳入的裁切圖」座標，不可再除一次 det 的縮放倍率。
- 回傳的 confidence 是辨識分數，不能當作答案正確率。
- 原始碼在 CPU 下把 ch、ch_server、japan、chinese_cht 改成 ch_lite。即使傳 chinese_cht，仍不能宣稱實際跑 server 繁中設定。
- 原始碼強制 rec_batch_num=6，傳入較小值會被覆寫；若採 batch 1，須在本專案的最小改寫版本明確調整並記錄差異。
- 原始 wrapper 會透過全域裝置判斷覆蓋 kwargs.device，單純傳 device='cpu' 不足以保證 CPU；本專案改寫須直接強制 CPU 並驗證模型與輸入 tensor 裝置。

模型對照：

| 方案 | 偵測 | 辨識 | 字典 |
| --- | --- | --- | --- |
| 沿用 CPU ch_lite（建議首輪） | ch_PP-OCRv5_det_infer.pth | ch_PP-OCRv5_rec_infer.pth | ppocrv5_dict.txt |
| 明確指定 server 辨識（另待選擇） | 同上 | ch_PP-OCRv5_rec_server_infer.pth | 同上 |

本機字典含抽查的繁中字、英文字母、數字、括號、百分比與幣別符號；這只能證明字典有該字，不能證明辨識品質。

官方模型目錄：<https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/tree/main/models/OCR/paddleocr_torch>。
目錄顯示偵測約 14.5 MB、lite 辨識約 32.6 MB、server 辨識約 135 MB。只下載選定的兩個權重，不下載整個 PDF-Extract-Kit。上述為權重檔大小，不是 RAM 峰值。下載前須固定實際 repo commit，保存模型 SHA-256。

## 4. 建議的實作分工

| 檔案 | 修改內容（待確認後實作） |
| --- | --- |
| Code/functions/integrations/mineru_paddle_ocr.py | Docling OCR options、stage、註冊及延後載入；座標、信心、失敗及去重診斷 |
| Code/functions/integrations/mineru_ocr_vendor/ | 若採最小納入方案，僅選定 OCR 偵測／辨識及必要架構、字典、前後處理；保留來源與授權 |
| Code/functions/ingestion/pdf_to_markdown.py | 把 OCR options 換成新 stage；Docling 其餘流程沿用；OCR 失敗不換回 EasyOCR |
| Code/config/settings.py | 集中記錄模型、CPU、縮放、偵測與辨識參數、快取及開關；保留預設關閉 |
| Code/main.py | 更新 OCR 標示及錯誤／待核對狀態，保留 Python 3.11、單選與批次入口 |
| Code/schemas.py | 僅在必要時增加明確的 OCR 區域診斷格式，不改既有正文流程 |
| Code/functions/experiments/export_output.py | 集中寫入 OCR 區域狀態／參數／來源診斷；仍為 EXPERIMENT_ONLY，可停用 |
| Code/tests/ | 模擬座標與區域觸發測試、可選真實 OCR 測試；與人工核對分開 |
| Code/requirements.txt、requirements.lock | 依確認後的最小依賴更新；不安裝完整 mineru[pipeline] |
| USER_STORIES.md、FLOWCHART.md、Code/README.md | 更新決策、實際流程、操作、驗證與限制 |

重用方式尚待選擇：

1. **最小納入（建議）**：將選定 OCR 元件及必要資源放到 Code，改成專案命名空間；替換原自動裝置／下載 wrapper，保留必要辨識邏輯，記錄檔案來源、雜湊及變更。Reference Sources 保持唯讀，正式執行不依賴它的存放位置。
2. **直接以本機參考樹作執行依賴**：少複製來源，但綁定 Reference Sources 路徑；原 wrapper 還會強制載入 modelscope、讀其裝置設定，且 CPU 語言與 batch 行為不易明確控制。需額外隔離這些行為，不能假稱原封不動即可符合要求。

不採用複製整個儲存庫／venv／快取，也不修改獨立 MinerU 網頁。

## 5. 區域觸發、座標與原生文字優先

1. 採 Docling OcrMode.PDF_AWARE_LAYOUT_REGIONS，沿用 get_ocr_rects(page)。它檢查版面區域中的 bitmap、可用原生文字與未被文字層解釋的向量形狀；不以「整頁有任何文字」作跳過條件。
2. OCR 關閉時不載入元件。OCR 開啟後，第一個非空 OCR 區域才延後載入一組 det／rec，在同一轉換器內重用；只初始化 OCR，不載入 MinerU 其他模型。
3. 裁切範圍用 PDF 左上座標 (L,T,R,B)；實際送入 OCR 的圖為 W×H。
4. `sx=W/(R-L)`、`sy=H/(B-T)`。OCR 回傳每個像素角點 (u,v) 換為 `x=L+u/sx`、`y=T+v/sy`。保留四個角點到 Docling BoundingRectangle，不只取某兩點，記錄取整差異。
5. 檢查有限數值、尺寸、信心分數範圍及位置。錯誤座標不硬裁成看似正確，明確回報；旋轉與裁切偏移需測試。Docling/PDFium 已處理的旋轉不可再次套用。
6. 建立 TextCell(text=原辨識文字, orig=原辨識文字, from_ocr=True, confidence=原分數, rect=換算四點)。PDF 實體頁序由原 Page／provenance 保留；不把 crop 內行號當頁碼。
7. 使用 post_process_cells 既有 PDF_FIRST 規則保留原生文字，並記錄 OCR 加入、空結果、低信心與重疊排除數量。
8. **已知風險**：Docling 的去重是框重疊判斷，小面積重疊也可能丟掉整個 OCR cell。建議關閉 MinerU 的偵測框合併以降低跨欄與過大框；若混合文字的部分重疊仍會丟失新增內容，記錄待核對／失敗，不默默丟棄，也不自行增加遮罩或語意重排策略。是否進一步改用原生文字遮罩等方法，須以實測結果另行確認。

辨識出的字、符號與數字不做財務語意修補，不刪除負號、括號、小數、百分比、幣別、單位、期間。版面與閱讀順序繼續由 Docling 負責。

## 6. 首輪建議參數（尚待確認）

| 參數 | 建議值 | 理由／差異 |
| --- | --- | --- |
| OCR 預設 | 關閉 | 沿用已確認選擇 |
| device | cpu | 強制 CPU，不自動偵測 GPU |
| profile | ch_lite | 明列本機 MinerU 的 CPU 實際方案 |
| scale | 3.0，即 216 DPI | 沿用目前 Docling OCR 的縮放基準 |
| det_limit_side_len / type | 960 / max | 沿用 MinerU OCR 元件預設；小字效果需核對 |
| det_db_thresh | 0.3 | 偵測元件預設 |
| det_db_box_thresh | 0.3 | 對齊 MinerU pipeline 的 OCR 初始化參數 |
| det_db_unclip_ratio | 1.8 | 對齊 MinerU pipeline 的 OCR 初始化參數 |
| use_dilation | True | 對齊 MinerU pipeline 的 OCR 初始化參數 |
| enable_merge_det_boxes | False | 本專案建議調整，避免跨欄合併；仍需實測 |
| rec_batch_num | 1 | 本專案建議調整原 wrapper 固定 6 的行為，減少同時辨識用量 |
| drop_score | 0.5 | 統一辨識分數門檻，低分需記錄，不算成功文字 |
| 額外方向分類／公式辨識 | 關閉 | 第一輪只接必要 det＋rec |
| CPU threads / PDF batch | 2 / 1 | 沿用目前設定，不同時修改效能參數 |

## 7. 依賴、授權、下載與 RAM

- 本機 MinerU 的完整 pipeline extra 要求 transformers<5，而本專案是 transformers 5.17.0；直接安裝完整 extra 可能改動現有環境，不能將完整安裝視為安全捷徑。
- OCR 靜態路徑需要 torch、numpy、OpenCV、Pillow、PyYAML、shapely、pyclipper、tqdm、OmegaConf，原 wrapper 另用 loguru。大部分已安裝，OmegaConf／loguru 未安裝；若採最小來源改寫，需依實際保留的 imports 決定是否需要 loguru，鎖定確切相容版本後再安裝。
- 不同 OpenCV 套件都提供 cv2，不同時加裝 opencv-python 與目前 headless 版本。只因 MinerU pyproject 有依賴，不代表 OCR 必須安裝 PaddlePaddle、ModelScope、YOLO、ONNXRuntime 或完整 Transformers 舊版。
- 原 source 的模型架構 registry 也匯入其他 backbone/head。最小納入時需限縮到選定模型的必要範圍，不能只複製一個 wrapper 就聲稱依賴已完整隔離。
- 權重載入建議明確 map_location='cpu'、weights_only=True；不因載入錯誤而自動放寬反序列化或退回其他引擎。
- 下載僅取官方 repo 中選定 det/rec，固定 revision 與 SHA-256，建議專案快取 Code/.cache/mineru_ocr/；不複製其他工具的環境或快取。辨識時只用本機檔案。
- 本機 MinerU 根授權為 AGPL-3.0；部分 PaddleOCR 衍生檔案有 Apache-2.0 標頭。官方 PDF-Extract-Kit 模型卡標為 AGPL-3.0。實作須保留來源作者、LICENSE／NOTICE 與修改記錄，不因移除 YOLO 就把整個來源改稱 Apache-2.0；對外提供時仍須依實際採用範圍核對原授權要求。
- Docling 的版面與表格模型依然存在。47 MB 左右的 lite 權重不表示只需 47 MB RAM；峰值還有模型結構、裁切圖、偵測中間張量與並行 Docling stage。此階段沒有載入新模型，無法提供實測 RAM 或速度提升數字。
- 預計只允許單程序、單文件、小範圍測試，記錄程序 RSS、private／Windows commit 可用量及耗時。若記憶體不足，回報並等待釋放，不修改系統分頁檔、不停止其他工作。

來源授權檔：`Reference Sources/MinerU_Protago-master/LICENSE.md`；模型卡：<https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/blob/main/README.md>。

## 8. 失敗處理與實驗診斷

- OCR 區域發生例外、回傳結構錯誤、文字框數量對不上、座標非法：記錄文件／實體頁序／區域／引擎與錯誤，讓 Docling 標記失敗頁，整份不視為 OCR 通過；不退回 EasyOCR。
- 模型回傳 [None]／空陣列、或全部低於門檻：記錄 ocr_no_text／low_confidence，不當成成功辨識的空白；保留原始 PDF 頁序及可用原生文字，整份需核對 OCR 狀態。
- 真空白與未辨識不能單靠空回傳區分，人工品質驗收另外記錄。
- 必要 OCR 區域診斷加入原本 Output/markdown_raw/<文件>/<執行時間>/，仍集中在 export_output.py，附 EXPERIMENT_ONLY；關閉輸出不阻斷核心記憶體資料流。具體診斷產物在實作時保持小範圍，不預設把全文寫入日誌。

## 9. 提議的驗證範圍（須先確認，尚未實跑新引擎）

文件：Financial Statements/2025Q4_2330_Financial_Report.pdf，85 頁。

| PDF 實體頁序 | 已讀到的結構 | 測試目標 |
| --- | --- | --- |
| 2 | 原生文字 0、圖片物件 1 | 掃描目錄，章節、頁碼與附註編號是否分開 |
| 3 | 原生文字 0、圖片物件 1 | 掃描正文，文字完整性、直排日期與閱讀順序分開分析 |
| 15 | 原生字元 820、圖片物件 0 | 原生正文優先、OCR 不應無條件覆寫；附註與小表格 |
| 50 | 原生字元 1470、圖片物件 0 | 財務表格、負值／幣別／小數及原生文字去重 |

此文件逐頁掃描「原生字元>0 且有圖片物件」未找到候選，不宣稱已驗證真實混合頁。建議另加一份明確標示的合成混合頁（原生文字＋掃描區域），驗證觸發與座標；若要真實混合品質評估，需使用者指定文件／頁碼。合成頁是工程測試，不能取代真實混合頁驗收。

現有基準：

- `Output/markdown_raw/2025Q4_2330_Financial_Report/docling_20261020_235006_210207/`：OCR 關閉，既有 manifest 記錄 577.83 秒，第 1～14 頁無文字。
- `.../docling_20261021_005845_572821/`：EasyOCR 開啟，既有 manifest 記錄 3342.996 秒，沒有 no_text_extracted 頁。
- 這是兩份歷史整份執行資料，環境負載未知，不能直接當成新引擎的效能對照或 OCR 準確率。
- 已讀到第 2 頁目錄有空白項目／標題欄位對應問題、第 3 頁有片段與日期順序問題；來源可能涉及辨識與版面，須檢查中間 OCR 框後分開歸因。
- **第 50 頁在上述兩版均有相同的錯欄**：特別盈餘公積的三個年度季別數字擠入同一個儲存格。因此換 OCR 不能宣稱會解決這個問題，表格結構需要獨立評估。

測試層次：

1. 無模型測試：非整數 crop 偏移與縮放、四點／旋轉、信心閾值、錯誤回傳、空結果、部分重疊、混合區域觸發、禁止 EasyOCR／完整 MinerU pipeline、關閉輸出可回傳核心結果。
2. 真實 OCR 小範圍：先確認頁面後，只處理上述頁面／選定區域，固定模型 commit、影像縮放與參數，逐頁比較文字框及文字。不直接啟動整份或整批。
3. 人工核對：對照原 PDF 與診斷圖，逐項列出可核對的錯字、漏字、財務符號、重複、錯欄與閱讀順序。沒有樣本評估不報準確率，不預設優於 EasyOCR。

## 10. 等待使用者決定

1. 是否採最小必要 OCR 原始碼及資源納入 Code，保留來源／授權並記錄改寫？或把 Reference Sources 作為外部執行依賴？
2. 首輪是否採第 6 節的 ch_lite 參數組合？若要 CPU 使用 server 辨識，須明確取消原 wrapper 的語言改寫並接受額外資源用量。
3. 是否同意第 2、3、15、50 頁＋標示為合成的混合頁先做工程驗證？或指定真實混合頁取代／補充？

答案未確認前，不安裝依賴、不複製 OCR 元件、不更換現有執行引擎、不進行真實 OCR 測試。
