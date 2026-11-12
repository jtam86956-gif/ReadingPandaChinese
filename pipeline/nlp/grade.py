"""难度分级：基于 HSK 3.0 词表覆盖率，估算文章难度。

主词表来自 data/hsk/HSK{1..7}.txt（由 scripts/fetch_hsk30.py 从 GF 0025—2021
《等级标准》抓取）：一级~六级各自独立；高等（七—九级）合并为 level 7。

参考数据：data/hsk/reference/hsk30_exam_syllabus.tsv（HSK 3.0《考试大纲》，
含跨级标注）。生词判定时把它作为第二来源：一个词的「有效已知等级」取 GF 与
考试大纲主级的较低者——任一权威来源在某级收录，即视为该级学习者已学。这能
修正 GF 因词形差异（括注/下标）导致的漏匹配，并减少把中低难度词误判为生词。
考试大纲缺失时优雅降级，仅用 GF，不影响主路径。

词级查询返回 1-7；文章等级输出限定在 1-6（产品用 1-6 刻度，高等映射为 6）。
主词表缺失时降级到内置最小样本并打 warning，保证流水线可跑。
"""
from __future__ import annotations

import csv
import logging
import re
from functools import lru_cache

from pipeline import config

log = logging.getLogger(__name__)

# 内置最小 HSK 样本（仅用于 M0 无数据时兜底跑通；正式词表放 data/hsk/）
_BUILTIN_HSK = {
    1: ["我", "你", "他", "是", "不", "了", "人", "有", "这", "中", "国", "的", "一", "在", "上", "下", "大", "小", "好", "看"],
    2: ["工作", "学习", "生活", "朋友", "时候", "问题", "现在", "因为", "所以", "已经", "可以", "应该", "需要", "觉得", "知道"],
    3: ["新闻", "国际", "社会", "经济", "市场", "发展", "表示", "认为", "影响", "包括", "通过", "进行", "开始", "继续", "可能"],
    4: ["政策", "措施", "报告", "数据", "研究", "分析", "结果", "目前", "根据", "然而", "因此", "虽然", "但是", "如果"],
    5: ["显著", "持续", "逐步", "广泛", "推动", "促进", "面临", "应对", "挑战", "趋势", "领域", "层面", "机制", "体系"],
    6: ["毋庸置疑", "层出不穷", "日新月异", "举足轻重", "众所周知", "应运而生", "迫在眉睫", "循序渐进", "因地制宜", "相辅相成"],
}


@lru_cache(maxsize=1)
def _load_hsk() -> dict:
    """返回 {level: set(words)}，优先 data/hsk，兜底内置样本。"""
    hsk_dir = config.DATA_DIR / "hsk"
    loaded = {}
    for level in range(1, 8):
        f = hsk_dir / f"HSK{level}.txt"
        if f.exists():
            words = {line.strip() for line in f.read_text(encoding="utf-8").splitlines() if line.strip()}
            if words:
                loaded[level] = words
    if loaded:
        log.info("已加载 data/hsk 词表：%s", {k: len(v) for k, v in loaded.items()})
        return loaded
    log.warning("data/hsk 词表缺失，使用内置最小样本分级（仅 M0 验证）。请补充正式词表。")
    return {k: set(v) for k, v in _BUILTIN_HSK.items()}


# 词形归一化：让两份词表与分词结果口径一致
#   同形词下标  本1 / 点1 / 和1  -> 本 / 点 / 和
#   括注        们（朋友们）      -> 们
_TRAIL_DIGIT_RE = re.compile(r"\d+$")
_PAREN_RE = re.compile(r"（[^）]*）")


def _normalize_word(word: str) -> str:
    """归一化词形：去掉尾部同形词下标与全角括注，便于和分词结果匹配。"""
    w = _PAREN_RE.sub("", word)
    w = _TRAIL_DIGIT_RE.sub("", w)
    return w.strip()


@lru_cache(maxsize=1)
def _load_exam() -> dict:
    """考试大纲参考数据：{归一化词: {"primary": int, "cross": [int]}}。

    缺失时返回 {} —— 参考数据，仅用于优化生词判定，不影响主分级。
    同形归一冲突时保留更低主级（更乐观的「已学」判定）。
    """
    path = config.DATA_DIR / "hsk" / "reference" / "hsk30_exam_syllabus.tsv"
    if not path.exists():
        log.info("未找到考试大纲参考词表，生词判定仅用 GF 标准。")
        return {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            key = _normalize_word(r["word"])
            if not key:
                continue
            primary = int(r["primary"])
            cross = [int(x) for x in r["cross"].split(",") if x] if r["cross"] else []
            prev = out.get(key)
            if prev is None or primary < prev["primary"]:
                out[key] = {"primary": primary, "cross": cross}
    n_cross = sum(1 for v in out.values() if v["cross"])
    log.info("已加载考试大纲参考词表：%d 词（其中 %d 条含跨级标注）", len(out), n_cross)
    return out


def _gf_word_level(word: str) -> int | None:
    """仅基于 GF 0025—2021 主词表的等级（精确匹配），未收录返回 None。"""
    hsk = _load_hsk()
    for level in range(1, 8):
        if word in hsk.get(level, set()):
            return level
    return None


def word_level(word: str) -> int | None:
    """词的「有效已知等级」：取 GF 标准 与 考试大纲主级 的较低者。

    任一权威来源在某级收录即视为该级学习者已学，返回 1-7；均未收录返回 None。
    level 7 = 高等（七—九级合并）。考试大纲缺失时退化为纯 GF 等级。
    """
    gf = _gf_word_level(word)
    exam = _load_exam().get(_normalize_word(word))
    primary = exam["primary"] if exam else None
    cands = [lv for lv in (gf, primary) if lv is not None]
    return min(cands) if cands else None


def word_cross_levels(word: str) -> list[int]:
    """考试大纲中该词的跨级标注（如 '1（4）' -> [4]）；无或未收录返回 []。"""
    exam = _load_exam().get(_normalize_word(word))
    return list(exam["cross"]) if exam and exam["cross"] else []


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 难度模型：以「难词占比」定级。
# 难词 = HSK 6 级及以上 + 权威词表未收录的字；对中高级学习者来说，
# 真正决定阅读难度的是这类词的密度，而不是全文的平均词级
# （「的/是/我」这类高频词会严重拉低平均值）。
_HARD_RATIO_BASE = 0.12   # 难词占比 12% 为最低档
_HARD_RATIO_STEP = 0.06   # 每多 6 个百分点升一级
_LEVEL_FLOOR = 5          # 本产品面向 HSK 5–9 学习者
_LEVEL_CEIL = 9
# 各等级字数上限：超出则上调一级，避免「词不难但读不完」
_LENGTH_CAP = {5: 800, 6: 1000, 7: 1200, 8: 1500, 9: 2000}


def grade_level(tokens: list, word_count: int | None = None) -> int:
    """按「难词占比」估算文章难度，输出 5-9。

    难词 = HSK 6 级及以上 或 权威词表未收录的单字。占比每增加 6 个百分点升一级，
    12% 对应最低档 5 级。最后做长度修正：字数超过该等级上限时上调一级。

    为什么不用「HSK 累积覆盖率 ≥ 95%」：近代白话作品（鲁迅、胡适等）的未收录字
    占 7%–28%，覆盖率几乎不可能达到 95%，会导致全部文章被压到同一档，失去区分度。
    """
    chars = [c for t in tokens for c in t["w"] if _CJK_RE.fullmatch(c)]
    if not chars:
        return config.DEFAULT_LEVEL

    levels = [word_level(c) for c in chars]
    hard_ratio = sum(1 for lv in levels if lv is None or lv >= 6) / len(chars)

    level = _LEVEL_FLOOR + int(max(0.0, hard_ratio - _HARD_RATIO_BASE) / _HARD_RATIO_STEP)
    level = min(max(level, _LEVEL_FLOOR), _LEVEL_CEIL)

    chars_total = word_count if word_count is not None else len(chars)
    while level < _LEVEL_CEIL and chars_total > _LENGTH_CAP.get(level, 10 ** 9):
        level += 1
    return level
