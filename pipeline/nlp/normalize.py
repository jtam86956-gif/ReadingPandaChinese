"""繁简统一：把所有内容归一为简体中文。

产品输出要求简体（PRD §9）。信源可能返回繁体（如 BBC 中文部分文章），
统一在入仓前转换。用 opencc-python-reimplemented（纯 Python，无需系统库）。
"""
from __future__ import annotations

from functools import lru_cache

try:
    import opencc
except Exception:  # noqa: BLE001
    opencc = None


@lru_cache(maxsize=1)
def _converter():
    if opencc is None:
        return None
    return opencc.OpenCC("t2s")


def to_simplified(text: str) -> str:
    """繁转简；依赖缺失时原样返回（保证流水线不中断）。"""
    if not text:
        return text
    conv = _converter()
    if conv is None:
        return text
    return conv.convert(text)
