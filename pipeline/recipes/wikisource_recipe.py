"""维基文库公版书抓取。

内容红线（PRD v0.3）：只抓取**公版**内容，且**只做抓取与原样展示**——
不改写原文、不附加任何生成式释义或注释。

数据来源：中文维基文库（https://zh.wikisource.org），MediaWiki API。
收录作品均为作者逝世逾 50 年、进入公有领域的白话作品，逐篇校验：
  - 魯迅（1936 年逝世）
  - 朱自清（1948 年逝世）
  - 胡適（1962 年逝世）

产出：把每部作品按句子边界切分为 300–600 字的「节选」，每节选作为一篇
阅读材料交给 pipeline.manifest 加工（注音 / 分词 / HSK 分级）。
原文保持繁体，由 normalize.to_simplified 统一转简体。
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import time
import urllib.parse
from datetime import datetime
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

API = "https://zh.wikisource.org/w/api.php"
UA = "PandaNewsBot/0.1 (open-source Chinese learning reader; public-domain texts)"
TIMEOUT = 40
RETRIES = 4          # 429 限流是常态，需要足够退避
REQUEST_INTERVAL = 2.0  # 每次请求之间的间隔（秒）

# 已核实存在完整正文、且进入公有领域的作品（标题以维基文库实际页面为准）
# category 用于内容分类；文学与社科交替排列，保证每天取到的节选有题材差异。
WORKS = [
    {"title": "孔乙己", "author": "魯迅", "year": 1919, "category": "文学"},
    {"title": "敬告青年", "author": "陳獨秀", "year": 1915, "category": "社科"},
    {"title": "故鄉", "author": "魯迅", "year": 1921, "category": "文学"},
    {"title": "容忍與自由", "author": "胡適", "year": 1959, "category": "社科"},
    {"title": "阿Q正傳", "author": "魯迅", "year": 1921, "category": "文学"},
    {"title": "文學改良芻議", "author": "胡適", "year": 1917, "category": "社科"},
    {"title": "藥", "author": "魯迅", "year": 1919, "category": "文学"},
    {"title": "民報發刊詞", "author": "孫文", "year": 1905, "category": "社科"},
    {"title": "狂人日記", "author": "魯迅", "year": 1918, "category": "文学"},
    {"title": "祝福", "author": "魯迅", "year": 1924, "category": "文学"},
    {"title": "社戲", "author": "魯迅", "year": 1922, "category": "文学"},
    {"title": "一件小事", "author": "魯迅", "year": 1919, "category": "文学"},
    {"title": "背影", "author": "朱自清", "year": 1925, "category": "文学"},
    {"title": "差不多先生傳", "author": "胡適", "year": 1924, "category": "文学"},
]

MIN_LEN = 300
MAX_LEN = 600

_SENT_END = "。！？…"
_ZERO_WIDTH = "\u200b\ufeff\u200e\u200f"

# 页面头部/底部导航与版权模板，属页面元信息而非原文
_NOISE_PATTERNS = [
    re.compile(r"^←"),
    re.compile(r"^→$"),
    re.compile(r"^《[^》]*》$"),
    re.compile(r"作者[:：]"),
    re.compile(r"^本作品收錄於"),
    re.compile(r"姊妹计划"),
    re.compile(r"^版本信息$"),
    re.compile(r"^原載"),
    re.compile(r"^下文不是"),
    re.compile(r"^此版本取自"),
    re.compile(r"^另參見"),
    re.compile(r"^本文初刊"),
    re.compile(r"^\d{4}年\d{1,2}月"),
]


def _api(params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(RETRIES):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — 429/网络抖动统一重试
            last = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"维基文库请求失败：{last!r}")


def _to_text(html: str) -> str:
    """HTML -> 纯文本：去掉脚本/样式/表格/注脚/编辑链接/章节标题，保留正文换行。"""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = re.sub(r"<table.*?</table>", "", html, flags=re.S | re.I)
    html = re.sub(r"<h[1-6][^>]*>.*?</h[1-6]>", "\n", html, flags=re.S | re.I)
    html = re.sub(r'<span[^>]*class="mw-editsection"[^>]*>.*?</span>', "", html, flags=re.S | re.I)
    html = re.sub(r'<sup[^>]*class="reference"[^>]*>.*?</sup>', "", html, flags=re.S | re.I)
    html = re.sub(r"<(p|div|br|li)\b[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    text = _html.unescape(html)
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, "")
    # 编辑链接被拆成「[」「编辑」「]」三段，单独清洗后可能残留半截括号
    text = re.sub(r"[\[［]?\s*编辑\s*[\]］]", "", text)
    return text


def _clean(text: str) -> list:
    """按行清洗：去掉导航、版权模板、空行，返回正文段落列表。"""
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("　").strip()
        if not line:
            continue
        if any(p.search(line) for p in _NOISE_PATTERNS):
            continue
        lines.append(line)
    return lines


def _chunk(text: str, min_len: int = MIN_LEN, max_len: int = MAX_LEN) -> list:
    """把整篇正文按句子边界切成 [min_len, max_len] 的节选。"""
    sentences, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _SENT_END:
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())

    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) > max_len:
            chunks.append(cur)
            cur = ""
        cur += s
    if cur:
        chunks.append(cur)
    return [c for c in chunks if len(c) >= min_len]


def _fetch_work(work: dict) -> str:
    """拉取一部作品的正文纯文本。

    段落直接拼接（不加换行）：维基文库的换行只是排版，若当作句界会把
    一个完整句子切断，导致节选在句子中间收尾。
    """
    data = _api({"action": "parse", "page": work["title"], "prop": "text"})
    if "parse" not in data:
        raise RuntimeError("页面不存在或无法解析")
    text = "".join(_clean(_to_text(data["parse"]["text"])))

    # 页面正文开头常重复「标题 + 作者」（如「敬告靑年陈独秀窃以…」），去掉这段前缀
    idx = text.find(work["author"], 0, 40) if work.get("author") else -1
    if idx != -1:
        text = text[idx + len(work["author"]):]
    return text


def fetch(source: dict, limit: int = 5) -> list:
    """返回 raw 文章列表（每项可由 manifest.build_manifest 直接消费）。

    轮转策略：按当年第几天偏移起始作品，每次运行从不同作品开始取节选，
    避免连续多日重复同一篇。
    """
    today = datetime.now()
    day = today.timetuple().tm_yday

    def _rotate(items: list, k: int) -> list:
        if not items:
            return []
        k %= len(items)
        return items[k:] + items[:k]

    literature = _rotate([w for w in WORKS if w.get("category") == "文学"], day)
    social = _rotate([w for w in WORKS if w.get("category") == "社科"], day)

    # 文学、社科交替取，避免某天全是同一题材；某一类取完则用另一类补齐
    ordered = []
    li = si = 0
    while len(ordered) < limit and (li < len(literature) or si < len(social)):
        prefer_lit = len(ordered) % 2 == 0
        if prefer_lit and li < len(literature):
            ordered.append(literature[li]); li += 1
        elif not prefer_lit and si < len(social):
            ordered.append(social[si]); si += 1
        elif li < len(literature):
            ordered.append(literature[li]); li += 1
        elif si < len(social):
            ordered.append(social[si]); si += 1

    articles = []
    for work in ordered:
        if len(articles) >= limit:
            break
        try:
            text = _fetch_work(work)
        except Exception as e:  # noqa: BLE001 — 单篇失败不影响其它作品
            log.warning("跳过《%s》：%r", work["title"], e)
            continue

        chunks = _chunk(text)
        if not chunks:
            log.warning("《%s》未切出合格节选（正文过短）", work["title"])
            continue

        excerpt = chunks[0]
        articles.append({
            "title": f"{work['title']}（{work['author']}·节选）",
            "body": excerpt,
            "source": source.get("name", "维基文库·公版书"),
            "source_url": "https://zh.wikisource.org/wiki/" + urllib.parse.quote(work["title"]),
            "published_at": today.strftime("%Y-%m-%d"),
            "category": work.get("category", source.get("category", "文学")),
        })
        log.info("取到公版节选：《%s》%d 字", work["title"], len(excerpt))
        time.sleep(REQUEST_INTERVAL)  # 节流，避免 429

    return articles
