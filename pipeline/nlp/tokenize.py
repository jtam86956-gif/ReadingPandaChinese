"""分词 + 词性标注。

M0 用 jieba.posseg。后续可换 pkuseg（准确率更高）或 HanLP。
"""
from __future__ import annotations

import jieba.posseg as pseg

# 首次 import 会加载词典，提前初始化避免首次调用延迟
pseg.POSTokenizer()


def tokenize(text: str):
    """返回 [{"w": 词, "pos": 词性}, ...]。

    跳过纯空白 token。
    """
    out = []
    for w in pseg.cut(text):
        word = w.word.strip()
        if not word:
            continue
        out.append({"w": word, "pos": w.flag or None})
    return out
