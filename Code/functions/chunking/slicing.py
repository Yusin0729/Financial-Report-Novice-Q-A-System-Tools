"""以來源區間切Atom；保留頁序，安全字數邊界不切開HTML或實體。"""
import re
from dataclasses import replace
from bisect import bisect_left, bisect_right
from functions.markdown_processing.mark_headings import _protected_lines


def slice_atom(atom, start, end):
    spans, offset = [], 0
    for span in atom.spans:
        length = span['end']-span['start']
        left, right = max(start, offset), min(end, offset+length)
        if left < right:
            spans.append({'start':span['start']+left-offset, 'end':span['start']+right-offset,
                          'pages':list(span['pages'])})
        offset += length
    if offset != len(atom.content) or not spans:
        raise ValueError('Atom內容與來源區間長度不符，不能切分')
    return replace(atom, content=atom.content[start:end], spans=spans,
                   pages=sorted({p for s in spans for p in s['pages']}))


def remove_heading_marks(atom):
    if atom.kind == 'table':
        return atom, []
    lines = atom.content.splitlines(keepends=True)
    protected = _protected_lines(atom.content, lines)
    removed, retained, offset = [], [], 0
    for index, line in enumerate(lines):
        match = re.match(r'^[ \t]*#{1,6}[ \t]+', line) if index not in protected else None
        cut = match.end() if match else 0
        if cut:
            removed.extend(slice_atom(atom, offset, offset+cut).spans)
        if offset+cut < offset+len(line):
            retained.append(slice_atom(atom, offset+cut, offset+len(line)))
        offset += len(line)
    if not retained:
        raise ValueError('移除結構標記後沒有正文')
    return replace(atom, content=''.join(a.content for a in retained),
                   spans=[s for a in retained for s in a.spans]), removed


def split_text(atom, limit):
    """分項目標floor(N/k)；目標後找可用空行、中文句點，否則按字數。

    超過上限的邊界不算可用；末段仍超限則增加k重算。
    """
    from functions.chunking.chunks import visible_units
    positions, counts, count = [0], [0], 0
    for end, weight, _ in visible_units(atom.content):
        count += weight
        positions.append(end)
        counts.append(count)
    if count <= limit:
        return [atom]
    blanks = [m.end() for m in re.finditer(
        r'\r\n[^\S\r\n]*\r\n|\n[^\S\r\n]*\n|\r(?!\n)[^\S\r\n]*\r(?!\n)',atom.content)]
    stops = [m.end() for m in re.finditer('。',atom.content)]
    for divisor in range(max(2,(count+limit-1)//limit),count+1):
        target = max(1,count//divisor)
        cuts, start, used = [0], 0, 0
        for _ in range(divisor-1):
            if count-used <= target:
                break
            lo = positions[bisect_left(counts,used+target)]
            hi = positions[min(bisect_right(counts,min(count-1,used+limit))-1,len(positions)-1)]
            cut = None
            for boundaries in (blanks,stops):
                index = bisect_left(boundaries,lo)
                if index < len(boundaries) and boundaries[index] <= hi:
                    cut = boundaries[index]
                    break
            cut = cut if cut is not None else lo
            if cut <= start or cut >= len(atom.content):
                break
            cuts.append(cut)
            used = counts[bisect_left(positions,cut)]
            start = cut
        cuts.append(len(atom.content))
        parts = [slice_atom(atom,a,b) for a,b in zip(cuts,cuts[1:]) if a < b]
        if all(part.weight <= limit for part in parts):
            return parts
    raise ValueError('無法在指定上限切分正文，未截斷或遺失內容')
