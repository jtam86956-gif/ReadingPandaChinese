/* 熊猫新闻 · 极简阅读器
 *
 * 只做三件事：展示原文、给生词注音、查极简本地释义。
 * 不做词典查询、不做整句翻译、不调任何外部 API。
 *
 * 数据来源：仓库内的 content/（catalog.json + manifest.json）。
 * 默认相对当前页取 ../content；也可用 ?data=<url> 指向远端 raw 目录。
 */

const params = new URLSearchParams(location.search);
const DATA_BASE = (params.get('data') || '../content').replace(/\/+$/, '');
const CJK = /[\u4e00-\u9fff]/;

const state = {
  catalog: [],
  glossary: {},
  manifest: null,
  showAllRuby: localStorage.getItem('pn.rubyAll') === '1',
};

const $ = (id) => document.getElementById(id);

/* ---------------- 数据加载 ---------------- */

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function manifestUrl(item) {
  // catalog.path 形如 content/wikisource/2026-11-12/<id>/manifest.json
  return `${DATA_BASE}/${item.path.replace(/^content\//, '')}`;
}

async function boot() {
  try {
    const [catalog, glossary] = await Promise.all([
      getJSON(`${DATA_BASE}/catalog.json`),
      getJSON('glossary.json'),
    ]);
    state.catalog = catalog.items || [];
    state.glossary = glossary;
    renderCatalog();
  } catch (err) {
    $('catalog').innerHTML =
      `<p class="hint">加载失败：${err.message}<br>` +
      `请通过本地服务器打开（例如在仓库根目录运行 <code>python3 -m http.server</code>），` +
      `或用 <code>?data=https://raw.githubusercontent.com/&lt;user&gt;/&lt;repo&gt;/main/content</code> 指定数据地址。</p>`;
  }
}

/* ---------------- 目录 ---------------- */

function renderCatalog() {
  $('ruby-all').checked = state.showAllRuby;
  const last = localStorage.getItem('pn.last');
  const byDate = new Map();
  for (const item of [...state.catalog].sort((a, b) => b.published_at.localeCompare(a.published_at))) {
    if (!byDate.has(item.published_at)) byDate.set(item.published_at, []);
    byDate.get(item.published_at).push(item);
  }

  const box = $('catalog');
  box.innerHTML = '';
  for (const [date, items] of byDate) {
    const day = document.createElement('section');
    day.className = 'day';
    day.innerHTML = `<h3>${date}${items.some((i) => i.id === last) ? ' · 上次读到' : ''}</h3>`;
    for (const item of items) {
      const el = document.createElement('div');
      el.className = 'item';
      el.innerHTML =
        `<span class="level">L${item.level}</span>` +
        `<span class="name">${escapeHtml(item.title)}</span>` +
        `<span class="cat">${escapeHtml(item.category || '')}</span>`;
      el.onclick = () => openArticle(item);
      day.appendChild(el);
    }
    box.appendChild(day);
  }
  $('catalog').hidden = false;
  $('reader').hidden = true;
  $('back').hidden = true;
}

/* ---------------- 阅读 ---------------- */

async function openArticle(item) {
  $('catalog').hidden = true;
  $('reader').hidden = false;
  $('back').hidden = false;
  $('body').innerHTML = '<p class="hint">加载中…</p>';

  try {
    const m = await getJSON(manifestUrl(item));
    state.manifest = m;
    localStorage.setItem('pn.last', m.id);
    renderArticle(m);
    window.scrollTo({ top: 0 });
  } catch (err) {
    $('body').innerHTML = `<p class="hint">无法加载文章：${err.message}</p>`;
  }
}

function renderArticle(m) {
  $('title').textContent = m.title;
  $('meta').innerHTML =
    `<span class="level">L${m.level}</span>` +
    `<span>${escapeHtml(m.category || '')}</span>` +
    `<span>${m.word_count} 字</span>` +
    `<a href="${m.source_url}" target="_blank" rel="noopener">${escapeHtml(m.source)}</a>`;

  const newWords = new Set((m.new_vocab || []).map((v) => v.w));
  const body = $('body');
  body.innerHTML = '';

  for (const sentence of m.content) {
    const p = document.createElement('p');
    const chars = [...sentence.text];
    const syls = (sentence.pinyin || '').split(/\s+/).filter(Boolean);
    const aligned = syls.length === chars.length;
    const segs = buildSegments(sentence.text, sentence.tokens || []);

    let charIndex = 0;
    for (const seg of segs) {
      const start = charIndex;   // 固定本段起点，供点击回调使用（循环结束后 charIndex 已变）
      const span = document.createElement('span');
      span.className = 'w' + (seg.token && newWords.has(seg.token.w) ? ' new' : '');
      const segChars = [...seg.text];

      // 是否给这段文字注音：开启全文注音，或该词是本文生词
      const rubyHere = aligned && (state.showAllRuby || (seg.token && newWords.has(seg.token.w)));

      segChars.forEach((ch, i) => {
        const syl = aligned ? syls[charIndex + i] : '';
        if (rubyHere && CJK.test(ch) && syl) {
          const ruby = document.createElement('ruby');
          ruby.append(ch);
          const rt = document.createElement('rt');
          rt.textContent = syl;
          ruby.append(rt);
          span.append(ruby);
        } else {
          span.append(ch);
        }
      });

      if (seg.token) {
        span.onclick = (ev) => showPop(ev, seg.token, aligned ? syls.slice(start, start + segChars.length) : []);
      }
      charIndex += segChars.length;
      p.appendChild(span);
    }
    body.appendChild(p);
  }

  renderVocab(m.new_vocab || []);
}

/** 把句子按 token 切段；任一段对不上原文就退化为「整句一段」，保证不丢字。 */
function buildSegments(text, tokens) {
  const chars = [...text];
  const segs = [];
  let i = 0;
  for (const token of tokens) {
    const w = [...token.w];
    if (chars.slice(i, i + w.length).join('') !== token.w) {
      return [{ text, token: null }];
    }
    segs.push({ text: token.w, token });
    i += w.length;
  }
  if (i !== chars.length) return [{ text, token: null }];
  return segs;
}

function renderVocab(vocab) {
  const box = $('vocab');
  if (!vocab.length) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = '<h3>本文生词</h3>';
  const ul = document.createElement('ul');
  for (const v of vocab) {
    const li = document.createElement('li');
    const gloss = state.glossary[v.w];
    li.innerHTML =
      `${escapeHtml(v.w)}${v.hsk ? ` <span class="level">L${v.hsk}</span>` : ''}` +
      (gloss ? `<span class="g">${escapeHtml(gloss)}</span>` : '');
    ul.appendChild(li);
  }
  box.appendChild(ul);
}

/* ---------------- 弹层：点字/点词看拼音与释义 ---------------- */

function showPop(ev, token, syls) {
  ev.stopPropagation();
  const pop = $('pop');
  const pinyin = syls.filter((s) => s && !/^[，。！？；：、（）「」『』—…]$/.test(s)).join(' ');
  const gloss = state.glossary[token.w];

  pop.innerHTML =
    `<div style="font-size:16px">${escapeHtml(token.w)}</div>` +
    (pinyin ? `<div class="py">${escapeHtml(pinyin)}</div>` : '') +
    (gloss
      ? `<div class="gl">${escapeHtml(gloss)}</div>`
      : `<div class="none">本地词表未收录</div>`);

  const rect = ev.target.getBoundingClientRect();
  pop.hidden = false;
  pop.style.left = `${Math.min(rect.left + window.scrollX, window.innerWidth - 260)}px`;
  pop.style.top = `${rect.bottom + window.scrollY + 8}px`;
}

document.addEventListener('click', () => { $('pop').hidden = true; });

/* ---------------- 交互 ---------------- */

$('back').onclick = () => {
  renderCatalog();
  window.scrollTo({ top: 0 });
};

$('ruby-all').onchange = (e) => {
  state.showAllRuby = e.target.checked;
  localStorage.setItem('pn.rubyAll', state.showAllRuby ? '1' : '0');
  if (state.manifest) renderArticle(state.manifest);
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

boot();
