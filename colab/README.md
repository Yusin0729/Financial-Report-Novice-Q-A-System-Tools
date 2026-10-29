# Colab GPU 使用方式

完整的 GitHub 上傳、Colab 開啟與資料準備步驟，見 [GitHub 與 Colab 上傳指南](GITHUB_COLAB_GUIDE.md)。

1. 將程式上傳 GitHub（此修改未代為上傳）。API 金鑰放 Colab「密鑰」，不要提交 `.env`。
2. 在 Colab 開啟 `colab/Financial_RAG_GPU.ipynb`，選 GPU 執行階段，填入 GitHub URL，逐格執行。
3. Notebook 的 clone 格適用可直接讀取的 GitHub 儲存庫。私有庫需先自行登入 Git／安全 clone 到 `/content/Financial_RAG`；勿把 token 放 Notebook 或網址。
4. 財報／產物從 Drive 複製到 `/content` 執行；Chroma、題庫使用本機磁碟。完成工作後執行最後的備份格，再結束執行階段。
5. 備份 ZIP 保留原路徑結構。需要恢復時，先解壓到 Drive 的新資料目錄，再在全新執行階段執行資料複製格；不要合併不同版本的 Chroma 目錄。

## 裝置

`FINANCIAL_RAG_DEVICE=auto|cpu|cuda` 同時控制 Docling、BGE-M3 與 BGE 重排序。
`auto` 在 CUDA 可用時使用 GPU，否則 CPU；`cuda` 無可用 GPU 時直接報錯。
`FINANCIAL_RAG_RUNTIME_PYTHON=current` 讓子程序共用 Colab Python。未設定時，Windows 仍使用原來的 `.venv_pdf`／`.venv`。

CPU／GPU 不列入向量模型簽章，不會只因換裝置要求重建索引；浮點誤差仍可能影響極接近分數的排序。
GPU 加速本機模型；Voyage、GPT、Gemini 在服務端運算，Colab GPU 不會降低其 API token 用量。
目前保留完整精度與原批次設定；GPU 記憶體不足時先使用批次 1，並避免同時載入多個模型。

## 套件與驗證範圍

安裝器合併兩份 requirements，但保留 Colab 預裝的 torch／torchvision／torchaudio，避免套用 Windows CPU 版本。
如果既有 torch 與專案其他鎖定版本不相容，pip 會停止；不會自動降級為 CPU。此時需提供錯誤再調整版本。
不使用 Windows 的 requirements.lock。此版本僅完成離線程式驗證與本機 CPU 回歸，尚未在真實 Colab GPU 執行安裝或模型推論。

`.gitignore` 已排除資料、報告、金鑰及快取；它不會移除已追蹤檔案或 Git 歷史中的金鑰，上傳前需確認 Git 暫存清單。
