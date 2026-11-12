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
            "translation": None,        # M0 占位：接词典/LLM 后填充
            "audio_url": None,          # M0 占位：接 TTS 后填充
            "tokens": toks,
        })

    level = grade.grade_level(all_tokens)
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
        "word_count": _word_count(body),
        "audio_url": None,
        "content": content,
        "new_vocab": new_vocab,
    }


def _collect_new_vocab(tokens: list, level: int) -> list:
    """收集「潜在生词」：HSK 未收录 或 等级 >= 当前文章等级 的词，去重。"""
    seen = set()
    out = []
    for t in tokens:
        w = t["w"]
        if w in seen:
            continue
        if len(w) < 1:
            continue
        is_new = t.get("hsk") is None or (t.get("hsk") or 0) >= max(level, 4)
        if is_new and _has_cjk(w):  # 只收含汉字的词，剔除 Author / 标点等噪音
            seen.add(w)
            entry = {"w": w, "hsk": t.get("hsk"), "meaning": None, "example": None}
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
