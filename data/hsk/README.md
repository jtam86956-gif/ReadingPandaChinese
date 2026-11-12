# HSK 3.0 词表

难度分级（`pipeline/nlp/grade.py`）依赖本目录的词表。词表**从官方标准自动抓取生成，非人工编造**。

## 文件说明

| 文件 | 内容 | 行数（唯一词） |
|---|---|---|
| `HSK1.txt` ~ `HSK6.txt` | 一级~六级词汇，每行一个词 | 497 / 767 / 967 / 995 / 1068 / 1136 |
| `HSK7.txt` | 高等（七—九级合并）词汇 | 5621 |
| `hsk30_full.tsv` | 全量原始数据：`序号\t级别\t词\t拼音\t词性`（11092 行，溯源用） | 11092 |
| `SOURCES.md` | 数据来源与授权说明 | — |

> 唯一词数略少于官方「词条数」，是因为官方词表中同一词在同级可能有多个词条
> （多音字/多义词，如「长 cháng/zhǎng」）。分级器只需词的集合归属，故去重；
> 完整词条（含拼音/词性）保留在 `hsk30_full.tsv`。

## 数据来源（权威）

1. 《国际中文教育中文水平等级标准》**GF 0025—2021**（教育部/国家语委，2021 发布）：
   共 11092 词，「三等九级」。
2. 汉考国际官方查询接口（新 HSK 词表）：
   `https://admin.chinesetest.cn/newhsk/standardsAction.do?means=getStandardWordsList`

详见 [SOURCES.md](SOURCES.md)。脚本抓取后会自动校验：总数 == 11092 且各级累积词条数与官方标准逐字一致，否则报错退出。

## 重新生成 / 更新

```bash
python3 scripts/fetch_hsk30.py
```

跑完会覆盖本目录所有文件并打印校验结果。若官方标准未来更新，重跑即可同步。

## 参考数据：HSK 3.0 考试大纲

`reference/` 目录下另有一份 **HSK 3.0《考试大纲》（2025-11，HSK Korea 发布）** 的解析结果，
作为**参考补充**，不参与主分级：

- `reference/hsk30_exam_syllabus.tsv`：11000 条，含独有的**跨级标注**（如 `1（4）`）。
- `reference/COMPARISON.md`：与主词表（GF 0025—2021）的对照分析与差异说明。
- `reference/raw/hsk30_exam_syllabus_korea.pdf`：原始 PDF 存档。
- 解析脚本：`scripts/parse_hsk30_exam_syllabus.py`（依赖 `pypdf`）。

⚠️ 两份文档的等级刻度不同（一级累积 500 vs 300），等级号不能直接横向比较，详见 `reference/COMPARISON.md`。

## 在流水线中的用法

- `grade.word_level(word)` 返回词的最低 HSK 级（1–7，7 = 高等），未收录返回 `None`。
- `grade.grade_level(tokens)` 输出文章难度（1–6，高等映射为 6），写入 `manifest.json` 的 `level` 字段。
- 词表缺失时降级到内置最小样本并打 warning（仅作兜底）。
