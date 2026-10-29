"""純記憶體加標籤；原文及HTML table保持原樣，hd數字就是邏輯層級。"""
import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import asdict
from html import escape
from html.parser import HTMLParser

from config.markdown_headings import PAGE_NUMBER_PATTERN
from config.markdown_tagging import CONTENT_TAG, TABLE_TAG, TAG_GENERATOR, TAGGING_VERSION, RESTORABLE_VERSIONS
from schemas import TaggedBlock, TaggingMetadata, TaggingResult, NotesScope
from .classify_tag_heading import classify_tag_heading
from .heading_hierarchy import HeadingHierarchy
from .mark_headings import _protected_lines
from .page_markers import parse_page_marker

_HEADER = re.compile(r'<!-- RAG_TAGGING version="([^"]+)" original_sha256="([0-9a-f]{64})"(?: notes_start="([0-9]+)" notes_end="([0-9]+)")? -->\n')
_OPEN = re.compile(r'<(hd[1-9][0-9]*|content|tableblock|notes|excluded)\s+.+>\n$')
_CLOSE = re.compile(r'</(hd[1-9][0-9]*|content|tableblock|notes|excluded)><!-- RAG_TAG_END ([bs][0-9]+) -->\n$')
_PRINTED_PAGE = re.compile(PAGE_NUMBER_PATTERN)


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class _Attributes(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def restore_tagged_markdown(text: str) -> str:
    """僅還原本程式版本標記的包裝，全文SHA驗證失敗時拒絕繼續。"""
    header = _HEADER.match(text)
    if not header:
        if text.startswith('<!-- RAG_TAGGING'):
            raise ValueError('加標籤版本標記損壞，不安全還原')
        return text
    if header[1] not in RESTORABLE_VERSIONS:
        raise ValueError(f'不支援的加標籤版本：{header[1]}')
    output, stack = [], []
    for line in text[header.end():].splitlines(keepends=True):
        opening, closing = _OPEN.fullmatch(line), _CLOSE.fullmatch(line)
        if opening and f'generator="{TAG_GENERATOR}"' in line:
            parser = _Attributes(); parser.feed(line)
            attrs = parser.attrs
            if attrs.get('version') != header[1] or not re.fullmatch(r'[bs][0-9]+',attrs.get('id','')):
                raise ValueError('加標籤屬性損壞')
            if stack and stack[-1][0] not in ('notes','excluded'):
                raise ValueError('區塊標籤內不可再巢狀生成區塊')
            stack.append((opening[1],attrs['id'],attrs.get('added_eol')=='1'))
        elif closing:
            if not stack or (closing[1],closing[2]) != stack[-1][:2]:
                raise ValueError('加標籤開閉不匹配')
            active=stack.pop()
            if active[2]:
                if not output or not output[-1].endswith('\n'):
                    raise ValueError('加標籤換行還原資訊損壞')
                output[-1]=output[-1][:-1]
        else:
            output.append(line)
    if stack:
        raise ValueError('加標籤未閉合')
    restored=''.join(output)
    if text_hash(restored) != header[2]:
        raise ValueError('還原後原文SHA-256不符，拒絕重複處理')
    return restored


def tag_markdown(text: str, metadata: TaggingMetadata | None = None, *, notes_scope: NotesScope | None = None) -> TaggingResult:
    metadata = metadata or TaggingMetadata()
    original = restore_tagged_markdown(text)
    lines = original.splitlines(keepends=True)
    header=_HEADER.match(text)
    if notes_scope is None and header and header[3] and header[4]:
        notes_scope=NotesScope(int(header[3]),int(header[4]),header[2],'previous_confirmed_tagging')
    if notes_scope is None:
        raise ValueError('附註起訖範圍尚未確認，不猜測notes邊界')
    if notes_scope.source_sha256!=text_hash(original):
        raise ValueError('附註範圍與來源SHA-256不符，須重新確認')
    if not 1<=notes_scope.start_line<=notes_scope.end_line<=len(lines):
        raise ValueError('附註範圍超出原Markdown行數')
    scope_start,scope_end=notes_scope.start_line-1,notes_scope.end_line-1
    table_ranges=[];code_lines=set()
    protected=_protected_lines(original, lines, table_ranges=table_ranges, code_lines=code_lines)
    starts=[];offset=0
    for line in lines:
        starts.append(offset);offset+=len(line)
    # 同行多表格或表格前後文字一起包裝，絕不在table內插入標籤。
    intervals=[]
    for start,end in table_ranges:
        a=bisect_right(starts,start)-1;b=bisect_right(starts,end-1)-1
        if intervals and a<=intervals[-1][1]:
            intervals[-1]=(intervals[-1][0],max(b,intervals[-1][1]))
        else:intervals.append((a,b))
    table_lines=dict(intervals)
    for a,b in intervals:
        if a<scope_start<=b or a<=scope_end<b:
            raise ValueError('附註邊界切入HTML表格，拒絕切割')
    first=classify_tag_heading(lines[scope_start].rstrip('\r\n'))
    if scope_start in protected or first is None or first.role!='section':
        raise ValueError('已確認附註起點必須是表格／程式碼外的中文編號##標題')
    tracker=HeadingHierarchy()
    blocks=[];issues=[];printed=[];out=[];pending=[];pending_start=0
    current_pdf=None; section_count=0

    def emit(kind, raw, start, end, pdf_pages=None):
        path=tracker.path
        pages=pdf_pages if pdf_pages is not None else ((current_pdf,) if current_pdf else ())
        block=TaggedBlock(kind,start+1,end+1,path,tuple(pages))
        blocks.append(block)
        name=f'hd{path[-1].level}' if kind=='heading' else TABLE_TAG if kind=='table' else CONTENT_TAG
        attrs={
            'generator':TAG_GENERATOR,'version':TAGGING_VERSION,'id':f'b{len(blocks):06d}',
            'kind':kind,'level':str(path[-1].level) if kind=='heading' else '',
            'marker_type':path[-1].marker_type or '' if kind=='heading' else '',
            'path':json.dumps([asdict(x) for x in path],ensure_ascii=False,separators=(',',':')),
            'pdf_pages':','.join(map(str,pages)), 'printed_pages':'', **asdict(metadata),
            'added_eol':'0' if raw.endswith(('\r','\n')) else '1',
        }
        attributes=' '.join(f'{key}="{escape(value,quote=True)}"' for key,value in attrs.items())
        out.append(f'<{name} {attributes}>\n'+raw+('' if attrs['added_eol']=='0' else '\n')+
                   f'</{name}><!-- RAG_TAG_END {attrs["id"]} -->\n')

    def flush():
        if pending:
            emit('content',''.join(pending),pending_start,pending_start+len(pending)-1)
            pending.clear()

    i=0
    while i<len(lines):
        line=lines[i];body=line.rstrip('\r\n')
        page=parse_page_marker(body)
        if i<scope_start or i>scope_end:
            flush()
            if page and i not in code_lines:current_pdf=page
            i+=1;continue
        if i in code_lines:
            flush();out.append(line);i+=1;continue
        if i in table_lines:
            flush();end=table_lines[i];raw=''.join(lines[i:end+1])
            inside_pages=[number for l in lines[i:end+1] if (number:=parse_page_marker(l.rstrip('\r\n'))) is not None]
            pages=tuple(dict.fromkeys(([current_pdf] if current_pdf else [])+inside_pages))
            if tracker.path:emit('table',raw,i,end,pages)
            else:out.append(raw)
            if inside_pages:current_pdf=inside_pages[-1]
            i=end+1;continue
        if page:
            flush();current_pdf=page;out.append(line);i+=1;continue
        if i in protected:
            flush();out.append(line);i+=1;continue
        if _PRINTED_PAGE.fullmatch(body):
            flush()
            printed.append({'markdown_line':i+1,'text':body,'candidate':re.search(r'[0-9]+',body)[0],
                            'status':'unconfirmed_printed_page','pdf_page':current_pdf})
            out.append(line);i+=1;continue
        heading=classify_tag_heading(body)
        if heading:
            flush(); tracked=False
            if heading.role=='section':
                tracker.start_section(heading.title);section_count+=1;tracked=True
            elif tracker.path and heading.role=='dynamic':
                if len(tracker.path)>=1:
                    tracker.add_dynamic(heading.title,heading.marker_type);tracked=True
                else:
                    issues.append({'markdown_line':i+1,'status':'missing_section','title':heading.title})
            elif tracker.path and heading.role=='untracked':
                issues.append({'markdown_line':i+1,'status':'unnumbered_heading_preserved','title':heading.title})
            if tracked:emit('heading',line,i,i)
            else:out.append(line)
            i+=1;continue
        if not tracker.path or not body.strip():
            flush();out.append(line)
        else:
            if not pending:pending_start=i
            pending.append(line)
        i+=1
    flush()
    if not section_count:
        raise ValueError('已確認附註範圍內沒有中文編號章節')
    digest=text_hash(original)

    def scope_wrapper(name,raw,number):
        if not raw:return ''
        added='0' if raw.endswith(('\r','\n')) else '1'
        attrs={'generator':TAG_GENERATOR,'version':TAGGING_VERSION,'id':f's{number:06d}',
               'added_eol':added,**asdict(metadata)}
        if name=='excluded':attrs['reason']='非附註範圍'
        attributes=' '.join(f'{k}="{escape(v,quote=True)}"' for k,v in attrs.items())
        return f'<{name} {attributes}>\n'+raw+('' if added=='0' else '\n')+f'</{name}><!-- RAG_TAG_END s{number:06d} -->\n'

    tagged=(f'<!-- RAG_TAGGING version="{TAGGING_VERSION}" original_sha256="{digest}" notes_start="{notes_scope.start_line}" notes_end="{notes_scope.end_line}" -->\n'+
            scope_wrapper('excluded',''.join(lines[:scope_start]),1)+
            scope_wrapper('notes',''.join(out),2)+
            scope_wrapper('excluded',''.join(lines[scope_end+1:]),3))
    # 交付前驗證每個新增標籤可還原；包含所有原文及table字元。
    if restore_tagged_markdown(tagged)!=original:
        raise ValueError('加標籤原文完整性驗證失敗')
    return TaggingResult(tagged,TAGGING_VERSION,tuple(blocks),tuple(issues),tuple(printed),digest,notes_scope)
