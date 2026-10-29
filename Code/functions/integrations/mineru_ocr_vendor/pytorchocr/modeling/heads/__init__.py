# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import copy
from .det_db_head import DBHead
from .rec_ctc_head import CTCHead
from .rec_multi_head import MultiHead

def build_head(config, **kwargs):
    config = copy.deepcopy(config)
    name = config.pop("name")
    config.update(kwargs)
    registry = {'DBHead': DBHead, 'CTCHead': CTCHead, 'MultiHead': MultiHead}
    if name not in registry:
        raise ValueError(f"Unsupported OCR component: {name}")
    return registry[name](**config)
