#!/usr/bin/env python3
"""一次性数据导入：从汉考国际官方接口抓取 HSK 3.0 词汇大纲，生成分级词表。

数据来源（权威）：
  - 《国际中文教育中文水平等级标准》GF 0025—2021（教育部/国家语委，2021 发布）
  - 官方查询接口：https://admin.chinesetest.cn/newhsk/standardsAction.do
    字段：No. / 级别 / 词语 / 拼音 / 词性，共 11092 条，按拼音排序。

产出：
  data/hsk/HSK{1..7}.txt   每级一个词表（每行一个词，按官方拼音序），供 grade.py 加载
  data/hsk/hsk30_full.tsv  全量原始数据（序号\\t级别\\t词\\t拼音\\t词性），留作溯源

级别映射：一级→1 … 六级→6，高等（七—九级合并）→7。
校验：抓取总数必须 == 11092，各级数量必须与官方标准累积量一致，否则报错退出。

用法：
  python3 scripts/fetch_hsk30.py
"""
from __future__ import annotations

import re
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "hsk"

BASE = "https://admin.chinesetest.cn/newhsk/standardsAction.do?means=getStandardWordsList&pager.offset={offset}"
TOTAL = 11092            # 官方公布总词数
PAGE_SIZE = 10
UA = "PandaNewsBot/0.1 (open-source learning tool; data import from official public standard)"

# 官方标准公布的各级「累积」词汇量（用于校验）
EXPECTED_CUMULATIVE = {1: 500, 2: 1272, 3: 2245, 4: 3245, 5: 4316, 6: 5456, 7: 11092}

LEVEL_MAP = {"一级": 1, "二级": 2, "三级": 3, "四级": 4, "五级": 5, "六级": 6, "高等": 7}

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TOTAL_RE = re.compile(r"共有\s*(\d+)\s*条")


def _clean(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def fetch_page(offset: int, retries: int = 3) -> str:
    url = BASE.format(offset=offset)
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(1.0 + random.random())
    return ""


def parse_page(html: str):
    """返回 [(no:int, level:int, word:str, pinyin:str, pos:str), ...]。"""
    rows = []
    for raw in ROW_RE.findall(html):
        cells = CELL_RE.findall(raw)
        if len(cells) < 4:
            continue
        cells = [_clean(c) for c in cells]
        if cells[0] in ("No.", "") or not cells[0].isdigit():
            continue
        try:
            no = int(cells[0])
        except ValueError:
            continue
        level_cn = cells[1]
        if level_cn not in LEVEL_MAP:
            # 跳过未知级别，但记录一下
            continue
        rows.append((no, LEVEL_MAP[level_cn], cells[2], cells[3], cells[4] if len(cells) > 4 else ""))
    return rows


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    offsets = list(range(0, TOTAL, PAGE_SIZE))
    print(f"开始抓取：{len(offsets)} 页，预期 {TOTAL} 条 …")

    all_rows: list[tuple] = []
    seen_pages = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_page, off): off for off in offsets}
        for fut in as_completed(futures):
            off = futures[fut]
            try:
                html = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ offset={off} 失败：{e!r}", file=sys.stderr)
                continue
            rows = parse_page(html)
            if not rows:
                m = TOTAL_RE.search(html)
                total = int(m.group(1)) if m else "?"
                print(f"  ! offset={off} 解析到 0 行（页面总记录显示 {total}）", file=sys.stderr)
                continue
            all_rows.extend(rows)
            seen_pages += 1
            if seen_pages % 100 == 0:
                print(f"  进度：{seen_pages}/{len(offsets)} 页，累计 {len(all_rows)} 行")
            time.sleep(0.05)  # 全局轻微节流

    # 校验总数
    all_rows.sort(key=lambda r: r[0])
    print(f"抓取完成：{len(all_rows)} 条（预期 {TOTAL}）")
    if len(all_rows) != TOTAL:
        print(f"✗ 总数不匹配！缺 {TOTAL - len(all_rows)} 条，退出。", file=sys.stderr)
        return 1

    # 校验 1：各级【词条数】累积必须与官方标准完全一致（完整性判据）
    entry_count: dict[int, int] = {i: 0 for i in range(1, 8)}
    for _no, level, _w, _py, _p in all_rows:
        entry_count[level] += 1

    cum = 0
    entries_ok = True
    print("\n级别【词条数】校验（与官方标准累积量对比，完整性判据）：")
    for level in range(1, 8):
        cum += entry_count[level]
        exp = EXPECTED_CUMULATIVE[level]
        mark = "✓" if cum == exp else "✗"
        if cum != exp:
            entries_ok = False
        label = "高等(7-9)" if level == 7 else f"{level}级"
        print(f"  {mark} {label:>8}: 本级 {entry_count[level]:>5}  累积 {cum:>6}  (官方 {exp:>6})")

    # 去重得到分级词表（同词同级多义项只保留一个；分级器只需要词的集合归属）
    by_level: dict[int, list[str]] = {i: [] for i in range(1, 8)}
    seen_word_level: set[tuple[str, int]] = set()
    for _no, level, word, _py, _pos in all_rows:
        key = (word, level)
        if key in seen_word_level:
            continue
        seen_word_level.add(key)
        by_level[level].append(word)

    # 信息展示：去重后唯一词数（会略少于词条数，因多音字/多义词）
    print("\n级别【唯一词数】（写入 HSKn.txt，略少于词条数为正常）：")
    for level in range(1, 8):
        label = "高等(7-9)" if level == 7 else f"{level}级"
        print(f"  {label:>8}: {len(by_level[level]):>5} 唯一词  "
              f"(词条 {entry_count[level]:>5}, 同词多义 {entry_count[level] - len(by_level[level])})")

    if not entries_ok:
        print("\n✗ 各级词条数与官方标准不一致，请人工核对后再使用。", file=sys.stderr)
        return 2
    print("\n✓ 数据完整性校验通过：总数与各级词条数均与官方标准一致。")

    # 写分级词表（每行一个词，保持官方拼音序）
    for level, words in by_level.items():
        name = "HSK7.txt" if level == 7 else f"HSK{level}.txt"
        (OUT_DIR / name).write_text("\n".join(words) + "\n", encoding="utf-8")
    # 写全量溯源 TSV
    with (OUT_DIR / "hsk30_full.tsv").open("w", encoding="utf-8") as f:
        f.write("no\tlevel\tword\tpinyin\tpos\n")
        for no, level, word, py, pos in all_rows:
            f.write(f"{no}\t{level}\t{word}\t{py}\t{pos}\n")
    # 出处说明
    (OUT_DIR / "SOURCES.md").write_text(
        "# HSK 3.0 词表数据来源\n\n"
        "本目录词表由 `scripts/fetch_hsk30.py` 从以下官方来源自动抓取生成，非人工编造：\n\n"
        "1. 《国际中文教育中文水平等级标准》GF 0025—2021（中华人民共和国教育部、国家语言文字工作委员会，2021-03-24 发布，2021-07-01 实施）。\n"
        "   PDF：https://www.moe.gov.cn/jyb_sjzl/ziliao/A19/202111/W020211118507389477190.pdf\n"
        "2. 汉考国际官方查询接口（新 HSK 词表）：\n"
        "   https://admin.chinesetest.cn/newhsk/standardsAction.do?means=getStandardWordsList\n\n"
        "共 11092 条，按「三等九级」分级：一级~六级各自独立，七~九级合并为「高等」(HSK7.txt)。\n"
        "用途：为 Panda News 阅读材料做难度分级与生词标注。数据为事实性参考信息，\n"
        "本工具不声称等同于官方考试，引用时请保留本出处说明。\n"
        f"\n生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )

    print(f"\n已写入 {OUT_DIR.relative_to(ROOT)}/ 下：HSK1-7.txt + hsk30_full.tsv + SOURCES.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
