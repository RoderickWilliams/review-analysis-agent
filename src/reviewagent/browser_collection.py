"""Bounded collection in the same owned profiles used for QR login."""
from __future__ import annotations

import hashlib
import re
import time
import random
import threading
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from reviewagent.auto_login import AutoLoginManager
from reviewagent.browser_session import BrowserNavigationError, open_driver, platform_key, record_authenticated


_platform_guards = {name: threading.Lock() for name in ("jd", "taobao", "xhs")}
_next_platform_access = {}


class CollectionPaused(ValueError):
    def __init__(self, message, *, code="needs_input"):
        super().__init__(message)
        self.code = code


_DEFAULT_COMMENT = re.compile(r"^该用户觉得商品(?:非常好|还不错|一般|不好|很差)[，,]?\s*给出\s*\d\s*星好评$")


def _is_default_comment(text):
    """Star-only reviews carry a platform placeholder instead of buyer words."""
    return bool(_DEFAULT_COMMENT.match((text or "").strip()))


class ReviewBatch(list):
    """Collected rows plus the page facts used to explain a collection gap."""

    def __init__(self, rows=(), facts=None):
        super().__init__(rows)
        self.facts = facts or {}


def _allowed_url(url, platform):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    domains = {"jd": ("jd.com",), "taobao": ("taobao.com", "tmall.com", "tb.cn"),
               "xhs": ("xiaohongshu.com", "xhslink.com", "xhslink.cn")}[platform_key(platform)]
    return parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.port in {None, 443} and any(host == d or host.endswith("." + d) for d in domains)


def _page_state(driver, platform):
    current_url = (driver.current_url or "").strip()
    if not current_url or current_url.lower() in {"about:blank", "chrome://newtab/", "chrome://new-tab-page/", "edge://newtab/"}:
        return "blank_page"
    if not _allowed_url(current_url, platform):
        return "unsupported_redirect"
    path = urlsplit(current_url).path.lower()
    host = (urlsplit(current_url).hostname or "").lower()
    if platform_key(platform) == "jd" and (host.endswith(".pf.jd.com") or "frequent" in host):
        return "rate_limited"
    login_address = host.startswith(("passport.", "login.")) or "/login" in path
    state = driver.execute_script(r"""
        if (location.protocol !== 'https:' || !document.body || !document.body.innerText.trim()) return 'blank_page';
        const shown = s => [...document.querySelectorAll(s)].some(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
        if (shown('[id*="captcha"], .geetest_panel, .verify-wrap, .nc-container')) return 'verification_required';
        const text = document.body?.innerText || '';
        if (text.length < 10000 && /账号异常|账户异常|账号被冻结|账户被冻结|账号被封禁|账号存在风险|账号被限制/.test(text)) return 'account_restricted';
        if (text.length < 2000 && /访问频繁|操作频繁|请求过于频繁|访问受限|Access Denied|Too Many Requests|暂时无法展示该商品的信息/i.test(text)) return 'rate_limited';
        if (shown('.login-container, .login-modal, .login-mask, #login-dialog')) return 'needs_login';
        if (/登录后.{0,12}(查看|浏览).{0,8}(评价|评论)|请先登录.{0,12}(评价|评论)/.test(text)) return 'needs_login';
        if ([...document.querySelectorAll('iframe[src]')].some(e => e.getClientRects().length && /^https:\/\/(?:login|passport)\.(?:taobao|tmall)\.com\//i.test(e.src))) return 'needs_login';
        if (text.length < 5000 && /商品不存在|商品已下架|找不到该商品|该商品不存在|笔记已删除|笔记不存在|当前笔记暂时无法浏览|你访问的页面不见了|该笔记暂时无法浏览/.test(text)) return 'source_unavailable';
        return 'ready';
    """)
    if state in {"verification_required", "rate_limited", "account_restricted", "source_unavailable"}:
        return state
    if host == "passport.taobao.com" and path.startswith("/iv/"):
        if AutoLoginManager()._is_login_success(driver, platform, allow_login_result=True):
            return "login_complete"
        return "identity_verification"
    if login_address or state == "needs_login":
        if AutoLoginManager()._is_login_success(driver, platform, allow_login_result=True):
            return "login_complete"
        return "needs_login"
    return state


def _wait(seconds, cancelled):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cancelled():
            raise CollectionPaused("已取消，逐批采集进度已保留", code="cancelled")
        time.sleep(min(.25, max(0, deadline - time.monotonic())))


def _review_date(raw):
    """Keep ambiguous/relative dates unknown; the original label is stored too."""
    match = re.search(r"(?<!\d)(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?!\d)", str(raw or ""))
    if not match:
        return ""
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return ""


def _extract(driver, platform):
    if platform == "xhs":
        return driver.execute_script("""
            return [...document.querySelectorAll('.comment-item')].flatMap(card => {
                const body = card.querySelector('.content .note-text, .content .content, .content .text, .content');
                const content = body?.innerText?.trim();
                if (!content) return [];
                return [{content, comment_id:card.getAttribute('data-id') || card.id || '',
                         user_name:card.querySelector('.author .name, .user-name')?.innerText?.trim() || '',
                         time:card.querySelector('.date')?.innerText?.trim() || '', rateScore:null}];
            });
        """) or []
    # Reuse only the existing DOM parser; it does not launch its old browser.
    page = SimpleNamespace(evaluate=lambda script: driver.execute_script("return (" + script + ")();"))
    if platform == "jd":
        from reviewagent.scrapers.jd_playwright_scraper import JDPlaywrightScraper
        return JDPlaywrightScraper._extract_comments_from_dom(SimpleNamespace(_page=page))
    from reviewagent.scrapers.taobao_playwright_scraper import TaobaoPlaywrightScraper
    rows = TaobaoPlaywrightScraper._extract_comments_from_dom(SimpleNamespace(_page=page))
    return [clean for row in rows if (clean := _clean_taobao_card(row))]


def _clean_taobao_card(row):
    """Separate legacy whole-card fallback from buyer text using explicit headers."""
    row = dict(row)
    original = str(row.get('content') or '').strip()
    header = re.match(r'^(.{1,40}?)\s+(\d{4}(?:-\d{1,2}-\d{1,2}|年\d{1,2}月\d{1,2}日))\s*(.*)$', original)
    if not header:
        return row
    user, when, body = header.groups()
    row['user_name'] = row.get('user_name') or user
    row['time'] = row.get('time') or when
    if body.startswith(('已购：', '已购:')):
        purchase = re.match(r'^已购[：:](.*?)\s+\d+\s+\d+\s+(.+)$', body)
        if not purchase:
            return None  # Ambiguous card metadata must not become model evidence.
        row['sku'] = row.get('sku') or purchase.group(1)
        body = purchase.group(2)
    body = re.split(r'\s+商家回复[：:]', body, maxsplit=1)[0].strip()
    row['content'] = body
    row['raw_card_text'] = original
    return row if body else None


def _find_comment_entry(driver, *, all_only=False):
    """Return the innermost review entry with its click point.

    Tmall keeps the handler on the child element, so clicking a text wrapper does nothing.
    """
    return driver.execute_script(r"""
        const allOnly = arguments[0];
        const names = /^(商品评价|宝贝评价|用户评价|评价|累计评价|全部评价|全部评论|查看全部评价|查看全部评论)([（(]?\d+[+万w]?[）)]?)?$/;
        const nodes = [...document.querySelectorAll('a,button,li,span,div')].filter(e => {
            const label = (e.innerText || '').trim();
            return e.getClientRects().length && names.test(label) && (/全部/.test(label) === !!allOnly);
        });
        if (!nodes.length) return null;
        const leaf = nodes.find(e => !nodes.some(other => other !== e && e.contains(other))) || nodes[0];
        leaf.scrollIntoView({block: 'center', inline: 'center'});
        const rect = leaf.getBoundingClientRect();
        return {x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2),
                text: (leaf.innerText || '').trim(), tag: leaf.tagName};
    """, all_only)


def _open_comments(driver, *, all_only=False):
    """Expand the review list; scripted clicks are ignored by some Tmall handlers."""
    target = _find_comment_entry(driver, all_only=all_only)
    if target and hasattr(driver, "click_at"):
        try:
            driver.click_at(target["x"], target["y"])
            return True
        except Exception:
            pass
    if not target and not all_only:
        target = _find_comment_entry(driver, all_only=True)
        if target and hasattr(driver, "click_at"):
            try:
                driver.click_at(target["x"], target["y"])
                return True
            except Exception:
                pass
    if target and not hasattr(driver, "click_at"):
        # Selenium-backed browsers still accept scripted clicks; only the CDP driver needs trusted input.
        return bool(driver.execute_script(r"""
            const allOnly = arguments[0];
            const names = /^(商品评价|宝贝评价|用户评价|评价|累计评价|全部评价|全部评论|查看全部评价|查看全部评论)([（(]?\d+[+万w]?[）)]?)?$/;
            const nodes = [...document.querySelectorAll('a,button,li,span,div')].filter(e => {
                const label = (e.innerText || '').trim();
                return e.getClientRects().length && names.test(label) && (/全部/.test(label) === !!allOnly);
            });
            if (!nodes.length) return false;
            const leaf = nodes.find(e => !nodes.some(other => other !== e && e.contains(other))) || nodes[0];
            leaf.scrollIntoView({block: 'center'});
            leaf.click();
            return true;
        """, all_only))
    return False


_TMALL_RATE_JS = r"""
const page = arguments[0], fold = arguments[1];
if (!(window.lib && window.lib.mtop && window.lib.mtop.request)) return null;
const data = {showTrueCount: false, auctionNumId: AUCTION, pageNo: page, pageSize: 20,
              orderType: '', searchImpr: '-8', expression: '', skuVids: '',
              rateSrc: 'pc_rate_list', rateType: '', foldFlag: fold};
return window.lib.mtop.request({api: 'mtop.taobao.rate.detaillist.get', v: '6.0', type: 'GET', data: data})
  .then(r => {const d = (r && r.data) || {};
             const list = d.rateList || (d.data && d.data.rateList) || [];
             return {rows: list, total: Number(d.total || 0)};})
  .catch(() => ({rows: [], total: -1}));
"""


def _tmall_rate_rows(driver, item_id, limit, cancelled):
    """Page the page's own rate API, including reviews Tmall folds out of the list.

    Returns (rows, ok). ok is False when the page did not expose the mtop library.
    """
    import json as _json
    rows, ok = [], False
    script = _TMALL_RATE_JS.replace("AUCTION", _json.dumps(str(item_id)))
    for fold in ("0", "1"):
        page = 1
        while len(rows) < limit and page <= 10:
            if cancelled():
                return rows, ok
            try:
                data = driver.execute_script(script, page, fold)
            except Exception:
                return rows, ok
            if not isinstance(data, dict) or data.get("total") == -1:
                return rows, ok
            ok = True
            batch = data.get("rows") or []
            if not batch:
                break
            rows.extend(item for item in batch if isinstance(item, dict))
            page += 1
    return rows[:limit], ok


JD_COMMENT_API = "https://club.jd.com/comment/productPageComments.action"


def _jd_api_url(item_id, page, page_size=10):
    return (JD_COMMENT_API + "?productId=" + str(item_id) + "&score=0&sortType=5&page=" + str(page)
            + "&pageSize=" + str(page_size) + "&isShadowSku=0&fold=1")


def _jd_browser_reviews(driver, item_id, limit, cancelled, emit):
    """在专用浏览器会话里直接读京东评论接口。

    纯 requests 会被京东按 444 拒绝；浏览器带着自己的 Cookie 与 TLS 指纹可以拿到 JSON。
    """
    import json as _json
    rows, page = [], 0
    while len(rows) < limit and page < 30:
        if cancelled():
            break
        try:
            driver.get(_jd_api_url(item_id, page))
        except Exception:
            break
        _wait(1, cancelled)
        text = (driver.execute_script("return (document.body && document.body.innerText) || '';") or "").strip()
        try:
            data = _json.loads(text)
        except Exception:
            break
        if not isinstance(data, dict):
            break
        batch = data.get("comments") or []
        if not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                item = dict(item)
                item["_jd_page"] = page + 1
                rows.append(item)
        page += 1
        if emit:
            emit("jd_api", "京东评论接口（浏览器会话）：第 %d 页，累计 %d 条" % (page, len(rows)))
    return rows[:limit]


def _folded_reviews(driver):
    """Return Tmall's folded-review count and the point of its notice."""
    data = driver.execute_script(r"""
        const nodes = [...document.querySelectorAll('*')].filter(e => e.getClientRects().length
            && /已折叠\s*\d+\s*条/.test((e.innerText || '').trim()));
        if (!nodes.length) return null;
        const leaf = nodes.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length)[0];
        const count = ((leaf.innerText || '').trim().match(/已折叠\s*(\d+)\s*条/) || [])[1];
        leaf.scrollIntoView({block: 'center', inline: 'center'});
        const rect = leaf.getBoundingClientRect();
        return {count: count ? Number(count) : 0, x: Math.round(rect.left + rect.width / 2),
                y: Math.round(rect.top + rect.height / 2)};
    """)
    return data or {}


def _comment_page_diagnostics(driver):
    """Record structural signals only; never cookies, page HTML or URL tokens."""
    return driver.execute_script(r"""
        const text = document.body?.innerText || '';
        const labels = [...document.querySelectorAll('button,a,li,span')]
          .filter(e => e.getClientRects().length)
          .map(e => e.innerText?.trim() || '')
          .filter(t => t.length < 35 && /评价|评论|登录/.test(t));
        const classes = [...document.querySelectorAll('[class]')]
          .flatMap(e => [...e.classList]).filter(c => /comment|review|rate|login/i.test(c));
        return {host:location.hostname, path:location.pathname,
          title:document.title, ready_state:document.readyState, text_length:text.trim().length,
          text_preview:text.slice(0,500).replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]+/g,'[邮箱]').replace(/1[3-9]\d{9}/g,'[手机号]'),
          frames:[...document.querySelectorAll('iframe[src]')].map(e => {try {const u=new URL(e.src); return {host:u.hostname,path:u.pathname,visible:!!e.getClientRects().length};} catch {return {};}}).slice(0,10),
          labels:[...new Set(labels)].slice(0,20), classes:[...new Set(classes)].slice(0,30),
          login_gate:/登录后.{0,12}(查看|浏览)|请先登录/.test(text),
          no_reviews:/暂无评价|暂无评论|还没有评价|还没有评论/.test(text)};
    """) or {}


def _degraded_page(snapshot):
    """平台只下发购买区、没有评价模块时返回 True；数据来自页面快照，不推断。"""
    if not isinstance(snapshot, dict):
        return False
    length = snapshot.get("len")
    return (isinstance(length, int) and not isinstance(length, bool) and length < 600
            and not snapshot.get("hasReviews") and (snapshot.get("height") or 0) < 1200)


def _wait_for_comment_section(driver, platform, url, cancelled, emit):
    """Wait for hydrated review controls, not just a product document title."""
    deadline = time.monotonic() + 90
    started = time.monotonic()
    scrolls = 0
    emit('loading_comments', '商品页面仍在加载，等待评价区域出现（最多90秒），请保持窗口打开')
    while time.monotonic() < deadline:
        if cancelled():
            raise CollectionPaused('任务已取消', code='cancelled')
        _await_access(driver, platform, url, cancelled, emit)
        ready = driver.execute_script(r"""
            const shown = e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
            if ([...document.querySelectorAll('.tm-rate-content,.tb-rev-item,[class*="commentItem"],[class*="Comment--"],[class*="rate-item"],#comment-root')].some(shown)) return true;
            return [...document.querySelectorAll('a,button,li,span,div')].some(e => shown(e) && /^(商品评价|宝贝评价|用户评价|累计评价|全部评价|查看全部评价|查看全部评论|暂无评价|暂无评论)([\s（(\d+万w）)]*)$/.test(e.innerText.trim()));
        """)
        if ready is True:
            return
        if scrolls < 8:
            # Restore the legacy lazy-loading action before declaring reviews absent.
            _scroll_comments(driver)
            scrolls += 1
        thin = driver.execute_script(r"""
            const text = document.body?.innerText || '';
            return {len: text.trim().length, hasReviews: /用户评价|商品评价|宝贝评价/.test(text),
                    height: document.documentElement.scrollHeight};
        """) or {}
        if time.monotonic() - started > 30 and _degraded_page(thin):
            raise CollectionPaused('平台只返回了精简商品页（仅购买区，评价模块未下发）；这通常是访问频率限制，已停止本次采集',
                                   code='degraded_page')
        _wait(3, cancelled)
    import json
    raise CollectionPaused('等待90秒后评价区域仍未加载完成；页面诊断：' + json.dumps(_comment_page_diagnostics(driver), ensure_ascii=False), code='comment_section_not_loaded')


def _scroll_comments(driver):
    driver.execute_script("""
        const roots = [...document.querySelectorAll('[class*="rateListBox"], [class*="jdc-page-overlay"], .comments-container, .comment-list, .J_commentsList, [class*="CommentList"], [class*="comments--"]')].filter(e => e.getClientRects().length);
        const panes = roots.flatMap(e => [e, ...e.querySelectorAll('div,section,ul')]).filter(e => e.scrollHeight > e.clientHeight + 30 && /auto|scroll/.test(getComputedStyle(e).overflowY));
        const pane = panes.sort((a,b) => b.scrollHeight-a.scrollHeight)[0];
        if (pane) pane.scrollBy(0, Math.max(700, pane.clientHeight*.8));
        else window.scrollBy(0, 800);
    """)


def _next_comments(driver):
    return driver.execute_script("""
        const roots = document.querySelectorAll('#comment, #comment-root, [class*="rateListBox"], .J_commentsList, [class*="CommentList"]');
        for (const root of roots) for (const b of root.querySelectorAll('a,button')) {
            if (b.getClientRects().length && !b.disabled && !/disabled/.test(b.className) && /^(下一页|下页|下一页 ›|›)$/.test(b.textContent.trim())) {b.click(); return true;}
        }
        return false;
    """)


def _popup_comments(driver):
    from reviewagent.scrapers.jd_drissionpage_scraper import RATE_CARD_CSS_FALLBACKS, RATE_DESC_CSS_FALLBACKS
    import json
    script = r"""
        const cards = [...document.querySelectorAll(CARDS)].filter(e => e.getClientRects().length);
        return cards.flatMap(card => {
            const body = card.querySelector(DESCRIPTIONS);
            if (!body?.innerText?.trim()) return [];
            const star = card.querySelector('[class*=star]');
            const score = star?.className?.match(/star[-_]?([1-5])(?:\D|$)/i);
            return [{content:body.innerText.trim(), comment_id:card.dataset?.commentId || '',
                     user_name:card.querySelector('.user-info,.u-name,.nickname')?.innerText?.trim() || '',
                     time:card.querySelector('.order-info,.comment-date,.date')?.innerText?.trim() || '',
                     sku:card.querySelector('.sku-info,.J_order_type')?.innerText?.trim() || '',
                     rateScore:score?Number(score[1]):null}];
        });
    """
    script = script.replace('CARDS', json.dumps(','.join(value.removeprefix('css:') for value in RATE_CARD_CSS_FALLBACKS)))
    script = script.replace('DESCRIPTIONS', json.dumps(','.join(value.removeprefix('css:') for value in RATE_DESC_CSS_FALLBACKS)))
    return driver.execute_script(script) or []


def _await_access(driver, platform, url, cancelled, emit):
    state = _page_state(driver, platform)
    if state in {'rate_limited', 'account_restricted'}:
        raise CollectionPaused('平台限制访问或提示账号异常，已停止当前平台；请手动查看平台提示', code=state)
    if state in {'needs_login', 'verification_required', 'identity_verification', 'login_complete'}:
        if state != 'login_complete':
            emit('awaiting_login' if state == 'needs_login' else 'awaiting_verification',
                 '淘宝正在检测账号状态，当前不是二维码登录页；尚未采集评论，请在平台页面完成身份校验' if state == 'identity_verification' else '请在当前专用窗口扫码登录或完成平台验证，成功后继续；无需发送账号或验证码')
        deadline = time.monotonic() + 300
        while state in {'needs_login', 'verification_required', 'identity_verification'} and time.monotonic() < deadline:
            _wait(1, cancelled)
            if not driver.window_handles:
                raise CollectionPaused('专用窗口已关闭，已保留进度', code='login_cancelled')
            if state == 'needs_login' and hasattr(driver, 'follow_login_tab'):
                driver.follow_login_tab(platform)
            previous_state = state
            state = _page_state(driver, platform)
            if state != previous_state and state in {'needs_login', 'verification_required', 'identity_verification'}:
                emit('awaiting_login' if state == 'needs_login' else 'awaiting_verification',
                     '仍需扫码登录' if state == 'needs_login' else '淘宝账号状态检测尚未完成，当前没有二维码；尚未采集评论' if state == 'identity_verification' else '平台仍要求身份验证，请在专用窗口手动完成；当前尚未采集')
        if state in {'needs_login', 'verification_required', 'identity_verification'}:
            code = 'login_timeout' if state == 'needs_login' else 'identity_verification_timeout' if state == 'identity_verification' else 'verification_required'
            message = '淘宝账号状态检测持续5分钟仍未完成；采集已停止，不再自动重新登录' if state == 'identity_verification' else '等待登录或身份验证超过5分钟；本次未进入评论采集，已保留状态'
            raise CollectionPaused(message, code=code)
        if state in {'ready', 'login_complete'}:
            manager = AutoLoginManager()
            if manager._is_login_success(driver, platform, allow_login_result=True):
                record_authenticated(driver, platform)
            emit('authenticated', '登录页面已完成，正在返回商品；专用窗口用于读取评论，采集结束后自动关闭')
            try:
                driver.get(url)
            except BrowserNavigationError as exc:
                raise CollectionPaused(str(exc), code=exc.code) from None
            _wait(2, cancelled)
            if hasattr(driver, 'follow_login_tab'):
                driver.follow_login_tab(platform)
            state = _page_state(driver, platform)
            if state in {'needs_login', 'login_complete'}:
                raise CollectionPaused('登录操作后商品仍回到登录页，已暂停以避免循环重试；本次未读取评论', code='login_redirect_loop')
    if state != 'ready':
        raise CollectionPaused('来源页面仍不可访问；具体状态：' + state, code=state)


def product_metadata(driver):
    """Read public structured fields; missing identifiers remain unconfirmed."""
    data = driver.execute_script(r"""
        const products = [];
        const visit = data => {
            if (Array.isArray(data)) {data.forEach(visit); return;}
            if (!data || typeof data !== 'object') return;
            const types = [].concat(data['@type'] || []);
            if (types.includes('Product')) products.push(data);
            if (data['@graph']) visit(data['@graph']);
        };
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
            try {visit(JSON.parse(script.textContent));} catch {}
        }
        const p = products[0] || {};
        const value = v => typeof v === 'string' || typeof v === 'number' ? String(v) : v?.name || '';
        const specs = {};
        const countMatch = (document.body?.innerText || '').match(/用户评价\s*[·•]?\s*(\d+)(?![\d万])/);
        for (const name of ['color', 'size', 'material']) if (value(p[name])) specs[name] = value(p[name]);
        for (const prop of [].concat(p.additionalProperty || [])) {
            if (prop?.name && value(prop.value)) specs[String(prop.name)] = value(prop.value);
        }
        return {displayed_review_count:countMatch ? Number(countMatch[1]) : null,
                title:value(p.name) || document.querySelector('meta[property="og:title"]')?.content || document.title,
                brand:value(p.brand), model:value(p.model) || value(p.mpn), key_specs:specs, specs_confirmed:false,
                identity_source:'public_jsonld', gtin:value(p.gtin14 || p.gtin13 || p.gtin12 || p.gtin8 || p.gtin)};
    """)
    return {key: value for key, value in (data or {}).items() if value not in ("", {}, None)}


def collect_source(source, limit, cancelled, *, on_state=None, on_batch=None, on_metadata=None):
    platform = platform_key(source.get('platform', ''))
    guard = _platform_guards[platform]
    if not guard.acquire(blocking=False):
        raise CollectionPaused('该平台已有采集任务，为保护账号，本次不并发请求', code='platform_busy')
    try:
        delay = max(0, _next_platform_access.get(platform, 0) - time.monotonic())
        if delay:
            if on_state:
                on_state({'platform': platform, 'status': 'cooldown', 'message': '平台任务间隔等待，期间不发起新请求，可取消'})
            _wait(delay, cancelled)
        if cancelled():
            raise CollectionPaused('已取消，未发起新的平台请求', code='cancelled')
        return _collect_source(source, limit, cancelled, on_state=on_state, on_batch=on_batch, on_metadata=on_metadata)
    finally:
        _next_platform_access[platform] = time.monotonic() + random.uniform(20, 40)
        guard.release()


def _collect_source(source, limit, cancelled, *, on_state=None, on_batch=None, on_metadata=None):
    """Return actual visible comments; a blocked page never triggers bypass fallbacks."""
    from reviewagent import config
    if not config.SCRAPING_ENABLED:
        raise CollectionPaused("采集尚未开启，可先导入评论", code="disabled")
    platform = platform_key(source.get("platform", ""))
    url = source.get("url") or source.get("source_url") or ""
    if not _allowed_url(url, platform):
        raise CollectionPaused("来源链接不属于对应平台的 HTTPS 地址", code="invalid_source")
    def emit(status, message):
        if on_state:
            on_state({"platform": platform, "status": status, "message": message})
    from reviewagent.public_collection import public_reviews, normalize_comment, comment_rows
    public = public_reviews(source, limit, cancelled, on_state=on_state, on_batch=on_batch)
    if public or cancelled():
        return public
    if platform == 'xhs':
        from reviewagent.scrapers import xhs_reader
        if xhs_reader.available():
            emit('backend_collection', '尝试本机小红书只读采集器，只读取笔记评论，不启用OCR模型')
            try:
                capture = xhs_reader.capture(links=[url], with_comments=True, limit=1, with_ocr=False, timeout=60)
                actual = [{**row, 'rating': None, 'source_url': url, 'platform': 'xhs', 'source_platform': 'xhs',
                           'content_kind': 'social_comment', 'extraction_method': 'xhs_batch_reader'}
                          for row in capture.get('reviews', []) if row.get('review_text')]
                if actual:
                    if on_batch:
                        on_batch(actual[:limit])
                    return actual[:limit]
            except xhs_reader.XhsError:
                emit('browser_fallback', '小红书只读后端未取得评论，改用专用浏览器确认页面和登录状态')
    driver = None
    reviews, seen = [], set()
    try:
        emit('opening_browser', '正在打开本机专用浏览器；不要求预先登录')
        # 京东评论接口在无头会话里同样可用，不需要登录，也不该弹窗打扰用户。
        driver = open_driver(platform, headless=(platform == 'jd'))
        if hasattr(driver, 'start_review_listener'):
            driver.start_review_listener()
        if platform == 'jd':
            from reviewagent.public_collection import product_id as _product_id
            jd_item_id = _product_id(url, 'jd')
            if jd_item_id:
                api_rows = _jd_browser_reviews(driver, jd_item_id, limit, cancelled, emit)
                if api_rows:
                    for raw in api_rows:
                        page_no = raw.pop('_jd_page', None) if isinstance(raw, dict) else None
                        locator = {'kind': 'jd_comment_api', 'page': page_no,
                                   'comment_id': str(raw.get('id') or raw.get('guid') or '')} if page_no else None
                        review = normalize_comment(raw, source, 'owned_browser_jd_api', locator=locator)
                        if not review or review['comment_id'] in seen:
                            continue
                        reviews.append(review)
                        seen.add(review['comment_id'])
                        if len(reviews) >= limit:
                            break
                    if reviews:
                        if on_batch:
                            on_batch(reviews)
                        return ReviewBatch(reviews, {'jd_api': 'ok', 'attribution': 'by_productId_parameter'})
        try:
            driver.get(url)
        except BrowserNavigationError as exc:
            raise CollectionPaused(str(exc), code=exc.code) from None
        except Exception:
            state = _page_state(driver, platform)
            if state != 'ready':
                raise CollectionPaused('商品页导航未完成；当前页面状态：' + state, code=state) from None
        _wait(2, cancelled)
        _await_access(driver, platform, url, cancelled, emit)
        if platform == 'taobao':
            _wait_for_comment_section(driver, platform, url, cancelled, emit)
        metadata = product_metadata(driver)
        if on_metadata:
            on_metadata(metadata)
        displayed = metadata.get('displayed_review_count')
        if isinstance(displayed, int) and not isinstance(displayed, bool) and displayed > 0:
            limit = min(limit, displayed)
        emit('collecting', '正在采集接口响应与评价弹窗，逐批保存真实原文')
        folded = {}
        facts = {}
        if platform != 'xhs':
            opened = _open_comments(driver)
            emit('opening_comments', '已点击评价入口' if opened else '尚未定位到可点击的评价入口，正在检查页面结构')
            _wait(2, cancelled)
            _await_access(driver, platform, url, cancelled, emit)
            if platform == 'taobao':
                expanded = _open_comments(driver, all_only=True)
                emit('opening_comments', '已点击查看全部评价，等待评论列表加载' if expanded else '已进入评价区域，检查已加载评论与全部评价入口')
                _wait(3, cancelled)
                folded = _folded_reviews(driver)
                if folded.get('count'):
                    emit('expanded_reviews', '平台折叠了 %d 条评价，尝试展开；若平台仍不展示，则按实际可见条数采集并标注缺口' % folded['count'])
                    try:
                        driver.click_at(folded['x'], folded['y'])
                    except Exception:
                        pass
                    _wait(2, cancelled)
                item_id = (parse_qs(urlsplit(url).query).get('id') or [''])[0]
                if item_id.isdigit():
                    batch_rows, ok = _tmall_rate_rows(driver, item_id, limit, cancelled)
                    facts['rate_api'] = 'ok' if ok else 'unavailable'
                    if ok:
                        emit('rate_api', '已通过页面评论接口补取 %d 条（含折叠评价），逐条去重' % len(batch_rows))
                    for raw in batch_rows:
                        review = normalize_comment(raw, source, 'owned_browser_rate_api')
                        if review and _is_default_comment(review.get('review_text')):
                            facts['rating_only'] = facts.get('rating_only', 0) + 1
                            continue
                        fingerprint = (review.get('reviewer_name'), review.get('review_date'), review.get('review_text')) if review else None
                        if not review or review['comment_id'] in seen or fingerprint in seen:
                            continue
                        reviews.append(review)
                        seen.add(review['comment_id'])
                        seen.add(fingerprint)
                        if len(reviews) >= limit:
                            break
                    if on_batch and reviews:
                        on_batch(reviews)
        stagnant = 0
        deadline = time.monotonic() + 180
        for _ in range(60):
            if cancelled() or time.monotonic() >= deadline:
                break
            _await_access(driver, platform, url, cancelled, emit)
            previous = len(reviews)
            raw_rows = list(_extract(driver, platform))
            if platform == 'jd':
                raw_rows.extend(_popup_comments(driver))
            if hasattr(driver, 'review_payloads'):
                for body in driver.review_payloads():
                    raw_rows.extend(comment_rows(body, platform))
            for raw in raw_rows:
                review = normalize_comment(raw, source, 'owned_browser_response_dom')
                if review and _is_default_comment(review.get('review_text')):
                    continue
                fingerprint = (review.get('reviewer_name'), review.get('review_date'), review.get('review_text')) if review else None
                if not review or review['comment_id'] in seen or fingerprint in seen:
                    continue
                reviews.append(review)
                seen.add(review['comment_id'])
                seen.add(fingerprint)
                if len(reviews) >= limit:
                    break
            if on_batch and len(reviews) > previous:
                on_batch(reviews)
            if len(reviews) >= limit:
                break
            stagnant = stagnant + 1 if len(reviews) == previous else 0
            if stagnant >= 4:
                break
            if stagnant == 2 and platform != 'xhs':
                _next_comments(driver)
                if platform == 'taobao':
                    _open_comments(driver, all_only=True)
            _scroll_comments(driver)
            _wait(min(12, 2 * 2 ** stagnant), cancelled)
        if not reviews:
            import json
            detail = _comment_page_diagnostics(driver)
            raise CollectionPaused('未读取到评论正文；页面诊断：' + json.dumps(detail, ensure_ascii=False), code='no_review_text')
        facts.update({'displayed': displayed if isinstance(displayed, int) and not isinstance(displayed, bool) else None,
                      'folded': folded.get('count') if folded else None,
                      'selected': len(reviews)})
        return ReviewBatch(reviews, facts)
    except CollectionPaused:
        raise
    except Exception as exc:
        if type(exc).__name__ in {'PageDisconnectedError', 'TargetClosedError', 'NoSuchWindowException', 'InvalidSessionIdException'}:
            raise CollectionPaused('专用浏览器连接已关闭，当前平台已暂停，原文和进度保留', code='browser_closed') from None
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def discover_sources(query, platforms, maximum, cancelled, *, on_state=None, on_batch=None):
    from urllib.parse import urlencode
    from reviewagent import config
    if not config.SCRAPING_ENABLED:
        raise CollectionPaused("采集尚未开启", code="disabled")
    searches = {"jd": "https://search.jd.com/Search?" + urlencode({"keyword": query}),
                "taobao": "https://s.taobao.com/search?" + urlencode({"q": query}),
                "xhs": "https://www.xiaohongshu.com/search_result?" + urlencode({"keyword": query})}
    candidates, gaps, seen = [], [], set()
    # Divide the source allowance across platforms so one search cannot use it all.
    allowance = maximum
    for requested in platforms:
        if cancelled():
            break
        platform = platform_key(requested)
        driver = None
        try:
            driver = open_driver(platform, headless=True)
            driver.get(searches[platform])
            _wait(3, cancelled)
            state = _page_state(driver, platform)
            if state in {"needs_login", "verification_required", "identity_verification", "login_complete"}:
                # 后台搜索遇到登录/校验时才把窗口弹出来，登录完成后继续当前搜索。
                driver.quit()
                driver = open_driver(platform, headless=False)
                driver.get(searches[platform])
                _wait(2, cancelled)
            _await_access(driver, platform, searches[platform], cancelled, lambda status, message: on_state({"platform": platform, "status": status, "message": message}) if on_state else None)
            anchors = driver.execute_script("""
                return [...document.querySelectorAll('a[href]')].slice(0, 3000).map(a => ({url:a.href,
                    title:(a.getAttribute('title') || a.innerText || a.querySelector('img')?.alt || '').trim()}));
            """)
            count = 0
            for anchor in anchors or []:
                url = anchor.get("url", "")
                parsed = urlsplit(url)
                host = (parsed.hostname or "").lower()
                if not _allowed_url(url, platform) or url in seen:
                    continue
                product = (platform == "jd" and host == "item.jd.com" and re.fullmatch(r"/(?:product/)?[A-Za-z0-9_-]+\.html", parsed.path)) or (
                    platform == "taobao" and host in {"item.taobao.com", "detail.tmall.com"} and parsed.path in {"/item.htm", "/item.htm/"}) or (
                    platform == "xhs" and re.match(r"/(?:explore|discovery/item)/[a-zA-Z0-9]+", parsed.path))
                if not product or not anchor.get("title"):
                    continue
                seen.add(url)
                candidates.append({"url": url, "title": anchor["title"], "platform": "tmall" if host == "detail.tmall.com" else platform,
                                   "status": "needs_capture", "brand": "", "model": "", "key_specs": {},
                                   "specs_confirmed": False, "identity_source": "search_result", "discovery_source": "owned_browser_search"})
                count += 1
                if count >= allowance:
                    break
            if not count:
                gaps.append({"platform": platform, "message": "搜索未返回可核对的商品或笔记链接，可补充来源链接"})
        except CollectionPaused as exc:
            gaps.append({"platform": platform, "code": exc.code, "message": str(exc)})
        except Exception:
            gaps.append({"platform": platform, "message": "本平台搜索连接未完成，其他平台结果已保留"})
        finally:
            if driver is not None:
                driver.quit()
        if on_batch:
            on_batch(candidates, gaps)
    return candidates, gaps
