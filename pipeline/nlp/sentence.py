"""中文句子切分。

按中英文句末标点 + 换行切分，保留标点在句尾，过滤空句。
M0 用规则切分；复杂语境（引号、省略号）后续可换 LLM 或 nltk 风格分句。
"""
from __future__ import annotations

import re

# 句末标点（含英文）：。！？；!?; 以及换行
_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\n])")


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    raw = _SPLIT_RE.split(text)
    out = []
    for chunk in raw:
        s = chunk.strip()
        if s:
            out.append(s)
    return out
