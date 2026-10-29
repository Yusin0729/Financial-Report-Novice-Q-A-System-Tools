
import copy
from .db_postprocess import DBPostProcess
from .rec_postprocess import CTCLabelDecode

def build_post_process(config, global_config=None):
    config = copy.deepcopy(config)
    name = config.pop("name")
    if global_config:
        config.update(global_config)
    registry = {'DBPostProcess': DBPostProcess, 'CTCLabelDecode': CTCLabelDecode}
    if name not in registry:
        raise ValueError(f"Unsupported OCR component: {name}")
    return registry[name](**config)
