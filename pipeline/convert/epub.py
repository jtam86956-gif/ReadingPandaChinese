"""epub 生成（M0 占位 / 可选能力）。

规划（对应 TECH-STACK §3.4）：
- 用 Calibre `ebook-convert` 把 manifest 转成带注音 CSS 的 epub，供第三方阅读器
  （多看 / Kindle）使用，与 App 内的 JSON 渲染互为补充。
- 需先 `pip install` 流水线依赖 + 系统安装 calibre（`brew install calibre` 或
  `apt-get install calibre`）。
- 生成的 epub 体积较小可进 Git；带图的大 epub 走 Git LFS / R2。

M0 不启用：App 直接消费 manifest.json，epub 留待有第三方阅读需求时接通。
"""
from __future__ import annotations

from pathlib import Path


def build_epub(manifest: dict, out_path: Path) -> Path:
    """把 manifest 转成 epub。M0 未实现，调用会抛错并给出接通指引。"""
    raise NotImplementedError(
        "epub 生成尚未接通。计划：用 Calibre ebook-convert 生成带注音 CSS 的 epub。"
        "系统需安装 calibre（brew install calibre）。详见 TECH-STACK.md §3.4。"
    )
