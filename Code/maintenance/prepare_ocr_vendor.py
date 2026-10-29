"""一次性重現最小 OCR 來源納入；唯讀參考樹，保留來源 SHA 與授權。"""
import ast
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Reference Sources/MinerU_Protago-master'
DEST = ROOT / 'Code/functions/integrations/mineru_ocr_vendor'
BASE = 'mineru/model/utils/'
FILES = {
    'tools/infer/predict_det.py': None,
    'tools/infer/predict_rec.py': None,
    'tools/infer/predict_system.py': ['TextSystem', 'sorted_boxes'],
    'tools/infer/pytorchocr_utility.py': None,
    'pytorchocr/base_ocr_v20.py': None,
    'pytorchocr/modeling/architectures/base_model.py': None,
    'pytorchocr/modeling/common.py': None,
    'pytorchocr/modeling/backbones/rec_lcnetv3.py': None,
    'pytorchocr/modeling/backbones/rec_svtrnet.py': None,
    'pytorchocr/modeling/backbones/rec_hgnet.py': ['ConvBNAct'],
    'pytorchocr/modeling/backbones/det_mobilenet_v3.py': ['SEModule', 'ConvBNLayer'],
    'pytorchocr/modeling/necks/db_fpn.py': ['RSELayer', 'RSEFPN'],
    'pytorchocr/modeling/necks/rnn.py': None,
    'pytorchocr/modeling/necks/intracl.py': None,
    'pytorchocr/modeling/heads/det_db_head.py': ['DBHead'],
    'pytorchocr/modeling/heads/rec_ctc_head.py': None,
    'pytorchocr/modeling/heads/rec_multi_head.py': None,
    'pytorchocr/postprocess/db_postprocess.py': None,
    'pytorchocr/postprocess/rec_postprocess.py': ['BaseRecLabelDecode', 'CTCLabelDecode'],
    'pytorchocr/data/__init__.py': None,
    'pytorchocr/data/imaug/__init__.py': None,
    'pytorchocr/data/imaug/operators.py': ['DetResizeForTest', 'NormalizeImage', 'ToCHWImage', 'KeepKeys'],
}


def main():
    if (DEST / 'SOURCE.json').exists() and '--refresh' not in sys.argv:
        raise FileExistsError('避免覆寫已納入的程式；重建請另行審查')
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for name, selected in FILES.items():
        original = (SOURCE / BASE / name).read_bytes()
        text = original.decode('utf-8')
        if selected:
            lines = text.splitlines(keepends=True)
            tree = ast.parse(text)
            definitions = {n.name: n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
            selected = set(selected)
            while True:
                used_local = {n.id for name in selected for n in ast.walk(definitions[name]) if isinstance(n, ast.Name)}
                expanded = selected | (used_local & definitions.keys())
                if expanded == selected:
                    break
                selected = expanded
            selected = sorted(selected)
            # 原檔標頭保留；限縮 top-level 類別／函式，刪去不再使用的 import。
            nodes = [n for n in tree.body if not isinstance(n, (ast.ClassDef, ast.FunctionDef)) or n.name in selected]
            used = {n.id for top in nodes if not isinstance(top, (ast.Import, ast.ImportFrom))
                    for n in ast.walk(top) if isinstance(n, ast.Name)}
            nodes = [n for n in nodes if not isinstance(n, (ast.Import, ast.ImportFrom)) or
                     any((a.asname or a.name.split('.')[0]) in used or a.name == '*' for a in n.names)]
            header = ''.join(lines[:tree.body[0].lineno-1])
            text = header + '\n\n'.join(''.join(lines[n.lineno-1:n.end_lineno]) for n in nodes)
        if name.endswith('predict_system.py'):
            text = text.replace('from . import  predict_cls', '')
            text = text.replace('self.text_classifier = predict_cls.TextClassifier(args, **kwargs)',
                                'raise ValueError("orientation classifier is not included")')
        if name.endswith('base_ocr_v20.py'):
            text = text.replace('torch.load(weights_path)', "torch.load(weights_path, map_location='cpu', weights_only=True)")
            text = text.replace('torch.load(weights_path, weights_only=True)', "torch.load(weights_path, map_location='cpu', weights_only=True)")
        if name.endswith('pytorchocr_utility.py'):
            text = text.replace('from omegaconf import OmegaConf', 'import yaml')
            text = text.replace('OmegaConf.load(DEFAULT_CFG_PATH)', "yaml.safe_load(DEFAULT_CFG_PATH.read_text(encoding='utf-8'))")
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
        records.append({'source': BASE + name, 'source_sha256': hashlib.sha256(original).hexdigest(),
                        'selected_definitions': selected, 'vendored_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    registries = {
        'pytorchocr/modeling/backbones/__init__.py': ('build_backbone', 'model_type', {'PPLCNetV3': '.rec_lcnetv3'}),
        'pytorchocr/modeling/necks/__init__.py': ('build_neck', '', {'RSEFPN': '.db_fpn', 'SequenceEncoder': '.rnn'}),
        'pytorchocr/modeling/heads/__init__.py': ('build_head', '**kwargs', {'DBHead': '.det_db_head', 'CTCHead': '.rec_ctc_head', 'MultiHead': '.rec_multi_head'}),
        'pytorchocr/postprocess/__init__.py': ('build_post_process', 'global_config=None', {'DBPostProcess': '.db_postprocess', 'CTCLabelDecode': '.rec_postprocess'}),
    }
    for name, (function, extra, classes) in registries.items():
        original = (SOURCE / BASE / name).read_bytes()
        header = original.decode('utf-8').split('def ')[0].split('__all__')[0]
        # 不保留原 registry 的廣泛匯入，只註冊 ch_lite 使用的模型。
        header = '\n'.join(line for line in header.splitlines() if line.startswith('#'))
        imports = '\n'.join(f'from {mod} import {cls}' for cls, mod in classes.items())
        code = f'{header}\nimport copy\n{imports}\n\ndef {function}(config{", " + extra if extra else ""}):\n    config = copy.deepcopy(config)\n    name = config.pop("name")\n'
        if function == 'build_post_process':
            code += '    if global_config:\n        config.update(global_config)\n'
        if function == 'build_head':
            code += '    config.update(kwargs)\n'
        code += f'    registry = {{{", ".join(repr(c) + ": " + c for c in classes)}}}\n    if name not in registry:\n        raise ValueError(f"Unsupported OCR component: {{name}}")\n    return registry[name](**config)\n'
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding='utf-8')
        records.append({'source': BASE + name, 'source_sha256': hashlib.sha256(original).hexdigest(), 'modification': 'selected registry only'})
    # 僅保留兩個核准模型架構與字典。
    resource = SOURCE / BASE / 'pytorchocr/utils/resources'
    cfg = yaml.safe_load((resource / 'arch_config.yaml').read_text(encoding='utf-8'))
    target = DEST / 'pytorchocr/utils/resources'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'arch_config.yaml').write_text(yaml.safe_dump({k: cfg[k] for k in ['ch_PP-OCRv5_det_infer', 'ch_PP-OCRv5_rec_infer']}, sort_keys=False), encoding='utf-8')
    for name in ['arch_config.yaml', 'ppocrv5_dict.txt']:
        original = (resource / ('dict/' + name if name.endswith('.txt') else name)).read_bytes()
        if name.endswith('.txt'):
            (target / name).write_bytes(original)
        records.append({'source': BASE + 'pytorchocr/utils/resources/' + name, 'source_sha256': hashlib.sha256(original).hexdigest()})
    for folder in list(DEST.rglob('*')):
        if folder.is_dir() and folder.name != '__pycache__':
            init = folder / '__init__.py'
            if not init.exists():
                init.write_text('', encoding='utf-8')
    (DEST / '__init__.py').write_text('', encoding='utf-8')
    (DEST / 'LICENSE.md').write_bytes((SOURCE / 'LICENSE.md').read_bytes())
    (DEST / 'SOURCE.json').write_text(json.dumps({'upstream': 'https://github.com/opendatalab/MinerU', 'local_version': '2.6.5', 'commit': None, 'files': records}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
