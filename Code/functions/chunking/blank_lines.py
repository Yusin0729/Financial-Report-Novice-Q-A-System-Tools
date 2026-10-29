"""切分完成後清除空行，同步保留正文來源映射；不改切分判斷。"""
import re
from functions.content_context import content_body
from functions.chunking.semantic_structure import size


def _ranges(spans, start, end):
    offset = 0
    for span in spans:
        length = span['end'] - span['start']
        left, right = max(start, offset), min(end, offset + length)
        if left < right:
            yield {**span, 'start': span['start'] + left - offset,
                   'end': span['start'] + right - offset, 'pages': list(span['pages'])}
        offset += length


def remove_blank_lines(document, source):
    """只刪整行空白；父項由清理後的搜尋子項依序重建，避免父子失配。"""
    removed = []
    for chunk in document['chunks']:
        body = content_body(chunk)
        spans, lines, offset = [], [], 0
        # 只將CR/LF視為換行，不把行內Unicode空白誤當換行。
        for match in re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)', body):
            line = match[0]
            if not line:
                continue
            mapped = list(_ranges(chunk['source_spans'], offset, offset + len(line)))
            if line.strip():
                lines.append(line)
                spans.extend(mapped)
            else:
                removed.extend(mapped)
            offset += len(line)
        body = ''.join(lines)
        if not body.strip():
            raise ValueError('空行清理後chunk沒有正文，拒絕輸出')
        chunk.update(content=chunk.get('content_prefix', '') + body,
                     source_spans=spans, body_char_count=size(body))
    for parent in document.get('parents', []):
        field = 'heading_parent_id' if parent.get('node_type') == 'heading_parent' else 'parent_id'
        children = [c for c in document['chunks'] if c.get(field) == parent['chunk_id']]
        children.sort(key=(lambda c: c['source_spans'][0]['start']) if field == 'heading_parent_id'
                      else (lambda c: c['part_index']))
        body = ''.join(content_body(c) for c in children)
        parent.update(content=parent.get('content_prefix', '') + body,
                      source_spans=[s.copy() for c in children for s in c['source_spans']],
                      body_char_count=size(body))
    document['removed_blank_line_spans'] = removed
    for item in document['chunks'] + document.get('parents', []):
        if ''.join(source[s['start']:s['end']] for s in item['source_spans']) != content_body(item):
            raise ValueError('空行清理後來源位置與正文不符')
