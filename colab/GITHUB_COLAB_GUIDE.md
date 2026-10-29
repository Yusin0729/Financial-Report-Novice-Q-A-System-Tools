# GitHub 上傳與 Colab 開始使用

本指南把 Financial_RAG 的程式放到 GitHub，再由 Colab Notebook 取得程式。上傳前先確認 GitHub 儲存庫的公開／私人設定；公開儲存庫的程式任何人都能讀取。

## 一、建立 GitHub 儲存庫

1. 登入 GitHub，按右上角 **+ → New repository**。
2. 儲存庫名稱可用 `Financial_RAG`。選 **Private**，除非你確定要公開程式碼。
3. 建立空儲存庫即可；不要勾選初始化 README、license 或 `.gitignore`，避免第一次推送出現無關的合併問題。
4. 複製儲存庫的 HTTPS 網址，例如 `https://github.com/你的帳號/Financial_RAG.git`。不要把密碼、Personal Access Token 或 API key 放進網址。

## 二、確認目前專案位置

目前程式專案在 `D:\Financial_RAG`。用 PowerShell 開啟此資料夾：

```powershell
Set-Location D:\Financial_RAG
git status --short
```

如果顯示「不是 git repository」，初始化一次：

```powershell
git init -b main
```

如果資料夾已經是 Git repository，不要再次初始化；先看 `git status`、`git branch --show-current` 和 `git remote -v`。後續指令以 main 分支為例，已有其他分支名稱時請用實際名稱。若找不到 git 指令，先從 [Git 官方網站](https://git-scm.com/downloads/win) 安裝 Git for Windows，再重新開啟 PowerShell。

## 三、選擇要上傳的檔案

Colab 需要程式、Notebook 和設定文件。財報、API 設定、向量庫、題庫、模型快取及執行產物留在本機／Drive，不要上傳。

從專案根目錄執行：

```powershell
git add AGENTS.md Code Code_2 colab FLOWCHART.md USER_STORIES.md .gitignore
```

這會依 `.gitignore` 排除 `.env`、`Data/`、`Output/`、`outputs/`、`VectorStore/`、財報、快取及虛擬環境。不要使用 `git add -f` 強制加入被忽略的檔案。

## 四、推送前檢查

先檢查準備提交的檔案：

```powershell
git status --short
git diff --cached --stat
git diff --cached --name-only
```

清單裡應該有 `Code/`、`Code_2/`、`colab/` 和文件；不應有 `.env`、API 設定資料庫、財報 PDF、`Output/`、`VectorStore/`、`Data/`、`.cache/` 或 `.venv/`。

如清單中有不該上傳的檔案，先取消暫存該檔案，再確認 `.gitignore` 規則：

```powershell
git restore --staged -- 路徑
```

`git restore --staged` 適用於已有 commit 的儲存庫。若是首次提交、還沒有任何 commit，改用 `git rm --cached -- 路徑`；資料夾則用 `git rm -r --cached -- 資料夾路徑`。這些指令只取消 Git 暫存／追蹤，不刪除工作目錄原檔。不要以為 `.gitignore` 會自動移除以前已提交的檔案；若金鑰曾經提交，應先在服務商撤銷／輪替，再處理 Git 歷史。

確認清單乾淨後提交並推送：

若 Git 提示尚未設定作者資訊，先設定此儲存庫的顯示名稱及提交信箱（可使用 GitHub 提供的 noreply 信箱）；這些是 commit 作者資料，不是登入憑證：

```powershell
git config user.name "你的顯示名稱"
git config user.email "你的提交信箱"
```

```powershell
git commit -m "Prepare Financial RAG for Colab"
git remote add origin https://github.com/你的帳號/Financial_RAG.git
git push -u origin main
```

如果 `origin` 已存在，跳過 `git remote add`，先用 `git remote -v` 確認它指向你剛建立的儲存庫。GitHub 可能會開啟瀏覽器登入；用 Git Credential Manager 或 GitHub Desktop 登入，不要把 token 寫進指令、Notebook 或檔案。

## 五、在 Colab 開啟 Notebook

1. 開啟 GitHub 儲存庫中的 `colab/Financial_RAG_GPU.ipynb`。
2. 從 GitHub 下載此 `.ipynb`，到 [Colab](https://colab.research.google.com/) 的 **檔案 → 上傳筆記本（Upload notebook）** 選取檔案。開啟 Notebook 只載入筆記本，程式庫仍由第一個程式格取得。
3. 選 **執行階段 → 變更執行階段類型 → GPU**。GPU 是否實際分配，以 Notebook 顯示的 PyTorch CUDA 與 GPU 名稱為準。
4. 逐格執行 Notebook。第一格填剛才的 HTTPS 儲存庫網址與 branch（預設 `main`）。公開儲存庫可以直接 clone；私人儲存庫須先在 Colab 安全登入 GitHub，再 clone 到 `/content/Financial_RAG`。不要把私人 token 放進 Notebook cell、URL 或輸出。
5. 需要 Voyage／GPT／Gemini 時，在 Colab 左側 **密鑰** 新增 `VOYAGE_API_KEY`、`OPENAI_API_KEY`、`GEMINI_API_KEY`，並允許此 Notebook 讀取。Notebook 不會印出金鑰。
6. 將財報或既有階段產物放進 Google Drive 的 `Financial_RAG_data` 資料夾，依原有目錄結構整理；執行 Notebook 的資料複製格，檔案會複製到 Colab `/content` 執行。Chroma 和 SQLite 題庫不直接從 Drive 執行。
7. 填起訖階段、來源 ID 和切分／模型設定後再執行工作格。工作完成後執行最後的備份格，確認備份 ZIP 已寫入 Drive，再結束 Colab 執行階段。

## 常見情況

- pip 因套件版本與 Colab 預裝 PyTorch 不相容而停止：保留錯誤訊息，不要移除 constraints 或改裝 CPU PyTorch；依錯誤調整相容版本。
- Notebook 顯示 CPU：確認 Colab 已分配 GPU，重新執行裝置設定格。`auto` 會在找不到 CUDA 時退回 CPU；若希望立即報錯，可把 `DEVICE` 設成 `cuda`。
- `/content` 會隨執行階段回收。每次工作完成都先備份；重新啟動時把所需資料放入 Drive，再複製到新的 Colab 執行目錄。
- 跨 Windows／Linux 搬移既有 Chroma 資料庫尚未做真實 Colab 還原驗證。重要實驗請保留原索引備份；必要時從 chunk JSON 在 Colab 建新索引。
- 改了 GitHub 程式後，重新啟動 Notebook 執行階段或使用新工作目錄，再確認載入的是更新後的 commit。

## 本機完成程度

Notebook、Colab 輔助程式與裝置切換已加入專案；此指南說明上傳流程。上傳 GitHub、Colab 套件相容性及真 GPU 推論仍由使用者在其帳號環境執行與核對。


## 資料目錄範例

Drive 的 `MyDrive/Financial_RAG_data/` 下面放原專案的對應資料夾：

```text
Financial_RAG_data/
  Financial Statements/        # 從第一階段開始時需要的 PDF
  Output/
    markdown_raw/             # 從第二階段開始所需的來源批次
    markdown_processed/       # 從第三階段開始所需的來源批次
    markdown_tagged/          # 從第四階段開始所需的來源批次
    markdown_chunk/           # 從第五階段開始所需的 chunk JSON
  Data/                       # 可選：既有問題向量題庫
  VectorStore/                # 可選：既有索引；跨平台仍待核對
```

只帶本次起始階段需要的來源即可；保留批次名稱和子目錄結構。設定 `SOURCE_IDS` 時，使用 Notebook 來源清單印出的完整 ID，不自行猜檔名。金鑰放 Colab Secrets，不放上述資料目錄。

## 官方參考

- [GitHub：將本機程式加入 GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
- [Colab：Notebook 上傳、執行環境與資料保存說明](https://research.google.com/colaboratory/faq.html)
