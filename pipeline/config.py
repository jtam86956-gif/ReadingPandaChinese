"""Panda News 内容流水线 —— 单一配置入口。

所有路径、信源、阈值集中在此，避免散落在各模块。
"""
from __future__ import annotations

from pathlib import Path

# --- 仓库根 / 输出目录 ---
ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
DATA_DIR = ROOT / "data"
SCHEMA_DIR = ROOT / "schema"

# --- 内容信源 ---
# 内容红线（PRD v0.3）：只接入**公版或自有**内容，代码只做抓取与原样展示，
# 不改写、不附加任何生成式释义或注释。非公版来源（商业新闻、政府媒体）一律不接入。
SOURCES = [
    {
        "id": "wikisource",
        "name": "维基文库·公版书",
        "type": "wikisource",
        "category": "文学",
        "enabled": True,
    },
]

# --- 抓取 ---
FETCH_TIMEOUT = 30           # 秒
MAX_ARTICLES_PER_RUN = 5     # 每次流水线最多处理几篇（M0 验证用小量）
USER_AGENT = "PandaNewsBot/0.1 (+https://github.com/panda-news)"

# --- NLP 分级 ---
# 无 HSK 词表时的兜底等级（data/hsk 缺失时使用，并打 warning）
DEFAULT_LEVEL = 3

# --- manifest schema 校验（默认开启）---
VALIDATE_MANIFEST = True
