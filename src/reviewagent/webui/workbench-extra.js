/* Product identity and editable operator drafts. Shared workbench helpers load next. */
'use strict';
function inputLink(text){return (String(text||'').match(/https?:\/\/[^\s<>「」"']+/i)||[])[0]||''}
async function beginResearchFlow(){
  const url=inputLink(state.analysis.input);
  if(!url){openCandidateWizard();return}
  await collectSelectedLinks([url]);
}
async function collectSelectedLinks(urls){
  if(!state.config?.scraping_enabled){await api('/v1/collection/configure',jsonBody({enabled:true}));await connect()}
  acceptAnalysis(await api(apiPath(''),{method:'PATCH',body:JSON.stringify({extra_links:urls,selected_urls:urls})}));
  state.autoAnalyzeAfterCollectId=state.analysis.analysis_id;setView('overview');await startJob('collect');if(!state.config?.llm_configured)notify('未配置模型：本次仅抓取评论，无法完成分析。请点击左下角配置模型。');
}
function openCandidateWizard(){
  state.candidateWizard={platform:state.analysis.request?.platforms?.includes('taobao')?'taobao':state.analysis.request?.platforms?.[0]||'jd',selected:new Set(),manual:false,completed:false};
  showModal('选择要分析的商品','<div id="candidate-selection" aria-live="polite"></div><div id="candidate-picker"></div>','下一步：采集分析',async()=>{
    const wizard=state.candidateWizard;if(!wizard)return;
    let urls=[...wizard.selected];if(wizard.manual){const manual=($('#candidate-manual')?.value||'').split('\n').map(inputLink).filter(Boolean);urls=[...new Set([...urls,...manual])]}
    wizard.completed=true;state.candidateWizard=null;$('#modal').close();
    if(!urls.length){setView('overview');notify('未抓取到评论');return}
    await collectSelectedLinks(urls);
  });
  renderCandidateWizard();searchCandidatePlatform();
}
function renderCandidateWizard(){
  const wizard=state.candidateWizard,box=$('#candidate-picker');if(!wizard||!box)return;
  const busy=busyStatuses.has(state.analysis.status),platforms=state.analysis.request?.platforms||['taobao','jd'];
  const items=(state.analysis.candidates||[]).filter(c=>(c.platform==='tmall'?'taobao':c.platform)===wizard.platform).slice(0,5);
  box.innerHTML=select('candidate_platform','选择平台',platforms.map(p=>[p,label[p]||p]),wizard.platform)+(wizard.manual?'<label class="field"><span>自行粘贴商品链接或分享文案，每行一条</span><textarea id="candidate-manual"></textarea></label><p class="note">未填写就下一步或关闭，会提示未抓取到评论并返回主页面。</p>':`<p class="note">关键词匹配忽略大小写；每个平台默认最多 5 条真实链接。${busy?esc(state.analysis.progress?.message||'正在检索，需登录时请在专用窗口扫码。'):''}</p>${items.map(c=>`<label class="candidate-option"><input type="checkbox" data-candidate-url="${esc(c.url)}" ${wizard.selected.has(c.url)?'checked':''} ${busy?'disabled':''}><span>${esc(c.title||'商品标题待核对')}<small>${sourceLink(c.url,'查看商品链接')}</small></span></label>`).join('')||'<p class="note">未匹配到可核对链接；可重新搜索，或自行粘贴商品链接。</p>'}<button type="button" class="button" id="candidate-retry" ${busy?'disabled':''}>重新搜索</button> <button type="button" class="button" id="candidate-other" ${busy?'disabled':''}>不是我想要的</button>`);
  $('[name="candidate_platform"]',box).disabled=busy;
  $('[name="candidate_platform"]',box).addEventListener('change',event=>{wizard.platform=event.target.value;wizard.manual=false;searchCandidatePlatform()});
  $$('[data-candidate-url]',box).forEach(input=>input.addEventListener('change',()=>{if(input.checked)wizard.selected.add(input.dataset.candidateUrl);else wizard.selected.delete(input.dataset.candidateUrl);renderCandidateSelection()}));
  $('#candidate-other')?.addEventListener('click',()=>{wizard.manual=true;renderCandidateWizard()});$('#candidate-retry')?.addEventListener('click',searchCandidatePlatform);$('#modal-submit').disabled=busy;
  renderCandidateSelection();
}
function renderCandidateSelection(){
  const wizard=state.candidateWizard,box=$('#candidate-selection');if(!wizard||!box)return;
  const groups=new Map(),candidates=state.analysis.candidates||[];
  for(const url of wizard.selected){const item=candidates.find(c=>c.url===url)||{url,title:'已选择商品',platform:'unknown'},platform=item.platform==='tmall'?'taobao':item.platform;if(!groups.has(platform))groups.set(platform,[]);groups.get(platform).push(item)}
  box.innerHTML=`<section class="panel"><strong>已选 ${groups.size} 个平台来源 · ${wizard.selected.size} 条商品链接</strong><p class="note">切换平台保留选择；下一步统一采集，品牌、型号与规格分别分组。</p>${[...groups].map(([platform,items])=>`<div><span class="badge">${esc(label[platform]||platform)}</span>${items.map(item=>`<div class="candidate-selection-row"><span>${esc(item.title)}</span><button type="button" class="text-button" data-unselect-url="${esc(item.url)}" aria-label="取消选择 ${esc(item.title)}">取消选择</button></div>`).join('')}</div>`).join('')||'<p class="note">尚未选择商品，可在各平台分别勾选。</p>'}</section>`;
  $$('[data-unselect-url]',box).forEach(button=>button.addEventListener('click',()=>{wizard.selected.delete(button.dataset.unselectUrl);renderCandidateWizard()}));
}
async function searchCandidatePlatform(){
  try{if(!state.config?.scraping_enabled){await api('/v1/collection/configure',jsonBody({enabled:true}));await connect()}const wizard=state.candidateWizard;if(!wizard)return;acceptAnalysis(await api(apiPath(''),{method:'PATCH',body:JSON.stringify({discovery_platform:wizard.platform,candidate_limit:5})}));await startJob('discover');renderCandidateWizard()}catch(error){$('#modal-error').textContent=error.message;$('#modal-error').hidden=false}
}
function bindPlatformChoices(){
  const tier=$('[name="tier"]',$('#modal')),boxes=$$('[name="platforms"]',$('#modal'));if(!tier||!boxes.length)return;
  function sync(reset=false){const max=tier.value==='light'?2:3;let selected=boxes.filter(b=>b.checked);if(reset){boxes.forEach(b=>b.checked=max===3||['jd','taobao'].includes(b.value));selected=boxes.filter(b=>b.checked)}if(selected.length>max){selected.slice(max).forEach(b=>b.checked=false);selected=boxes.filter(b=>b.checked)}boxes.forEach(b=>b.disabled=!b.checked&&selected.length>=max);const count=$('#platform-count');if(count)count.textContent=` 已选 ${selected.length} / ${max} 个。`}
  tier.addEventListener('change',()=>sync(true));boxes.forEach(b=>b.addEventListener('change',()=>sync()));sync();
}
function modelSettings(){
  let verified=null;
  showModal('工作台设置',`${select('theme','界面主题',[['light','浅色'],['dark','深色'],['system','跟随系统']],storage.get('theme')||'light')}<label class="field"><span>API Key</span><input id="model-api-key" type="password" autocomplete="off" placeholder="输入模型供应商的 API Key"><small>仅发送至所选供应商验证，保留于服务内存；不会写入浏览器存储。</small></label>${select('provider','供应商',[['auto','自动识别'],['deepseek','DeepSeek'],['openai','OpenAI'],['gemini','Google Gemini'],['anthropic','Anthropic Claude'],['custom','其他 OpenAI 兼容接口']],'auto')}${field('base_url','自定义 API 地址（仅自定义接口填写）','','url')}<button type="button" class="button" id="verify-model-key">验证并获取模型</button><p id="model-config-hint" class="note"></p><div id="model-choices"></div><dl class="facts"><div><dt>当前模型</dt><dd>${esc(state.config?.llm_configured?state.config.model:'未配置')}</dd></div></dl>${select('browser','专用窗口浏览器',[['auto','系统默认浏览器'],['edge','Microsoft Edge'],['chrome','Google Chrome'],['firefox','Firefox']],state.config?.browser_preference||'auto')}${select('browser_network','平台采集网络',[['direct','直接连接（不使用代理）'],['system','跟随系统网络设置']],state.config?.browser_network||'direct')}<p class="note">Edge 与 Chrome 均可使用本机专用配置。直接连接只影响平台采集，不更改系统代理；模型供应商的网络可达性需单独确认。</p>${apiKeyGuide()}${field('access_token','服务访问令牌（启用访问控制时填写）','','password')}`,'保存设置',async form=>{
    const d=new FormData(form);if(d.get('access_token'))state.token=String(d.get('access_token'));
    if($('#model-api-key').value&&!verified)throw new Error('请先验证 API Key 并选择模型');
    if(verified){await api('/v1/model/configure',jsonBody({ticket:verified.ticket,model:d.get('selected_model'),input_price:Number(d.get('input_price'))||null,output_price:Number(d.get('output_price'))||null}))}
    await api('/v1/collection/configure',jsonBody({browser:d.get('browser'),network:d.get('browser_network')}));
    storage.set('theme',d.get('theme'));applyTheme();$('#modal').close();await connect();toast('设置已保存');
    if(state.resumeLinkAnalysis===state.analysis?.analysis_id&&state.config?.llm_configured){state.resumeLinkAnalysis=null;const urls=state.pendingSelectedLinks||[inputLink(state.analysis.input)];state.pendingSelectedLinks=null;await collectSelectedLinks(urls)}
  });
  async function verify(){
    const key=$('#model-api-key').value.trim();if(!key)return;
    const provider=$('[name="provider"]').value;verified=null;$('#model-choices').innerHTML='';$('#model-config-hint').textContent='正在验证所选供应商…';
    try{const result=await api('/v1/model/detect',jsonBody({api_key:key,provider,base_url:$('[name="base_url"]').value.trim()}));if($('#model-api-key').value.trim()!==key)return;if(result.needs_provider){$('#model-config-hint').textContent=result.message;return}verified=result;$('#model-config-hint').textContent=result.provider_name+' · '+result.base_url;$('#model-choices').innerHTML=select('selected_model','分析模型',result.models.map(id=>[id,id]),result.model)+(result.needs_prices?`<p class="note">为继续遵守人民币 1.5 元上限，请按供应商价格填写单价；美元价格需换算。</p><div class="field-row">${field('input_price','输入单价（元 / 百万 token）','','number','min="0.000001" step="any" required')}${field('output_price','输出单价（元 / 百万 token）','','number','min="0.000001" step="any" required')}</div>`:'')}catch(error){$('#model-config-hint').textContent=error.message}
  }
  $('#verify-model-key').addEventListener('click',verify);
  $('#model-api-key').addEventListener('input',()=>{verified=null;$('#model-choices').innerHTML=''});
  $('#model-api-key').addEventListener('change',verify);
  $('[name="provider"]').addEventListener('change',verify);
  $('[name="base_url"]').addEventListener('input',()=>{verified=null;$('#model-choices').innerHTML=''});
}
function sourceRows(){
  const a=state.analysis;if(!a)return [];
  const sources=[a.object,...(a.candidates||[])].filter(Boolean),known=new Set(sources.map(s=>s.url||s.source_url||''));
  for(const r of a.reviews||[]){const url=r.source_url||'';if(!known.has(url)){known.add(url);sources.push({url,platform:r.platform,title:r.product_name||'导入评论来源'})}}
  return sources.map(s=>({...s,...(a.source_identities?.[s.url||s.source_url||'']||{})}));
}
function productsView(){
  if(!state.analysis)return overview();
  const busy=busyStatuses.has(state.analysis.status),groups=state.analysis.groups||[];
  return `${actionButtons()}<div class="section-bar"><h2>商品来源与规格核对</h2><span class="badge">同品牌 · 同型号 · 同关键规格才合并</span></div><p class="note">缺少身份字段或评论所选规格时单独待确认。同 SPU 的不同容量、尺寸或套装分别统计；不按标题相似就合并。</p><div class="table-wrap"><table><thead><tr><th>来源 / 商品</th><th>品牌 / 型号</th><th>关键规格</th><th>核对</th></tr></thead><tbody>${sourceRows().map(s=>`<tr><td><strong>${esc(s.title||'商品信息待补')}</strong><div class="cell-meta">${esc(label[s.platform]||s.platform||'手动导入')} · ${sourceLink(s.url||s.source_url)}</div></td><td>${esc(s.brand||'品牌待确认')}<div class="cell-meta">${esc(s.model||'型号待确认')}</div></td><td>${esc(Object.entries(s.key_specs||{}).map(([k,v])=>k+'：'+v).join(' / ')||'规格待确认')}<div class="cell-meta">${s.specs_confirmed?'关键规格已核对':'尚未确认规格完整性'}</div></td><td><button class="button" data-edit-source="${esc(s.url||s.source_url||'__primary__')}" ${busy?'disabled':''}>核对 / 编辑</button></td></tr>`).join('')}</tbody></table></div><div class="section-bar"><h2>独立分析组 <span class="badge">${groups.length}</span></h2></div>${groups.length?`<div class="table-wrap"><table><thead><tr><th>商品 / 规格</th><th>来源</th><th>原文</th><th>已分析</th><th>正面 / 负面</th><th>身份状态</th><th>证据</th></tr></thead><tbody>${groups.map(g=>`<tr><td><strong>${esc(g.title)}</strong><div class="cell-meta">${esc(g.brand||'品牌待确认')} · ${esc(g.model||'型号待确认')} · ${esc(g.spec_label)}</div></td><td>${esc(g.platforms.map(p=>label[p]||p).join(' / '))}</td><td class="numeric">${g.review_count}</td><td class="numeric">${g.statistics?.successful_count||0}</td><td class="numeric">${g.statistics?.sentiment_distribution?.positive||0} / ${g.statistics?.sentiment_distribution?.negative||0}</td><td><span class="badge ${g.status==='confirmed'?'good':'warn'}">${g.status==='confirmed'?'已核对':'单独待确认'}</span></td><td><button class="text-button" data-select-group="${esc(g.group_id)}">查看原文 →</button></td></tr>`).join('')}</tbody></table></div>`:empty('尚未形成评论分组','可先核对来源身份，再导入或采集评论。','import','导入评论')}`;
}
function editSource(key){
  const url=key==='__primary__'?'':key,s=sourceRows().find(item=>(item.url||item.source_url||'')===url);if(!s)return;
  const specs=Object.entries(s.key_specs||{}).map(([name,value])=>name+'='+value).join('\n');
  showModal('核对商品身份与规格',`${field('title','商品名称',s.title||'','text','maxlength="500"')}${field('brand','品牌',s.brand||'','text','maxlength="120"')}${field('model','型号 / 厂家货号',s.model||'','text','maxlength="120"')}<label class="field"><span>关键规格（每行一项，例如 容量=500ml）</span><textarea name="key_specs" maxlength="10000">${esc(specs)}</textarea><small>填写会影响使用或购买的规格，如尺寸、容量、颜色、版本、套装数量；不知道时保留待确认。</small></label><div class="check-row"><label><input type="checkbox" name="specs_confirmed" ${s.specs_confirmed?'checked':''}>品牌、型号及关键规格均已核对</label></div><div class="check-row"><label><input type="checkbox" name="selected_scope" ${s.reviews_scope==='selected_spec'?'checked':''}>已确认此来源评论仅对应上述规格</label></div><p class="note">未确认评论范围时，缺少所选规格的评论仍单独待确认。保存不会调用模型。</p>`,'保存核对结果',async form=>{
    const d=new FormData(form),keySpecs=Object.create(null);
    for(const line of String(d.get('key_specs')||'').split('\n').filter(s=>s.trim())){const pos=line.indexOf('=');if(pos<1||!line.slice(pos+1).trim())throw new Error('每行请使用 规格名称=规格值');const name=line.slice(0,pos).trim();if(Object.hasOwn(keySpecs,name))throw new Error('规格名称重复：'+name);keySpecs[name]=line.slice(pos+1).trim()}
    const payload={source_url:url,title:String(d.get('title')||'').trim(),brand:String(d.get('brand')||'').trim(),model:String(d.get('model')||'').trim(),key_specs:keySpecs,specs_confirmed:d.has('specs_confirmed'),reviews_scope:d.has('selected_scope')?'selected_spec':'unknown'};
    acceptAnalysis(await api(apiPath('/source-identity'),{method:'PATCH',body:JSON.stringify(payload)}));$('#modal').close();toast('身份与规格已保存，分组统计已更新');
  });
}
function draftsView(){
  const items=state.analysis?.report?.drafts||[],busy=busyStatuses.has(state.analysis?.status);
  const names={selling_point:'商品卖点',support_script:'客服话术',content_topic:'内容选题',schedule:'排期'};
  return `<div class="section-bar"><h2>可编辑运营草稿 <span class="badge">${items.length}</span></h2><button class="button" data-command="drafts-csv" ${items.length?'':'disabled'}>↓ 导出草稿</button></div><div class="heading-actions">${Object.entries(names).map(([kind,name])=>`<button class="button primary" data-command="generate_${kind}" ${busy?'disabled':''}>生成${name}</button>`).join('')}</div><p class="note">按商品组分别整理。产品参数、处理政策和对外承诺需核对；日期、渠道和指标由运营编辑。重新生成会保留人工修改。</p>${items.length?`<div class="draft-grid">${items.map(d=>`<article class="panel draft-card"><div class="panel-title"><span class="badge">${names[d.kind]||esc(d.kind)}</span><span>${d.edited?'已编辑':'草稿'}${d.needs_review?' · 证据需复核':''}</span></div><h3>${esc(d.title)}</h3><p class="cell-meta">${esc(d.group_title||'商品组待确认')}</p><p class="draft-body">${esc(d.body)}</p><div class="draft-meta"><span>${esc(d.channel||'渠道待定')} · ${esc(d.scheduled_date||'日期待定')}</span><button class="button" data-edit-draft="${esc(d.id)}" ${busy?'disabled':''}>编辑草稿</button></div></article>`).join('')}</div>`:'<p class="note">点击上方对应按钮，仅生成所选类型的草稿。有原句支持才生成；使用已配置模型生成，与本次分析共用最高 ¥1.50 预算；预算不足时保留已有内容并提示。</p>'}`;
}
function editDraft(id){
  const draft=state.analysis?.report?.drafts?.find(d=>d.id===id);if(!draft)return;
  showModal('编辑运营草稿',`${field('title','标题',draft.title,'text','required maxlength="200"')}<label class="field"><span>正文 / 执行说明</span><textarea name="body" required maxlength="10000" class="draft-editor">${esc(draft.body)}</textarea></label><div class="field-row">${field('channel','渠道',draft.channel||'','text','maxlength="120"')}${field('scheduled_date','排期日期',draft.scheduled_date||'','date')}</div>${select('state','状态',[['draft','待核对草稿'],['ready','已校对'],['archived','已归档']],draft.state||'draft')}<p class="note">${esc(draft.notes||'')}</p>${(draft.evidence_ids||[]).map(rid=>`<button class="text-button" type="button" data-evidence="${esc(rid)}">查看原文证据 →</button>`).join(' ')}`,'保存草稿',async form=>{acceptAnalysis(await api(apiPath('/drafts/'+encodeURIComponent(id)),{method:'PATCH',body:JSON.stringify(Object.fromEntries(new FormData(form)))}));$('#modal').close();toast('草稿已保存')});
}

function isShowcaseDemo(){return window.REVIEWAGENT_DEMO===true||document.documentElement.dataset.mode==='demo'}
function apiKeyGuide(){return `<details class="panel"><summary>如何获取 API Key 与设置模型预算</summary><ol class="note"><li>打开供应商官方平台并登录，进入 API Keys 页面，创建后复制 Key。</li><li>粘贴到上方输入框，验证供应商并选择模型。通用 sk- 前缀无法唯一识别供应商，请手动选择。</li><li>输入和输出单价分别计费。系统按人民币价格自动折算每次请求的 token 上限，分析、洞察、草稿和重试共用本次最高 ¥1.50 预算。未知价格需先按官方价格补充，外币单价先换算成人民币。</li></ol><p class="note"><a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener noreferrer">DeepSeek API Keys ↗</a> · <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">OpenAI API Keys ↗</a> · <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Google AI Studio API Keys ↗</a> · <a href="https://platform.claude.com/settings/keys" target="_blank" rel="noopener noreferrer">Claude API Keys ↗</a></p><p class="note">网页聊天订阅与 API 用量分开计费；请勿将 Key 粘贴进评论、链接或分享截图。</p></details>`}
function showModelOnboarding(){
  if(isShowcaseDemo()||state.config?.llm_configured||$('#modal').open)return;
  showModal('先配置你的分析模型',`<p>请点击工作台左下角的设置按钮，配置 API Key 并选择分析模型。</p><p class="note">暂不配置也可以搜索商品、抓取评论；模型分析、洞察和运营草稿需要配置后才能完成。</p><button type="button" class="button primary" id="onboarding-configure">立即配置模型</button>${apiKeyGuide()}`,'',null);
  $('#onboarding-configure').addEventListener('click',modelSettings);
}

draftsView = function () {
  const items = state.analysis?.report?.drafts || [], busy = busyStatuses.has(state.analysis?.status);
  const groups = [
    ['selling_point', '商品卖点', '详情页与商品卡可直接使用'],
    ['support_script', '客服话术', '客服知识库可直接使用'],
    ['content_topic', '内容选题 · 小红书图文模板', '标题 / 正文 / 配图建议 / 话题，按小红书笔记结构生成'],
    ['schedule', '排期', '内容与行动的时间安排'],
  ];
  const buttons = groups.map(([kind, name]) => '<button class="button primary" data-command="generate_' + kind + '" ' + (busy ? 'disabled' : '') + '>生成' + (kind === 'content_topic' ? '内容选题' : name) + '</button>').join('');
  const cards = groups.map(([kind, name, hint]) => {
    const list = items.filter(d => d.kind === kind);
    if (!list.length) return '';
    const body = list.map(d => '<article class="panel draft-card"><div class="panel-title"><span class="badge">' + (kind === 'content_topic' ? '小红书图文' : name) + '</span><span>' + (d.edited ? '已编辑' : '草稿') + (d.needs_review ? ' · 证据需复核' : '') + '</span></div><h3>' + esc(d.title) + '</h3><p class="cell-meta">' + esc(d.group_title || '商品组待确认') + '</p><p class="draft-body">' + esc(d.body) + '</p><div class="draft-meta"><span>' + esc(d.channel || '渠道待定') + ' · ' + esc(d.scheduled_date || '日期待定') + '</span><button class="button" data-edit-draft="' + esc(d.id) + '" ' + (busy ? 'disabled' : '') + '>编辑草稿</button></div></article>').join('');
    return '<div class="section-bar"><h2>' + name + ' <span class="badge">' + list.length + '</span></h2><span class="subtext">' + hint + '</span></div><div class="draft-grid">' + body + '</div>';
  }).join('');
  return '<div class="section-bar"><h2>可编辑运营草稿 <span class="badge">' + items.length + '</span></h2><button class="button" data-command="drafts-csv" ' + (items.length ? '' : 'disabled') + '>↓ 导出草稿</button></div><div class="heading-actions">' + buttons + '</div><p class="note">按类型分区展示，避免混在一起。产品参数、处理政策和对外承诺需核对；日期、渠道和指标由运营编辑。重新生成会保留人工修改。</p>' + (items.length ? cards : '<p class="note">点击上方对应按钮，仅生成所选类型的草稿。有原句支持才生成；使用已配置模型生成，与本次分析共用最高 ¥1.50 预算；预算不足时保留已有内容并提示。</p>');
};
