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

# --- 内容信源（M0 先接 1-2 个合规公开 RSS；可在 data/sources.json 扩展）---
# 选型原则：公开 RSS、允许抓取、非付费墙。详见 PRD §6.1。
SOURCES = [
    {
        "id": "bbc_zh",
        "name": "BBC 中文",
        "feed": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "category": "时事",
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
