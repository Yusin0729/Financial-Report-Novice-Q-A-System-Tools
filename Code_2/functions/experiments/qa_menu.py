"""EXPERIMENT_ONLY：暫時的問答參數選單，之後可整個移除。

只處理終端輸入及當次參數，不負責檢索／模型／寫檔。
移除時調整main.interactive_qa及選單4呼叫；保留qa.pipeline.ask與qa.run.run_question。
正式環境預計由外部一次傳入參數產生完整答案，不能在核心呼叫此選單。
"""
import re
from dataclasses import replace
from Code_2.config.qa import QASettings


def choose_count(label, *, default, upper):
    """0取消；空白只採已顯示且有效的既有設定，無效輸入重新詢問。"""
    suffix = f'，Enter沿用{default}' if default is not None else ''
    while True:
        value = input(f'{label}（1–{upper}{suffix}，0取消）：').strip()
        if value == '0':
            return None
        if not value and default is not None:
            return default
        if re.fullmatch(r'[0-9]+', value) and 1 <= int(value) <= upper:
            return int(value)
        print(f'請輸入1至{upper}的整數；0取消本題。')


def run_qa_menu(settings, *, index_loader, execute, display_indexes, display_result):
    """EXPERIMENT_ONLY：設定只用於當次問題，不回寫設定檔或更動索引。"""
    qa = QASettings()
    print('[1] 只排序\n[2] 到重排序\n[3] 完整回答（Gemini）')
    selection = input('選擇執行模式，0返回：').strip()
    if selection == '0':
        return
    mode = {'1': 'retrieve', '2': 'rerank', '3': 'answer'}.get(selection)
    if mode is None:
        print('模式編號無效。')
        return
    indexes = index_loader(settings)
    display_indexes(indexes)
    if not indexes:
        return
    choice = input('選擇問答索引，0返回：').strip()
    if choice == '0':
        return
    if not re.fullmatch(r'[0-9]+', choice) or not 1 <= int(choice) <= len(indexes):
        print('索引編號無效。')
        return
    entry = indexes[int(choice) - 1]
    rule=str(entry.get('signature',{}).get('source_chunk_rule') or '')
    if rule.startswith('bounded-parent-child/') or rule=='content-end-original/1.0':
        value=input('額外帶回標題父項？y啟用，Enter不帶回：').strip().lower()
        if value not in ('','y','n'):
            print('請輸入y、n或Enter。')
            return
        qa=replace(qa,include_heading_parent=value=='y')
    stock = input('股票代號（Enter搜尋該索引全部公司）：').strip() or None
    if stock is not None and not re.fullmatch(r'[0-9]+', stock):
        print('請輸入股票代號數字，保留前導0；公司名稱不自動猜配代號。')
        return
    year = input('內容年度（西元；Enter不限；比對years清單）：').strip()
    if year and (not re.fullmatch(r'[0-9]+', year) or not 1900 <= int(year) <= 2199):
        print('年度須為1900至2199的西元整數。')
        return
    retrieve_k = choose_count('向量檢索數量', default=qa.retrieve_k, upper=qa.max_retrieve_k)
    if retrieve_k is None:
        return
    evidence_k = qa.evidence_k
    if mode != 'retrieve':
        default = qa.evidence_k if qa.evidence_k <= retrieve_k else None
        if default is None:
            print(f'既有重排序數量{qa.evidence_k}超過本次檢索數量{retrieve_k}，請明確指定。')
        evidence_k = choose_count('Voyage重排序保留數量', default=default, upper=retrieve_k)
        if evidence_k is None:
            return
    qa = replace(qa, retrieve_k=retrieve_k, evidence_k=evidence_k)
    print(f'本題範圍：股票代號 {stock or "不限"}；內容年度 {year or "不限"}；召回最多{qa.retrieve_k}塊。')
    if entry['backend'] == 'voyage':
        print('所選Voyage索引需將問題傳Voyage產生查詢向量。')
    if mode != 'retrieve':
        print(f'問題與最多{qa.retrieve_k}個候選片段傳Voyage，保留最多{qa.evidence_k}塊。')
    if mode == 'answer':
        print(f'最多{qa.evidence_k}個完整證據傳Gemini回答；計費依金鑰專案方案，程式無法強制免費。')
    print('輸入0返回。')
    question = input('請輸入問題：')
    if question.strip() == '0':
        return
    result = execute(question, settings, backend=entry['backend'], collection=entry['collection'],
                     stock_code=stock, report_year=int(year) if year else None, index=entry, mode=mode, qa=qa)
    display_result(result)
