# Panda News（熊猫新闻）技术选型文档

> 配套《PRD.md》。目标：以最低冷启动成本搭出「内容流水线 + Git 分发 + Web 阅读器」，并为后续 App 与 AI 能力留好扩展位。
>
> 版本：v0.1｜日期：2026-11-12｜状态：草案

---

## 1. 设计原则与约束

1. **内容仓库 = 单一事实源（Single Source of Truth）**：所有内容产物（JSON 元数据、epub、音频索引）先写进 Git 仓库，App/服务都从仓库消费。这是从 awesome-english-ebooks 继承的核心模式。
2. **免费托管优先**：MVP 阶段尽量用 GitHub（仓库/raw/CDN）+ Cloudflare 免费层，把月度成本压到 ¥300 以内。
3. **本地优先，云端增强**：NLP 加工、词典释义尽量本地/离线完成（成本低、延迟低）；LLM 只用于「整句讲解」这种本地做不好的事，且按需触发 + 缓存。
4. **契约优先**：内容 manifest 有稳定 JSON schema，阅读器与后端按 schema 解耦，内容流水线可独立演进。
5. **规避 DMCA**：内容来源、抓取方式、存储位置都按合规设计（见 PRD §6.1 与本文 §9）。

---

## 2. 整体架构

```
┌───────────────────────────────────────────────────────────────────┐
│  内容生产流水线（定时任务，GitHub Actions / NAS）                  │
│  源站 RSS ─▶ Calibre 抓取 ─▶ 中文 NLP 加工 ─▶ 翻译/TTS ─▶ 多格式  │
└───────────────┬───────────────────────────────────────────────────┘
                │ git commit & push
                ▼
┌───────────────────────────────────────────────────────────────────┐
│  内容仓库（Git）  —— 单一事实源                                    │
│  按 日期/等级/分类 组织；每篇 = manifest.json + .epub + 音频索引    │
│  大文件 → Git LFS / 对象存储（R2）；小文件 + 元数据进 Git          │
└───────┬───────────────────────────────┬───────────────────────────┘
        │ raw / CDN                       │ 同步构建索引
        ▼                                 ▼
┌──────────────────────┐      ┌────────────────────────────────────┐
│  CDN / 对象存储      │      │  索引服务（Meilisearch）            │
│  大文件分发          │      │  词典 + 全文检索 + 文章检索          │
└──────────┬───────────┘      └───────────────┬────────────────────┘
           │                                  │
           ▼                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│  后端 BFF（薄）：Cloudflare Workers / FastAPI                      │
│  列目录 · 取文章 · 查词 · 全文检索 · AI 讲解（代理 LLM）· 同步      │
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTPS / JSON
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│  客户端：Web 阅读器（Next.js）→ 后续 iOS/Android                   │
│  沉浸式阅读 · 点字/点词 · 注音 · 翻译 · 朗读 · 生词本 · SRS · 统计  │
│  本地存储（IndexedDB / SQLite）优先，云端同步增强                  │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. 内容生产流水线

借鉴 awesome-english-ebooks 的「Calibre + 定时任务」模式，但把语言加工从「纯格式转换」升级为「中文 NLP 加工」。

### 3.1 运行环境与调度
| 选项 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **GitHub Actions（定时）** | 全在仓库内、免费 2000 分钟/月、无需自备机器 | 单次运行有时长限制（6h）、私有依赖需 secret | ✅ **MVP 首选**：流水线轻量，够用 |
| 群晖 NAS / 本地 cron | 不占 Actions 额度、可跑重任务、私密 | 需自备机器、网络依赖家里 | 备选：音频批量生成/大任务时用 |
| 云服务器（cron） | 稳定 | 要钱 | 留待规模化 |

**MVP 方案**：用 GitHub Actions 的 `schedule` 触发，每日跑一次新闻抓取；TTS 音频生成较重，放到 NAS 或周末 Actions 跑（免费额度内）。

### 3.2 抓取层
| 任务 | 选型 | 说明 |
|---|---|---|
| 新闻 RSS 抓取 | **Calibre news recipe**（`*.recipe`）或 `feedparser` + `readability` | 沿用 awesome 模式。Calibre recipe 适合「整期杂志/站点」；单篇 RSS 用 feedparser 更灵活 |
| 正文提取 | `trafilatura` 或 `readability-lxml` | 比 BeautifulSoup 手写规则稳，自动去广告/导航 |
| 公版书获取 | 维基文库 API / 中文电子书（自备） | 公有领域，直接入库 |
| 去重 | 按 `source_url` 哈希 + 标题相似度 | 避免同一篇重复入库 |

> 关键：Calibre 的 `BasicNewsRecipe` 框架天然支持「RSS 列表 → 逐篇抓正文 → 合成一本电子书」，为每个新闻源写一个 recipe 即可，是 awesome 项目的心脏，直接复用。

### 3.3 中文 NLP 加工层（本产品差异化核心）
| 能力 | 选型 | 版本/说明 | 替代 |
|---|---|---|---|
| **注音（拼音带声调）** | **pypinyin** | `lazy_pinyin(..., style=TONE)`；准确率高，离线 | xpinyin（较弱） |
| **分词 + 词性** | **jieba**（`jieba.posseg`）或 **pkuseg** | jieba 生态成熟、词库多；pkuseg 准确率更高但慢 | HanLP（重） |
| **繁简转换** | **OpenCC**（`opencc-python-reimplemented`） | 文章统一存简体，阅读时按需转繁体 | — |
| **难度分级** | 自实现：HSK 词表 + 字频表（`jieba` 分词后统计） | 计算 HSK 各级覆盖率、平均句长、生僻字占比 → 映射 1–6 级 | 可用 LLM 打分作为校验 |
| **整句翻译** | 本地词典拼接 + **LLM（DeepSeek / GPT-4o-mini / 通义千问）** | 简单句本地拼；难句调 LLM，结果缓存 | 谷歌翻译 API（付费） |
| **词典数据** | **CC-CEDICT**（开源英汉词典，免费商用） | 加载为本地 SQLite/JSON，点词查义走它，零成本 | 汉典、百度汉语 API |
| **笔顺数据** | **hanzi-writer-data**（开源，~9k 字） | 前端 `hanzi-writer` 消费，做笔顺动画 | 小学堂（更全但需授权） |
| **TTS 音频** | **edge-tts**（免费，微软 Edge 语音）MVP / **Azure TTS**（付费，质量高）后期 | edge-tts 免费、质量已不错；Azure 有更自然的神经语音 + 分句时间戳 | 阿里云 TTS |

**加工流水线（单篇）伪代码**：
```python
article = fetch_rss_and_extract(url)          # 标题、正文、来源、日期
sentences = split_sentences(article.body)     # 按。！？；分段分句
for s in sentences:
    s.pinyin = pypinyin(s.text, style=TONE)   # 注音
    s.tokens = jieba.posseg(s.text)            # 分词+词性
    s.translation = translate(s.text)         # 本地拼 or LLM（缓存）
    s.audio = tts(s.text)                     # edge-tts
article.level = grade_level(article)          # HSK 覆盖率 + 句长
article.new_vocab = extract_new_vocab(article) # 超出用户等级的词
write_json(article)                           # manifest.json
convert_epub(article)                         # 带注音 CSS 的 epub
git_commit_push(article)
```

### 3.4 格式产物
| 产物 | 用途 | 生成工具 | 是否进 Git |
|---|---|---|---|
| `manifest.json` | App 直接消费的结构化数据（句子+拼音+分词+翻译+音频） | 流水线脚本 | ✅ 进 Git（核心） |
| `article.epub` | 第三方阅读器兼容（多看/Kindle），带注音 CSS | Calibre `ebook-convert` + 自定义 CSS | ✅ 进 Git（小，~数十 KB） |
| `article.pdf` | 打印/分享 | Calibre / WeasyPrint | ⚠️ 可选，放对象存储 |
| `audio/*.mp3` | 整篇 + 分句朗读 | edge-tts / Azure | ⚠️ 放对象存储（R2），Git 只存 `audio_url` |
| `index/` | 供 Meilisearch 的批量导入 JSON | 流水线脚本 | ✅ 进 Git |

> **仓库体积控制**：`manifest.json` 每篇几 KB–几十 KB，一年 365 篇也就几十 MB，完全可控。真正大的是音频（每篇几 MB）——音频绝不进 Git，放 R2，Git 里只存 URL。epub 若带图可能大，走 Git LFS 或也放对象存储。

---

## 4. 存储与分发

### 4.1 Git 内容仓库
- **结构**（单一仓库 `panda-news-content`）：
  ```
  content/
  ├── news/
  │   └── 2026/
  │       └── 11/
  │           └── 2026-11-12_001/
  │               ├── manifest.json
  │               ├── article.epub
  │               └── README.md
  ├── graded/          # 分级短文（按等级）
  │   ├── hsk3/
  │   └── hsk4/
  ├── classic/         # 公版经典
  └── index/
      ├── articles.jsonl   # 全量文章索引（供 Meilisearch 导入）
      └── catalog.json     # 目录 API 用：按日期/等级/分类的文章清单
  ```
- **catalog.json** 是 App「发现页」的数据源：流水线每次跑完更新它，App 拉这一个文件就知道有哪些文章。

### 4.2 对象存储（大文件）
| 选型 | 优点 | 结论 |
|---|---|---|
| **Cloudflare R2** | 零出口流量费（全球 CDN 免费）、10GB 免费额度、S3 兼容 | ✅ 首选：音频/大 epub/pdf 放这 |
| GitHub Release / raw | 免费但有体积限制与限流 | 仅小文件 |
| 七牛/阿里云 OSS | 国内快 | 若主用户在国内，后续加国内节点 |

### 4.3 检索索引
| 选型 | 说明 | 结论 |
|---|---|---|
| **Meilisearch** | 轻量（单二进制）、中文分词内置、免费、自托管/R2 前可放 Fly.io 免费层 | ✅ 首选：词典 + 文章全文 + 搜词 |
| Typesense | 类似 Meilisearch | 备选 |
| Algolia | 托管省心，但免费额度有限 | 量大时考虑 |

部署：Meilisearch 跑在 Fly.io 免费 VM（或 Nas），每日从 Git 的 `index/articles.jsonl` 增量导入。词典（CC-CEDICT）也导进去，实现「搜词 → 释义 + 出现该词的文章」。

---

## 5. 后端服务（BFF，薄）

MVP 阶段后端极薄，大部分内容直接走 Git raw / CDN。后端只做「Git 做不好的事」。

### 5.1 选型
| 选项 | 说明 | 结论 |
|---|---|---|
| **Cloudflare Workers** | 全球边缘、免费 10 万请求/天、KV/D1 存储、与 R2 同生态 | ✅ MVP 首选：无服务器、零运维 |
| FastAPI（Python） | 与流水线同语言，易复用 NLP 逻辑 | 备选：若后端逻辑变重（AI 编排、用户系统）迁过去 |
| Next.js API Routes | 与前端同仓 | 最简场景可用，但边缘能力不如 Workers |

### 5.2 后端职责与端点
```
GET  /api/catalog              → 文章目录（缓存 catalog.json）
GET  /api/article/{id}         → 单篇 manifest（走 R2/raw，带缓存）
GET  /api/dict/{word}          → 查词（Meilisearch/词典）
GET  /api/search?q=&type=      → 全文检索文章 / 搜词
POST /api/ai/explain           → AI 句子讲解（代理 LLM，带缓存 + 限流）
POST /api/sync                 → 同步生词本/进度（需登录，M2）
GET  /api/stats                → 学习统计（M2）
```

**缓存策略**：目录与文章内容是「写一次读多次」，在 Workers 边缘缓存（Cache API / KV），TTL 1 小时；查词结果缓存 24h；AI 讲解结果按句子哈希缓存（同一篇同一句不重复花钱）。

### 5.3 LLM 代理
- 模型：**DeepSeek-V3**（中文好、便宜）或 **GPT-4o-mini** 兜底。
- 触发：仅当用户点「AI 讲解」时调用；非自动。
- 缓存：句子 hash → 讲解结果，存 KV，命中直接返回。
- 限流：每用户每日 N 次（防滥用）。
- Prompt 约束：只讲解语法/词汇，不给无关内容；输出结构化 JSON（语法点、难点词、同义句）。

---

## 6. 前端阅读器

### 6.1 技术栈
| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | **Next.js 14+（App Router）** + TypeScript | SSR/SSG 文章页利于 SEO 与首屏；React 生态组件全 |
| 样式 | Tailwind CSS | 快速搭阅读 UI |
| 状态 | Zustand（轻量） + 本地存储 | 生词本、设置、进度 |
| 本地存储 | **IndexedDB**（via `idb` 或 Dexie.js） | Web 端存生词本/进度/已下载文章，离线可用 |
| 部署 | **Vercel**（免费额度够 MVP）或 Cloudflare Pages | 与 Workers/R2 同生态优先 Cloudflare Pages |

### 6.2 阅读渲染（关键）
- **主路径：自定义 JSON 渲染器**。文章以 `manifest.json` 的句子数组交付，前端按句渲染 `<p>`，每个字/词包成可点击的 `<span>`，带 `data-char` / `data-word`，点击弹出浮层。这是体验核心，不能依赖 epub.js（epub 拿不到分词粒度）。
- **注音渲染**：用 `<ruby>` 标签（`<ruby>中<rt>zhōng</rt></ruby>`），原生支持、可 CSS 控制开关。「只给生字注音」：遍历句子，对不在用户「已掌握词表」里的字加 ruby。
- **epub 兼容阅读**（次要，给第三方用户）：提供 `.epub` 下载，App 内不渲染 epub。

### 6.3 关键交互组件
| 功能 | 实现 |
|---|---|
| 点字查义浮层 | 点击 `<span data-char>` → 调 `/api/dict` → 浮层显示拼音/释义/部首/笔画；「加入生词本」按钮 |
| 笔顺动画 | **hanzi-writer** 库（消费 hanzi-writer-data），弹层里 canvas 动画 |
| 整句翻译 | 点击句子空白处 → 调 `/api/article/{id}` 本地已有 translation，直接显示；「AI 讲解」按钮调 `/api/ai/explain` |
| 朗读 | **Web Speech API**（`SpeechSynthesis`，免费、系统语音）MVP；后期接自己的 TTS 音频（`Howler.js` 播放，支持分句高亮跟随） |
| 生词本 SRS 卡片 | 本地 IndexedDB 存生词 + SM-2 调度状态；复习页翻卡交互 |
| 多端同步 | 登录后调用 `/api/sync` 推送/拉取增量（M2） |

### 6.4 性能要点
- 文章页 SSG/ISR：manifest 不变就不重建，首屏快。
- 词典与 manifest 预取：进入阅读页前预取当前篇 manifest，点字即时响应（本地已有数据时不发请求）。
- 浮层用 React Portal，避免重排。

---

## 7. 部署与运维拓扑（MVP）

```
┌─────────────────────────────────────────────────────┐
│ GitHub                                              │
│  ├─ panda-news-content  (内容仓库 + Actions 流水线)   │
│  └─ panda-news-app      (前端源码)                   │
└────────┬───────────────────────────┬────────────────┘
         │ push 产物                  │ CI/CD 部署
         ▼                            ▼
┌─────────────────────┐      ┌────────────────────────┐
│ Cloudflare R2       │      │ Cloudflare Pages        │
│ (音频/大文件)       │      │ (Next.js 前端)          │
└──────────┬──────────┘      └───────────┬────────────┘
           │                             │
           └──────────────┬──────────────┘
                          ▼
                ┌───────────────────────┐
                │ Cloudflare Workers    │
                │ (BFF API + KV 缓存)   │
                └───────────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        R2(内容)      Meilisearch     LLM API
        (检索)        (Fly.io 免费)  (DeepSeek)
```

**每日流水线（GitHub Actions schedule `0 2 * * *` UTC）**：
1. checkout 内容仓库
2. `pip install` 依赖（calibre 用预装镜像或 apt 安装）
3. 跑 `python pipeline.py run-today` → 抓、加工、写文件
4. 更新 `catalog.json` 与 `index/articles.jsonl`
5. `git commit -am "content: 2026-11-12" && git push`
6. 触发 Webhook → Meilisearch 增量导入
7. 音频（若生成）上传 R2

> Calibre 在 Actions 里装：`apt-get install -y calibre`（约几百 MB，会占启动时间，但每天一次可接受）；或自建含 calibre 的 Docker 镜像提速。

---

## 8. 成本估算（MVP，月度）

| 项目 | 用量 | 费用 |
|---|---|---|
| GitHub（仓库 + Actions） | 公开仓库免费；Actions 2000 分钟/月 | ¥0 |
| Cloudflare Pages（前端托管） | 免费额度 | ¥0 |
| Cloudflare Workers（API） | 10 万请求/天免费 | ¥0 |
| Cloudflare R2（存储+出口） | 10GB 存储免费 + 出口免费 | ¥0 |
| Cloudflare KV（缓存） | 免费额度 | ¥0 |
| Meilisearch（Fly.io） | 免费 3×256MB VM | ¥0 |
| LLM（AI 讲解） | 假设 1k DAU × 2 次/天 × ~¥0.002/次 | ≈ ¥120/月 |
| TTS（edge-tts） | 免费 | ¥0 |
| 域名（可选） | 1 个 | ≈ ¥60/年 |
| **合计** | | **≈ ¥130/月**（远低于 ¥300 预算） |

> LLM 是唯一变量成本：可通过缓存 + 限流 + 本地词典兜底控制。若 DAU 上量，AI 讲解可转会员功能。

---

## 9. 技术风险与对策

| # | 风险 | 等级 | 对策 |
|---|---|---|---|
| T1 | 资讯版权（DMCA） | 高 | 优先公版 + RSS 摘要 + 自建；全文抓取仅允许源；每篇保留 `source_url` 与署名；提供「内容投诉」入口 |
| T2 | GitHub 仓库体积/raw 限流 | 中 | 音频/大文件走 R2；manifest 小文件走 raw + Workers 边缘缓存；超限迁自建镜像 |
| T3 | 注音/分词准确率 | 中 | pypinyin + jieba 成熟；对多音字（`了 le/liǎo`、`重 zhòng/chóng`）结合上下文词性消歧；关键内容人工抽检；允许用户报错纠错 |
| T4 | LLM 成本/延迟 | 中 | 本地词典覆盖 80% 高频查询；AI 讲解按需触发 + 按句缓存 + 限流；选便宜模型（DeepSeek） |
| T5 | TTS 音频量大 | 中 | 用免费 edge-tts；MVP 先只生成「今日推荐」3 篇的音频，其余按需/离线生成；音频放 R2 不重复生成 |
| T6 | 阅读器点字粒度性能 | 低 | 句子级预取 + IndexedDB 缓存词典；浮层本地渲染 |
| T7 | 多端同步一致性 | 低（M2 才做） | 以「最后写入胜出 + 生词并集」简化；不做复杂冲突合并 |
| T8 | 合规：未成年人/K12 | 中 | 内容审核（敏感词过滤）；提供 Kids 模式（只显示分级短文/经典，屏蔽资讯） |
| T9 | 单点依赖 GitHub | 低 | 内容仓可随时镜像到 Gitee/自建 Git；Workers 与 R2 不依赖 GitHub 可用性 |

---

## 10. 建议的代码仓库组织

两个仓库（内容与应用分离，参考 awesome 模式：内容仓独立、消费方解耦）：

```
panda-news-content/          # 内容仓库（公开，单一事实源）
├── .github/workflows/daily.yml   # 每日流水线
├── pipeline/                      # 抓取+加工脚本
│   ├── recipes/                   # Calibre news recipes
│   ├── nlp/                       # 注音/分词/分级/翻译
│   ├── tts/                       # 音频生成
│   ├── convert/                   # epub/pdf 生成
│   └── pipeline.py                # 编排入口
├── content/                       # 产物（见 §4.1）
├── data/                          # HSK 词表、字频表、CC-CEDICT
└── schema/                        # manifest.json 的 JSON Schema

panda-news-app/              # 应用仓库
├── web/                          # Next.js 阅读器（MVP）
├── workers/                      # Cloudflare Workers BFF
├── shared/                       # TS 类型（与 manifest schema 对齐）
└── docs/                         # 本文档与 PRD
```

> 一开始也可以单仓库 monorepo（`content/` + `app/` 放一起）降低心智负担，内容量上来再拆。

---

## 11. 与 PRD 里程碑的技术对应

| PRD 里程碑 | 技术交付 |
|---|---|
| M0 内容流水线验证 | `pipeline/` 跑通：Calibre 抓 1–2 个 RSS + pypinyin 注音 → 生成 `manifest.json` + epub → push 到 content 仓 |
| M1 MVP 阅读器 | `web/` Next.js 阅读器：读 catalog/manifest、点字查义（CC-CEDICT）、整句翻译、注音开关、Web Speech 朗读 |
| M2 生词本 + SRS | IndexedDB 生词本 + SM-2；Workers `/api/sync`；账户（Supabase Auth 或自建）；Meilisearch 部署 |
| M3 内容扩充 + AI | 公版经典入库、分级短文、edge-tts 音频、`/api/ai/explain` 接 DeepSeek + KV 缓存、全文搜索 |
| M4 多端 + 增长 | React Native / Flutter 出 App；R2 全球加速；推荐算法 |

---

## 12. 待决技术问题

1. **阅读器端方案**：纯 Web 起步，M4 是否用 React Native（共享 TS 逻辑）还是 Flutter（性能好）重做？→ 建议 RN，复用 TS。
2. **TTS 音频是否进 MVP**：edge-tts 免费但每天生成全部音频占 Actions 时间；MVP 先只给「今日推荐」生成，其余用 Web Speech 兜底。
3. **账户体系**：M2 才需要。用 **Supabase Auth**（免费、快）还是自建？→ 建议 Supabase，省时间。
4. **国内访问**：若主用户在国内，GitHub raw / R2 / Vercel 可能慢或不可达；是否加国内镜像（Gitee + 七牛 + 腾讯云）？→ 看种子用户分布再定。
5. **AI 讲解的语种**：默认英语讲解（面向 CSL），是否支持用户母语讲解（LLM 用用户目标语输出）？→ M3 加，存用户 `target_lang` 偏好。

---

*本文档与 PRD 配套，随 MVP 推进迭代。选型以「免费、低运维、可扩展」为首要原则，待验证后再替换为生产级组件。*
