"""EXPERIMENT_ONLY：年度×標題目標的必要原始數字判定，不接觸模型。"""
import html
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from Code_2.functions.experiments.eval_scoring import title_name

# 只辨識數字token，不將相鄰儲存格／兩個數字黏成新數字。
NUMBER = re.compile(r'(?<![\d.])(?P<sign>[+\-−－]?)[ \t]*'
                    r'(?P<value>\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)'
                    r'[ \t]*(?P<percent>[%％]?)(?![\d.])')


def numeric_tokens(text):
    text = unicodedata.normalize('NFKC', html.unescape(str(text)))
    text = re.sub(r'<[^>]*>', '|', text)
    text = re.sub(r'(?<=\d)[ \t]*[,，][ \t]*(?=\d{3}(?:\D|$))', ',', text)
    tokens = set()
    for match in NUMBER.finditer(text):
        value = match['value'].replace(',', '').replace('，', '')
        negative = match['sign'] in ('-', '−', '－')
        # 財報括號負值；允許括號內幣別符號及空白。
        prefix = text[max(0, match.start()-12):match.start()]
        suffix = text[match.end():match.end()+8]
        if re.search(r'\([\s$]*$', prefix) and re.match(r'\s*\)', suffix):
            negative = True
        try:
            number = Decimal(value) * (-1 if negative else 1)
        except InvalidOperation:
            continue
        tokens.add((number, bool(match['percent'])))
    return tokens


def number_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('必要數字必須使用非空字串，保留小數、百分比與負號')
    text = unicodedata.normalize('NFKC', value.strip())
    # 數字標準不接受解釋文字或多個數字。
    if not re.fullmatch(r'(?:[+\-−－]?\s*\d[\d,，]*(?:\.\d+)?\s*%?|\(\s*\d[\d,，]*(?:\.\d+)?\s*%?\s*\))', text):
        raise ValueError('必要數字格式無效：'+value)
    tokens = numeric_tokens(text)
    if len(tokens) != 1:
        raise ValueError('必要數字須為單一數值：'+value)
    return next(iter(tokens))


def parse_targets(value):
    if value in (None, ''):
        return None
    try:
        targets = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        raise ValueError('Required_Numbers須為JSON陣列') from None
    if not isinstance(targets, list) or not targets:
        raise ValueError('Required_Numbers須為非空JSON陣列')
    seen = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != {'year', 'title', 'numbers'}:
            raise ValueError('每組必要數字須包含year、title、numbers')
        if target['year'] is not None and (type(target['year']) is not int or not 1900 <= target['year'] <= 2199):
            raise ValueError('必要數字year須為西元整數或null')
        if not isinstance(target['title'], str) or not title_name(target['title']):
            raise ValueError('必要數字title不得空白')
        numbers = target['numbers']
        if not isinstance(numbers, list) or not numbers:
            raise ValueError('每個年度×標題須有非空numbers陣列')
        for number in numbers:
            number_key(number)
        key = (target['year'], title_name(target['title']))
        if key in seen:
            raise ValueError('必要數字的年度×標題重複')
        seen.add(key)
    return targets


def target_numbers(targets, year, title):
    return next((t['numbers'] for t in targets if t['year'] == year and
                 title_name(t['title']) == title_name(title)), None)


def missing_numbers(numbers, text):
    present = numeric_tokens(text)
    return [number for number in numbers if number_key(number) not in present]
