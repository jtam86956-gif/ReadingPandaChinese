# 词典数据

阅读器「点词查义」与流水线生词释义依赖这里的词典。

## 推荐：CC-CEDICT
- 开源英汉词典，免费商用，CC BY-SA 3.0 授权。
- 下载：https://www.mdbg.net/chinese/dictionary?page=cc-cedict
- 格式：`cedict_ts.u8`（繁体，需转简体入库）。

## 用法（M1 接通）
- 解析为 SQLite 或 JSON，导入 Meilisearch 索引。
- `manifest` 中 token 的 `meaning`、`new_vocab[].meaning` 由流水线查本地词典填充
  （M0 暂为 null，留待 M1）。
