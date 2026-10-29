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
from .db_fpn import RSEFPN
from .rnn import SequenceEncoder

def build_neck(config):
    config = copy.deepcopy(config)
    name = config.pop("name")
    registry = {'RSEFPN': RSEFPN, 'SequenceEncoder': SequenceEncoder}
    if name not in registry:
        raise ValueError(f"Unsupported OCR component: {name}")
    return registry[name](**config)
