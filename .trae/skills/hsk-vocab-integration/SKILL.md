---
name: hsk-vocab-integration
description: Fetch, parse, and integrate authoritative HSK vocabulary into the grading pipeline. Use when adding or updating HSK word lists, parsing an exam-syllabus PDF, or improving new-word judgment with cross-level annotations. Do not use for non-HSK vocabulary.
---

# HSK Vocabulary Integration

End-to-end procedure for bringing an authoritative HSK vocabulary source into Panda News's
difficulty grading (`pipeline/nlp/grade.py`) and new-word judgment (`pipeline/manifest.py`).
The two sources already in this repo are templates; reuse their scripts rather than rewriting.

## Non-negotiable principle

**Never fabricate vocabulary.** Every word list must come from an authoritative, citeable
source, and the import must be verifiable against the official published counts. If a source
cannot be verified, do not integrate it.

Authoritative sources used so far:

- GF 0025—2021 《国际中文教育中文水平等级标准》— 11092 entries, cumulative
  500 / 1272 / 2245 / 3245 / 4316 / 5456 / 11092. Machine-readable via the official
  Hanban interface: `https://admin.chinesetest.cn/newhsk/standardsAction.do?means=getStandardWordsList`.
- HSK 3.0 《考试大纲》(2025-11, HSK Korea) — 11000 entries, cumulative
  300 / 500 / 1000 / 2000 / 3600 / 5400 / 11000, with cross-level annotations like `1（4）`.
  PDF source. Different level scale from the standard — **do not compare level numbers
  across the two documents directly**.

## Workflow

### 1. Verify the source before writing any parser

- Locate the official publisher and confirm the **total entry count** and **per-level
  cumulative counts** are published. These are your validation baseline.
- Prefer a machine-readable source (API / structured TSV) over PDF. Only parse PDF when no
  structured source exists.
- Record the source URL and access date in a `SOURCES.md` or `COMPARISON.md` next to the data.

### 2. Write a reproducible fetch/parse script with hard validation

Template scripts already exist — copy and adapt them:

- `scripts/fetch_hsk30.py` — scrapes the official API into `data/hsk/HSK{1..7}.txt`
  and `data/hsk/hsk30_full.tsv`.
- `scripts/parse_hsk30_exam_syllabus.py` — parses the exam-syllabus PDF into
  `data/hsk/reference/hsk30_exam_syllabus.tsv` using `pypdf` (`pip install --user pypdf`).

The script **must** fail with a non-zero exit if any of these do not match the official
baseline:

- total entry count
- per-level cumulative counts

Do not rely on "looks about right." Sort and assert sequence continuity (1..N) too.

### 3. Normalize word forms — this is where most bugs hide

The two sources use **different word-form conventions**, so a raw exact match will miss
many common words (e.g. GF stores `们（朋友们）`, exam stores `们`; GF stores `本`, exam
stores `本1`). Normalize before lookup so both match jieba token output:

- strip a trailing run of ASCII digits: `本1` → `本`, `点1` → `点`
- strip full-width parenthetical glosses: `们（朋友们）` → `们`, `没（有）` → `没`

Apply the **same** `_normalize_word` to keys of **both** lookups and to the incoming token,
so a word is resolved identically everywhere. In `grade.py` this lives in
`_normalize_word()` and is applied in `_load_exam()`; the GF list is matched exactly but
`word_level()` also consults the normalized exam index, which fills the gaps.

### 4. Wire into grading with one consistent notion of level

Per the existing design:

- `word_level(word)` returns the **effective known level** = the lower of the GF level and
  the exam-syllabus primary level. Rationale: if either authoritative source lists a word at
  level L, a level-L learner is assumed to have learned it.
- Use this effective level for **both** article grading (`grade_level`) and new-word
  judgment (`_collect_new_vocab`). Never let a token carry one level for grading and a
  different level for new-word flags — inconsistent conclusions confuse the reader.
- Expose exam cross-level annotations via `word_cross_levels(word)` and write a `cross`
  field onto the token and `new_vocab` entry only when non-empty (keeps manifests lean).
- **Graceful degradation is mandatory:** the exam syllabus is reference data. If its file is
  missing, `_load_exam()` returns `{}` and `word_level()` falls back to GF only. The main
  path must never break because optional reference data is absent.

### 5. Validate with a controlled before/after on the same article

Absolute numbers across different fetched articles are not comparable. To prove an
optimization:

1. Take one manifest's sentence texts as fixed input.
2. Run tokenize → grade → `_collect_new_vocab` twice: once with the new data enabled, once
   with `_load_exam` mocked to `{}` (degraded).
3. Compare: null-token count, per-level hit distribution, new-vocab list, article level.
4. Confirm the JSON manifest still passes `schema/manifest.schema.json` and that article
   `level` stays within 1–6 and did not jump wildly.

### 6. Document provenance and comparison

- Keep raw source PDFs in `data/hsk/<area>/reference/raw/` for reproducibility.
- Write a `COMPARISON.md` when integrating a second source: overlap size, unique-to-each
  counts, and a clear caveat if level scales differ (they do here).

## Pitfalls already paid for (do not repeat)

- **PDF text extraction quirks (exam syllabus):** the level column uses `7-9` for the band
  and `（7-9）` inside cross annotations — the regex must accept digit ranges, not just
  `（\d+）`. Words may contain full-width parens (`没（有）`), so the word character class
  must include `（）`. The 词性 column wraps across lines and can concatenate with the next
  row's number with no space (`副）46 1 多少`) — use a lookahead anchored on
  `(?<!\d)\d+\s+<level>\s+<CJK>`, not a leading `\s+`. Collapse internal newlines in
  pinyin/词性 to spaces before writing TSV, or columns misalign. Truncate at the section
  heading after the vocabulary (e.g. `汉字大纲`) so the last row doesn't swallow following
  chapters. Remove the per-page watermark (`汉考国际`) and bare page-number footers.
- **False match from cover/TOC pages:** a row pattern can match garbage on the title page
  (e.g. a pure-digit "word"). Require the captured word to contain at least one CJK char.
- **Level scales differ between documents:** a word at "level 3" in the standard and
  "level 6" in the exam is usually a scale difference, not a contradiction. Report raw
  agreement but don't treat disagreement as an error.
- **Python 3.9 compatibility:** every module under `pipeline/` needs
  `from __future__ import annotations` (no `X | None` syntax at runtime). New helper modules
  must follow this.
- **`-v/--verbose` is a global option** on `pipeline.pipeline` — put it before the
  subcommand: `python3 -m pipeline.pipeline -v run-today --limit 1`.

## Files to consult

- `pipeline/nlp/grade.py` — `_normalize_word`, `_load_exam`, `word_level`,
  `word_cross_levels`, `grade_level`.
- `pipeline/manifest.py` — `_collect_new_vocab` and token `cross` injection.
- `schema/manifest.schema.json` — declare any new token/new_vocab field here.
- `data/hsk/reference/COMPARISON.md` — the comparison report format to mirror.
