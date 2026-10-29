"""已確認的堆疊追蹤核心；呼叫端提供已辨識標題，不讀寫文件。

參考 chunk_hierarchy.py 的同層／下層彈出概念重新實作，
不匯入舊程式，不沿用固定hd層級或年度抽取。
"""
from config.markdown_tagging import (
    DYNAMIC_MARKER_TYPES, FIRST_DYNAMIC_LEVEL, SECTION_LEVEL,
)
from schemas import HeadingPathItem


class HeadingHierarchy:
    def __init__(self):
        self._path: dict[int, HeadingPathItem] = {}
        self._type_levels: dict[str, int] = {}

    @property
    def path(self) -> tuple[HeadingPathItem, ...]:
        """回傳不可變快照，內文與表格可繼承，不因後續標題而被改寫。"""
        return tuple(self._path[level] for level in sorted(self._path))

    @staticmethod
    def _validate_title(title: str):
        if not isinstance(title, str) or not title.strip():
            raise ValueError('階層標題不可為空；不建立猜測的父層')

    def start_section(self, title: str):
        self._validate_title(title)
        self._type_levels.clear()
        self._path = {SECTION_LEVEL: HeadingPathItem(SECTION_LEVEL, title, 'chinese_comma')}
        return self.path

    def add_dynamic(self, title: str, marker_type: str):
        self._validate_title(title)
        if marker_type not in DYNAMIC_MARKER_TYPES:
            raise ValueError(f'未確認的動態編號類型：{marker_type}')
        if SECTION_LEVEL not in self._path:
            raise ValueError('尚未確認第1層中文編號章節，不建立動態小標題')
        if marker_type not in self._type_levels:
            self._type_levels[marker_type] = FIRST_DYNAMIC_LEVEL + len(self._type_levels)
        level = self._type_levels[marker_type]
        # 回到同層／上層清除舊路徑，但保留本節的類型→層級對應。
        self._path = {k: v for k, v in self._path.items() if k < level}
        self._path[level] = HeadingPathItem(level, title, marker_type)
        return self.path
