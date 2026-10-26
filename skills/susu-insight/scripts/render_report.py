#!/usr/bin/env python3
"""Render analyzed account comments with the bundled offline template; stdlib only."""
import collections
import datetime
import html
import json
import re
import sys
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare(data):
    require(isinstance(data.get('account', {}).get('name'), str) and data['account']['name'].strip(), 'account.name required')
    for key in ('contents', 'comments', 'perceptions', 'topics', 'opportunities', 'word_candidates'):
        require(isinstance(data.get(key), list), key+' must be an array')
    def index(items, label):
        result = {}
        for item in items:
            cid = item.get('id')
            require(isinstance(cid, str) and re.fullmatch(r'[A-Za-z0-9_-]+', cid), label+' id must use letters/numbers/_/-')
            require(cid not in result, 'duplicate '+label+' id: '+cid)
            result[cid] = item
        return result
    sources = index(data['contents'], 'content')
    require(len({key.lower() for key in sources}) == len(sources), 'content ids must also be unique ignoring case')
    comments = index(data['comments'], 'comment')
    topics = index(data['topics'], 'topic')
    for c in comments.values():
        require(c.get('content_id') in sources, 'unknown content: '+c['id'])
        require(isinstance(c.get('text'), str), 'comment text required: '+c['id'])
        require(c.get('likes') is None or type(c['likes']) is int and c['likes'] >= 0, 'invalid likes: '+c['id'])
        require(c.get('scope') in ('professional', 'perception', 'context', 'exclude'), 'invalid scope: '+c['id'])
        require(c['scope'] != 'professional' or c.get('expression') in ('substantive', 'reaction'), 'v1.1 requires expression substantive/reaction: '+c['id'])
        require(type(c.get('is_author')) is bool, 'is_author boolean required: '+c['id'])
        require(not c['is_author'] or c['scope'] in ('context', 'exclude'), 'author cannot count as audience: '+c['id'])
        require(c['scope'] != 'exclude' or c.get('reason'), 'excluded record needs reason: '+c['id'])
        parent = c.get('parent_id')
        if parent:
            require(parent in comments and comments[parent]['content_id'] == c['content_id'], 'invalid reply parent: '+c['id'])
            visited = {c['id']}
            while parent:
                require(parent not in visited and parent in comments, 'cyclic or missing parent: '+c['id'])
                visited.add(parent)
                parent = comments[parent].get('parent_id')
    eligible = [c for c in comments.values() if c['scope'] == 'professional']
    assigned = []
    for topic in topics.values():
        require(topic.get('placement') in ('main', 'additional'), 'v1.3 topic needs placement main/additional: '+topic['id'])
        for field in ('title', 'discussion', 'summary'):
            require(isinstance(topic.get(field), str) and topic[field].strip(), 'v1.1 topic needs '+field+': '+topic['id'])
        refs = topic.get('comment_ids', [])
        require(refs and len(refs) == len(set(refs)), 'topic needs unique evidence: '+topic['id'])
        require(all(cid in comments and comments[cid]['scope'] == 'professional' for cid in refs), 'topic references nonprofessional or missing comments')
        representatives = topic.get('representative_ids', [])
        require(1 <= len(representatives) <= 3 and len(representatives) == len(set(representatives)), 'topic needs 1-3 distinct representative_ids: '+topic['id'])
        require(all(cid in refs and comments[cid]['expression'] == 'substantive' for cid in representatives), 'representatives must be substantive comments in the topic: '+topic['id'])
        assigned.extend(refs)
    require(collections.Counter(assigned) == collections.Counter(c['id'] for c in eligible), 'every professional comment must have exactly one primary topic')
    for finding in data['perceptions']:
        refs = finding.get('evidence_ids', [])
        require(refs and all(cid in comments and comments[cid]['scope'] in ('professional', 'perception') for cid in refs), 'creator perception needs audience evidence')
    for opportunity in data['opportunities']:
        signals = opportunity.get('signals', [])
        require(isinstance(signals, list) and signals and all(x in ('debate', 'question', 'emotion') for x in signals) and len(signals) == len(set(signals)), 'opportunity needs distinct supported signals')
        require(isinstance(opportunity.get('situation'), str) and opportunity['situation'].strip(), 'opportunity needs a concrete situation')
        require(opportunity.get('topic_id') in topics, 'opportunity needs an existing topic')
        refs = opportunity.get('evidence_ids', [])
        require(1 <= len(refs) <= 3 and len(refs) == len(set(refs)), 'opportunity needs 1-3 distinct evidence_ids')
        require(all(cid in topics[opportunity['topic_id']]['comment_ids'] and comments[cid]['expression'] == 'substantive' for cid in refs), 'opportunity evidence must be substantive comments in its topic')
    for c in comments.values():
        require(c['scope'] not in ('professional', 'perception') or c['text'].strip(), 'empty audience comment')
    words = []
    seen = set()
    for word in data['word_candidates']:
        require(isinstance(word, str) and word.strip(), 'word must be a nonempty string')
        word = word.strip()
        if word in seen:
            continue
        seen.add(word)
        refs = [c['id'] for c in eligible if word in c['text']]
        if refs:
            words.append({'term': word, 'count': len(refs), 'comment_ids': refs})
    words.sort(key=lambda w: -w['count'])
    stats = {'provided': len(comments), 'professional': len(eligible), 'professional_top_level': sum(not c.get('parent_id') for c in eligible), 'professional_replies': sum(bool(c.get('parent_id')) for c in eligible), 'scope_counts': dict(collections.Counter(c['scope'] for c in comments.values()))}
    stats['topics'] = {t['id']: {'total': len(t['comment_ids']), 'substantive': sum(comments[c]['expression'] == 'substantive' for c in t['comment_ids']), 'reaction': sum(comments[c]['expression'] == 'reaction' for c in t['comment_ids'])} for t in topics.values()}
    return sources, comments, topics, eligible, words, stats


def render(data):
    sources, comments, topics, eligible, words, stats = prepare(data)
    def esc(value): return html.escape(str(value))
    def quote(cid):
        c = comments[cid]
        likes = '点赞未知' if c['likes'] is None else str(c['likes'])+' 赞'
        observed = c.get('observed_like_values', [])
        if c['likes'] is None and len(set(observed)) > 1:
            likes = '点赞记录有冲突：'+' / '.join(str(v) for v in observed)
        level = '作者回复' if c['is_author'] else '回复' if c.get('parent_id') else '一级评论'
        parent = '<p class="note">回复对象：'+esc(comments[c['parent_id']]['text'])+'</p>' if c.get('parent_id') else ''
        location = ' · 原材料第'+str(c['source_line'])+'行' if c.get('source_line') else ''
        return '<blockquote class="quote">'+parent+'<p>“'+esc(c['text'])+'”</p><footer><a href="#source-'+c['content_id'].lower()+'">'+esc(c['content_id']+' · '+cid+' · '+level+location)+'</a><span class="likes">'+esc(likes)+'</span></footer></blockquote>'
    def evidence(ids, label='查看评论依据'):
        return '<details><summary>'+esc(label)+' · '+str(len(ids))+'条</summary><div class="evidence-list">'+''.join(quote(cid) for cid in ids)+'</div></details>'
    def section(num, sid, title, body):
        return '<section class="section" id="'+sid+'"><div class="section-head"><span class="section-index">'+num+'</span><h2>'+title+'</h2></div>'+body+'</section>'
    title = data['account']['name']+' · 评论需求研究'
    body = '<header><div class="topline"><span>账号评论研究</span><span>'+datetime.date.today().isoformat()+'</span></div><h1>'+esc(title)+'</h1><p class="intro">'+esc(data.get('summary', ''))+'</p><p class="note">'+esc(data.get('material_note', ''))+'</p><div class="scope"><span><strong>'+str(len(sources))+'</strong>篇材料</span><span><strong>'+str(stats['provided'])+'</strong>条收到的评论记录</span><span><strong>'+str(len(topics))+'</strong>类专业相关讨论</span></div></header>'
    first = '<div class="insight-list">'
    for i, item in enumerate(data['perceptions'], 1):
        first += '<article class="insight"><span class="count">'+str(i).zfill(2)+'</span><div><h3>'+esc(item['title'])+'</h3><p class="explain">'+esc(item['explanation'])+'</p>'+evidence(item['evidence_ids'])+'</div></article>'
    first += '</div>'
    if not data['perceptions']:
        first += '<p class="note">现有材料尚不足以归纳观众对博主的稳定认知。</p>'
    body += section('01', 'attraction', '看懂这个博主', first)
    cloud = '<section class="wordcloud-panel"><span class="eyebrow">先看原话里的关键词</span><h3>评论里，哪些词被反复提起？</h3><p class="note">词越大，提到它的评论越多。点击词语查看原话。</p><div id="comment-wordcloud" class="wordcloud" role="group" aria-label="关键词词云"></div><div id="wordcloud-evidence" class="wordcloud-evidence" hidden><div class="wordcloud-evidence-head"><h4 id="wordcloud-selected" aria-live="polite"></h4><button id="wordcloud-close" type="button">收起原话</button></div><div id="wordcloud-quotes" class="evidence-list"></div></div><details><summary>统计范围与词频明细</summary><p class="note">仅统计专业相关观众评论：'+str(stats['professional_top_level'])+'条一级、'+str(stats['professional_replies'])+'条回复。每条同一词只计一次；不代表独立人数。图表与词云均不包含作者回复、无关及排除记录。</p><div class="wordcloud-frequency-list">'+''.join('<span>'+esc(w['term'])+' <b>'+str(w['count'])+'条</b></span>' for w in words)+'</div></details></section>'
    ordered = sorted(topics.values(), key=lambda t: -len(t['comment_ids']))
    main_topics = [t for t in ordered if t['placement'] == 'main']
    extra_topics = [t for t in ordered if t['placement'] == 'additional']
    maximum = max([len(t['comment_ids']) for t in main_topics] or [1])
    def topic_card(t):
        ids = t['comment_ids']; counts = stats['topics'][t['id']]
        primary = sum(not comments[c].get('parent_id') for c in ids)
        nnotes = len({comments[c]['content_id'] for c in ids})
        reps = t['representative_ids']
        result = '<article class="topic-card" id="group-'+t['id']+'" aria-labelledby="heading-'+t['id']+'"><h3 id="heading-'+t['id']+'" tabindex="-1">'+esc(t['title'])+'</h3><p class="topic-discussion">'+esc(t['discussion'])+'</p>'
        result += '<div class="topic-meta"><strong>相关讨论 '+str(counts['total'])+'条</strong><span>具体表达 '+str(counts['substantive'])+'条 · 简短附和/反应 '+str(counts['reaction'])+'条</span></div><p class="keywords">'+esc(' / '.join(t.get('keywords', [])))+'</p>'
        if t.get('need'):
            result += '<div class="topic-need"><b>其中有人具体问到</b><p>'+esc(t['need'])+'</p></div>'
        result += '<div class="representative"><h4>看一条原话</h4>'+quote(reps[0])+'</div>'
        if len(reps)>1:
            result += '<details class="representative-more"><summary>再看其他代表评论 · '+str(len(reps)-1)+'条</summary><div class="evidence-list">'+''.join(quote(c) for c in reps[1:])+'</div></details>'
        result += '<details class="topic-explanation"><summary>展开这类讨论的不同说法</summary><p>'+esc(t['summary'])+'</p><p class="note">'+esc(t.get('signal', ''))+'</p></details>'
        result += evidence(ids, '查看全部归类原话')
        linked = [i for i,op in enumerate(data['opportunities'],1) if op['topic_id']==t['id']]
        if linked:
            result += '<p class="topic-next"><a href="#op-'+str(linked[0])+'">去看由这类讨论延伸的 '+str(len(linked))+' 条内容建议 →</a></p>'
        result += '<p class="note">'+str(primary)+'条一级 · '+str(len(ids)-primary)+'条回复 · '+str(nnotes)+'篇材料</p></article>'
        return result
    second = cloud+'<div class="discussion-overview"><h3>大家主要在聊这几件事</h3><p class="note">先扫一遍话题，找到你关心的事；点开卡片，看评论原话与不同说法。</p>'
    if main_topics:
        second += '<div class="topic-workspace"><div class="topic-map-column"><p id="topic-map-legend" class="map-legend">横条越长，相关讨论越多；以本次最多的一类为参照。</p><div id="topic-index" class="topic-map" role="group" aria-label="选择讨论分类">'
        for index, t in enumerate(main_topics, 1):
            count = len(t['comment_ids'])
            second += '<button type="button" class="topic-tile" data-topic="'+t['id']+'" data-count="'+str(count)+'" aria-controls="group-'+t['id']+'" aria-pressed="false" aria-label="'+esc(t['title']+'，相关讨论'+str(count)+'条，展开原话')+'"><span class="tile-top"><span class="tile-index">'+str(index).zfill(2)+'</span><span class="tile-count"><b>'+str(count)+'</b> 条讨论</span></span><span class="tile-title">'+esc(t['title'])+'</span><span class="tile-keywords">'+esc(' · '.join(t.get('keywords', [])[:3]))+'</span><span class="tile-meter" aria-hidden="true"><i style="width:'+str(round(count/maximum*100,2))+'%"></i></span><span class="tile-open">看原话与分析 <span aria-hidden="true">↗</span></span></button>'

        second += '</div><p class="note">数量反映讨论多少。观点、情绪与提问都保留，低赞的具体追问也值得看。</p></div><div class="topic-detail-column" tabindex="0" role="region" aria-label="所选话题的评论与分析"><div class="detail-toolbar"><p class="selected-topic-label" aria-live="polite">正在看这类讨论</p><a href="#topic-index">返回话题总览 ↑</a></div>'+''.join(topic_card(t) for t in main_topics)+'</div></div>'
    if extra_topics:
        second += '<details class="additional-topics"><summary>另外 '+str(len(extra_topics))+' 条值得留意的追问</summary><p class="note">这些线索比较零散，单独保留，方便按兴趣查看。</p>'
        for t in extra_topics:
            second += '<details class="extra-topic"><summary>'+esc(t['title'])+' · '+str(len(t['comment_ids']))+'条相关讨论</summary>'+topic_card(t)+'</details>'
        second += '</details>'
    second += '<details class="count-explanation"><summary>这些数字怎么算？</summary><p class="note">相关讨论包括一级评论和回复；具体表达包含观点、情绪、经历和提问，简短附和/反应包括赞同、笑声等。两项相加为相关讨论数，不代表求助人数。各条点赞可在原话中查看。</p></details></div>'
    if not ordered:
        second += '<p class="note">现有材料没有形成专业相关的问题分类；保留已能判断的博主认知。</p>'
    body += section('02', 'discussion', '评论里，大家都在关心什么？', second)
    signal_labels = {'debate':'有不同看法', 'question':'有人明确提问', 'emotion':'有情绪共鸣'}
    def illustration(kind):
        drawings = {
            'goal': '<circle cx="158" cy="54" r="34"/><circle cx="158" cy="54" r="22"/><circle cx="158" cy="54" r="9"/><path d="M66 96L155 56M134 54l22 1-13 18M77 87l-19-4 8 15M131 98h59"/>',
            'dialogue': '<path d="M49 21h92a12 12 0 0 1 12 12v32a12 12 0 0 1-12 12h-42L77 94V77H49a12 12 0 0 1-12-12V33a12 12 0 0 1 12-12Z"/><path d="M159 40h26a12 12 0 0 1 12 12v29a12 12 0 0 1-12 12h-9l-1 16-21-16h-29M59 41h67M59 55h43"/><circle cx="164" cy="62" r="2"/><circle cx="177" cy="62" r="2"/>',
            'work': '<path d="M37 67h156M48 67v38M180 67v38M66 28h82l-8 39H73ZM98 80h38M160 40h20v27h-20ZM180 45c18-1 18 17 0 16"/><path d="M163 30c-7-8 6-9 0-17M174 28c-7-8 6-9 0-17M31 109h167"/>',
            'growth': '<path d="M35 107h160M52 105V80h30V59h30V36h32V16h41M43 57c17-25 39-36 67-37M95 11l16 9-9 15"/><circle cx="175" cy="64" r="13"/><path d="M175 77v31M159 107h32M166 68l9-7 9 5"/>',
            'bridge': '<path d="M28 105h53M154 105h54M55 91c0-64 131-64 131 0M55 88h131M67 63v25M87 47v41M111 40v48M136 43v45M160 54v34M180 73v15M96 100c8-7 16-7 24 0s16 7 24 0"/><circle cx="54" cy="27" r="8"/><path d="M46 38h16M52 38v15"/>',
            'boundary': '<rect x="100" y="17" width="76" height="90" rx="4"/><path d="M109 107V30l51-8v85M160 107h26M28 107h63M75 58h39M103 49l11 9-11 9"/><circle cx="150" cy="67" r="2"/><path d="M46 21v13M39 28h14"/>',
            'balance': '<path d="M119 27v78M96 107h46M66 40h106M119 22l-7 12h14ZM69 41L46 82h46ZM170 41l-23 41h46ZM46 82c1 23 44 23 46 0M147 82c1 23 44 23 46 0"/><circle cx="188" cy="20" r="5"/>',
            'heart': '<path d="M119 91S56 59 66 32c7-19 33-20 53 3 20-23 46-22 53-3 10 27-53 59-53 59Z"/><path d="M36 109c28-23 49-4 67-15s23-40 42-22 23 16 56 0M43 28v16M35 36h16M188 48v10M183 53h10"/>',
            'compass': '<circle cx="117" cy="61" r="43"/><path d="M100 80l10-32 26-11-11 30ZM110 48l15 19M117 10V4M117 118v-6M66 61h-7M168 61h7M39 98h17M48 90v17"/>'
        }
        drawing = drawings.get(kind, drawings['dialogue'])
        return '<svg class="card-art" viewBox="0 0 240 125" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'+drawing+'</svg>'
    def opportunity_card(i, op):
        topic = topics[op['topic_id']]
        badges = ''.join('<span class="signal-badge">'+signal_labels[k]+'</span>' for k in op['signals'])
        if len(topic['comment_ids']) == 1:
            badges += '<span class="signal-badge single-signal">单条线索</span>'
        art = illustration(op.get('illustration', 'dialogue' if 'debate' in op['signals'] else 'compass'))
        cover_title = op['title'].strip('《》')
        result = '<details class="opportunity" id="op-'+str(i)+'"><summary class="op-preview"><span class="card-meta"><span>选题卡片 / '+str(i).zfill(2)+'</span><span class="card-mark" aria-hidden="true">✧</span></span>'+art+'<h3>'+esc(cover_title)+'</h3><span class="signal-badges">'+badges+'</span><span class="card-bottom"><span>苏苏进化论 · 评论研究</span><span class="cover-open">展开 ↗</span><span class="cover-close">收起 ↙</span></span></summary><div class="op-body"><p class="origin">来自分类：<a href="#group-'+topic['id']+'">'+esc(topic['title'])+'</a></p><div class="reading-step"><h4>这张卡片在讲什么</h4><p>'+esc(op['situation'])+'</p></div><div class="reading-step"><h4>从这些评论想到的</h4>'+''.join(quote(cid) for cid in op['evidence_ids'])+'</div><div class="reading-step"><h4>为什么值得接着讲</h4><p>'+esc(op['connection'])+'</p></div><div class="action"><span class="eyebrow">这条内容可以这样讲</span><p>'+esc(op['example'])+'</p></div>'
        if op.get('product'):
            result += '<details class="product-idea"><summary>如果继续做产品</summary><p>'+esc(op['product'])+'</p></details>'
        return result+'</div></details>'
    main_ops = [(i,op) for i,op in enumerate(data['opportunities'],1) if topics[op['topic_id']]['placement']=='main']
    extra_ops = [(i,op) for i,op in enumerate(data['opportunities'],1) if topics[op['topic_id']]['placement']=='additional']
    third = '<p class="section-desc">每一张知识卡片，都是一个可以继续讲的选题。挑一张感兴趣的，点开看评论依据与具体讲法。</p><div class="op-card-grid">'+''.join(opportunity_card(i,op) for i,op in main_ops)+'</div>'
    if extra_ops:
        third += '<details class="additional-opps"><summary>从零散追问延伸的内容 · '+str(len(extra_ops))+'条</summary><div class="op-card-grid">'+''.join(opportunity_card(i,op) for i,op in extra_ops)+'</div></details>'
    if not data['opportunities']:
        third += '<p class="note">当前不强行延伸选题，先保留上面的讨论与问题。</p>'
    body += section('03', 'opportunities', '顺着这些讨论，可以做什么内容？', third)
    body += '<details class="sources" id="sources"><summary>本次材料与处理记录</summary><p class="note">'+esc(data.get('material_note', ''))+'</p><ul class="source-list">'
    for source in sources.values():
        body += '<li class="source-item" id="source-'+source['id'].lower()+'"><strong>'+esc(source['id']+' · '+source['title'])+'</strong><span>'+esc(source.get('note', ''))+'</span></li>'
    body += '</ul><p class="note">专业相关 '+str(stats['professional'])+' 条；仅用于博主认知 '+str(stats['scope_counts'].get('perception', 0))+' 条；上下文 '+str(stats['scope_counts'].get('context', 0))+' 条；排除 '+str(stats['scope_counts'].get('exclude', 0))+' 条。</p>'
    if data.get('profile_note'):
        body += '<p class="note">'+esc(data['profile_note'])+'</p>'
    for note in data.get('processing_notes', []):
        body += '<p class="note">'+esc(note)+'</p>'
    for c in comments.values():
        if c['scope'] != 'professional':
            body += '<details><summary>'+esc(c['id']+' · '+c['scope'])+'</summary>'+quote(c['id'])+'<p class="note">'+esc(c.get('reason', ''))+'</p></details>'
    body += '</details><footer class="report-footer"><span>'+esc(title)+'</span><span>Skill v1.6.1</span></footer>'
    worddata = {'words': words, 'comments': [{**c, 'note': c['content_id']} for c in eligible]}
    tokens = {'TITLE': esc(title), 'ACCOUNT': esc(data['account']['name']), 'HANDLE': esc(data['account'].get('handle', '')), 'BODY': body, 'WORD_DATA': json.dumps(worddata, ensure_ascii=False).replace('<', '\\u003c')}
    template = (Path(__file__).resolve().parents[1]/'assets/report-template.html').read_text(encoding='utf-8')
    result = re.sub(r'@@([A-Z_]+)@@', lambda m: tokens[m[1]], template)
    return result, {'analysis': data, 'statistics': stats, 'wordcloud': worddata}


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: render_report.py <analysis.json> <output-dir>')
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    page, audit = render(data)
    folder = Path(sys.argv[2]); folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[^\w\u4e00-\u9fff-]+', '-', data['account']['name']).strip('-') or 'account'
    stem += '-评论研究-'+datetime.date.today().isoformat()
    base = stem; i = 2
    while (folder/(stem+'.html')).exists() or (folder/(stem+'.json')).exists():
        stem = base+'-'+str(i); i += 1
    (folder/(stem+'.html')).write_text(page, encoding='utf-8')
    (folder/(stem+'.json')).write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(str((folder/(stem+'.html')).resolve()))


if __name__ == '__main__':
    main()
