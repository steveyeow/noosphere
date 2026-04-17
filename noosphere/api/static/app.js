/* Noosphere v9 — Terminal + Corpora + Network + Chat + Cloud Auth */
const API='/api/v1';
let _gAnim=null,_lpAnim=null,_termAnim=null,_files=[],_corpora=[],_chatH=[],_ownerName='',_firstName='';
let _cloudMode=false,_supabase=null,_authUser=null,_authSession=null;
const isDark=()=>document.documentElement.classList.contains('dark')||(!document.documentElement.classList.contains('light')&&window.matchMedia('(prefers-color-scheme: dark)').matches);
const PAL=['#e76f51','#2a9d8f','#264653','#e9c46a','#f4a261','#588157','#457b9d','#9b2226','#6d6875','#b56576','#355070','#6c757d','#e07a5f','#3d405b','#81b29a'];
const cC=n=>{let h=0;for(let i=0;i<n.length;i++)h=((h<<5)-h+n.charCodeAt(i))|0;return PAL[Math.abs(h)%PAL.length]};
const hR=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const fmtN=n=>{if(n>=1e6)return(n/1e6).toFixed(1).replace(/\.0$/,'')+'M';if(n>=1e4)return(n/1e3).toFixed(1).replace(/\.0$/,'')+'K';return n.toLocaleString()};
const cp=(t,b)=>{navigator.clipboard.writeText(t).then(()=>{if(b){const o=b.textContent;b.textContent='Copied!';setTimeout(()=>b.textContent=o,1200)}})};
function toast(msg,type='error'){const t=document.createElement('div');t.className='toast toast-'+type;t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.classList.add('show'),10);setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300)},4000)}

/* ── Cloud Auth (Supabase) ── */
async function initAuth(){
  try{
    const r=await fetch(`${API}/health`);const d=await r.json();
    // Check if server is in cloud mode by trying the cloud/me endpoint
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
  else if(h==='#/pricing')renderPricing();
  else if(h==='#/account')renderAccount();
  else if(h==='#/network'||h.startsWith('#/explore'))renderNet();
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
async function loadMe(){try{const r=await fetch(`${API}/me`);const d=await r.json();_ownerName=d.name||'';_firstName=_ownerName.includes(' ')?_ownerName.split(' ')[0]:(_ownerName.match(/^[A-Z][a-z]+/)||[_ownerName])[0]}catch(e){}}

/* ── Chat session persistence ── */
let _chatSessions=[];
async function loadChatSessions(){
  try{const r=await fetch(`${API}/chat-sessions?limit=20`);_chatSessions=await r.json()}catch(e){_chatSessions=[]}
  renderSBChats();
}
/* ── Noos icon (landing page logo SVG) ── */
const NOOS_ICON_SVG=`<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/><circle cx="18" cy="42" r="3" fill="currentColor" opacity="0.5"/><line x1="20" y1="24" x2="44" y2="20" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="20" y1="24" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="44" y1="20" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/><line x1="18" y1="42" x2="36" y2="42" stroke="currentColor" stroke-width="1.5" opacity="0.4"/></svg>`;
const NOOS_DOT=`<span class="term-noos-dot">●</span>`;
const PROMPT_CHEVRON=`<span class="term-user-chevron">❯</span>`;
function noosHd(){return `<div class="noos-hd">${NOOS_DOT}<span class="noos-nm">Noos</span></div>`}

/* ── Command picker ── */
const TERM_CMDS=[{cmd:'/upload',desc:'Add a file to a corpus'},{cmd:'/history',desc:'View recent conversations'},{cmd:'/new',desc:'Create a new corpus'},{cmd:'/help',desc:'Show all commands'}];
function showCmdPicker(input,matches){
  let p=document.getElementById('term-cmd-picker');
  if(!p){p=document.createElement('div');p.id='term-cmd-picker';p.className='term-cmd-picker';document.getElementById('term-input-area')?.appendChild(p)}
  if(!matches.length){p.style.display='none';return}
  p.style.display='block';
  p.innerHTML=matches.map((c,i)=>`<div class="term-cmd-item${i===0?' focused':''}" data-cmd="${c.cmd}"><span class="term-cmd-name">${c.cmd}</span><span class="term-cmd-desc">${c.desc}</span></div>`).join('');
  p.querySelectorAll('.term-cmd-item').forEach(item=>{item.onmousedown=e=>{e.preventDefault();input.value=item.dataset.cmd;hideCmdPicker();input.focus()}});
}
function hideCmdPicker(){const p=document.getElementById('term-cmd-picker');if(p)p.style.display='none'}

function renderSBChats(){
  const el=document.getElementById('sb-chats');if(!el)return;
  const chats=_chatSessions.slice(0,8);
  if(!chats.length){el.innerHTML='';return}
  el.innerHTML='<div class="sb-chats-lbl">Recent</div>'+chats.map(c=>`<a href="#/corpus/${c.corpus_id}?session=${c.id}" class="sb-chat-item" title="${esc(c.title||'')}">${esc(c.title||'Untitled')}</a>`).join('');
}
function setSBActive(h){document.getElementById('nav-corpora').classList.toggle('active',h==='#/corpora');document.getElementById('nav-explore').classList.toggle('active',h.startsWith('#/explore')||h==='#/network');const np=document.getElementById('nav-pricing');if(np)np.classList.toggle('active',h==='#/pricing');const na=document.getElementById('nav-account');if(na)na.classList.toggle('active',h==='#/account')}
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
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  const hour=new Date().getHours();
  const greet=hour<12?'Morning':hour<18?'Afternoon':'Evening';
  const totalDocs=_corpora.reduce((a,c)=>a+(c.document_count||0),0);
  const totalWords=_corpora.reduce((a,c)=>a+(c.word_count||0),0);
  const pubCount=_corpora.filter(c=>(c.access_level||'public')==='public').length;
  const statsText=_corpora.length?`${fmtN(_corpora.length)} corpora · ${fmtN(totalDocs)} docs · ${fmtN(totalWords)} words`:'No corpora yet';
  const statsText2=_corpora.length?`${pubCount} public · ${_corpora.length-pubCount} private`:'';
  const recentC=[..._corpora].sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||'')).slice(0,5);
  const recentRows=recentC.map(c=>`<div class="term-wrec-row"><a href="#/corpus/${c.id}" class="term-wrec-link">${esc(c.name)}</a><span class="term-wrec-meta">${fmtN(c.document_count||0)} docs</span></div>`).join('');

  ct.innerHTML=`<div class="term-full">
    <div class="term-top">
      <div class="term-welcome">
        <div class="term-wl">
          <canvas class="term-dragon" id="dragon-cv" width="60" height="60"></canvas>
          <div class="term-winfo">
            <div class="term-wname">Good ${greet.toLowerCase()}${_firstName?', '+_firstName:''}</div>
            <div class="term-wmeta">${statsText}</div>
            ${statsText2?`<div class="term-wmeta">${statsText2}</div>`:''}
          </div>
        </div>
        <div class="term-wsep"></div>
        <div class="term-wr">
          <div class="term-wlbl">Recent activity</div>
          ${recentRows||`<div class="term-wmeta">No corpora yet — start by adding one</div>`}
        </div>
      </div>
    </div>
    <div class="term-scroll" id="term-scroll">
      <div class="term-output" id="term-output"></div>
      <div class="term-input-area" id="term-input-area">
        <div class="term-input-wrap">
          <span class="term-user-chevron">❯</span>
          <span class="term-cursor">\u2588</span>
          <input type="text" class="term-input" id="term-input" placeholder="Paste a URL, upload a file, or ask a question" autofocus />
        </div>
      </div>
      <div class="term-hints" id="term-hints">
        <div class="term-sg" data-cmd="url"><span class="term-caret">/</span> Paste a link to import</div>
        <div class="term-sg" data-cmd="/upload"><span class="term-caret">/</span> upload — add a file</div>
        <div class="term-sg" data-cmd="/history"><span class="term-caret">/</span> history — recent chats</div>
        <div class="term-sg" data-cmd="/new"><span class="term-caret">/</span> new — create corpus</div>
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
  const hints=document.getElementById('term-hints');
  const cursorEl=document.querySelector('.term-cursor');
  _termCtx={};

  // Noos greeting
  const greetEl=document.createElement('div');greetEl.className='noos-msg';
  greetEl.innerHTML=`${NOOS_DOT}<span><span class="noos-nm">Noos</span><span class="noos-body">Hi, ${_firstName||'explorer'}. What would you like to add to Noosphere today?</span></span>`;
  output.appendChild(greetEl);

  input.addEventListener('focus',()=>{if(cursorEl)cursorEl.style.display='none'});
  input.addEventListener('blur',()=>{if(cursorEl&&!input.value)cursorEl.style.display='';hideCmdPicker()});
  input.addEventListener('input',()=>{
    if(cursorEl)cursorEl.style.display=input.value?'none':'';
    const v=input.value;
    if(v.startsWith('/')){const q=v.toLowerCase();showCmdPicker(input,TERM_CMDS.filter(c=>c.cmd.startsWith(q)))}
    else hideCmdPicker();
  });

  document.querySelectorAll('.term-sg').forEach(s=>{s.onclick=()=>{
    const cmd=s.dataset.cmd;
    if(cmd==='/upload'){input.value='';hints.style.display='none';document.getElementById('term-input-area').style.display='none';showTermUpload(output,input,hints);return}
    if(cmd==='url'){input.value='';input.placeholder='Paste a URL and press Enter...';input.focus();return}
    input.value=cmd;input.focus();
  }});

  let _sending=false;
  async function sendInput(){
    if(_sending)return;
    const val=input.value.trim();if(!val)return;
    if(val.toLowerCase()==='/upload'){input.value='';hints.style.display='none';document.getElementById('term-input-area').style.display='none';showTermUpload(output,input,hints);return}
    if(val.toLowerCase()==='/history'){
      input.value='';hints.style.display='none';
      await loadChatSessions();
      if(!_chatSessions.length){addLine(output,'resp','No chat history yet.')}
      else{addLine(output,'resp','Recent conversations:');_chatSessions.slice(0,10).forEach(c=>{const el=document.createElement('div');el.className='term-line term-option';el.innerHTML=NOOS_DOT+'<span><span style="color:var(--tx3);margin-right:8px">'+esc(c.corpus_name||'')+'</span>'+esc(c.title||'Untitled')+'</span>';el.onclick=()=>{location.hash='#/corpus/'+c.corpus_id+'?session='+c.id};output.appendChild(el)})}
      input.focus();return;
    }
    if(val.toLowerCase()==='/help'){
      input.value='';hints.style.display='none';
      [['URL','Paste any URL to import a page'],['  /upload','Add a file to a corpus'],['  /history','View recent conversations'],['  /new','Create a new corpus']].forEach(([cmd,desc])=>addLine(output,'hint',cmd.padEnd(12)+desc));
      input.focus();return;
    }
    if(val.toLowerCase()==='/new'){
      input.value='';hints.style.display='none';
      addLine(output,'resp','Enter a name for the new corpus:');
      document.getElementById('term-input-area').style.display='none';
      const wrap=document.createElement('div');wrap.style.cssText='margin-left:18px;margin-top:8px;display:flex;gap:8px;align-items:center';
      wrap.innerHTML='<input type="text" class="term-input" id="new-corpus-input" placeholder="Corpus name..." style="flex:1;font-size:13px;border:1px solid var(--brd);border-radius:8px;padding:6px 10px;background:var(--bg2)" /><button class="btn-sm" id="new-corpus-btn">Create</button>';
      output.appendChild(wrap);
      const ni=document.getElementById('new-corpus-input');ni.focus();
      async function doCreate(){const name=ni.value.trim();if(!name)return;wrap.remove();document.getElementById('term-input-area').style.display='';try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,access_level:'public'})});const c=await r.json();await loadC();addLine(output,'card',null,null,{type:'card',label:name,status:'CREATED',detail:'New corpus created',corpus_id:c.id});renderSBChats()}catch(e){addLine(output,'resp','Failed: '+e.message)}input.focus()}
      document.getElementById('new-corpus-btn').onclick=doCreate;ni.onkeydown=e=>{if(e.key==='Enter')doCreate();if(e.key==='Escape'){wrap.remove();document.getElementById('term-input-area').style.display='';input.focus()}};
      return;
    }
    _sending=true;input.value='';input.disabled=true;
    hints.style.display='none';
    addLine(output,'prompt',val);
    const loadId='ld-'+Date.now();
    addLine(output,'resp','Processing...',loadId);
    try{
      const r=await fetch(`${API}/terminal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:val,context:_termCtx})});
      const d=await r.json();
      document.getElementById(loadId)?.remove();
      _termCtx=d.context||{};
      for(const line of(d.lines||[]))addLine(output,line.type,null,null,line);
      if(d.context?.action==='open_write'){document.getElementById('term-input-area').style.display='none';showTermWrite(output,input,hints)}
    }catch(err){document.getElementById(loadId)?.remove();addLine(output,'resp','Error: '+err.message)}
    input.disabled=false;input.focus();
    _sending=false;
  }
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sendInput()}});
}

function addLine(container,type,text,id,line){
  const el=document.createElement('div');
  if(id)el.id=id;
  const ln=line||{};
  if(type==='prompt'){el.className='term-line term-prompt';el.innerHTML=PROMPT_CHEVRON+'<span class="term-prompt-text">'+esc(text||ln.text||'')+'</span>'}
  else if(type==='resp'){el.className='term-line term-resp';el.innerHTML=NOOS_DOT+'<span>'+esc(text||ln.text||'')+'</span>'}
  else if(type==='hint'){el.className='term-line term-resp';el.style.opacity='.5';el.innerHTML=NOOS_DOT+'<span>'+esc(ln.text||'')+'</span>'}
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

/* ══════ TERMINAL UPLOAD ══════ */
function showTermUpload(output,input,hints){
  const wrap=document.createElement('div');wrap.className='term-upload-wrap';
  let _uFiles=[];
  wrap.innerHTML=`<div class="term-upload-dz" id="tu-dz"><input type="file" id="tu-fi" multiple accept=".md,.txt,.text,.html,.htm,.pdf,.docx,.csv,.json,.jsonl" hidden /><div class="term-upload-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--tx3)" stroke-width="1.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></div><div class="term-upload-txt">Drop files here, or <span class="term-upload-browse">browse</span></div><div class="term-upload-formats">PDF, Markdown, DOCX, TXT, CSV, JSON</div></div><div class="term-upload-list" id="tu-list"></div><div class="term-upload-origin"><label for="tu-sk">Origin</label><select id="tu-sk"><option value="user_original" selected>My original content</option><option value="external_public">Public external reference</option><option value="external_subscription">Subscription / paid external</option></select></div><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Upload & Index</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div>`;
  output.appendChild(wrap);
  const _sc=document.getElementById('term-scroll');if(_sc)_sc.scrollTop=_sc.scrollHeight;

  const dz=wrap.querySelector('#tu-dz'),fi=wrap.querySelector('#tu-fi'),list=wrap.querySelector('#tu-list');
  const goBtn=wrap.querySelector('#tu-go'),cancelBtn=wrap.querySelector('#tu-cancel');

  function refreshList(){
    list.innerHTML=_uFiles.map((f,i)=>`<div class="term-upload-file"><span>${esc(f.name)}</span><span style="display:flex;align-items:center;gap:8px"><span class="term-upload-size">${(f.size/1024).toFixed(1)}KB</span><button class="term-upload-remove" data-idx="${i}" title="Remove">&times;</button></span></div>`).join('');
    list.querySelectorAll('.term-upload-remove').forEach(btn=>{btn.onclick=e=>{e.stopPropagation();_uFiles.splice(parseInt(btn.dataset.idx),1);refreshList()}});
    goBtn.disabled=!_uFiles.length;
  }
  function addFiles(fl){for(const f of fl)_uFiles.push(f);refreshList()}

  dz.onclick=()=>fi.click();
  dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag-over')};
  dz.ondragleave=()=>dz.classList.remove('drag-over');
  dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag-over');addFiles(e.dataTransfer.files)};
  fi.onchange=()=>{addFiles(fi.files);fi.value=''};

  cancelBtn.onclick=()=>{wrap.remove();hints.style.display='';document.getElementById('term-input-area').style.display='';input.focus()};

  goBtn.onclick=async()=>{
    if(!_uFiles.length)return;
    goBtn.disabled=true;goBtn.textContent='Uploading...';
    cancelBtn.style.display='none';

    let cid;
    await loadC();
    if(_corpora.length===1){cid=_corpora[0].id}
    else if(_corpora.length===0){
      try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});const c=await r.json();cid=c.id;await loadC()}catch(e){addLine(output,'resp','Failed to create corpus.');wrap.remove();input.focus();return}
    }else{
      const picked=await pickCorpusInline(output);
      if(!picked){wrap.remove();hints.style.display='';document.getElementById('term-input-area').style.display='';input.focus();return}
      cid=picked;
    }

    const fd=new FormData();
    for(const f of _uFiles)fd.append('files',f);
    const _sk=wrap.querySelector('#tu-sk')?.value||'user_original';
    fd.append('source_kind',_sk);
    try{
      const r=await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
      const d=await r.json();
      wrap.remove();
      addLine(output,'resp',`Uploaded ${d.uploaded||_uFiles.length} file${_uFiles.length>1?'s':''}`);
    }catch(e){wrap.remove();document.getElementById('term-input-area').style.display='';addLine(output,'resp','Upload failed: '+e.message);input.focus();return}

    document.getElementById('term-input-area').style.display='';
    addLine(output,'resp','Indexing...');
    try{
      const r=await fetch(`${API}/corpora/${cid}/index`,{method:'POST'});
      const d=await r.json();
      if(!r.ok){addLine(output,'resp','Indexing failed: '+(d.detail||r.statusText));input.focus();return}
      addLine(output,'resp',`Indexed: ${d.chunk_count||'?'} chunks`);
      const corpus=_corpora.find(c=>c.id===cid);
      addLine(output,'card',null,null,{type:'card',label:'Files Added',status:'READY',detail:`${corpus?corpus.name:'My Knowledge'}`,val:`${_uFiles.length} file${_uFiles.length>1?'s':''} uploaded & indexed`,corpus_id:cid});
      addLine(output,'resp','Agents can now cite this content.');
      await loadC();
    }catch(e){addLine(output,'resp','Indexing failed: '+e.message)}
    input.focus();
  };
}

/* ══════ TERMINAL INLINE WRITE ══════ */
function showTermWrite(output,input,hints){
  const wrap=document.createElement('div');wrap.className='term-write-wrap';
  wrap.innerHTML='<input type="text" class="term-write-title" id="tw-title" placeholder="Title" /><textarea class="term-write-body" id="tw-body" placeholder="Write your knowledge here... (Markdown supported)" rows="6"></textarea><div class="term-write-actions"><button class="btn-sm" id="tw-save">Save & Index</button><button class="btn-sm-ghost" id="tw-cancel">Cancel</button></div>';
  output.appendChild(wrap);
  const _sc=document.getElementById('term-scroll');if(_sc)_sc.scrollTop=_sc.scrollHeight;
  wrap.querySelector('#tw-title').focus();

  function restoreInput(){document.getElementById('term-input-area').style.display='';if(hints)hints.style.display='';if(input)input.focus()}

  wrap.querySelector('#tw-cancel').onclick=()=>{wrap.remove();restoreInput()};
  wrap.querySelector('#tw-save').onclick=async()=>{
    const title=wrap.querySelector('#tw-title').value.trim(),body=wrap.querySelector('#tw-body').value.trim();
    if(!title||!body){toast('Title and content are required');return}
    const btn=wrap.querySelector('#tw-save');btn.disabled=true;btn.textContent='Saving...';
    await loadC();let cid;
    if(_corpora.length===0){try{const r=await fetch(API+'/corpora',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});cid=(await r.json()).id;await loadC()}catch(e){toast('Failed to create corpus');btn.disabled=false;btn.textContent='Save & Index';return}}
    else if(_corpora.length===1){cid=_corpora[0].id}
    else{const picked=await pickCorpusInline(output);if(!picked){btn.disabled=false;btn.textContent='Save & Index';return}cid=picked}
    const fd=new FormData();fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+body],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');
    try{await fetch(API+'/corpora/'+cid+'/upload',{method:'POST',body:fd})}catch(e){toast('Upload failed');btn.disabled=false;btn.textContent='Save & Index';return}
    btn.textContent='Indexing...';
    try{await fetch(API+'/corpora/'+cid+'/index',{method:'POST'})}catch(e){}
    wrap.remove();restoreInput();
    const corpus=_corpora.find(c=>c.id===cid);
    addLine(output,'resp','Saved: "'+title+'"');
    addLine(output,'card',null,null,{type:'card',label:'Source Added',status:'READY',detail:(corpus?corpus.name:'Corpus')+' — '+title,corpus_id:cid});
    await loadC();
  };
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

function renderMCList(host){
  const el=document.getElementById('mc-content');
  if(!_corpora.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet. Click <strong>+ New</strong> to add your knowledge.</div>';return}
  el.className='mc-list';
  el.innerHTML=_corpora.map(c=>{
    const al=c.access_level||'public';
    const tg=Array.isArray(c.tags)?c.tags:[];
    const desc=c.description||'';
    const updatedLabel=_timeAgo(c.updated_at);
    return`<div class="mc-card" data-id="${c.id}">
      <div class="mc-card-body">
        <div class="mc-card-top"><a class="mc-card-name" href="#/corpus/${c.id}">${esc(c.name)}</a><span class="mc-badge mc-badge-${al}">${al==='token'?'Token-gated':al.charAt(0).toUpperCase()+al.slice(1)}</span></div>
        ${desc?'<div class="mc-card-desc">'+esc(desc)+'</div>':''}
        <div class="mc-card-meta">${c.document_count?'<span class="mc-meta-item"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> '+c.document_count+'</span>':''}${c.word_count?'<span class="mc-meta-item"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7V4a2 2 0 0 1 2-2h8.5L20 7.5V20a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3"/><polyline points="14 2 14 8 20 8"/><line x1="2" y1="15" x2="12" y2="15"/></svg> '+(c.word_count).toLocaleString()+'</span>':''}${tg.length?'<span class="mc-meta-tags">'+tg.slice(0,3).map(t=>'<span class="mc-meta-tag">'+esc(t)+'</span>').join('')+'</span>':''}${updatedLabel?'<span class="mc-meta-item mc-meta-updated">Updated '+updatedLabel+'</span>':''}</div>
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
  panel.innerHTML=`<div class="cv-add-body"><input type="text" class="fi" id="cc-topic" placeholder='Topic to compile, e.g. "pricing strategy"' style="font-size:13px" /><div style="display:flex;gap:8px;align-items:center;margin-top:8px"><label style="font-size:11px;color:var(--tx3)">Retrieval breadth:</label><input type="number" class="fi" id="cc-topk" value="10" min="3" max="30" style="width:60px;font-size:12px" /></div><div style="font-size:11px;color:var(--tx3);margin-top:6px;line-height:1.5">Retrieves top passages from your Sources and uses an LLM to synthesize a concept note. Requires chat API keys.</div><div class="cv-add-actions"><button class="btn-sm" id="cc-go">✨ Compile</button><button class="btn-sm-ghost" id="cc-cancel">Cancel</button></div></div>`;
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
    }catch(e){toast('Compile failed: '+e.message);btn.disabled=false;btn.textContent='✨ Compile'}
  };
}

/* ══════ INLINE ADD DOCUMENT (Raw ingestion only — tabs for Upload/Write/URL/Archive/RSS) ══════ */
function showCorpusAddDoc(corpusId){
  const container=document.getElementById('cv-raw-docs')||document.getElementById('cv-docs');
  if(!container)return;
  if(document.getElementById('cv-add-panel'))return;
  const panel=document.createElement('div');panel.id='cv-add-panel';panel.className='cv-add-panel';
  panel.innerHTML=`<div class="cv-add-tabs"><button class="cv-add-tab active" data-tab="upload">Upload Files</button><button class="cv-add-tab" data-tab="write">Write</button><button class="cv-add-tab" data-tab="url">From URL</button><button class="cv-add-tab" data-tab="urls">Batch URLs</button><button class="cv-add-tab" data-tab="feed">RSS Feed</button><button class="cv-add-tab" data-tab="archive">Import Archive</button></div><div class="cv-add-body" id="cv-add-body"></div>`;
  container.parentNode.insertBefore(panel,container);

  const body=panel.querySelector('#cv-add-body');
  const tabs=panel.querySelectorAll('.cv-add-tab');
  let _files=[];

  function setTab(tab){
    tabs.forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
    if(tab==='upload'){
      body.innerHTML=`<div class="cv-add-dz" id="cv-add-dz"><input type="file" id="cv-add-fi" multiple accept=".md,.txt,.text,.html,.htm,.pdf,.docx,.csv,.json,.jsonl" hidden /><div style="color:var(--tx3);font-size:13px">Drop files here, or <span style="color:var(--tx);font-weight:600;cursor:pointer;text-decoration:underline;text-underline-offset:2px" id="cv-add-browse">browse</span></div><div style="font-size:11px;color:var(--tx3);margin-top:4px">PDF, Markdown, DOCX, TXT, CSV, JSON</div><div id="cv-add-flist"></div></div><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go" disabled>Upload & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
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
        try{await fetch(`${API}/corpora/${corpusId}/upload`,{method:'POST',body:fd})}catch(e){toast('Upload failed');goBtn.disabled=false;goBtn.textContent='Upload & Index';return}
        goBtn.textContent='Indexing...';
        try{await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'})}catch(e){}
        _files=[];panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='write'){
      body.innerHTML=`<input type="text" class="term-write-title" id="cv-add-title" placeholder="Title" style="margin-bottom:6px" /><textarea class="term-write-body" id="cv-add-text" placeholder="Write your knowledge here... (Markdown supported)" rows="6" style="min-height:100px"></textarea><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Save & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-title').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const title=body.querySelector('#cv-add-title').value.trim(),text=body.querySelector('#cv-add-text').value.trim();
        if(!title||!text){toast('Title and content are required');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Saving...';
        const fd=new FormData();fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+text],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-')+'.md');
        try{await fetch(`${API}/corpora/${corpusId}/upload`,{method:'POST',body:fd})}catch(e){toast('Upload failed');btn.disabled=false;btn.textContent='Save & Index';return}
        btn.textContent='Indexing...';
        try{await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'})}catch(e){}
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='url'){
      body.innerHTML=`<input type="text" class="fi" id="cv-add-url" placeholder="https://example.com/article" style="font-size:13px" /><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Fetch & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-url').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const url=body.querySelector('#cv-add-url').value.trim();
        if(!url){toast('Enter a URL');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Fetching...';
        try{const r=await fetch(`${API}/corpora/${corpusId}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});if(!r.ok)throw new Error((await r.json()).detail||'Failed')}catch(e){toast('Fetch failed: '+e.message);btn.disabled=false;btn.textContent='Fetch & Index';return}
        btn.textContent='Indexing...';
        try{await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'})}catch(e){}
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='urls'){
      body.innerHTML=`<textarea class="term-write-body" id="cv-add-urls" placeholder="Paste URLs, one per line (max 40)" rows="6" style="min-height:80px;font-size:12px;font-family:monospace"></textarea><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Fetch All & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-urls').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const raw=body.querySelector('#cv-add-urls').value.trim();
        const urls=raw.split('\n').map(u=>u.trim()).filter(u=>u&&u.startsWith('http'));
        if(!urls.length){toast('Enter at least one URL');return}
        if(urls.length>40){toast('Maximum 40 URLs per batch');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent=`Fetching ${urls.length} URLs...`;
        try{const r=await fetch(`${API}/corpora/${corpusId}/ingest-urls`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})});if(!r.ok)throw new Error((await r.json()).detail||'Failed');const d=await r.json();toast(`Ingested ${d.ingested||0} pages${d.failed?' ('+d.failed+' failed)':''}`,'success')}catch(e){toast('Batch ingest failed: '+e.message);btn.disabled=false;btn.textContent='Fetch All & Index';return}
        btn.textContent='Indexing...';
        try{await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'})}catch(e){}
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='feed'){
      body.innerHTML=`<input type="text" class="fi" id="cv-add-feed" placeholder="https://example.com/feed.xml" style="font-size:13px" /><div style="display:flex;gap:8px;align-items:center;margin-top:6px"><label style="font-size:11px;color:var(--tx3)">Max items:</label><input type="number" class="fi" id="cv-add-feed-max" value="25" min="1" max="100" style="width:60px;font-size:12px" /></div><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go">Fetch Feed & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div>`;
      body.querySelector('#cv-add-feed').focus();
      body.querySelector('#cv-add-cancel').onclick=()=>panel.remove();
      body.querySelector('#cv-add-go').onclick=async()=>{
        const feedUrl=body.querySelector('#cv-add-feed').value.trim();
        const maxItems=parseInt(body.querySelector('#cv-add-feed-max').value)||25;
        if(!feedUrl){toast('Enter a feed URL');return}
        const btn=body.querySelector('#cv-add-go');btn.disabled=true;btn.textContent='Fetching feed...';
        try{const r=await fetch(`${API}/corpora/${corpusId}/ingest-feed`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feed_url:feedUrl,max_items:maxItems})});if(!r.ok)throw new Error((await r.json()).detail||'Failed');const d=await r.json();toast(`Fetched ${d.fetched||0} entries, ingested ${d.ingested||0}`,'success')}catch(e){toast('Feed ingest failed: '+e.message);btn.disabled=false;btn.textContent='Fetch Feed & Index';return}
        panel.remove();renderCorpus(corpusId);
      };
    } else if(tab==='archive'){
      body.innerHTML=`<div style="display:flex;flex-direction:column;gap:10px"><div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><label style="font-size:12px;color:var(--tx2);display:flex;align-items:center;gap:6px"><input type="radio" name="arc-kind" value="twitter" checked /> Twitter / X data export</label><label style="font-size:12px;color:var(--tx2);display:flex;align-items:center;gap:6px"><input type="radio" name="arc-kind" value="notion" /> Notion workspace export</label></div><input type="file" id="cv-arc-fi" accept=".zip" style="font-size:12px" /><div style="font-size:11px;color:var(--tx3);line-height:1.5">These are your own exports from services you own, so all items are tagged as <strong>your original content</strong>. Twitter: upload the ZIP you get from twitter.com/settings/download_your_data. Notion: Settings → Data export (Markdown &amp; CSV).</div><div class="cv-add-actions"><button class="btn-sm" id="cv-add-go" disabled>Import & Index</button><button class="btn-sm-ghost" id="cv-add-cancel">Cancel</button></div></div>`;
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
        }catch(e){toast('Import failed: '+e.message,'error');goBtn.disabled=false;goBtn.textContent='Import & Index';return}
        panel.remove();renderCorpus(corpusId);
      };
    }
  }
  tabs.forEach(t=>t.onclick=()=>setTab(t.dataset.tab));
  setTab('upload');
}

/* ══════ CORPUS DETAIL + CHAT ══════ */
async function renderCorpus(id,sessionId){
  stopAll();_chatH=[];const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.innerHTML='<div class="empty">Loading...</div>';
  let c;try{const r=await fetch(`${API}/corpora/${id}`);if(!r.ok){const e=await r.json().catch(()=>({}));ct.innerHTML=`<a class="cv-back" href="#/corpora">&larr; Corpora</a><div class="empty" style="margin-top:40px">${r.status===401?'Access denied — this corpus requires authentication':r.status===403?e.detail||'Access denied':'Corpus not found'}</div>`;hideRP();return}c=await r.json()}catch(e){ct.innerHTML='<div class="empty">Not found</div>';hideRP();return}
  let docs=[];try{const r=await fetch(`${API}/corpora/${id}/documents`);if(r.ok)docs=await r.json()}catch(e){}
  let an={};try{const r=await fetch(`${API}/corpora/${id}/analytics?limit=5`);if(r.ok)an=await r.json()}catch(e){}
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
  const wikiEmpty='<div class="empty">No concept notes yet — ✨ Compile to synthesize from your sources.</div>';
  const rawEmpty='<div class="empty">No sources yet — + Add to import URLs, upload files, or import an archive.</div>';
  ct.innerHTML=`<div class="cv-layout"><div class="cv-scroll"><div class="cv-header"><div class="cv-header-top"><a class="cv-back" href="#/corpora">&larr; Corpora</a></div><div class="cv-identity"><h1 class="cv-name">${esc(c.name)}</h1><span class="mc-badge mc-badge-${al}">${badgeLabel}</span></div><div class="cv-desc-wrap">${c.description?`<p class="cv-desc" id="cv-desc">${esc(c.description)}</p>`:`<p class="cv-desc cv-desc-empty" id="cv-desc">Add a description...</p>`}<button class="cv-desc-edit-btn" id="cv-desc-edit" title="Edit description"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></div>${tg.length?`<div class="cv-tags">${tg.map(t=>`<span class="mc-meta-tag">${esc(t)}</span>`).join('')}</div>`:''}</div><div class="cv-sec cv-sec-wiki"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Wiki</span><span class="cv-st-sub">${wikiDocs.length?wikiDocs.length+' · AI synthesis':'AI synthesis'}</span></div><button class="btn-add" id="cv-compile-btn">✨ Compile</button></div><div id="cv-wiki-docs">${wikiDocs.length===0?wikiEmpty:wikiDocs.map(docItemHTML).join('')}</div></div><div class="cv-sec cv-sec-raw"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Sources</span><span class="cv-st-sub">${rawDocs.length?rawDocs.length+' · substrate':'substrate'}</span></div><button class="btn-add" id="cv-raw-add">+ Add</button></div><div id="cv-raw-docs">${rawDocs.length===0?rawEmpty:rawDocs.map(docItemHTML).join('')}</div></div><div class="chat-area" id="chat-area"></div></div><div id="cv-chat-bar" class="cv-chat-bar"><div class="composer"><textarea class="composer-input" id="c-ci" placeholder="Ask about ${esc(c.name)}…" rows="1"></textarea><div class="composer-toolbar"><button class="composer-send" id="c-send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></div></div></div></div>`;
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
  document.getElementById('cv-compile-btn').onclick=()=>showCorpusCompile(id);
  document.getElementById('cv-raw-add').onclick=()=>showCorpusAddDoc(id);
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
  setupCorpusInteract(id,sessionId);
}

const ENTITY_KIND_ICON={person:'👤',concept:'💡',work:'📚',place:'📍'};
async function loadCorpusEntities(corpusId){
  const list=document.getElementById('cv-entities-list');if(!list)return;
  try{
    const r=await fetch(`${API}/corpora/${corpusId}/entities`);
    if(!r.ok){list.innerHTML='<div class="empty" style="font-size:12px">Failed to load</div>';return}
    const d=await r.json();
    const ents=(d.entities||[]).filter(e=>e.mention_count>0);
    if(!ents.length){list.innerHTML='<div class="empty" style="font-size:12px;color:var(--tx3)">No entities extracted yet — click ⚡ Extract to identify people, companies, and concepts mentioned in your documents.</div>';return}
    // Group by kind
    const byKind={};
    for(const e of ents){(byKind[e.kind]=byKind[e.kind]||[]).push(e)}
    const order=['person','concept','work','place'];
    list.innerHTML=order.filter(k=>byKind[k]).map(k=>{
      const items=byKind[k].sort((a,b)=>b.mention_count-a.mention_count).slice(0,30);
      return `<div class="cv-ent-group"><div class="cv-ent-kind">${ENTITY_KIND_ICON[k]||'•'} ${k}s</div><div class="cv-ent-row">${items.map(e=>`<a class="cv-ent-chip" href="#/corpus/${corpusId}/entity/${e.id}" title="${e.mention_count} mention${e.mention_count===1?'':'s'}">${esc(e.canonical_name)}<span class="cv-ent-cnt">${e.mention_count}</span></a>`).join('')}</div></div>`;
    }).join('');
  }catch(e){list.innerHTML='<div class="empty" style="font-size:12px">Failed to load</div>'}
}

function showEntitiesModal(corpusId,entities){
  const byKind={};
  for(const e of entities){if(e.mention_count>0)(byKind[e.kind]=byKind[e.kind]||[]).push(e)}
  const order=['person','concept','work','place'];
  const sections=order.filter(k=>byKind[k]).map(k=>{
    const items=byKind[k].sort((a,b)=>b.mention_count-a.mention_count);
    return `<div class="cv-ent-group"><div class="cv-ent-kind">${ENTITY_KIND_ICON[k]||'•'} ${k}s</div><div class="cv-ent-row">${items.map(e=>`<a class="cv-ent-chip" href="#/corpus/${corpusId}/entity/${e.id}"><span>${esc(e.canonical_name)}</span><span class="cv-ent-cnt">${e.mention_count}</span></a>`).join('')}</div></div>`;
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
  const kindIcon=ENTITY_KIND_ICON[ent.kind]||'•';
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
    : (canCompile?`<div class="ep-compile-empty"><button class="btn-sm" id="ep-compile-btn">⚡ ${compileBtnLabel}</button><span class="ep-compile-hint">Synthesize a summary from the ${ent.doc_count} related doc${ent.doc_count===1?'':'s'}</span></div>`:'');
  ct.innerHTML=`<div class="ep-wrap"><a class="cv-back" href="#/corpus/${corpusId}">&larr; ${esc(c?.name||'Corpus')}</a><div class="ep-header"><div class="ep-kind">${kindIcon} ${esc(ent.kind)}</div><h1 class="ep-name">${esc(ent.canonical_name)}</h1>${aliases.length?`<div class="ep-aliases">also known as ${aliases.map(a=>`<span class="ep-alias">${esc(a)}</span>`).join(', ')}</div>`:''}<div class="ep-stats"><span><strong>${ent.doc_count||0}</strong> document${ent.doc_count===1?'':'s'}</span>${ent.authored_by?.length?`<span>${ent.authored_by.length} authored</span>`:''}${ent.participated?.length?`<span>${ent.participated.length} participated</span>`:''}${ent.mentioned_in?.length?`<span>${ent.mentioned_in.length} mentioned</span>`:''}</div></div>${compiledBlock}${buckets.length?bucketHTML:'<div class="empty">No documents reference this entity yet.</div>'}</div>`;

  async function doCompile(btnId){
    const btn=document.getElementById(btnId);if(!btn)return;
    btn.disabled=true;const orig=btn.textContent;btn.textContent='Compiling...';
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/entities/${entityId}/compile`,{method:'POST'});
      if(!r.ok){const d=await r.json().catch(()=>({}));toast('Compile failed: '+(d.detail||'error'),'error');btn.disabled=false;btn.textContent=orig;return}
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
      if(body.content){btn.textContent='Re-indexing...';try{await fetch(`${API}/corpora/${corpusId}/index`,{method:'POST'})}catch(e){}}
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
    try{const r=await fetch(`${API}/corpora/${id}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,history:_chatH,top_k:5,session_id:_sessionId||undefined})});const d=await r.json();document.getElementById('c-ld')?.remove();_chatH.push({role:'assistant',content:d.response});
      if(d.session_id)_sessionId=d.session_id;
      loadChatSessions();
      appendAssistantChatBlock(area,d.response,d.citations||[],id,msg,_sessionId)}
    catch(e){document.getElementById('c-ld')?.remove();area.innerHTML+=`<div class="chat-msg assistant">${noosHd()}<span style="color:var(--tx3)">Failed. Check LLM API keys.</span></div>`}send.disabled=false;area.scrollTop=area.scrollHeight}
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
    <div class="rp-sec"><div class="rp-lbl">Details</div>${c.author_name?`<div class="rp-detail-row"><span class="rp-detail-label">Author</span><span>${esc(c.author_name)}</span></div>`:''}${c.embedding_model?`<div class="rp-detail-row"><span class="rp-detail-label">Model</span><span>${esc(c.embedding_model)}</span></div>`:''}<div class="rp-detail-row"><span class="rp-detail-label">Status</span><span>${esc(c.status)}</span></div><div class="rp-detail-row rp-handles-row" id="rp-handles-row"><span class="rp-detail-label">Handles</span><span id="rp-handles-view">${(Array.isArray(c.owned_handles)&&c.owned_handles.length)?c.owned_handles.map(h=>`<span class="cv-handle-tag">${esc(h)}</span>`).join(' '):'<span style="color:var(--tx3);font-style:italic">none set</span>'} <a href="#" class="rp-subtle-link" id="rp-handles-edit">edit</a></span></div></div>
    <div class="rp-sec"><div class="rp-lbl">Entities</div><div class="rp-entities-row" id="rp-entities-row"><span style="font-size:12px;color:var(--tx3)">Loading…</span></div></div>
    <div class="rp-sec rp-sec-maint"><div class="rp-lbl">Maintenance</div><div class="rp-maint-row"><a href="#" class="rp-subtle-link" id="rp-reindex">Re-index</a><a href="#" class="rp-subtle-link" id="rp-export">Export</a><a href="#" class="rp-subtle-link rp-danger" id="rp-delete">Delete corpus</a></div></div>`;

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
        row.innerHTML=`<span style="font-size:12px;color:var(--tx3)">None yet</span> <a href="#" class="rp-subtle-link" id="rp-extract-btn">⚡ Extract with AI</a>`;
      }else{
        row.innerHTML=`<span style="font-size:12px;color:var(--tx2)"><strong>${shown}</strong> entities</span> <a href="#" class="rp-subtle-link" id="rp-browse-ent">browse</a> · <a href="#" class="rp-subtle-link" id="rp-extract-btn">⚡ Re-extract</a>`;
      }
      const extractBtn=document.getElementById('rp-extract-btn');
      if(extractBtn)extractBtn.onclick=async(ev)=>{
        ev.preventDefault();extractBtn.textContent='Extracting…';
        try{
          const rr=await fetch(`${API}/corpora/${c.id}/extract-entities`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:50})});
          if(!rr.ok)throw new Error((await rr.json().catch(()=>({}))).detail||'Failed');
          const dd=await rr.json();
          toast(`Enriched ${dd.enriched||0} doc${dd.enriched===1?'':'s'}${dd.remaining?', '+dd.remaining+' remaining':''}`,'success');
          renderCorpus(c.id);
        }catch(e){toast('Extract failed: '+e.message,'error');extractBtn.textContent='⚡ Extract with AI'}
      };
      const browseBtn=document.getElementById('rp-browse-ent');
      if(browseBtn)browseBtn.onclick=(ev)=>{ev.preventDefault();showEntitiesModal(c.id,ents)};
    }catch(e){row.innerHTML='<span style="font-size:12px;color:var(--tx3)">Failed to load</span>'}
  })();

  /* Maintenance row */
  document.getElementById('rp-reindex').onclick=async(e)=>{
    e.preventDefault();
    const btn=document.getElementById('rp-reindex');const orig=btn.textContent;btn.textContent='Indexing…';
    try{await fetch(`${API}/corpora/${c.id}/index`,{method:'POST'});renderCorpus(c.id)}
    catch(err){toast('Re-index failed');btn.textContent=orig}
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
function renderPricing(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  const isAuth=!!_authUser;
  const currentTier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  const email=_authUser?.email||'';
  ct.innerHTML=`<div class="pg-page">
    <div class="pg-hd"><h1 class="pg-title">Plans</h1><p class="pg-sub">Publish your knowledge. Grow your network.<br>Start free, upgrade when you need more.</p></div>
    <div class="pg-cards">
      <div class="pg-card${currentTier==='free'?' pg-current':''}">
        <div class="pg-tier-row"><span class="pg-tier">Free</span></div>
        <div class="pg-price"><span class="pg-amt">$0</span><span class="pg-period">/mo</span></div>
        <div class="pg-desc">Get started, no credit card needed</div>
        <ul class="pg-features">
          <li>1 corpus, 100 documents</li>
          <li>50 searches per day</li>
          <li>20 chat messages per day</li>
          <li>1,000 queries per month</li>
          <li>5 URL imports per day</li>
        </ul>
        ${currentTier==='free'?'<div class="pg-badge">Current plan</div>':''}
      </div>
      <div class="pg-card pg-card-pro${currentTier==='pro'?' pg-current':''}">
        <div class="pg-tier-row"><span class="pg-tier">Pro</span>${currentTier==='pro'?'<span class="pg-tier-badge">Current</span>':''}</div>
        <div class="pg-price"><span class="pg-amt">$9</span><span class="pg-period">/mo</span></div>
        <div class="pg-desc">For power users who build and share knowledge</div>
        <ul class="pg-features">
          <li>Everything in Free</li>
          <li>Unlimited corpora & documents</li>
          <li>10,000 searches per day</li>
          <li>500 chat messages per day</li>
          <li>100,000 queries per month</li>
          <li>100 URL imports per day</li>
          <li>Stripe Connect — earn from paid corpora</li>
          <li>Priority access</li>
        </ul>
        ${currentTier==='pro'?'<button class="pg-upgrade" id="pg-upgrade-btn">Manage Subscription</button>':
          isAuth?'<button class="pg-upgrade" id="pg-upgrade-btn">Upgrade to Pro</button>':
          '<a href="#/login" class="pg-upgrade">Sign in to upgrade</a>'}
      </div>
    </div>
    <div class="pg-self-host">
      <strong>Self-hosted?</strong> All features are free and unlimited. No cloud account needed. <code>pip install noosphere && noosphere serve</code>
    </div>
    ${isAuth?`<div class="pg-footer"><div class="pg-footer-email">${esc(email)}</div><button class="pg-footer-signout" id="pg-signout-btn">Sign Out</button></div>`:''}
  </div>`;
  const btn=document.getElementById('pg-upgrade-btn');
  if(btn){
    if(currentTier==='pro'){
      btn.onclick=async()=>{
        btn.disabled=true;btn.textContent='Loading...';
        try{const r=await fetch(`${API}/cloud/create-portal-session`,{method:'POST'});const d=await r.json();if(d.url)window.location.href=d.url;else{toast(d.detail||'Failed');btn.disabled=false;btn.textContent='Manage Subscription'}}catch(e){toast('Failed');btn.disabled=false;btn.textContent='Manage Subscription'}
      };
    }else{
      btn.onclick=async()=>{
        btn.disabled=true;btn.textContent='Loading...';
        try{const r=await fetch(`${API}/cloud/create-checkout-session`,{method:'POST'});const d=await r.json();if(d.url)window.location.href=d.url;else{toast(d.detail||'Failed to start checkout');btn.disabled=false;btn.textContent='Upgrade to Pro'}}catch(e){toast('Failed to start checkout');btn.disabled=false;btn.textContent='Upgrade to Pro'}
      };
    }
  }
  document.getElementById('pg-signout-btn')?.addEventListener('click',signOut);
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
