# Panda News · 内容仓库（panda-news-content）

> 「通过阅读真实中文资讯学习中文」——内容生产与分发的单一事实源。
> 借鉴 [`hehonghui/awesome-english-ebooks`](https://github.com/hehonghui/awesome-english-ebooks)
> 的「内容流水线 + Git 分发」模式，把语言加工环节替换为中文 NLP。

配套文档：[产品 PRD](docs/PRD.md) ｜ [技术选型](docs/TECH-STACK.md)

---

## 这是什么

一个**定时运行的内容流水线**：每天抓取**公版中文内容**（维基文库公版书）→ 做中文 NLP 加工
（繁简统一、注音、分词、词性、难度分级）→ 输出结构化的 `manifest.json` →
提交到本仓库 → 阅读器 App 从仓库消费。

仓库本身就是产品：`content/` 是货架，`content/catalog.json` 是目录 API，
`schema/manifest.schema.json` 是内容契约。

> 当前为 **M0 骨架**：已跑通「公版内容抓取 → 加工 → manifest 落盘 → catalog 重建」。
> 内容红线：只抓公版/自有内容，只做原样展示，不生成释义、不做整句翻译、不接外部词典。
> epub 生成、TTS 音频为占位能力，见 `pipeline/convert/`、`pipeline/tts/`。

---

## 目录结构

```
.
├── pipeline/                  # 内容流水线代码
│   ├── config.py              # 单一配置（信源、路径、阈值）
│   ├── pipeline.py            # 编排入口（CLI）
│   ├── manifest.py            # manifest 构建 / 校验 / 落盘
│   ├── recipes/wikisource_recipe.py  # 维基文库公版书抓取 + 节选
│   ├── nlp/                   # 中文 NLP：注音/分词/分级/繁简/分句
│   ├── convert/epub.py        # 【占位】epub 生成（Calibre）
│   └── tts/audio.py           # 【占位】TTS 音频（edge-tts → R2）
├── content/                   # 产物（单一事实源）
│   ├── <source>/<date>/<id>/manifest.json
│   └── catalog.json           # 全量目录（阅读器发现页数据源）
├── data/                      # 词表 / 词典（按需补充）
│   ├── hsk/                   # HSK1-6 词表
│   └── cedict/                # 【占位】极简本地释义词表（不接外部词典）
├── schema/manifest.schema.json # manifest 契约
├── .github/workflows/daily.yml # 每日定时流水线
├── requirements.txt
└── docs/                      # PRD + 技术选型
```

---

## 快速开始

```bash
# 1. 安装依赖
python3 -m pip install -r requirements.txt

# 2. 跑一次（抓 1 篇验证）
python3 -m pipeline.pipeline run-today --limit 1

# 3. 只重建目录
python3 -m pipeline.pipeline rebuild-catalog
```

成功后会生成：
- `content/<source>/<date>/<id>/manifest.json` — 单篇结构化数据
- `content/catalog.json` — 全量文章目录

---

## manifest.json 是什么

每篇文章一个 `manifest.json`，是阅读器的直接数据源。包含：
- 标题、来源、原文链接、发布日期、难度等级（HSK 1-9）、分类、字数
- `content[]`：逐句的「原文 + 拼音 + 分词(含词性/HSK 级) + 分句音频」
- `new_vocab[]`：本文潜在生词

完整结构见 [schema/manifest.schema.json](schema/manifest.schema.json)。

---

## 内容合规

- 优先使用**公有领域**内容（公版经典）与**公开 RSS**（BBC 中文等）。
- 每篇保留 `source` 与 `source_url` 署名；不抓取付费墙内容。
- 音频、大文件不进 Git，走对象存储（R2），`manifest` 只存 URL。
- 详见 [PRD §6.1](docs/PRD.md) 与 [TECH-STACK §9](docs/TECH-STACK.md)。

---

## 路线图

| 阶段 | 状态 | 交付 |
|---|---|---|
| M0 内容流水线验证 | ✅ | RSS 抓取 + 中文 NLP 加工 → manifest.json + catalog.json |
| M1 MVP 阅读器 | ⬜ | Web 阅读器消费 manifest：点字拼音/释义、整句翻译、注音开关 |
| M2 生词本 + SRS | ⬜ | 生词本、间隔重复复习、账户同步 |
| M3 内容扩充 + AI | ⬜ | 公版经典、分级短文、TTS 音频、AI 句子讲解、搜索 |
