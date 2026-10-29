"""以 bundled Python 執行；實驗 PDF 寫檔集中 export_output。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.experiments.export_output import export_synthetic_mixed_fixture

if __name__=='__main__':
    # EXPERIMENT_ONLY：僅測試資產，不納入財報語料。
    print(export_synthetic_mixed_fixture(SETTINGS.markdown_output_dir,Path(sys.argv[1])))
