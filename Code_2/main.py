"""Code_2問答入口：檢索、重排序、回答與既有索引紀錄。"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Code_2.config.embedding import Settings
from Code.functions.embedding.indexing import recent_attempts
from Code_2.config.embedding import BATCH_PATTERN
from Code_2.functions.qa.catalog import list_indexes
from Code_2.functions.qa.run import run_question
from Code_2.functions.qa.answers import render_answer
from Code_2.config.qa import MODE_LABELS, QASettings
import re


def choose_batch(root):
    from Code_2.functions.embedding.paths import locations
    batches = locations(root)
    if not batches:
        print('沒有可選的批次。')
        return None
    for i, batch in enumerate(batches, 1):
        print(f'[{i}] {batch.relative_to(root).as_posix()}')
    selection = input('選擇批次，0返回：').strip()
    if selection == '0':
        return None
    if not selection.isdigit() or not 1 <= int(selection) <= len(batches):
        print('無效的批次編號。')
        return None
    return batches[int(selection) - 1]


def exit_status(rows):
    if any(r['status'] == 'interrupted' for r in rows):
        return 130
    return int(any(r['status'] not in ('indexed', 'already_indexed', 'checked', 'prepared_needs_review') for r in rows))


def show_indexes(indexes):
    if not indexes:
        print('沒有已提交完成的索引，請先建庫。')
    for i, entry in enumerate(indexes, 1):
        print(f'[{i}] {entry["backend"]}｜{entry["collection"]}｜{len(entry["doc_ids"])}份／{entry["chunk_count"]}塊')
        print('  文件：' + ', '.join(entry['doc_ids']))


def interactive_qa(settings):
    # EXPERIMENT_ONLY：暫時選單。移除本函式及選單4呼叫，不移除核心ask／CLI。
    from Code_2.functions.experiments.qa_menu import run_qa_menu
    return run_qa_menu(settings, index_loader=list_indexes, execute=run_question,
                       display_indexes=show_indexes, display_result=show_question_result)


def show_question_result(result):
    print(render_answer(result))
    if result.get('export_status') == 'saved':
        print(f'已保存Markdown與JSON：{result["output_dir"]}')
    elif result.get('export_status') == 'failed':
        print(result.get('export_error', '本題未成功保存。'))
    elif result.get('export_status') == 'disabled':
        print('已停用實驗寫檔，本題只顯示於畫面。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='財報檢索及可選BGE／Voyage重排序＋Gemini／GPT問答；建庫請使用Code第五階段')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--prepare-batch', type=Path, help=argparse.SUPPRESS)
    group.add_argument('--embed-batch', type=Path, help=argparse.SUPPRESS)
    group.add_argument('--ask', help='原始問題；依--qa-mode執行至排序／重排序／回答')
    group.add_argument('--list-indexes', action='store_true', help='列出已提交索引，不呼叫模型API')
    parser.add_argument('--collection', help='問答所用的已建collection')
    parser.add_argument('--stock-code', help='問答股票代號篩選，保留前導0')
    parser.add_argument('--year', '--report-year', dest='report_year', type=int, help='內容年度篩選：years包含指定西元年；--report-year為相容別名')
    parser.add_argument('--qa-mode', choices=tuple(MODE_LABELS), help='retrieve只排序／rerank到重排序／answer完整回答（預設）')
    parser.add_argument('--rerank-profile',help='重排序設定ID；本機BGE使用local_bge_reranker_v2_m3，不需金鑰')
    parser.add_argument('--include-heading-parent',action='store_true',help='檢索後額外帶回標題父項，內文／表格父項仍固定帶回')
    parser.add_argument('--backend', choices=('bge', 'voyage', 'both'), help='選擇模型，未指定時依設定')
    parser.add_argument('--fields', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--check-only', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--allow-voyage-api', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--no-export', action='store_true', help='停用問答實驗寫檔；問答仍會呼叫API')
    args = parser.parse_args(argv)
    settings = Settings()
    if args.no_export:
        settings = replace(settings, export_enabled=False)
    if args.allow_voyage_api:
        settings = replace(settings, allow_voyage_api=True)
    if args.embed_batch and args.no_export:
        parser.error('--no-export只控制前處理；建庫只檢查請用--check-only')
    if args.prepare_batch and args.check_only:
        parser.error('--check-only只用於建庫；前處理請用--no-export')
    if args.ask is not None and (args.check_only or args.fields or args.backend == 'both'):
        parser.error('問答只選單一已建索引，不使用--check-only／--fields；停用問答寫檔請用--no-export')
    if args.ask is None and (args.collection or args.stock_code or args.report_year or args.qa_mode or args.include_heading_parent or args.rerank_profile):
        parser.error('--collection／--stock-code／--report-year／--qa-mode只適用--ask；互動模式請由選單選擇')
    if args.prepare_batch or args.embed_batch or args.fields or args.check_only:
        parser.error('前處理與建庫已移至Code網頁第五階段或Code/vector.py')
    try:
        if args.list_indexes:
            show_indexes(list_indexes(settings, args.backend if args.backend != 'both' else None))
            return 0
        if args.ask is not None:
            result = run_question(args.ask, settings, backend=args.backend or 'bge', collection=args.collection,
                                  stock_code=args.stock_code, report_year=args.report_year, mode=args.qa_mode or 'answer',
                                  qa=replace(QASettings(),include_heading_parent=args.include_heading_parent,rerank_profile=args.rerank_profile))
            show_question_result(result)
            return int(result['status'] == 'failed' or result.get('export_status') == 'failed')
        while True:
            print('\n財報工具\n[3] 查看最近建庫紀錄\n[4] 財報查詢（排序／重排序／完整回答）\n[0] 離開')
            choice = input('請選擇：').strip()
            if choice == '0':
                return 0
            if choice == '4':
                try:
                    interactive_qa(settings)
                except (ValueError, OSError):
                    print('問答索引讀取失敗，請核對已提交索引與操作說明。')
                continue
            if choice == '3':
                for name in ('bge', 'voyage'):
                    rows = recent_attempts(settings, name)
                    print(f'{name}：{len(rows)}筆紀錄')
                    for row in rows:
                        print(f'  {row.get("doc_id", row.get("source_file"))}：{row["status"]}')
                        for over in row.get('over_limit', []):
                            print(f'  超限：{over["chunk_id"]}，{over["tokens"]}/{over["limit"]} tokens')
                        if 'error' in row:
                            print(f'  {row["error"]}')
                continue
            print('請輸入3、4或0；建庫請使用Code第五階段。')
    except (ValueError, OSError) as error:
        print(f'執行失敗：{type(error).__name__}: {error}')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\n已停止。')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
