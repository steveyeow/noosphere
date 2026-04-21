/* Noosphere v9 — Terminal + Corpora + Network + Chat + Cloud Auth */
const API='/api/v1';
let _gAnim=null,_lpAnim=null,_termAnim=null,_files=[],_corpora=[],_chatH=[],_ownerName='',_firstName='';
let _cloudMode=false,_supabase=null,_authUser=null,_authSession=null;
// Home composer's corpus scope — hoisted to module scope so downstream
// helpers (placeholder refresh, compile routing) can see what the user has
// selected in the chip. null = "Any" (across all corpora); otherwise a corpus id.
let _homeScope=null;
// Composer mode: 'create' | 'enrich' | 'compile'. Default 'enrich' because
// most sessions add to an existing KB; 'create' kicks in for users without
// any corpora; 'compile' swaps Send behavior to synthesize a wiki/entity.
let _composerMode='enrich';
const COMPOSER_MODES=[
  {id:'create',name:'Create',desc:'Start a new knowledge base from this chat'},
  {id:'enrich',name:'Enrich',desc:'Grow an existing knowledge base through conversation'},
  {id:'compile',name:'Compile',desc:'Synthesize a wiki or entity page from your sources'},
];
const isDark=()=>document.documentElement.classList.contains('dark')||(!document.documentElement.classList.contains('light')&&window.matchMedia('(prefers-color-scheme: dark)').matches);
const PAL=['#e76f51','#2a9d8f','#264653','#e9c46a','#f4a261','#588157','#457b9d','#9b2226','#6d6875','#b56576','#355070','#6c757d','#e07a5f','#3d405b','#81b29a'];
const cC=n=>{let h=0;for(let i=0;i<n.length;i++)h=((h<<5)-h+n.charCodeAt(i))|0;return PAL[Math.abs(h)%PAL.length]};
const hR=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const fmtN=n=>{if(n>=1e6)return(n/1e6).toFixed(1).replace(/\.0$/,'')+'M';if(n>=1e4)return(n/1e3).toFixed(1).replace(/\.0$/,'')+'K';return n.toLocaleString()};
const cp=(t,b)=>{navigator.clipboard.writeText(t).then(()=>{if(b){const o=b.textContent;b.textContent='Copied!';setTimeout(()=>b.textContent=o,1200)}})};
function toast(msg,type='error',action){
  const t=document.createElement('div');t.className='toast toast-'+type;
  if(action){
    t.innerHTML='<span class="toast-msg"></span><button class="toast-act" type="button"></button>';
    t.querySelector('.toast-msg').textContent=msg;
    const b=t.querySelector('.toast-act');b.textContent=action.label;
    b.onclick=()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300);action.onclick&&action.onclick()};
  }else{t.textContent=msg}
  document.body.appendChild(t);
  setTimeout(()=>t.classList.add('show'),10);
  // Linger longer when there's an action — user needs time to react
  const ttl=action?8000:4000;
  setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300)},ttl);
}

/* Handle a 429 quota_exceeded response. Returns true if handled (caller should
   bail without throwing). Pass the parsed JSON body — we don't re-read it.

   Uses showProModal for quota_exceeded (unified paywall with full Free/Pro
   comparison). Resource-limit codes (corpus/document/monthly) still toast
   because those hit elsewhere in the UX and a full modal would be overkill. */
function handleQuotaError(res,body){
  if(!res||res.status!==429)return false;
  const det=body&&body.detail;
  if(!det||typeof det!=='object')return false;
  const quotaCodes=['quota_exceeded','corpus_limit_reached','document_limit_reached','monthly_query_limit'];
  if(!quotaCodes.includes(det.code))return false;
  if(det.code==='quota_exceeded'){
    showProModal(det.message||'');
    return true;
  }
  toast(det.message||'Upgrade to Pro for higher limits.','error',
    {label:'Upgrade →',onclick:()=>{location.hash='#/pricing'}});
  return true;
}

/* Pre-intercept a Pro-only action for Free users, saving a round-trip.
   Returns true if the user is Free (modal opened, caller should bail).
   Self-hosted users (no auth) always pass through. */
function gateProFeature(reason){
  if(!_authUser)return false;
  const tier=_authUser.user_metadata?.tier||'free';
  if(tier==='pro')return false;
  showProModal(reason);
  return true;
}

/* Extract a readable error message from a parsed JSON body. Handles the case
   where FastAPI's `detail` is an object (e.g. 429 quota_exceeded) rather than
   a string — `new Error(object)` yields "[object Object]" which is broken UX. */
function errMsg(body,fallback){
  const d=body&&body.detail;
  if(typeof d==='string')return d;
  if(d&&typeof d==='object'&&typeof d.message==='string')return d.message;
  return fallback||'Error';
}

/* Debounced /index trigger. Every ingest action used to fire /index
   immediately; chained ingests (Save-to-corpus on 5 replies, uploading 5
   files via 5 Upload panels) produced 5 separate index runs. We coalesce
   per-corpus: the last call within the window wins, and the quota /
   processing cost is paid once instead of N times. Content-hash based
   incremental indexing makes this safe — no-op runs are already cheap,
   but collapsing them is cheaper still. */
const _indexTimers={};
const _indexInFlight={};
function ensureIndexed(corpusId,delayMs=1200){
  if(!corpusId)return;
  if(_indexTimers[corpusId])clearTimeout(_indexTimers[corpusId]);
  _indexTimers[corpusId]=setTimeout(async()=>{
    delete _indexTimers[corpusId];
    if(_indexInFlight[corpusId])return;   // already running; skip coalesced trigger
    _indexInFlight[corpusId]=true;
    try{
      await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'});
    }catch(e){/* non-blocking; corpus detail page exposes a Re-process button for recovery */}
    finally{delete _indexInFlight[corpusId]}
  },delayMs);
}

/* ── Cloud Auth (Supabase) ── */
async function initAuth(){
  try{
    // Cloud mode is detected via /me. Do not depend on /health here — if
    // that endpoint 500s, initAuth would throw on r.json() and leave
    // _cloudMode=false, hiding the sign-in UI entirely.
    const mr=await fetch(`${API}/me`);const md=await mr.json();
    _cloudMode=!!md.cloud;
    if(!_cloudMode)return;
    // Load Supabase config from meta tag or well-known
    const cfg=document.querySelector('meta[name="supabase-url"]');
    const supaUrl=cfg?.content||window.__SUPABASE_URL||'';
    const anonKey=document.querySelector('meta[name="supabase-anon-key"]')?.content||window.__SUPABASE_ANON_KEY||'';
    if(!supaUrl||!anonKey){
      // Try fetching config from server
      try{
        const cr=await fetch('/static/supabase-config.json');
        if(cr.ok){const cc=await cr.json();if(cc.url&&cc.anonKey){window.__SUPABASE_URL=cc.url;window.__SUPABASE_ANON_KEY=cc.anonKey;return initAuth()}}
      }catch(e){}
      _cloudMode=false;return;
    }
    if(typeof supabase!=='undefined'&&supabase.createClient){
      _supabase=supabase.createClient(supaUrl,anonKey);
      // Check if URL has OAuth callback tokens (access_token in hash)
      const fullHash=window.location.hash;
      if(fullHash.includes('access_token=')){
        // Let Supabase parse the tokens from the URL
        const{data,error}=await _supabase.auth.getSession();
        if(data.session){_authSession=data.session;_authUser=data.session.user}
        // Clean up the URL — remove token params, go to main
        history.replaceState(null,'',window.location.pathname+'#/main');
      }else{
        const{data}=await _supabase.auth.getSession();
        if(data.session){_authSession=data.session;_authUser=data.session.user}
      }
      _supabase.auth.onAuthStateChange((event,session)=>{
        _authSession=session;_authUser=session?.user||null;
        renderAuthUI();
        if(event==='SIGNED_IN'){
          // Clean URL if needed and navigate
          if(window.location.hash.includes('access_token=')){
            history.replaceState(null,'',window.location.pathname+'#/main');
          }
          route();
        }
      });
    }
  }catch(e){console.warn('Auth init:',e)}
}

function authHeaders(){
  const h={};
  if(_authSession?.access_token)h['Authorization']='Bearer '+_authSession.access_token;
  return h;
}

function apiFetch(url,opts={}){
  opts.headers={...(opts.headers||{}),...authHeaders()};
  return window._origFetch(url,opts);
}

// Monkey-patch fetch to auto-inject auth headers for API calls
window._origFetch=window.fetch;
window.fetch=function(url,opts={}){
  if(_authSession?.access_token&&typeof url==='string'&&(url.startsWith(API)||url.startsWith('/'))){
    opts=opts||{};opts.headers={...(opts.headers||{}),...authHeaders()};
  }
  return window._origFetch(url,opts);
};

async function signInWithGoogle(){
  if(!_supabase)return;
  await _supabase.auth.signInWithOAuth({provider:'google',options:{redirectTo:window.location.origin}});
}

async function signOut(){
  if(!_supabase)return;
  await _supabase.auth.signOut();
  _authUser=null;_authSession=null;
  renderAuthUI();route();
}

function renderAuthUI(){
  const bot=document.getElementById('sb-bot');
  if(!bot)return;
  /* Non-cloud: dark mode toggle only */
  if(!_cloudMode){
    bot.innerHTML=`<button class="sb-btn" id="dark-btn" title="Toggle dark mode"><svg class="icon-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg><svg class="icon-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>`;
    bot.querySelector('#dark-btn').addEventListener('click',toggleTheme);
    return;
  }
  if(_authUser){
    const email=_authUser.email||'';
    const name=email.split('@')[0]||'User';
    const avatar=_authUser.user_metadata?.avatar_url;
    const tier=_authUser.user_metadata?.tier||'free';
    const tierLabel=tier==='pro'?'Pro':'Free';
    bot.innerHTML=`<div class="sb-profile" id="sb-profile">${avatar?'<img src="'+esc(avatar)+'" class="sb-auth-avatar"/>':'<span class="sb-auth-initial">'+esc(name[0].toUpperCase())+'</span>'}<span class="sb-profile-info sb-lb"><span class="sb-auth-name">${esc(name)}</span><span class="sb-tier-badge sb-tier-${tier}">${tierLabel}</span></span><svg class="sb-profile-chev sb-lb" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></div><div class="sb-popover hidden" id="sb-popover"><a href="#/account" class="sb-pop-item"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg><span>Account</span></a><a href="#/pricing" class="sb-pop-item"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg><span>Pricing</span></a><button class="sb-pop-item" id="sb-pop-theme"><svg class="icon-sun" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg><svg class="icon-moon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg><span>Dark mode</span></button><div class="sb-pop-divider"></div><button class="sb-pop-item sb-pop-danger" id="sb-pop-signout"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg><span>Sign out</span></button></div>`;
    const profile=bot.querySelector('#sb-profile');
    const popover=bot.querySelector('#sb-popover');
    profile.addEventListener('click',e=>{e.stopPropagation();popover.classList.toggle('hidden')});
    bot.querySelector('#sb-pop-theme').addEventListener('click',e=>{e.stopPropagation();toggleTheme()});
    bot.querySelector('#sb-pop-signout').addEventListener('click',signOut);
    popover.querySelectorAll('a.sb-pop-item').forEach(a=>a.addEventListener('click',()=>popover.classList.add('hidden')));
    document.addEventListener('click',function _closePopover(e){if(!bot.contains(e.target)){popover.classList.add('hidden')}});
  }else{
    bot.innerHTML=`<button class="sb-btn sb-auth-login" style="width:100%;justify-content:center;gap:6px;padding:6px 10px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg><span class="sb-lb">Sign in</span></button>`;
    bot.querySelector('.sb-auth-login').onclick=signInWithGoogle;
  }
}
function pickCorpusInline(container){
  return new Promise(resolve=>{
    const wrap=document.createElement('div');wrap.className='term-pick-wrap';
    wrap.innerHTML='<div class="term-resp" style="padding-left:0;margin-bottom:4px">Which corpus?</div>'+
      _corpora.map(c=>'<div class="term-pick-opt" data-id="'+c.id+'"><span class="term-caret" style="font-size:12px;opacity:.4">&gt;</span> '+esc(c.name)+' <span style="color:var(--tx3);font-size:11px">('+c.document_count+')</span></div>').join('')+
      '<div class="term-pick-opt term-pick-new" data-id="_new"><span class="term-caret" style="font-size:12px;opacity:.4">+</span> Create new corpus</div>'+
      '<div class="term-pick-opt term-pick-cancel" data-id=""><span class="term-caret" style="font-size:12px;opacity:.4">&times;</span> Cancel</div>';
    container.appendChild(wrap);
    const sc=document.getElementById('term-scroll');if(sc)sc.scrollTop=sc.scrollHeight;
    wrap.querySelectorAll('.term-pick-opt').forEach(o=>{o.onclick=async()=>{
      let id=o.dataset.id;
      if(id==='_new'){
        wrap.innerHTML='<div class="term-resp" style="padding-left:0">Name for the new corpus:</div><div style="display:flex;gap:8px;align-items:center;margin-top:6px"><input type="text" class="term-input" id="tp-name" placeholder="Corpus name..." style="flex:1;font-size:13px" /><button class="btn-sm" id="tp-go">Create</button><button class="btn-sm-ghost" id="tp-cc">Cancel</button></div>';
        if(sc)sc.scrollTop=sc.scrollHeight;
        wrap.querySelector('#tp-name').focus();
        wrap.querySelector('#tp-cc').onclick=()=>{wrap.remove();resolve(null)};
        const goFn=async()=>{const nm=wrap.querySelector('#tp-name').value.trim();if(!nm){toast('Name is required');return}
          try{const r=await fetch(API+'/corpora',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm,access_level:'public'})});const c=await r.json();id=c.id;await loadC();wrap.remove();resolve(id)}catch(e){toast('Failed to create corpus');wrap.remove();resolve(null)}};
        wrap.querySelector('#tp-go').onclick=goFn;
        wrap.querySelector('#tp-name').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();goFn()}};
        return;
      }
      wrap.remove();resolve(id||null);
    }});
  });
}

async function route(){const h=location.hash||'#/';stopAll();
  if(h==='#/'||h===''||h==='#/landing'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLP();return}
  if(h==='#/login'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLogin();return}
  // Cloud mode: redirect to login if not authenticated and trying to access app
  if(_cloudMode&&!_authUser&&h!=='#/explore'&&!h.startsWith('#/explore')){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLogin();return}
  document.getElementById('page-landing').classList.add('hidden');document.getElementById('page-main').classList.remove('hidden');
  await Promise.all([loadC(),loadMe(),loadChatSessions()]);setSBActive(h);renderSBChats();
  if(h==='#/main')renderHome();
  else if(h==='#/corpora')renderMyCorpora();
  else if(h==='#/chats')renderChats();
  else if(h==='#/connectors')renderConnectors();
  else if(h==='#/pricing')renderPricing();
  else if(h==='#/account')renderAccount();
  else if(h==='#/network'||h.startsWith('#/explore'))renderNet();
  else if(h.startsWith('#/compile')){
    const qp=new URLSearchParams(h.split('?')[1]||'');
    await renderCompile(qp);
  }
  else if(h.startsWith('#/corpus/')){
    // #/corpus/{cid} or #/corpus/{cid}/entity/{eid}[?query]
    const afterPrefix=h.substring('#/corpus/'.length);
    const [pathPart,queryPart]=afterPrefix.split('?');
    const segs=pathPart.split('/');
    const corpusId=segs[0];
    if(segs[1]==='entity'&&segs[2]){
      await renderEntity(corpusId,segs[2]);
    }else{
      const params=new URLSearchParams(queryPart||'');
      const sessionId=params.get('session');
      await renderCorpus(corpusId,sessionId);
    }
  }
  else renderHome();
}
function stopAll(){if(_lpAnim){cancelAnimationFrame(_lpAnim);_lpAnim=null}if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}if(_termAnim){cancelAnimationFrame(_termAnim);_termAnim=null}}
async function loadC(){try{const r=await fetch(`${API}/corpora`);_corpora=await r.json()}catch(e){_corpora=[]}}
async function loadMe(){try{const r=await fetch(`${API}/me`);const d=await r.json();_ownerName=d.name||'';
  // Only extract a first name we're confident about: space-separated (e.g. "Steve Yao" → "Steve")
  // or CamelCase boundary (e.g. "SteveYao" → "Steve"). Concatenated usernames like "steveyao" stay
  // empty — better to show no name than the wrong one.
  if(_ownerName.includes(' '))_firstName=_ownerName.split(' ')[0];
  else{const m=_ownerName.match(/^[A-Z][a-z]+(?=[A-Z])/);_firstName=m?m[0]:''}
}catch(e){}}

/* ── Chat session persistence ── */
let _chatSessions=[];
async function loadChatSessions(){
  try{const r=await fetch(`${API}/chat-sessions?limit=20`);_chatSessions=await r.json()}catch(e){_chatSessions=[]}
  renderSBChats();
}
/* ── Noos icon (landing page logo SVG) ── */
const NOOS_ICON_SVG=`<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/><circle cx="18" cy="42" r="3" fill="currentColor" opacity="0.5"/><line x1="20" y1="24" x2="44" y2="20" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="20" y1="24" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="44" y1="20" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="18" y1="42" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/></svg>`;
const NOOS_DOT=`<span class="term-noos-dot">●</span>`;
function noosHd(){return `<div class="noos-hd"><span class="noos-av">${NOOS_ICON_SVG}</span><span class="noos-nm">Noos</span></div>`}

/* ── Command picker ── */
const TERM_CMDS=[
  {cmd:'/new',desc:'Create a new knowledge base'},
  {cmd:'/upload',desc:'Upload a file to a knowledge base'},
  {cmd:'/write',desc:'Write a note'},
  {cmd:'/history',desc:'Recent conversations'},
  {cmd:'/status',desc:'Your knowledge bases at a glance'},
  {cmd:'/help',desc:'Show all commands'},
];
function showCmdPicker(input,matches){
  let p=document.getElementById('term-cmd-picker');
  if(!p){
    p=document.createElement('div');p.id='term-cmd-picker';p.className='term-cmd-picker';
    const parent=document.getElementById('term-input-area')||document.getElementById('home-composer');
    parent?.appendChild(p);
  }
  if(!matches.length){p.style.display='none';return}
  p.style.display='block';
  p.innerHTML=matches.map((c,i)=>`<div class="term-cmd-item${i===0?' focused':''}" data-cmd="${c.cmd}"><span class="term-cmd-name">${c.cmd}</span><span class="term-cmd-desc">${c.desc}</span></div>`).join('');
  p.querySelectorAll('.term-cmd-item').forEach(item=>{item.onmousedown=e=>{e.preventDefault();input.value=item.dataset.cmd;hideCmdPicker();input.focus()}});
}
function hideCmdPicker(){const p=document.getElementById('term-cmd-picker');if(p)p.style.display='none'}

function _currentSessionId(){
  const h=location.hash;if(!h.startsWith('#/corpus/'))return null;
  const q=h.split('?')[1]||'';return new URLSearchParams(q).get('session');
}
function renderSBChats(){
  const el=document.getElementById('sb-chats');if(!el)return;
  if(!_chatSessions.length){el.innerHTML='';return}
  const activeSid=_currentSessionId();
  el.innerHTML=_chatSessions.map(c=>{
    const active=c.id===activeSid?' active':'';
    return`<div class="sb-chat-wrap${active}" data-sid="${c.id}"><a href="#/corpus/${c.corpus_id}?session=${c.id}" class="sb-chat-item" title="${esc(c.title||'')}">${esc(c.title||'Untitled')}</a><button class="sb-chat-del" data-sid="${c.id}" title="Delete chat" aria-label="Delete chat">×</button></div>`;
  }).join('');
  el.querySelectorAll('.sb-chat-del').forEach(btn=>{
    btn.onclick=async e=>{e.preventDefault();e.stopPropagation();await _deleteSession(btn.dataset.sid)};
  });
}
async function _deleteSession(sid){
  if(!confirm('Delete this chat?'))return;
  try{await fetch(`${API}/chat-sessions/${sid}`,{method:'DELETE'})}catch(e){}
  const wasCurrent=_currentSessionId()===sid;
  _chatSessions=_chatSessions.filter(c=>c.id!==sid);
  renderSBChats();
  if(document.querySelector('.chats-list'))renderChats();
  if(wasCurrent){const base=location.hash.split('?')[0];location.hash=base||'#/main'}
}
function setSBActive(h){document.getElementById('sb-new')?.classList.toggle('active',h==='#/main');document.getElementById('nav-corpora').classList.toggle('active',h==='#/corpora');document.getElementById('nav-explore').classList.toggle('active',h.startsWith('#/explore')||h==='#/network');document.getElementById('nav-chats')?.classList.toggle('active',h==='#/chats');const np=document.getElementById('nav-pricing');if(np)np.classList.toggle('active',h==='#/pricing');const na=document.getElementById('nav-account');if(na)na.classList.toggle('active',h==='#/account')}
function hideRP(){document.getElementById('rpanel').classList.add('hidden')}

/* ══════ LANDING ══════ */
const DM_FALLBACK=[{n:"Lenny's Newsletter",d:'product, growth',c:'#e76f51'},{n:'Paul Graham',d:'startups, philosophy',c:'#2a9d8f'},{n:'AI Research',d:'AI, ML',c:'#264653'},{n:'Feynman Lectures',d:'physics, science',c:'#f4a261'},{n:'Stoic Philosophy',d:'philosophy, ethics',c:'#588157'},{n:'YC Startup School',d:'startups, growth',c:'#457b9d'},{n:'Design Patterns',d:'software, design',c:'#e9c46a'},{n:'World History',d:'history, culture',c:'#b56576'}];
function renderLP(){const el=document.getElementById('page-landing');el.innerHTML=`<div class="lp"><nav class="lp-top"><span class="lp-brand"><svg width="17" height="17" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere</span><div class="lp-top-right"><a href="https://github.com/steveyeow/noosphere" target="_blank" rel="noopener" class="lp-social-link" title="GitHub"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg></a><a href="https://discord.gg/8PAmqAU24R" target="_blank" rel="noopener" class="lp-social-link" title="Discord"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg></a><button class="lp-dark-btn" id="lp-dark-btn" title="Toggle dark mode"><svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg><svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button></div></nav><div class="lp-cv" id="lp-cv"></div><div class="lp-ct"><div class="lp-h"><h1 class="lp-h1">Publish your knowledge to a network any AI agent can query.</h1><p class="lp-sub">Your knowledge compounds into a growing global network — upload files, import feeds, save insights from conversations. Share it free, keep it private, or charge for access.</p><button class="lp-go" id="lp-go">Get Started →</button><a href="#/explore" class="lp-explore" id="lp-explore" style="display:inline-block;margin-left:12px;color:var(--accent);text-decoration:none;font-size:15px;opacity:0.85">Explore Knowledge Bases →</a></div><div class="lp-term" id="lp-term"><div class="lp-term-bar"><span class="lp-term-dot red"></span><span class="lp-term-dot ylw"></span><span class="lp-term-dot grn"></span><span class="lp-term-title">noosphere</span></div><div class="lp-term-body" id="lp-term-body"></div></div></div><div class="lp-mission">Expand the scope and scale of collective enlightenment.</div></div>`;
  document.getElementById('lp-go').onclick=()=>{
    if(_cloudMode&&!_authUser){location.hash='#/login'}else{location.hash='#/main'}
  };
  document.getElementById('lp-explore').onclick=e=>{e.preventDefault();location.hash='#/explore'};
  document.getElementById('lp-dark-btn').onclick=toggleTheme;
  drawLPGraph();animateLPTerm()}

let _loginMode='signin'; // 'signin' or 'signup'
function renderLogin(){
  const el=document.getElementById('page-landing');
  const isSignup=_loginMode==='signup';
  el.innerHTML=`<div class="login-page">
    <div class="login-card">
      <div class="login-logo">${NOOS_ICON_SVG}</div>
      <h1 class="login-title">Welcome to <strong>Noosphere</strong></h1>
      <p class="login-sub">Publish knowledge any AI agent can read. It grows, gets discovered, and earns for you.</p>
      <button class="login-google" id="login-google-btn">
        <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
        Continue with Google
      </button>
      <div class="login-divider"><span>or ${isSignup?'sign up':'sign in'} with email</span></div>
      <input class="login-input" id="login-email" type="email" placeholder="Email address" autocomplete="email"/>
      <input class="login-input" id="login-pass" type="password" placeholder="Password" autocomplete="${isSignup?'new-password':'current-password'}"/>
      <button class="login-submit" id="login-submit-btn">${isSignup?'Sign up':'Sign in'}</button>
      <p class="login-toggle">${isSignup?"Already have an account? <a href='#' id='login-switch'>Sign in</a>":"Don't have an account? <a href='#' id='login-switch'>Sign up</a>"}</p>
      <a href="#/" class="login-back">&larr; Back</a>
    </div>
  </div>`;
  document.getElementById('login-google-btn').onclick=signInWithGoogle;
  document.getElementById('login-switch').onclick=e=>{e.preventDefault();_loginMode=isSignup?'signin':'signup';renderLogin()};
  document.getElementById('login-submit-btn').onclick=async()=>{
    const email=document.getElementById('login-email').value.trim();
    const pass=document.getElementById('login-pass').value;
    if(!email||!pass){toast('Email and password required');return}
    const btn=document.getElementById('login-submit-btn');btn.disabled=true;btn.textContent='Loading...';
    try{
      if(isSignup){
        const{error}=await _supabase.auth.signUp({email,password:pass});
        if(error)throw error;
        toast('Check your email to confirm your account','success');
      }else{
        const{error}=await _supabase.auth.signInWithPassword({email,password:pass});
        if(error)throw error;
        location.hash='#/main';
      }
    }catch(e){toast(e.message||'Authentication failed')}
    btn.disabled=false;btn.textContent=isSignup?'Sign up':'Sign in';
  };
  document.getElementById('login-pass').onkeydown=e=>{if(e.key==='Enter')document.getElementById('login-submit-btn').click()};
}

function animateLPTerm(){
  const body=document.getElementById('lp-term-body');if(!body)return;
  const lines=[
    {delay:400,type:'cmd',text:'> Upload: startup-essays.pdf, product-notes.md'},
    {delay:1000,type:'out',text:'Ingesting 2 files...'},
    {delay:600,type:'status',text:'BUILDING',label:'Knowledge base: Startup Playbook'},
    {delay:500,type:'out',text:'Chunking into 47 semantic blocks...'},
    {delay:900,type:'out',text:'Generating embeddings ████████████████ 47/47'},
    {delay:400,type:'status',text:'READY',label:'Indexed & searchable'},
    {delay:800,type:'out',text:''},
    {delay:200,type:'cmd',text:'> Search: "how to find good startup ideas"'},
    {delay:1100,type:'result',score:'0.94',text:'"The very best startup ideas tend to have three things in common: they\'re something the founders themselves want..."',cite:'startup-essays.pdf — p.12'},
    {delay:700,type:'result',score:'0.89',text:'"Live in the future, then build what\'s missing."',cite:'product-notes.md'},
    {delay:600,type:'out',text:''},
    {delay:200,type:'cmd',text:'> Connect to Noosphere network'},
    {delay:800,type:'status',text:'LIVE',label:'Joined the Noosphere'},
    {delay:400,type:'out',text:'MCP endpoint: localhost:8420/mcp'},
    {delay:300,type:'out',text:'Any AI agent can now discover & query your knowledge.'},
  ];

  let i=0,totalDelay=0;
  function addLine(l){
    const el=document.createElement('div');
    if(l.type==='cmd'){
      el.className='lpt-line lpt-cmd';el.textContent=l.text;
    }else if(l.type==='out'){
      if(!l.text){el.className='lpt-spacer';el.innerHTML='&nbsp;'}
      else{el.className='lpt-line lpt-out';el.textContent=l.text;}
    }else if(l.type==='status'){
      el.className='lpt-line lpt-status';
      const st=l.text==='INDEXED'?'#3b82f6':l.text==='CREATING'?'#f59e0b':l.text==='LIVE'?'#22c55e':'#86868b';
      el.innerHTML=`<span class="lpt-badge" style="color:${st}">${l.text}</span> ${esc(l.label)}`;
    }else if(l.type==='result'){
      el.className='lpt-result';
      el.innerHTML=`<span class="lpt-score">Score: ${l.score}</span><div class="lpt-quote">${esc(l.text)}</div><div class="lpt-cite">${esc(l.cite)}</div>`;
    }
    body.appendChild(el);body.scrollTop=body.scrollHeight;
  }

  function step(){
    if(i>=lines.length){setTimeout(()=>{body.innerHTML='';i=0;totalDelay=0;step()},3000);return}
    const l=lines[i];
    setTimeout(()=>{addLine(l);i++;step()},l.delay);
  }
  step();
}
async function drawLPGraph(){const co=document.getElementById('lp-cv');if(!co)return;
  let DM=DM_FALLBACK;
  try{const r=await fetch(`${API}/corpora`);const live=await r.json();if(live&&live.length>=3){DM=live.map(c=>{const tg=Array.isArray(c.tags)?c.tags:[];return{n:c.name,d:tg.join(', '),c:cC(c.name)}})}}catch(e){}
  const tk=m=>(m.d||'').split(/[,;]+/).map(d=>d.trim().toLowerCase()).filter(Boolean);const ns=DM.map((m,i)=>({id:'l'+i,name:m.n,dom:m.d,color:m.c||cC(m.n),ini:m.n.split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk:tk(m)}));const lk=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=ns[i].tk.filter(t=>ns[j].tk.some(u=>t===u||t.includes(u)||u.includes(t)));if(s.length)lk.push({source:ns[i].id,target:ns[j].id,s:s.length})}const dp=devicePixelRatio||1,W=co.clientWidth||800,H=co.clientHeight||600,BR=Math.max(14,Math.min(22,W/(ns.length*2.5)));const cv=document.createElement('canvas');cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';co.appendChild(cv);const cx=cv.getContext('2d');cx.scale(dp,dp);const pts=[];lk.forEach(l=>{for(let i=0;i<Math.max(1,Math.round(l.s*1.5));i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.2,op:.3+Math.random()*.5})});const gX=W*.5,zn=[{cx:W*.15+140,cy:H/2,hw:200,hh:140},{cx:W*.75+60,cy:H/2,hw:300,hh:200}];function av(){let n;function f(){for(const nd of n)for(const z of zn){const dx=nd.x-z.cx,dy=nd.y-z.cy,ox=z.hw-Math.abs(dx),oy=z.hh-Math.abs(dy);if(ox>0&&oy>0){if(ox<oy){nd.vx+=(dx>=0?1:-1)*ox*.08;nd.vx*=.85}else{nd.vy+=(dy>=0?1:-1)*oy*.08;nd.vy*=.85}}}}f.initialize=x=>{n=x};return f}const sim=d3.forceSimulation(ns).force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(55,220-d.s*50)).strength(d=>.08+d.s*.15)).force('charge',d3.forceManyBody().strength(-400).distanceMax(550)).force('center',d3.forceCenter(gX,H/2).strength(.02)).force('collision',d3.forceCollide().radius(BR+12)).force('avoid',av()).alphaDecay(.03).velocityDecay(.35);let hov=null,mp=null;cv.onmousemove=e=>{const r=cv.getBoundingClientRect();mp=[e.clientX-r.left,e.clientY-r.top];hov=null;for(const n of ns)if(Math.hypot(n.x-mp[0],n.y-mp[1])<BR+4){hov=n;break}cv.style.cursor=hov?'pointer':'default'};cv.onmouseleave=()=>{hov=null;mp=null};function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);for(const l of lk){const s=l.source,t=l.target;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=`rgba(160,170,190,${.1+l.s*.07})`;cx.lineWidth=.5+l.s*.3;cx.stroke()}for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=`rgba(130,150,200,${p.op*.35})`;cx.fill()}for(const n of ns){const h=hov===n;let r=BR;if(mp){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<180?BR*(1+(1-d/180)*.45):BR*.8}if(h)r=Math.max(r,BR*1.35);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*1.8);g.addColorStop(0,`rgba(${cr},${cg},${cb},${h?.1:.04})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*1.8,0,Math.PI*2);cx.fillStyle=g;cx.fill();if(h){cx.beginPath();cx.arc(n.x,n.y,rr+2,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},.4)`;cx.lineWidth=1.5;cx.stroke()}cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);cx.fillStyle=n.color;cx.fill();cx.strokeStyle='rgba(255,255,255,.2)';cx.lineWidth=1;cx.stroke();cx.fillStyle='rgba(255,255,255,.92)';cx.font=`700 ${rr*.5}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.9:.65})`:`rgba(30,35,50,${h?.85:.55})`;cx.font=`600 ${h?10:9}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+10)}cx.restore();_lpAnim=requestAnimationFrame(draw)}sim.on('tick',()=>{});_lpAnim=requestAnimationFrame(draw)}

/* ══════ HOME — Terminal (input top, output below) ══════ */
const TERM_STATUS_C={READY:'#10b981',INDEXED:'#3b82f6',CREATED:'#f59e0b'};
let _termCtx={};

function renderHome(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.classList.add('content--home');
  const _h=new Date().getHours();
  const _tod=_h<12?'Good morning':_h<18?'Good afternoon':'Good evening';
  const greetText=_firstName?`${_tod}, ${_firstName}`:_tod;

  ct.innerHTML=`<div class="home" id="home">
    <div class="home-hero" id="home-hero">
      <canvas class="home-hero-mark" id="dragon-cv" width="64" height="64"></canvas>
      <h1 class="home-greet">${esc(greetText)}</h1>
    </div>
    <div class="home-output" id="term-output"></div>
    <div class="home-dock" id="home-dock">
      <div class="home-composer" id="home-composer">
        <textarea class="home-composer-input" id="term-input" placeholder="Pick a knowledge base below — then add new ideas via chat, URL, or file" rows="1"></textarea>
        <div class="home-composer-foot">
          <span class="home-composer-left">
            <button class="composer-attach" id="home-attach" title="Add content" aria-label="Add content"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
            <button class="composer-sliders" id="home-sliders" title="Sources" aria-label="Sources"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg></button>
            <button class="composer-mode-label" id="home-mode-label" type="button">Enrich mode</button>
            <span class="home-composer-hint" id="home-composer-hint">Type <kbd>/</kbd> for commands</span>
            <button class="home-composer-cancel" id="home-cancel" type="button" style="display:none">Cancel</button>
          </span>
          <span class="home-composer-right">
            <span class="home-composer-model" id="home-composer-model">Noos</span>
            <button class="home-composer-send" id="home-send" title="Send" aria-label="Send">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
            </button>
          </span>
        </div>
        <div class="home-composer-conn">
          <button class="home-chip" id="chip-corpus" type="button" aria-haspopup="menu"><span class="home-chip-label" id="chip-corpus-label">Corpus: Any</span><span class="home-chip-caret">▾</span></button>
          <div class="chint" id="home-chint"></div>
        </div>
      </div>
    </div>
    <div class="home-tworow" id="home-tworow">
      <div class="home-col">
        <div class="home-col-hd">Recent corpora</div>
        <div class="home-col-list" id="home-col-recent"></div>
      </div>
      <div class="home-col">
        <div class="home-col-hd">Suggested writes</div>
        <div class="home-col-list" id="home-col-suggested"></div>
      </div>
    </div>
  </div>`;

  (function drawDragon(){
    const cv=document.getElementById('dragon-cv');if(!cv)return;
    const x=cv.getContext('2d');
    const P=5,_='',O='#c8956c',L='#dba882';
    let blink=false,frame=0,nextBlink=90+Math.random()*120|0;
    function draw(){
      const dk=isDark();
      const E=dk?'#d0cfc8':'#1d1d1f';
      const W=dk?'#a87048':'#f5e6d3';
      const base=[
        [_,_,_,L,_,_,_,_,_,L,_,_],
        [_,_,L,_,_,_,_,_,_,L,_,_],
        [_,_,O,O,O,O,O,O,O,O,_,_],
        [_,O,_,_,_,_,_,_,_,_,O,_],
        [_,O,_,E,E,_,_,E,E,_,O,_],
        [_,_,O,_,_,_,_,_,_,O,_,_],
        [_,_,O,_,_,E,E,_,_,O,_,_],
        [_,_,_,O,W,W,W,W,O,_,_,_],
        [_,_,_,O,_,_,_,_,O,_,_,_],
        [L,O,O,_,_,_,_,_,_,O,O,L],
        [_,L,_,O,_,_,_,_,O,_,L,_],
        [_,_,_,E,_,_,_,_,E,_,_,_],
      ];
      x.clearRect(0,0,cv.width,cv.height);
      const rows=base.map(r=>[...r]);
      if(blink){rows[4]=[_,O,_,O,O,_,_,O,O,_,O,_]}
      const t=frame*0.04;
      const breathOff=Math.sin(t)*1.5;
      const wingPhase=Math.sin(t*1.8);
      if(wingPhase>0){
        rows[9]=[_,O,O,_,_,_,_,_,_,O,O,_];
        rows[10]=[L,L,_,O,_,_,_,_,O,_,L,L];
      }else{
        rows[9]=[_,_,O,_,_,_,_,_,_,O,_,_];
        rows[10]=[_,_,L,O,_,_,_,_,O,L,_,_];
      }
      const oY=Math.round(breathOff);
      rows.forEach((r,y)=>r.forEach((c,xi)=>{if(c){x.fillStyle=c;x.fillRect(xi*P,y*P+oY+2,P,P)}}));
    }
    function tick(){
      frame++;
      if(frame>=nextBlink&&!blink){blink=true;setTimeout(()=>{blink=false;nextBlink=frame+90+Math.random()*180|0},100+Math.random()*60)}
      draw();
      requestAnimationFrame(tick);
    }
    tick();
  })();

  const input=document.getElementById('term-input');
  const output=document.getElementById('term-output');
  const sendBtn=document.getElementById('home-send');
  const slidersBtn=document.getElementById('home-sliders');
  if(slidersBtn)slidersBtn.onclick=(e)=>showSourcesPopover(e.currentTarget,{corpusId:null,corpusName:null});
  const attachBtn=document.getElementById('home-attach');
  if(attachBtn)attachBtn.onclick=(e)=>showAttachPopover(e.currentTarget,output,input);
  // Mode label is clickable too — anchors the popover to the sliders button so
  // the flyout lines up predictably regardless of which of the two the user hits.
  const modeLabelBtn=document.getElementById('home-mode-label');
  if(modeLabelBtn)modeLabelBtn.onclick=()=>{const a=document.getElementById('home-sliders');showSourcesPopover(a,{corpusId:null,corpusName:null})};
  _refreshComposerPlaceholder();
  renderChint('home-chint',{corpusId:null});
  const composer=document.getElementById('home-composer');
  const cancelBtn=document.getElementById('home-cancel');
  const modelLbl=document.getElementById('home-composer-model');
  const hintLbl=document.getElementById('home-composer-hint');
  const chipBtn=document.getElementById('chip-corpus');
  const chipLbl=document.getElementById('chip-corpus-label');
  _termCtx={};
  // Composer mode state. 'ask' (default, talk to your knowledge) vs.
  // 'write' (the composer becomes a note body; Send becomes Save).
  let _mode='ask';
  // Scoped corpus: null means "Any" (default). Persists across sends.
  // Hoisted to module-level _homeScope so the Recently compiled section and
  // the Compile picker can read the same selection.
  _homeScope=null;

  // Auto-resize textarea as user types
  function autosize(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,_mode==='write'?Math.round(window.innerHeight*0.6):200)+'px'}
  input.addEventListener('input',()=>{
    autosize();
    const v=input.value;
    // Slash commands are only meaningful in ask mode — in write mode a leading
    // "/" is just markdown content, not a command.
    if(_mode==='ask'&&v.startsWith('/')){const q=v.toLowerCase();showCmdPicker(input,TERM_CMDS.filter(c=>c.cmd.startsWith(q)))}
    else hideCmdPicker();
    if(_mode==='write')scheduleDraftSave();
  });
  // Debounced localStorage autosave so users never lose a long-form note to a
  // stray refresh or cancel. One global draft slot is enough — the composer is
  // a singleton. Cleared on successful save; preserved on Cancel so coming
  // back to Write restores what was in flight.
  const DRAFT_KEY='noos_draft_note';
  let _draftTimer=null,_draftFlashTimer=null;
  function setDraftStatus(text,transient){
    if(!modelLbl||_mode!=='write')return;
    modelLbl.textContent=text||'';
    if(_draftFlashTimer){clearTimeout(_draftFlashTimer);_draftFlashTimer=null}
    if(transient){_draftFlashTimer=setTimeout(()=>{if(_mode==='write'&&modelLbl)modelLbl.textContent=''},2000)}
  }
  function scheduleDraftSave(){
    if(_draftTimer)clearTimeout(_draftTimer);
    _draftTimer=setTimeout(()=>{
      try{
        const v=input.value;
        if(v.trim()){localStorage.setItem(DRAFT_KEY,v);setDraftStatus('Draft saved',true)}
        else{localStorage.removeItem(DRAFT_KEY)}
      }catch(e){}
    },600);
  }
  function clearDraft(){try{localStorage.removeItem(DRAFT_KEY)}catch(e){}}
  input.addEventListener('blur',()=>hideCmdPicker());
  // Keyboard: Esc exits write mode. Enter sends in ask mode; in write mode
  // plain Enter inserts a newline (matches Notion/Obsidian expectations for
  // prose) and ⌘/Ctrl+Enter saves.
  input.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&_mode==='write'){e.preventDefault();exitToAsk();return}
    if(e.key!=='Enter')return;
    if(_mode==='write'){
      if(e.metaKey||e.ctrlKey){e.preventDefault();sendInput()}
    } else if(!e.shiftKey){
      e.preventDefault();sendInput();
    }
  });

  // Move from centered empty-state to active chat mode: output fills above,
  // composer sticks to bottom, hero + suggestions hide.
  function collapseToChat(){
    const h=document.getElementById('home');
    if(h)h.classList.add('home--active');
  }
  // Return to centered empty state when there is nothing to show — otherwise
  // leaving a fresh /write + Cancel would strand the user in empty chat mode.
  function maybeUncollapse(){
    if(!output||output.children.length===0){
      const h=document.getElementById('home');if(h)h.classList.remove('home--active');
    }
  }

  function updateChip(){
    const c=_homeScope&&_corpora.find(x=>x.id===_homeScope);
    const name=c?c.name:'Any';
    const prefix=_mode==='write'?'Save to: ':'Corpus: ';
    chipLbl.textContent=prefix+name;
    // Enrich placeholder depends on whether a KB is picked — keep them in sync.
    _refreshComposerPlaceholder();
  }
  function enterWrite(seedTitle){
    _mode='write';
    composer.classList.add('home-composer-note');
    const h=document.getElementById('home');if(h)h.classList.add('home--writing');
    input.placeholder='Jot down a note — first line becomes the title. Markdown supported.';
    input.rows=10;
    // Pre-fill the first line with the suggested title so the user jumps
    // straight into the body. The first line is treated as the title on save.
    // If a draft was autosaved from a prior session, restore it unless the
    // user explicitly clicked a fresh starter (seedTitle).
    let restoredDraft=false;
    if(seedTitle){
      input.value='# '+seedTitle+'\n\n';
      setTimeout(()=>{input.selectionStart=input.selectionEnd=input.value.length;},0);
    } else {
      try{const d=localStorage.getItem(DRAFT_KEY);if(d&&d.trim()){input.value=d;restoredDraft=true}}catch(e){}
    }
    autosize();
    sendBtn.title='Save (⌘↵)';sendBtn.setAttribute('aria-label','Save');
    sendBtn.classList.add('is-save');
    sendBtn.innerHTML='<span>Save</span>';
    if(cancelBtn)cancelBtn.title='Cancel (Esc)';
    if(modelLbl)modelLbl.textContent='';
    // Hide the ask-flow mode label (Enrich/Create/Compile) — it routes chat
    // behavior, not saves. Surface a keyboard hint in its place so users know
    // Enter is a newline and ⌘↵ saves.
    if(modeLabelBtn)modeLabelBtn.style.display='none';
    if(attachBtn)attachBtn.style.display='none';
    if(slidersBtn)slidersBtn.style.display='none';
    if(hintLbl)hintLbl.style.display='none';
    if(cancelBtn)cancelBtn.style.display='';
    updateChip();
    input.focus();
    if(restoredDraft)setDraftStatus('Draft restored',true);
  }
  function exitToAsk(){
    _mode='ask';
    composer.classList.remove('home-composer-note');
    const h=document.getElementById('home');if(h)h.classList.remove('home--writing');
    input.rows=2;autosize();
    sendBtn.title='Send';sendBtn.setAttribute('aria-label','Send');
    sendBtn.classList.remove('is-save');
    sendBtn.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
    if(modelLbl)modelLbl.textContent='Noos';
    if(modeLabelBtn)modeLabelBtn.style.display='';
    if(attachBtn)attachBtn.style.display='';
    if(slidersBtn)slidersBtn.style.display='';
    if(hintLbl){hintLbl.style.display='';hintLbl.innerHTML='Type <kbd>/</kbd> for commands'}
    if(cancelBtn)cancelBtn.style.display='none';
    updateChip();
    _refreshComposerPlaceholder();
    maybeUncollapse();
    input.focus();
  }
  if(cancelBtn)cancelBtn.onclick=exitToAsk;

  // Corpus chip menu — click to pick a corpus scope (or create new inline).
  let _menuOpen=false;
  function closeChipMenu(){const m=document.getElementById('chip-corpus-menu');if(m)m.remove();_menuOpen=false}
  function openChipMenu(){
    if(_menuOpen){closeChipMenu();return}
    const menu=document.createElement('div');menu.id='chip-corpus-menu';menu.className='home-chip-menu open';
    const isWrite=_mode==='write';
    const rows=[];
    if(!isWrite){rows.push(`<div class="home-chip-menu-item${_homeScope===null?' active':''}" data-id=""><span>Any</span><span class="home-chip-menu-hint">search all</span></div>`)}
    rows.push(..._corpora.map(c=>`<div class="home-chip-menu-item${_homeScope===c.id?' active':''}" data-id="${c.id}"><span>${esc(c.name)}</span><span class="home-chip-menu-hint">${c.document_count||0} docs</span></div>`));
    if(_corpora.length||!isWrite)rows.push('<div class="home-chip-menu-divider"></div>');
    rows.push('<div class="home-chip-menu-new"><input type="text" id="chip-new-name" placeholder="New corpus name" /><button id="chip-new-go">Create</button></div>');
    menu.innerHTML=rows.join('');
    composer.appendChild(menu);
    // Direction-aware positioning: drop DOWN when composer is centered (empty
    // state has room below); drop UP when composer is stuck to viewport bottom
    // in chat mode (downward would overflow).
    const cr=chipBtn.getBoundingClientRect();const mr=composer.getBoundingClientRect();
    const chatMode=document.getElementById('home')?.classList.contains('home--active');
    menu.style.left=(cr.left-mr.left)+'px';
    if(chatMode){
      menu.style.bottom=(mr.bottom-cr.top+6)+'px';
      menu.style.top='auto';
    }else{
      menu.style.top=(cr.bottom-mr.top+6)+'px';
      menu.style.bottom='auto';
    }
    _menuOpen=true;
    menu.querySelectorAll('.home-chip-menu-item').forEach(el=>{
      el.onclick=()=>{_homeScope=el.dataset.id||null;updateChip();closeChipMenu();input.focus()};
    });
    const nameEl=menu.querySelector('#chip-new-name'),goEl=menu.querySelector('#chip-new-go');
    const createNew=async()=>{
      const nm=nameEl.value.trim();if(!nm){nameEl.focus();return}
      goEl.disabled=true;goEl.textContent='…';
      try{
        const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm,access_level:'public'})});
        const c=await r.json();await loadC();_homeScope=c.id;updateChip();closeChipMenu();toast(`Created ${nm}`,'success');renderSBChats();input.focus();
      }catch(e){toast('Failed to create corpus');goEl.disabled=false;goEl.textContent='Create'}
    };
    goEl.onclick=createNew;
    nameEl.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();createNew()}else if(e.key==='Escape'){closeChipMenu()}};
    // Click outside to dismiss.
    setTimeout(()=>document.addEventListener('mousedown',outsideClose,{once:true}),0);
  }
  function outsideClose(e){
    const m=document.getElementById('chip-corpus-menu');
    if(!m)return;
    if(chipBtn.contains(e.target)||m.contains(e.target)){document.addEventListener('mousedown',outsideClose,{once:true});return}
    closeChipMenu();
  }
  chipBtn.onclick=openChipMenu;

  let _sending=false;
  async function saveNote(body){
    // Derive title from the first non-empty line (strip markdown headers).
    const firstLine=(body.split('\n').find(l=>l.trim())||'').replace(/^#+\s*/,'').trim();
    const title=firstLine.slice(0,80)||('Note '+new Date().toLocaleDateString('en-US',{month:'short',day:'numeric'}));
    sendBtn.disabled=true;
    await loadC();
    let cid=_homeScope;
    if(!cid){
      if(_corpora.length===0){
        try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});const c=await r.json();cid=c.id;await loadC()}
        catch(e){toast('Failed to create corpus');sendBtn.disabled=false;return}
      } else if(_corpora.length===1){
        cid=_corpora[0].id;
      } else {
        toast('Pick a corpus first');sendBtn.disabled=false;openChipMenu();return;
      }
    }
    const fd=new FormData();
    fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+body],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');
    try{await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd})}
    catch(e){toast('Save failed: '+e.message);sendBtn.disabled=false;return}
    ensureIndexed(cid);
    clearDraft();
    input.value='';autosize();sendBtn.disabled=false;
    collapseToChat();
    const corpus=_corpora.find(c=>c.id===cid);
    addLine(output,'resp','Saved: "'+title+'"');
    addLine(output,'card',null,null,{type:'card',label:'Note saved',status:'READY',detail:(corpus?corpus.name:'Corpus')+' — '+title,corpus_id:cid});
    exitToAsk();
    await loadC();
  }
  async function sendInput(){
    if(_sending)return;
    const val=input.value.trim();if(!val)return;
    // Write-mode: Send button acts as Save (short-circuits slash commands so
    // users can freely include "/" in their notes).
    if(_mode==='write'){await saveNote(val);return}
    // Compile mode: Send becomes "synthesize a wiki page on this topic" and
    // lands the user in the canvas view. Corpus must be scoped (a topic-wide
    // compile across all corpora isn't meaningful yet).
    if(_composerMode==='compile'){
      if(!_homeScope){
        await loadC();
        if(!_corpora.length){toast('Add sources first to compile');return}
        if(_corpora.length===1){_homeScope=_corpora[0].id}
        else{toast('Pick a corpus in the chip to compile into');return}
      }
      const topic=val;input.value='';autosize();
      location.hash='#/compile?fresh=1&corpus='+encodeURIComponent(_homeScope)+'&topic='+encodeURIComponent(topic);
      return;
    }
    // Client-side slash handlers that short-circuit /terminal
    if(val.toLowerCase()==='/upload'){input.value='';autosize();collapseToChat();showTermUpload(output,input,_homeScope);return}
    if(val.toLowerCase()==='/write'){input.value='';autosize();enterWrite();return}
    if(val.toLowerCase()==='/history'){
      input.value='';autosize();collapseToChat();
      await loadChatSessions();
      if(!_chatSessions.length){addLine(output,'resp','No chat history yet.')}
      else{addLine(output,'resp','Recent conversations:');_chatSessions.slice(0,10).forEach(c=>{const el=document.createElement('div');el.className='term-line term-option';el.innerHTML=NOOS_DOT+'<span><span style="color:var(--tx3);margin-right:8px">'+esc(c.corpus_name||'')+'</span>'+esc(c.title||'Untitled')+'</span>';el.onclick=()=>{location.hash='#/corpus/'+c.corpus_id+'?session='+c.id};output.appendChild(el)})}
      input.focus();return;
    }
    if(val.toLowerCase()==='/help'){
      input.value='';autosize();collapseToChat();
      [['URL','Paste any URL to import a page'],['  /upload','Add a file to a corpus'],['  /write','Write a quick note'],['  /history','View recent conversations'],['  /new','Create a new corpus'],['  /status','Show your corpora stats']].forEach(([cmd,desc])=>addLine(output,'hint',cmd.padEnd(12)+desc));
      input.focus();return;
    }
    if(val.toLowerCase()==='/new'){
      input.value='';autosize();collapseToChat();
      addLine(output,'resp','Name for the new knowledge base:');
      const wrap=document.createElement('div');wrap.style.cssText='margin-left:18px;margin-top:8px;display:flex;gap:8px;align-items:center';
      wrap.innerHTML='<input type="text" id="new-corpus-input" placeholder="e.g. Research notes" style="flex:1;font-size:13px;border:1px solid var(--brd);border-radius:8px;padding:6px 10px;background:var(--bg2);color:var(--tx);outline:none" /><button class="btn-sm" id="new-corpus-btn">Create</button>';
      output.appendChild(wrap);
      const ni=document.getElementById('new-corpus-input');ni.focus();
      async function doCreate(){const name=ni.value.trim();if(!name)return;wrap.remove();try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,access_level:'public'})});const c=await r.json();await loadC();addLine(output,'card',null,null,{type:'card',label:name,status:'CREATED',detail:'New knowledge base created',corpus_id:c.id});renderSBChats()}catch(e){addLine(output,'resp','Failed: '+e.message)}input.focus()}
      document.getElementById('new-corpus-btn').onclick=doCreate;ni.onkeydown=e=>{if(e.key==='Enter')doCreate();if(e.key==='Escape'){wrap.remove();input.focus()}};
      return;
    }
    _sending=true;input.value='';autosize();input.disabled=true;
    collapseToChat();
    addLine(output,'prompt',val);
    const loadId='ld-'+Date.now();
    addLine(output,'thinking','Thinking…',loadId);
    try{
      const r=await fetch(`${API}/terminal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:val,context:_termCtx})});
      const d=await r.json();
      document.getElementById(loadId)?.remove();
      _termCtx=d.context||{};
      for(const line of(d.lines||[]))addLine(output,line.type,null,null,line);
      if(d.context?.action==='open_write'){enterWrite()}
      if(d.context?.action==='open_upload'){showTermUpload(output,input,_homeScope)}
    }catch(err){document.getElementById(loadId)?.remove();addLine(output,'resp','Error: '+err.message)}
    input.disabled=false;input.focus();
    _sending=false;
  }
  sendBtn.onclick=sendInput;

  // Note: the external shortcut row (Write / Upload / Add RSS pills) was
  // removed — Write is covered by the Suggested column below; Upload and
  // Add RSS moved into the composer's "+" attach menu (showAttachPopover).
  // The "+" button click handler is wired above next to the sliders button.

  // Two-column shelf — Recent corpora (left) + Suggested write starters (right).
  // Notion-style compact list; left lets users jump back into a KB, right seeds
  // Write mode with a pre-filled title so no blank-page moment.
  renderHomeTworow(enterWrite);

  // Message-level "Save to corpus" — delegated at the output container so
  // every current and future assistant reply picks it up. The chosen corpus
  // chip drives the destination; otherwise we fall through the same
  // auto-create / single / pick logic as saveNote.
  output.addEventListener('click',async e=>{
    const btn=e.target.closest('.term-save');
    if(!btn||btn.classList.contains('saved')||btn.disabled)return;
    const content=(btn.dataset.content||'').trim();
    if(!content)return;
    btn.disabled=true;const orig=btn.innerHTML;btn.innerHTML='Saving…';
    const firstLine=(content.split('\n').find(l=>l.trim())||'').replace(/^#+\s*/,'').trim();
    const title=firstLine.slice(0,80)||('Captured '+new Date().toLocaleDateString('en-US',{month:'short',day:'numeric'}));
    let cid=_homeScope;
    if(!cid){
      await loadC();
      if(_corpora.length===1){cid=_corpora[0].id}
      else if(_corpora.length===0){
        try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});cid=(await r.json()).id;await loadC()}
        catch(e){toast('Failed to create corpus');btn.innerHTML=orig;btn.disabled=false;return}
      } else {
        const picked=await pickCorpusInline(output);
        if(!picked){btn.innerHTML=orig;btn.disabled=false;return}
        cid=picked;
      }
    }
    const fd=new FormData();
    fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+content],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');
    // Save-to-corpus preserves an AI-synthesized reply the user chose to keep.
    // It's NOT user_original (the user didn't write it); it's user_capture —
    // same semantic bucket as /capture (capturing something from a live
    // session). Attribution matters: only first-party user_original content
    // should feed monetization downstream.
    fd.append('source_kind','user_capture');
    try{
      await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
      ensureIndexed(cid);
      btn.classList.add('saved');btn.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Saved`;
      await loadC();
    }catch(e){
      toast('Save failed: '+e.message);btn.innerHTML=orig;btn.disabled=false;
    }
  });

  input.focus();autosize();
}

/* ══════ HOME TWO-COLUMN ROW — Recent corpora + Suggested write starters ══════
   Notion-style below-composer shelf. Left column shows recently-touched KBs
   as one-tap jumps back; right column shows write-starters that seed Write
   mode with a pre-filled title so users don't stare at a blank composer. */
// Four daily-produced content shapes, each teaching a distinct Noosphere
// value — not a generic write prompt:
//   - Random thoughts          → volume capture; no judgment, just dump
//   - Skill I'm learning       → growth over time; the KB accumulates expertise
//   - Reading notes            → external input curation; you read, Noos keeps it
//   - Question I'm chewing on  → long-lived unfinished content; traditional notes
//                                apps are worst at this — Noosphere's retrieval
//                                + living wiki surfaces old open questions when
//                                new info arrives. This suggestion signals "you
//                                don't have to finish writing to save it."
const WRITE_SUGGESTIONS=[
  {title:'Random thoughts'},
  {title:"Skill I'm learning"},
  {title:'Reading notes'},
  {title:"Question I'm chewing on"},
];
// Minimal line-icon SVGs (no decorative emoji — Feynman aesthetic)
const ICON_CHAT=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
const ICON_PEN=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`;
async function renderHomeTworow(enterWrite){
  // Suggested — static list, render immediately
  const sugEl=document.getElementById('home-col-suggested');
  if(sugEl){
    sugEl.innerHTML=WRITE_SUGGESTIONS.map(s=>`<button class="home-col-item" type="button" data-title="${esc(s.title)}"><span class="home-col-ico">${ICON_PEN}</span><span class="home-col-nm">${esc(s.title)}</span></button>`).join('');
    sugEl.querySelectorAll('.home-col-item').forEach(btn=>{
      btn.onclick=()=>enterWrite(btn.dataset.title);
    });
  }
  // Recent corpora — load async, sort by updated_at desc, show top 3.
  const recEl=document.getElementById('home-col-recent');
  if(!recEl)return;
  await loadC();
  if(!_corpora.length){
    recEl.innerHTML=`<div class="home-col-empty">No knowledge bases yet. Create one from the composer above.</div>`;
    return;
  }
  const recent=[..._corpora].sort((a,b)=>(b.updated_at||b.created_at||'').localeCompare(a.updated_at||a.created_at||'')).slice(0,3);
  recEl.innerHTML=recent.map(c=>{
    const dot=cC(c.name||'');
    return `<a class="home-col-item" href="#/corpus/${c.id}"><span class="home-col-ico home-col-dot" style="background:${dot}"></span><span class="home-col-nm">${esc(c.name||'Untitled')}</span></a>`;
  }).join('');
}

/* ══════ COMPILE CANVAS ══════
   Feynman-style split: canvas on left (wide) with the compiled artifact,
   refinement chat on right (380px). Three entry params via hash query:
     ?doc=X              → load concept doc, show canvas
     ?entity=X&corpus=Y  → load entity compiled-truth, show canvas
     ?fresh=1&corpus=Y&topic=... or &entity=...  → run compile first, then show

   The canvas is not an editor — refine chat is the only way to change it.
   Keeps the one-directional Feynman pattern (chat → canvas, not the reverse).
*/

// Minimal markdown→HTML. Scoped to what compile output actually contains:
// headings, paragraphs, bullet lists, bold/italic/inline-code, links.
function _mdToHtml(md){
  if(!md)return'';
  const lines=md.split('\n');
  const out=[];let inList=false,inCode=false,para=[];
  const flushPara=()=>{if(para.length){out.push('<p>'+_inline(para.join(' '))+'</p>');para=[]}};
  const flushList=()=>{if(inList){out.push('</ul>');inList=false}};
  for(let raw of lines){
    if(/^```/.test(raw)){flushPara();flushList();if(inCode){out.push('</code></pre>');inCode=false}else{out.push('<pre><code>');inCode=true}continue}
    if(inCode){out.push(esc(raw));continue}
    const h=raw.match(/^(#{1,4})\s+(.+)$/);
    if(h){flushPara();flushList();out.push('<h'+h[1].length+'>'+_inline(h[2])+'</h'+h[1].length+'>');continue}
    const li=raw.match(/^\s*[-*]\s+(.+)$/);
    if(li){flushPara();if(!inList){out.push('<ul>');inList=true}out.push('<li>'+_inline(li[1])+'</li>');continue}
    if(!raw.trim()){flushPara();flushList();continue}
    para.push(raw);
  }
  flushPara();flushList();if(inCode)out.push('</code></pre>');
  return out.join('\n');
}
function _inline(s){
  return esc(s)
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}

// Split concept doc content into (compiledTruth, timelineLines). Mirrors
// the backend parser so the canvas can show truth-only up top and timeline
// as provenance below. Timeline is evidence-of-sources, not the artifact.
function _splitConcept(content){
  if(!content)return{truth:'',timeline:[]};
  const m=content.match(/\n\s*\n##\s+Timeline\s*\n/);
  if(!m)return{truth:content.trim(),timeline:[]};
  const truth=content.slice(0,m.index).trim();
  const rest=content.slice(m.index+m[0].length).trim();
  const timeline=rest.split('\n').filter(l=>/^\s*-\s+/.test(l)).map(l=>l.replace(/^\s*-\s+/,'').trim());
  return{truth,timeline};
}

// Typewriter reveal: fake streaming. Splits into small chunks (word-ish) and
// appends at a rhythm that looks like LLM token streaming. Returns a stop
// function in case user clicks "Skip to end".
let _revealAbort=null;
function _revealMarkdown(target,md,onDone){
  if(_revealAbort){_revealAbort();_revealAbort=null}
  target.innerHTML='';
  const chunks=md.match(/(\S+\s*|\n)/g)||[md];
  let i=0,buf='',cancelled=false;
  function step(){
    if(cancelled)return;
    if(i>=chunks.length){target.innerHTML=_mdToHtml(md);if(onDone)onDone();return}
    // Write 2 chunks per tick to keep things moving on longer docs
    buf+=chunks[i++]||'';
    if(i<chunks.length)buf+=chunks[i++]||'';
    target.innerHTML=_mdToHtml(buf)+'<span class="cmp-cursor">▍</span>';
    setTimeout(step,24);
  }
  step();
  _revealAbort=()=>{cancelled=true;target.innerHTML=_mdToHtml(md);if(onDone)onDone()};
  return _revealAbort;
}

async function renderCompile(params){
  hideRP();
  const ct=document.getElementById('content');
  ct.classList.remove('content--home','content--corpus');
  ct.classList.add('content--compile');
  const corpusId=params.get('corpus');
  const docId=params.get('doc');
  const entityId=params.get('entity');
  const topic=params.get('topic');
  const fresh=params.get('fresh')==='1';

  // Resolve corpus for the header
  let corpus=null;
  if(corpusId){
    try{const r=await fetch(`${API}/corpora/${corpusId}`);if(r.ok)corpus=await r.json()}catch(e){}
  }
  if(!corpus&&docId){
    try{
      await loadC();
      for(const c of _corpora){const r=await fetch(`${API}/corpora/${c.id}/documents/${docId}`);if(r.ok){corpus=c;break}}
    }catch(e){}
  }

  ct.innerHTML=`<div class="cmp" id="cmp">
    <div class="cmp-canvas" id="cmp-canvas">
      <div class="cmp-hd">
        <button class="cmp-back" id="cmp-back" title="Back"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg></button>
        <div class="cmp-crumb">
          ${corpus?`<a href="#/corpus/${corpus.id}">${esc(corpus.name)}</a> <span class="cmp-crumb-sep">/</span>`:''}
          <span class="cmp-crumb-kind">${entityId?'Entity':'Concept'}</span>
        </div>
        <div class="cmp-hd-right"><span class="cmp-status" id="cmp-status"></span></div>
      </div>
      <article class="cmp-article">
        <h1 class="cmp-title" id="cmp-title">${topic?esc(topic):(entityId?'Loading entity…':'Loading…')}</h1>
        <div class="cmp-meta" id="cmp-meta"></div>
        <div class="cmp-body" id="cmp-body"><div class="cmp-loading">Compiling<span class="cmp-dots"><span>.</span><span>.</span><span>.</span></span></div></div>
        <div class="cmp-sources" id="cmp-sources"></div>
      </article>
    </div>
    <aside class="cmp-chat" id="cmp-chat">
      <div class="cmp-chat-hd">
        <span class="cmp-chat-ttl">Refine</span>
        <span class="cmp-chat-sub">Tell Noos what to change</span>
      </div>
      <div class="cmp-chat-stream" id="cmp-chat-stream"></div>
      <div class="cmp-chat-dock">
        <textarea class="cmp-chat-input" id="cmp-chat-input" rows="2" placeholder="e.g. Make section 2 shorter. Add more detail on pricing." disabled></textarea>
        <button class="cmp-chat-send" id="cmp-chat-send" disabled title="Send"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button>
      </div>
    </aside>
  </div>`;
  document.getElementById('cmp-back').onclick=()=>history.length>1?history.back():(location.hash='#/main');

  // State closure for refine actions
  const state={corpusId:corpus?corpus.id:corpusId,docId:null,entityId:null,title:'',truth:'',timeline:[],sources:[]};

  function applyConceptDoc(doc){
    state.docId=doc.id;state.title=doc.title||'Untitled';
    const parsed=_splitConcept(doc.content||'');
    state.truth=parsed.truth;state.timeline=parsed.timeline;
    let meta={};try{meta=JSON.parse(doc.metadata_json||'{}')}catch(e){}
    state.sources=meta.source_document_ids||[];
    document.getElementById('cmp-title').textContent=state.title;
    const ver=meta.version?`v${meta.version}`:'';
    const when=meta.last_compiled_at?' · '+_fmtRel(meta.last_compiled_at):'';
    document.getElementById('cmp-meta').innerHTML=`<span class="cmp-meta-pill">${ver?ver:'v1'}${when}</span>${state.sources.length?`<span class="cmp-meta-pill">${state.sources.length} source${state.sources.length===1?'':'s'}</span>`:''}`;
    document.getElementById('cmp-status').textContent='';
    _revealMarkdown(document.getElementById('cmp-body'),state.truth,()=>renderSources());
  }
  function applyEntity(ent){
    state.entityId=ent.id;state.title=ent.canonical_name||'Entity';
    state.truth=ent.description||'';
    document.getElementById('cmp-title').textContent=state.title;
    document.getElementById('cmp-meta').innerHTML=`<span class="cmp-meta-pill">${esc(ent.kind||'entity')}</span>${ent.mention_count?`<span class="cmp-meta-pill">${ent.mention_count} mentions</span>`:''}`;
    document.getElementById('cmp-status').textContent='';
    _revealMarkdown(document.getElementById('cmp-body'),state.truth,()=>{});
  }
  function renderSources(){
    const el=document.getElementById('cmp-sources');if(!el)return;
    if(!state.timeline.length){el.innerHTML='';return}
    const items=state.timeline.slice(0,12).map(l=>`<li>${esc(l)}</li>`).join('');
    el.innerHTML=`<div class="cmp-sources-hd">Timeline · ${state.timeline.length} source${state.timeline.length===1?'':'s'}</div><ul class="cmp-sources-list">${items}</ul>`;
  }
  function enableChat(){
    const inp=document.getElementById('cmp-chat-input');const btn=document.getElementById('cmp-chat-send');
    inp.disabled=false;btn.disabled=false;
    const stream=document.getElementById('cmp-chat-stream');
    stream.innerHTML=`<div class="cmp-chat-intro">Compile ready. Ask me to revise — e.g. "make the intro shorter", "add a section on pricing".</div>`;
    inp.focus();
  }
  function pushChat(who,text){
    const stream=document.getElementById('cmp-chat-stream');
    const el=document.createElement('div');el.className='cmp-chat-msg cmp-chat-'+who;
    el.innerHTML=`<div class="cmp-chat-msg-body">${esc(text)}</div>`;
    stream.appendChild(el);stream.scrollTop=stream.scrollHeight;
    return el;
  }
  async function submitRefine(){
    const inp=document.getElementById('cmp-chat-input');
    const instruction=inp.value.trim();if(!instruction)return;
    const btn=document.getElementById('cmp-chat-send');
    inp.value='';inp.disabled=true;btn.disabled=true;
    pushChat('user',instruction);
    const thinking=pushChat('noos','Revising…');
    try{
      let url;
      if(state.docId)url=`${API}/corpora/${state.corpusId}/documents/${state.docId}/refine-compile`;
      else if(state.entityId)url=`${API}/corpora/${state.corpusId}/entities/${state.entityId}/refine-compile`;
      else throw new Error('Nothing to refine');
      const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({instruction})});
      if(!r.ok){
        const d=await r.json().catch(()=>({}));
        if(handleQuotaError(r,d)){thinking.remove();inp.disabled=false;btn.disabled=false;return}
        throw new Error(errMsg(d,'Refine failed'));
      }
      const d=await r.json();
      thinking.querySelector('.cmp-chat-msg-body').textContent='Revised.';
      state.truth=d.compiled_truth||d.compiled_text||state.truth;
      const bodyEl=document.getElementById('cmp-body');
      bodyEl.classList.add('cmp-body-flash');
      _revealMarkdown(bodyEl,state.truth,()=>{setTimeout(()=>bodyEl.classList.remove('cmp-body-flash'),1200)});
      // Update version pill if we have it
      const meta=document.getElementById('cmp-meta');const pill=meta.querySelector('.cmp-meta-pill');
      if(d.version&&pill)pill.textContent=`v${d.version} · just now`;
    }catch(e){
      thinking.querySelector('.cmp-chat-msg-body').textContent='Failed: '+e.message;
    }
    inp.disabled=false;btn.disabled=false;inp.focus();
  }
  document.getElementById('cmp-chat-send').onclick=submitRefine;
  document.getElementById('cmp-chat-input').addEventListener('keydown',e=>{
    if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();submitRefine()}
    else if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitRefine()}
  });

  // Data fetch paths
  try{
    if(fresh&&topic&&corpusId){
      document.getElementById('cmp-status').textContent='Compiling…';
      const r=await fetch(`${API}/corpora/${corpusId}/compile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic,top_k:10})});
      if(!r.ok){
        const d=await r.json().catch(()=>({}));
        if(handleQuotaError(r,d))return;
        throw new Error(errMsg(d,'Compile failed'));
      }
      const d=await r.json();
      // Server returns the full doc; swap URL so reload works and Back lands cleanly
      history.replaceState(null,'',`#/compile?doc=${d.id}`);
      applyConceptDoc(d);
      enableChat();
    } else if(fresh&&entityId&&corpusId){
      document.getElementById('cmp-status').textContent='Compiling…';
      const r=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}/compile`,{method:'POST'});
      if(!r.ok){
        const d=await r.json().catch(()=>({}));
        if(handleQuotaError(r,d))return;
        throw new Error(errMsg(d,'Compile failed'));
      }
      // Fetch the entity back to get kind/mention_count for display
      const er=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}`);
      const ent=await er.json();
      history.replaceState(null,'',`#/compile?entity=${entityId}&corpus=${corpusId}`);
      applyEntity(ent);
      enableChat();
    } else if(docId){
      // Need corpus id to call the doc endpoint — try each user corpus
      await loadC();
      let doc=null,cid=state.corpusId;
      if(cid){const r=await fetch(`${API}/corpora/${cid}/documents/${docId}`);if(r.ok)doc=await r.json()}
      if(!doc){
        for(const c of _corpora){
          const r=await fetch(`${API}/corpora/${c.id}/documents/${docId}`);
          if(r.ok){doc=await r.json();cid=c.id;break}
        }
      }
      if(!doc)throw new Error('Concept not found');
      state.corpusId=cid;
      applyConceptDoc(doc);
      enableChat();
    } else if(entityId&&corpusId){
      const r=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}`);
      if(!r.ok)throw new Error('Entity not found');
      const ent=await r.json();
      applyEntity(ent);
      enableChat();
    } else {
      document.getElementById('cmp-body').innerHTML='<div class="cmp-empty">Nothing to compile — pick a target from the home page.</div>';
      document.getElementById('cmp-status').textContent='';
    }
  } catch(e){
    document.getElementById('cmp-body').innerHTML=`<div class="cmp-empty cmp-empty-err">${esc(e.message||'Compile failed')}</div>`;
    document.getElementById('cmp-status').textContent='';
  }
}

function _fmtRel(iso){
  if(!iso)return'';
  const t=new Date(iso).getTime();if(!t)return'';
  const d=(Date.now()-t)/1000;
  if(d<60)return'just now';
  if(d<3600)return Math.floor(d/60)+'m ago';
  if(d<86400)return Math.floor(d/3600)+'h ago';
  if(d<86400*7)return Math.floor(d/86400)+'d ago';
  return new Date(iso).toLocaleDateString('en-US',{month:'short',day:'numeric'});
}

function addLine(container,type,text,id,line){
  const el=document.createElement('div');
  if(id)el.id=id;
  const ln=line||{};
  if(type==='prompt'){el.className='term-line term-prompt';el.innerHTML='<span class="term-prompt-text">'+esc(text||ln.text||'')+'</span>'}
  else if(type==='resp'){
    el.className='term-line term-resp';
    const content=text||ln.text||'';
    // Save button appended to every Noos reply — saves the message as a
    // user_original note, hydrating chat-generated knowledge into the corpus.
    el.innerHTML=noosHd()+'<div class="term-resp-body"></div><div class="term-resp-actions"><button class="term-save" type="button" title="Save to corpus"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Save</button></div>';
    el.querySelector('.term-resp-body').textContent=content;
    el.querySelector('.term-save').dataset.content=content;
  }
  else if(type==='thinking'){el.className='term-line term-thinking';el.innerHTML='<span>'+esc(text||ln.text||'')+'</span>'}
  else if(type==='hint'){el.className='term-line term-hint';el.innerHTML='<span>'+esc(ln.text||'')+'</span>'}
  else if(type==='option'){el.className='term-line term-option';el.textContent=ln.text||'';
    el.onclick=()=>{const input=document.getElementById('term-input');if(input&&ln.value){input.value=ln.value;input.focus();setTimeout(()=>input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})),50)}}}
  else if(type==='card'){el.className='term-card';el.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center"><span class="term-card-lbl">${esc(ln.label||'')}</span><span class="term-status" style="color:${TERM_STATUS_C[ln.status]||'var(--tx3)'}">${esc(ln.status||'')}</span></div><div class="term-card-det">${esc(ln.detail||'')}</div>${ln.val?`<div class="term-card-val">${esc(ln.val)}</div>`:''}`;
    if(ln.corpus_id){el.style.cursor='pointer';el.onclick=()=>{location.hash='#/corpus/'+ln.corpus_id}}}
  else if(type==='search_result'){el.className='sr-card';el.innerHTML=`<div class="sr-top"><span class="sr-score">${((ln.score||0)*100).toFixed(0)}%</span><span class="sr-title">${esc(ln.title||'')}</span>${ln.source?`<span class="sr-source">${esc(ln.source)}</span>`:''}</div><div class="sr-text">${esc(ln.text||'')}</div>`}
  else return;
  container.appendChild(el);
  const sc=document.getElementById('term-scroll');
  if(sc)sc.scrollTop=sc.scrollHeight;
}

/* ══════ TERMINAL UPLOAD ══════
   Unified "put external stuff in" door — Files / URL / Paste / Archive tabs.
   Each tab resolves to its own ingest endpoint but the user sees one entry:
     - Files   → POST /corpora/:id/upload (multipart, files)
     - URL     → POST /corpora/:id/ingest-url
     - Paste   → POST /corpora/:id/upload (multipart, synthesized .md)
     - Archive → POST /corpora/:id/import/{twitter|notion}
   Call sites pass `defaultCorpus` so the home page's chip selection carries. */
function showTermUpload(output,input,defaultCorpus){
  const wrap=document.createElement('div');wrap.className='term-upload-wrap';
  let _uFiles=[];let _tab='files';
  wrap.innerHTML=`<div class="term-upload-tabs"><button class="term-upload-tab active" data-tab="files" type="button">Files</button><button class="term-upload-tab" data-tab="url" type="button">URL</button><button class="term-upload-tab" data-tab="paste" type="button">Paste</button><button class="term-upload-tab" data-tab="archive" type="button">Archive</button></div><div class="term-upload-body" id="tu-body"></div>`;
  output.appendChild(wrap);
  const sc=document.getElementById('term-scroll');if(sc)sc.scrollTop=sc.scrollHeight;
  const body=wrap.querySelector('#tu-body');
  const tabsEl=wrap.querySelectorAll('.term-upload-tab');

  // Shared: resolve a corpus id. Read _homeScope FRESH on each call so chip
  // changes between open-panel and submit are respected. Fallbacks: single
  // corpus → auto-create → inline picker.
  async function resolveCorpus(){
    let cid=_homeScope||defaultCorpus||null;
    if(cid)return cid;
    await loadC();
    if(_corpora.length===1)return _corpora[0].id;
    if(_corpora.length===0){
      try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});const c=await r.json();await loadC();return c.id}
      catch(e){return null}
    }
    return await pickCorpusInline(output);
  }
  function cancelAndReturn(){
    wrap.remove();
    const home=document.getElementById('home');
    if(home&&!output.children.length)home.classList.remove('home--active');
    if(input)input.focus();
  }
  function renderFiles(){
    body.innerHTML=`<div class="term-upload-dz" id="tu-dz"><input type="file" id="tu-fi" multiple accept=".md,.txt,.text,.html,.htm,.pdf,.docx,.csv,.json,.jsonl" hidden /><div class="term-upload-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--tx3)" stroke-width="1.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></div><div class="term-upload-txt">Drop files here, or <span class="term-upload-browse">browse</span></div><div class="term-upload-formats">PDF · Markdown · DOCX · TXT · CSV · JSON</div></div><div class="term-upload-list" id="tu-list"></div><div class="term-upload-origin"><label for="tu-sk">Origin</label><select id="tu-sk"><option value="user_original" selected>My original content</option><option value="external_public">Public external reference</option><option value="external_subscription">Subscription / paid external</option></select></div><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Upload</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
    const dz=body.querySelector('#tu-dz'),fi=body.querySelector('#tu-fi'),list=body.querySelector('#tu-list');
    const goBtn=body.querySelector('#tu-go'),cancelBtn=body.querySelector('#tu-cancel');
    function refreshList(){
      list.innerHTML=_uFiles.map((f,i)=>`<div class="term-upload-file"><span>${esc(f.name)}</span><span style="display:flex;align-items:center;gap:8px"><span class="term-upload-size">${(f.size/1024).toFixed(1)}KB</span><button class="term-upload-remove" data-idx="${i}" title="Remove">&times;</button></span></div>`).join('');
      list.querySelectorAll('.term-upload-remove').forEach(btn=>{btn.onclick=e=>{e.stopPropagation();_uFiles.splice(parseInt(btn.dataset.idx),1);refreshList()}});
      goBtn.disabled=!_uFiles.length;
    }
    function addFiles(fl){for(const f of fl)_uFiles.push(f);refreshList()}
    refreshList();
    dz.onclick=()=>fi.click();
    dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag-over')};
    dz.ondragleave=()=>dz.classList.remove('drag-over');
    dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag-over');addFiles(e.dataTransfer.files)};
    fi.onchange=()=>{addFiles(fi.files);fi.value=''};
    cancelBtn.onclick=cancelAndReturn;
    goBtn.onclick=async()=>{
      if(!_uFiles.length)return;
      goBtn.disabled=true;goBtn.textContent='Uploading...';cancelBtn.style.display='none';
      const cid=await resolveCorpus();
      if(!cid){wrap.remove();addLine(output,'resp','No corpus selected.');if(input)input.focus();return}
      const fd=new FormData();
      for(const f of _uFiles)fd.append('files',f);
      fd.append('source_kind',body.querySelector('#tu-sk')?.value||'user_original');
      try{
        const r=await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){addLine(output,'resp','Upload failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        addLine(output,'resp',`Added ${d.uploaded||_uFiles.length} file${_uFiles.length>1?'s':''}`);
        // Fire-and-forget processing. Debouncer coalesces consecutive ingests
        // into one index run; corpus detail page has a Re-process button for
        // recovery if anything ever fails silently.
        ensureIndexed(cid);
        const corpus=_corpora.find(c=>c.id===cid);
        addLine(output,'card',null,null,{type:'card',label:'Files Added',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:`${_uFiles.length} file${_uFiles.length>1?'s':''} added — ingesting in background`,corpus_id:cid});
        await loadC();
      }catch(e){wrap.remove();addLine(output,'resp','Upload failed: '+e.message)}
      if(input)input.focus();
    };
  }
  function renderURL(){
    body.innerHTML=`<div class="term-upload-txt-hint">Paste a web page URL — one-time snapshot. For a source that keeps flowing, use Add RSS instead.</div><input type="url" id="tu-url" placeholder="https://example.com/article" class="term-upload-input" /><div class="term-upload-rss-hint" id="tu-rss-hint" style="display:none"><span>This looks like a feed URL —</span><button type="button" class="tu-rss-switch" id="tu-rss-switch">use Add RSS</button></div><div class="term-upload-origin"><label for="tu-sk">Origin</label><select id="tu-sk"><option value="external_public" selected>Public external reference</option><option value="external_subscription">Subscription / paid external</option><option value="user_original">My original content</option></select></div><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Import page</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
    const urlEl=body.querySelector('#tu-url'),goBtn=body.querySelector('#tu-go'),cancelBtn=body.querySelector('#tu-cancel');
    const rssHint=body.querySelector('#tu-rss-hint');
    urlEl.focus();
    // RSS detection — heuristic match on URL pattern. Not definitive (plenty
    // of feeds live at non-obvious paths) but catches 90% of common cases.
    const RSS_PATTERN=/(\/feed\/?|\/rss\/?|\/atom\/?|\.rss$|\.atom$|\.xml$|\/feed\.xml|\/rss\.xml|\/index\.xml)/i;
    urlEl.oninput=()=>{
      const v=urlEl.value.trim();
      goBtn.disabled=!v;
      rssHint.style.display=v&&RSS_PATTERN.test(v)?'':'none';
    };
    urlEl.onkeydown=e=>{if(e.key==='Enter'&&!goBtn.disabled){e.preventDefault();goBtn.click()}};
    body.querySelector('#tu-rss-switch').onclick=()=>{
      const url=urlEl.value.trim();
      wrap.remove();
      const home=document.getElementById('home');
      if(home)home.classList.add('home--active');
      showTermConnectRSS(output,input,_homeScope||defaultCorpus);
      // Pre-fill the RSS panel with what they had typed
      setTimeout(()=>{const rssUrl=document.getElementById('tu-url');if(rssUrl)rssUrl.value=url;const goBtn=document.getElementById('tu-go');if(goBtn)goBtn.disabled=!url},50);
    };
    cancelBtn.onclick=cancelAndReturn;
    goBtn.onclick=async()=>{
      const url=urlEl.value.trim();if(!url)return;
      goBtn.disabled=true;goBtn.textContent='Importing...';cancelBtn.style.display='none';
      const cid=await resolveCorpus();
      if(!cid){wrap.remove();addLine(output,'resp','No corpus selected.');if(input)input.focus();return}
      const sk=body.querySelector('#tu-sk')?.value||'external_public';
      try{
        const r=await fetch(`${API}/corpora/${cid}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,source_kind:sk})});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){addLine(output,'resp','Import failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        addLine(output,'resp',`Imported: "${d.title||d.name||url}"`);
        ensureIndexed(cid);
        const corpus=_corpora.find(c=>c.id===cid);
        addLine(output,'card',null,null,{type:'card',label:'URL Imported',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:urlEl.value||'',corpus_id:cid});
        await loadC();
      }catch(e){wrap.remove();addLine(output,'resp','Import failed: '+e.message)}
      if(input)input.focus();
    };
  }
  function renderPaste(){
    body.innerHTML=`<div class="term-upload-txt-hint">Paste any text — the first line becomes the title. Markdown is supported.</div><textarea id="tu-paste" class="term-upload-input term-upload-textarea" placeholder="Paste article, notes, transcript…" rows="7"></textarea><div class="term-upload-origin"><label for="tu-sk">Origin</label><select id="tu-sk"><option value="external_public" selected>Public external reference</option><option value="user_original">My original content</option><option value="external_subscription">Subscription / paid external</option></select></div><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Save</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
    const taEl=body.querySelector('#tu-paste'),goBtn=body.querySelector('#tu-go'),cancelBtn=body.querySelector('#tu-cancel');
    taEl.focus();
    taEl.oninput=()=>{goBtn.disabled=!taEl.value.trim()};
    cancelBtn.onclick=cancelAndReturn;
    goBtn.onclick=async()=>{
      const text=taEl.value.trim();if(!text)return;
      goBtn.disabled=true;goBtn.textContent='Saving...';cancelBtn.style.display='none';
      const cid=await resolveCorpus();
      if(!cid){wrap.remove();addLine(output,'resp','No corpus selected.');if(input)input.focus();return}
      const firstLine=(text.split('\n').find(l=>l.trim())||'').replace(/^#+\s*/,'').trim();
      const title=firstLine.slice(0,80)||('Pasted '+new Date().toLocaleDateString('en-US',{month:'short',day:'numeric'}));
      const fd=new FormData();
      fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+text],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-').slice(0,60)+'.md');
      fd.append('source_kind',body.querySelector('#tu-sk')?.value||'external_public');
      try{
        const r=await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){addLine(output,'resp','Save failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        addLine(output,'resp',`Saved: "${title}"`);
        ensureIndexed(cid);
        const corpus=_corpora.find(c=>c.id===cid);
        addLine(output,'card',null,null,{type:'card',label:'Text Saved',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:title,corpus_id:cid});
        await loadC();
      }catch(e){wrap.remove();addLine(output,'resp','Save failed: '+e.message)}
      if(input)input.focus();
    };
  }
  function renderArchive(){
    body.innerHTML=`<div class="term-upload-txt-hint">Import a full archive export. Every item lands as your own content.</div><div class="term-upload-archive-picks"><label class="term-upload-archive-pick"><input type="radio" name="arc-kind" value="twitter" checked /><span>Twitter / X</span><span class="term-upload-archive-sub">ZIP from twitter.com/settings/download_your_data</span></label><label class="term-upload-archive-pick"><input type="radio" name="arc-kind" value="notion" /><span>Notion</span><span class="term-upload-archive-sub">ZIP from Settings → Data export (Markdown &amp; CSV)</span></label></div><input type="file" id="tu-fi" accept=".zip" class="term-upload-input" /><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Import archive</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
    const fi=body.querySelector('#tu-fi'),goBtn=body.querySelector('#tu-go'),cancelBtn=body.querySelector('#tu-cancel');
    fi.onchange=()=>{goBtn.disabled=!fi.files.length};
    cancelBtn.onclick=cancelAndReturn;
    goBtn.onclick=async()=>{
      if(!fi.files.length)return;
      const kind=(body.querySelector('input[name="arc-kind"]:checked')||{}).value||'twitter';
      const label=kind==='twitter'?'Twitter / X':'Notion';
      goBtn.disabled=true;goBtn.textContent='Importing...';cancelBtn.style.display='none';
      const cid=await resolveCorpus();
      if(!cid){wrap.remove();addLine(output,'resp','No corpus selected.');if(input)input.focus();return}
      const fd=new FormData();fd.append('file',fi.files[0]);
      try{
        const r=await fetch(`${API}/corpora/${cid}/import/${kind}`,{method:'POST',body:fd});
        const d=await r.json().catch(()=>({}));
        wrap.remove();
        if(!r.ok){addLine(output,'resp','Import failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        const corpus=_corpora.find(c=>c.id===cid);
        addLine(output,'resp',`Imported ${d.imported||0} of ${d.total||0} items${d.skipped?` (${d.skipped} skipped)`:''}.`);
        // Archive import used to skip indexing — newly imported items stayed
        // un-searchable until something else triggered /index. Fix: debounced
        // trigger here so the archive actually becomes usable.
        ensureIndexed(cid);
        addLine(output,'card',null,null,{type:'card',label:`${label} imported`,status:'READY',detail:corpus?corpus.name:'My Knowledge',val:`${d.imported||0} items`,corpus_id:cid});
        await loadC();
      }catch(e){wrap.remove();addLine(output,'resp','Import failed: '+e.message)}
      if(input)input.focus();
    };
  }
  function setTab(t){
    _tab=t;
    tabsEl.forEach(el=>el.classList.toggle('active',el.dataset.tab===t));
    if(t==='files')renderFiles();
    else if(t==='url')renderURL();
    else if(t==='paste')renderPaste();
    else if(t==='archive')renderArchive();
  }
  tabsEl.forEach(el=>el.onclick=()=>setTab(el.dataset.tab));
  setTab('files');
}

/* ══════ CONNECT RSS FEED ══════
   Persistent source — the backend enrichment loop re-polls registered feeds,
   so this is the one connector that actually keeps flowing. */
function showTermConnectRSS(output,input,defaultCorpus){
  const tier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  const footer=tier==='pro'
    ? `<div style="font-family:inherit;font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Noos watches this feed and pulls in new posts automatically.</div>`
    : (_authUser
        ? `<div style="font-family:inherit;font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Free: Noos reads these now. <a href="#" data-pro-link="auto-add" style="color:#3b82f6;text-decoration:none">Upgrade to Pro</a> to keep this feed growing on its own.</div>`
        : `<div style="font-family:inherit;font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Noos reads these now. Re-add later to pull new posts.</div>`);
  const wrap=document.createElement('div');wrap.className='term-upload-wrap';
  wrap.innerHTML=`<div style="font-family:inherit;font-size:13px;color:var(--tx);margin-bottom:4px;font-weight:600">Connect a feed</div><div style="font-family:inherit;font-size:12px;color:var(--tx2);margin-bottom:12px;line-height:1.55">Noos reads every post and adds it to your corpus — you can chat about it right after.</div><input type="url" id="tu-url" placeholder="https://example.com/feed.xml" style="width:100%;padding:10px 12px;border:1px solid var(--brd);border-radius:8px;background:var(--bg);color:var(--tx);font-family:var(--mono);font-size:12px;outline:none" /><div style="display:flex;gap:8px;align-items:center;margin-top:10px;font-family:inherit;font-size:11px;color:var(--tx3)"><label for="tu-max">Max items</label><input type="number" id="tu-max" value="25" min="1" max="100" style="width:70px;padding:5px 8px;border:1px solid var(--brd);border-radius:6px;background:var(--bg);color:var(--tx);font-family:var(--mono);font-size:11px;outline:none" /></div>${footer}<div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Add feed</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
  output.appendChild(wrap);
  const sc=document.getElementById('term-scroll');if(sc)sc.scrollTop=sc.scrollHeight;
  const urlEl=wrap.querySelector('#tu-url'),maxEl=wrap.querySelector('#tu-max'),goBtn=wrap.querySelector('#tu-go'),cancelBtn=wrap.querySelector('#tu-cancel');
  urlEl.focus();
  urlEl.oninput=()=>{goBtn.disabled=!urlEl.value.trim()};
  urlEl.onkeydown=e=>{if(e.key==='Enter'&&!goBtn.disabled){e.preventDefault();goBtn.click()}};
  wrap.querySelector('[data-pro-link]')?.addEventListener('click',ev=>{ev.preventDefault();showProModal('Auto-add is a Pro feature')});
  cancelBtn.onclick=()=>{
    wrap.remove();
    const home=document.getElementById('home');
    if(home&&!output.children.length)home.classList.remove('home--active');
    if(input)input.focus();
  };
  goBtn.onclick=async()=>{
    const url=urlEl.value.trim();if(!url)return;
    const maxItems=parseInt(maxEl.value)||25;
    goBtn.disabled=true;goBtn.textContent='Fetching feed...';cancelBtn.style.display='none';
    // Read _homeScope fresh — user may have changed the chip after opening.
    let cid=_homeScope||defaultCorpus||null;
    if(!cid){
      await loadC();
      if(_corpora.length===1){cid=_corpora[0].id}
      else if(_corpora.length===0){
        try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});const c=await r.json();cid=c.id;await loadC()}
        catch(e){addLine(output,'resp','Failed to create corpus.');wrap.remove();if(input)input.focus();return}
      } else {
        const picked=await pickCorpusInline(output);
        if(!picked){wrap.remove();if(input)input.focus();return}
        cid=picked;
      }
    }
    try{
      const r=await fetch(`${API}/corpora/${cid}/ingest-feed`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feed_url:url,max_items:maxItems})});
      const d=await r.json();
      if(handleQuotaError(r,d)){wrap.remove();if(input)input.focus();return}
      wrap.remove();
      if(!r.ok){addLine(output,'resp','Add feed failed: '+(d.detail||r.statusText));if(input)input.focus();return}
      const corpus=_corpora.find(c=>c.id===cid);
      const tierNow=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
      const tail=tierNow==='pro'?" Noos will check back every hour.":"";
      addLine(output,'resp',`Noos read ${d.ingested||0} new post${d.ingested===1?'':'s'} from this feed.${tail}`);
      addLine(output,'card',null,null,{type:'card',label:'Feed connected',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:url,corpus_id:cid});
      await loadC();
    }catch(e){wrap.remove();addLine(output,'resp','Add feed failed: '+e.message)}
    if(input)input.focus();
  };
}

/* ══════ CHATS PAGE ══════ */
function renderChats(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="mc-wrap mc-wrap--chats">
    <div class="mc-top"><h1 class="mc-title">Chats</h1></div>
    <div class="mc-search-wrap">
      <svg class="mc-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" class="mc-search" id="chats-search" placeholder="Search chats…" />
    </div>
    <div class="mc-sub"><span class="mc-sub-label">${_chatSessions.length} ${_chatSessions.length===1?'chat':'chats'}</span></div>
    <div id="chats-list-content" style="flex:1;overflow:hidden"></div>
  </div>`;
  const list=document.getElementById('chats-list-content');
  if(!_chatSessions.length){list.innerHTML='<div class="empty" style="margin-top:60px">No chats yet. Start one from any corpus.</div>';return}
  list.className='chats-list';
  list.innerHTML=_chatSessions.map(c=>{
    const corpus=_corpora.find(x=>x.id===c.corpus_id);
    const corpusName=corpus?esc(corpus.name):'';
    const ago=_timeAgo(c.updated_at);
    return`<div class="chats-row" data-id="${c.id}" data-cid="${c.corpus_id}">
      <div class="chats-row-body">
        <div class="chats-row-title">${esc(c.title||'Untitled')}</div>
        <div class="chats-row-meta">${corpusName?'<span class="chats-row-meta-corpus">'+corpusName+'</span>':''}${ago?'<span>Last active '+ago+'</span>':''}</div>
      </div>
      <button class="chats-row-del" data-sid="${c.id}" title="Delete chat" aria-label="Delete chat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg></button>
    </div>`;
  }).join('');
  list.querySelectorAll('.chats-row').forEach(row=>{
    row.addEventListener('click',e=>{
      if(e.target.closest('.chats-row-del'))return;
      location.hash=`#/corpus/${row.dataset.cid}?session=${row.dataset.id}`;
    });
  });
  list.querySelectorAll('.chats-row-del').forEach(btn=>{
    btn.onclick=async e=>{e.stopPropagation();await _deleteSession(btn.dataset.sid)};
  });
  document.getElementById('chats-search').addEventListener('input',e=>{
    const q=e.target.value.toLowerCase();
    document.querySelectorAll('.chats-row').forEach(row=>{
      const title=row.querySelector('.chats-row-title')?.textContent.toLowerCase()||'';
      const corpus=row.querySelector('.chats-row-meta-corpus')?.textContent.toLowerCase()||'';
      row.style.display=(title.includes(q)||corpus.includes(q))?'':'none';
    });
  });
}

/* ══════ MY CORPORA ══════ */
let _mcView='list';
function renderMyCorpora(){
  hideRP();const ct=document.getElementById('content'),host=location.origin;ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="mc-wrap">
    <div class="mc-top">
      <h1 class="mc-title">Corpora</h1>
      <button class="mc-new-btn" id="mc-new-btn"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> New</button>
    </div>
    <div class="mc-search-wrap">
      <svg class="mc-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" class="mc-search" id="mc-search" placeholder="Search corpora…" />
    </div>
    <div class="mc-sub"><span class="mc-sub-label">${_corpora.length} corpora</span><div class="mc-toggle"><button class="${_mcView==='list'?'active':''}" id="mc-list-btn">List</button><button class="${_mcView==='graph'?'active':''}" id="mc-graph-btn">Network</button></div></div>
    <div id="mc-content" style="flex:1;overflow:hidden"></div>
  </div>`;
  document.getElementById('mc-new-btn').onclick=()=>{_termCtx={};location.hash='#/main';if(location.hash==='#/main')renderHome()};
  document.getElementById('mc-list-btn').onclick=()=>{_mcView='list';renderMyCorpora()};
  document.getElementById('mc-graph-btn').onclick=()=>{_mcView='graph';renderMyCorpora()};
  if(_mcView==='list')renderMCList(host);else renderMCGraph();
  document.getElementById('mc-search').addEventListener('input',e=>{
    const q=e.target.value.toLowerCase();
    document.querySelectorAll('.mc-card').forEach(card=>{
      const name=card.querySelector('.mc-card-name')?.textContent.toLowerCase()||'';
      const desc=card.querySelector('.mc-card-desc')?.textContent.toLowerCase()||'';
      card.style.display=(name.includes(q)||desc.includes(q))?'':'none';
    });
  });
}

function _timeAgo(iso){
  if(!iso)return'';
  const d=new Date(iso),now=new Date(),s=Math.floor((now-d)/1000);
  if(s<60)return'just now';if(s<3600)return Math.floor(s/60)+' min ago';
  if(s<86400)return Math.floor(s/3600)+' hours ago';
  const days=Math.floor(s/86400);
  if(days===1)return'yesterday';if(days<30)return days+' days ago';
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:d.getFullYear()!==now.getFullYear()?'numeric':undefined});
}

// Owner-view badge: describes the corpus's access posture from the creator's
// perspective. "Public" is the default and renders nothing (no signal to add).
// Paid shows concrete pricing ($X.XX/query) when configured, falling back to
// "Monetized" when access_level='paid' but pricing_json is missing/invalid.
function _mcBadge(c){
  const al=c.access_level||'public';
  if(al==='private')return'<span class="mc-badge mc-badge-private">Private</span>';
  if(al==='token')return'<span class="mc-badge mc-badge-token">Token-gated</span>';
  if(al==='paid'){
    let p=null;
    if(c.pricing_json){try{p=typeof c.pricing_json==='string'?JSON.parse(c.pricing_json):c.pricing_json}catch(e){}}
    if(p&&p.amount_cents){
      const dollars=(p.amount_cents/100).toFixed(2);
      const sym=(p.currency||'usd').toLowerCase()==='usd'?'$':((p.currency||'').toUpperCase()+' ');
      const unit=p.type==='per_query'?'/query':' one-time';
      return`<span class="mc-badge mc-badge-paid">${sym}${dollars}${unit}</span>`;
    }
    return'<span class="mc-badge mc-badge-paid">Monetized</span>';
  }
  return'';
}

function renderMCList(host){
  const el=document.getElementById('mc-content');
  if(!_corpora.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet. Click <strong>+ New</strong> to add your knowledge.</div>';return}
  el.className='mc-list';
  el.innerHTML=_corpora.map(c=>{
    const tg=Array.isArray(c.tags)?c.tags:[];
    const desc=c.description||'';
    const updatedLabel=_timeAgo(c.updated_at);
    const stats=[];
    if(c.document_count){stats.push('<span class="mc-meta-item">'+c.document_count+' '+(c.document_count===1?'source':'sources')+'</span>')}
    else{stats.push('<span class="mc-meta-item mc-meta-empty">Empty</span>')}
    if(c.word_count){stats.push('<span class="mc-meta-sep">·</span><span class="mc-meta-item">'+c.word_count.toLocaleString()+' words</span>')}
    const cc=c.concept_count||0, ec=c.entity_count||0;
    if(cc){stats.push('<span class="mc-meta-sep">·</span><span class="mc-meta-item mc-meta-compiled">'+cc+' '+(cc===1?'concept':'concepts')+'</span>')}
    if(ec){stats.push('<span class="mc-meta-sep">·</span><span class="mc-meta-item">'+ec+' '+(ec===1?'entity':'entities')+'</span>')}
    if(c.document_count&&!cc&&!ec){stats.push('<span class="mc-meta-sep">·</span><span class="mc-meta-item mc-meta-empty">Not compiled</span>')}
    const tagsRow=tg.length?'<div class="mc-card-tags">'+tg.slice(0,5).map(t=>'<span class="mc-meta-tag">'+esc(t)+'</span>').join('')+'</div>':'';
    const descRow=desc?'<div class="mc-card-desc">'+esc(desc)+'</div>':(c.document_count?'':'<div class="mc-card-desc-empty">No description yet — add sources to begin.</div>');
    return`<div class="mc-card" data-id="${c.id}">
      <div class="mc-card-body">
        <div class="mc-card-top"><a class="mc-card-name" href="#/corpus/${c.id}">${esc(c.name)}</a>${_mcBadge(c)}</div>
        ${descRow}
        ${tagsRow}
        <div class="mc-card-meta">${stats.join('')}${updatedLabel?'<span class="mc-meta-item mc-meta-updated">Updated '+updatedLabel+'</span>':''}</div>
      </div>
      <div class="mc-card-actions"><button class="mc-card-more" data-id="${c.id}">···</button><div class="mc-menu hidden" data-for="${c.id}"><button class="mc-menu-item" data-action="rename" data-id="${c.id}">Rename</button><button class="mc-menu-item" data-action="export" data-id="${c.id}">Export</button><button class="mc-menu-item mc-menu-danger" data-action="delete" data-id="${c.id}">Delete</button></div></div>
    </div>`}).join('');
  el.querySelectorAll('.mc-card').forEach(card=>{card.addEventListener('click',e=>{if(e.target.closest('.mc-card-actions')||e.target.closest('.mc-card-name'))return;location.hash='#/corpus/'+card.dataset.id})});
  el.querySelectorAll('.mc-card-more').forEach(btn=>{btn.onclick=e=>{e.stopPropagation();el.querySelectorAll('.mc-menu').forEach(m=>m.classList.add('hidden'));const menu=el.querySelector(`.mc-menu[data-for="${btn.dataset.id}"]`);if(menu)menu.classList.toggle('hidden')}});
  document.addEventListener('click',()=>{el.querySelectorAll('.mc-menu').forEach(m=>m.classList.add('hidden'))},{once:true});
  el.querySelectorAll('.mc-menu-item').forEach(item=>{item.onclick=async e=>{
    e.stopPropagation();const action=item.dataset.action,cid=item.dataset.id;
    el.querySelectorAll('.mc-menu').forEach(m=>m.classList.add('hidden'));
    if(action==='rename'){const c=_corpora.find(x=>x.id===cid);const name=prompt('Rename corpus:',c?.name||'');if(!name)return;
      try{await fetch(`${API}/corpora/${cid}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});await loadC();renderMyCorpora()}catch(e){}}
    else if(action==='delete'){const c=_corpora.find(x=>x.id===cid);if(!confirm(`Delete "${c?.name||cid}" and all its documents? This cannot be undone.`))return;
      try{await fetch(`${API}/corpora/${cid}`,{method:'DELETE'});await loadC();renderMyCorpora()}catch(e){}}
    else if(action==='export'){window.open(`${API}/corpora/${cid}/export`,'_blank')}
  }});
}

function renderMCGraph(){
  const el=document.getElementById('mc-content');el.innerHTML='';el.className='mc-graph';
  if(!_corpora.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet.</div>';return}
  drawGraphIn(el,_corpora);
}

/* ══════ NETWORK ══════ */
function renderNet(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="nv-wrap"><canvas id="nv-cv" class="nv-canvas"></canvas><div class="nv-tt hidden" id="nv-tt"></div></div>`;

  const cv=document.getElementById('nv-cv');if(!cv)return;
  if(!_corpora.length){const w=cv.parentElement;const e=document.createElement('div');e.className='empty';e.style.cssText='position:absolute;top:40%;left:50%;transform:translate(-50%,-50%)';e.innerHTML='The Noosphere is empty.<br>Click <strong>+ New</strong> to add knowledge.';w.appendChild(e);return}
  drawGraphIn(cv.parentElement,_corpora,cv);
}

/* ══════ EXPLORE (NETWORK GRAPH + DIRECTORY) ══════ */
async function renderExplore(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  const params=new URLSearchParams(location.hash.split('?')[1]||'');
  const q=params.get('q')||'';
  ct.innerHTML=`<div class="explore-page" style="max-width:960px;margin:0 auto;padding:24px 20px">
    <div class="nv-wrap" style="height:320px;position:relative;border-radius:12px;border:1px solid var(--brd);margin-bottom:24px;overflow:hidden;background:var(--bg2)">
      <canvas id="nv-cv" class="nv-canvas" style="width:100%;height:100%"></canvas>
      <div class="nv-tt hidden" id="nv-tt"></div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:20px">
      <input id="explore-q" type="text" placeholder="Search by topic, author, or tag..." value="${esc(q)}" style="flex:1;padding:10px 14px;border-radius:8px;border:1px solid var(--brd);background:var(--bg2);color:var(--tx);font-size:14px">
      <button id="explore-go" style="padding:10px 20px;border-radius:8px;background:var(--btnBg);color:var(--btnC);border:none;cursor:pointer;font-size:14px">Search</button>
    </div>
    <div id="explore-results" style="display:flex;flex-direction:column;gap:12px"></div>
  </div>`;
  // Draw the network graph in the top section
  const cv=document.getElementById('nv-cv');
  if(cv&&_corpora.length){drawGraphIn(cv.parentElement,_corpora,cv)}
  const inp=document.getElementById('explore-q');
  const go=()=>{const v=inp.value.trim();if(v)location.hash='#/explore?q='+encodeURIComponent(v);doExploreSearch(v)};
  document.getElementById('explore-go').onclick=go;
  inp.onkeydown=e=>{if(e.key==='Enter')go()};
  if(q)doExploreSearch(q);else doExploreBrowse();
}
async function doExploreSearch(q){
  const el=document.getElementById('explore-results');
  el.innerHTML='<div style="color:var(--muted)">Searching...</div>';
  try{
    const r=await fetch(`${API}/network/search?q=${encodeURIComponent(q)}&limit=30`);
    const d=await r.json();
    if(!d.results||!d.results.length){el.innerHTML='<div style="color:var(--muted)">No knowledge bases found for this query.</div>';return}
    el.innerHTML=d.results.map(c=>_exploreCard(c)).join('');
  }catch(e){el.innerHTML='<div style="color:var(--err)">Search failed.</div>'}
}
async function doExploreBrowse(){
  const el=document.getElementById('explore-results');
  el.innerHTML='<div style="color:var(--muted)">Loading...</div>';
  try{
    const r=await fetch(`${API}/corpora`);
    const all=await r.json();
    const pub=all.filter(c=>c.access_level!=='private');
    if(!pub.length){el.innerHTML='<div style="color:var(--muted)">No public knowledge bases yet. Be the first — click <strong>+ New</strong>.</div>';return}
    el.innerHTML=pub.map(c=>_exploreCard({
      corpus_id:c.id,corpus_name:c.name,description:c.description||'',
      author:c.author_name||'',tags:c.tags||[],document_count:c.document_count||0,
      access_level:c.access_level||'public',source:'local',score:1
    })).join('');
  }catch(e){el.innerHTML='<div style="color:var(--err)">Failed to load.</div>'}
}
function _exploreCard(c){
  const tags=(c.tags||[]).slice(0,5).map(t=>`<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:var(--bg-hover);font-size:11px;color:var(--muted)">${esc(t)}</span>`).join(' ');
  const q=c.quality||{};
  const docs=q.document_count||c.document_count||0;
  const words=q.word_count||0;
  const badge=c.access_level==='paid'?'<span style="color:var(--accent);font-size:11px;font-weight:600">PAID</span>':c.access_level==='private'?'<span style="color:var(--muted);font-size:11px">PRIVATE</span>':'';
  const src=c.source==='remote'?`<span style="font-size:11px;color:var(--muted)">remote</span>`:'';
  const link=c.source==='remote'&&c.preview_url?c.preview_url:`#/corpus/${c.corpus_id}`;
  const onclick=c.source==='remote'?`onclick="window.open('${c.api_endpoint||'#'}','_blank')"`:
    `onclick="location.hash='#/corpus/${c.corpus_id}'"`;
  return `<div class="explore-card" ${onclick} style="padding:16px 20px;border-radius:10px;border:1px solid var(--border);background:var(--bg-card);cursor:pointer;transition:border-color .15s" onmouseenter="this.style.borderColor='var(--accent)'" onmouseleave="this.style.borderColor='var(--border)'">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <strong style="font-size:15px">${esc(c.corpus_name||'')}</strong>${badge} ${src}
    </div>
    ${c.author?`<div style="font-size:12px;color:var(--muted);margin-bottom:4px">by ${esc(c.author)}</div>`:''}
    ${c.description?`<div style="font-size:13px;color:var(--fg);margin-bottom:8px;opacity:0.85">${esc(c.description).slice(0,200)}</div>`:''}
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      ${tags}
      <span style="font-size:11px;color:var(--muted);margin-left:auto">${docs} docs${words?` · ${Math.round(words/1000)}k words`:''}</span>
    </div>
  </div>`;
}

/* ══════ SHARED GRAPH DRAWING ══════ */
async function drawGraphIn(container,corpora,existingCanvas){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const _activity={};
  await Promise.all(corpora.map(async c=>{try{const r=await fetch(`${API}/corpora/${c.id}/analytics?limit=1`);if(r.ok){const a=await r.json();_activity[c.id]=a.total_queries||0}else{_activity[c.id]=0}}catch(e){_activity[c.id]=0}}));
  const ns=corpora.map(c=>{const tg=Array.isArray(c.tags)?c.tags:[];const tk=[];tg.forEach(t=>tk.push(...t.toLowerCase().split(/[\s,]+/).filter(Boolean)));return{...c,color:cC(c.name),ini:(c.name||'?').split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk,queries:_activity[c.id]||0}});
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
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect();const x=e.clientX-r.left,y=e.clientY-r.top;mp=[x,y];if(drag){drag.fx=x;drag.fy=y;cv.style.cursor='grabbing';return}hov=getN(x,y);cv.style.cursor=hov?'pointer':'grab';if(hov&&tt){tt.innerHTML=`<div class="tt-n">${esc(hov.name)}</div><div class="tt-m">${hov.document_count} documents · ${hov.access_level} · Click to chat</div>`;tt.classList.remove('hidden');tt.style.left=(x+12)+'px';tt.style.top=(y-8)+'px'}else if(tt){tt.classList.add('hidden')}};
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
      if(n.queries>0){const pulseR=rr+4+Math.sin(now*.003+n.queries)*(3+Math.min(n.queries,20)*.3);const pulseOp=.15+Math.sin(now*.004+n.name.length)*.1;cx.beginPath();cx.arc(n.x,n.y,pulseR,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},${pulseOp})`;cx.lineWidth=2;cx.stroke()}
      cx.fillStyle='rgba(255,255,255,.95)';cx.font=`700 ${rr*.55}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);
      const dk=isDark();cx.fillStyle=dk?`rgba(245,245,247,${h?.95:.7})`:`rgba(30,35,50,${h?.9:.6})`;cx.font=`600 ${h?12:11}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+14);
      cx.fillStyle=dk?'rgba(200,200,210,.4)':'rgba(100,110,130,.4)';cx.font='400 9px Inter,sans-serif';cx.fillText((n.queries>0?n.queries+' queries':n.document_count+' docs'),n.x,n.y+rr+26)}
    cx.restore();_gAnim=requestAnimationFrame(draw)}
  sim.on('tick',()=>{});_gAnim=requestAnimationFrame(draw);
}

/* ══════ INLINE COMPILE (Wiki generator, separate from + Add) ══════ */
function showCorpusCompile(corpusId){
  const container=document.getElementById('cv-wiki-docs');if(!container)return;
  if(document.getElementById('cv-compile-panel'))return;
  const panel=document.createElement('div');panel.id='cv-compile-panel';panel.className='cv-add-panel';
  panel.innerHTML=`<div class="cv-add-body"><input type="text" class="fi" id="cc-topic" placeholder='Topic to compile, e.g. "pricing strategy"' style="font-size:13px" /><div style="display:flex;gap:8px;align-items:center;margin-top:8px"><label style="font-size:11px;color:var(--tx3)">Retrieval breadth:</label><input type="number" class="fi" id="cc-topk" value="10" min="3" max="30" style="width:60px;font-size:12px" /></div><div style="font-size:11px;color:var(--tx3);margin-top:6px;line-height:1.5">Retrieves top passages from your Sources and uses an LLM to synthesize a concept note. Requires chat API keys.</div><div class="cv-add-actions"><button class="btn-sm" id="cc-go">Compile</button><button class="btn-sm-ghost" id="cc-cancel">Cancel</button></div></div>`;
  container.parentNode.insertBefore(panel,container);
  const topic=panel.querySelector('#cc-topic');topic.focus();
  panel.querySelector('#cc-cancel').onclick=()=>panel.remove();
  panel.querySelector('#cc-go').onclick=async()=>{
    const t=topic.value.trim();const tk=parseInt(panel.querySelector('#cc-topk').value)||10;
    if(!t){toast('Enter a topic');return}
    const btn=panel.querySelector('#cc-go');btn.disabled=true;btn.textContent='Compiling...';
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/compile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:t,top_k:tk})});
      if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||'Failed');
      const d=await r.json();toast(`Compiled: ${d.title||t}`,'success');
      panel.remove();renderCorpus(corpusId);
    }catch(e){toast('Compile failed: '+e.message);btn.disabled=false;btn.textContent='Compile'}
  };
}

/* ══════ INLINE ADD DOCUMENT (Raw ingestion only — tabs for Upload/Write/URL/Archive/RSS) ══════ */
function showCorpusAddDoc(corpusId,initialTab){
  const container=document.getElementById('cv-raw-docs')||document.getElementById('cv-docs')||document.getElementById('cv-build-srcs');
  if(!container)return;
  if(document.getElementById('cv-add-panel'))return;
  const panel=document.createElement('div');panel.id='cv-add-panel';panel.className='cv-add-panel';
  panel.innerHTML=`<div class="cv-add-tabs"><button class="cv-add-tab active" data-tab="upload">Upload files</button><button class="cv-add-tab" data-tab="write">Write</button><button class="cv-add-tab" data-tab="url">From URL</button><button class="cv-add-tab" data-tab="urls">Batch URLs</button><button class="cv-add-tab" data-tab="feed">Add feed</button><button class="cv-add-tab" data-tab="archive">Import archive</button></div><div class="cv-add-body" id="cv-add-body"></div>`;
  container.parentNode.insertBefore(panel,container);

  const body=panel.querySelector('#cv-add-body');
  const tabs=panel.querySelectorAll('.cv-add-tab');
  let _files=[];

  function setTab(tab){
    tabs.forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
    if(tab==='upload'){
      body.innerHTML=`<div class="cv-add-dz" id="cv-add-dz"><input type="file" id="cv-add-fi" multiple accept=".md,.txt,.text,.html,.htm,.pdf,.docx,.csv,.json,.jsonl" hidden /><div style="color:var(--tx3);font-size:13px">Drop files here, or <span style="color:var(--tx);font-weight:600;cursor:pointer;text-decoration:underline;text-underline-offset:2px" id="cv-add-browse">browse</span></div><div style="font-size:11px;color:var(--tx3);margin-top:4px">PDF, Markdown, DOCX, TXT, CSV, JSON</div><div id="cv-add-flist"></div></div><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go" disabled>Upload</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      const dz=body.querySelector('#cv-add-dz'),fi=body.querySelector('#cv-add-fi'),flist=body.querySelector('#cv-add-flist');
      const goBtn=body.querySelector('#cv-add-go'),cancelBtn=body.querySelector('#cv-add-cancel');
      function refreshFL(){flist.innerHTML=_files.map(f=>`<div style="font-size:12px;padding:2px 0;color:var(--tx2)">${esc(f.name)} <span style="color:var(--tx3)">${(f.size/1024).toFixed(1)}KB</span></div>`).join('');goBtn.disabled=!_files.length}
      body.querySelector('#cv-add-browse').onclick=()=>fi.click();
      dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag-over')};
      dz.ondragleave=()=>dz.classList.remove('drag-over');
      dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag-over');for(const f of e.dataTransfer.files)_files.push(f);refreshFL()};
      fi.onchange=()=>{for(const f of fi.files)_files.push(f);fi.value='';refreshFL()};
      cancelBtn.onclick=()=>{_files=[];panel.remove()};
      goBtn.onclick=async()=>{
        if(!_files.length)return;goBtn.disabled=true;goBtn.textContent='Uploading...';
        const fd=new FormData();for(const f of _files)fd.append('files',f);
        try{await fetch(`${API}/corpora/${corpusId}/upload`,{method:'POST',body:fd})}catch(e){toast('Upload failed');goBtn.disabled=false;goBtn.textContent='Upload';return}
        ensureIndexed(corpusId);
        _files=[];panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='write'){
      body.innerHTML=`<input type="text" class="term-write-title" id="cv-add-title" placeholder="Title" style="margin-bottom:6px" /><textarea class="term-write-body" id="cv-add-text" placeholder="Write your knowledge here... (Markdown supported)" rows="6" style="min-height:100px"></textarea><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Save</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-title').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const title=body.querySelector('#cv-add-title').value.trim(),text=body.querySelector('#cv-add-text').value.trim();
        if(!title||!text){toast('Title and content are required');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Saving...';
        const fd=new FormData();fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+text],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');
        try{await fetch(`${API}/corpora/${corpusId}/upload`,{method:'POST',body:fd})}catch(e){toast('Upload failed');btn.disabled=false;btn.textContent='Save';return}
        ensureIndexed(corpusId);
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='url'){
      body.innerHTML=`<input type="text" class="fi" id="cv-add-url" placeholder="https://example.com/article" style="font-size:13px" /><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Import</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-url').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const url=body.querySelector('#cv-add-url').value.trim();
        if(!url){toast('Enter a URL');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Fetching...';
        try{const r=await fetch(`${API}/corpora/${corpusId}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});if(!r.ok)throw new Error((await r.json()).detail||'Failed')}catch(e){toast('Fetch failed: '+e.message);btn.disabled=false;btn.textContent='Import';return}
        ensureIndexed(corpusId);
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='urls'){
      body.innerHTML=`<textarea class="term-write-body" id="cv-add-urls" placeholder="Paste URLs, one per line (max 40)" rows="6" style="min-height:80px;font-size:12px;font-family:monospace"></textarea><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Import all</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-urls').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const raw=body.querySelector('#cv-add-urls').value.trim();
        const urls=raw.split('\n').map(u=>u.trim()).filter(u=>u&&u.startsWith('http'));
        if(!urls.length){toast('Enter at least one URL');return}
        if(urls.length>40){toast('Maximum 40 URLs per batch');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent=`Fetching ${urls.length} URLs...`;
        try{const r=await fetch(`${API}/corpora/${corpusId}/ingest-urls`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})});if(!r.ok)throw new Error((await r.json()).detail||'Failed');const d=await r.json();toast(`Imported ${d.ingested||0} pages${d.failed?' ('+d.failed+' failed)':''}`,'success')}catch(e){toast('Batch import failed: '+e.message);btn.disabled=false;btn.textContent='Import all';return}
        ensureIndexed(corpusId);
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='feed'){
      const tier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
      const hint=tier==='pro'
        ? `<div style="font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Noos will read every post now and keep watching — new posts sync in automatically.</div>`
        : (_authUser
            ? `<div style="font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Noos reads every post now. <a href="#" data-pro-link="auto-add" style="color:#3b82f6;text-decoration:none">Upgrade to Pro</a> to keep this feed growing on its own.</div>`
            : `<div style="font-size:11px;color:var(--tx3);margin-top:8px;line-height:1.5">Noos reads every post now. Re-add later to pull new ones.</div>`);
      body.innerHTML=`<div style="font-size:12px;color:var(--tx2);margin-bottom:10px;line-height:1.55">Noos reads every post and adds it to this corpus — you can chat about it right after.</div><input type="text" class="fi" id="cv-add-feed" placeholder="https://example.com/feed.xml" style="font-size:13px" /><div style="display:flex;gap:8px;align-items:center;margin-top:6px"><label style="font-size:11px;color:var(--tx3)">Max items:</label><input type="number" class="fi" id="cv-add-feed-max" value="25" min="1" max="100" style="width:60px;font-size:12px" /></div>${hint}<div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Add feed</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-feed').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('[data-pro-link]')?.addEventListener('click',ev=>{ev.preventDefault();showProModal('Auto-add is a Pro feature')});
      body.querySelector('#cv-add-go').onclick=async()=>{
        const feedUrl=body.querySelector('#cv-add-feed').value.trim();
        const maxItems=parseInt(body.querySelector('#cv-add-feed-max').value)||25;
        if(!feedUrl){toast('Enter a feed URL');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Reading feed…';
        try{
          const r=await fetch(`${API}/corpora/${corpusId}/ingest-feed`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feed_url:feedUrl,max_items:maxItems})});
          const d=await r.json().catch(()=>({}));
          if(handleQuotaError(r,d)){btn.disabled=false;btn.textContent='Add feed';return}
          if(!r.ok)throw new Error(d.detail||'Failed');
          const tierNow=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
          const tail=tierNow==='pro'?" Noos will check back every hour.":"";
          toast(`Noos read ${d.ingested||0} new post${d.ingested===1?'':'s'}.${tail}`,'success');
        }catch(e){toast('Add feed failed: '+e.message);btn.disabled=false;btn.textContent='Add feed';return}
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='archive'){
      body.innerHTML=`<div style="display:flex;flex-direction:column;gap:10px"><div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><label style="font-size:12px;color:var(--tx2);display:flex;align-items:center;gap:6px"><input type="radio" name="arc-kind" value="twitter" checked /> Twitter / X data export</label><label style="font-size:12px;color:var(--tx2);display:flex;align-items:center;gap:6px"><input type="radio" name="arc-kind" value="notion" /> Notion workspace export</label></div><input type="file" id="cv-arc-fi" accept=".zip" style="font-size:12px" /><div style="font-size:11px;color:var(--tx3);line-height:1.5">These are your own exports from services you own, so all items are tagged as <strong>your original content</strong>. Twitter: upload the ZIP you get from twitter.com/settings/download_your_data. Notion: Settings → Data export (Markdown &amp; CSV).</div><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go" disabled>Import archive</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div></div>`;
      const fi=body.querySelector('#cv-arc-fi');
      const goBtn=body.querySelector('#cv-add-go');
      fi.onchange=()=>{goBtn.disabled=!fi.files.length};
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      goBtn.onclick=async()=>{
        if(!fi.files.length)return;
        const kind=(body.querySelector('input[name="arc-kind"]:checked')||{}).value||'twitter';
        goBtn.disabled=true;goBtn.textContent='Importing...';
        const fd=new FormData();fd.append('file',fi.files[0]);
        try{
          const r=await fetch(`${API}/corpora/${corpusId}/import/${kind}`,{method:'POST',body:fd});
          if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||'Failed');
          const d=await r.json();
          toast(`Imported ${d.imported||0} of ${d.total||0} items${d.skipped?', '+d.skipped+' skipped':''}`,'success');
        }catch(e){toast('Import failed: '+e.message,'error');goBtn.disabled=false;goBtn.textContent='Import archive';return}
        // Archive import used to skip /index here — newly imported docs stayed
        // un-searchable. ensureIndexed fires a debounced run to pick them up.
        ensureIndexed(corpusId);
        panel.remove();renderCorpus(corpusId);
      };
    }
  }
  tabs.forEach(t=>t.onclick=()=>setTab(t.dataset.tab));
  setTab(initialTab||'upload');
}

/* ══════ COMPOSER SOURCES POPOVER ══════
   Shown when the user clicks the ⚙ icon on a composer (corpus or home).
   Lists currently-connected external information sources and offers
   "+ Add source" which opens a catalog of planned connectors (Notion,
   Drive, GitHub, Gmail, Slack, Email, RSS). Connectors that aren't
   wired yet show a "Coming soon" tag and are disabled. The catalog lives
   here in one place so that as each OAuth connector ships, only its
   entry needs to flip from `soon` → `avail`. */

/* Planned external-source connectors. Each status:
     'avail' — user can connect now (OAuth flow exists)
     'soon'  — planned, grayed out, "Coming soon" tag
   Pro-gating: every external connector is Pro (matches Notion Business). */
const _SOURCE_CONNECTORS=[
  {kind:'notion',name:'Notion',desc:'Live-sync your pages and databases',mono:'N',bg:'#000000',fg:'#ffffff',status:'soon',pro:true},
  {kind:'gdrive',name:'Google Drive',desc:'Docs, Sheets, and folders',mono:'D',bg:'#1a73e8',fg:'#ffffff',status:'soon',pro:true},
  {kind:'github',name:'GitHub',desc:'READMEs, issues, discussions',mono:'Gh',bg:'#1f2328',fg:'#ffffff',status:'soon',pro:true},
  {kind:'gmail',name:'Gmail',desc:'Threads filtered by label',mono:'M',bg:'#ea4335',fg:'#ffffff',status:'soon',pro:true},
  {kind:'slack',name:'Slack',desc:'Channels and direct messages',mono:'#',bg:'#4a154b',fg:'#ffffff',status:'soon',pro:true},
  {kind:'email_inbox',name:'Email forwarding',desc:'Forward emails to a unique inbox address',mono:'@',bg:'#6e6e73',fg:'#ffffff',status:'soon',pro:true},
  {kind:'rss_auto',name:'RSS (auto-sync)',desc:'Scheduled feed polling',mono:'≫',bg:'#f26522',fg:'#ffffff',status:'soon',pro:true},
];

/* Composer "+" attach menu — Notion pattern. Single unified entry point for
   adding content to a KB: file upload, paste text, import a URL, import a
   public archive, or register an RSS feed. Replaces the old big-pill
   shortcut row below the composer so the surface between composer and
   Recent / Suggested stays clean. */
function _closeAttachPopover(){
  const p=document.getElementById('attach-pop');if(p)p.remove();
  document.querySelectorAll('.composer-attach.active').forEach(b=>b.classList.remove('active'));
}
function showAttachPopover(anchor,output,input){
  if(document.getElementById('attach-pop')){_closeAttachPopover();return}
  anchor.classList.add('active');
  // Icon set — minimal line glyphs matching the rest of the popover family.
  const ICO_FILE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`;
  const ICO_LINK=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.72"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.72-1.72"/></svg>`;
  const ICO_FEED_LOCAL=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>`;
  const ICO_ARCHIVE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><line x1="10" y1="12" x2="14" y2="12"/></svg>`;

  const pop=document.createElement('div');pop.id='attach-pop';pop.className='srcs-pop';
  pop.innerHTML=`<button class="srcs-pop-item" data-action="upload"><span class="srcs-pop-ico">${ICO_FILE}</span><span class="srcs-pop-nm">Upload file</span><span class="srcs-pop-aside"><span class="srcs-pop-val">PDF · MD · DOCX</span></span></button>` +
    `<button class="srcs-pop-item" data-action="url"><span class="srcs-pop-ico">${ICO_LINK}</span><span class="srcs-pop-nm">Import a page</span><span class="srcs-pop-aside"><span class="srcs-pop-val">URL or paste</span></span></button>` +
    `<button class="srcs-pop-item" data-action="archive"><span class="srcs-pop-ico">${ICO_ARCHIVE}</span><span class="srcs-pop-nm">Import archive</span><span class="srcs-pop-aside"><span class="srcs-pop-val">Twitter · Notion</span></span></button>` +
    `<div class="srcs-pop-sep"></div>` +
    `<button class="srcs-pop-item" data-action="rss"><span class="srcs-pop-ico">${ICO_FEED_LOCAL}</span><span class="srcs-pop-nm">Add RSS feed</span><span class="srcs-pop-aside"><span class="srcs-pop-val">living source</span></span></button>`;
  document.body.appendChild(pop);
  const r=anchor.getBoundingClientRect();const pw=pop.offsetWidth;const ph=pop.offsetHeight;
  let left=r.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;if(left<8)left=8;
  let top=r.bottom+6;if(top+ph>window.innerHeight-8)top=r.top-ph-6;
  pop.style.left=left+'px';pop.style.top=top+'px';

  pop.querySelectorAll('.srcs-pop-item').forEach(btn=>{
    btn.onclick=()=>{
      const action=btn.dataset.action;
      _closeAttachPopover();
      // Collapse home to chat mode so the injected panel has room.
      const home=document.getElementById('home');if(home)home.classList.add('home--active');
      if(action==='upload'){showTermUpload(output,input,_homeScope)}
      else if(action==='url'){showTermUpload(output,input,_homeScope);setTimeout(()=>{const urlTab=document.querySelector('.term-upload-tab[data-tab="url"]');urlTab?.click()},50)}
      else if(action==='archive'){showTermUpload(output,input,_homeScope);setTimeout(()=>{const arcTab=document.querySelector('.term-upload-tab[data-tab="archive"]');arcTab?.click()},50)}
      else if(action==='rss'){showTermConnectRSS(output,input,_homeScope)}
    };
  });

  setTimeout(()=>{
    const outside=(e)=>{if(!pop.contains(e.target)&&e.target!==anchor){_closeAttachPopover();document.removeEventListener('click',outside,true)}};
    document.addEventListener('click',outside,true);
    const esc=(e)=>{if(e.key==='Escape'){_closeAttachPopover();document.removeEventListener('keydown',esc)}};
    document.addEventListener('keydown',esc);
  },0);
}

function _closeSrcsPopover(){
  const p=document.getElementById('srcs-pop');if(p)p.remove();
  const f=document.getElementById('srcs-flyout');if(f)f.remove();
  document.querySelectorAll('.composer-sliders.active').forEach(b=>b.classList.remove('active'));
}
function _closeSrcsFlyout(){
  const f=document.getElementById('srcs-flyout');if(f)f.remove();
  document.querySelectorAll('.srcs-pop-item.hover').forEach(b=>b.classList.remove('hover'));
}

function _refreshComposerPlaceholder(){
  // Retint the composer placeholder + the inline mode label so Send behavior
  // is legible at a glance (Notion "Plan mode" pattern). Enrich is scoped to
  // a specific KB by design, so its placeholder swaps based on whether the
  // Corpus chip has a pick.
  const input=document.getElementById('term-input');
  const composer=document.getElementById('home-composer');
  const isWrite=composer&&composer.classList.contains('home-composer-note');
  if(input&&!isWrite){
    if(_composerMode==='compile'){
      input.placeholder='Topic to compile — "Vision Pro reviews", "Team culture rituals"';
    }else if(_composerMode==='create'){
      input.placeholder='What\'s on your mind? — "harness engineering", "founder playbook"';
    }else{
      // Enrich — target a specific KB
      const picked=_homeScope&&_corpora.find(c=>c.id===_homeScope);
      if(picked){
        input.placeholder=`Chat to enrich "${picked.name}", or add a URL or file`;
      }else{
        input.placeholder='Pick a knowledge base below — chat to enrich, or add a URL or file';
      }
    }
  }
  const lbl=document.getElementById('home-mode-label');
  if(lbl){
    const m=COMPOSER_MODES.find(x=>x.id===_composerMode)||COMPOSER_MODES[1];
    lbl.textContent=m.name+' mode';
  }
}

/* Sources popover — Notion-style hierarchy.

   Main panel shows three rows: My sources (count), Add sources (connector
   logos), Mode (current mode name). Each row with a `>` indicator opens a
   right-side flyout submenu on hover/click. The flyout sits flush with the
   main panel so users can slide the cursor across without losing the menu. */
function showSourcesPopover(anchor,ctx){
  // Toggle: clicking again closes
  if(document.getElementById('srcs-pop')){_closeSrcsPopover();return}
  anchor.classList.add('active');
  // Connected sources for THIS corpus (none yet — Phase 2+ populates this
  // from the connectors table once OAuth connectors are wired up).
  const connected=[];
  // Mode section — only on home composer (no ctx.corpusId means "Any" scope).
  // Inside a specific corpus, mode is implicitly Enrich and swapping is noise.
  const showModes=!ctx||!ctx.corpusId;
  const pop=document.createElement('div');
  pop.id='srcs-pop';pop.className='srcs-pop';

  // Icons — minimal line glyphs, no decorative emoji.
  const ICO_SRCS=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><line x1="7.8" y1="7.2" x2="11" y2="16.2"/><line x1="16.2" y1="7.2" x2="13" y2="16.2"/></svg>`;
  const ICO_ADD=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  const ICO_MODE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`;
  const ICO_CHEV=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="srcs-chev"><polyline points="9 18 15 12 9 6"/></svg>`;

  // Mini-logo strip for the Add sources row — first 4 connectors as quick chips.
  const addLogos=_SOURCE_CONNECTORS.slice(0,4).map(c=>`<span class="srcs-mini-logo" style="background:${c.bg};color:${c.fg}">${c.mono}</span>`).join('');

  const currentMode=COMPOSER_MODES.find(m=>m.id===_composerMode)||COMPOSER_MODES[1];

  const modeRowHTML=showModes?`<div class="srcs-pop-sep"></div><button class="srcs-pop-item" data-menu="mode"><span class="srcs-pop-ico">${ICO_MODE}</span><span class="srcs-pop-nm">Mode</span><span class="srcs-pop-aside"><span class="srcs-pop-val">${esc(currentMode.name)}</span>${ICO_CHEV}</span></button>`:'';

  pop.innerHTML=`<button class="srcs-pop-item" data-menu="sources"><span class="srcs-pop-ico">${ICO_SRCS}</span><span class="srcs-pop-nm">My sources</span><span class="srcs-pop-aside"><span class="srcs-pop-val">${connected.length}</span>${ICO_CHEV}</span></button><button class="srcs-pop-item" id="srcs-pop-add"><span class="srcs-pop-ico">${ICO_ADD}</span><span class="srcs-pop-nm">Add sources</span><span class="srcs-pop-aside"><span class="srcs-pop-logos">${addLogos}</span></span></button>${modeRowHTML}`;
  document.body.appendChild(pop);
  // Drop down below the anchor, left-aligned to the button
  const r=anchor.getBoundingClientRect();const pw=pop.offsetWidth;const ph=pop.offsetHeight;
  let left=r.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;if(left<8)left=8;
  let top=r.bottom+6;if(top+ph>window.innerHeight-8)top=r.top-ph-6;
  pop.style.left=left+'px';pop.style.top=top+'px';

  // Add sources → open connector-picker modal
  document.getElementById('srcs-pop-add').onclick=()=>{_closeSrcsPopover();showAddSourcePicker(ctx||{})};

  // Flyout submenu renderer — anchored to the Mode / My sources row
  function openFlyout(rowBtn,which){
    _closeSrcsFlyout();
    rowBtn.classList.add('hover');
    const fl=document.createElement('div');fl.id='srcs-flyout';fl.className='srcs-flyout';
    if(which==='mode'){
      fl.innerHTML=COMPOSER_MODES.map(m=>`<button class="srcs-flyout-row${m.id===_composerMode?' active':''}" data-mode="${m.id}"><span class="srcs-flyout-main"><span class="srcs-flyout-nm">${esc(m.name)}</span><span class="srcs-flyout-dc">${esc(m.desc)}</span></span><span class="srcs-flyout-chk">${m.id===_composerMode?'✓':''}</span></button>`).join('');
    }else if(which==='sources'){
      if(connected.length){
        fl.innerHTML=connected.map(c=>`<div class="srcs-flyout-row srcs-flyout-static"><span class="srcs-flyout-main"><span class="srcs-flyout-nm">${esc(c.name)}</span></span></div>`).join('');
      }else{
        fl.innerHTML=`<div class="srcs-flyout-empty">No sources connected yet.<br/>Add Notion, Drive, or GitHub to feed this corpus live.</div>`;
      }
    }
    document.body.appendChild(fl);
    // Position: right of the main panel, top-aligned with the hovered row.
    const popR=pop.getBoundingClientRect();const rowR=rowBtn.getBoundingClientRect();
    const fw=fl.offsetWidth;const fh=fl.offsetHeight;
    let fLeft=popR.right+6;
    if(fLeft+fw>window.innerWidth-8)fLeft=popR.left-fw-6;
    let fTop=rowR.top-4;
    if(fTop+fh>window.innerHeight-8)fTop=window.innerHeight-fh-8;
    if(fTop<8)fTop=8;
    fl.style.left=fLeft+'px';fl.style.top=fTop+'px';

    if(which==='mode'){
      fl.querySelectorAll('.srcs-flyout-row').forEach(btn=>{
        btn.onclick=()=>{
          _composerMode=btn.dataset.mode;
          _closeSrcsPopover();
          _refreshComposerPlaceholder();
        };
      });
    }
  }

  pop.querySelectorAll('.srcs-pop-item[data-menu]').forEach(btn=>{
    // Hover opens flyout (Notion pattern) — click also works for touch/keyboard.
    btn.addEventListener('mouseenter',()=>openFlyout(btn,btn.dataset.menu));
    btn.addEventListener('click',()=>openFlyout(btn,btn.dataset.menu));
  });
  // Closing the flyout when hovering a non-menu item (like Add sources)
  pop.querySelectorAll('.srcs-pop-item:not([data-menu])').forEach(btn=>{
    btn.addEventListener('mouseenter',_closeSrcsFlyout);
  });

  // Close on outside click / Escape
  setTimeout(()=>{
    const outside=(e)=>{
      if(pop.contains(e.target))return;
      const fl=document.getElementById('srcs-flyout');
      if(fl&&fl.contains(e.target))return;
      if(e.target===anchor)return;
      _closeSrcsPopover();document.removeEventListener('click',outside,true);
    };
    document.addEventListener('click',outside,true);
    const esc=(e)=>{if(e.key==='Escape'){_closeSrcsPopover();document.removeEventListener('keydown',esc)}};
    document.addEventListener('keydown',esc);
  },0);
}

/* Connector-logos hint strip below composer — Notion-style "Get better
   answers from your apps" row. Dismissible via × (persisted in localStorage);
   clicking any logo jumps to the Directory. Rendered into an empty
   container by id (e.g. 'c-chint' on corpus, 'home-chint' on home). */
const _CHINT_FLAG='noosphere_chint_dismissed';
function renderChint(elId,ctx){
  const el=document.getElementById(elId);if(!el)return;
  if(localStorage.getItem(_CHINT_FLAG)==='1'){el.innerHTML='';return}
  const logos=_SOURCE_CONNECTORS.map(c=>`<button class="chint-logo" style="background:${c.bg};color:${c.fg}" title="${esc(c.name)}" data-kind="${c.kind}">${c.mono}</button>`).join('');
  el.innerHTML=`<span class="chint-lbl">Connect live sources</span><span class="chint-logos">${logos}</span><button class="chint-close" type="button" title="Dismiss">×</button>`;
  el.querySelector('.chint-close').onclick=()=>{localStorage.setItem(_CHINT_FLAG,'1');el.innerHTML=''};
  el.querySelectorAll('.chint-logo').forEach(btn=>{btn.onclick=()=>{location.hash='#/connectors'}});
}

/* Full Directory page — browseable catalog of all planned connectors.
   Modelled after Claude Code's Connectors Directory. Each card has a
   brand-colored monogram, name, description, and a Connect button that
   is disabled for entries whose status is 'soon'. Search filters live
   client-side. */
function renderConnectors(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  const cardsHTML=_SOURCE_CONNECTORS.map((c,i)=>{
    const isSoon=c.status==='soon';
    const btnLabel=isSoon?'Coming soon':(c.pro?'Connect · Pro':'Connect');
    const btnClass=isSoon?'ck-btn ck-btn-soon':'ck-btn ck-btn-connect';
    return `<div class="ck-card${isSoon?' ck-card-soon':''}"><div class="ck-card-top"><span class="ck-ico" style="background:${c.bg};color:${c.fg}">${c.mono}</span><div class="ck-card-meta"><div class="ck-nm">${esc(c.name)}</div><div class="ck-rank">#${i+1} popular</div></div></div><div class="ck-dc">${esc(c.desc)}</div><div class="ck-card-foot"><button class="${btnClass}" data-kind="${c.kind}" ${isSoon?'disabled':''}>${btnLabel}</button></div></div>`;
  }).join('');
  ct.innerHTML=`<div class="ck-page"><div class="ck-hd"><h1 class="ck-title">Connectors</h1><p class="ck-sub">Connect external sources so your corpus stays live — agents query them in real time. Rolling out continuously.</p></div><div class="ck-toolbar"><input type="text" class="ck-search" id="ck-search" placeholder="Search connectors..." /></div><div class="ck-grid" id="ck-grid">${cardsHTML}</div></div>`;
  document.getElementById('ck-search').oninput=(e)=>{
    const q=e.target.value.toLowerCase().trim();
    ct.querySelectorAll('.ck-card').forEach(card=>{
      const nm=card.querySelector('.ck-nm').textContent.toLowerCase();
      const dc=card.querySelector('.ck-dc').textContent.toLowerCase();
      card.style.display=(!q||nm.includes(q)||dc.includes(q))?'':'none';
    });
  };
  ct.querySelectorAll('.ck-btn-connect').forEach(btn=>{
    btn.onclick=()=>{
      const kind=btn.dataset.kind;const c=_SOURCE_CONNECTORS.find(x=>x.kind===kind);
      if(c.pro&&gateProFeature(`${c.name} connector is a Pro feature`))return;
      toast(`${c.name} OAuth flow not wired yet`,'error');
    };
  });
}

function showAddSourcePicker(ctx){
  const existing=document.getElementById('srcs-pick-overlay');if(existing)existing.remove();
  const ov=document.createElement('div');ov.id='srcs-pick-overlay';ov.className='srcs-pick-overlay';
  const rows=_SOURCE_CONNECTORS.map(c=>{
    const isSoon=c.status==='soon';
    const tag=isSoon
      ? `<span class="srcs-pick-tag">Coming soon</span>`
      : (c.pro?`<span class="srcs-pick-tag tag-pro">Pro</span>`:`<span class="srcs-pick-tag tag-avail">Available</span>`);
    return `<button class="srcs-pick-row" data-kind="${c.kind}" ${isSoon?'disabled':''}><span class="srcs-pick-ico" style="background:${c.bg};color:${c.fg}">${c.mono}</span><span class="srcs-pick-main"><span class="srcs-pick-nm">${esc(c.name)}${tag}</span><span class="srcs-pick-dc">${esc(c.desc)}</span></span></button>`;
  }).join('');
  ov.innerHTML=`<div class="srcs-pick" style="position:relative"><button class="srcs-pick-close" id="srcs-pick-close" title="Close">×</button><div class="srcs-pick-hd"><h2 class="srcs-pick-ttl">Add a source</h2><p class="srcs-pick-sub">Connect external tools so agents can draw from your living knowledge. More connectors rolling out continuously.</p></div><div class="srcs-pick-body">${rows}</div></div>`;
  document.body.appendChild(ov);
  const close=()=>{ov.remove()};
  document.getElementById('srcs-pick-close').onclick=close;
  ov.addEventListener('click',e=>{if(e.target===ov)close()});
  ov.querySelectorAll('.srcs-pick-row').forEach(btn=>{
    btn.onclick=()=>{
      if(btn.disabled)return;
      const kind=btn.dataset.kind;
      const c=_SOURCE_CONNECTORS.find(x=>x.kind===kind);
      if(c.pro&&gateProFeature(`${c.name} connector is a Pro feature`))return;
      // Real OAuth flow wired per-connector as each lands.
      toast(`${c.name} OAuth flow not wired yet`,'error');
    };
  });
}

/* ══════ CORPUS DETAIL + CHAT ══════ */
async function renderCorpus(id,sessionId){
  stopAll();_chatH=[];const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.innerHTML='<div class="empty">Loading...</div>';
  let c;try{const r=await fetch(`${API}/corpora/${id}`);if(!r.ok){const e=await r.json().catch(()=>({}));const msg=r.status===404?'Corpus not found':r.status===401?'Access denied — this corpus requires authentication':r.status===402?e.detail||'Payment required to access this corpus':r.status===403?e.detail||'Access denied':e.detail||'Corpus not found';ct.innerHTML=`<a class="cv-back" href="#/corpora">&larr; Corpora</a><div class="empty" style="margin-top:40px">${msg}</div>`;hideRP();return}c=await r.json()}catch(e){ct.innerHTML='<div class="empty">Not found</div>';hideRP();return}
  let docs=[];try{const r=await fetch(`${API}/corpora/${id}/documents`);if(r.ok)docs=await r.json()}catch(e){}
  let an={};try{const r=await fetch(`${API}/corpora/${id}/analytics?limit=5`);if(r.ok)an=await r.json()}catch(e){}
  let cap=null;try{const r=await fetch(`${API}/corpora/${id}/describe`);if(r.ok)cap=await r.json()}catch(e){}
  ct.classList.add('content--corpus');
  const al=c.access_level||'public';const tg=Array.isArray(c.tags)?c.tags:[];
  const badgeLabel=al==='token'?'Token-gated':al.charAt(0).toUpperCase()+al.slice(1);
  // Split docs: wiki = AI-synthesized (doc_type=concept), raw = substrate (everything else).
  const wikiDocs=docs.filter(d=>d.doc_type==='concept');
  const rawDocs=docs.filter(d=>d.doc_type!=='concept');
  const docItemHTML=(d)=>{
    const wc=d.word_count||0;const wlab=wc.toLocaleString()+' word'+(wc===1?'':'s');
    const sk=d.source_kind||'user_original';const skLabel=sk.replace('_',' ');
    return `<div class="doc-item" data-id="${d.id}"><div class="doc-hd"><span class="doc-tt">${esc(d.title)}</span><span class="doc-hd-right"><span class="doc-mt">${wlab}${d.date?' · '+d.date:''} · <span class="doc-sk sk-${sk}">${skLabel}</span></span><span class="doc-actions"><button class="doc-action-btn doc-edit-btn" data-id="${d.id}" title="Edit"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button><button class="doc-action-btn doc-del-btn" data-id="${d.id}" title="Delete"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button></span><span class="doc-ar">▸</span></span></div></div>`;
  };
  const wikiEmpty='<div class="empty">No concept notes yet — Compile to synthesize from your sources.</div>';
  const rawEmpty='<div class="empty">No sources yet — + Add to import URLs, upload files, or import an archive.</div>';
  ct.innerHTML=`<div class="cv-layout"><div class="cv-scroll"><div class="cv-header"><div class="cv-header-top"><a class="cv-back" href="#/corpora">&larr; Corpora</a></div><div class="cv-identity"><h1 class="cv-name">${esc(c.name)}</h1><span class="mc-badge mc-badge-${al}">${badgeLabel}</span></div><div class="cv-desc-wrap">${c.description?`<p class="cv-desc" id="cv-desc">${esc(c.description)}</p>`:`<p class="cv-desc cv-desc-empty" id="cv-desc">Add a description...</p>`}<button class="cv-desc-edit-btn" id="cv-desc-edit" title="Edit description"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></div>${tg.length?`<div class="cv-tags">${tg.map(t=>`<span class="mc-meta-tag">${esc(t)}</span>`).join('')}</div>`:''}</div>${renderCapCard(cap)}<div class="cv-sec cv-sec-wiki"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Wiki</span><span class="cv-st-sub">${wikiDocs.length?wikiDocs.length+' · AI synthesis':'AI synthesis'}</span></div><button class="btn-add" id="cv-compile-btn">Compile</button></div><div id="cv-wiki-docs">${wikiDocs.length===0?wikiEmpty:wikiDocs.map(docItemHTML).join('')}</div></div><div class="cv-sec cv-sec-raw"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Sources</span><span class="cv-st-sub">${rawDocs.length?rawDocs.length+' · substrate':'substrate'}</span></div><button class="btn-add" id="cv-raw-add">+ Add</button></div><div id="cv-raw-docs">${rawDocs.length===0?rawEmpty:rawDocs.map(docItemHTML).join('')}</div></div><div class="chat-area" id="chat-area"></div></div><div id="cv-chat-bar" class="cv-chat-bar"><div class="composer"><textarea class="composer-input" id="c-ci" placeholder="Ask about ${esc(c.name)}…" rows="1"></textarea><div class="composer-toolbar"><button class="composer-sliders" id="c-sliders" title="Sources" aria-label="Sources"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg></button><div class="composer-spacer"></div><button class="composer-send" id="c-send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></div></div><div class="chint" id="c-chint"></div></div></div>`;
  showRP(c,an);
  document.getElementById('cv-desc-edit').onclick=()=>{
    const wrap=document.querySelector('.cv-desc-wrap');
    const cur=c.description||'';
    wrap.innerHTML=`<input type="text" class="cv-desc-input" id="cv-desc-inp" value="${esc(cur)}" placeholder="Add a description..." /><div class="cv-desc-inp-actions"><button class="btn-sm" id="cv-desc-sv">Save</button><button class="btn-sm-ghost" id="cv-desc-cc">Cancel</button></div>`;
    document.getElementById('cv-desc-inp').focus();
    document.getElementById('cv-desc-cc').onclick=()=>renderCorpus(id);
    document.getElementById('cv-desc-sv').onclick=async()=>{
      const v=document.getElementById('cv-desc-inp').value.trim();
      if(v===cur){renderCorpus(id);return}
      try{await fetch(`${API}/corpora/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:v})});await loadC();renderCorpus(id)}catch(e){toast('Failed to save description')}
    };
  };
  document.getElementById('cv-compile-btn').onclick=()=>{
    if(gateProFeature('Compile is a Pro feature'))return;
    showCorpusCompile(id);
  };
  document.getElementById('cv-raw-add').onclick=()=>showCorpusAddDoc(id);
  document.getElementById('c-sliders').onclick=(e)=>showSourcesPopover(e.currentTarget,{corpusId:id,corpusName:c.name});
  renderChint('c-chint',{corpusId:id,corpusName:c.name});
  ct.querySelectorAll('.doc-del-btn').forEach(btn=>{btn.onclick=async e=>{
    e.stopPropagation();const did=btn.dataset.id;const doc=docs.find(d=>d.id===did);
    if(!confirm(`Delete "${doc?.title||did}"? This cannot be undone.`))return;
    try{await fetch(`${API}/corpora/${id}/documents/${did}`,{method:'DELETE'});renderCorpus(id)}catch(e){toast('Failed to delete document')}
  }});
  ct.querySelectorAll('.doc-edit-btn').forEach(btn=>{btn.onclick=async e=>{
    e.stopPropagation();const did=btn.dataset.id;const item=btn.closest('.doc-item');if(!item)return;
    if(item.classList.contains('editing'))return;
    try{const r=await fetch(`${API}/corpora/${id}/documents/${did}`);const doc=await r.json();showDocInlineEdit(id,item,doc)}catch(e){toast('Failed to load document')}
  }});
  ct.querySelectorAll('.doc-item').forEach(item=>{item.addEventListener('click',async e=>{if(e.target.closest('.doc-actions')||item.classList.contains('editing'))return;if(item.classList.contains('expanded')){const b=item.querySelector('.doc-bd');if(b)b.remove();item.classList.remove('expanded');return}item.classList.add('expanded');try{const r=await fetch(`${API}/corpora/${id}/documents/${item.dataset.id}`);const d=await r.json();const b=document.createElement('div');b.className='doc-bd';b.textContent=d.content||'';item.appendChild(b)}catch(e){}})});
  wireCapCard(id);
  setupCorpusInteract(id,sessionId);
}

// ── Capability card (agent-media identity panel) ──
const CAP_AUTONOMY_NAMES=['Responsive','Subscribing','Synthesizing','Proactive'];
const CAP_TASK_TYPES=['synthesis','retrieval','advice','how-to','factual-lookup','comparison'];

function renderCapCard(cap){
  if(!cap)return '';
  const kbr=Number(cap.kb_reputation||0);
  const tier=kbr>=0.5?'high':kbr>=0.2?'mid':'low';
  const lvl=Number(cap.autonomy_level||0);
  const lvlName=CAP_AUTONOMY_NAMES[lvl]||'Responsive';
  const tt=Array.isArray(cap.task_types)?cap.task_types:[];
  const samples=Array.isArray(cap.samples)?cap.samples:[];
  const sc=cap.source_composition||{};
  const scEntries=Object.entries(sc).filter(([k,v])=>v>0).sort((a,b)=>b[1]-a[1]);
  const lic=cap.license_terms||null;
  const licStr=lic&&typeof lic==='object'?Object.entries(lic).map(([k,v])=>`${k}: ${v}`).join(' · '):'not set';
  const calib=cap.calibration_policy||null;
  const calibStr=calib&&typeof calib==='object'?(calib.reports_confidence?`self-reported (${calib.confidence_source||'self'})`:'not reported'):'not set';
  return `<div class="cap-card"><div class="cap-card__top"><span class="cap-card__title">Capability card</span><span class="cap-card__subtitle">what agents see</span><div class="cap-card__badges"><span class="cap-card__kbr cap-card__kbr--${tier}" title="KB reputation — rolled-up trust score (citations + retention + calibration + satisfaction)">KBR ${kbr.toFixed(2)}</span><span class="cap-card__autonomy" title="Autonomy level — what this KB is allowed to do">L${lvl} · ${lvlName}</span></div></div><div class="cap-card__body"><span class="cap-card__label">Answers</span><div class="cap-card__value">${tt.length?tt.map(t=>`<span class="cap-card__pill">${esc(t)}</span>`).join(''):'<span class="cap-card__empty">No task types yet — auto-fill runs on first ingest.</span>'}</div><span class="cap-card__label">Content mix</span><div class="cap-card__value">${scEntries.length?`<div class="cap-card__comp-bar">${scEntries.map(([k,v])=>{const cls=k==='user_original'?'orig':k==='user_capture'?'cap':'ext';return `<div class="cap-card__comp-seg cap-card__comp-seg--${cls}" style="width:${(v*100).toFixed(1)}%" title="${esc(k)}: ${(v*100).toFixed(0)}%"></div>`}).join('')}</div><div class="cap-card__comp-leg">${scEntries.map(([k,v])=>`<span>${esc(k.replace(/_/g,' '))} ${(v*100).toFixed(0)}%</span>`).join('')}</div>`:'<span class="cap-card__empty">No documents yet</span>'}</div><span class="cap-card__label">Samples</span><div class="cap-card__value">${samples.length?samples.map((s,i)=>`<div class="cap-card__sample" data-idx="${i}"><div class="cap-card__sample-q">${esc(s.question||'')}</div><div class="cap-card__sample-a">${esc(s.answer_preview||'')}</div></div>`).join(''):'<span class="cap-card__empty">No sample Q&amp;A yet</span>'}</div><span class="cap-card__label">Licensing</span><div class="cap-card__value">${esc(licStr)}</div><span class="cap-card__label">Confidence</span><div class="cap-card__value">${esc(calibStr)}</div></div><div class="cap-card__actions"><button class="cap-card__btn" id="cap-regen">Auto-regenerate</button><button class="cap-card__btn cap-card__btn--ghost" id="cap-edit">Edit manually</button></div></div>`;
}

function wireCapCard(corpusId){
  const card=document.querySelector('.cap-card');if(!card)return;
  card.querySelectorAll('.cap-card__sample').forEach(s=>{s.addEventListener('click',()=>s.classList.toggle('open'))});
  const regen=document.getElementById('cap-regen');if(regen)regen.onclick=()=>capRegenerate(corpusId);
  const edit=document.getElementById('cap-edit');if(edit)edit.onclick=()=>capEdit(corpusId);
}

async function capRegenerate(corpusId){
  const btn=document.getElementById('cap-regen');if(btn){btn.disabled=true;btn.textContent='Proposing…'}
  try{
    const r=await fetch(`${API}/corpora/${corpusId}/manifest/suggest`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(!r.ok){const d=await r.json().catch(()=>({}));if(typeof handleQuotaError==='function'?!handleQuotaError(r,d):true)toast(d.detail||'Failed to regenerate','error');return}
    const prop=await r.json();
    showCapRegenModal(corpusId,prop);
  }catch(e){toast('Failed to reach the LLM','error')}
  finally{if(btn){btn.disabled=false;btn.textContent='Auto-regenerate'}}
}

function showCapRegenModal(corpusId,prop){
  const tt=Array.isArray(prop.task_types)?prop.task_types:[];
  const samples=Array.isArray(prop.samples)?prop.samples:[];
  const desc=prop.description_suggestion||'';
  const wrap=document.createElement('div');wrap.className='acm-overlay';
  wrap.innerHTML=`<div class="acm-panel" style="max-width:560px"><div class="acm-title">Proposed capability update</div><div class="acm-sub">Review what the LLM inferred from your corpus. Uncheck anything you don't want applied.</div><div style="margin:14px 0"><label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px"><input type="checkbox" id="cap-apply-tt" ${tt.length?'checked':''} ${tt.length?'':'disabled'}/><strong>Task types</strong></label><div style="padding-left:24px;color:var(--tx2);font-size:12px">${tt.length?tt.map(t=>`<span class="cap-card__pill">${esc(t)}</span>`).join(''):'<em>none proposed</em>'}</div></div><div style="margin:14px 0"><label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px"><input type="checkbox" id="cap-apply-samples" ${samples.length?'checked':''} ${samples.length?'':'disabled'}/><strong>Sample Q&amp;A</strong></label><div style="padding-left:24px;color:var(--tx2);font-size:12px">${samples.length?samples.map(s=>`<div style="margin-bottom:6px"><div>▸ ${esc(s.question||'')}</div><div style="color:var(--tx3);padding-left:12px">${esc(s.answer_preview||'')}</div></div>`).join(''):'<em>none proposed</em>'}</div></div>${desc?`<div style="margin:14px 0"><label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px"><input type="checkbox" id="cap-apply-desc"/><strong>Refresh description</strong></label><div style="padding-left:24px;color:var(--tx2);font-size:12px">${esc(desc)}</div></div>`:''}<div class="acm-actions"><button class="btn-sm-ghost" id="cap-regen-cancel">Cancel</button><button class="btn-sm" id="cap-regen-apply">Apply</button></div></div>`;
  document.body.appendChild(wrap);
  const close=()=>wrap.remove();
  wrap.querySelector('#cap-regen-cancel').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
  wrap.querySelector('#cap-regen-apply').onclick=async()=>{
    const applyTT=document.getElementById('cap-apply-tt')?.checked;
    const applyS=document.getElementById('cap-apply-samples')?.checked;
    const applyDesc=document.getElementById('cap-apply-desc')?.checked;
    const body={};
    if(applyTT)body.task_types=tt;
    if(applyS)body.samples=samples;
    if(applyDesc){body.description_suggestion=desc;body.refresh_description=true}
    if(!Object.keys(body).length){close();return}
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/manifest/apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok)throw new Error('apply failed');
      close();toast('Capability card updated');
      const hash=location.hash;location.hash='#/';setTimeout(()=>location.hash=hash,10);
    }catch(e){toast('Failed to apply','error')}
  };
}

async function capEdit(corpusId){
  let cap=null;try{const r=await fetch(`${API}/corpora/${corpusId}/describe`);if(r.ok)cap=await r.json()}catch(e){}
  if(!cap)return toast('Could not load capability card','error');
  const tt=Array.isArray(cap.task_types)?cap.task_types.join(', '):'';
  const samples=Array.isArray(cap.samples)?cap.samples:[];
  const samplesText=samples.map(s=>`${s.question||''} | ${s.answer_preview||''}`).join('\n');
  const wrap=document.createElement('div');wrap.className='acm-overlay';
  wrap.innerHTML=`<div class="acm-panel" style="max-width:560px"><div class="acm-title">Edit capability card</div><div class="acm-sub">Task types: comma-separated. Samples: one per line, format <code>question | answer preview</code>.</div><div style="margin:14px 0"><label style="display:block;font-size:12px;color:var(--tx2);margin-bottom:4px">Task types (valid: ${CAP_TASK_TYPES.join(', ')})</label><input type="text" id="cap-edit-tt" class="cv-desc-input" value="${esc(tt)}" placeholder="advice, synthesis"/></div><div style="margin:14px 0"><label style="display:block;font-size:12px;color:var(--tx2);margin-bottom:4px">Samples</label><textarea id="cap-edit-samples" class="cv-desc-input" rows="5" placeholder="How do I stir-fry? | Use high heat and peanut oil.">${esc(samplesText)}</textarea></div><div class="acm-actions"><button class="btn-sm-ghost" id="cap-edit-cancel">Cancel</button><button class="btn-sm" id="cap-edit-save">Save</button></div></div>`;
  document.body.appendChild(wrap);
  const close=()=>wrap.remove();
  wrap.querySelector('#cap-edit-cancel').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
  wrap.querySelector('#cap-edit-save').onclick=async()=>{
    const ttRaw=document.getElementById('cap-edit-tt').value;
    const ttArr=ttRaw.split(',').map(s=>s.trim().toLowerCase()).filter(s=>CAP_TASK_TYPES.includes(s)).slice(0,4);
    const sLines=document.getElementById('cap-edit-samples').value.split('\n').map(l=>l.trim()).filter(Boolean);
    const sArr=sLines.map(l=>{const idx=l.indexOf('|');if(idx<0)return null;return{question:l.slice(0,idx).trim(),answer_preview:l.slice(idx+1).trim()}}).filter(s=>s&&s.question&&s.answer_preview).slice(0,3);
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/manifest/apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_types:ttArr,samples:sArr})});
      if(!r.ok)throw new Error('save failed');
      close();toast('Capability card saved');
      const hash=location.hash;location.hash='#/';setTimeout(()=>location.hash=hash,10);
    }catch(e){toast('Failed to save','error')}
  };
}

async function loadCorpusEntities(corpusId){
  const list=document.getElementById('cv-entities-list');if(!list)return;
  try{
    const r=await fetch(`${API}/corpora/${corpusId}/entities`);
    if(!r.ok){list.innerHTML='<div class="empty" style="font-size:12px">Failed to load</div>';return}
    const d=await r.json();
    const ents=(d.entities||[]).filter(e=>e.mention_count>0);
    if(!ents.length){list.innerHTML='<div class="empty" style="font-size:12px;color:var(--tx3)">No entities extracted yet — click Extract to identify people and concepts in your documents.</div>';return}
    // Group by kind
    const byKind={};
    for(const e of ents){(byKind[e.kind]=byKind[e.kind]||[]).push(e)}
    const order=['person','concept','work','place'];
    list.innerHTML=order.filter(k=>byKind[k]).map(k=>{
      const items=byKind[k].sort((a,b)=>b.mention_count-a.mention_count).slice(0,30);
      return `<div class="cv-ent-group"><div class="cv-ent-kind">${k}s</div><div class="cv-ent-row">${items.map(e=>`<a class="cv-ent-chip" href="#/corpus/${corpusId}/entity/${e.id}" title="${e.mention_count} mention${e.mention_count===1?'':'s'}">${esc(e.canonical_name)}<span class="cv-ent-cnt">${e.mention_count}</span></a>`).join('')}</div></div>`;
    }).join('');
  }catch(e){list.innerHTML='<div class="empty" style="font-size:12px">Failed to load</div>'}
}

function showEntitiesModal(corpusId,entities){
  const byKind={};
  for(const e of entities){if(e.mention_count>0)(byKind[e.kind]=byKind[e.kind]||[]).push(e)}
  const order=['person','concept','work','place'];
  const sections=order.filter(k=>byKind[k]).map(k=>{
    const items=byKind[k].sort((a,b)=>b.mention_count-a.mention_count);
    return `<div class="cv-ent-group"><div class="cv-ent-kind">${k}s</div><div class="cv-ent-row">${items.map(e=>`<a class="cv-ent-chip" href="#/corpus/${corpusId}/entity/${e.id}"><span>${esc(e.canonical_name)}</span><span class="cv-ent-cnt">${e.mention_count}</span></a>`).join('')}</div></div>`;
  }).join('');
  const wrap=document.createElement('div');wrap.className='acm-overlay';
  wrap.innerHTML=`<div class="acm-panel" style="max-width:560px"><div class="acm-title">Entities in this corpus</div><div class="acm-sub">People, concepts, and works extracted from your documents</div><div style="max-height:60vh;overflow-y:auto">${sections||'<div class="empty">None with mentions yet.</div>'}</div><div class="acm-actions"><button class="btn-sm-ghost" id="acm-close">Close</button></div></div>`;
  document.body.appendChild(wrap);
  const close=()=>wrap.remove();
  wrap.querySelector('#acm-close').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
  // clicking a chip navigates away via href — close modal as side effect
  wrap.querySelectorAll('.cv-ent-chip').forEach(a=>a.addEventListener('click',close));
}

async function renderEntity(corpusId,entityId){
  const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.innerHTML='<div class="empty">Loading...</div>';
  hideRP();
  let c=null;try{const r=await fetch(`${API}/corpora/${corpusId}`);if(r.ok)c=await r.json()}catch(e){}
  let ent=null;try{const r=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}`);if(!r.ok){ct.innerHTML=`<a class="cv-back" href="#/corpus/${corpusId}">&larr; Back</a><div class="empty" style="margin-top:40px">Entity not found</div>`;return}ent=await r.json()}catch(e){ct.innerHTML='<div class="empty">Failed to load</div>';return}
  const aliases=Array.isArray(ent.aliases)?ent.aliases:[];
  const buckets=[
    {key:'authored_by',label:'Authored',docs:ent.authored_by||[]},
    {key:'participated',label:'Participated in',docs:ent.participated||[]},
    {key:'mentioned_in',label:'Mentioned in',docs:ent.mentioned_in||[]},
  ].filter(b=>b.docs.length>0);
  const bucketHTML=buckets.map(b=>`<div class="ep-bucket"><div class="ep-bucket-lbl">${esc(b.label)} <span class="ep-bucket-cnt">${b.docs.length}</span></div><div class="ep-doc-list">${b.docs.map(d=>`<a class="ep-doc" href="#/corpus/${corpusId}/doc/${d.id}" onclick="event.preventDefault();location.hash='#/corpus/${corpusId}';"><div class="ep-doc-title">${esc(d.title)}</div><div class="ep-doc-meta">${esc(d.doc_type||'')}${d.date?' · '+esc(d.date):''}${d.word_count?' · '+d.word_count+' words':''}<span class="ep-doc-sk sk-${d.source_kind}">${esc(d.source_kind)}</span></div></a>`).join('')}</div></div>`).join('');
  const canCompile=ent.doc_count>0;
  const compileBtnLabel=ent.description?'Recompile':'Compile truth';
  const compiledBlock=ent.description
    ? `<div class="ep-compiled"><div class="ep-compiled-hd"><span class="ep-compiled-lbl">Compiled truth</span><button class="btn-sm-ghost" id="ep-recompile-btn">Recompile</button></div><div class="ep-compiled-body" id="ep-compiled-body">${esc(ent.description).replace(/\n/g,'<br/>')}</div></div>`
    : (canCompile?`<div class="ep-compile-empty"><button class="btn-sm" id="ep-compile-btn">${compileBtnLabel}</button><span class="ep-compile-hint">Synthesize a summary from the ${ent.doc_count} related doc${ent.doc_count===1?'':'s'}</span></div>`:'');
  ct.innerHTML=`<div class="ep-wrap"><a class="cv-back" href="#/corpus/${corpusId}">&larr; ${esc(c?.name||'Corpus')}</a><div class="ep-header"><div class="ep-kind">${esc(ent.kind)}</div><h1 class="ep-name">${esc(ent.canonical_name)}</h1>${aliases.length?`<div class="ep-aliases">also known as ${aliases.map(a=>`<span class="ep-alias">${esc(a)}</span>`).join(', ')}</div>`:''}<div class="ep-stats"><span><strong>${ent.doc_count||0}</strong> document${ent.doc_count===1?'':'s'}</span>${ent.authored_by?.length?`<span>${ent.authored_by.length} authored</span>`:''}${ent.participated?.length?`<span>${ent.participated.length} participated</span>`:''}${ent.mentioned_in?.length?`<span>${ent.mentioned_in.length} mentioned</span>`:''}</div></div>${compiledBlock}${buckets.length?bucketHTML:'<div class="empty">No documents reference this entity yet.</div>'}</div>`;

  async function doCompile(btnId){
    const btn=document.getElementById(btnId);if(!btn)return;
    btn.disabled=true;const orig=btn.textContent;btn.textContent='Compiling...';
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}/compile`,{method:'POST'});
      if(!r.ok){
        const d=await r.json().catch(()=>({}));
        if(!handleQuotaError(r,d))toast('Compile failed: '+errMsg(d,'error'),'error');
        btn.disabled=false;btn.textContent=orig;return;
      }
      renderEntity(corpusId,entityId);
    }catch(e){toast('Compile failed: '+e.message,'error');btn.disabled=false;btn.textContent=orig}
  }
  const cBtn=document.getElementById('ep-compile-btn');if(cBtn)cBtn.onclick=()=>doCompile('ep-compile-btn');
  const rBtn=document.getElementById('ep-recompile-btn');if(rBtn)rBtn.onclick=()=>doCompile('ep-recompile-btn');
}

function showDocInlineEdit(corpusId,item,doc){
  const existing=item.querySelector('.doc-bd');if(existing)existing.remove();
  item.classList.remove('expanded');item.classList.add('editing');
  const ed=document.createElement('div');ed.className='doc-edit-inline';
  ed.innerHTML=`<input type="text" class="doc-edit-title" value="${esc(doc.title||'')}" placeholder="Title" /><textarea class="doc-edit-content" rows="8" placeholder="Content (Markdown supported)...">${esc(doc.content||'')}</textarea><div class="doc-edit-actions"><button class="btn-sm-ghost doc-edit-cancel">Cancel</button><button class="btn-sm doc-edit-save">Save</button></div>`;
  ed.onclick=e=>e.stopPropagation();
  item.appendChild(ed);
  ed.querySelector('.doc-edit-title').focus();
  ed.querySelector('.doc-edit-cancel').onclick=()=>{ed.remove();item.classList.remove('editing')};
  ed.querySelector('.doc-edit-save').onclick=async()=>{
    const title=ed.querySelector('.doc-edit-title').value.trim();
    const content=ed.querySelector('.doc-edit-content').value.trim();
    if(!title){toast('Title is required');return}
    const btn=ed.querySelector('.doc-edit-save');btn.disabled=true;btn.textContent='Saving...';
    const body={};
    if(title!==doc.title)body.title=title;
    if(content!==doc.content)body.content=content;
    if(!Object.keys(body).length){ed.remove();item.classList.remove('editing');return}
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/documents/${doc.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok)throw new Error((await r.json()).detail||'Failed');
      if(body.content){ensureIndexed(corpusId)}
      renderCorpus(corpusId);
    }catch(e){toast('Save failed: '+e.message);btn.disabled=false;btn.textContent='Save'}
  };
}

function appendAssistantChatBlock(area,text,citations,corpusId,userQuestion,sessionId){
  const wrap=document.createElement('div');
  wrap.className='chat-msg assistant';
  wrap.insertAdjacentHTML('afterbegin',noosHd());
  const outer=document.createElement('div');
  outer.className='noos-body';
  const body=document.createElement('div');
  body.className='noos-md';
  body.style.whiteSpace='pre-wrap';
  body.textContent=text||'';
  outer.appendChild(body);
  if(citations&&citations.length){
    const cd=document.createElement('div');
    cd.className='chat-cites';
    citations.forEach(ct=>{const sp=document.createElement('span');sp.className='chat-cite';sp.textContent=ct.title||'';cd.appendChild(sp)});
    outer.appendChild(cd);
  }
  const actions=document.createElement('div');
  actions.className='chat-msg-actions';
  const btn=document.createElement('button');
  btn.type='button';
  btn.className='btn-sm-ghost chat-save';
  btn.textContent='Save to corpus';
  btn.onclick=async()=>{
    btn.disabled=true;
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/capture`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:text,question:userQuestion||'',session_id:sessionId||undefined})});
      if(!r.ok)throw new Error('capture failed');
      toast('Saved as a capture document','success');
    }catch(e){toast('Save failed');btn.disabled=false}
  };
  actions.appendChild(btn);
  outer.appendChild(actions);
  wrap.appendChild(outer);
  area.appendChild(wrap);
}

async function setupCorpusInteract(id,sessionId){
  const ci=document.getElementById('c-ci'),send=document.getElementById('c-send'),area=document.getElementById('chat-area');
  if(!ci||!send||!area)return;
  let _sessionId=sessionId||null;

  if(_sessionId){
    try{
      const r=await fetch(`${API}/chat-sessions/${_sessionId}`);
      if(r.ok){
        const session=await r.json();
        let lastUser='';
        for(const m of(session.messages||[])){
          _chatH.push({role:m.role,content:m.content});
          if(m.role==='user'){
            area.innerHTML+=`<div class="chat-msg user">${esc(m.content)}</div>`;
            lastUser=m.content;
          }else{
            appendAssistantChatBlock(area,m.content,m.citations||[],id,lastUser,_sessionId);
            lastUser='';
          }
        }
        area.scrollTop=area.scrollHeight;
      }else{_sessionId=null}
    }catch(e){_sessionId=null}
  } else {
    const sessions=_chatSessions.filter(s=>s.corpus_id===id);
    if(sessions.length){
      _sessionId=sessions[0].id;
      try{
        const r=await fetch(`${API}/chat-sessions/${_sessionId}`);
        if(r.ok){
          const session=await r.json();
          let lastUser='';
          for(const m of(session.messages||[])){
            _chatH.push({role:m.role,content:m.content});
            if(m.role==='user'){
              area.innerHTML+=`<div class="chat-msg user">${esc(m.content)}</div>`;
              lastUser=m.content;
            }else{
              appendAssistantChatBlock(area,m.content,m.citations||[],id,lastUser,_sessionId);
              lastUser='';
            }
          }
          area.scrollTop=area.scrollHeight;
        }else{_sessionId=null}
      }catch(e){_sessionId=null}
    }
  }

  ci.addEventListener('input',()=>{ci.style.height='auto';ci.style.height=Math.min(ci.scrollHeight,120)+'px'});
  async function chat(){const msg=ci.value.trim();if(!msg)return;ci.value='';ci.style.height='auto';area.innerHTML+=`<div class="chat-msg user">${esc(msg)}</div>`;area.scrollTop=area.scrollHeight;send.disabled=true;area.innerHTML+=`<div class="chat-msg assistant" id="c-ld">${noosHd()}<span style="color:var(--tx3)">Thinking...</span></div>`;area.scrollTop=area.scrollHeight;_chatH.push({role:'user',content:msg});
    try{const r=await fetch(`${API}/corpora/${id}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,history:_chatH,top_k:5,session_id:_sessionId||undefined})});
      if(!r.ok){const err=await r.json().catch(()=>({}));throw new Error(err.detail||`HTTP ${r.status}`)}
      const d=await r.json();document.getElementById('c-ld')?.remove();_chatH.push({role:'assistant',content:d.response});
      if(d.session_id)_sessionId=d.session_id;
      loadChatSessions();
      appendAssistantChatBlock(area,d.response,d.citations||[],id,msg,_sessionId)}
    catch(e){document.getElementById('c-ld')?.remove();area.innerHTML+=`<div class="chat-msg assistant">${noosHd()}<div class="chat-err">${esc(e.message||'Failed to reach LLM provider.')}</div></div>`}send.disabled=false;area.scrollTop=area.scrollHeight}
  send.onclick=chat;ci.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chat()}};
}

const ACC_MSG={public:'Discoverable by all agents worldwide.',private:'Only accessible via your personal endpoint.',token:'Requires access token to query.',paid:'Agents pay per query or subscribe. Set pricing below.'};

function showAccessConfirmModal(newLevel, summary){
  // summary: { total, originals, by_source_kind, visibility: {owner, external} }
  return new Promise(resolve=>{
    const titles={public:'Enable public access',paid:'Enable paid access',token:'Enable token-gated access'};
    const visibleTo={public:'everyone',paid:'paying subscribers',token:'token holders'};
    const orig=summary.originals;
    const extPub=summary.by_source_kind?.external_public||0;
    const extSub=summary.by_source_kind?.external_subscription||0;
    const cap=summary.by_source_kind?.user_capture||0;
    const origBreakdown=[orig?`${orig} original${orig===1?'':'s'}`:null,cap?`(incl. ${cap} chat capture${cap===1?'':'s'})`:null].filter(Boolean).join(' ');
    const extLines=[];
    if(extPub>0)extLines.push(`<div class="acm-row acm-ext"><span class="acm-dot"></span><span class="acm-lbl">${extPub} external public reference${extPub===1?'':'s'}</span><span class="acm-note">hidden from ${visibleTo[newLevel]}</span></div>`);
    if(extSub>0)extLines.push(`<div class="acm-row acm-ext"><span class="acm-dot"></span><span class="acm-lbl">${extSub} subscription content</span><span class="acm-note">owner-only</span></div>`);
    const wrap=document.createElement('div');wrap.className='acm-overlay';
    wrap.innerHTML=`<div class="acm-panel"><div class="acm-title">${titles[newLevel]||'Enable external access'}</div><div class="acm-sub">Your corpus contains:</div><div class="acm-list"><div class="acm-row acm-orig"><span class="acm-dot"></span><span class="acm-lbl">${origBreakdown}</span><span class="acm-note">visible to ${visibleTo[newLevel]}</span></div>${extLines.join('')}</div><div class="acm-expl">Only your originals are served to non-owners. External material stays private.</div><div class="acm-actions"><button class="btn-sm-ghost" id="acm-cc">Cancel</button><button class="btn-sm" id="acm-ok">${titles[newLevel]||'Confirm'}</button></div></div>`;
    document.body.appendChild(wrap);
    const close=r=>{wrap.remove();resolve(r)};
    wrap.querySelector('#acm-cc').onclick=()=>close(false);
    wrap.querySelector('#acm-ok').onclick=()=>close(true);
    wrap.addEventListener('click',e=>{if(e.target===wrap)close(false)});
  });
}

async function showRP(c,an){const rp=document.getElementById('rpanel');rp.classList.remove('hidden');const host=location.origin;const al=c.access_level||'public';
  let regStatus='';
  try{const hr=await fetch(`${API}/health`);const h=await hr.json();regStatus=al!=='private'&&h.registry_connected?'<div class="rp-reg ok">Registered in the Noosphere</div>':'<div class="rp-reg local">Local only</div>'}catch(e){regStatus='<div class="rp-reg local">Local only</div>'}

  rp.innerHTML=`<div class="rp-sec rp-sec-first"><div class="rp-lbl">Connect Agents</div><div class="rp-ep"><span class="rp-epl">MCP</span><span class="rp-epu">${host}/mcp</span><button class="rp-cp" onclick="cp('${host}/mcp',this)">Copy</button></div><div class="rp-ep"><span class="rp-epl">API</span><span class="rp-epu">${host}/api/v1/corpora/${c.id}/search</span><button class="rp-cp" onclick="cp('${host}/api/v1/corpora/${c.id}/search',this)">Copy</button></div></div>
    <div class="rp-sec"><div class="rp-lbl">Stats</div><div class="rp-stats"><div><div class="rp-sv">${fmtN(c.document_count||0)}</div><div class="rp-sl">documents</div></div><div><div class="rp-sv">${fmtN(c.chunk_count||0)}</div><div class="rp-sl">chunks</div></div><div><div class="rp-sv">${fmtN(c.word_count||0)}</div><div class="rp-sl">words</div></div><div><div class="rp-sv">${fmtN(an.total_queries||0)}</div><div class="rp-sl">queries</div></div></div></div>
    <div class="rp-sec"><div class="rp-lbl">Access</div><div class="rp-row"><select id="rp-acc"><option value="public" ${al==='public'?'selected':''}>Public</option><option value="private" ${al==='private'?'selected':''}>Private</option><option value="token" ${al==='token'?'selected':''}>Token-gated</option><option value="paid" ${al==='paid'?'selected':''}>Paid</option></select><button class="btn-sm" id="rp-sv">Save</button></div><div class="rp-msg info" id="rp-msg">${ACC_MSG[al]||''}</div>${regStatus}</div>
    <div id="rp-tokens" class="rp-sec" style="display:${al==='token'?'block':'none'}"><div class="rp-lbl">Access Tokens</div><button class="btn-sm" id="rp-gen-tk" style="margin-bottom:8px">+ Generate Token</button><div id="rp-tk-list"></div></div>
    <div id="rp-pricing" class="rp-sec" style="display:${al==='paid'?'block':'none'}"><div class="rp-lbl">Pricing</div><div id="rp-pricing-body"></div></div>
    <div id="rp-revenue" class="rp-sec" style="display:${al==='paid'?'block':'none'}"><div class="rp-lbl">Revenue</div><div id="rp-revenue-body" style="font-size:12px;color:var(--tx3)">Loading...</div></div>
    <div class="rp-sec"><div class="rp-lbl">Your handles</div><div class="rp-handles-body" id="rp-handles-view">${(Array.isArray(c.owned_handles)&&c.owned_handles.length)?c.owned_handles.map(h=>`<span class="cv-handle-tag">${esc(h)}</span>`).join(' '):'<span style="font-size:12px;color:var(--tx3);font-style:italic">none set</span>'} <a href="#" class="rp-subtle-link" id="rp-handles-edit">edit</a></div><div class="rp-hint">URLs from these default to your original content.</div></div>
    <div class="rp-sec"><div class="rp-lbl">Entities</div><div class="rp-entities-row" id="rp-entities-row"><span style="font-size:12px;color:var(--tx3)">Loading…</span></div></div>
    <div class="rp-sec rp-sec-maint"><div class="rp-lbl">Maintenance</div><div class="rp-maint-row"><a href="#" class="rp-subtle-link" id="rp-reindex" title="Re-embed all documents — use this if a recent upload didn't become searchable">Re-embed</a><a href="#" class="rp-subtle-link" id="rp-export">Export</a><a href="#" class="rp-subtle-link rp-danger" id="rp-delete">Delete corpus</a></div></div>`;

  document.getElementById('rp-acc').onchange=()=>{
    const v=document.getElementById('rp-acc').value;
    document.getElementById('rp-msg').textContent=ACC_MSG[v]||'';
    document.getElementById('rp-tokens').style.display=v==='token'?'block':'none';
    document.getElementById('rp-pricing').style.display=v==='paid'?'block':'none';
    document.getElementById('rp-revenue').style.display=v==='paid'?'block':'none';
    if(v==='paid')loadPricingUI(c);
  };
  document.getElementById('rp-sv').onclick=async()=>{
    const newAl=document.getElementById('rp-acc').value;
    const curAl=c.access_level||'public';
    if(newAl===curAl){toast('No change');return}
    const external=['public','paid','token'];
    if(external.includes(newAl)){
      let summary=null;
      try{const r=await fetch(`${API}/corpora/${c.id}/access-summary`);if(r.ok)summary=await r.json()}catch(e){}
      if(summary && summary.total>0){
        if(!summary.can_enable_external_access){
          toast('This corpus contains only external material — add at least one user-originated document first','error');
          return;
        }
        const proceed=await showAccessConfirmModal(newAl,summary);
        if(!proceed)return;
      }
    }
    try{
      const r=await fetch(`${API}/corpora/${c.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:newAl})});
      if(!r.ok){const d=await r.json().catch(()=>({}));toast(d.detail||'Failed to update access','error');return}
      await loadC();renderCorpus(c.id);
    }catch(e){toast('Failed: '+e.message,'error')}
  };

  /* Handles edit (moved from main view) */
  document.getElementById('rp-handles-edit').onclick=(e)=>{
    e.preventDefault();
    const view=document.getElementById('rp-handles-view');
    const cur=(Array.isArray(c.owned_handles)?c.owned_handles:[]).join('\n');
    view.innerHTML=`<textarea class="cv-handles-input" id="rp-handles-inp" rows="3" placeholder="One per line — e.g. twitter.com/steve, stevesayao.com">${esc(cur)}</textarea><div class="cv-handles-actions"><button class="btn-sm" id="rp-handles-sv">Save</button><button class="btn-sm-ghost" id="rp-handles-cc">Cancel</button></div>`;
    document.getElementById('rp-handles-inp').focus();
    document.getElementById('rp-handles-cc').onclick=()=>renderCorpus(c.id);
    document.getElementById('rp-handles-sv').onclick=async()=>{
      const list=document.getElementById('rp-handles-inp').value.split('\n').map(s=>s.trim()).filter(Boolean);
      try{await fetch(`${API}/corpora/${c.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({owned_handles:list})});await loadC();renderCorpus(c.id)}catch(e){toast('Failed to save handles')}
    };
  };

  /* Entities: count + extract / browse */
  (async()=>{
    const row=document.getElementById('rp-entities-row');if(!row)return;
    try{
      const r=await fetch(`${API}/corpora/${c.id}/entities`);
      const d=await r.json();
      const ents=(d.entities||[]);
      const total=ents.length;
      const shown=ents.filter(e=>e.mention_count>0).length;
      if(total===0){
        row.innerHTML=`<span style="font-size:12px;color:var(--tx3)">None yet</span> <a href="#" class="rp-subtle-link" id="rp-extract-btn">Extract with AI</a>`;
      }else{
        row.innerHTML=`<span style="font-size:12px;color:var(--tx2)"><strong>${shown}</strong> entities</span> <a href="#" class="rp-subtle-link" id="rp-browse-ent">browse</a> · <a href="#" class="rp-subtle-link" id="rp-extract-btn">Re-extract</a>`;
      }
      const extractBtn=document.getElementById('rp-extract-btn');
      if(extractBtn)extractBtn.onclick=async(ev)=>{
        ev.preventDefault();
        if(gateProFeature('Entity extraction is a Pro feature'))return;
        const prevLabel=extractBtn.textContent;extractBtn.textContent='Extracting…';
        try{
          const rr=await fetch(`${API}/corpora/${c.id}/extract-entities`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:50})});
          const body=await rr.json().catch(()=>({}));
          if(handleQuotaError(rr,body)){extractBtn.textContent=prevLabel;return}
          if(!rr.ok)throw new Error(body.detail||'Failed');
          toast(`Enriched ${body.enriched||0} doc${body.enriched===1?'':'s'}${body.remaining?', '+body.remaining+' remaining':''}`,'success');
          renderCorpus(c.id);
        }catch(e){toast('Extract failed: '+e.message,'error');extractBtn.textContent=prevLabel}
      };
      const browseBtn=document.getElementById('rp-browse-ent');
      if(browseBtn)browseBtn.onclick=(ev)=>{ev.preventDefault();showEntitiesModal(c.id,ents)};
    }catch(e){row.innerHTML='<span style="font-size:12px;color:var(--tx3)">Failed to load</span>'}
  })();

  /* Maintenance row */
  document.getElementById('rp-reindex').onclick=async(e)=>{
    e.preventDefault();
    // User-initiated recovery path — run now (no debounce), force=true so we
    // re-embed everything regardless of content_hash (useful when embeddings
    // got corrupted or an earlier index run failed mid-flight).
    const btn=document.getElementById('rp-reindex');const orig=btn.textContent;
    btn.textContent='Embedding…';btn.style.pointerEvents='none';
    try{
      const r=await fetch(`${API}/corpora/${c.id}/index`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:true})});
      if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.detail||'Failed')}
      const d=await r.json();
      toast(`Re-embedded ${d.embedded||0} chunks`,'success');
      renderCorpus(c.id);
    }catch(err){
      toast('Re-embed failed: '+err.message,'error');
      btn.textContent=orig;btn.style.pointerEvents='';
    }
  };
  document.getElementById('rp-export').onclick=(e)=>{
    e.preventDefault();window.open(`${API}/corpora/${c.id}/export`,'_blank');
  };
  document.getElementById('rp-delete').onclick=async(e)=>{
    e.preventDefault();
    if(!confirm(`Delete "${c.name}" and all its documents? This cannot be undone.`))return;
    try{await fetch(`${API}/corpora/${c.id}`,{method:'DELETE'});await loadC();location.hash='#/corpora'}
    catch(err){toast('Delete failed: '+err.message,'error')}
  };

  /* Token management */
  async function loadTokens(){
    const list=document.getElementById('rp-tk-list');if(!list)return;
    try{const r=await fetch(`${API}/corpora/${c.id}/tokens`);const tks=await r.json();
      if(!tks.length){list.innerHTML='<div style="font-size:11px;color:var(--tx3)">No tokens yet</div>';return}
      list.innerHTML=tks.map(t=>`<div class="rp-tk-item"><div class="rp-tk-info"><span class="rp-tk-label">${esc(t.label||'Untitled')}</span><span class="rp-tk-meta">${t.usage_count||0} uses</span></div><button class="btn-sm-ghost rp-tk-revoke" data-id="${t.id}" style="color:#ef4444;border-color:#ef4444">Revoke</button></div>`).join('');
      list.querySelectorAll('.rp-tk-revoke').forEach(b=>{b.onclick=async()=>{await fetch(`${API}/corpora/${c.id}/tokens/${b.dataset.id}`,{method:'DELETE'});loadTokens()}});
    }catch(e){list.innerHTML='<div style="font-size:11px;color:var(--tx3)">Failed to load tokens</div>'}
  }

  document.getElementById('rp-gen-tk').onclick=async()=>{
    const label=prompt('Token label (optional):','');
    if(label===null)return;
    try{
      const r=await fetch(`${API}/corpora/${c.id}/tokens`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:label||'API Token'})});
      const tk=await r.json();
      const list=document.getElementById('rp-tk-list');
      const notice=document.createElement('div');notice.className='rp-tk-created';
      notice.innerHTML=`<div style="font-size:11px;color:var(--acc);margin-bottom:4px">Token created — copy it now (shown only once):</div><div class="rp-tk-val"><code>${esc(tk.token)}</code><button class="btn-sm" onclick="cp('${tk.token}',this)">Copy</button></div>`;
      list.prepend(notice);
      setTimeout(()=>{notice.remove();loadTokens()},15000);
    }catch(e){alert('Failed to create token')}
  };

  if(al==='token')loadTokens();
  if(al==='paid'){loadPricingUI(c);loadRevenueUI(c.id)}
}

async function loadPricingUI(corpus){
  const body=document.getElementById('rp-pricing-body');if(!body)return;
  let pricing=null;
  try{const r=await fetch(`${API}/corpora/${corpus.id}/pricing`);const d=await r.json();pricing=d.pricing}catch(e){}
  const type=pricing?.type||'per_query';
  const amount=(pricing?.amount_cents||500)/100;
  const queries=pricing?.queries_per_payment||100;
  const priceId=pricing?.stripe_price_id||'';

  body.innerHTML=`
    <div style="display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;gap:8px;align-items:center">
        <label style="font-size:11px;color:var(--tx3);width:50px">Type</label>
        <select id="rp-pr-type" class="fi" style="font-size:12px;flex:1">
          <option value="per_query" ${type==='per_query'?'selected':''}>Per-query</option>
          <option value="subscription" ${type==='subscription'?'selected':''}>Subscription</option>
        </select>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <label style="font-size:11px;color:var(--tx3);width:50px">Price $</label>
        <input type="number" class="fi" id="rp-pr-amount" value="${amount}" min="0.5" step="0.5" style="font-size:12px;flex:1" />
      </div>
      <div id="rp-pr-pq" style="display:${type==='per_query'?'flex':'none'};gap:8px;align-items:center">
        <label style="font-size:11px;color:var(--tx3);width:50px">Queries</label>
        <input type="number" class="fi" id="rp-pr-queries" value="${queries}" min="1" style="font-size:12px;flex:1" />
      </div>
      <div id="rp-pr-sub" style="display:${type==='subscription'?'flex':'none'};gap:8px;align-items:center">
        <label style="font-size:11px;color:var(--tx3);width:50px">Price ID</label>
        <input type="text" class="fi" id="rp-pr-priceid" value="${esc(priceId)}" placeholder="price_..." style="font-size:12px;flex:1" />
      </div>
      <div style="font-size:10px;color:var(--tx3)">Self-hosted: your Stripe keys, you keep 100%</div>
      <button class="btn-sm" id="rp-pr-save">Save Pricing</button>
    </div>`;

  document.getElementById('rp-pr-type').onchange=()=>{
    const t=document.getElementById('rp-pr-type').value;
    document.getElementById('rp-pr-pq').style.display=t==='per_query'?'flex':'none';
    document.getElementById('rp-pr-sub').style.display=t==='subscription'?'flex':'none';
  };

  document.getElementById('rp-pr-save').onclick=async()=>{
    const btn=document.getElementById('rp-pr-save');
    const pType=document.getElementById('rp-pr-type').value;
    const amountCents=Math.round(parseFloat(document.getElementById('rp-pr-amount').value)*100);
    if(amountCents<50){toast('Minimum price is $0.50');return}
    const payload={type:pType,amount_cents:amountCents,currency:'usd'};
    if(pType==='per_query'){
      payload.queries_per_payment=parseInt(document.getElementById('rp-pr-queries').value)||100;
    } else {
      const pid=document.getElementById('rp-pr-priceid').value.trim();
      if(!pid){toast('Stripe Price ID is required for subscriptions');return}
      payload.stripe_price_id=pid;
    }
    btn.disabled=true;btn.textContent='Saving...';
    try{
      const r=await fetch(`${API}/corpora/${corpus.id}/pricing`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if(!r.ok)throw new Error((await r.json()).detail||'Failed');
      toast('Pricing saved','success');btn.textContent='Save Pricing';btn.disabled=false;
    }catch(e){toast('Failed: '+e.message);btn.textContent='Save Pricing';btn.disabled=false}
  };
}

async function loadRevenueUI(corpusId){
  const body=document.getElementById('rp-revenue-body');if(!body)return;
  try{
    const r=await fetch(`${API}/corpora/${corpusId}/revenue`);
    if(!r.ok){body.textContent='—';return}
    const d=await r.json();
    const dollars=(d.total_revenue_cents||0)/100;
    body.innerHTML=`<div style="display:flex;gap:16px;margin-bottom:6px"><div><div style="font-size:16px;font-weight:600;color:var(--acc)">$${dollars.toFixed(2)}</div><div style="font-size:10px;color:var(--tx3)">total revenue</div></div><div><div style="font-size:16px;font-weight:600">${d.total_payments||0}</div><div style="font-size:10px;color:var(--tx3)">payments</div></div><div><div style="font-size:16px;font-weight:600">${d.active_subscriptions||0}</div><div style="font-size:10px;color:var(--tx3)">active subs</div></div></div>${d.recent_payments?.length?'<div style="font-size:10px;color:var(--tx3);margin-top:4px">Recent: '+d.recent_payments.slice(0,3).map(p=>'$'+(p.amount_cents/100).toFixed(2)+' ('+p.status+')').join(', ')+'</div>':''}`;
  }catch(e){body.textContent='Failed to load revenue'}
}

/* ── Pricing Page ── */
/* Shared tier-card HTML — used by the /pricing page and the paywall modal.
   Both surfaces render the same Free vs Pro comparison; only the containing
   chrome (page header vs modal header) differs. */
function _tierCardsHTML(currentTier){
  return `<div class="pg-cards">
    <div class="pg-card${currentTier==='free'?' pg-current':''}">
      <div class="pg-tier-row"><span class="pg-tier">Free</span></div>
      <div class="pg-price"><span class="pg-amt">$0</span><span class="pg-period">/mo</span></div>
      <div class="pg-desc">Static knowledge base</div>
      <ul class="pg-features">
        <li>1 corpus, 100 documents</li>
        <li><strong>Add sources</strong> manually — files (PDF · DOCX · MD · TXT · CSV · JSON), URLs, RSS (1 RSS/day). Noos normalizes any format into clean, agent-readable text.</li>
        <li><strong>Embed</strong> — Noos turns every passage into a semantic vector, so chat finds and cites the exact source for your question</li>
        <li><strong>Chat</strong> — ground answers in your knowledge network; build new knowledge through conversation (20 msgs/day)</li>
      </ul>
      ${currentTier==='free'?'<div class="pg-badge">Current plan</div>':''}
    </div>
    <div class="pg-card pg-card-pro${currentTier==='pro'?' pg-current':''}">
      <div class="pg-tier-row"><span class="pg-tier">Pro</span>${currentTier==='pro'?'<span class="pg-tier-badge">Current</span>':''}</div>
      <div class="pg-price"><span class="pg-amt">$9</span><span class="pg-period">/mo</span></div>
      <div class="pg-desc">Living knowledge base</div>
      <ul class="pg-features">
        <li>Everything in Free, plus:</li>
        <li>Unlimited corpora & documents</li>
        <li><strong>Auto-add</strong> — connect a feed once, Noos pulls in new posts as they publish. Higher daily caps on manual uploads.</li>
        <li><strong>Embed at scale</strong> — no document cap; your entire growing library stays searchable</li>
        <li><strong>Chat</strong> — higher daily cap, enough for sustained building sessions</li>
        <li><strong>Compile</strong> — Noos turns your corpus into Wiki articles, Entity profiles, and Timelines, and keeps them evolving as your sources change.</li>
        <li><strong>Monetize</strong> — charge per query on your corpora. Noos collects via Stripe Connect; you keep the revenue.</li>
        <li>Priority access</li>
      </ul>
      ${currentTier==='pro'?'<button class="pg-upgrade" data-pg-action="manage">Manage Subscription</button>':
        _authUser?'<button class="pg-upgrade" data-pg-action="upgrade">Upgrade to Pro</button>':
        '<a href="#/login" class="pg-upgrade">Sign in to upgrade</a>'}
    </div>
  </div>`;
}

function _wireTierCardButtons(root){
  root.querySelectorAll('[data-pg-action]').forEach(btn=>{
    const action=btn.dataset.pgAction;
    btn.onclick=async()=>{
      btn.disabled=true;const prev=btn.textContent;btn.textContent='Loading...';
      const url=action==='manage'?`${API}/cloud/create-portal-session`:`${API}/cloud/create-checkout-session`;
      try{const r=await fetch(url,{method:'POST'});const d=await r.json();
        if(d.url){window.location.href=d.url;return}
        toast(d.detail||'Failed');btn.disabled=false;btn.textContent=prev;
      }catch(e){toast('Failed');btn.disabled=false;btn.textContent=prev}
    };
  });
}

function renderPricing(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  const isAuth=!!_authUser;
  const currentTier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  const email=_authUser?.email||'';
  ct.innerHTML=`<div class="pg-page">
    <div class="pg-hd"><h1 class="pg-title">Plans</h1><p class="pg-sub">Static corpus or living knowledge base.<br>Start free, upgrade when Noos should grow with you.</p></div>
    ${_tierCardsHTML(currentTier)}
    <div class="pg-self-host">
      <strong>Self-hosted?</strong> All features are free and unlimited. No cloud account needed. <code>pip install noosphere && noosphere serve</code>
    </div>
    ${isAuth?`<div class="pg-footer"><div class="pg-footer-email">${esc(email)}</div><button class="pg-footer-signout" id="pg-signout-btn">Sign Out</button></div>`:''}
  </div>`;
  _wireTierCardButtons(ct);
  document.getElementById('pg-signout-btn')?.addEventListener('click',signOut);
}

/* Paywall modal — opens when a Free user hits a Pro-gated feature, either
   proactively (pre-intercepted click on Compile etc.) or reactively (429
   quota_exceeded response). `reason` is a short headline explaining WHY
   this modal appeared; falls back to a generic upgrade prompt. */
function showProModal(reason){
  const isAuth=!!_authUser;
  const currentTier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  // Self-hosted (no auth wired) has no Pro concept — no-op.
  if(!isAuth && !reason)return;
  const existing=document.getElementById('pro-modal-overlay');
  if(existing)existing.remove();
  const overlay=document.createElement('div');
  overlay.id='pro-modal-overlay';
  overlay.className='pro-modal-overlay';
  overlay.innerHTML=`<div class="pro-modal">
    <button class="pro-modal-close" aria-label="Close">×</button>
    ${reason?`<div class="pro-modal-reason">${esc(reason)}</div>`:''}
    <h2 class="pro-modal-title">Upgrade to Pro</h2>
    <p class="pro-modal-sub">Turn your corpus into a living knowledge base — Noos keeps it evolving.</p>
    ${_tierCardsHTML(currentTier)}
  </div>`;
  document.body.appendChild(overlay);
  _wireTierCardButtons(overlay);
  const close=()=>overlay.remove();
  overlay.querySelector('.pro-modal-close').onclick=close;
  overlay.addEventListener('click',e=>{if(e.target===overlay)close()});
  document.addEventListener('keydown',function esc(e){if(e.key==='Escape'){close();document.removeEventListener('keydown',esc)}});
}

/* ── Account Settings ── */
async function renderAccount(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="pg-page"><div class="pg-hd"><h1 class="pg-title">Account</h1></div><div class="acct-loading">Loading...</div></div>`;
  let user={},usage={};
  try{
    const[mr,ur]=await Promise.all([fetch(`${API}/cloud/me`),fetch(`${API}/cloud/usage`)]);
    user=await mr.json();usage=await ur.json();
  }catch(e){}
  const tier=user.tier||'free';
  const email=user.email||_authUser?.email||'';
  const daily=usage.daily_usage||{};
  const res=usage.resources||{};
  const usageRows=Object.entries(daily).map(([action,v])=>{
    const pct=v.limit?Math.min(100,Math.round(v.used/v.limit*100)):0;
    return`<div class="acct-usage-row">
      <span class="acct-usage-label">${action}</span>
      <div class="acct-usage-bar"><div class="acct-usage-fill${pct>=90?' acct-usage-warn':''}" style="width:${pct}%"></div></div>
      <span class="acct-usage-num">${v.used} / ${v.limit}</span>
    </div>`;
  }).join('');
  const corporaRes=res.corpora||{};
  const queriesRes=res.queries_this_month||{};

  const initial=(email||'U')[0].toUpperCase();
  const avatar=_authUser?.user_metadata?.avatar_url;
  const name=_authUser?.user_metadata?.full_name||_authUser?.user_metadata?.name||email.split('@')[0]||'User';

  ct.innerHTML=`<div class="pg-page">
    <div class="acct-profile">
      ${avatar?`<img src="${esc(avatar)}" class="acct-avatar"/>`:`<span class="acct-avatar acct-avatar-init">${esc(initial)}</span>`}
      <div class="acct-profile-info">
        <div class="acct-profile-name">${esc(name)}</div>
        <div class="acct-profile-email">${esc(email)}</div>
      </div>
      <span class="acct-profile-tier sb-tier-badge sb-tier-${tier}">${tier==='pro'?'Pro':'Free'}</span>
    </div>
    <div class="acct-grid">
      <div class="acct-section">
        <h2 class="acct-section-title">Plan</h2>
        <div class="acct-plan-row">
          <span class="acct-plan-tier">${tier==='pro'?'Pro':'Free'}</span>
          ${user.subscription_status?`<span class="acct-plan-status">${user.subscription_status}</span>`:''}
        </div>
        ${tier==='free'?`<a href="#/pricing" class="acct-upgrade">Upgrade to Pro →</a>`:''}
        ${tier==='pro'?`<button class="acct-manage" id="acct-portal-btn">Manage subscription</button>`:''}
      </div>
      <div class="acct-section">
        <h2 class="acct-section-title">Resources</h2>
        <div class="acct-res-grid">
          <div class="acct-res-item"><span class="acct-res-val">${corporaRes.used||0}<span class="acct-res-lim"> / ${corporaRes.limit==='unlimited'||corporaRes.limit>=999999?'∞':corporaRes.limit||'—'}</span></span><span class="acct-res-label">Corpora</span></div>
          <div class="acct-res-item"><span class="acct-res-val">${queriesRes.used||0}<span class="acct-res-lim"> / ${queriesRes.limit>=999999?'∞':queriesRes.limit||'—'}</span></span><span class="acct-res-label">Queries this month</span></div>
        </div>
      </div>
    </div>
    <div class="acct-section">
      <h2 class="acct-section-title">Today's usage</h2>
      ${usageRows||'<div class="acct-empty">No activity yet today</div>'}
    </div>
    ${tier==='pro'?`<div class="acct-section"><h2 class="acct-section-title">Payouts</h2><p class="acct-sub">Earn from paid corpora. Consumers pay, you get 90%.</p><button class="acct-connect" id="acct-connect-btn">Set up payouts</button></div>`:''}
    <div class="acct-footer">
      <button class="acct-signout" id="acct-signout-btn">Sign out</button>
    </div>
  </div>`;

  document.getElementById('acct-portal-btn')?.addEventListener('click',async function(){
    this.disabled=true;this.textContent='Loading...';
    try{
      const r=await fetch(`${API}/cloud/create-portal-session`,{method:'POST'});
      const d=await r.json();
      if(d.url)window.location.href=d.url;
      else{toast(d.detail||'Failed');this.disabled=false;this.textContent='Manage subscription'}
    }catch(e){toast('Failed');this.disabled=false;this.textContent='Manage subscription'}
  });
  document.getElementById('acct-connect-btn')?.addEventListener('click',async function(){
    this.disabled=true;this.textContent='Loading...';
    try{
      const r=await fetch(`${API}/cloud/connect/onboard`,{method:'POST'});
      const d=await r.json();
      if(d.url)window.location.href=d.url;
      else{toast(d.detail||'Failed');this.disabled=false;this.textContent='Set up payouts'}
    }catch(e){toast('Failed');this.disabled=false;this.textContent='Set up payouts'}
  });
  document.getElementById('acct-signout-btn')?.addEventListener('click',signOut);
}

function toggleTheme(){if(isDark()){document.documentElement.classList.add('light');document.documentElement.classList.remove('dark');localStorage.setItem('noosphere-theme','light')}else{document.documentElement.classList.add('dark');document.documentElement.classList.remove('light');localStorage.setItem('noosphere-theme','dark')}}

document.addEventListener('DOMContentLoaded',async()=>{
  const sbToggle=()=>document.getElementById('sidebar').classList.toggle('collapsed');
  document.getElementById('sb-toggle')?.addEventListener('click',sbToggle);
  document.querySelector('.sb-logo')?.addEventListener('click',e=>{const sb=document.getElementById('sidebar');if(sb.classList.contains('collapsed')){e.preventDefault();sbToggle()}});
  document.getElementById('sb-new')?.addEventListener('click',()=>{_termCtx={};location.hash='#/main';if(location.hash==='#/main')renderHome()});
  await initAuth();renderAuthUI();
  window.addEventListener('hashchange',route);route()});
