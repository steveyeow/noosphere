/* Noosphere v3 */
const API='/api/v1';
let _gAnim=null,_lpAnim=null,_files=[],_mCid=null,_corpora=[];

const isDark=()=>document.documentElement.classList.contains('dark')||(!document.documentElement.classList.contains('light')&&window.matchMedia('(prefers-color-scheme: dark)').matches);
const PAL=['#e76f51','#2a9d8f','#264653','#e9c46a','#f4a261','#588157','#457b9d','#9b2226','#6d6875','#b56576','#355070','#6c757d','#e07a5f','#3d405b','#81b29a'];
const cC=n=>{let h=0;for(let i=0;i<n.length;i++)h=((h<<5)-h+n.charCodeAt(i))|0;return PAL[Math.abs(h)%PAL.length]};
const hR=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const cp=(t,b)=>{navigator.clipboard.writeText(t).then(()=>{if(b){const o=b.textContent;b.textContent='Copied!';setTimeout(()=>b.textContent=o,1200)}})};

/* ── Route ── */
async function route(){const h=window.location.hash||'#/';stopLP();
  if(h==='#/'||h===''||h==='#/landing'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLP();}
  else{document.getElementById('page-landing').classList.add('hidden');document.getElementById('page-main').classList.remove('hidden');await loadCorpora();renderSB(h);
    if(h==='#/main'){renderNet();hideRP();}else if(h.startsWith('#/corpus/')){await renderCorpus(h.split('/')[2]);}else{renderNet();hideRP();}}}

async function loadCorpora(){try{const r=await fetch(`${API}/corpora`);_corpora=await r.json()}catch(e){_corpora=[]}}

function renderSB(h){
  const el=document.getElementById('sb-corpora');
  el.innerHTML=_corpora.length===0?'<div style="padding:5px 12px;font-size:10px;color:var(--tx3)">No corpora yet</div>'
    :_corpora.map(c=>{const a=h==='#/corpus/'+c.id?' active':'';return`<a href="#/corpus/${c.id}" class="sb-corpus${a}"><span class="sb-dot" style="background:${cC(c.name)}"></span><span class="sb-corpus-name">${esc(c.name)}</span></a>`}).join('');
  document.getElementById('nav-network').classList.toggle('active',h==='#/main');
}

/* ══════ LANDING ══════ */
const DEMO=[{name:"Lenny's Newsletter",d:'product, growth, startups',c:'#e76f51'},{name:'Paul Graham Essays',d:'startups, philosophy',c:'#2a9d8f'},{name:'AI Research',d:'AI, machine learning',c:'#264653'},{name:'Feynman Lectures',d:'physics, science',c:'#f4a261'},{name:'Stoic Philosophy',d:'philosophy, ethics',c:'#588157'},{name:'YC Startup School',d:'startups, growth',c:'#457b9d'},{name:'Design Patterns',d:'software, design',c:'#e9c46a'},{name:'World History',d:'history, culture',c:'#b56576'}];

function renderLP(){
  const el=document.getElementById('page-landing');
  el.innerHTML=`<div class="lp"><nav class="lp-top"><span class="lp-brand"><svg width="17" height="17" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere</span><button class="lp-cta" id="lp-cta">Get Started</button></nav><div class="lp-cv" id="lp-cv"></div><div class="lp-ct"><div class="lp-h"><h1 class="lp-h1">Publish your knowledge for agents.</h1><p class="lp-sub">Turn any knowledge base into an agent-readable corpus. AI agents discover, query, and cite your knowledge via MCP and API. You control access: free, private, or paid.</p><button class="lp-go" id="lp-go">Get Started →</button></div><div class="lp-demo"><div class="lp-dt">Semantic Search with Citations</div><div class="lp-dq"><input value="How should startups think about pricing?" readonly /><button>Search</button></div><div class="lp-r"><div class="lp-sc">Score: 0.87</div><div class="lp-rt">"The biggest mistake I see in pricing is undercharging..."</div><div class="lp-ci">Pricing your AI product — Jul 2025</div></div><div class="lp-r"><div class="lp-sc">Score: 0.82</div><div class="lp-rt">"Value-based pricing means charging based on the outcome you deliver..."</div><div class="lp-ci">The pricing playbook — Mar 2024</div></div></div></div></div>`;
  document.getElementById('lp-cta').onclick=()=>{location.hash='#/main'};
  document.getElementById('lp-go').onclick=()=>{location.hash='#/main'};
  drawLPGraph();
}
function stopLP(){if(_lpAnim){cancelAnimationFrame(_lpAnim);_lpAnim=null}}

function drawLPGraph(){
  const co=document.getElementById('lp-cv');if(!co)return;
  const tk=m=>(m.d||'').split(/[,;]+/).map(d=>d.trim().toLowerCase()).filter(Boolean);
  const ns=DEMO.map((m,i)=>({id:'l'+i,name:m.name,dom:m.d,color:m.c,ini:m.name.split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk:tk(m)}));
  const lk=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=ns[i].tk.filter(t=>ns[j].tk.some(u=>t===u||t.includes(u)||u.includes(t)));if(s.length)lk.push({source:ns[i].id,target:ns[j].id,s:s.length})}
  const dp=devicePixelRatio||1,W=co.clientWidth||800,H=co.clientHeight||600,BR=Math.max(14,Math.min(22,W/(ns.length*2.5)));
  const cv=document.createElement('canvas');cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';co.appendChild(cv);const cx=cv.getContext('2d');cx.scale(dp,dp);
  const pts=[];lk.forEach(l=>{for(let i=0;i<Math.max(1,Math.round(l.s*1.5));i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.2,op:.3+Math.random()*.5})});
  const gX=W*.55,zn=[{cx:W*.1+170,cy:H/2,hw:200,hh:120}];
  function av(){let n;function f(){for(const nd of n)for(const z of zn){const dx=nd.x-z.cx,dy=nd.y-z.cy,ox=z.hw-Math.abs(dx),oy=z.hh-Math.abs(dy);if(ox>0&&oy>0){if(ox<oy){nd.vx+=(dx>=0?1:-1)*ox*.08;nd.vx*=.85}else{nd.vy+=(dy>=0?1:-1)*oy*.08;nd.vy*=.85}}}}f.initialize=x=>{n=x};return f}
  const sim=d3.forceSimulation(ns).force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(55,220-d.s*50)).strength(d=>.08+d.s*.15)).force('charge',d3.forceManyBody().strength(-400).distanceMax(550)).force('center',d3.forceCenter(gX,H/2).strength(.02)).force('collision',d3.forceCollide().radius(BR+12)).force('avoid',av()).alphaDecay(.03).velocityDecay(.35);
  let hov=null,mp=null;cv.onmousemove=e=>{const r=cv.getBoundingClientRect();mp=[e.clientX-r.left,e.clientY-r.top];hov=null;for(const n of ns)if(Math.hypot(n.x-mp[0],n.y-mp[1])<BR+4){hov=n;break}cv.style.cursor=hov?'pointer':'default'};cv.onmouseleave=()=>{hov=null;mp=null};
  function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);
    for(const l of lk){const s=l.source,t=l.target;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=`rgba(160,170,190,${.1+l.s*.07})`;cx.lineWidth=.5+l.s*.3;cx.stroke()}
    for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=`rgba(130,150,200,${p.op*.35})`;cx.fill()}
    for(const n of ns){const h=hov===n;let r=BR;if(mp){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<180?BR*(1+(1-d/180)*.45):BR*.8}if(h)r=Math.max(r,BR*1.35);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);
      const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*1.8);g.addColorStop(0,`rgba(${cr},${cg},${cb},${h?.1:.04})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*1.8,0,Math.PI*2);cx.fillStyle=g;cx.fill();
      if(h){cx.beginPath();cx.arc(n.x,n.y,rr+2,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},.4)`;cx.lineWidth=1.5;cx.stroke()}
      cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);cx.fillStyle=n.color;cx.fill();cx.strokeStyle='rgba(255,255,255,.2)';cx.lineWidth=1;cx.stroke();
      cx.fillStyle='rgba(255,255,255,.92)';cx.font=`700 ${rr*.5}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);
      const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.9:.65})`:`rgba(30,35,50,${h?.85:.55})`;cx.font=`600 ${h?10:9}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+10);
      cx.fillStyle=dk?'rgba(200,200,210,.35)':'rgba(100,110,130,.35)';cx.font='400 7px Inter,sans-serif';cx.fillText(n.dom.length>24?n.dom.slice(0,22)+'…':n.dom,n.x,n.y+rr+19)}
    cx.restore();_lpAnim=requestAnimationFrame(draw)}
  sim.on('tick',()=>{});_lpAnim=requestAnimationFrame(draw);
}

/* ══════ NETWORK ══════ */
function renderNet(){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const ct=document.getElementById('content');
  ct.innerHTML=`
    <div class="nv-bar">
      <div class="nv-search"><input class="nv-si" id="gs-i" placeholder="Search the Noosphere..." /><button class="nv-sb" id="gs-b">Search</button></div>
      <button class="expand-btn" id="exp-btn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Expand the Noosphere</button>
    </div>
    <div id="gs-res" class="nv-results"></div>
    <div class="nv-graph" id="nv-g"></div>
    <div class="nv-tt hidden" id="nv-tt"></div>`;
  document.getElementById('exp-btn').onclick=()=>openModal();
  const gB=document.getElementById('gs-b'),gI=document.getElementById('gs-i'),gR=document.getElementById('gs-res');
  async function gs(){const q=gI.value.trim();if(!q)return;gR.innerHTML='<div class="empty">Searching...</div>';
    try{const r=await fetch(`${API}/search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,top_k:5})});const d=await r.json();
      if(!d.results||!d.results.length){gR.innerHTML='<div class="empty">No results found</div>';return}
      gR.innerHTML=d.results.map(r=>`<div class="sr-card"><div class="sr-score">Score: ${r.score}</div><div class="sr-corpus">from ${esc(r.corpus_name||'')}</div><div class="sr-text">${esc(r.text)}</div>${r.citation?`<div class="sr-cite">${esc(r.citation.document_title||'')} ${r.citation.date?'· '+r.citation.date:''}</div>`:''}</div>`).join('')+`<div style="font-size:9px;color:var(--tx3);margin-top:4px">${d.corpora_searched} corpora searched</div>`}
    catch(e){gR.innerHTML='<div class="empty">Search failed</div>'}}
  gB.onclick=gs;gI.onkeydown=e=>{if(e.key==='Enter')gs()};
  drawNSGraph();
}

function drawNSGraph(){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const co=document.getElementById('nv-g');if(!co||!_corpora.length){if(co&&!_corpora.length)co.innerHTML='<div class="empty">The Noosphere is empty.<br>Click "Expand the Noosphere" to add knowledge.</div>';return}co.innerHTML='';
  const ns=_corpora.map(c=>{const tg=Array.isArray(c.tags)?c.tags:[];const tk=[];tg.forEach(t=>tk.push(...t.toLowerCase().split(/[\s,]+/).filter(Boolean)));return{...c,color:cC(c.name),ini:(c.name||'?').split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk}});
  const lk=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=new Set(ns[i].tk);const sh=[...new Set(ns[j].tk)].filter(t=>s.has(t));if(sh.length)lk.push({source:ns[i].id,target:ns[j].id,s:sh.length})}
  const dp=devicePixelRatio||1,W=co.clientWidth||600,H=co.clientHeight||280,BR=Math.max(14,Math.min(24,W/(ns.length*2.5)));
  const cv=document.createElement('canvas');cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';co.appendChild(cv);const cx=cv.getContext('2d');cx.scale(dp,dp);
  const pts=[];lk.forEach(l=>{for(let i=0;i<Math.max(1,Math.round(l.s*1.5));i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.2,op:.3+Math.random()*.5})});
  const sim=d3.forceSimulation(ns).force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(50,170-d.s*40)).strength(d=>.1+d.s*.15)).force('charge',d3.forceManyBody().strength(-300).distanceMax(450)).force('center',d3.forceCenter(W/2,H/2).strength(.06)).force('collision',d3.forceCollide().radius(BR+10)).alphaDecay(.04).velocityDecay(.4);
  let hov=null,mp=null;const tt=document.getElementById('nv-tt');
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect();mp=[e.clientX-r.left,e.clientY-r.top];hov=null;for(const n of ns)if(Math.hypot(n.x-mp[0],n.y-mp[1])<BR+4){hov=n;break}cv.style.cursor=hov?'pointer':'grab';
    if(hov&&tt){tt.innerHTML=`<div class="tt-n">${esc(hov.name)}</div><div class="tt-m">${hov.document_count} sources · ${hov.access_level} · Click to view</div>`;tt.classList.remove('hidden');tt.style.left=(e.clientX-r.left+10)+'px';tt.style.top=(e.clientY-r.top-6)+'px'}else if(tt){tt.classList.add('hidden')}};
  cv.onmouseleave=()=>{hov=null;mp=null;if(tt)tt.classList.add('hidden')};
  cv.onclick=()=>{if(hov)location.hash='#/corpus/'+hov.id};
  function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);
    for(const l of lk){const s=l.source,t=l.target;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=`rgba(160,170,190,${.1+l.s*.07})`;cx.lineWidth=.5+l.s*.3;cx.stroke()}
    for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=`rgba(130,150,200,${p.op*.35})`;cx.fill()}
    for(const n of ns){const h=hov===n;let r=BR;if(mp){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<160?BR*(1+(1-d/160)*.4):BR*.8}if(h)r=Math.max(r,BR*1.35);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);
      const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*1.8);g.addColorStop(0,`rgba(${cr},${cg},${cb},${h?.1:.04})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*1.8,0,Math.PI*2);cx.fillStyle=g;cx.fill();
      if(h){cx.beginPath();cx.arc(n.x,n.y,rr+2,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},.4)`;cx.lineWidth=1.5;cx.stroke()}
      cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);cx.fillStyle=n.color;cx.fill();cx.strokeStyle='rgba(255,255,255,.2)';cx.lineWidth=1;cx.stroke();
      cx.fillStyle='rgba(255,255,255,.92)';cx.font=`700 ${rr*.5}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);
      const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.9:.65})`:`rgba(30,35,50,${h?.85:.55})`;cx.font=`600 ${h?10:9}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+10)}
    cx.restore();_gAnim=requestAnimationFrame(draw)}
  sim.on('tick',()=>{});_gAnim=requestAnimationFrame(draw);
}

/* ══════ CORPUS ══════ */
async function renderCorpus(id){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const ct=document.getElementById('content');ct.innerHTML='<div class="empty">Loading...</div>';
  let c;try{const r=await fetch(`${API}/corpora/${id}`);c=await r.json()}catch(e){ct.innerHTML='<div class="empty">Not found</div>';hideRP();return}
  let docs=[];try{const r=await fetch(`${API}/corpora/${id}/documents`);docs=await r.json()}catch(e){}
  let an={};try{const r=await fetch(`${API}/corpora/${id}/analytics?limit=10`);an=await r.json()}catch(e){}

  ct.innerHTML=`
    <div class="cv-sec"><div class="cv-st">Sources (${docs.length}) <button class="btn-add" id="cv-add">+ Add</button></div>
      <div id="cv-docs">${docs.length===0?'<div class="empty">No sources yet. Click + Add to upload files or paste a URL.</div>'
        :docs.map((d,i)=>`<div class="src-item${i===0?' expanded':''}" data-id="${d.id}"><div class="src-head"><span class="src-title">${esc(d.title)}</span><span class="src-meta">${d.word_count||0}w${d.date?' · '+d.date:''}</span><span class="src-arrow">▸</span></div>${i===0?'<div class="src-body" id="src-body-0">Loading...</div>':''}</div>`).join('')}</div>
    </div>
    <div class="cv-sec"><div class="cv-st">Try a Search</div>
      <div style="display:flex;gap:5px"><input class="nv-si" id="cv-q" placeholder="Ask a question..." style="font-size:12px;padding:7px 10px" /><button class="nv-sb" id="cv-s" style="font-size:11px;padding:6px 12px">Search</button></div>
      <div id="cv-r" style="margin-top:6px"></div>
    </div>`;

  showRP(c,an);

  // Auto-expand first doc
  if(docs.length>0){
    try{const r=await fetch(`${API}/corpora/${id}/documents/${docs[0].id}`);const d=await r.json();const b=document.getElementById('src-body-0');if(b)b.textContent=d.content||''}catch(e){}}

  document.getElementById('cv-add').onclick=()=>openModal(id);
  ct.querySelectorAll('.src-item').forEach(item=>{
    item.addEventListener('click',async()=>{
      const wasExpanded=item.classList.contains('expanded');
      if(wasExpanded){const b=item.querySelector('.src-body');if(b)b.remove();item.classList.remove('expanded');return}
      item.classList.add('expanded');
      try{const r=await fetch(`${API}/corpora/${id}/documents/${item.dataset.id}`);const d=await r.json();const b=document.createElement('div');b.className='src-body';b.textContent=d.content||'';item.appendChild(b)}catch(e){}
    });
  });

  const sB=document.getElementById('cv-s'),sI=document.getElementById('cv-q'),sR=document.getElementById('cv-r');
  async function ds(){const q=sI.value.trim();if(!q)return;sR.innerHTML='<div class="empty">Searching...</div>';
    try{const r=await fetch(`${API}/corpora/${id}/search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,top_k:5})});const d=await r.json();
      if(!d.results||!d.results.length){sR.innerHTML='<div class="empty">No results</div>';return}
      sR.innerHTML=d.results.map(r=>`<div class="sr-card"><div class="sr-score">Score: ${r.score}</div><div class="sr-text">${esc(r.text)}</div>${r.citation?`<div class="sr-cite">${esc(r.citation.document_title||'')} ${r.citation.date?'· '+r.citation.date:''}</div>`:''}</div>`).join('')+`<div style="font-size:9px;color:var(--tx3);margin-top:4px">${d.usage.latency_ms}ms · ${d.usage.chunks_searched} chunks</div>`}
    catch(e){sR.innerHTML='<div class="empty">Search failed</div>'}}
  sB.onclick=ds;sI.onkeydown=e=>{if(e.key==='Enter')ds()};
}

const ACCESS_MSG={
  public:'This corpus is discoverable by all agents in the Noosphere. Anyone can query it without authentication.',
  private:'This corpus is only accessible via your personal endpoint. It will not appear in the Noosphere registry.',
  token:'Access requires a token key. You can generate and share keys with specific people or agents. (Token management coming in Phase 2)',
  paid:'Agents pay per query or subscribe to access. Configure your Stripe keys in .env to enable payments. (Payment integration coming in Phase 2)'
};

function showRP(c,an){
  const rp=document.getElementById('rpanel');rp.classList.remove('hidden');
  const host=location.origin;const tg=Array.isArray(c.tags)?c.tags:[];const al=c.access_level||'public';

  rp.innerHTML=`
    <div class="rp-name">${esc(c.name)}</div>
    ${c.author_name?`<div class="rp-author">by ${esc(c.author_name)}</div>`:''}
    ${c.description?`<div class="rp-desc">${esc(c.description)}</div>`:''}
    ${tg.length?`<div class="rp-tags">${tg.map(t=>`<span class="rp-tag">${esc(t)}</span>`).join('')}</div>`:''}

    <div class="rp-sec"><div class="rp-lbl">Connect Agents</div>
      <div class="rp-ep"><span class="rp-epl">MCP</span><span class="rp-epu">${host}/mcp</span><button class="rp-cp" onclick="cp('${host}/mcp',this)">Copy</button></div>
      <div class="rp-ep"><span class="rp-epl">API</span><span class="rp-epu">${host}/api/v1/corpora/${c.id}/search</span><button class="rp-cp" onclick="cp('${host}/api/v1/corpora/${c.id}/search',this)">Copy</button></div>
    </div>

    <div class="rp-sec"><div class="rp-lbl">Stats</div>
      <div class="rp-stats">
        <div><div class="rp-sv">${c.document_count}</div><div class="rp-sl">sources</div></div>
        <div><div class="rp-sv">${c.chunk_count}</div><div class="rp-sl">chunks</div></div>
        <div><div class="rp-sv">${(c.word_count||0).toLocaleString()}</div><div class="rp-sl">words</div></div>
        <div><div class="rp-sv">${an.total_queries||0}</div><div class="rp-sl">queries</div></div>
      </div>
    </div>

    <div class="rp-sec"><div class="rp-lbl">Access</div>
      <div class="rp-row">
        <select id="rp-acc">
          <option value="public" ${al==='public'?'selected':''}>Public</option>
          <option value="private" ${al==='private'?'selected':''}>Private</option>
          <option value="token" ${al==='token'?'selected':''}>Token-gated</option>
          <option value="paid" ${al==='paid'?'selected':''}>Paid</option>
        </select>
        <button class="btn-sm" id="rp-sv">Save</button>
      </div>
      <div class="rp-msg info" id="rp-msg">${ACCESS_MSG[al]||''}</div>
    </div>

    <div class="rp-sec">
      <button class="btn-primary" id="rp-idx" style="width:100%;margin-bottom:4px">Re-index</button>
      ${c.embedding_model?`<div style="font-size:9px;color:var(--tx3)">Model: ${c.embedding_model}</div>`:''}
      <div style="font-size:9px;color:var(--tx3)">Status: ${c.status}</div>
    </div>`;

  document.getElementById('rp-acc').onchange=()=>{document.getElementById('rp-msg').textContent=ACCESS_MSG[document.getElementById('rp-acc').value]||''};
  document.getElementById('rp-sv').onclick=async()=>{
    const v=document.getElementById('rp-acc').value;
    await fetch(`${API}/corpora/${c.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:v})});
    await loadCorpora();renderSB(location.hash);renderCorpus(c.id)};
  document.getElementById('rp-idx').onclick=async()=>{
    document.getElementById('rp-idx').textContent='Indexing...';document.getElementById('rp-idx').disabled=true;
    try{await fetch(`${API}/corpora/${c.id}/index`,{method:'POST'})}catch(e){}renderCorpus(c.id)};
}
function hideRP(){document.getElementById('rpanel').classList.add('hidden')}

/* ══════ MODAL ══════ */
function openModal(eid){
  _files=[];_mCid=eid||null;
  document.getElementById('modal').classList.remove('hidden');
  const isNew=!_mCid;
  document.getElementById('modal-title').textContent=isNew?'Expand the Noosphere':'Add Sources';
  document.getElementById('modal-submit').textContent=isNew?'Publish':'Upload';
  document.getElementById('modal-status').classList.add('hidden');
  document.getElementById('modal-body').innerHTML=`
    ${isNew?`<label class="fl">Name *</label><input type="text" id="f-n" class="fi" placeholder="e.g. My Blog, Research Notes" />
    <label class="fl">Description</label><input type="text" id="f-d" class="fi" placeholder="What knowledge does this contain?" />
    <label class="fl">Author</label><input type="text" id="f-a" class="fi" placeholder="Your name" />
    <label class="fl">Tags</label><input type="text" id="f-t" class="fi" placeholder="AI, startups (comma-separated)" />
    <label class="fl">Access</label>
    <div class="acc-opts">
      <label class="acc-opt"><input type="radio" name="f-ac" value="public" checked /> <strong>Public</strong> — discoverable by all agents</label>
      <label class="acc-opt"><input type="radio" name="f-ac" value="private" /> <strong>Private</strong> — only your endpoint</label>
      <label class="acc-opt"><input type="radio" name="f-ac" value="token" /> <strong>Token-gated</strong> — access keys for specific agents</label>
      <div class="acc-note">Token management coming in Phase 2</div>
      <label class="acc-opt"><input type="radio" name="f-ac" value="paid" /> <strong>Paid</strong> — agents pay per query</label>
      <div class="acc-note">Requires Stripe keys in .env · Phase 2</div>
    </div>`:''}
    <label class="fl">Upload files (.md, .txt)</label>
    <div class="dz" id="dz"><input type="file" id="f-f" multiple accept=".md,.txt,.text,.html" hidden /><div class="dz-text">Drop files here or <span class="dz-browse">browse</span></div><div class="dz-list" id="dz-l"></div></div>
    <label class="fl">Or paste a URL</label>
    <input type="text" id="f-u" class="fi" placeholder="https://example.com/article" />
    <label class="fck"><input type="checkbox" id="f-i" checked /> Auto-index after upload</label>
    ${isNew?`<div class="reg-prompt"><strong>🌐 Join the Noosphere?</strong> Register so agents worldwide can discover your knowledge. Only metadata is shared — content stays on your server.<br/><label class="fck"><input type="checkbox" id="f-r" checked /> Register to the Noosphere</label></div>`:''}`;
  const dz=document.getElementById('dz'),fi=document.getElementById('f-f');
  if(dz&&fi){dz.onclick=()=>fi.click();dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag-over')};dz.ondragleave=()=>dz.classList.remove('drag-over');dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag-over');addF(e.dataTransfer.files)};fi.onchange=()=>addF(fi.files)}
}
function closeModal(){document.getElementById('modal').classList.add('hidden');_files=[]}
async function submit(){
  const st=document.getElementById('modal-status'),btn=document.getElementById('modal-submit');btn.disabled=true;st.classList.remove('hidden');
  let cid=_mCid;
  if(!cid){const nm=(document.getElementById('f-n')||{}).value?.trim();if(!nm){st.textContent='Name is required';btn.disabled=false;return}
    st.textContent='Creating...';const tg=(document.getElementById('f-t')||{}).value?.split(',').map(t=>t.trim()).filter(Boolean)||[];const ac=document.querySelector('input[name="f-ac"]:checked')?.value||'public';
    try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm,description:(document.getElementById('f-d')||{}).value||'',author_name:(document.getElementById('f-a')||{}).value||'',tags:tg,access_level:ac})});const corpus=await r.json();cid=corpus.id}catch(e){st.textContent='Failed';btn.disabled=false;return}}
  if(_files.length){st.textContent=`Uploading ${_files.length} files...`;const fd=new FormData();for(const f of _files)fd.append('files',f);try{await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd})}catch(e){}}
  const url=(document.getElementById('f-u')||{}).value?.trim();if(url){st.textContent='Fetching URL...';try{await fetch(`${API}/corpora/${cid}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})})}catch(e){}}
  if(document.getElementById('f-i')?.checked){st.textContent='Indexing...';try{await fetch(`${API}/corpora/${cid}/index`,{method:'POST'})}catch(e){}}
  st.textContent='Done!';btn.disabled=false;setTimeout(()=>{closeModal();location.hash='#/corpus/'+cid},400)}
function addF(fl){for(const f of fl)_files.push(f);const el=document.getElementById('dz-l');if(el)el.innerHTML=_files.map(f=>`<div>${esc(f.name)} (${(f.size/1024).toFixed(1)}KB)</div>`).join('')}

/* ── Theme ── */
function toggleTheme(){if(isDark()){document.documentElement.classList.add('light');document.documentElement.classList.remove('dark');localStorage.setItem('noosphere-theme','light')}else{document.documentElement.classList.add('dark');document.documentElement.classList.remove('light');localStorage.setItem('noosphere-theme','dark')}}

/* ── Init ── */
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('dark-toggle')?.addEventListener('click',toggleTheme);
  document.getElementById('sb-toggle')?.addEventListener('click',()=>{document.getElementById('sidebar').classList.toggle('collapsed')});
  document.getElementById('modal-close')?.addEventListener('click',closeModal);
  document.getElementById('modal-cancel')?.addEventListener('click',closeModal);
  document.getElementById('modal-submit')?.addEventListener('click',submit);
  document.getElementById('modal')?.addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
  window.addEventListener('hashchange',route);route()});
