/* Noosphere v6 — Terminal + My Corpora + Network + Chat */
const API='/api/v1';
let _gAnim=null,_lpAnim=null,_termAnim=null,_files=[],_corpora=[],_chatH=[];
const isDark=()=>document.documentElement.classList.contains('dark')||(!document.documentElement.classList.contains('light')&&window.matchMedia('(prefers-color-scheme: dark)').matches);
const PAL=['#e76f51','#2a9d8f','#264653','#e9c46a','#f4a261','#588157','#457b9d','#9b2226','#6d6875','#b56576','#355070','#6c757d','#e07a5f','#3d405b','#81b29a'];
const cC=n=>{let h=0;for(let i=0;i<n.length;i++)h=((h<<5)-h+n.charCodeAt(i))|0;return PAL[Math.abs(h)%PAL.length]};
const hR=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const cp=(t,b)=>{navigator.clipboard.writeText(t).then(()=>{if(b){const o=b.textContent;b.textContent='Copied!';setTimeout(()=>b.textContent=o,1200)}})};

async function route(){const h=location.hash||'#/';stopAll();
  if(h==='#/'||h===''||h==='#/landing'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLP();return}
  document.getElementById('page-landing').classList.add('hidden');document.getElementById('page-main').classList.remove('hidden');
  await loadC();setSBActive(h);
  if(h==='#/main')renderHome();
  else if(h==='#/write')renderWrite();
  else if(h==='#/upload')renderUpload();
  else if(h==='#/corpora')renderMyCorpora();
  else if(h==='#/network')renderNet();
  else if(h.startsWith('#/corpus/'))await renderCorpus(h.split('/')[2]);
  else renderHome();
}
function stopAll(){if(_lpAnim){cancelAnimationFrame(_lpAnim);_lpAnim=null}if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}if(_termAnim){cancelAnimationFrame(_termAnim);_termAnim=null}}
async function loadC(){try{const r=await fetch(`${API}/corpora`);_corpora=await r.json()}catch(e){_corpora=[]}}
function setSBActive(h){document.getElementById('nav-corpora').classList.toggle('active',h==='#/corpora');document.getElementById('nav-net').classList.toggle('active',h==='#/network')}
function hideRP(){document.getElementById('rpanel').classList.add('hidden')}

/* ══════ LANDING ══════ */
const DM=[{n:"Lenny's Newsletter",d:'product, growth',c:'#e76f51'},{n:'Paul Graham',d:'startups, philosophy',c:'#2a9d8f'},{n:'AI Research',d:'AI, ML',c:'#264653'},{n:'Feynman Lectures',d:'physics, science',c:'#f4a261'},{n:'Stoic Philosophy',d:'philosophy, ethics',c:'#588157'},{n:'YC Startup School',d:'startups, growth',c:'#457b9d'},{n:'Design Patterns',d:'software, design',c:'#e9c46a'},{n:'World History',d:'history, culture',c:'#b56576'}];
function renderLP(){const el=document.getElementById('page-landing');el.innerHTML=`<div class="lp"><nav class="lp-top"><span class="lp-brand"><svg width="17" height="17" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere</span><button class="lp-cta" id="lp-cta">Get Started</button></nav><div class="lp-cv" id="lp-cv"></div><div class="lp-ct"><div class="lp-h"><h1 class="lp-h1">Publish your knowledge for agents.</h1><p class="lp-sub">Turn any knowledge base into an agent-readable corpus. AI agents discover, query, and cite your knowledge via MCP and API.</p><button class="lp-go" id="lp-go">Get Started →</button></div><div class="lp-demo"><div class="lp-dt">Semantic Search with Citations</div><div class="lp-dq"><input value="How should startups think about pricing?" readonly /><button>Search</button></div><div class="lp-r"><div class="lp-sc">Score: 0.87</div><div class="lp-rt">"The biggest mistake I see in pricing is undercharging..."</div><div class="lp-ci">Pricing your AI product — Jul 2025</div></div><div class="lp-r"><div class="lp-sc">Score: 0.82</div><div class="lp-rt">"Value-based pricing means charging based on the outcome..."</div><div class="lp-ci">The pricing playbook — Mar 2024</div></div></div></div></div>`;
  document.getElementById('lp-cta').onclick=document.getElementById('lp-go').onclick=()=>{location.hash='#/main'};drawLPGraph()}
function drawLPGraph(){const co=document.getElementById('lp-cv');if(!co)return;const tk=m=>(m.d||'').split(/[,;]+/).map(d=>d.trim().toLowerCase()).filter(Boolean);const ns=DM.map((m,i)=>({id:'l'+i,name:m.n,dom:m.d,color:m.c,ini:m.n.split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk:tk(m)}));const lk=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=ns[i].tk.filter(t=>ns[j].tk.some(u=>t===u||t.includes(u)||u.includes(t)));if(s.length)lk.push({source:ns[i].id,target:ns[j].id,s:s.length})}const dp=devicePixelRatio||1,W=co.clientWidth||800,H=co.clientHeight||600,BR=Math.max(14,Math.min(22,W/(ns.length*2.5)));const cv=document.createElement('canvas');cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';co.appendChild(cv);const cx=cv.getContext('2d');cx.scale(dp,dp);const pts=[];lk.forEach(l=>{for(let i=0;i<Math.max(1,Math.round(l.s*1.5));i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.2,op:.3+Math.random()*.5})});const gX=W*.55,zn=[{cx:W*.1+170,cy:H/2,hw:200,hh:120}];function av(){let n;function f(){for(const nd of n)for(const z of zn){const dx=nd.x-z.cx,dy=nd.y-z.cy,ox=z.hw-Math.abs(dx),oy=z.hh-Math.abs(dy);if(ox>0&&oy>0){if(ox<oy){nd.vx+=(dx>=0?1:-1)*ox*.08;nd.vx*=.85}else{nd.vy+=(dy>=0?1:-1)*oy*.08;nd.vy*=.85}}}}f.initialize=x=>{n=x};return f}const sim=d3.forceSimulation(ns).force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(55,220-d.s*50)).strength(d=>.08+d.s*.15)).force('charge',d3.forceManyBody().strength(-400).distanceMax(550)).force('center',d3.forceCenter(gX,H/2).strength(.02)).force('collision',d3.forceCollide().radius(BR+12)).force('avoid',av()).alphaDecay(.03).velocityDecay(.35);let hov=null,mp=null;cv.onmousemove=e=>{const r=cv.getBoundingClientRect();mp=[e.clientX-r.left,e.clientY-r.top];hov=null;for(const n of ns)if(Math.hypot(n.x-mp[0],n.y-mp[1])<BR+4){hov=n;break}cv.style.cursor=hov?'pointer':'default'};cv.onmouseleave=()=>{hov=null;mp=null};function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);for(const l of lk){const s=l.source,t=l.target;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=`rgba(160,170,190,${.1+l.s*.07})`;cx.lineWidth=.5+l.s*.3;cx.stroke()}for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=`rgba(130,150,200,${p.op*.35})`;cx.fill()}for(const n of ns){const h=hov===n;let r=BR;if(mp){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<180?BR*(1+(1-d/180)*.45):BR*.8}if(h)r=Math.max(r,BR*1.35);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*1.8);g.addColorStop(0,`rgba(${cr},${cg},${cb},${h?.1:.04})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*1.8,0,Math.PI*2);cx.fillStyle=g;cx.fill();if(h){cx.beginPath();cx.arc(n.x,n.y,rr+2,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},.4)`;cx.lineWidth=1.5;cx.stroke()}cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);cx.fillStyle=n.color;cx.fill();cx.strokeStyle='rgba(255,255,255,.2)';cx.lineWidth=1;cx.stroke();cx.fillStyle='rgba(255,255,255,.92)';cx.font=`700 ${rr*.5}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.9:.65})`:`rgba(30,35,50,${h?.85:.55})`;cx.font=`600 ${h?10:9}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+10)}cx.restore();_lpAnim=requestAnimationFrame(draw)}sim.on('tick',()=>{});_lpAnim=requestAnimationFrame(draw)}

/* ══════ HOME — Interactive Terminal ══════ */
const TERM_STATUS_C={READY:'#10b981',INDEXED:'#3b82f6',CREATED:'#f59e0b'};
const TERM_SUGGESTIONS=[
  {text:'https://example.com/my-article',label:'Import a URL'},
  {text:'/write',label:'Write a new source'},
  {text:'What is RAG and how does it work?',label:'Ask the Noosphere'},
  {text:'/status',label:'View my corpora'},
];
let _termCtx={};

function renderHome(){
  hideRP();const ct=document.getElementById('content');
  const hour=new Date().getHours();
  const greet=hour<12?'Morning':hour<18?'Afternoon':'Evening';
  ct.innerHTML=`<div class="term-full">
    <div class="term-greet">
      <div class="term-greet-left">
        <div class="term-greet-hi">${greet}</div>
        <div class="term-greet-sub">What knowledge will you add to the Noosphere?</div>
      </div>
      <svg class="term-pixel" width="40" height="40" viewBox="0 0 8 8" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">
        <rect x="2" y="0" width="4" height="1" fill="var(--acc)"/>
        <rect x="1" y="1" width="6" height="3" fill="var(--acc)" opacity=".7"/>
        <rect x="2" y="2" width="1" height="1" fill="white"/><rect x="5" y="2" width="1" height="1" fill="white"/>
        <rect x="1" y="4" width="6" height="2" fill="var(--acc)" opacity=".5"/>
        <rect x="3" y="4" width="2" height="1" fill="var(--acc)" opacity=".9"/>
        <rect x="1" y="6" width="2" height="1" fill="var(--acc)" opacity=".4"/>
        <rect x="5" y="6" width="2" height="1" fill="var(--acc)" opacity=".4"/>
      </svg>
    </div>
    <div class="term-body" id="term-body"></div>
    <div class="term-input-wrap"><span class="term-caret">&gt;</span><input type="text" class="term-input" id="term-input" placeholder="Paste a URL, ask a question, or type / for shortcuts" autofocus /><span class="term-cursor-input">\u2588</span></div>
    <div class="term-hints" id="term-hints"></div>
  </div>`;

  const body=document.getElementById('term-body');
  const input=document.getElementById('term-input');
  const hints=document.getElementById('term-hints');
  _termCtx={};

  renderSuggestions(hints);

  let _sending=false;
  async function sendInput(){
    if(_sending)return;
    const val=input.value.trim();if(!val)return;
    _sending=true;input.value='';input.disabled=true;
    hints.style.display='none';
    appendLine(body,{type:'prompt',text:val});
    appendLine(body,{type:'resp',text:'Processing...',id:'term-loading'});
    try{
      const r=await fetch(`${API}/terminal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:val,context:_termCtx})});
      const d=await r.json();
      document.getElementById('term-loading')?.remove();
      _termCtx=d.context||{};
      for(const line of(d.lines||[]))appendLine(body,line);
      if(d.context?.action==='open_write'){setTimeout(()=>{location.hash='#/write'},500)}
    }catch(err){
      document.getElementById('term-loading')?.remove();
      appendLine(body,{type:'resp',text:'Error: '+err.message});
    }
    input.disabled=false;input.focus();body.scrollTop=body.scrollHeight;
    _sending=false;
  }
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sendInput()}});
}

function appendLine(body,line,hints){
  const el=document.createElement('div');
  if(line.id)el.id=line.id;
  if(line.type==='prompt'){el.className='term-line term-prompt';el.innerHTML='<span class="term-caret">&gt;</span><span>'+esc(line.text)+'</span>'}
  else if(line.type==='resp'){el.className='term-line term-resp';el.textContent=line.text}
  else if(line.type==='hint'){el.className='term-line term-resp';el.style.opacity='.6';el.textContent=line.text}
  else if(line.type==='option'){el.className='term-line term-option';el.textContent=line.text;el.style.cursor='pointer';
    el.onclick=()=>{const input=document.getElementById('term-input');if(input&&line.value){input.value=line.value;input.focus();input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}))}}}
  else if(line.type==='card'){el.className='term-card';el.innerHTML=`<div style="display:flex;justify-content:space-between"><span class="term-card-lbl">${esc(line.label||'')}</span><span class="term-status" style="color:${TERM_STATUS_C[line.status]||'#6e6e73'}">${esc(line.status||'')}</span></div><div class="term-card-det">${esc(line.detail||'')}</div>${line.val?`<div class="term-card-val">${esc(line.val)}</div>`:''}`;
    if(line.corpus_id){el.style.cursor='pointer';el.onclick=()=>{location.hash='#/corpus/'+line.corpus_id}}}
  else if(line.type==='cite'){el.className='term-line';el.innerHTML=`<span class="chat-cite">${esc(line.text)}</span>`}
  else return;
  body.appendChild(el);body.scrollTop=body.scrollHeight;
}

function renderSuggestions(el){
  el.innerHTML=TERM_SUGGESTIONS.map(s=>`<div class="term-suggestion"><span class="term-caret">&gt;</span> <span class="term-sg-label">${esc(s.label)}</span></div>`).join('');
  el.querySelectorAll('.term-suggestion').forEach((s,i)=>{s.onclick=()=>{const input=document.getElementById('term-input');if(input){input.value=TERM_SUGGESTIONS[i].text;input.focus();setTimeout(()=>{const e=new KeyboardEvent('keydown',{key:'Enter',bubbles:true});input.dispatchEvent(e)},50)}}});
}

/* ══════ WRITE ══════ */
function renderWrite(){hideRP();const ct=document.getElementById('content');ct.innerHTML=`<div class="write-page"><div class="write-top"><input type="text" id="w-title" placeholder="Title..." /></div><div class="write-editor"><textarea id="w-body" placeholder="Start writing your knowledge here...\n\nYou can write in Markdown. This becomes a source that agents can search and cite."></textarea></div><div class="write-bar"><div style="display:flex;gap:8px;align-items:center"><label style="font-size:12px;color:var(--tx2)">Corpus:</label><select id="w-corpus" style="padding:4px 8px;border-radius:6px;border:1px solid var(--brd);background:var(--bg);color:var(--tx);font-size:12px"><option value="_new">+ Create new corpus</option>${_corpora.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div><div style="display:flex;gap:8px"><button class="btn-ghost" onclick="location.hash='#/main'">Cancel</button><button class="btn-primary" id="w-save">Save & Index</button></div></div></div>`;
  document.getElementById('w-save').onclick=async()=>{const title=document.getElementById('w-title').value.trim(),body=document.getElementById('w-body').value.trim();if(!title||!body)return;const btn=document.getElementById('w-save');btn.disabled=true;btn.textContent='Saving...';let cid=document.getElementById('w-corpus').value;if(cid==='_new'){try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:title,access_level:'public'})});cid=(await r.json()).id}catch(e){btn.disabled=false;btn.textContent='Save & Index';return}}const fd=new FormData();fd.append('files',new Blob([`---\ntitle: ${title}\n---\n\n${body}`],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');try{await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd})}catch(e){}btn.textContent='Indexing...';try{await fetch(`${API}/corpora/${cid}/index`,{method:'POST'})}catch(e){}location.hash='#/corpus/'+cid}}

/* ══════ UPLOAD ══════ */
function renderUpload(){hideRP();_files=[];const ct=document.getElementById('content');ct.innerHTML=`<div class="upload-page"><div class="term-title" style="text-align:left;font-size:20px;margin-bottom:4px">Upload Knowledge</div><div style="font-size:13px;color:var(--tx2);margin-bottom:16px">Upload files or import from a URL</div><label class="fl">Corpus</label><select id="u-co" class="fi" style="margin-bottom:8px"><option value="_new">+ Create new corpus</option>${_corpora.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><div id="u-nf"><label class="fl">Name *</label><input type="text" id="u-nm" class="fi" placeholder="e.g. My Blog" /><label class="fl">Tags</label><input type="text" id="u-tg" class="fi" placeholder="AI, startups (comma-separated)" /></div><label class="fl">Files (.md, .txt)</label><div class="dz" id="u-dz"><input type="file" id="u-fi" multiple accept=".md,.txt,.text,.html" hidden /><div class="dz-tx">Drop files here or <span class="dz-br">browse</span></div><div class="dz-ls" id="u-dl"></div></div><label class="fl">Or paste a URL</label><input type="text" id="u-url" class="fi" placeholder="https://example.com/article" /><label class="fck"><input type="checkbox" id="u-idx" checked /> Auto-index after upload</label><div class="reg-p"><strong>🌐 Join the Noosphere?</strong> Register so agents worldwide can discover your knowledge.<br/><label class="fck"><input type="checkbox" id="u-reg" checked /> Register to the Noosphere</label></div><div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px"><button class="btn-ghost" onclick="location.hash='#/main'">Cancel</button><button class="btn-primary" id="u-sub">Publish</button></div><div class="hidden" id="u-st" style="font-size:12px;color:var(--acc);margin-top:8px"></div></div>`;
  document.getElementById('u-co').onchange=()=>{document.getElementById('u-nf').style.display=document.getElementById('u-co').value==='_new'?'':'none'};
  const dz=document.getElementById('u-dz'),fi=document.getElementById('u-fi');dz.onclick=()=>fi.click();dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag-over')};dz.ondragleave=()=>dz.classList.remove('drag-over');dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag-over');addF(e.dataTransfer.files)};fi.onchange=()=>addF(fi.files);
  document.getElementById('u-sub').onclick=async()=>{const st=document.getElementById('u-st'),btn=document.getElementById('u-sub');btn.disabled=true;st.classList.remove('hidden');let cid=document.getElementById('u-co').value;
    if(cid==='_new'){const nm=document.getElementById('u-nm').value.trim();if(!nm){st.textContent='Name required';btn.disabled=false;return}st.textContent='Creating...';const tg=document.getElementById('u-tg').value.split(',').map(t=>t.trim()).filter(Boolean);try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm,tags:tg,access_level:'public'})});cid=(await r.json()).id}catch(e){st.textContent='Failed';btn.disabled=false;return}}
    if(_files.length){st.textContent=`Uploading ${_files.length} files...`;const fd=new FormData();for(const f of _files)fd.append('files',f);try{await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd})}catch(e){}}
    const url=document.getElementById('u-url').value.trim();if(url){st.textContent='Fetching URL...';try{await fetch(`${API}/corpora/${cid}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})})}catch(e){}}
    if(document.getElementById('u-idx').checked){st.textContent='Indexing...';try{await fetch(`${API}/corpora/${cid}/index`,{method:'POST'})}catch(e){}}
    st.textContent='Done!';btn.disabled=false;setTimeout(()=>{location.hash='#/corpus/'+cid},400)}}
function addF(fl){for(const f of fl)_files.push(f);const el=document.getElementById('u-dl');if(el)el.innerHTML=_files.map(f=>`<div>${esc(f.name)} (${(f.size/1024).toFixed(1)}KB)</div>`).join('')}

/* ══════ MY CORPORA ══════ */
let _mcView='list';
function renderMyCorpora(){
  hideRP();const ct=document.getElementById('content'),host=location.origin;
  ct.innerHTML=`<div style="display:flex;flex-direction:column;height:100%"><div class="mc-header"><div class="mc-title">My Corpora</div><div class="mc-toggle"><button class="${_mcView==='list'?'active':''}" id="mc-list-btn">List</button><button class="${_mcView==='graph'?'active':''}" id="mc-graph-btn">Network</button></div></div><div id="mc-content" style="flex:1;overflow:hidden"></div></div>`;
  document.getElementById('mc-list-btn').onclick=()=>{_mcView='list';renderMyCorpora()};
  document.getElementById('mc-graph-btn').onclick=()=>{_mcView='graph';renderMyCorpora()};
  if(_mcView==='list')renderMCList(host);else renderMCGraph();
}

function renderMCList(host){
  const el=document.getElementById('mc-content');
  if(!_corpora.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet. Click <strong>+ New</strong> in the sidebar to add your knowledge.</div>';return}
  el.className='mc-list';
  el.innerHTML=_corpora.map(c=>{const al=c.access_level||'public';const tg=Array.isArray(c.tags)?c.tags:[];
    return`<div class="mc-card" data-id="${c.id}"><div class="mc-card-top"><div class="mc-card-name">${esc(c.name)}</div><span class="mc-card-badge ${al}">${al}</span></div>${c.description?`<div class="mc-card-desc">${esc(c.description)}</div>`:''}
    <div class="mc-card-ep"><span class="mc-card-epl">MCP</span><span class="mc-card-epu">${host}/mcp</span><button class="mc-card-cp" onclick="event.stopPropagation();cp('${host}/mcp',this)">Copy</button></div>
    <div class="mc-card-ep"><span class="mc-card-epl">API</span><span class="mc-card-epu">${host}/api/v1/corpora/${c.id}/search</span><button class="mc-card-cp" onclick="event.stopPropagation();cp('${host}/api/v1/corpora/${c.id}/search',this)">Copy</button></div>
    <div class="mc-card-stats"><span>${c.document_count} sources</span><span>${c.chunk_count} chunks</span><span>${(c.word_count||0).toLocaleString()} words</span><span class="hl">${c.status}</span></div></div>`}).join('');
  el.querySelectorAll('.mc-card').forEach(card=>{card.addEventListener('click',()=>{location.hash='#/corpus/'+card.dataset.id})});
}

function renderMCGraph(){
  const el=document.getElementById('mc-content');el.innerHTML='';el.className='mc-graph';
  if(!_corpora.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet.</div>';return}
  drawGraphIn(el,_corpora);
}

/* ══════ NETWORK ══════ */
function renderNet(){
  hideRP();const ct=document.getElementById('content');
  ct.innerHTML=`<div class="nv-wrap"><canvas id="nv-cv" class="nv-canvas"></canvas><div class="nv-tt hidden" id="nv-tt"></div><div class="nv-bottom"><div class="composer"><textarea class="composer-input" id="nv-ci" placeholder="Ask the Noosphere..." rows="1"></textarea><div class="composer-toolbar"><button class="composer-send" id="nv-send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></div></div><div id="nv-resp" style="margin-top:10px"></div></div></div>`;
  const ci=document.getElementById('nv-ci'),send=document.getElementById('nv-send'),resp=document.getElementById('nv-resp');
  ci.addEventListener('input',()=>{ci.style.height='auto';ci.style.height=Math.min(ci.scrollHeight,120)+'px'});
  async function ask(){const q=ci.value.trim();if(!q)return;ci.value='';ci.style.height='auto';send.disabled=true;resp.innerHTML='<div style="font-size:13px;color:var(--tx3)">Thinking...</div>';
    try{const r=await fetch(`${API}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:q})});const d=await r.json();
      resp.innerHTML=`<div style="font-size:14px;line-height:1.7;margin-bottom:8px">${esc(d.response)}</div>${d.citations&&d.citations.length?`<div class="chat-cites">${d.citations.map(c=>`<span class="chat-cite">${esc(c.corpus_name||c.title||'')}</span>`).join('')}</div>`:''}`}
    catch(e){resp.innerHTML='<div style="font-size:13px;color:var(--tx3)">Failed. Check LLM API keys in .env</div>'}send.disabled=false}
  send.onclick=ask;ci.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}};

  const cv=document.getElementById('nv-cv');if(!cv)return;
  if(!_corpora.length){const w=cv.parentElement;const e=document.createElement('div');e.className='empty';e.style.cssText='position:absolute;top:40%;left:50%;transform:translate(-50%,-50%)';e.innerHTML='The Noosphere is empty.<br>Click <strong>+ New</strong> to add knowledge.';w.appendChild(e);return}
  drawGraphIn(cv.parentElement,_corpora,cv);
}

/* ══════ SHARED GRAPH DRAWING ══════ */
function drawGraphIn(container,corpora,existingCanvas){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const ns=corpora.map(c=>{const tg=Array.isArray(c.tags)?c.tags:[];const tk=[];tg.forEach(t=>tk.push(...t.toLowerCase().split(/[\s,]+/).filter(Boolean)));return{...c,color:cC(c.name),ini:(c.name||'?').split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk}});
  const lk=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=new Set(ns[i].tk);const sh=[...new Set(ns[j].tk)].filter(t=>s.has(t));if(sh.length)lk.push({source:ns[i].id,target:ns[j].id,s:sh.length})}

  const bottomEl=container.querySelector('.nv-bottom');
  const W=container.clientWidth,H=container.clientHeight-(bottomEl?bottomEl.offsetHeight:0);
  const dp=devicePixelRatio||1;
  let cv=existingCanvas;
  if(!cv){cv=document.createElement('canvas');cv.style.cursor='grab';container.appendChild(cv)}
  cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';
  const cx=cv.getContext('2d');cx.scale(dp,dp);
  const BR=Math.max(20,Math.min(32,W/(ns.length*2.5)));
  const pts=[];lk.forEach(l=>{for(let i=0;i<Math.max(1,Math.round(l.s*1.5));i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.5,op:.3+Math.random()*.5})});
  const sim=d3.forceSimulation(ns).force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(70,220-d.s*50)).strength(d=>.1+d.s*.12)).force('charge',d3.forceManyBody().strength(-500).distanceMax(600)).force('center',d3.forceCenter(W/2,H/2).strength(.04)).force('collision',d3.forceCollide().radius(BR+16)).alphaDecay(.03).velocityDecay(.35);

  let drag=null,hov=null,mp=null;const tt=container.querySelector('.nv-tt')||document.getElementById('nv-tt');
  function getN(x,y){for(const n of ns)if(Math.hypot(n.x-x,n.y-y)<BR+6)return n;return null}
  cv.onmousedown=e=>{const r=cv.getBoundingClientRect();drag=getN(e.clientX-r.left,e.clientY-r.top);if(drag){drag.fx=drag.x;drag.fy=drag.y;sim.alphaTarget(.3).restart()}};
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect();const x=e.clientX-r.left,y=e.clientY-r.top;mp=[x,y];if(drag){drag.fx=x;drag.fy=y;cv.style.cursor='grabbing';return}hov=getN(x,y);cv.style.cursor=hov?'pointer':'grab';if(hov&&tt){tt.innerHTML=`<div class="tt-n">${esc(hov.name)}</div><div class="tt-m">${hov.document_count} sources · ${hov.access_level} · Click to chat</div>`;tt.classList.remove('hidden');tt.style.left=(x+12)+'px';tt.style.top=(y-8)+'px'}else if(tt){tt.classList.add('hidden')}};
  cv.onmouseup=()=>{if(drag){drag.fx=null;drag.fy=null;sim.alphaTarget(0);drag=null}};
  cv.onclick=()=>{if(!drag&&hov)location.hash='#/corpus/'+hov.id};
  cv.onmouseleave=()=>{hov=null;mp=null;if(tt)tt.classList.add('hidden');if(drag){drag.fx=null;drag.fy=null;sim.alphaTarget(0);drag=null}};

  function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);
    for(const l of lk){const s=l.source,t=l.target;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=`rgba(160,170,190,${.1+l.s*.07})`;cx.lineWidth=.6+l.s*.4;cx.stroke()}
    for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=`rgba(130,150,200,${p.op*.4})`;cx.fill()}
    for(const n of ns){const h=hov===n||drag===n;let r=BR;if(mp&&!drag){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<200?BR*(1+(1-d/200)*.5):BR*.85}if(h)r=Math.max(r,BR*1.4);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);
      const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*2);g.addColorStop(0,`rgba(${cr},${cg},${cb},${h?.12:.05})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*2,0,Math.PI*2);cx.fillStyle=g;cx.fill();
      if(h){cx.beginPath();cx.arc(n.x,n.y,rr+3,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},.5)`;cx.lineWidth=2;cx.stroke()}
      cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);cx.fillStyle=n.color;cx.fill();cx.strokeStyle='rgba(255,255,255,.25)';cx.lineWidth=1.5;cx.stroke();
      cx.fillStyle='rgba(255,255,255,.95)';cx.font=`700 ${rr*.55}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);
      const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.95:.7})`:`rgba(30,35,50,${h?.9:.6})`;cx.font=`600 ${h?12:11}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+14);
      cx.fillStyle=dk?'rgba(200,200,210,.4)':'rgba(100,110,130,.4)';cx.font='400 9px Inter,sans-serif';cx.fillText(n.document_count+' sources',n.x,n.y+rr+26)}
    cx.restore();_gAnim=requestAnimationFrame(draw)}
  sim.on('tick',()=>{});_gAnim=requestAnimationFrame(draw);
}

/* ══════ CORPUS DETAIL + CHAT ══════ */
async function renderCorpus(id){
  stopAll();_chatH=[];const ct=document.getElementById('content');ct.innerHTML='<div class="empty">Loading...</div>';
  let c;try{const r=await fetch(`${API}/corpora/${id}`);c=await r.json()}catch(e){ct.innerHTML='<div class="empty">Not found</div>';hideRP();return}
  let docs=[];try{const r=await fetch(`${API}/corpora/${id}/documents`);docs=await r.json()}catch(e){}
  let an={};try{const r=await fetch(`${API}/corpora/${id}/analytics?limit=5`);an=await r.json()}catch(e){}
  ct.innerHTML=`<div class="cv-sec"><div class="cv-st">Sources (${docs.length}) <button class="btn-add" id="cv-add">+ Add</button></div><div id="cv-docs">${docs.length===0?'<div class="empty">No sources yet</div>':docs.map((d,i)=>`<div class="src-item${i===0?' expanded':''}" data-id="${d.id}"><div class="src-hd"><span class="src-tt">${esc(d.title)}</span><span class="src-mt">${d.word_count||0}w${d.date?' · '+d.date:''}</span><span class="src-ar">▸</span></div>${i===0?'<div class="src-bd" id="sb0">Loading...</div>':''}</div>`).join('')}</div></div><div class="chat-area" id="chat-area"></div><div class="chat-bottom"><div class="composer"><textarea class="composer-input" id="c-ci" placeholder="Chat with ${esc(c.name)}..." rows="1"></textarea><div class="composer-toolbar"><button class="composer-send" id="c-send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></div></div></div>`;
  showRP(c,an);
  if(docs.length>0){try{const r=await fetch(`${API}/corpora/${id}/documents/${docs[0].id}`);const d=await r.json();const b=document.getElementById('sb0');if(b)b.textContent=d.content||''}catch(e){}}
  document.getElementById('cv-add').onclick=()=>{location.hash='#/upload'};
  ct.querySelectorAll('.src-item').forEach(item=>{item.addEventListener('click',async()=>{if(item.classList.contains('expanded')){const b=item.querySelector('.src-bd');if(b)b.remove();item.classList.remove('expanded');return}item.classList.add('expanded');try{const r=await fetch(`${API}/corpora/${id}/documents/${item.dataset.id}`);const d=await r.json();const b=document.createElement('div');b.className='src-bd';b.textContent=d.content||'';item.appendChild(b)}catch(e){}})});
  const ci=document.getElementById('c-ci'),send=document.getElementById('c-send'),area=document.getElementById('chat-area');
  ci.addEventListener('input',()=>{ci.style.height='auto';ci.style.height=Math.min(ci.scrollHeight,120)+'px'});
  async function chat(){const msg=ci.value.trim();if(!msg)return;ci.value='';ci.style.height='auto';area.innerHTML+=`<div class="chat-msg user">${esc(msg)}</div>`;area.scrollTop=area.scrollHeight;send.disabled=true;area.innerHTML+=`<div class="chat-msg assistant" id="c-ld" style="color:var(--tx3)">Thinking...</div>`;area.scrollTop=area.scrollHeight;_chatH.push({role:'user',content:msg});
    try{const r=await fetch(`${API}/corpora/${id}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,history:_chatH,top_k:5})});const d=await r.json();document.getElementById('c-ld')?.remove();_chatH.push({role:'assistant',content:d.response});area.innerHTML+=`<div class="chat-msg assistant">${esc(d.response)}${d.citations&&d.citations.length?`<div class="chat-cites">${d.citations.map(c=>`<span class="chat-cite">${esc(c.title||'')}</span>`).join('')}</div>`:''}</div>`}
    catch(e){document.getElementById('c-ld')?.remove();area.innerHTML+=`<div class="chat-msg assistant" style="color:var(--tx3)">Failed. Check LLM API keys.</div>`}send.disabled=false;area.scrollTop=area.scrollHeight}
  send.onclick=chat;ci.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chat()}};
}

const ACC_MSG={public:'Discoverable by all agents worldwide.',private:'Only accessible via your personal endpoint.',token:'Requires access keys. (Coming soon)',paid:'Agents pay per query. (Coming soon)'};
function showRP(c,an){const rp=document.getElementById('rpanel');rp.classList.remove('hidden');const host=location.origin;const tg=Array.isArray(c.tags)?c.tags:[];const al=c.access_level||'public';
  rp.innerHTML=`<div class="rp-name">${esc(c.name)}</div>${c.author_name?`<div class="rp-author">by ${esc(c.author_name)}</div>`:''}${c.description?`<div class="rp-desc">${esc(c.description)}</div>`:''}${tg.length?`<div class="rp-tags">${tg.map(t=>`<span class="rp-tag">${esc(t)}</span>`).join('')}</div>`:''}
    <div class="rp-sec"><div class="rp-lbl">Connect Agents</div><div class="rp-ep"><span class="rp-epl">MCP</span><span class="rp-epu">${host}/mcp</span><button class="rp-cp" onclick="cp('${host}/mcp',this)">Copy</button></div><div class="rp-ep"><span class="rp-epl">API</span><span class="rp-epu">${host}/api/v1/corpora/${c.id}/search</span><button class="rp-cp" onclick="cp('${host}/api/v1/corpora/${c.id}/search',this)">Copy</button></div></div>
    <div class="rp-sec"><div class="rp-lbl">Stats</div><div class="rp-stats"><div><div class="rp-sv">${c.document_count}</div><div class="rp-sl">sources</div></div><div><div class="rp-sv">${c.chunk_count}</div><div class="rp-sl">chunks</div></div><div><div class="rp-sv">${(c.word_count||0).toLocaleString()}</div><div class="rp-sl">words</div></div><div><div class="rp-sv">${an.total_queries||0}</div><div class="rp-sl">queries</div></div></div></div>
    <div class="rp-sec"><div class="rp-lbl">Access</div><div class="rp-row"><select id="rp-acc"><option value="public" ${al==='public'?'selected':''}>Public</option><option value="private" ${al==='private'?'selected':''}>Private</option><option value="token" ${al==='token'?'selected':''}>Token-gated</option><option value="paid" ${al==='paid'?'selected':''}>Paid</option></select><button class="btn-sm" id="rp-sv">Save</button></div><div class="rp-msg info" id="rp-msg">${ACC_MSG[al]||''}</div></div>
    <div class="rp-sec"><button class="btn-primary" id="rp-idx" style="width:100%;margin-bottom:6px">Re-index</button>${c.embedding_model?`<div style="font-size:10px;color:var(--tx3)">Model: ${c.embedding_model}</div>`:''}<div style="font-size:10px;color:var(--tx3)">Status: ${c.status}</div></div>`;
  document.getElementById('rp-acc').onchange=()=>{document.getElementById('rp-msg').textContent=ACC_MSG[document.getElementById('rp-acc').value]||''};
  document.getElementById('rp-sv').onclick=async()=>{await fetch(`${API}/corpora/${c.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:document.getElementById('rp-acc').value})});await loadC();renderCorpus(c.id)};
  document.getElementById('rp-idx').onclick=async()=>{document.getElementById('rp-idx').textContent='Indexing...';document.getElementById('rp-idx').disabled=true;try{await fetch(`${API}/corpora/${c.id}/index`,{method:'POST'})}catch(e){}renderCorpus(c.id)};
}

function toggleTheme(){if(isDark()){document.documentElement.classList.add('light');document.documentElement.classList.remove('dark');localStorage.setItem('noosphere-theme','light')}else{document.documentElement.classList.add('dark');document.documentElement.classList.remove('light');localStorage.setItem('noosphere-theme','dark')}}

document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('dark-btn')?.addEventListener('click',toggleTheme);
  document.getElementById('sb-toggle')?.addEventListener('click',()=>document.getElementById('sidebar').classList.toggle('collapsed'));
  document.getElementById('sb-new')?.addEventListener('click',()=>{location.hash='#/main'});
  window.addEventListener('hashchange',route);route()});
