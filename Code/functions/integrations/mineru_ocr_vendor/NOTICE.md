# 來源與修改紀錄

本目錄重用本機 MinerU 2.6.5 的必要 PyTorch OCR 程式，來源 https://github.com/opendatalab/MinerU 。本機來源無 Git commit，逐檔原始 SHA-256 與選取定義見 SOURCE.json。根授權 AGPL-3.0 見 LICENSE.md；保留原有 PaddlePaddle Authors 的 Apache-2.0 標頭，不將整體改稱 Apache 授權。對外散布／提供服務須遵守相應授權及原始碼提供要求。

2026-10-21 修改：僅保留 ch_lite 模型架構、必要 det/rec 模組及字典；限縮 registry，不匯入完整 MinerU pipeline、公式或方向模型。權重載入固定 CPU、weights_only=True；架構 YAML 使用 safe_load 取代 OmegaConf。prepare_ocr_vendor.py 可重現納入步驟。外層 mineru_paddle.py 是 PytorchPaddleOCR 的最小改寫：CPU 固定、batch 1、不合併框、不自動變更語言、不透過全域 MinerU 下載器；保留未過門檻結果供診斷。

權重來自 opendatalab/PDF-Extract-Kit-1.0，模型卡授權 AGPL-3.0，版本及 SHA-256 見 config/ocr.py。未複製原環境或快取；未聲稱重現完整 MinerU。
