"""EXPERIMENT_ONLY：以標準庫讀寫xlsx，不執行公式、巨集或外部連結。"""
import base64
import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr
from Code_2.config.evaluation import EvaluationSettings
from Code_2.config.qa import QASettings
from Code_2.functions.experiments.numeric_evidence import parse_targets

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HEADERS=('ID','Question','Answer','Page','Doc_Id','Years','Evidence_Main_Section','Evidence_Sub_Section','Evidence_Note_Title','Evidence_Type','Cross_Page_Table')

def text(value):
    return '' if value is None else str(value).strip()

def years(value):
    if not text(value):return []
    parts=re.split(r'[,，;；、\s]+',text(value))
    result=[]
    for part in parts:
        if not re.fullmatch(r'\d{4}',part) or not 1900<=int(part)<=2199:
            raise ValueError('Years須為西元年度，多個年度用逗號或分號分隔')
        if int(part) not in result:result.append(int(part))
    return result

def stock_from_doc(value):
    value=text(value)
    if not value:return None
    match=re.fullmatch(r'\d{4}(?:Q[1-4]|0[1-4])?_(\d+)_[^/\\]+(?:\.pdf)?',value,re.I)
    if not match:raise ValueError('Doc_Id無法可靠取得股號，請使用財報檔名格式')
    return match[1]

def pages(value):
    if not text(value):return []
    result=[]
    for part in re.split(r'[,，;；、\s]+',text(value)):
        match=re.fullmatch(r'(?:(\d{4})_(\d+)_)?P?([1-9]\d*)',part,re.I)
        if not match:raise ValueError('Page須為2024_2330_P50或頁碼，多頁以逗號／分號分隔')
        item={'report_year':int(match[1]) if match[1] else None,'stock_code':match[2],'page':int(match[3])}
        if item not in result:result.append(item)
    return result

def titles(value):
    # 逗號／頓號後接新的章節編號才是多標題邊界；標題自身的逗號、頓號保留。
    numbering=r'(?:[一二三四五六七八九十百千〇零兩廿卅壹貳參肆伍陸柒捌玖拾0-9]+\s*[、.．]|[（(]\s*[一二三四五六七八九十百千〇零兩廿卅0-9]+\s*[)）])'
    boundary=r'[;；\r\n]+|[,，、]\s*(?='+numbering+r')'
    return list(dict.fromkeys(s.strip() for s in re.split(boundary,text(value)) if s.strip()))

def _xml(archive,name):
    raw=archive.read(name)
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('不接受XML實體宣告')
    return ET.fromstring(raw)

def read_upload(data,filename,sheet=None):
    cfg=EvaluationSettings()
    if not isinstance(filename,str) or not filename.lower().endswith('.xlsx') or '/' in filename or '\\' in filename:
        raise ValueError('請上傳.xlsx檔，不接受舊版xls或巨集檔')
    if not isinstance(data,str) or len(data)>cfg.max_upload_bytes*4//3+8:raise ValueError('Excel超過上傳大小限制')
    try:raw=base64.b64decode(data,validate=True)
    except (ValueError,TypeError):raise ValueError('Excel上傳內容無效') from None
    if len(raw)>cfg.max_upload_bytes:raise ValueError('Excel超過上傳大小限制')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            if len(infos)>5000 or sum(i.file_size for i in infos)>cfg.max_uncompressed_bytes:
                raise ValueError('Excel展開後過大')
            book=_xml(z,'xl/workbook.xml')
            rels={r.attrib['Id']:r.attrib for r in _xml(z,'xl/_rels/workbook.xml.rels')}
            sheets=book.find('m:sheets',NS)
            names=[s.attrib['name'] for s in sheets]
            chosen=sheet or names[0]
            if chosen not in names:raise ValueError('工作表不存在')
            node=next(s for s in sheets if s.attrib['name']==chosen)
            relation=rels[node.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            if relation.get('TargetMode')=='External':raise ValueError('不接受外部工作表')
            target=relation['Target']
            path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not path.startswith('xl/'):raise ValueError('工作表路徑無效')
            shared=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                shared=[''.join(t.text or '' for t in s.iter('{'+NS['m']+'}t')) for s in _xml(z,'xl/sharedStrings.xml')]
            table=[]
            for row in _xml(z,path).findall('m:sheetData/m:row',NS):
                values={}
                for c in row.findall('m:c',NS):
                    ref=c.attrib.get('r','')
                    col=re.match(r'[A-Z]+',ref)
                    if not col:raise ValueError('Excel儲存格座標無效')
                    kind=c.attrib.get('t');v=c.find('m:v',NS)
                    if c.find('m:f',NS) is not None:
                        value='[不支援公式]'
                    elif kind=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//m:t',NS))
                    elif kind=='s':value=shared[int(v.text)] if v is not None else ''
                    else:value=v.text if v is not None else ''
                    values[col[0]]=text(value)
                if any(values.values()):table.append((int(row.attrib.get('r',len(table)+1)),values))
                if len(table)>cfg.max_rows+1:raise ValueError('Excel題數超過上限')
    except (zipfile.BadZipFile,KeyError,IndexError,ET.ParseError) as e:
        raise ValueError('Excel結構無法讀取') from None
    if not table:raise ValueError('工作表沒有資料')
    mapping=table[0][1]
    if len(set(mapping.values()))!=len(mapping):raise ValueError('Excel欄位名稱重複')
    if not {'ID','Question'}.issubset(mapping.values()):raise ValueError('必須有ID及Question欄位')
    output=[];seen=set()
    for number,values in table[1:]:
        row={k:'' for k in HEADERS}
        row.update({name:values.get(col,'') for col,name in mapping.items() if name in (*HEADERS,'Required_Numbers','Required_Numbers_Status','Required_Numbers_Note','Required_Numbers_Source')})
        errors=[];identity=row['ID']
        if row['Evidence_Type'] and row['Evidence_Type'] not in ('table','text','mixed'):
            errors.append('Evidence_Type須為table、text或mixed')
        if row['Cross_Page_Table'] and row['Cross_Page_Table'] not in ('yes','no','unknown','not_applicable'):
            errors.append('Cross_Page_Table須為yes、no、unknown或not_applicable')
        if row.get('Required_Numbers_Status') not in (None,'','ready','pending','existing_excluded'):
            errors.append('Required_Numbers_Status須為ready或pending')
        excluded=identity in cfg.excluded_ids
        if not identity or not row['Question']:errors.append('ID／Question必填')
        if identity in seen:errors.append('ID重複')
        if '[不支援公式]' in (identity,row['Question'],row['Years'],row['Doc_Id'],row['Page'],row['Evidence_Note_Title']):errors.append('輸入欄位不接受公式，請貼成值')
        if len(row['Question'])>QASettings().max_question_characters:errors.append('Question超過目前字數上限')
        seen.add(identity)
        try:
            row['filter_years']=years(row['Years']);row['stock_code']=stock_from_doc(row['Doc_Id'])
            row['expected_pages']=pages(row['Page']);row['expected_titles']=titles(row['Evidence_Note_Title'])
            row['numeric_targets']=parse_targets(row.get('Required_Numbers'))
        except ValueError as e:errors.append(str(e))
        row.update(row_number=number,errors=errors,excluded=excluded)
        output.append(row)
    # ID重複的所有列皆阻擋，不能只把第二列標錯。
    counts={r['ID']:sum(x['ID']==r['ID'] for x in output) for r in output}
    for row in output:
        if counts[row['ID']]>1 and 'ID重複' not in row['errors']:row['errors'].append('ID重複')
    return {'filename':filename,'sheet':chosen,'sheets':names,'rows':output,
            'valid_count':sum(not r['errors'] and not r['excluded'] for r in output)}

def _col(index):
    value=''
    while index:
        index,rem=divmod(index-1,26);value=chr(65+rem)+value
    return value

def write_xlsx(sheets, *, presentation=False):
    """應用程式執行時匯出純值報告；不產生或執行公式。"""
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        base='http://schemas.openxmlformats.org/'
        style_type='<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' if presentation else ''
        z.writestr('[Content_Types].xml','<Types xmlns="'+base+'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+style_type+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="{base}package/2006/relationships"><Relationship Id="rId1" Type="{base}officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{NS["m"]}" xmlns:r="{base}officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        style_rel=f'<Relationship Id="styles" Type="{base}officeDocument/2006/relationships/styles" Target="styles.xml"/>' if presentation else ''
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="{base}package/2006/relationships">'+style_rel+''.join(f'<Relationship Id="rId{i}" Type="{base}officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        if presentation:
            z.writestr('xl/styles.xml',f'''<styleSheet xmlns="{NS['m']}"><fonts count="2"><font><sz val="11"/><name val="Microsoft JhengHei"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Microsoft JhengHei"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF245A70"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="4"><xf fontId="0" fillId="0" borderId="0"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" applyFill="1" applyFont="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"><alignment vertical="top"/></xf><xf numFmtId="10" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"><alignment vertical="top"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        for i,(_,rows) in enumerate(sheets,1):
            xml=[]
            for n,row in enumerate(rows,1):
                cells=[]
                for c,value in enumerate(row,1):
                    if type(value) in (int,float):
                        import math
                        if not math.isfinite(value):raise ValueError('Excel數值非有限值')
                        percentage=presentation and c<=len(rows[0]) and '率' in str(rows[0][c-1])
                        style=' s="3"' if percentage else (' s="2"' if presentation and type(value) is float else '')
                        cells.append(f'<c r="{_col(c)}{n}" t="n"{style}><v>{value}</v></c>')
                        continue
                    value='' if value is None else str(value)
                    value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',value)
                    if len(value)>32767:raise ValueError('Excel單格超過32767字，未截斷報告')
                    style=' s="1"' if presentation and n==1 else ''
                    cells.append(f'<c r="{_col(c)}{n}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(value)}</t></is></c>')
                height=' ht="36" customHeight="1"' if presentation and n==1 else ''
                xml.append(f'<row r="{n}"{height}>'+''.join(cells)+'</row>')
            pane='ySplit="1" topLeftCell="B2"' if presentation else 'ySplit="2" topLeftCell="B3"'
            widths='<col min="1" max="1" width="23" customWidth="1"/><col min="2" max="2" width="45" customWidth="1"/><col min="3" max="1001" width="20" customWidth="1"/>' if presentation else '<col min="1" max="1" width="30" customWidth="1"/><col min="2" max="1001" width="48" customWidth="1"/>'
            auto=f'<autoFilter ref="A1:{_col(len(rows[0]))}{len(rows)}"/>' if presentation and rows else ''
            z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="{NS["m"]}"><sheetViews><sheetView workbookViewId="0"><pane xSplit="1" {pane} activePane="bottomRight" state="frozen"/></sheetView></sheetViews><cols>'+widths+'</cols><sheetData>'+''.join(xml)+'</sheetData>'+auto+'</worksheet>')
    return out.getvalue()
