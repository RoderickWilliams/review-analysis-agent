/* ReviewAgent v2 Web UI — interactions */
(function () {
  'use strict';

  var root = document.documentElement;
  var THEME_KEY = 'ra-theme';
  var INTRO_KEY = 'ra-intro-seen';
  var themeOrder = ['system', 'light', 'dark'];
  var themeLabels = { system: '跟随系统', light: '浅色', dark: '深色' };
  var theme = 'system';

  function readStore(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function writeStore(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }
  function systemDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function effectiveTheme(pref) {
    if (pref === 'system') return systemDark() ? 'dark' : 'light';
    return pref;
  }
  function applyTheme(pref, announce) {
    theme = themeOrder.indexOf(pref) >= 0 ? pref : 'system';
    root.dataset.theme = effectiveTheme(theme);
    root.dataset.themePref = theme;
    var btn = document.getElementById('theme-btn');
    if (btn) {
      var label = '切换主题：' + themeLabels[theme];
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label + '（点击切换）');
    }
    if (announce) toast('主题：' + themeLabels[theme]);
  }

  function initTheme() {
    var saved = readStore(THEME_KEY);
    applyTheme(saved || 'system', false);
    var btn = document.getElementById('theme-btn');
    if (btn) {
      btn.addEventListener('click', function () {
        var idx = themeOrder.indexOf(theme);
        var next = themeOrder[(idx + 1) % themeOrder.length];
        writeStore(THEME_KEY, next);
        applyTheme(next, true);
      });
    }
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function () {
        if (theme === 'system') applyTheme('system', false);
      };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  }

  var toastTimer = null;
  function toast(message) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('is-visible');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('is-visible'); }, 3600);
  }

  var tabButtons = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.tab-panel'));
  var navItems = Array.prototype.slice.call(document.querySelectorAll('.nav-item'));

  function panelForTab(name) {
    return document.getElementById('panel-' + name);
  }

  function activateTab(name, options) {
    options = options || {};
    var panel = panelForTab(name);
    if (!panel) return;
    tabButtons.forEach(function (btn) {
      var active = btn.dataset.tab === name;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.tabIndex = active ? 0 : -1;
    });
    panels.forEach(function (p) {
      var active = p.id === panel.id;
      p.classList.toggle('is-active', active);
      p.hidden = !active;
    });
    navItems.forEach(function (item) {
      if (item.closest('.side-nav')) {
        var active = item.dataset.tab === name;
        item.classList.toggle('is-active', active);
      }
    });
    if (options.updateHash !== false) {
      if (history.replaceState) history.replaceState(null, '', '#' + panel.id);
      else location.hash = panel.id;
    }
    if (options.focusTab) {
      var current = tabButtons.filter(function (b) { return b.dataset.tab === name; })[0];
      if (current) current.focus();
    }
  }

  function initTabs() {
    tabButtons.forEach(function (btn, index) {
      btn.addEventListener('click', function () {
        activateTab(btn.dataset.tab, { focusTab: false });
      });
      btn.addEventListener('keydown', function (event) {
        var key = event.key;
        var next = null;
        if (key === 'ArrowRight') next = (index + 1) % tabButtons.length;
        if (key === 'ArrowLeft') next = (index - 1 + tabButtons.length) % tabButtons.length;
        if (key === 'Home') next = 0;
        if (key === 'End') next = tabButtons.length - 1;
        if (next !== null) {
          event.preventDefault();
          activateTab(tabButtons[next].dataset.tab, { focusTab: true });
        }
      });
    });

    navItems.forEach(function (item) {
      item.addEventListener('click', function (event) {
        var targetId = item.dataset.target;
        var target = targetId ? document.getElementById(targetId) : null;
        if (item.dataset.tab) {
          event.preventDefault();
          activateTab(item.dataset.tab, { updateHash: false });
          closeSidebar();
          navItems.forEach(function (other) { other.classList.remove('is-active'); });
          item.classList.add('is-active');
          if (target) {
            setTimeout(function () {
              target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 30);
          }
        }
      });
    });

    document.querySelectorAll('[data-tab-link]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        var tab = link.dataset.tabLink;
        var targetId = link.dataset.target;
        var target = targetId ? document.getElementById(targetId) : null;
        event.preventDefault();
        activateTab(tab, { updateHash: false });
        if (target) {
          setTimeout(function () { target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 30);
        }
      });
    });
  }

  function initHash() {
    var hash = (location.hash || '').replace('#', '');
    if (!hash) return;
    var target = document.getElementById(hash);
    if (!target) return;
    var panel = target.closest ? target.closest('.tab-panel') : null;
    if (panel) {
      var tab = panel.id.replace('panel-', '');
      activateTab(tab, { updateHash: false });
      setTimeout(function () { target.scrollIntoView({ block: 'start' }); }, 60);
    }
  }

  function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    var toggle = document.getElementById('menu-toggle');
    if (sidebar) sidebar.classList.remove('is-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  function initSidebar() {
    var sidebar = document.getElementById('sidebar');
    var toggle = document.getElementById('menu-toggle');
    if (!sidebar || !toggle) return;
    toggle.addEventListener('click', function () {
      var open = sidebar.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (event) {
      if (window.innerWidth > 860) return;
      if (!sidebar.classList.contains('is-open')) return;
      if (sidebar.contains(event.target) || toggle.contains(event.target)) return;
      closeSidebar();
    });
  }

  function initIntro() {
    var dialog = document.getElementById('intro-dialog');
    if (!dialog) return;
    function open() {
      if (typeof dialog.showModal === 'function') {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute('open', '');
      }
    }
    function close() {
      writeStore(INTRO_KEY, '1');
      if (typeof dialog.close === 'function' && dialog.open) dialog.close();
      else dialog.removeAttribute('open');
    }
    var closeBtn = document.getElementById('intro-close');
    var startBtn = document.getElementById('intro-start');
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (startBtn) startBtn.addEventListener('click', close);
    dialog.addEventListener('close', function () { writeStore(INTRO_KEY, '1'); });
    dialog.addEventListener('click', function (event) {
      if (event.target === dialog) close();
    });
    var about1 = document.getElementById('about-btn');
    var about2 = document.getElementById('about-btn-2');
    if (about1) about1.addEventListener('click', open);
    if (about2) about2.addEventListener('click', open);
    if (!readStore(INTRO_KEY)) {
      setTimeout(open, 650);
    }
  }

  var evidenceMap = {
    'ev-summary': {
      title: '结论依据（示例）',
      items: [
        { quote: '「说是防晒，但没写 UPF 和检测口径」', meta: '示例用户 A · 小红书 · 演示' },
        { quote: '「轻是轻，但说不出和别的差多少」', meta: '示例用户 B · 淘宝 · 演示' }
      ],
      note: '结论由痛点频次与严重度合成；正式版会附原文链接、采集时间和匹配规则。'
    },
    'ev-uv': {
      title: '防晒参数缺失',
      items: [
        { quote: '「说是防晒，但没写 UPF 和检测口径」', meta: '示例用户 A · 小红书 · 演示' },
        { quote: '「详情页只写了防晒，没写洗后还能不能防」', meta: '示例用户 C · 京东 · 演示' }
      ],
      note: '示例引语；正式版只有在原文或图片文字中找到的引语才进入榜单。'
    },
    'ev-wash': {
      title: '洗后防护疑问',
      items: [
        { quote: '「洗了两次，不知道还能不能防」', meta: '示例用户 D · 淘宝 · 演示' }
      ],
      note: '正式版会把「洗护说明缺失」和「效果承诺」分开，不混为同一类。'
    },
    'ev-size': {
      title: '尺码与版型',
      items: [
        { quote: '「按平时码买，肩部偏紧」', meta: '示例用户 E · 京东 · 演示' }
      ],
      note: '尺码问题需要结合退货原因与商品参数复核，演示版只给方向。'
    },
    'ev-light': {
      title: '「轻」的表达',
      items: [
        { quote: '「轻是轻，但说不出和别的差多少」', meta: '示例用户 B · 淘宝 · 演示' }
      ],
      note: '建议补重量、收纳体积、上身对比三项中的至少两项。'
    },
    'ev-topic': {
      title: '选题依据',
      items: [
        { quote: '「早八通勤，想要一件不闷的防晒衣」', meta: '示例用户 F · 小红书 · 演示' },
        { quote: '「通勤 30 分钟，值不值得买」', meta: '示例用户 G · 小红书 · 演示' }
      ],
      note: '选题只给角度与骨架，不冒充真实用户原话，不承诺效果。'
    },
    'ev-risk': {
      title: '风险信号（示例）',
      items: [
        { quote: '评分 5 星，文本主要描述物流', meta: '规则：评分-文本轻微不一致 · 演示' },
        { quote: '两条评论文本完全相同', meta: '规则：重复文本 · 已降权 · 演示' }
      ],
      note: '正式版会给出信号贡献、样本量和人工复核入口。'
    },
    'ev-method': {
      title: '方法说明',
      items: [
        { quote: '事实层：原句、评分、时间、链接、数量来自采集', meta: '方法' },
        { quote: '统计层：占比、频次、信任分由程序计算', meta: '方法' },
        { quote: '建议层：运营动作、改进、选题标「建议」并附依据', meta: '方法' },
        { quote: '文案层：草稿标「建议/草稿」，不编参数、认证、销量、效果承诺', meta: '方法' }
      ],
      note: '演示版不调用模型，不产生真实结论；完整版按这四层输出。'
    }
  };

  function openEvidence(key) {
    var dialog = document.getElementById('evidence-dialog');
    var body = document.getElementById('evidence-body');
    var title = document.getElementById('evidence-title');
    if (!dialog || !body || !title) return;
    var data = evidenceMap[key];
    if (!data) {
      data = { title: '证据', items: [{ quote: '演示版暂无这条证据。', meta: '演示' }], note: '' };
    }
    title.textContent = data.title;
    body.textContent = '';
    var list = document.createElement('div');
    list.className = 'evidence-list';
    data.items.forEach(function (item) {
      var block = document.createElement('blockquote');
      block.className = 'evidence-quote';
      var q = document.createElement('p');
      q.textContent = item.quote;
      var m = document.createElement('footer');
      m.textContent = item.meta;
      block.appendChild(q);
      block.appendChild(m);
      list.appendChild(block);
    });
    body.appendChild(list);
    if (data.note) {
      var note = document.createElement('p');
      note.className = 'footnote';
      note.textContent = data.note;
      body.appendChild(note);
    }
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function initEvidence() {
    var dialog = document.getElementById('evidence-dialog');
    if (!dialog) return;
    document.querySelectorAll('[data-evidence]').forEach(function (btn) {
      btn.addEventListener('click', function () { openEvidence(btn.dataset.evidence); });
    });
    function close() {
      if (typeof dialog.close === 'function' && dialog.open) dialog.close();
      else dialog.removeAttribute('open');
    }
    var closeBtn = document.getElementById('evidence-close');
    var okBtn = document.getElementById('evidence-ok');
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (okBtn) okBtn.addEventListener('click', close);
    dialog.addEventListener('click', function (event) {
      if (event.target === dialog) close();
    });
  }

  function tagTableCells() {
    document.querySelectorAll('table').forEach(function (table) {
      var headers = Array.prototype.map.call(
        table.querySelectorAll('thead th'),
        function (th) { return (th.textContent || '').trim(); }
      );
      table.querySelectorAll('tbody tr').forEach(function (row) {
        Array.prototype.forEach.call(row.children, function (cell, index) {
          if (headers[index] && !cell.dataset.label) cell.dataset.label = headers[index];
        });
      });
    });
  }

  function detectInput(value) {
    var text = String(value || '').trim();
    if (!text) return { kind: 'empty', label: '空输入' };
    if (/item\.jd\.com|jd\.com\/product/i.test(text)) return { kind: 'jd', label: '京东商品链接' };
    if (/taobao\.com|tmall\.com/i.test(text)) return { kind: 'taobao', label: '淘宝 / 天猫商品链接' };
    if (/xiaohongshu\.com|xhslink\.com/i.test(text)) return { kind: 'xhs', label: '小红书笔记或商品链接' };
    return { kind: 'name', label: '商品名' };
  }

  function initAnalyze() {
    var form = document.getElementById('analyze-form');
    var input = document.getElementById('object-input');
    if (!form || !input) return;
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var detected = detectInput(input.value);
      if (detected.kind === 'empty') {
        toast('先粘贴一个商品/笔记链接，或输入商品名。');
        input.focus();
        return;
      }
      toast('演示版：已识别为「' + detected.label + '」。真实服务会先显示分析对象卡片，确认归属与档位后再采集。');
    });
    var newBtn = document.getElementById('new-analysis');
    if (newBtn) {
      newBtn.addEventListener('click', function () {
        closeSidebar();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setTimeout(function () { input.focus(); }, 120);
      });
    }
  }

  function initTier() {
    var select = document.getElementById('tier-select');
    var label = document.getElementById('tier-label');
    if (!select || !label) return;
    var names = { light: '轻量', standard: '标准', deep: '深度', custom: '自定义' };
    select.addEventListener('change', function () {
      var name = names[select.value] || '标准';
      label.textContent = name;
      if (select.value === 'custom') {
        toast('演示版：自定义上限会在完整版打开输入窗口，单项最高值由程序限制。');
      } else {
        toast('已切换为「' + name + '」档；完整版会增量重跑，不重复采集已完成部分。');
      }
    });
  }

  function downloadActions() {
    var rows = [
      ['优先级', '动作', '为什么', '怎么验证', '依据', '负责人', '截止时间'],
      ['P0', '补防晒参数与检测口径', '痛点 01 频次最高，直接影响下单', '客服重复咨询量、退货原因', '示例证据 ev-uv', '', ''],
      ['P1', '详情页加入「轻量三细节」', '「轻」被认可，但缺少可感知对比', '停留时长、加购率', '示例证据 ev-light', '', ''],
      ['P1', '发 3 篇通勤场景笔记', '用真实场景承接搜索，不承诺效果', '收藏、评论问题类型', '示例证据 ev-topic', '', ''],
      ['P2', '测试两件装组合', '给不同预算一个选择，不直接降价', '客单价、转化率', '样本不足，待补', '', '']
    ];
    var lines = rows.map(function (row) {
      return row.map(function (cell) {
        return '"' + String(cell).replace(/"/g, '""') + '"';
      }).join(',');
    });
    var csv = '\ufeff' + lines.join('\r\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'reviewagent-actions-demo.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    toast('演示行动清单已导出。数字与依据为占位内容，正式版由分析结果生成。');
  }

  function initActions() {
    var ids = ['download-actions', 'download-actions-2'];
    ids.forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', downloadActions);
    });
    var generate = document.getElementById('generate-ops');
    var note = document.getElementById('ops-note');
    if (generate) {
      generate.addEventListener('click', function () {
        if (note) note.hidden = false;
        generate.textContent = '已生成（演示）';
        toast('运营方案骨架已生成并缓存；完整版会按分析结果生成可下载的详细方案。');
        var plan = document.getElementById('ops-plan');
        if (plan) plan.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
    var printBtn = document.getElementById('print-btn');
    if (printBtn) printBtn.addEventListener('click', function () { window.print(); });
  }

  function init() {
    tagTableCells();
    initTheme();
    initTabs();
    initHash();
    initSidebar();
    initIntro();
    initEvidence();
    initAnalyze();
    initTier();
    initActions();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
