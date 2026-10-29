"""既有財報Markdown命名遷移；預設僅列計畫，--apply才執行。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.experiments.export_output import migrate_markdown_filenames

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    # EXPERIMENT_ONLY：所有Output更名與紀錄寫入集中在export_output。
    plan=migrate_markdown_filenames(SETTINGS,apply=args.apply)
    for item in plan:print(f'{item["old"]} -> {Path(item["new"]).name}')
    print(f'{"已改名" if args.apply else "預計改名"} {len(plan)} 個檔案；內容不變。')
