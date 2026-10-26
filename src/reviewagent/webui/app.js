/* ReviewAgent v2 · 对象层工作台 */
(function () {
  'use strict';

  const API = '/v1';
  const TABS = [
    { group: 'overview', label: '总览', code: '01' },
    { group: 'diagnosis', label: '口碑诊断', code: '02' },
    { group: 'growth', label: '增长机会', code: '03' },
    { group: 'ops', label: '运营方案', code: '04' },
    { group: 'evidence', label: '证据与方法', code: '05' }
  ];
  const FIRST_TARGET = {
    overview: 'sec-overview',
    diagnosis: 'sec-diagnosis',
    growth: 'sec-improvements',
    ops: 'sec-ops',
    evidence: 'sec-evidence'
  };
  const TARGET_GROUP = {
    'sec-overview': 'overview',
    'sec-object': 'overview',
    'sec-coverage': 'overview',
    'sec-diagnosis': 'diagnosis',
    'sec-pains': 'diagnosis',
    'sec-competitors': 'diagnosis',
    'sec-improvements': 'growth',
    'sec-topics': 'growth',
    'sec-content': 'growth',
    'sec-ops': 'ops',
    'sec-actions': 'ops',
    'sec-evidence': 'evidence'
  };
  const STATUS_LABELS = {
    resolved: '对象已解析',
    partial: '部分解析',
    needs_capture: '待补采集',
    needs_link: '待补链接'
  };
  const RISK_LABELS = { low: '低', medium: '中', high: '高' };
  const KIND_LABELS = { input: '输入', data: '数据', method: '方法', search: '搜索' };
  const PLATFORM_LABELS = { jd: '京东', taobao: '淘宝', tmall: '天猫', xhs: '小红书', unknown: '未知平台' };
  const ICONS = ['box', 'database', 'users', 'file', 'activity'];
  const state = {
    analysis: null,
    loading: false,
    error: '',
    apiOffline: false,
    tab: 'overview',
    activeTarget: 'sec-overview',
    recent: [],
    draftInput: '',
    extraDraft: '',
    extraLinks: [],
    reviews: [],
    ownership: 'own',
    lastAttempt: null
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function text(value, fallback = '—') {
    if (value === null || value === undefined || value === '') return fallback;
    return esc(value);
  }

  function icon(name) {
    return '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
  }

  function normalizeUrl(value) {
    if (!value) return '';
    let raw = String(value).trim();
    if (!raw) return '';
    if (raw.startsWith('//')) raw = 'https:' + raw;
    try {
      const url = new URL(raw, window.location.origin);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
      return esc(url.href);
    } catch (err) {
      return '';
    }
  }

  function fmt(value, fallback = '—') {
    if (value === null || value === undefined || value === '') return fallback;
    if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString('zh-CN');
    return esc(value);
  }

  function fmtFloat(value, digits = 1, fallback = '—') {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return number.toFixed(digits);
  }

  function fmtDate(value, withTime = true) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return esc(value);
    try {
      return new Intl.DateTimeFormat('zh-CN', withTime
        ? { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
        : { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
    } catch (err) {
      return esc(value);
    }
  }

  function pct(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(100, Math.round(number * 100)));
  }

  function platformInfo(object) {
    const key = String(object && object.platform || 'unknown').toLowerCase();
    return {
      key,
      label: (object && object.platform_label) || PLATFORM_LABELS[key] || (key === 'unknown' ? '未知平台' : key),
      chipClass: 'platform-' + (PLATFORM_LABELS[key] ? key : 'unknown'),
      dotClass: 'is-' + (PLATFORM_LABELS[key] ? key : 'unknown')
    };
  }

  function statusInfo(object) {
    const raw = String(object && object.status || 'needs_link');
    return {
      raw,
      label: (object && object.status_label) || STATUS_LABELS[raw] || raw,
      tone: raw === 'resolved' ? '' : raw === 'partial' ? 'is-partial' : 'is-blocked'
    };
  }

  function confidenceInfo(object) {
    const number = Number(object && object.confidence);
    const label = object && object.confidence_label
      ? object.confidence_label
      : (!Number.isFinite(number) ? '未评估' : number >= 0.8 ? '高' : number >= 0.5 ? '中' : '低');
    return {
      label,
      line: Number.isFinite(number) ? label + ' · ' + Math.round(number * 100) + '%' : label,
      high: Number.isFinite(number) && number >= 0.8
    };
  }

  function riskLabel(value) {
    if (!value || value === 'unknown') return '未评估';
    return RISK_LABELS[String(value)] || String(value);
  }

  function apiError(data, status) {
    const detail = data && data.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item && (item.msg || item.message || String(item))).filter(Boolean).join('；');
    }
    if (data && data.message) return String(data.message);
    return '请求失败（HTTP ' + status + '）';
  }

  function parseLinks(value) {
    return String(value || '')
      .split(/[\r\n]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 20);
  }

  function todayString() {
    return new Date().toISOString().slice(0, 10);
  }

  function normalizeReview(item) {
    if (typeof item === 'string') {
      const textValue = item.trim();
      return textValue ? { review_text: textValue, platform: 'manual', review_date: todayString() } : null;
    }
    if (!item || typeof item !== 'object') return null;
    const textValue = item.review_text || item.text || item.content || item.comment;
    if (!textValue || !String(textValue).trim()) return null;
    const review = Object.assign({}, item, {
      review_text: String(textValue).trim(),
      platform: item.platform || 'manual',
      review_date: item.review_date || item.date || item.created_at || todayString()
    });
    return review;
  }

  function parseReviews(value) {
    const raw = String(value || '').trim();
    if (!raw) throw new Error('还没有填写评论样本');
    let list;
    if (raw.startsWith('[') || raw.startsWith('{')) {
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        throw new Error('JSON 格式不正确：' + err.message);
      }
      list = Array.isArray(parsed) ? parsed : (Array.isArray(parsed.reviews) ? parsed.reviews : []);
    } else {
      list = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    }
    const reviews = list.map(normalizeReview).filter(Boolean).slice(0, 500);
    if (!reviews.length) throw new Error('没有识别到有效评论，请检查字段 review_text');
    return reviews;
  }

  function toast(message, type) {
    const root = $('#toast-root');
    if (!root) return;
    const el = document.createElement('div');
    el.className = 'toast' + (type === 'error' ? ' is-error' : '');
    el.innerHTML = icon(type === 'error' ? 'alert' : 'check') + '<span>' + esc(message) + '</span>';
    root.appendChild(el);
    window.setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(4px)';
      el.style.transition = 'opacity .18s ease, transform .18s ease';
      window.setTimeout(() => el.remove(), 220);
    }, 3600);
  }

  function applyTheme(theme) {
    const value = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = value;
    const button = $('#btn-theme');
    if (button) {
      button.innerHTML = icon(value === 'dark' ? 'sun' : 'moon');
      button.setAttribute('aria-label', value === 'dark' ? '切换到浅色' : '切换到深色');
      button.setAttribute('title', value === 'dark' ? '切换到浅色' : '切换到深色');
    }
  }

  function readTheme() {
    const saved = localStorage.getItem('ra.theme');
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('ra.theme', next);
    applyTheme(next);
  }

  function bindImageFallbacks() {
    $$('.thumb img[data-thumb-img]').forEach((img) => {
      img.addEventListener('error', () => {
        const parent = img.parentNode;
        if (parent) parent.innerHTML = iconFallback();
      }, { once: true });
    });
  }

  function render() {
    const analysis = state.analysis;
    const title = analysis
      ? ((analysis.report && analysis.report.object && analysis.report.object.title) || (analysis.object && analysis.object.title) || '分析报告')
      : '新建分析';
    const crumb = $('#crumb-title');
    if (crumb) crumb.textContent = title;

    const tabsZone = $('#tabs-zone');
    if (tabsZone) {
      const showTabs = Boolean(analysis) && !state.loading;
      tabsZone.hidden = !showTabs;
      tabsZone.innerHTML = showTabs ? renderTabs() : '';
    }

    const searchZone = $('#search-zone');
    if (searchZone) searchZone.innerHTML = renderSearch();

    const summary = $('#report-summary');
    if (summary) {
      if (state.loading) {
        summary.innerHTML = renderLoadingSummary();
      } else if (analysis) {
        summary.innerHTML = renderReportSummary(analysis);
        bindImageFallbacks();
      } else {
        summary.innerHTML = '';
      }
    }

    const content = $('#content');
    if (content) {
      if (state.loading) {
        content.innerHTML = renderLoadingContent();
      } else if (!analysis) {
        content.innerHTML = renderEmpty();
      } else {
        content.innerHTML = renderReportGroups(analysis);
      }
    }

    applyGroupVisibility();
    updateTabs();
    renderSidebarState();
  }

  function renderTabs() {
    return '<div class="tabs" role="tablist" aria-label="报告视图">' + TABS.map((tab) => (
      '<button class="tab' + (state.tab === tab.group ? ' is-active' : '') + '" type="button" role="tab"'
        + ' aria-selected="' + (state.tab === tab.group ? 'true' : 'false') + '"'
        + ' data-group="' + esc(tab.group) + '">' + esc(tab.label) + '<small>' + esc(tab.code) + '</small></button>'
    )).join('') + '</div>';
  }

  function updateTabs() {
    $$('.tab').forEach((tab) => {
      const active = tab.dataset.group === state.tab;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    applyGroupVisibility();
  }

  function applyGroupVisibility() {
    $$('.group').forEach((group) => {
      const active = group.dataset.group === state.tab;
      group.classList.toggle('is-hidden', !active);
      group.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
  }

  function renderSidebarState() {
    const hasAnalysis = Boolean(state.analysis);
    $$('#side-nav .side-link').forEach((button) => {
      button.classList.toggle('is-disabled', !hasAnalysis);
      button.setAttribute('aria-disabled', hasAnalysis ? 'false' : 'true');
    });
    const target = hasAnalysis
      ? (TARGET_GROUP[state.activeTarget] === state.tab ? state.activeTarget : FIRST_TARGET[state.tab])
      : 'sec-overview';
    setActiveSide(target);
  }

  function setActiveSide(target) {
    if (!target) return;
    state.activeTarget = target;
    $$('#side-nav .side-link[data-target]').forEach((button) => {
      const active = button.dataset.target === target;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'location');
      else button.removeAttribute('aria-current');
    });
  }

  function renderSearch() {
    const analysis = state.analysis;
    const value = state.draftInput != null && state.draftInput !== ''
      ? state.draftInput
      : (analysis && analysis.input) || '';
    const disabled = state.loading ? ' disabled' : '';
    const buttonText = state.loading ? '解析中' : (analysis ? '重新分析' : '开始分析');
    const buttonIcon = state.loading ? '<svg class="icon spin" aria-hidden="true"><use href="#i-refresh"></use></svg>' : icon('search');

    if (!analysis) {
      return '<section class="hero" aria-labelledby="hero-title">'
        + '<div class="hero-kicker"><span class="status-dot"></span> REVIEWAGENT · OBJECT LAYER</div>'
        + '<h1 id="hero-title">先确认<span>对象</span>，再谈口碑。</h1>'
        + '<p class="hero-sub">粘贴商品链接，先解析标题、品牌、店铺与规格，再按品牌、型号和规格匹配同款。评论为空时，报告只到对象层，不生成口碑分数。</p>'
        + '<form id="analysis-form" class="hero-form" novalidate>'
        + '<div class="form-row">'
        + '<div class="input-wrap">' + icon('link')
        + '<input class="input" id="analysis-input" name="input" type="text" value="' + esc(value) + '" placeholder="粘贴商品链接，或输入商品名" autocomplete="off" spellcheck="false" aria-label="商品链接或商品名" /></div>'
        + '<button class="btn btn-primary" type="submit"' + disabled + '>' + buttonIcon + buttonText + '</button>'
        + '</div>'
        + '<div class="hero-chips">'
        + '<button class="chip chip-button" type="button" data-action="fill-sample">示例：京东茅台</button>'
        + '<span class="chip">京东链接直接解析对象</span>'
        + '<span class="chip">淘宝 / 天猫 / 小红书先识别，再提示补采集</span>'
        + '<span class="chip">商品名会给出搜索入口</span>'
        + '</div>'
        + '<div class="compact-options">'
        + '<div class="left"><span class="small-label">归属</span>' + renderOwnership(state.ownership, state.loading) + '</div>'
        + '<span class="faint">不登录 · 不猜价格与销量</span>'
        + '</div>'
        + '</form>'
        + '<div class="hero-foot">'
        + '<p>解析结果来自公开商品页；候选只来自同一 SPU 与你补充的链接。报告中的每个结论都带 evidence 与 method，缺口会直接列出来。</p>'
        + '<button class="btn btn-ghost btn-sm" type="button" data-action="open-about">' + icon('shield') + '数据边界</button>'
        + '</div>'
        + '</section>';
    }

    return '<section class="search-compact" aria-label="分析对象输入">'
      + '<div class="search-compact-top">'
      + '<div class="search-compact-title">' + icon('search') + '分析对象</div>'
      + '<span class="chip"><strong>对象层</strong> · 报告已生成</span>'
      + '</div>'
      + '<form id="analysis-form" novalidate>'
      + '<div class="form-row">'
      + '<div class="input-wrap">' + icon('link')
      + '<input class="input" id="analysis-input" name="input" type="text" value="' + esc(value) + '" placeholder="粘贴商品链接，或输入商品名" autocomplete="off" spellcheck="false" aria-label="商品链接或商品名"' + disabled + ' /></div>'
      + '<button class="btn btn-primary" type="submit"' + disabled + '>' + buttonIcon + buttonText + '</button>'
      + '</div>'
      + '<div class="compact-options">'
      + '<div class="left"><span class="small-label">归属</span>' + renderOwnership(state.ownership, state.loading)
      + '<span class="chip">档位 <strong>标准</strong></span></div>'
      + '<span class="faint">评论未采集 · 口碑指标留空</span>'
      + '</div>'
      + '</form>'
      + '</section>';
  }

  function renderOwnership(ownership, disabled) {
    const own = ownership === 'competitor' ? 'competitor' : 'own';
    const off = disabled ? ' disabled' : '';
    return '<div class="ownership" role="group" aria-label="商品归属">'
      + '<button class="seg-btn' + (own === 'own' ? ' is-active' : '') + '" type="button" data-action="ownership" data-value="own"' + off + '>自家商品</button>'
      + '<button class="seg-btn' + (own === 'competitor' ? ' is-active' : '') + '" type="button" data-action="ownership" data-value="competitor"' + off + '>竞品</button>'
      + '</div>';
  }

  function renderEmpty() {
    return (state.apiOffline ? renderErrorCard('本地 API 未连接', '页面已加载，但 /v1 接口没有响应。请先运行 reviewagent serve --port 8000，然后刷新。') : '')
      + (state.error && !state.apiOffline ? renderErrorCard('上一次分析中断', state.error) : '')
      + '<div class="start-grid">'
      + '<article class="start-card">' + icon('box') + '<div class="step-no">01 / RESOLVE</div><h3>解析对象</h3><p>从京东公开商品页提取标题、品牌、店铺、类目与同 SPU 规格。淘宝、天猫和小红书只识别链接，不假装解析。</p></article>'
      + '<article class="start-card">' + icon('users') + '<div class="step-no">02 / MATCH</div><h3>匹配同款</h3><p>同一 SPU 的规格直接标为同款；补充其他链接后，按品牌、型号词与标题相似度逐项比较，标出理由与不一致。</p></article>'
      + '<article class="start-card">' + icon('file') + '<div class="step-no">03 / REPORT</div><h3>生成报告</h3><p>没有评论就只输出对象层结论、证据、缺口与下一步。口碑分、风险、痛点和运营方案全部留空，不用占位数字。</p></article>'
      + '</div>'
      + '<div class="boundary-card">'
      + '<div><h3>这次版本做什么</h3><p>先把“这是哪个商品、有哪些同款、哪些信息还没拿到”说清楚。</p>'
      + '<ul class="boundary-list">'
      + '<li>' + icon('check') + '<span>京东商品页解析：标题、品牌、店铺、类目、规格</span></li>'
      + '<li>' + icon('check') + '<span>同 SPU 规格匹配，以及用户补充链接的逐项比较</span></li>'
      + '<li>' + icon('check') + '<span>每条结论带 evidence 与 method，缺口按严重程度列出</span></li>'
      + '<li>' + icon('check') + '<span>报告保存在本机；刷新后可从“最近分析”恢复</span></li>'
      + '</ul></div>'
      + '<div><h3>这次版本不做什么</h3><p>没有数据就不生成结论，避免把对象层报告伪装成口碑报告。</p>'
      + '<ul class="boundary-list">'
      + '<li>' + icon('x') + '<span>不登录抓评论，不绕过平台风控</span></li>'
      + '<li>' + icon('x') + '<span>不从商品页猜价格、销量或评论数</span></li>'
      + '<li>' + icon('x') + '<span>不生成口碑总分、痛点图谱或假引语</span></li>'
      + '<li>' + icon('x') + '<span>不把同款候选混成竞品对照</span></li>'
      + '</ul></div>'
      + '</div>'
      + renderRecent();
  }

  function renderRecent() {
    const items = Array.isArray(state.recent) ? state.recent : [];
    let body;
    if (!items.length) {
      body = '<div class="recent-empty">还没有保存的分析。完成第一次对象解析后，记录会出现在这里。</div>';
    } else {
      body = '<div class="recent-list">' + items.map((item) => {
        const title = item.title || item.input || '未命名对象';
        return '<button class="recent-item" type="button" data-action="open-recent" data-id="' + esc(item.analysis_id) + '">'
          + '<span class="thumb-sm">' + icon('box') + '</span>'
          + '<span class="recent-copy"><strong>' + esc(title) + '</strong><span>' + esc(item.platform || '对象') + ' · ' + esc(item.status_label || '已保存') + ' · ' + esc(fmtDate(item.created_at)) + '</span></span>'
          + '<span class="faint">' + icon('arrow-right') + '</span>'
          + '</button>';
      }).join('') + '</div>';
    }
    return '<section class="recent-card" aria-label="最近分析">'
      + '<div class="recent-head"><h3>最近分析</h3><span>仅保存在本机</span></div>'
      + body
      + '</section>';
  }

  function renderErrorCard(title, detail) {
    return '<div class="error-card">'
      + '<div class="error-title">' + icon('alert') + esc(title) + '</div>'
      + '<p class="error-detail">' + esc(detail) + '</p>'
      + '<div class="error-actions">'
      + '<button class="btn btn-sm" type="button" data-action="retry">' + icon('refresh') + '重试</button>'
      + '<a class="btn btn-sm" href="/docs" target="_blank" rel="noreferrer">' + icon('file') + 'API 文档</a>'
      + '</div></div>';
  }

  function renderLoadingSummary() {
    return '<div class="sk-card">'
      + '<div class="sk-line w40"></div><div class="sk-line w85"></div><div class="sk-line w55"></div>'
      + '<div class="sk-grid"><div class="sk-box"></div><div class="sk-box"></div><div class="sk-box"></div></div>'
      + '</div>';
  }

  function renderLoadingContent() {
    return '<div class="skeleton-wrap">'
      + '<div class="sk-card"><div class="sk-line w40"></div><div class="sk-line w70"></div></div>'
      + '<div class="loading-grid"><div class="sk-box"></div><div class="sk-box"></div><div class="sk-box"></div></div>'
      + '<div class="sk-card"><div class="sk-line w55"></div><div class="sk-line w85"></div><div class="sk-line w70"></div></div>'
      + '</div>';
  }

  function renderReportSummary(analysis) {
    const report = analysis.report || {};
    const object = Object.assign({}, report.object || {}, analysis.object || {});
    return (state.error ? renderErrorCard('重新分析中断，仍显示上一次报告', state.error) : '')
      + renderPrintHead(object, report, analysis)
      + renderObjectCard(object, analysis)
      + renderKpis(report);
  }

  function renderPrintHead(object, report, analysis) {
    const title = object.title || (analysis && analysis.input) || '未命名对象';
    const meta = ['ReviewAgent v2', '对象层报告', report.status_label, fmtDate(report.generated_at)].filter((part) => part && String(part).trim()).join(' · ');
    return '<div class="print-only print-head"><h1>' + esc(title) + '</h1>'
      + '<p>' + esc(meta) + '</p></div>';
  }

  function renderObjectCard(object, analysis) {
    const platform = platformInfo(object);
    const status = statusInfo(object);
    const confidence = confidenceInfo(object);
    const image = normalizeUrl(object.image_url);
    const url = normalizeUrl(object.url);
    const title = object.title || (object.platform_id ? platform.label + '商品 ' + object.platform_id : (object.input || '未解析出商品对象'));
    const metaScore = Number(object.metadata_score);
    const ringValue = Number.isFinite(metaScore) ? Math.max(0, Math.min(100, Math.round(metaScore))) : 0;
    const ownership = object.ownership === 'competitor' ? 'competitor' : 'own';
    const warning = object.status && object.status !== 'resolved'
      ? renderObjectWarning(object)
      : '';

    const thumb = image
      ? '<img src="' + image + '" alt="" loading="lazy" referrerpolicy="no-referrer" data-thumb-img="1" />'
      : '<span class="thumb-fallback">' + icon('box') + '</span>';

    return '<article class="card object-card">'
      + '<div class="object-top">'
      + '<div class="object-main">'
      + '<div class="thumb">' + thumb + '</div>'
      + '<div class="object-copy">'
      + '<div class="object-eyebrow">'
      + '<span class="platform-chip ' + esc(platform.chipClass) + '">' + esc(platform.label) + '</span>'
      + '<span class="confidence-chip' + (confidence.high ? ' is-high' : '') + '">' + esc(confidence.line) + '</span>'
      + '<span class="chip"><strong>' + esc(object.type_label || '对象') + '</strong></span>'
      + '</div>'
      + '<h1 class="object-title">' + esc(title) + '</h1>'
      + '<div class="object-meta">'
      + '<span class="meta-item">品牌 <b>' + text(object.brand) + '</b></span>'
      + '<span class="meta-item">店铺 <b>' + text(object.shop) + '</b></span>'
      + '<span class="meta-item">ID <b class="mono">' + text(object.platform_id) + '</b></span>'
      + '</div>'
      + '<div class="object-links">'
      + (url ? '<a class="external" href="' + url + '" target="_blank" rel="noreferrer">打开原页面 ' + icon('arrow-up-right') + '</a>' : '')
      + '<button class="link" type="button" data-action="focus-input">补 / 换链接</button>'
      + (object.variant_count ? '<span class="faint">同 SPU 规格 ' + esc(object.variant_count) + ' 个</span>' : '')
      + '</div>'
      + '</div></div>'
      + '<aside class="object-side">'
      + '<div class="object-status"><span class="status-pill ' + esc(status.tone) + '">' + esc(status.label) + '</span>'
      + '<span class="score-ring" style="--value:' + ringValue + '" title="对象元数据完整度"><span class="score-ring-inner"><strong>' + (Number.isFinite(metaScore) ? ringValue : '—') + '</strong><span>完整度</span></span></span></div>'
      + '<div><div class="small-label">归属</div>' + renderOwnership(ownership, false) + '</div>'
      + (url
        ? '<a class="btn btn-primary" href="' + url + '" target="_blank" rel="noreferrer">' + icon('arrow-up-right') + '打开原页面</a>'
        : '<button class="btn btn-primary" type="button" data-action="focus-input">' + icon('link') + '补一个链接</button>')
      + '<p class="object-note">解析器 ' + text(object.parser, '未解析') + ' · ' + fmtDate(object.fetched_at) + '</p>'
      + '</aside></div>'
      + warning
      + '</article>';
  }

  function iconFallback() {
    return '<span class="thumb-fallback"><svg class="icon" aria-hidden="true"><use href="#i-box"></use></svg></span>';
  }

  function renderObjectWarning(object) {
    const searchLinks = Array.isArray(object.search_urls) ? object.search_urls : [];
    const links = searchLinks.map((item) => {
      const url = normalizeUrl(item && item.url);
      if (!url) return '';
      return '<a href="' + url + '" target="_blank" rel="noreferrer">' + esc(item.platform || '搜索') + '</a>';
    }).filter(Boolean).join(' · ');
    return '<div class="object-warning">' + icon('alert')
      + '<div>' + esc(object.message || '对象信息不完整，先补一个能唯一定位的商品链接。')
      + (links ? ' 搜索入口：' + links : '')
      + '</div></div>';
  }

  function renderKpis(report) {
    const dashboard = report.dashboard || {};
    const trust = (report.diagnosis || {}).trust || null;
    const risk = trust && trust.risk_level ? riskLabel(trust.risk_level) : riskLabel(dashboard.risk_label || dashboard.risk);
    const candidate = dashboard.candidate_count != null ? dashboard.candidate_count : 0;
    const reviews = dashboard.review_count != null ? dashboard.review_count : 0;
    const scoreEmpty = dashboard.score == null;
    const cards = [
      { label: '口碑总分', value: scoreEmpty ? '—' : fmt(dashboard.score), unit: '/100', tag: '待评论', note: dashboard.score_note || '需要情绪分析', empty: scoreEmpty },
      { label: '评论样本', value: fmt(reviews), unit: '条', tag: '原始', note: reviews ? 'Trust Report 已接收' : '未采集评论', empty: false },
      { label: '风险等级', value: risk, unit: '', tag: trust ? '可信度' : '待评估', note: trust ? '来自 Trust Report' : '需要评论样本', empty: !trust },
      { label: '痛点', value: dashboard.pain_count == null ? '—' : fmt(dashboard.pain_count), unit: '个', tag: '待分析', note: dashboard.pain_note || '评论未分析', empty: dashboard.pain_count == null },
      { label: '同款候选', value: fmt(candidate), unit: '个', tag: '已匹配', note: (report.same_products && report.same_products.summary && report.same_products.summary.exact || 0) + ' 同款 · ' + (report.same_products && report.same_products.summary && report.same_products.summary.similar || 0) + ' 近似', empty: false },
      { label: '覆盖平台', value: fmt(dashboard.coverage_platforms), unit: '个', tag: '对象', note: dashboard.coverage_note || '已解析对象平台', empty: false }
    ];
    return '<div class="kpi-grid">' + cards.map((card) => (
      '<div class="kpi-card">'
        + '<div class="kpi-top"><span class="kpi-label">' + esc(card.label) + '</span><span class="kpi-tag">' + esc(card.tag) + '</span></div>'
        + '<div class="kpi-value' + (card.empty ? ' is-empty' : '') + '">' + esc(card.value) + (card.unit ? '<span class="kpi-unit">' + esc(card.unit) + '</span>' : '') + '</div>'
        + '<div class="kpi-note">' + esc(card.note) + '</div>'
      + '</div>'
    )).join('') + '</div>';
  }

  function renderReportGroups(analysis) {
    const report = analysis.report || {};
    const object = Object.assign({}, report.object || {}, analysis.object || {});
    const candidates = analysis.candidates || (report.same_products && report.same_products.items) || [];
    const summary = analysis.match_summary || (report.same_products && report.same_products.summary) || {};
    return '<section class="group' + (state.tab === 'overview' ? '' : ' is-hidden') + '" data-group="overview">'
      + renderOverview(report, object, summary)
      + renderObjectSection(report, object, candidates, summary)
      + renderCoverageSection(report)
      + '</section>'
      + '<section class="group' + (state.tab === 'diagnosis' ? '' : ' is-hidden') + '" data-group="diagnosis">'
      + renderDiagnosisSection(report)
      + renderPainsSection(report)
      + renderCompetitorsSection(report)
      + '</section>'
      + '<section class="group' + (state.tab === 'growth' ? '' : ' is-hidden') + '" data-group="growth">'
      + renderImprovementsSection(report, summary)
      + renderTopicsSection(report, summary)
      + renderContentSection(report)
      + '</section>'
      + '<section class="group' + (state.tab === 'ops' ? '' : ' is-hidden') + '" data-group="ops">'
      + renderOpsSection(report)
      + renderActionsSection(report, analysis)
      + '</section>'
      + '<section class="group' + (state.tab === 'evidence' ? '' : ' is-hidden') + '" data-group="evidence">'
      + renderEvidenceSection(report, analysis)
      + '</section>';
  }

  function sectionHead(kicker, title, desc, actions) {
    return '<div class="section-head"><div><div class="section-kicker">' + esc(kicker) + '</div><h2 class="section-title">' + esc(title) + '</h2>'
      + (desc ? '<p class="section-desc">' + esc(desc) + '</p>' : '')
      + '</div>' + (actions ? '<div class="section-actions">' + actions + '</div>' : '') + '</div>';
  }

  function renderOverview(report, object, summary) {
    const overview = report.overview || {};
    const dashboard = report.dashboard || {};
    const dataStatus = report.data_status || {};
    const bullets = Array.isArray(overview.bullets) ? overview.bullets : [];
    const actions = (report.next_actions || []).slice(0, 3);
    const exact = Number(summary.exact || 0);
    const similar = Number(summary.similar || 0);
    const competitor = Number(summary.competitor || 0);
    const uncertain = Number(summary.uncertain || 0);
    const reviewCount = dashboard.review_count || 0;

    return '<section class="section" id="sec-overview">'
      + sectionHead('01 / OVERVIEW', '结论', '先说明确认了哪些对象，以及哪些结论缺少数据。', '<button class="btn btn-sm" type="button" data-action="scroll-to" data-target="sec-evidence">' + icon('shield') + '查看证据</button>')
      + '<div class="grid-main-side">'
      + '<div class="card">'
      + '<div class="callout is-info"><div class="callout-title">' + icon('info') + '当前结论</div><p class="conclusion">' + esc(overview.conclusion || '报告已生成，但没有可展示的结论。') + '</p></div>'
      + '<div class="bullet-grid">' + bullets.map((item, index) => (
        '<div class="bullet"><span class="bullet-icon">' + icon(ICONS[index % ICONS.length]) + '</span><div><b>' + esc(item.label || '字段') + '</b><p>' + esc(item.value || '—') + '</p></div></div>'
      )).join('') + '</div>'
      + '<div class="divider"></div>'
      + '<div class="card-head"><div><div class="card-title">先补哪一步</div><p class="card-sub">按优先级排列的数据动作，不是运营建议。</p></div><button class="btn btn-sm" type="button" data-action="scroll-to" data-target="sec-actions">全部动作 ' + icon('arrow-right') + '</button></div>'
      + (actions.length ? renderActionList(actions) : '<div class="empty" style="margin-top:10px"><div class="empty-title">没有待补动作</div><div class="empty-text">当前报告没有记录到需要补做的数据动作。</div></div>')
      + '</div>'
      + '<div class="stack">'
      + '<div class="card"><div class="card-title">数据状态</div><p class="card-sub">' + esc(dataStatus.note || '对象层报告') + '</p><div style="margin-top:12px">'
      + '<div class="metric-line"><span>对象解析</span><b>' + (dataStatus.object_resolved ? '已完成' : '待补') + '</b></div>'
      + '<div class="metric-line"><span>评论采集</span><b>' + (reviewCount ? esc(reviewCount) + ' 条' : '未采集') + '</b></div>'
      + '<div class="metric-line"><span>情绪分析</span><b>未运行</b></div>'
      + '<div class="metric-line"><span>报告阶段</span><b>' + esc(dataStatus.status_label || '仅对象元数据') + '</b></div>'
      + '</div></div>'
      + '<div class="card"><div class="card-title">候选概览</div><p class="card-sub">同 SPU 规格会被标为同款，不混进竞品。</p><div style="margin-top:12px">'
      + '<div class="metric-line"><span>同款</span><b>' + exact + '</b></div>'
      + '<div class="metric-line"><span>近似款</span><b>' + similar + '</b></div>'
      + '<div class="metric-line"><span>竞品</span><b>' + competitor + '</b></div>'
      + '<div class="metric-line"><span>待判断</span><b>' + uncertain + '</b></div>'
      + '</div><button class="btn btn-sm" style="margin-top:12px;width:100%" type="button" data-action="scroll-to" data-target="sec-object">查看候选 ' + icon('arrow-right') + '</button></div>'
      + '</div></div></section>';
  }

  function renderObjectSection(report, object, candidates, summary) {
    const facts = [
      ['平台', platformInfo(object).label],
      ['商品 ID', object.platform_id || '—'],
      ['品牌', object.brand || '—'],
      ['店铺', object.shop || '—'],
      ['类目', Array.isArray(object.category) && object.category.length ? object.category.join(' / ') : '—'],
      ['置信度', confidenceInfo(object).line],
      ['解析器', object.parser || '—'],
      ['抓取时间', fmtDate(object.fetched_at)]
    ];
    const variants = Array.isArray(object.variants) ? object.variants : [];
    const notes = Array.isArray(summary.notes) ? summary.notes : [];
    const keywords = Array.isArray(summary.search_keywords) ? summary.search_keywords : [];
    return '<section class="section" id="sec-object">'
      + sectionHead('02 / OBJECT & MATCH', '对象与同款', '对象档案、同 SPU 规格与补充链接的逐项比较。', '<button class="btn btn-sm" type="button" data-action="scroll-to" data-target="sec-evidence">' + icon('link') + '证据</button>')
      + '<div class="card">'
      + '<div class="card-head"><div><div class="card-title">对象档案</div><p class="card-sub">' + esc(object.type_label || '对象') + ' · ' + esc(object.ownership_label || '归属未设置') + '</p></div><span class="chip">' + esc(object.status_label || '已记录') + '</span></div>'
      + '<div class="table-wrap" style="margin-top:12px"><table class="data-table"><tbody>'
      + facts.map(([label, value]) => '<tr><td style="width:110px;color:var(--muted)">' + esc(label) + '</td><td>' + esc(value) + '</td></tr>').join('')
      + '</tbody></table></div>'
      + (variants.length ? '<div style="margin-top:12px"><div class="small-label">同 SPU 规格 · ' + variants.length + ' 个</div><div class="tag-row" style="margin-top:6px">' + variants.slice(0, 16).map((variant) => {
        const label = typeof variant === 'string' ? variant : [variant.color, variant.size, variant.specName].filter(Boolean).join(' / ') || variant.skuId || '规格';
        return '<span class="tag">' + esc(label) + '</span>';
      }).join('') + (variants.length > 16 ? '<span class="tag">+' + (variants.length - 16) + '</span>' : '') + '</div></div>' : '')
      + '</div>'
      + '<div style="margin-top:12px">' + renderCandidateTable(candidates, summary) + '</div>'
      + renderExtraForm(summary)
      + (notes.length || keywords.length
        ? '<div class="callout is-info" style="margin-top:12px"><div class="callout-title">' + icon('info') + '匹配说明</div>'
          + (notes.length ? '<ul class="callout-list">' + notes.map((note) => '<li>' + icon('check') + '<span>' + esc(note) + '</span></li>').join('') + '</ul>' : '')
          + (keywords.length ? '<div class="tag-row" style="margin-top:9px">' + keywords.map((keyword) => '<span class="tag">' + esc(keyword) + '</span>').join('') + '</div>' : '')
          + '</div>'
        : '')
      + '</section>';
  }

  function renderCandidateTable(candidates, summary) {
    const list = Array.isArray(candidates) ? candidates : [];
    if (!list.length) {
      return '<div class="empty"><div class="empty-icon">' + icon('users') + '</div><div class="empty-title">还没有同款候选</div>'
        + '<p class="empty-text">当前对象没有同 SPU 规格，也没有补充链接。粘贴其他商品链接后，匹配器会按品牌、型号与标题逐项比较。</p>'
        + '<div class="empty-steps"><span><b>01</b> 补链接</span><span><b>02</b> 逐项比较</span><span><b>03</b> 写入证据</span></div></div>';
    }
    return '<div class="table-wrap"><table class="data-table candidate-table">'
      + '<thead><tr><th>匹配</th><th>候选</th><th>平台</th><th>分数</th><th>判定依据</th><th>数据</th><th>链接</th></tr></thead><tbody>'
      + list.map((candidate) => {
        const level = String(candidate.match_level || 'uncertain');
        const matchClass = level === 'exact' ? 'match-exact' : level === 'similar' ? 'match-similar' : level === 'competitor' ? 'match-competitor' : 'match-uncertain';
        const reasons = Array.isArray(candidate.match_reasons) ? candidate.match_reasons : (Array.isArray(candidate.reasons) ? candidate.reasons : []);
        const mismatches = Array.isArray(candidate.mismatches) ? candidate.mismatches : [];
        const score = candidate.match_score == null ? '—' : pct(candidate.match_score) + '%';
        const url = normalizeUrl(candidate.url);
        const unavailable = Array.isArray(candidate.unavailable_fields) && candidate.unavailable_fields.length
          ? candidate.unavailable_fields.join('、') + ' 未取得'
          : '价格、销量、评论数未取得';
        return '<tr>'
          + '<td data-label="匹配"><span class="match-pill ' + matchClass + '">' + esc(candidate.match_label || level) + '</span></td>'
          + '<td class="cell-title candidate-title" data-label="候选">' + esc(candidate.title || '未解析标题') + '<small>' + esc(candidate.source_label || '候选') + (candidate.platform_id ? ' · ' + esc(candidate.platform_id) : '') + '</small></td>'
          + '<td data-label="平台"><span class="platform-cell"><span class="platform-dot ' + esc(platformInfo(candidate).dotClass) + '"></span>' + esc(candidate.platform_label || platformInfo(candidate).label) + '</span></td>'
          + '<td class="num" data-label="匹配度">' + esc(score) + '</td>'
          + '<td data-label="判定依据"><div class="reason-chips">' + (reasons.length ? reasons.slice(0, 3).map((reason) => '<span class="reason">' + esc(reason) + '</span>').join('') : '<span class="faint">—</span>') + (mismatches.length ? '<span class="reason" title="' + esc(mismatches.join('；')) + '">差异 ' + mismatches.length + '</span>' : '') + '</div></td>'
          + '<td data-label="数据"><span class="unavailable">' + esc(unavailable) + '</span></td>'
          + '<td data-label="链接">' + (url ? '<a class="external" href="' + url + '" target="_blank" rel="noreferrer">打开 ' + icon('arrow-up-right') + '</a>' : '<span class="faint">—</span>') + '</td>'
          + '</tr>';
      }).join('')
      + '</tbody></table>'
      + '<div class="table-foot"><span>' + list.length + ' 个候选 · 同款 ' + (summary.exact || 0) + ' · 近似 ' + (summary.similar || 0) + ' · 竞品 ' + (summary.competitor || 0) + '</span><span>价格 / 销量 / 评论数不从页面猜</span></div>'
      + '</div>';
  }

  function renderExtraForm(summary) {
    const draft = state.extraDraft != null && state.extraDraft !== '' ? state.extraDraft : (state.extraLinks || []).join('\n');
    return '<div class="card extra-links-card" style="margin-top:12px"><div class="card-head"><div><div class="card-title">补充同款链接</div><p class="card-sub">每行一个链接；会重新解析主对象，并保留已填的评论样本。</p></div><span class="chip">最多 20 个</span></div>'
      + '<form id="extra-form" style="margin-top:12px" novalidate>'
      + '<label class="field"><span class="field-label">同款 / 近似款链接 <small>每行一个</small></span>'
      + '<textarea class="textarea" id="extra-links" name="extra_links" placeholder="https://item.jd.com/100012043978.html&#10;https://detail.tmall.com/item.htm?id=...">' + esc(draft) + '</textarea></label>'
      + '<div class="compact-options"><span class="form-hint">京东链接可直接解析；其他平台可能返回“待补采集”，不会假装拿到标题。</span>'
      + '<button class="btn btn-primary btn-sm" type="submit">' + icon('refresh') + '更新候选</button></div>'
      + '</form></div>';
  }

  function renderCoverageSection(report) {
    const coverage = report.coverage || {};
    const platforms = Array.isArray(coverage.platforms) ? coverage.platforms : [];
    return '<section class="section" id="sec-coverage">'
      + sectionHead('03 / COVERAGE', '平台覆盖', '只统计已经解析到的对象，不代表评论样本覆盖。', '')
      + '<div class="card" style="padding:0">'
      + (platforms.length
        ? '<div class="table-wrap" style="border:0;border-radius:var(--radius)"><table class="data-table"><thead><tr><th>平台</th><th>角色</th><th>对象</th><th>评论</th><th>状态</th></tr></thead><tbody>'
          + platforms.map((item) => '<tr><td><span class="platform-cell"><span class="platform-dot ' + esc(platformInfo(item).dotClass) + '"></span>' + esc(item.label || item.platform) + '</span></td><td>' + esc(item.role || '—') + '</td><td class="num">' + fmt(item.object_count) + '</td><td class="num">' + fmt(item.review_count) + '</td><td><span class="status-pill ' + (item.status === 'reviews_present' ? '' : 'is-partial') + '">' + esc(item.status_label || '仅有对象') + '</span></td></tr>').join('')
          + '</tbody></table></div>'
        : '<div class="empty" style="border:0"><div class="empty-title">没有平台记录</div><div class="empty-text">解析结束后，这里会列出主商品与候选所在平台。</div></div>')
      + '<div class="card-sub" style="padding:11px 14px;border-top:1px solid var(--line)">' + esc(coverage.note || '覆盖统计只统计已解析对象。') + '</div>'
      + '</div></section>';
  }

  function renderDiagnosisSection(report) {
    const diagnosis = report.diagnosis || {};
    const trust = diagnosis.trust || null;
    const score = trust && trust.overall_trust_score != null ? Number(trust.overall_trust_score) : null;
    const scoreText = score == null || !Number.isFinite(score) ? '—' : String(Math.round(score));
    const risk = trust && trust.risk_level ? riskLabel(trust.risk_level) : riskLabel(diagnosis.risk);
    const duplicateGroups = trust && Array.isArray(trust.duplicate_groups) ? trust.duplicate_groups.length : 0;
    const mismatch = trust && trust.mismatch_count != null ? trust.mismatch_count : null;
    const signals = [
      { label: '时间突发', value: trust ? (trust.burst_detected ? '检测到' : '未检测到') : '未运行', bar: trust ? (trust.burst_detected ? 100 : 12) : 0, note: '按评论时间分布' },
      { label: '重复评论', value: trust ? duplicateGroups + ' 组' : '未运行', bar: trust && duplicateGroups ? 100 : 12, note: '近重复文本分组' },
      { label: '评分矛盾', value: trust ? (trust.rating_anomaly ? '检测到' : '未检测到') : '未运行', bar: trust ? (trust.rating_anomaly ? 100 : 12) : 0, note: '评分与文本方向' },
      { label: '评分 / 文本不一致', value: trust && mismatch != null ? mismatch + ' 条' : '未运行', bar: trust && mismatch ? 100 : 12, note: '明褒暗贬与错配' }
    ];
    const reasons = Array.isArray(diagnosis.reasons) ? diagnosis.reasons : [];
    return '<section class="section" id="sec-diagnosis">'
      + sectionHead('04 / DIAGNOSIS', '口碑诊断', '可信度先于情绪；没有评论样本时不计算分数。', '<button class="btn btn-sm" type="button" data-action="guide-reviews">' + icon('plus') + '补评论样本</button>')
      + '<div class="card"><div class="trust-card">'
      + '<div class="trust-score"><div class="trust-label">TRUST SCORE</div>' + (score == null ? '<div class="trust-value is-empty">未评估</div><div class="trust-scale">需要评论样本</div>' : '<div class="trust-value">' + esc(scoreText) + '</div><div class="trust-scale">/ 100 · 后验均值</div>') + '<div class="trust-note">' + icon('info') + '<span>' + (trust ? 'Trust Report 已运行，风险等级 ' + esc(risk) + '。' : '评论样本为 0，Trust Report 未运行。') + '</span></div></div>'
      + '<div class="trust-body"><h3>' + esc(diagnosis.status_label || '缺少评论') + '</h3><p>' + esc(diagnosis.summary || '没有评论样本，无法计算可信度。') + '</p>'
      + '<div class="signal-grid">' + signals.map((signal) => '<div class="signal"><div class="signal-top"><span>' + esc(signal.label) + '</span><b>' + esc(signal.value) + '</b></div><div class="signal-bar"><i style="width:' + signal.bar + '%"></i></div><div class="signal-note">' + esc(signal.note) + '</div></div>').join('') + '</div>'
      + '</div></div>'
      + (reasons.length ? '<div class="callout is-warn" style="margin-top:14px"><div class="callout-title">' + icon('alert') + '为什么不是口碑总分</div><ul class="callout-list">' + reasons.map((reason) => '<li>' + icon('check') + '<span>' + esc(reason) + '</span></li>').join('') + '</ul></div>' : '')
      + '</div></section>';
  }

  function renderPainsSection(report) {
    const pains = report.pain_points || {};
    const items = Array.isArray(pains.items) ? pains.items : [];
    return '<section class="section" id="sec-pains">'
      + sectionHead('05 / PAIN POINTS', '痛点图谱', '痛点必须由评论原文支撑；空列表不代表没有痛点。', '<button class="btn btn-sm" type="button" data-action="guide-reviews">' + icon('plus') + '补评论</button>')
      + (items.length
        ? '<div class="card"><div class="card-sub">' + esc(pains.summary || '') + '</div></div>'
        : '<div class="card"><div class="empty" style="border:0;padding:0"><div class="empty-icon">' + icon('target') + '</div><div class="empty-title">' + esc(pains.status_label || '尚未生成') + '</div>'
          + '<p class="empty-text">' + esc(pains.summary || '没有评论原文，无法抽取痛点；空列表不代表没有痛点。') + '</p>'
          + '<div class="empty-steps"><span><b>01</b> 补评论原文</span><span><b>02</b> 情绪与有效性</span><span><b>03</b> 按频次 × 严重度排序</span></div>'
          + '<button class="btn btn-sm" type="button" data-action="guide-reviews">' + icon('plus') + '补评论样本</button></div>'
          + '<div class="divider"></div>'
          + '<div class="grid-3">'
          + '<div class="boundary-item" style="border:0;padding:0"><strong>评论原文</strong><p>至少一段可引用的用户原话，带来源与日期。</p></div>'
          + '<div class="boundary-item" style="border:0;padding:0"><strong>情绪与有效性</strong><p>9 类情绪、8 类有效性，先判定再聚合。</p></div>'
          + '<div class="boundary-item" style="border:0;padding:0"><strong>频次 × 严重度</strong><p>痛点排序需要样本量与影响面，不靠单条评论。</p></div>'
          + '</div></div>')
      + '</section>';
  }

  function renderCompetitorsSection(report) {
    const competitors = report.competitors || {};
    const items = Array.isArray(competitors.items) ? competitors.items : [];
    const rival = items.filter((item) => item.match_level === 'competitor');
    const summary = (report.same_products && report.same_products.summary) || {};
    return '<section class="section" id="sec-competitors">'
      + sectionHead('06 / COMPETITORS', '竞品对照', '同款不会被算成竞品；只有品牌不同且匹配度足够的候选才进入这里。', '')
      + '<div class="card">'
      + '<div class="callout is-info"><div class="callout-title">' + icon('users') + '当前候选结构</div><p>' + esc(competitors.summary || '候选只来自同一 SPU 与用户补充链接。') + '</p></div>'
      + '<div class="grid-3" style="margin-top:12px">'
      + '<div class="metric-line"><span>同款</span><b>' + (summary.exact || 0) + '</b></div>'
      + '<div class="metric-line"><span>近似款</span><b>' + (summary.similar || 0) + '</b></div>'
      + '<div class="metric-line"><span>竞品</span><b>' + rival.length + '</b></div>'
      + '</div>'
      + (rival.length
        ? '<div style="margin-top:12px">' + renderCandidateTable(rival, summary) + '</div>'
        : '<div class="empty" style="margin-top:12px"><div class="empty-icon">' + icon('users') + '</div><div class="empty-title">当前没有竞品候选</div>'
          + '<p class="empty-text">补充其他品牌或型号的链接后，匹配器才会给出竞品对照。同一 SPU 的其他规格只会标为同款，不会混进竞品。</p>'
          + '<button class="btn btn-sm" type="button" data-action="scroll-to" data-target="sec-object">' + icon('link') + '去补链接</button></div>')
      + '</div></section>';
  }

  function renderImprovementsSection(report, summary) {
    const improvements = report.improvements || {};
    return '<section class="section" id="sec-improvements">'
      + sectionHead('07 / OPPORTUNITIES', '增长机会', '改进方向必须由痛点与证据支撑；当前没有评论证据。', '<button class="btn btn-sm" type="button" data-action="guide-reviews">' + icon('plus') + '补评论</button>')
      + '<div class="card"><div class="empty" style="border:0;padding:0"><div class="empty-icon">' + icon('spark') + '</div><div class="empty-title">' + esc(improvements.status_label || '未生成') + '</div>'
      + '<p class="empty-text">' + esc(improvements.summary || '改进方向必须由痛点与证据支撑；当前没有评论证据。') + '</p>'
      + '<div class="empty-steps"><span><b>01</b> 痛点频次</span><span><b>02</b> 影响面</span><span><b>03</b> 可执行改动</span></div></div>'
      + '<div class="divider"></div><div class="grid-3">'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>产品改进</strong><p>来自可复现的抱怨与使用场景，不来自标题推测。</p></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>内容机会</strong><p>人群、场景、痛点、证据四件事齐全才进入选题。</p></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>验证方式</strong><p>每条改动都要有能看到变化的指标，不写空泛建议。</p></div>'
      + '</div></div></section>';
  }

  function renderTopicsSection(report, summary) {
    const topics = report.topics || {};
    const keywords = Array.isArray(summary.search_keywords) ? summary.search_keywords : [];
    return '<section class="section" id="sec-topics">'
      + sectionHead('08 / TOPICS', '内容选题', '选题需要人群、场景、痛点与证据；只有商品信息时留空。', '')
      + '<div class="card"><div class="empty" style="border:0;padding:0"><div class="empty-icon">' + icon('pen') + '</div><div class="empty-title">' + esc(topics.status_label || '未生成') + '</div>'
      + '<p class="empty-text">' + esc(topics.summary || '内容选题需要人群、痛点与场景；当前只有商品信息。') + '</p></div>'
      + (keywords.length ? '<div class="divider"></div><div class="small-label">匹配器给出的搜索词 · 用于人工找同款，不是选题</div><div class="tag-row" style="margin-top:7px">' + keywords.map((keyword) => '<span class="tag">' + esc(keyword) + '</span>').join('') + '</div>' : '')
      + '</div></section>';
  }

  function renderContentSection(report) {
    const kit = report.content_kit || {};
    return '<section class="section" id="sec-content">'
      + sectionHead('09 / CONTENT KIT', '内容生产包', '主图 brief、详情页 8 段与 15 秒脚本都依赖评论证据。', '')
      + '<div class="card"><div class="empty" style="border:0;padding:0"><div class="empty-icon">' + icon('file') + '</div><div class="empty-title">' + esc(kit.status_label || '未生成') + '</div>'
      + '<p class="empty-text">' + esc(kit.summary || '主图 brief、详情页 8 段与 15 秒脚本都依赖评论证据，暂不生成。') + '</p></div>'
      + '<div class="divider"></div><div class="grid-3">'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>主图 brief</strong><p>卖点顺序、场景与可核对细节。</p><span class="tag" style="margin-top:6px">待评论</span></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>详情页 8 段</strong><p>买家问题、卖点、结构、边界与售后。</p><span class="tag" style="margin-top:6px">待评论</span></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>15 秒脚本</strong><p>镜头、口播与字幕，逐条绑定证据。</p><span class="tag" style="margin-top:6px">待评论</span></div>'
      + '</div></div></section>';
  }

  function renderOpsSection(report) {
    const ops = report.ops_plan || {};
    return '<section class="section" id="sec-ops">'
      + sectionHead('10 / OPERATIONS', '运营方案', '运营方案需要痛点、转化证据与商家数据；当前样本不足。', '')
      + '<div class="card"><div class="empty" style="border:0;padding:0"><div class="empty-icon">' + icon('compass') + '</div><div class="empty-title">' + esc(ops.status_label || '未生成') + '</div>'
      + '<p class="empty-text">' + esc(ops.summary || '运营方案需要痛点、转化证据与商家数据；当前样本不足。') + '</p></div>'
      + '<div class="divider"></div><div class="grid-3">'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>商品页</strong><p>卖点顺序、信息缺口与异议处理。</p><span class="tag" style="margin-top:6px">待生成</span></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>定价与促销</strong><p>组合、满减与价格锚点，不靠猜。</p><span class="tag" style="margin-top:6px">待生成</span></div>'
      + '<div class="boundary-item" style="border:0;padding:0"><strong>内容与流量</strong><p>可验证的选题与场景内容。</p><span class="tag" style="margin-top:6px">待生成</span></div>'
      + '</div></div></section>';
  }

  function renderActionsSection(report, analysis) {
    const actions = Array.isArray(report.next_actions) ? report.next_actions : [];
    const opsActions = Array.isArray(report.actions) ? report.actions : [];
    return '<section class="section" id="sec-actions">'
      + sectionHead('11 / ACTIONS', '行动清单', '这些是补齐数据的动作，不是运营建议。', '<button class="btn btn-sm" type="button" data-action="download-csv"' + (opsActions.length ? '' : ' disabled title="运营动作尚未生成，CSV 只有表头"') + '>' + icon('download') + '导出 CSV</button>')
      + '<div class="card">'
      + (actions.length ? renderActionList(actions) : '<div class="empty" style="border:0;padding:0"><div class="empty-title">没有待补动作</div><div class="empty-text">当前报告没有记录到需要补做的数据动作。</div></div>')
      + '<div class="divider"></div><div class="card-sub">报告编号 <span class="mono">' + esc(analysis.analysis_id || '—') + '</span> · 生成于 ' + esc(fmtDate(report.generated_at)) + ' · 运营动作 ' + opsActions.length + ' 条</div>'
      + '</div></section>';
  }

  function renderActionList(actions) {
    return '<div class="action-list">' + actions.map((action) => {
      const priority = String(action.priority || 'P2').toUpperCase();
      const priorityClass = priority === 'P0' ? 'priority-p0' : priority === 'P1' ? 'priority-p1' : 'priority-p2';
      return '<div class="action-item"><span class="action-priority ' + priorityClass + '">' + esc(priority) + '</span>'
        + '<div class="action-copy"><strong>' + esc(action.label || '待补动作') + '</strong>'
        + (action.detail ? '<p class="action-detail">' + esc(action.detail) + '</p>' : '')
        + '<div class="action-meta"><span>' + esc(KIND_LABELS[action.kind] || action.kind || '数据') + '</span></div>'
        + '</div></div>';
    }).join('') + '</div>';
  }

  function renderEvidenceSection(report, analysis) {
    const evidence = Array.isArray(report.evidence) ? report.evidence : [];
    const gaps = Array.isArray(report.gaps) ? report.gaps : [];
    const method = report.method || {};
    const limitations = Array.isArray(method.limitations) ? method.limitations : [];
    return '<section class="section" id="sec-evidence">'
      + sectionHead('12 / EVIDENCE', '证据与方法', '每条结论应该能回到原页面或原始样本；查不到的缺口要写出来。', '<button class="btn btn-sm" type="button" data-action="print">' + icon('printer') + '打印 / PDF</button>')
      + '<div class="grid-2">'
      + '<div class="card"><div class="card-head"><div><div class="card-title">证据</div><p class="card-sub">对象页与候选页的抓取记录</p></div><span class="chip">' + evidence.length + ' 条</span></div>'
      + (evidence.length ? '<div class="evidence-list" style="margin-top:12px">' + evidence.map((item) => renderEvidenceItem(item)).join('') + '</div>'
        : '<div class="empty" style="margin-top:12px"><div class="empty-title">没有证据记录</div><div class="empty-text">当前报告没有可回溯的抓取证据。</div></div>')
      + '</div>'
      + '<div class="card"><div class="card-head"><div><div class="card-title">缺口</div><p class="card-sub">按严重程度排序；不是失败，是明确边界</p></div><span class="chip">' + gaps.length + ' 项</span></div>'
      + (gaps.length ? '<div class="gap-list" style="margin-top:12px">' + gaps.map((gap) => renderGap(gap)).join('') + '</div>'
        : '<div class="empty" style="margin-top:12px"><div class="empty-title">没有记录缺口</div><div class="empty-text">当前报告没有记录数据缺口。</div></div>')
      + '</div></div>'
      + '<div class="card" style="margin-top:12px"><div class="card-head"><div><div class="card-title">方法与限制</div><p class="card-sub">这份报告能解释到什么程度</p></div><span class="chip">' + esc(method.report_version || 'v2') + '</span></div>'
      + '<div class="table-wrap" style="margin-top:12px"><table class="data-table method-table"><tbody>'
      + '<tr><td>解析器</td><td>' + text(method.resolver) + '</td></tr>'
      + '<tr><td>匹配规则</td><td>' + text(method.matching) + '</td></tr>'
      + '<tr><td>LLM</td><td>' + (method.llm_used ? '已调用' : '未调用') + '</td></tr>'
      + '<tr><td>评论分析</td><td>' + esc(method.review_analysis === 'trust_only' ? '仅 Trust Report' : method.review_analysis === 'not_run' ? '未运行' : (method.review_analysis || '未运行')) + '</td></tr>'
      + '<tr><td>报告版本</td><td>' + text(method.report_version) + '</td></tr>'
      + '</tbody></table></div>'
      + (limitations.length ? '<div class="callout is-warn" style="margin-top:12px"><div class="callout-title">' + icon('alert') + '限制</div><ul class="callout-list">' + limitations.map((item) => '<li>' + icon('check') + '<span>' + esc(item) + '</span></li>').join('') + '</ul></div>' : '')
      + '<div class="divider"></div><div class="card-sub">报告编号 <span class="mono">' + esc(analysis.analysis_id || '—') + '</span> · 创建 ' + esc(fmtDate(analysis.created_at)) + '</div>'
      + '</div></section>';
  }

  function renderEvidenceItem(item) {
    const url = normalizeUrl(item.url);
    const type = String(item.type || 'evidence');
    const typeLabel = type === 'product_page' ? '商品页' : type === 'object' ? '对象页' : type === 'candidate' ? '候选' : '证据';
    const fields = Array.isArray(item.fields) ? item.fields : [];
    return '<article class="evidence-item"><div class="evidence-head"><span class="evidence-type is-fact">' + esc(typeLabel) + '</span><span class="evidence-title">' + esc(item.title || '抓取记录') + '</span></div>'
      + (item.quote && item.quote !== item.title ? '<div class="evidence-quote">' + esc(item.quote) + '</div>' : '')
      + '<div class="evidence-meta"><span class="mono">' + esc(item.id || '—') + '</span><span>' + esc(fmtDate(item.fetched_at)) + '</span>' + fields.slice(0, 4).map((field) => '<span class="tag">' + esc(field) + '</span>').join('') + (url ? '<a href="' + url + '" target="_blank" rel="noreferrer">打开原页面 ' + icon('arrow-up-right') + '</a>' : '') + '</div></article>';
  }

  function renderGap(gap) {
    const severity = String(gap.severity || 'medium');
    const severityClass = severity === 'high' ? 'match-competitor' : severity === 'low' ? 'match-uncertain' : 'match-similar';
    const label = severity === 'high' ? '高' : severity === 'low' ? '低' : '中';
    return '<div class="gap-item"><span class="match-pill ' + severityClass + '">' + label + '</span><div class="gap-copy"><b>' + esc(gap.label || gap.code || '数据缺口') + '</b>' + esc(gap.detail || '') + '<div class="gap-code">' + esc(gap.code || '') + '</div></div></div>';
  }

  function renderModal(kind) {
    if (kind === 'intro') return renderIntroModal();
    if (kind === 'about') return renderAboutModal();
    if (kind === 'reviews') return renderReviewsModal();
    return '';
  }

  function renderIntroModal() {
    return '<div class="modal-backdrop"><div class="modal modal-lg" role="dialog" aria-modal="true" aria-labelledby="intro-title">'
      + '<div class="modal-head"><div><div class="modal-kicker">REVIEWAGENT · OBJECT LAYER</div><h2 id="intro-title">先确认对象，再谈口碑</h2></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="关闭">' + icon('x') + '</button></div>'
      + '<div class="modal-body"><p>这是 v2 的对象层报告：能解析的解析，不能解析的明确标出来。页面先给出对象、同款与证据，再决定要不要继续补评论。</p>'
      + '<ul class="modal-list">'
      + '<li>' + icon('box') + '<div><b>商品对象</b><span>从公开商品页提取标题、品牌、店铺、类目与规格；淘宝、天猫、小红书只识别链接，不假装解析。</span></div></li>'
      + '<li>' + icon('users') + '<div><b>同款候选</b><span>同一 SPU 的规格直接标为同款；补充链接按品牌、型号与标题逐项比较，理由和不一致都写出来。</span></div></li>'
      + '<li>' + icon('alert') + '<div><b>评论为空</b><span>不生成口碑分、痛点或引语，只给出缺口和下一步。空列表不代表没有痛点。</span></div></li>'
      + '<li>' + icon('shield') + '<div><b>数据可回溯</b><span>每条结论带 evidence 与 method；原页面链接可点开，查不到的缺口直接列出来。</span></div></li>'
      + '</ul></div>'
      + '<div class="modal-foot"><label class="checkline"><input id="intro-dont-show" type="checkbox" /> 不再自动显示</label><button class="btn btn-primary" type="button" data-action="intro-close">开始查看</button></div>'
      + '</div></div>';
  }

  function renderAboutModal() {
    return '<div class="modal-backdrop"><div class="modal modal-lg" role="dialog" aria-modal="true" aria-labelledby="about-title">'
      + '<div class="modal-head"><div><div class="modal-kicker">ABOUT</div><h2 id="about-title">这份报告怎么来的</h2></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="关闭">' + icon('x') + '</button></div>'
      + '<div class="modal-body"><p>ReviewAgent v2 把“对象确认”和“口碑分析”拆开。当前页面只完成第一段：解析商品对象、匹配同款、记录证据与缺口。</p>'
      + '<div class="about-section"><h3>解析</h3><p>京东移动商品页的 <span class="mono">window._itemOnly</span> 提供标题、品牌、店铺与同 SPU 规格；淘宝、天猫、小红书链接只提取平台与 ID，不伪造标题。</p></div>'
      + '<div class="about-section"><h3>匹配</h3><p>同一 SPU 的不同规格直接标为同款；其他候选按品牌一致、型号词重合、标题相似度与类目比较。价格、销量、评论数不从页面猜，统一留空。</p></div>'
      + '<div class="about-section"><h3>报告</h3><p>对象层结论、候选、证据、缺口和下一步。没有评论样本时，口碑分、风险、痛点和运营方案都不生成；补入评论后只计算 Trust Report，情绪与痛点仍需完整分析。</p></div>'
      + '<div class="about-section"><h3>本机</h3><p>FastAPI 提供 <span class="mono">/v1/analysis</span>，报告存在本机 SQLite；页面是原生 HTML/CSS/JS，不加载 CDN。API 文档在 <a href="/docs" target="_blank" rel="noreferrer">/docs</a>。</p></div>'
      + '</div><div class="modal-foot"><span class="faint">对象层 · 不登录 · 不编数字</span><button class="btn" type="button" data-action="close-modal">知道了</button></div>'
      + '</div></div>';
  }

  function renderReviewsModal() {
    const initial = state.reviews && state.reviews.length ? JSON.stringify(state.reviews, null, 2) : '';
    return '<div class="modal-backdrop"><div class="modal modal-lg" role="dialog" aria-modal="true" aria-labelledby="reviews-title">'
      + '<div class="modal-head"><div><div class="modal-kicker">REVIEW SAMPLES</div><h2 id="reviews-title">补评论样本</h2></div><button class="icon-btn" type="button" data-action="close-modal" aria-label="关闭">' + icon('x') + '</button></div>'
      + '<form id="reviews-form" novalidate><div class="modal-body"><p>每行一条评论，或粘贴 JSON 数组。系统会用这些样本重算 Trust Report；痛点和运营方案仍需要完整分析，不会凭空生成。</p>'
      + '<label class="field" style="margin-top:12px"><span class="field-label">评论样本 <small>最多 500 条</small></span>'
      + '<textarea class="textarea" id="reviews-input" name="reviews" style="min-height:190px;font-family:var(--mono);font-size:11px" placeholder="穿了两次就起球，和详情页说的不一样&#10;2026-10-01, 京东, 尺码偏小&#10;&#10;也支持：[{&quot;review_text&quot;:&quot;...&quot;,&quot;review_date&quot;:&quot;2026-10-01&quot;,&quot;platform&quot;:&quot;jd&quot;}]">' + esc(initial) + '</textarea></label>'
      + '<div class="form-hint" style="margin-top:7px">字段：review_text 必填；review_date / platform / rating 可选。当前配置不调用 LLM，评论只用于本机 Trust Report 统计。</div>'
      + '</div><div class="modal-foot"><button class="btn" type="button" data-action="close-modal">取消</button><button class="btn btn-primary" type="submit">' + icon('refresh') + '重算报告</button></div></form>'
      + '</div></div>';
  }

  function openModal(kind) {
    closeSidebar();
    const root = $('#modal-root');
    if (!root) return;
    const html = renderModal(kind);
    if (!html) return;
    root.innerHTML = html;
    document.body.classList.add('modal-open');
    const first = $('#modal-root .modal button, #modal-root .modal input, #modal-root .modal textarea');
    if (first) window.setTimeout(() => first.focus(), 30);
  }

  function closeModal() {
    const root = $('#modal-root');
    if (root) root.innerHTML = '';
    document.body.classList.remove('modal-open');
  }

  function openReviews() {
    if (!state.analysis) {
      toast('先完成一次对象解析，再补评论样本');
      return;
    }
    openModal('reviews');
  }

  function submitReviews() {
    const input = $('#reviews-input');
    if (!input) return;
    let reviews;
    try {
      reviews = parseReviews(input.value);
    } catch (err) {
      toast(err.message, 'error');
      return;
    }
    const analysis = state.analysis;
    if (!analysis) {
      closeModal();
      toast('先完成一次对象解析，再补评论样本');
      return;
    }
    closeModal();
    const attempt = {
      input: analysis.input,
      extra_links: state.extraLinks,
      ownership: state.ownership,
      reviews
    };
    state.lastAttempt = attempt;
    runAnalysis(attempt);
  }

  function toggleSidebar() {
    const sidebar = $('#sidebar');
    const scrim = $('#sidebar-scrim');
    const button = $('#btn-menu');
    if (!sidebar) return;
    const open = !sidebar.classList.contains('is-open');
    sidebar.classList.toggle('is-open', open);
    if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (scrim) scrim.hidden = !open;
    document.body.classList.toggle('sidebar-open', open);
  }

  function closeSidebar() {
    const sidebar = $('#sidebar');
    const scrim = $('#sidebar-scrim');
    const button = $('#btn-menu');
    if (sidebar) sidebar.classList.remove('is-open');
    if (scrim) scrim.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('sidebar-open');
  }

  function setTab(group, options) {
    const opts = options || {};
    if (!TABS.some((tab) => tab.group === group)) group = 'overview';
    state.tab = group;
    if (!opts.keepTarget) state.activeTarget = FIRST_TARGET[group];
    updateTabs();
    renderSidebarState();
    if (opts.target) state.activeTarget = opts.target;
    setActiveSide(state.activeTarget);
    if (opts.scroll) {
      window.requestAnimationFrame(() => {
        const zone = $('#tabs-zone');
        if (zone) {
          const top = zone.getBoundingClientRect().top + window.scrollY - 64;
          window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        }
      });
    }
    if (opts.target) {
      window.requestAnimationFrame(() => {
        const target = document.getElementById(opts.target);
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  }

  function handleSideClick(button) {
    if (!state.analysis) {
      toast('先开始一次分析，目录会在报告生成后可用');
      return;
    }
    const target = button.dataset.target;
    const group = button.dataset.group;
    closeSidebar();
    setTab(group, { keepTarget: true, target });
  }

  function scrollToTarget(target) {
    if (!target) return;
    const group = TARGET_GROUP[target] || state.tab;
    setTab(group, { keepTarget: true, target });
  }

  async function runAnalysis(options) {
    if (state.loading) return;
    const input = String(options && options.input || '').trim();
    if (!input) {
      toast('请先粘贴商品链接或商品名');
      focusInput();
      return;
    }
    const extraLinks = Array.isArray(options.extra_links) ? options.extra_links.slice(0, 20) : [];
    const reviews = Array.isArray(options.reviews) ? options.reviews.slice(0, 500) : [];
    const ownership = options.ownership === 'competitor' ? 'competitor' : 'own';
    state.loading = true;
    state.error = '';
    state.draftInput = input;
    state.extraDraft = extraLinks.join('\n');
    render();

    let ok = false;
    let successMessage = '';
    try {
      const payload = {
        input,
        extra_links: extraLinks,
        ownership,
        tier: 'standard',
        window_months: 12,
        save: true
      };
      if (reviews.length) payload.reviews = reviews;
      const response = await fetch(API + '/analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(apiError(data, response.status));
      if (!data.analysis_id || !data.report) throw new Error('接口返回缺少报告字段');
      state.analysis = data;
      state.ownership = data.report && data.report.object && data.report.object.ownership === 'competitor' ? 'competitor' : ownership;
      state.draftInput = data.input || input;
      state.extraLinks = extraLinks;
      state.extraDraft = extraLinks.join('\n');
      state.reviews = reviews;
      state.error = '';
      state.apiOffline = false;
      state.tab = 'overview';
      state.activeTarget = 'sec-overview';
      localStorage.setItem('ra.lastAnalysis', data.analysis_id);
      await loadRecent();
      const trust = data.report && data.report.diagnosis && data.report.diagnosis.trust;
      successMessage = trust && trust.overall_trust_score != null
        ? '已用 ' + reviews.length + ' 条评论重算 Trust Report；痛点与运营方案仍未生成'
        : '报告已生成：' + (data.status_label || '对象层');
      ok = true;
    } catch (err) {
      state.error = err && err.message ? err.message : '分析失败';
      state.apiOffline = err instanceof TypeError;
      toast(state.error, 'error');
    } finally {
      state.loading = false;
      render();
      if (ok) {
        toast(successMessage);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
  }

  function focusInput() {
    const input = $('#analysis-input');
    if (input) {
      input.focus();
      input.select && input.select();
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function submitAnalysisForm() {
    const input = $('#analysis-input');
    if (!input) return;
    const value = input.value.trim();
    if (!value) {
      toast('请先粘贴商品链接或商品名');
      input.focus();
      return;
    }
    const same = state.analysis && value === state.analysis.input;
    const attempt = {
      input: value,
      extra_links: same ? state.extraLinks : [],
      reviews: same ? state.reviews : [],
      ownership: state.ownership
    };
    state.lastAttempt = attempt;
    runAnalysis(attempt);
  }

  function submitExtraForm() {
    if (!state.analysis) return;
    const field = $('#extra-links');
    if (!field) return;
    const links = parseLinks(field.value);
    if (!links.length) {
      toast('至少粘贴一个同款链接');
      field.focus();
      return;
    }
    state.extraDraft = field.value;
    state.extraLinks = links;
    const attempt = {
      input: state.analysis.input,
      extra_links: links,
      reviews: state.reviews,
      ownership: state.ownership
    };
    state.lastAttempt = attempt;
    runAnalysis(attempt);
  }

  function handleOwnership(value) {
    if (state.loading) return;
    const next = value === 'competitor' ? 'competitor' : 'own';
    if (state.ownership === next) return;
    state.ownership = next;
    if (!state.analysis) {
      render();
      return;
    }
    const attempt = {
      input: state.analysis.input,
      extra_links: state.extraLinks,
      reviews: state.reviews,
      ownership: next
    };
    state.lastAttempt = attempt;
    toast(next === 'competitor' ? '正在按「竞品」重建报告' : '正在按「自家商品」重建报告');
    runAnalysis(attempt);
  }

  function handleRetry() {
    if (state.lastAttempt) {
      runAnalysis(state.lastAttempt);
      return;
    }
    const input = state.draftInput || (state.analysis && state.analysis.input) || '';
    if (input.trim()) {
      runAnalysis({ input, extra_links: state.extraLinks, reviews: state.reviews, ownership: state.ownership });
    } else {
      focusInput();
    }
  }

  function handleDownloadCsv() {
    const analysis = state.analysis;
    const actions = analysis && analysis.report && Array.isArray(analysis.report.actions) ? analysis.report.actions : [];
    if (!analysis || !actions.length) {
      toast('运营动作尚未生成，CSV 只有表头');
      return;
    }
    const link = document.createElement('a');
    link.href = API + '/analysis/' + encodeURIComponent(analysis.analysis_id) + '/actions.csv';
    link.download = 'reviewagent-actions-' + analysis.analysis_id + '.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function handlePrint() {
    if (!state.analysis) {
      toast('先完成一次分析，再打印报告');
      return;
    }
    closeModal();
    closeSidebar();
    window.setTimeout(() => window.print(), 120);
  }

  async function loadRecent() {
    try {
      const response = await fetch(API + '/analysis?limit=6', { headers: { 'Accept': 'application/json' } });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      state.recent = Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []);
      if (state.analysis) state.apiOffline = false;
    } catch (err) {
      state.recent = [];
      if (err instanceof TypeError && !state.analysis) state.apiOffline = true;
    }
  }

  async function restoreLast() {
    const id = localStorage.getItem('ra.lastAnalysis');
    if (!id) return;
    try {
      const response = await fetch(API + '/analysis/' + encodeURIComponent(id), { headers: { 'Accept': 'application/json' } });
      if (response.status === 404) {
        localStorage.removeItem('ra.lastAnalysis');
        return;
      }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!data || !data.report) {
        localStorage.removeItem('ra.lastAnalysis');
        return;
      }
      state.analysis = data;
      state.draftInput = data.input || '';
      state.ownership = data.report && data.report.object && data.report.object.ownership === 'competitor' ? 'competitor' : 'own';
      state.tab = 'overview';
      state.activeTarget = 'sec-overview';
    } catch (err) {
      if (err instanceof TypeError) state.apiOffline = true;
    }
  }

  async function openRecent(id) {
    if (!id || state.loading) return;
    state.loading = true;
    state.error = '';
    render();
    let ok = false;
    try {
      const response = await fetch(API + '/analysis/' + encodeURIComponent(id), { headers: { 'Accept': 'application/json' } });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(apiError(data, response.status));
      if (!data.report) throw new Error('这条记录缺少报告内容');
      state.analysis = data;
      state.draftInput = data.input || '';
      state.extraDraft = '';
      state.extraLinks = [];
      state.reviews = [];
      state.ownership = data.report && data.report.object && data.report.object.ownership === 'competitor' ? 'competitor' : 'own';
      state.tab = 'overview';
      state.activeTarget = 'sec-overview';
      localStorage.setItem('ra.lastAnalysis', data.analysis_id || id);
      ok = true;
    } catch (err) {
      state.error = err && err.message ? err.message : '读取记录失败';
      toast(state.error, 'error');
    } finally {
      state.loading = false;
      render();
      if (ok) {
        toast('已恢复最近一次分析');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
  }

  function resetToNew() {
    closeSidebar();
    closeModal();
    state.analysis = null;
    state.error = '';
    state.loading = false;
    state.draftInput = '';
    state.extraDraft = '';
    state.extraLinks = [];
    state.reviews = [];
    state.ownership = 'own';
    state.tab = 'overview';
    state.activeTarget = 'sec-overview';
    state.lastAttempt = null;
    localStorage.removeItem('ra.lastAnalysis');
    render();
    window.setTimeout(() => {
      const input = $('#analysis-input');
      if (input) input.focus();
    }, 30);
  }

  function fillSample() {
    state.draftInput = 'https://item.jd.com/100012043978.html';
    const input = $('#analysis-input');
    if (input) {
      input.value = state.draftInput;
      input.focus();
      input.select && input.select();
    }
    toast('示例为京东茅台；可替换成你的商品链接');
  }

  function handleDelegatedClick(event) {
    const side = event.target.closest('.side-link[data-target]');
    if (side) {
      event.preventDefault();
      handleSideClick(side);
      return;
    }
    const tab = event.target.closest('.tab[data-group]');
    if (tab) {
      event.preventDefault();
      setTab(tab.dataset.group, { scroll: true });
      return;
    }
    const actionEl = event.target.closest('[data-action]');
    if (!actionEl) return;
    const action = actionEl.dataset.action;
    switch (action) {
      case 'fill-sample': fillSample(); break;
      case 'ownership': handleOwnership(actionEl.dataset.value); break;
      case 'scroll-to': scrollToTarget(actionEl.dataset.target); break;
      case 'open-recent': openRecent(actionEl.dataset.id); break;
      case 'open-about': openModal('about'); break;
      case 'close-modal': closeModal(); break;
      case 'intro-close':
        if ($('#intro-dont-show') && $('#intro-dont-show').checked) localStorage.setItem('ra.introSeen', '1');
        closeModal();
        break;
      case 'guide-reviews': openReviews(); break;
      case 'download-csv': handleDownloadCsv(); break;
      case 'print': handlePrint(); break;
      case 'focus-input': focusInput(); break;
      case 'retry': handleRetry(); break;
      default: break;
    }
  }

  function handleSubmit(event) {
    if (event.target.id === 'analysis-form') {
      event.preventDefault();
      submitAnalysisForm();
      return;
    }
    if (event.target.id === 'extra-form') {
      event.preventDefault();
      submitExtraForm();
      return;
    }
    if (event.target.id === 'reviews-form') {
      event.preventDefault();
      submitReviews();
    }
  }

  function handleInput(event) {
    if (event.target.id === 'analysis-input') state.draftInput = event.target.value;
    if (event.target.id === 'extra-links') state.extraDraft = event.target.value;
  }

  function handleKeydown(event) {
    if (event.key === 'Escape') {
      if ($('#modal-root') && $('#modal-root').children.length) {
        closeModal();
        return;
      }
      if ($('#sidebar') && $('#sidebar').classList.contains('is-open')) closeSidebar();
    }
  }

  function bindStatic() {
    const newButton = $('#btn-new');
    if (newButton) newButton.addEventListener('click', resetToNew);
    const printButton = $('#btn-print');
    if (printButton) printButton.addEventListener('click', handlePrint);
    const themeButton = $('#btn-theme');
    if (themeButton) themeButton.addEventListener('click', toggleTheme);
    const aboutButton = $('#btn-about');
    if (aboutButton) aboutButton.addEventListener('click', () => openModal('about'));
    const aboutSide = $('#btn-about-side');
    if (aboutSide) aboutSide.addEventListener('click', () => openModal('about'));
    const menuButton = $('#btn-menu');
    if (menuButton) menuButton.addEventListener('click', toggleSidebar);
    const scrim = $('#sidebar-scrim');
    if (scrim) scrim.addEventListener('click', closeSidebar);
    const modalRoot = $('#modal-root');
    if (modalRoot) {
      modalRoot.addEventListener('click', (event) => {
        if (event.target && event.target.classList && event.target.classList.contains('modal-backdrop')) closeModal();
      });
    }
    document.addEventListener('click', handleDelegatedClick);
    document.addEventListener('submit', handleSubmit);
    document.addEventListener('input', handleInput);
    document.addEventListener('keydown', handleKeydown);
    window.addEventListener('resize', () => {
      if (window.innerWidth > 980) closeSidebar();
    });
  }

  function maybeIntro() {
    if (new URLSearchParams(window.location.search).get('intro') === '0') return;
    if (localStorage.getItem('ra.introSeen') === '1') return;
    window.setTimeout(() => openModal('intro'), 450);
  }

  async function init() {
    applyTheme(readTheme());
    bindStatic();
    state.loading = true;
    render();
    await Promise.all([loadRecent(), restoreLast()]);
    state.loading = false;
    render();
    maybeIntro();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
