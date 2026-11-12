"""Panda News 内容流水线 —— 编排入口（最小闭环）。

M0 闭环：RSS 抓取 → 中文 NLP 加工 → 写出 manifest.json → 重建 catalog.json。
epub 转换 / TTS 音频为可选能力（见 convert / tts 模块），M0 不启用。

用法：
    python -m pipeline.pipeline run-today --limit 1
    python -m pipeline.pipeline run-today --limit 3 --source bbc_zh
    python -m pipeline.pipeline rebuild-catalog
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from pipeline import config, manifest
from pipeline.recipes import rss_recipe

log = logging.getLogger("pipeline")


def _setup_logging(verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _sources(source_id: str | None):
    if source_id:
        return [s for s in config.SOURCES if s["id"] == source_id and s.get("enabled", True)]
    return [s for s in config.SOURCES if s.get("enabled", True)]


def run_today(limit: int, source_id: str | None) -> int:
    sources = _sources(source_id)
    if not sources:
        log.error("没有可用信源（source=%s）", source_id)
        return 1

    written = 0
    today = datetime.now().strftime("%Y-%m-%d")
    for source in sources:
        articles = rss_recipe.fetch_feed(source, limit=limit)
        for seq, raw in enumerate(articles, start=1):
            try:
                m = manifest.build_manifest(raw, source["id"], seq)
                manifest.validate(m)
                manifest.write_manifest(m, source["id"])
                written += 1
            except Exception as e:  # noqa: BLE001 — 单篇容错
                log.exception("加工失败：%s — %r", raw.get("title"), e)

    rebuild_catalog()
    log.info("完成：日期=%s，新写入 manifest=%d", today, written)
    return 0 if written > 0 else 2


def rebuild_catalog() -> int:
    """扫描 content/ 下所有 manifest.json，重建 content/catalog.json。"""
    items = []
    for path in config.CONTENT_DIR.rglob("manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "id": data["id"],
                "title": data["title"],
                "source": data["source"],
                "published_at": data["published_at"],
                "level": data["level"],
                "category": data.get("category"),
                "word_count": data.get("word_count"),
                "path": str(path.relative_to(config.ROOT)),
            })
        except Exception as e:  # noqa: BLE001
            log.warning("跳过损坏的 manifest %s：%r", path, e)
    items.sort(key=lambda x: x["published_at"], reverse=True)
    catalog = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    out = config.CONTENT_DIR / "catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("重建 catalog：%d 篇 -> %s", len(items), out.relative_to(config.ROOT))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline", description="Panda News 内容流水线")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-today", help="抓取并加工今日内容")
    p_run.add_argument("--limit", type=int, default=config.MAX_ARTICLES_PER_RUN,
                       help="每个信源最多处理篇数（默认 %d）" % config.MAX_ARTICLES_PER_RUN)
    p_run.add_argument("--source", default=None, help="只跑指定信源 id")

    sub.add_parser("rebuild-catalog", help="只重建 content/catalog.json")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.cmd == "run-today":
        return run_today(args.limit, args.source)
    if args.cmd == "rebuild-catalog":
        return rebuild_catalog()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
