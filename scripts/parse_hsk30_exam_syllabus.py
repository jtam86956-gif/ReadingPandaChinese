"""解析 HSK 3.0 考试大纲 PDF（HSK Korea 2025-11 版），提取词汇与跨级标注。

输入：data/hsk/reference/raw/hsk30_exam_syllabus_korea.pdf
输出：data/hsk/reference/hsk30_exam_syllabus.tsv
      （序号\t主级\t跨级\t词语\t拼音\t词性，主级为 1-7，跨级如 "2,4"）

说明：本数据为「考试大纲」（实际考试范围），与已导入的 GF 0025-2021《等级标准》
是两份不同文档，此处仅作参考补充，不替换主词表。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "hsk" / "reference" / "raw" / "hsk30_exam_syllabus_korea.pdf"
OUT = ROOT / "data" / "hsk" / "reference" / "hsk30_exam_syllabus.tsv"

CJK = r"\u4e00-\u9fff"
# 等级：纯数字(7) / 范围(7-9) / 跨级标注(1（4）, 2（7-9）, 1（2）（4）)
_LVL = r"\d+(?:[-—]\d+)?(?:（\d+(?:[-—]\d+)?）)*"
# 一行词表：序号 等级 词语 [拼音 词性]，用前瞻定位下一行开头来吃掉折行
ROW_RE = re.compile(
    rf"(?<!\d)(\d+)\s+"        # 序号前不能是数字（避免匹配长数字中段）
    rf"({_LVL})\s+"
    rf"(?=\S*[{CJK}])([{CJK}\d（）]+)\s+"  # 词语必须含汉字，可带数字/全角括号
    rf"(.*?)"
    # 下一行开头：序号前只要不是数字即可（折行时可能紧跟 "）" 无空格）
    rf"(?=(?<!\d)\d{{1,5}}\s+{_LVL}\s+[{CJK}]|$)",
    re.S,
)
LEVEL_RE = re.compile(r"(\d+)")


def _clean_page(text: str) -> str:
    """去掉每页的页眉/页脚/水印，只留词表正文行。"""
    text = text.replace("汉考国际", "")
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s in ("序号 等级 词语 拼音 词性", "词汇大纲"):
            continue
        if set(s) <= {"-", " "}:  # 分隔线
            continue
        if re.fullmatch(r"\d+", s):  # 页脚孤立页码
            continue
        lines.append(ln)
    return "\n".join(lines)


def parse() -> list[tuple]:
    from pypdf import PdfReader

    reader = PdfReader(str(RAW))
    full = []
    for page in reader.pages:
        full.append(_clean_page(page.extract_text() or ""))
    text = "\n".join(full)
    # 词汇表从首行「1 1 爱」开始（目录里虽有「汉字大纲」但在它之前），
    # 到其后第一个「汉字大纲」章节标题结束，避免后续章节污染最后一行
    vstart = text.find("1 1 爱")
    if vstart < 0:
        vstart = 0
    vend = text.find("汉字大纲", vstart)
    text = text[vstart:vend] if vend > vstart else text[vstart:]

    rows = []
    for m in ROW_RE.finditer(text):
        no, level_raw, word, rest = m.groups()
        no = int(no)
        # 等级拆成主级 + 跨级；纯范围如 "7-9" 是高等 band 标签，不算跨级
        nums = [int(x) for x in LEVEL_RE.findall(level_raw)]
        primary = nums[0]
        cross = [] if re.fullmatch(r"\d+[-—]\d+", level_raw) else nums[1:]
        # 拼音 / 词性：词性必以汉字开头，拼音全是非汉字；
        # 折行产生的换行要折叠成空格，否则破坏 TSV 列对齐
        first_cjk = re.search(rf"[{CJK}]", rest)
        if first_cjk:
            pinyin = _norm_ws(rest[: first_cjk.start()])
            pos = _norm_ws(rest[first_cjk.start():])
        else:
            pinyin = _norm_ws(rest)
            pos = ""
        rows.append((no, primary, cross, word, pinyin, pos))
    return rows


def _norm_ws(s: str) -> str:
    """折叠换行/多空格为单空格并去首尾空白，保证 TSV 单行。"""
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    if not RAW.exists():
        print(f"缺少原始 PDF：{RAW}", file=sys.stderr)
        return 1
    rows = parse()
    print(f"解析到 {len(rows)} 条词汇")

    # 校验：序号应连续 1..N
    nos = [r[0] for r in rows]
    expected = list(range(1, len(rows) + 1))
    seq_ok = nos == expected
    print(f"序号连续 1..{len(rows)}：{'✓' if seq_ok else '✗（有缺失/重复）'}")
    if not seq_ok:
        missing = sorted(set(expected) - set(nos))
        dup = [n for n in set(nos) if nos.count(n) > 1]
        if missing:
            print(f"  缺失序号（前20）：{missing[:20]}")
        if dup:
            print(f"  重复序号（前20）：{dup[:20]}")

    # 主级分布
    from collections import Counter
    c = Counter(r[1] for r in rows)
    print("主级分布（累积）：")
    cum = 0
    for lv in sorted(c):
        cum += c[lv]
        print(f"  级 {lv}：+{c[lv]}（累积 {cum}）")

    # 跨级标注统计
    cross_rows = [r for r in rows if r[2]]
    print(f"含跨级标注的词：{len(cross_rows)} 条")
    print("  样例：", [(r[0], r[1], r[2], r[3]) for r in cross_rows[:6]])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        f.write("no\tprimary\tcross\tword\tpinyin\tpos\n")
        for no, primary, cross, word, pinyin, pos in rows:
            f.write(f"{no}\t{primary}\t{','.join(map(str, cross))}\t{word}\t{pinyin}\t{pos}\n")
    print(f"\n已写入 {OUT.relative_to(ROOT)}")
    return 0 if seq_ok else 2


if __name__ == "__main__":
    sys.exit(main())
