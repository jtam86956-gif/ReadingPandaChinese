"""manifest.json 构建、校验与落盘。

manifest 是内容仓库的核心契约（见 schema/manifest.schema.json）。
本模块只负责「原始文章 -> 结构化 manifest -> 写文件」，不关心抓取与调度。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pipeline import config
from pipeline.nlp import grade, normalize, pinyin, sentence, tokenize

log = logging.getLogger(__name__)

_NON_CJK_RE = re.compile(r"[\s，。！？；：、“”‘’（）《》〈〉\[\]()""'.,!?;]")
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")  # CJK 统一表意文字


def _has_cjk(word: str) -> bool:
    """是否含至少一个汉字（用于过滤英文/数字/标点等噪音 token）。"""
    return bool(_HAS_CJK_RE.search(word))


def _word_count(text: str) -> int:
    """粗略字数：去掉空白与常见标点后的字符数。"""
    return len(_NON_CJK_RE.sub("", text))


def build_manifest(raw: dict, source_id: str, seq: int) -> dict:
    """把一篇原始文章加工成符合 schema 的 manifest 字典。"""
    title = normalize.to_simplified(raw["title"])
    body = normalize.to_simplified(raw["body"])
    sentences = sentence.split_sentences(body)

    content = []
    all_tokens = []
    for idx, s in enumerate(sentences, start=1):
        toks = tokenize.tokenize(s)
        for t in toks:
            t["hsk"] = grade.word_level(t["w"])
            cross = grade.word_cross_levels(t["w"])
            if cross:
                t["cross"] = cross
            t.setdefault("meaning", None)
            all_tokens.append(t)
        content.append({
            "sentence_id": f"s{idx}",
            "text": s,
            "pinyin": pinyin.to_pinyin(s),
            "translation": None,        # 不生成译文，保持原文
            "audio_url": None,          # M0 占位：接 TTS 后填充
            "tokens": toks,
        })

    word_count = _word_count(body)
    level = grade.grade_level(all_tokens, word_count)
    new_vocab = _collect_new_vocab(all_tokens, level)

    return {
        "id": f"{source_id}_{raw['published_at'].replace('-', '')}_{seq:03d}",
        "title": title,
        "source": raw["source"],
        "source_url": raw["source_url"],
        "published_at": raw["published_at"],
        "level": level,
        "category": raw.get("category", "时事"),
        "tags": [],
        "word_count": word_count,
        "audio_url": None,
        "content": content,
        "new_vocab": new_vocab,
    }


# 人名/地名/专名/非语素/英文不作为生词收录：学习者不需要记音译人名
_SKIP_POS = {"nr", "ns", "nz", "x", "eng"}
# 生词判定的最低门槛：4 级以下的词不列为生词
_MIN_NEW_LEVEL = 4


def _chars_all_known(word: str, max_level: int) -> bool:
    """未收录的复合词按单字拆解：每个字都是已知词且不超过阈值，视为可理解。

    jieba 会把「一个」「别处」这类高频组合切成整词，而 HSK 词表只收了「一」「个」，
    若不拆字判断，这些常用组合会被误当成生词。
    """
    if len(word) < 2:
        return False
    levels = []
    for ch in word:
        if not _HAS_CJK_RE.search(ch):
            continue
        lv = grade.word_level(ch)
        if lv is None:
            return False
        levels.append(lv)
    return bool(levels) and max(levels) <= max_level


def _collect_new_vocab(tokens: list, level: int) -> list:
    """收集「潜在生词」：超出当前等级的已知词，或真正难以由已知成分解释的词。

    过滤三类噪音：人名/地名等专名、纯标点/英文、以及能由已知单字组合理解的词
    （如「一个」「别处」）。
    """
    threshold = max(level, _MIN_NEW_LEVEL)
    seen = set()
    out = []
    for t in tokens:
        w = t["w"]
        if w in seen or not _has_cjk(w):
            continue
        if len(w) < 2:
            # 只收词、不收字：单个汉字多为词内成分或异体字（淸/靑/煑），
            # 列进生词本没有学习价值，单字理解交给注音即可
            continue
        if (t.get("pos") or "") in _SKIP_POS:
            continue
        hsk = t.get("hsk")
        if hsk is None:
            is_new = not _chars_all_known(w, threshold)
        else:
            is_new = hsk >= threshold
        if not is_new:
            continue
        seen.add(w)
        entry = {"w": w, "hsk": hsk, "meaning": None, "example": None}
        if t.get("cross"):
            entry["cross"] = t["cross"]  # 考试大纲跨级标注，供阅读器标记「多级复现词」
        out.append(entry)
    return out[:40]  # M0 限制数量，避免过长


def validate(manifest: dict) -> bool:
    """用 schema 校验 manifest；失败仅记日志（不阻断，便于排查）。"""
    if not config.VALIDATE_MANIFEST:
        return True
    try:
        import jsonschema
        schema_path = config.SCHEMA_DIR / "manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(manifest, schema)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("manifest 校验失败 %s：%r", manifest.get("id"), e)
        return False


def write_manifest(manifest: dict, source_id: str) -> Path:
    """落盘到 content/<source_id>/<date>/<id>/manifest.json，返回路径。"""
    date = manifest["published_at"]
    out_dir = config.CONTENT_DIR / source_id / date / manifest["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("写入 %s", path.relative_to(config.ROOT))
    return path
