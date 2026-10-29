"""兩種策略只規劃搜尋單位／回傳父項，不重新解析Markdown。"""
from dataclasses import dataclass
from functions.chunking.semantic_structure import Node, Unit, semantic_units


@dataclass
class Plan:
    atoms: list
    parent: bool
    reason: str


def pack(units, limit):
    """在安全段落／綁定單位邊界裝箱；不可拆單位可以超限。"""
    result, pending, count = [], [], 0
    for unit in units:
        if pending and count + unit.weight > limit:
            result.append(pending)
            pending, count = [], 0
        pending.extend(unit.atoms)
        count += unit.weight
    if pending:
        result.append(pending)
    return result


def child_parts(atoms, target):
    """累積至少target字，在下一個原始段落結束處切；表格atom不拆。"""
    result, pending, count = [], [], 0
    for atom in atoms:
        pending.append(atom)
        count += atom.weight
        if count >= target:
            result.append(pending)
            pending, count = [], 0
    if pending:
        result.append(pending)  # 父項末尾短段仍保留，不能跨父項補足字數。
    return result


def plan_chunks(roots, config):
    if config.mode not in ('original', 'parent_child'):
        raise ValueError('切塊模式須為original或parent_child')
    for name in ('parent_limit', 'child_target', 'recursive_threshold'):
        if type(getattr(config, name)) is not int or getattr(config, name) < 1:
            raise ValueError(f'{name}須為正整數')
    if config.child_target > config.parent_limit:
        raise ValueError('Child目標字數不可大於Parent上限')
    result = []

    def emit(units):
        pending = []
        def plain():
            if pending:
                limit = config.recursive_threshold if config.mode == 'original' else config.parent_limit
                for atoms in pack(pending, limit):
                    result.append(Plan(atoms, config.mode == 'parent_child', 'paragraph_pack'))
                pending.clear()
        for unit in units:
            if unit.special:
                plain()
                # 已綁定內容沒有安全拆點，保留超限完整父項；原表及###不可破壞。
                result.append(Plan(unit.atoms, config.mode == 'parent_child' or
                                   unit.weight > config.recursive_threshold, unit.reason))
            else:
                pending.append(unit)
        plain()

    def visit(node):
        atoms = node.atoms()
        if not atoms:
            return
        if node.audit:
            result.append(Plan(atoms, False, 'audit_heading'))
            return
        units = semantic_units(atoms)
        if node.weight <= config.recursive_threshold and not any(u.special for u in units):
            result.append(Plan(atoms, config.mode == 'parent_child', 'heading_within_threshold'))
        elif any(isinstance(p, Node) for p in node.parts):
            run = []
            for part in node.parts:
                if isinstance(part, Node):
                    emit(semantic_units(run))
                    run = []
                    visit(part)
                else:
                    run.append(part)
            emit(semantic_units(run))
        else:
            emit(units)
    for root in roots:
        visit(root)
    return result
