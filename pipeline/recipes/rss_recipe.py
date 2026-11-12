"""RSS 信源抓取 + 正文提取。

对应 awesome-english-ebooks 的 Calibre news recipe 角色，但这里走更轻量的
feedparser + trafilatura，便于在 GitHub Actions 里无 Calibre 运行（M0）。
每个信源的 recipe 最终产出「原始文章」列表，交给 pipeline 做 NLP 加工。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import feedparser
import trafilatura

from pipeline import config

log = logging.getLogger(__name__)


def fetch_feed(source: dict, limit: int) -> list[dict]:
    """抓取一个 RSS 信源，返回最多 limit 篇原始文章。

    每篇结构：
      {title, url, source, source_url, published_at, body}
    单篇失败不影响其他篇。
    """
    articles = []
    log.info("抓取信源：%s (%s)", source["name"], source["feed"])
    feed = None
    for attempt in range(2):  # 应对瞬时网络/SSL 抖动
        feed = feedparser.parse(source["feed"])
        if not feed.bozo or feed.entries:
            break
        log.warning("信源解析重试 %d/2：%s", attempt + 1, source["name"])
        time.sleep(2)
    if feed is None or (feed.bozo and not feed.entries):
        log.error("信源解析失败：%s", source["name"])
        return articles

    for entry in feed.entries[:limit]:
        try:
            url = entry.get("link")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue
            body = _extract_body(url)
            if not body:
                log.warning("正文提取为空，跳过：%s", title)
                continue
            published = _parse_date(entry)
            articles.append({
                "title": title,
                "url": url,
                "source": source["name"],
                "source_url": url,
                "published_at": published,
                "category": source.get("category", "时事"),
                "body": body,
            })
        except Exception as e:  # noqa: BLE001 — 单篇容错
            log.warning("处理单篇失败 %s：%r", entry.get("link"), e)
    log.info("信源 %s 取得 %d 篇", source["name"], len(articles))
    return articles


def _extract_body(url: str) -> str:
    """用 trafilatura 提取正文纯文本。"""
    # trafilatura 2.x 的 fetch_url 不接受 timeout 关键字；超时走默认配置。
    # config.FETCH_TIMEOUT 保留给后续接入 requests 直连时使用。
    downloaded = trafilatura.fetch_url(
        url,
        config=trafilatura.settings.use_config(),
    )
    if not downloaded:
        return ""
    text = trafilatura.extract(
        downloaded,
        output_format="txt",
        include_comments=False,
        include_tables=False,
        no_fallback=True,
    )
    return (text or "").strip()


def _parse_date(entry) -> str:
    """从 entry 解析日期，失败则用今天。返回 YYYY-MM-DD。"""
    for key in ("published_parsed", "updated_parsed"):
        tp = entry.get(key)
        if tp:
            try:
                return datetime(*tp[:6]).strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                pass
    return datetime.now().strftime("%Y-%m-%d")
