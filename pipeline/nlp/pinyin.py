"""注音：把汉字转成带声调拼音。

M0 用 pypinyin（离线、成熟）。多音字消歧留待后续结合词性优化。
"""
from __future__ import annotations

from pypinyin import Style, lazy_pinyin


def to_pinyin(text: str) -> str:
    """返回空格分隔的带调拼音，如 '中国' -> 'zhōng guó'。

    标点与非汉字字符按原样保留（pypinyin errors='default'）。
    """
    if not text:
        return ""
    return " ".join(lazy_pinyin(text, style=Style.TONE, errors="default"))
