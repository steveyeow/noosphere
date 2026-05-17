/* Noosphere v9 — Terminal + Corpora + Network + Chat + Cloud Auth */
const API='/api/v1';
let _gAnim=null,_lpAnim=null,_termAnim=null,_files=[],_corpora=[],_chatH=[],_ownerName='',_firstName='';
let _cloudMode=false,_supabase=null,_authUser=null,_authSession=null;
/* ── Team workspaces ─────────────────────────────────────────────
   _workspace.kind: 'personal' | 'org'  ·  _workspace.org_id: string|null
   _orgs:          [{id,slug,name,role,...}]  (orgs the caller belongs to)
   _userId:        opaque id for self-hosted (persisted in localStorage),
                   or the cloud-mode JWT sub once /me returns.
   _selfHostedUserId — the localStorage value. Created lazily per browser
   so each invited member ends up with a distinct identity.
 */
const WS_KEY='noosphere-workspace';     // {kind, org_id}
const SH_UID_KEY='noosphere-user-id';   // self-hosted opaque user id
const DISPLAY_NAME_KEY='noosphere-display-name';  // user-chosen preferred name
let _workspace={kind:'personal',org_id:null};
let _orgs=[];
let _userId=null;
let _selfHostedUserId='';
let _isLocalOperator=false;
let _userDisplayName='';                // overrides extracted _firstName when set
function _loadDisplayName(){try{_userDisplayName=(localStorage.getItem(DISPLAY_NAME_KEY)||'').trim()}catch(_){_userDisplayName=''}}
function _saveDisplayName(v){
  try{
    const trimmed=(v||'').trim();
    if(trimmed){localStorage.setItem(DISPLAY_NAME_KEY,trimmed)}
    else{localStorage.removeItem(DISPLAY_NAME_KEY)}
    _userDisplayName=trimmed;
  }catch(_){}
}
function _ensureSelfHostedUserId(){
  let id=localStorage.getItem(SH_UID_KEY);
  if(!id){
    id='u_'+(crypto?.randomUUID?crypto.randomUUID().replace(/-/g,'').slice(0,16)
            :Math.random().toString(36).slice(2,10)+Date.now().toString(36));
    localStorage.setItem(SH_UID_KEY,id);
  }
  _selfHostedUserId=id;return id;
}
function _loadWorkspace(){
  try{const raw=localStorage.getItem(WS_KEY);if(raw){const v=JSON.parse(raw);
    if(v&&(v.kind==='personal'||(v.kind==='org'&&v.org_id))){_workspace=v}}}catch(_){}
}
function _saveWorkspace(){try{localStorage.setItem(WS_KEY,JSON.stringify(_workspace))}catch(_){}}
function _workspaceHeader(){
  return _workspace.kind==='org'&&_workspace.org_id?'org:'+_workspace.org_id:'personal';
}
// Home composer's corpus scope — hoisted to module scope so downstream
// helpers (placeholder refresh, compile routing) can see what the user has
// selected in the chip. null = "Any" (across all corpora); otherwise a corpus id.
let _homeScope=null;
// One-shot pre-selection consumed by renderHome() — set when the user enters
// the home composer from a corpus page's "Chat with X" CTA, so the chip and
// placeholder are already scoped on arrival.
let _pendingHomeScope=null;
// One-shot handoff: corpus-page chat dock → New Chat composer. _pendingHomeInput
// is the typed text; _pendingHomeAutoSend=true fires the home send-flow on the
// next renderHome so the user lands mid-send, not mid-draft.
let _pendingHomeInput=null;
let _pendingHomeAutoSend=false;
// One-shot: when the user picks an option (upload / url / archive / rss) from
// the corpus-page attach popover, the popover closes on the corpus page and
// we navigate to #/main with the corpus pre-selected. renderHome consumes
// this and renders the matching panel into the home chat-output stream — so
// the user lands directly in chat mode with the picked panel ready to fill.
let _pendingHomeAttachAction=null;
// One-shot: navigating to #/main?session=<sid> from a sidebar chat row or
// the Chats page. renderHome reads this, fetches the session, replays its
// messages into term-output, scopes the chip to its corpus, and arms
// _termCtx so the next user turn extends the same session instead of
// starting a fresh one. Rendered as the home composer's chat surface
// (no separate chat-detail page) so resuming is visually consistent with
// New Chat.
let _pendingHomeSession=null;
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

/* Map a 409 from POST /corpora into a friendly toast that lets the user
   open the existing corpus instead of failing silently. Returns true when
   handled so callers can short-circuit their generic error path. */
function handleDuplicateCorpus(res,body){
  if(!res||res.status!==409)return false;
  const det=body&&body.detail;
  if(!det||typeof det!=='object'||det.code!=='duplicate_corpus_name')return false;
  const existingId=det.existing_corpus_id;
  toast(det.message||'A corpus with that name already exists.','error',
    existingId?{label:'Open',onclick:()=>{location.hash='#/corpus/'+existingId}}:undefined);
  return true;
}

/* Pre-intercept a Pro-only action for Free users, saving a round-trip.
   Returns true if the user is Free (modal opened, caller should bail).

   Self-hosted (!_cloudMode): always pass through — the open-source build has
   no Pro concept; every feature is available. Cloud mode: Pro users pass,
   everyone else sees the paywall modal (including unauthenticated viewers,
   who need to sign in before upgrading). */
function gateProFeature(reason){
  if(!_cloudMode)return false;
  const tier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  if(tier==='pro')return false;
  showProModal(reason);
  return true;
}

/* True when Pro badges / Pro-locked rows should render at all. Self-hosted
   has no tiers, so hide them entirely. In cloud mode always show them —
   even for signed-out visitors (the badge tells them this is gated before
   they sign up). */
function shouldShowProUI(){return !!_cloudMode}

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
/* home--active safety net. Any panel that renders into term-output can
   ask the home wrapper to collapse (adds `home--active` so the composer
   moves to the top). When the panel is removed and term-output is empty,
   this observer un-collapses automatically — so new connectors don't
   have to remember the cleanup step in their cancel handler. Installed
   once per home mount (see renderHome). */
function _installHomeActiveWatcher(output){
  if(!output||output._hActiveWatch)return;
  output._hActiveWatch=true;
  const obs=new MutationObserver(()=>{
    if(!output.children.length){
      const home=document.getElementById('home');
      if(home&&home.classList.contains('home--active')){
        home.classList.remove('home--active');
      }
    }
  });
  obs.observe(output,{childList:true});
}

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
        // Clean up the URL — remove token params. If the user signed in
        // to accept an org invite, return to that invite so the join
        // auto-completes; otherwise go to main.
        history.replaceState(null,'',window.location.pathname+(_pendingInviteHash()||'#/main'));
      }else{
        const{data}=await _supabase.auth.getSession();
        if(data.session){_authSession=data.session;_authUser=data.session.user}
      }
      _supabase.auth.onAuthStateChange((event,session)=>{
        _authSession=session;_authUser=session?.user||null;
        renderAuthUI();
        if(event==='SIGNED_IN'){
          // Clean URL if needed and navigate. A stashed invite (cloud
          // sign-in to accept) takes priority over the default landing.
          const _pi=_pendingInviteHash();
          if(window.location.hash.includes('access_token=')){
            history.replaceState(null,'',window.location.pathname+(_pi||'#/main'));
          }else if(_pi){location.hash=_pi}
          route();
        }
      });
    }
  }catch(e){console.warn('Auth init:',e)}
}

/* An org invite stashed before bouncing an unauthenticated invitee
   through sign-in (cloud mode). Returns the invite hash to land on
   post-auth so the join auto-completes, or null. */
function _pendingInviteHash(){
  try{
    const raw=localStorage.getItem('nph-pending-invite');
    if(!raw)return null;
    const p=JSON.parse(raw);
    return p&&p.token?('#/invite/'+encodeURIComponent(p.token)):null;
  }catch(e){return null}
}

function authHeaders(){
  const h={};
  if(_authSession?.access_token)h['Authorization']='Bearer '+_authSession.access_token;
  // Team workspace context — sent on every API call.
  h['X-Noosphere-Workspace']=_workspaceHeader();
  // Self-hosted: each browser carries its own opaque user_id so multiple
  // members on one server are distinguishable. Cloud uses JWT instead.
  if(!_cloudMode){
    if(!_selfHostedUserId)_ensureSelfHostedUserId();
    if(_selfHostedUserId)h['X-Noosphere-User-Id']=_selfHostedUserId;
  }
  return h;
}

function apiFetch(url,opts={}){
  opts.headers={...(opts.headers||{}),...authHeaders()};
  return window._origFetch(url,opts);
}

// Monkey-patch fetch to auto-inject auth + workspace headers for API calls.
// Token-gated corpora live behind Authorization: Bearer <corpus_access_token>;
// when the user has paid/entered a token for a specific corpus we substitute
// it for that corpus's URLs so subsequent fetches authenticate as the
// token holder rather than the logged-in user (whose JWT means nothing to
// the per-corpus access table).
window._origFetch=window.fetch;
window.fetch=function(url,opts={}){
  if(typeof url==='string'&&(url.startsWith(API)||url.startsWith('/api'))){
    opts=opts||{};opts.headers={...(opts.headers||{}),...authHeaders()};
    const m=url.match(/\/api\/v1\/corpora\/([^\/?#]+)/);
    if(m){
      try{
        const t=sessionStorage.getItem('nph-corpus-token-'+m[1]);
        if(t)opts.headers['Authorization']='Bearer '+t;
      }catch(e){}
    }
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

/* Single bottom-of-sidebar control — the workspace + profile hub.
   Notion-style: shows the active workspace as the primary label and the
   operator/user as the sub-label. The popover lists workspaces (radio),
   Org settings (when in an org), then "you-level" actions (create org,
   theme, account, sign out). Workspaces and profile actions live together
   here because both are about "who you are and where you're working." */
const _ICON_SUN='<svg class="icon-sun" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
const _ICON_MOON='<svg class="icon-moon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const _ICON_PLUS='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
const _ICON_GEAR='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
const _ICON_USERS='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>';

function _activeWorkspaceLabel(){
  if(_workspace.kind==='org'&&_workspace.org_id){
    const o=_orgs.find(o=>o.id===_workspace.org_id);
    return o?o.name:'Personal';
  }
  return 'Personal';
}

/* Workspace context is signaled by the bottom-left profile chip; we
   intentionally do NOT duplicate it across page headers. Kept as a no-op
   helper so existing call sites remain harmless. */
function workspaceEyebrowHTML(){return ''}

function _operatorChipText(){
  // Preferred name wins everywhere it's surfaced (greeting, personal card,
  // Settings header). Falls back to email-prefix (cloud) / OWNER_NAME
  // (self-hosted) so we never show an empty label.
  if(_userDisplayName)return _userDisplayName;
  if(_cloudMode&&_authUser){
    const email=_authUser.email||'';
    return email.split('@')[0]||'User';
  }
  return _ownerName||'You';
}

/* Avatar for the bottom-left chip. Shape changes with workspace:
   - Personal: user avatar (cloud) or user initial (self-hosted) — about you
   - Team:     circular initial of the org name — about *where* you are    */
function _renderChipAvatarHTML(){
  if(_workspace.kind==='org'&&_workspace.org_id){
    const o=_orgs.find(o=>o.id===_workspace.org_id);
    const ch=esc(((o?.name||'?')[0]||'?').toUpperCase());
    return `<span class="sb-auth-initial sb-auth-initial--team">${ch}</span>`;
  }
  if(_cloudMode&&_authUser){
    const av=_authUser.user_metadata?.avatar_url;
    if(av)return `<img src="${esc(av)}" class="sb-auth-avatar"/>`;
    const nm=(_authUser.email||'U').split('@')[0]||'U';
    return `<span class="sb-auth-initial">${esc((nm[0]||'?').toUpperCase())}</span>`;
  }
  const op=_operatorChipText();
  return `<span class="sb-auth-initial">${esc((op[0]||'·').toUpperCase())}</span>`;
}

function renderAuthUI(){
  const bot=document.getElementById('sb-bot');
  if(!bot)return;
  // Cloud + signed out: just a sign-in button (orgs require an identity).
  if(_cloudMode&&!_authUser){
    bot.innerHTML=`<button class="sb-btn sb-auth-login" style="width:100%;justify-content:center;gap:6px;padding:6px 10px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg><span class="sb-lb">Sign in</span></button>`;
    bot.querySelector('.sb-auth-login').onclick=signInWithGoogle;
    return;
  }
  // Avatar reflects *where* (org initial for team, user avatar for
  // personal); the label is *who* (the preferred / operator name). The
  // small chip on the right edge says *which workspace mode* the user is
  // in — "Team" when an org is active, the personal plan tier otherwise.
  // The personal Pro/Free badge is meaningless in a team workspace because
  // we have not yet introduced org-level entitlements (see organizations.tier
  // — hardcoded 'team' for all orgs; org Stripe path is scaffolded but unused).
  let tierText='';
  if(_cloudMode&&_authUser){
    if(_workspace.kind==='org'&&_workspace.org_id){
      tierText='Team';
    }else{
      const t=(_authUser.user_metadata?.tier||'free').toLowerCase();
      tierText=t==='pro'?'Pro':'Free';
    }
  }
  bot.innerHTML=`
    <div class="sb-profile sb-profile-ws" id="sb-profile">
      ${_renderChipAvatarHTML()}
      <span class="sb-profile-name sb-lb" id="sb-profile-name">${esc(_operatorChipText())}</span>
      ${tierText?`<span class="sb-profile-tier sb-lb">${tierText}</span>`:''}
      <svg class="sb-profile-chev sb-lb" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="sb-popover sb-popover-ws hidden" id="sb-popover"></div>`;
  const profile=bot.querySelector('#sb-profile');
  const popover=bot.querySelector('#sb-popover');
  profile.addEventListener('click',e=>{e.stopPropagation();
    if(popover.classList.contains('hidden')){
      popover.innerHTML=_renderProfilePopoverHTML();
      _wireProfilePopover(bot,popover);
      popover.classList.remove('hidden');
    }else{popover.classList.add('hidden')}
  });
  document.addEventListener('click',function _closePopover(e){if(!bot.contains(e.target))popover.classList.add('hidden')});
}

function _renderProfilePopoverHTML(){
  // Workspace card — always rendered; the contents adapt to the active
  // workspace. Org shows team identity + member count + Settings/Invite
  // pills. Personal shows the user (or "Personal") + plan tier (cloud) +
  // single Settings pill. Settings is a single, consistent entry point —
  // the destination changes with workspace, like Claude / Notion.
  let wsCard='';
  if(_workspace.kind==='org'&&_workspace.org_id){
    const o=_orgs.find(o=>o.id===_workspace.org_id);
    if(o){
      const initial=esc((o.name?.[0]||'?').toUpperCase());
      const memberCount=(typeof o.member_count==='number')?o.member_count:null;
      const meta=memberCount!==null
        ? `Team · ${memberCount} member${memberCount===1?'':'s'}`
        : `Team · ${esc(o.role||'member')}`;
      // Org card pills are *operational* (dashboard entry points), not
      // settings: Manage = the team dashboard (members/invites/audit/
      // connectors). True org-level settings live under #/settings.
      wsCard=`
        <div class="sb-pop-card">
          <div class="sb-pop-card-id">
            <span class="sb-pop-card-avatar">${initial}</span>
            <div class="sb-pop-card-text">
              <div class="sb-pop-card-name">${esc(o.name)}</div>
              <div class="sb-pop-card-meta">${meta}</div>
            </div>
          </div>
          <div class="sb-pop-card-actions">
            <a class="sb-pop-pill" data-act="org-manage" data-slug="${esc(o.slug)}">${_ICON_USERS}<span>Manage</span></a>
            <a class="sb-pop-pill" data-act="org-invite" data-slug="${esc(o.slug)}">${_ICON_PLUS}<span>Invite members</span></a>
          </div>
        </div>`;
    }
  }else{
    // Personal workspace card — pure identity. No action pills here;
    // app-wide preferences live under the explicit Settings entry below.
    let avatarHTML='';
    if(_cloudMode&&_authUser){
      const av=_authUser.user_metadata?.avatar_url;
      const nm=(_authUser.email||'U').split('@')[0]||'U';
      avatarHTML=av?`<img src="${esc(av)}" class="sb-pop-card-avatar"/>`:`<span class="sb-pop-card-avatar">${esc((nm[0]||'?').toUpperCase())}</span>`;
    }else{
      const op=_ownerName||'Y';
      avatarHTML=`<span class="sb-pop-card-avatar">${esc((op[0]||'?').toUpperCase())}</span>`;
    }
    let meta='';
    if(_cloudMode&&_authUser){
      const tier=(_authUser.user_metadata?.tier||'free').toLowerCase();
      meta=tier==='pro'?'Pro plan':'Free plan';
    }
    wsCard=`
      <div class="sb-pop-card sb-pop-card--personal">
        <div class="sb-pop-card-id">
          ${avatarHTML}
          <div class="sb-pop-card-text">
            <div class="sb-pop-card-name">Personal</div>
            ${meta?`<div class="sb-pop-card-meta">${esc(meta)}</div>`:''}
          </div>
        </div>
      </div>`;
  }
  // Workspaces list (radio).
  const wsItems=[];
  wsItems.push(`<button class="sb-pop-item sb-pop-ws${_workspace.kind==='personal'?' is-active':''}" data-act="ws-personal"><span class="sb-pop-ws-dot"></span><span class="sb-pop-ws-name">Personal</span>${_workspace.kind==='personal'?'<span class="sb-pop-ws-check">✓</span>':''}</button>`);
  for(const o of _orgs){
    const active=_workspace.kind==='org'&&_workspace.org_id===o.id;
    wsItems.push(`<a class="sb-pop-item sb-pop-ws${active?' is-active':''}" data-act="ws-org" data-id="${esc(o.id)}" data-slug="${esc(o.slug||'')}"><span class="sb-pop-ws-dot"></span><span class="sb-pop-ws-name">${esc(o.name)}</span><span class="sb-pop-ws-role">${esc(o.role||'member')}</span>${active?'<span class="sb-pop-ws-check">✓</span>':''}</a>`);
  }
  // Account block (cloud only).
  const accountBlock=(_cloudMode&&_authUser)?`
    <div class="sb-pop-divider"></div>
    <div class="sb-pop-section-label">Account · ${esc(_authUser.email||'')}</div>
    <a href="#/account" class="sb-pop-item"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg><span>Account</span></a>
    <a href="#/pricing" class="sb-pop-item"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg><span>${(_authUser&&(_authUser.user_metadata?.tier||'').toLowerCase()==='pro')?'Manage subscription':'Pricing'}</span></a>
  `:'';
  const signoutItem=(_cloudMode&&_authUser)?
    `<button class="sb-pop-item sb-pop-danger" id="sb-pop-signout"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg><span>Sign out</span></button>`:'';
  // Create organization sits directly under the workspaces list (no
  // divider) — it's a "this is where workspaces come from" continuation,
  // not a separate category. Theme + account/signout get their own block.
  return `
    ${wsCard}
    <div class="sb-pop-section-label">Workspaces</div>
    <div class="sb-pop-section">${wsItems.join('')}<button class="sb-pop-item" id="sb-pop-create-org">${_ICON_PLUS}<span>Create organization</span></button></div>
    <div class="sb-pop-divider"></div>
    <a class="sb-pop-item" data-act="settings">${_ICON_GEAR}<span>Settings</span></a>
    <button class="sb-pop-item" id="sb-pop-theme">${_ICON_SUN}${_ICON_MOON}<span>Theme</span></button>
    ${accountBlock}
    ${signoutItem}
  `;
}

function _wireProfilePopover(bot,popover){
  const close=()=>popover.classList.add('hidden');
  popover.querySelectorAll('[data-act]').forEach(el=>{
    el.addEventListener('click',ev=>{
      ev.preventDefault();ev.stopPropagation();close();
      const act=el.dataset.act;
      if(act==='ws-personal')setWorkspace({kind:'personal',org_id:null});
      else if(act==='ws-org')setWorkspace({kind:'org',org_id:el.dataset.id});
      // Org card pills open the consolidated Settings modal on the matching
      // Team section. The card only renders in an org workspace, so the
      // active org is already correct — no slug resolution needed.
      else if(act==='org-manage'){_ensureSettingsBackdrop();_showSettingsModal('team-members')}
      else if(act==='org-invite'){_ensureSettingsBackdrop();_showSettingsModal('team-invites')}
      // Settings = same modal, opens on Account.
      else if(act==='settings')location.hash='#/settings';
    });
  });
  popover.querySelectorAll('a.sb-pop-item:not([data-act])').forEach(a=>a.addEventListener('click',close));
  bot.querySelector('#sb-pop-theme').addEventListener('click',e=>{e.stopPropagation();toggleTheme()});
  bot.querySelector('#sb-pop-create-org').addEventListener('click',e=>{e.stopPropagation();close();_showCreateOrgModal()});
  if(_cloudMode&&_authUser)bot.querySelector('#sb-pop-signout').addEventListener('click',signOut);
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
  // Logged-in cloud users skip the marketing landing — they came to use
  // the app, not re-read the pitch. Also handles Stripe's post-checkout
  // redirect (APP_URL/?subscription=success → hash empty) so users land
  // straight in the app after upgrading.
  if((h==='#/'||h===''||h==='#/landing')&&_cloudMode&&_authUser){
    history.replaceState(null,'',window.location.pathname+window.location.search+'#/main');
    return route();
  }
  if(h==='#/'||h===''||h==='#/landing'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLP();return}
  if(h==='#/team'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLPTeam();return}
  if(h==='#/login'){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLogin();return}
  if(h.startsWith('#/invite/')){
    document.getElementById('page-landing').classList.remove('hidden');
    document.getElementById('page-main').classList.add('hidden');
    await renderInviteAccept(h.substring('#/invite/'.length));return;
  }
  // Cloud mode: redirect to login if not authenticated and trying to access app
  if(_cloudMode&&!_authUser&&h!=='#/explore'&&!h.startsWith('#/explore')){document.getElementById('page-landing').classList.remove('hidden');document.getElementById('page-main').classList.add('hidden');renderLogin();return}
  document.getElementById('page-landing').classList.add('hidden');document.getElementById('page-main').classList.remove('hidden');
  await Promise.all([loadC(),loadMe(),loadChatSessions()]);setSBActive(h);renderSBChats();
  if(h==='#/main'||h.startsWith('#/main?')){
    // ?session=<sid> → resume that chat in the home composer. Set the pending
    // slot here (not in renderHome) so #/main with no query still resets it.
    const q=h.split('?')[1]||'';
    _pendingHomeSession=new URLSearchParams(q).get('session')||null;
    renderHome();
  }
  else if(h==='#/corpora')renderMyCorpora();
  else if(h==='#/chats')renderChats();
  else if(h==='#/connectors')renderConnectors();
  else if(h==='#/settings'||h==='#/preferences'){
    // Settings is a modal overlay — opens on top of whatever page is
    // currently rendered. On a cold URL hit (refresh into #/settings),
    // fall back to home as the backdrop so the modal doesn't float on
    // an empty page.
    _ensureSettingsBackdrop();
    _showSettingsModal();
    return;
  }
  else if(h.startsWith('#/orgs/')){
    // Team management is no longer a standalone page — it lives in the
    // Settings modal. Old links / profile pills redirect here.
    const segs=h.substring('#/orgs/'.length).split('/');
    const slug=decodeURIComponent(segs[0]||'');const tab=segs[1]||'';
    await _openTeamSettings(slug,tab);
    return;
  }
  else if(h==='#/pricing')renderPricing();
  else if(h==='#/account')renderAccount();
  else if(h==='#/network'||h.startsWith('#/explore'))renderNet();
  else if(h.startsWith('#/compile')){
    const qp=new URLSearchParams(h.split('?')[1]||'');
    await renderCompile(qp);
  }
  else if(h.startsWith('#/corpus/')){
    // #/corpus/{cid}                    — Overview tab (default)
    // #/corpus/{cid}/insights           — Insights tab (agent activity)
    // #/corpus/{cid}/entity/{eid}[?q]   — entity drill-down (legacy)
    const afterPrefix=h.substring('#/corpus/'.length);
    const [pathPart,queryPart]=afterPrefix.split('?');
    const segs=pathPart.split('/');
    const corpusId=segs[0];
    if(segs[1]==='entity'&&segs[2]){
      await renderEntity(corpusId,segs[2]);
    }else if(segs[1]==='insights'){
      await renderCorpusInsights(corpusId);
    }else if(segs[1]==='settings'){
      await renderCorpusSettings(corpusId);
    }else{
      const params=new URLSearchParams(queryPart||'');
      const sessionId=params.get('session');
      await renderCorpus(corpusId,sessionId);
    }
  }
  else renderHome();
}
function stopAll(){if(_lpAnim){cancelAnimationFrame(_lpAnim);_lpAnim=null}if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}if(_termAnim){cancelAnimationFrame(_termAnim);_termAnim=null}_setCorpusJsonLD(null)}
// Inject schema.org Dataset JSON-LD for the active corpus so AI crawlers
// (ChatGPT search, Perplexity, Anthropic web fetch) and traditional search
// engines see structured metadata when they execute the SPA. Pass null to
// clear — called from stopAll() on every view switch so stale JSON-LD never
// outlives the corpus it described.
function _setCorpusJsonLD(c){
  const old=document.getElementById('corpus-jsonld');
  if(old)old.remove();
  if(!c)return;
  const slug=encodeURIComponent(c.slug||c.id);
  const base=location.origin;
  const ld={
    "@context":"https://schema.org",
    "@type":"Dataset",
    "name":c.name||"",
    "description":c.description||"",
    "url":`${base}/c/${slug}`,
    "distribution":[
      {"@type":"DataDownload","encodingFormat":"text/markdown","contentUrl":`${base}/c/${slug}/llms.txt`},
      {"@type":"DataDownload","encodingFormat":"text/markdown","contentUrl":`${base}/c/${slug}/llms-full.txt`},
    ],
  };
  if(c.license)ld.license=c.license;
  if(c.author_name)ld.creator={"@type":"Person","name":c.author_name};
  if(Array.isArray(c.tags)&&c.tags.length)ld.keywords=c.tags.join(", ");
  const s=document.createElement('script');
  s.type='application/ld+json';
  s.id='corpus-jsonld';
  s.text=JSON.stringify(ld);
  document.head.appendChild(s);
}
async function loadC(){try{const r=await fetch(`${API}/corpora`);_corpora=await r.json()}catch(e){_corpora=[]}}
async function loadMe(){try{const r=await fetch(`${API}/me`);const d=await r.json();_ownerName=d.name||'';
  // Only extract a first name we're confident about: space-separated (e.g. "Steve Yao" → "Steve")
  // or CamelCase boundary (e.g. "SteveYao" → "Steve"). Concatenated usernames like "steveyao" stay
  // empty — better to show no name than the wrong one.
  if(_ownerName.includes(' '))_firstName=_ownerName.split(' ')[0];
  else{const m=_ownerName.match(/^[A-Z][a-z]+(?=[A-Z])/);_firstName=m?m[0]:''}
  _userId=d.user_id||null;
  _isLocalOperator=!!d.is_local_operator;
  _orgs=Array.isArray(d.orgs)?d.orgs:[];
  // Source of truth for `tier` is Noosphere's users table (updated by the
  // Stripe webhook on checkout.session.completed). Supabase JWT user_metadata
  // is NOT auto-synced. Mirror server tier into _authUser.user_metadata so
  // the many UI sites reading _authUser.user_metadata.tier get the post-
  // upgrade value without needing a JWT refresh.
  if(_authUser&&typeof d.tier==='string'){
    _authUser.user_metadata=_authUser.user_metadata||{};
    _authUser.user_metadata.tier=d.tier;
  }
  // Active workspace must reference an org the user still belongs to —
  // otherwise reset to Personal so we don't fire requests against a
  // workspace the server will 403.
  if(_workspace.kind==='org'&&_workspace.org_id&&!_orgs.find(o=>o.id===_workspace.org_id)){
    _workspace={kind:'personal',org_id:null};_saveWorkspace();
  }
  renderWorkspaceSwitcher();
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
  const h=location.hash;
  // Sidebar chat sessions resolve to #/main?session=<sid> now (the home
  // composer is the chat surface). Legacy #/corpus/<cid>?session=<sid>
  // links are still recognized so any in-flight bookmarks keep working.
  if(!h.startsWith('#/main')&&!h.startsWith('#/corpus/'))return null;
  const q=h.split('?')[1]||'';return new URLSearchParams(q).get('session');
}
function renderSBChats(){
  const el=document.getElementById('sb-chats');if(!el)return;
  if(!_chatSessions.length){el.innerHTML='';return}
  const activeSid=_currentSessionId();
  el.innerHTML=_chatSessions.map(c=>{
    const active=c.id===activeSid?' active':'';
    return`<div class="sb-chat-wrap${active}" data-sid="${c.id}"><a href="#/main?session=${c.id}" class="sb-chat-item" title="${esc(c.title||'')}">${esc(c.title||'Untitled')}</a><button class="sb-chat-del" data-sid="${c.id}" title="Delete chat" aria-label="Delete chat">×</button></div>`;
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
// Feynman-style dataset — 44 representative KBs with rich multi-tag
// domains so the force-directed graph has plenty of shared-token
// links, producing a densely woven network rather than a sparse scatter.
// Live corpora from the registry prepend to this list (see drawLPGraph);
// this curated set is the floor.
// Curated knowledge-wiki names — every entry is a *content body* (a wiki,
// a collection of letters/essays/lectures, a domain), never a bare person
// name. Noosphere's product is wikis-as-agents, not minds-as-agents.
// Tags use Feynman-style multi-word specificity (e.g. "ancient philosophy"
// not bare "philosophy") to keep the edge density Feynman-like (~150 edges
// across 53 nodes); over-shared bare tags cause edge explosion.
const DM_FALLBACK=[
  // Product / startups
  {n:"Lenny's Newsletter",d:'product, growth, startups, management'},
  {n:'YC Startup School',d:'startups, fundraising, product, leadership'},
  {n:'First Round Review',d:'startups, management, leadership, hiring'},
  {n:'A16Z Memos',d:'venture capital, software, technology, techno-optimism'},
  {n:'Paul Graham Essays',d:'startups, essays, programming, hackers'},
  {n:'Naval Almanack',d:'wealth, decision-making, principles, leverage'},
  // AI / ML / agents
  {n:'AI Research Digest',d:'AI, ML, deep learning, neural networks'},
  {n:'Karpathy Notes',d:'AI, neural networks, deep learning, teaching'},
  {n:'LLM Prompting',d:'AI, prompting, language models, tools'},
  {n:'AI Coding',d:'AI, coding, cursor, software engineering'},
  // Science / research
  {n:'Feynman Lectures',d:'physics, quantum mechanics, teaching'},
  {n:'Darwin Archive',d:'biology, evolution, natural history'},
  {n:'Einstein Letters',d:'physics, relativity, philosophy of science'},
  {n:'Newton Principia',d:'physics, classical mechanics, mathematics, optics'},
  {n:'Climate Science',d:'climate, environment, earth science, data'},
  // Philosophy — multi-word tags split the cluster
  {n:'Stoic Philosophy',d:'ancient philosophy, stoicism, ethics, virtue'},
  {n:'Eastern Wisdom',d:'eastern philosophy, taoism, confucianism, ethics'},
  {n:'Kant Essays',d:'modern philosophy, epistemology, metaphysics, ethics'},
  {n:'Nietzsche Texts',d:'modern philosophy, existentialism, ethics, cultural criticism'},
  // Finance / investing
  {n:'Munger Almanack',d:'investing, mental models, multidisciplinary thinking'},
  {n:'Buffett Letters',d:'investing, value investing, business analysis'},
  {n:'Crypto Trading',d:'crypto, trading, markets, decentralized finance'},
  {n:'Harness Engineering',d:'AI agents, harness, evals, prompt engineering'},
  // Design / craft
  {n:'Design Patterns',d:'software design, engineering, programming'},
  {n:'Type Design',d:'typography, design craft, lettering'},
  {n:'UX Research',d:'design research, product, user psychology'},
  // History / culture
  {n:'Ancient Rome',d:'roman history, politics, civilization'},
  {n:'Chinese Dynasties',d:'chinese history, culture, governance'},
  // Writing / creative
  {n:'Writing Craft',d:'writing, narrative, creative craft'},
  {n:'Reading Notes',d:'books, learning, knowledge work'},
  // Psychology
  {n:'Kahneman Notes',d:'cognitive psychology, behavioral economics, decision-making'},
  {n:'Jung Archetypes',d:'depth psychology, mythology, archetypes'},
  // Tech / programming
  {n:'Hacker News Digest',d:'technology, hackers, startups, programming'},
  {n:'Indie Hackers',d:'startups, bootstrapping, indie business'},
  {n:'Substack Reads',d:'writing, essays, journalism, blogging'},
  {n:'Rust Book',d:'rust, systems programming, software engineering'},
  {n:'Tailwind Docs',d:'web design, css, frontend, technology'},
  // Investment extensions
  {n:'Howard Marks Memos',d:'investing, market cycles, risk'},
  {n:'Bogle Index Notes',d:'index investing, passive funds, markets'},
  // Ancient texts
  {n:'Aurelius Meditations',d:'stoicism, ancient philosophy, ethics, virtue'},
  {n:'Sun Tzu Art of War',d:'military strategy, leadership, eastern philosophy'},
  {n:'Aristotle Ethics',d:'ancient philosophy, ethics, virtue, logic'},
  {n:'Tao Te Ching',d:'eastern philosophy, taoism, metaphysics, ethics'},
  // Science extensions
  {n:'Dawkins Selfish Gene',d:'evolutionary biology, genetics, sociobiology'},
  {n:'Marathon Training',d:'running, endurance, fitness, training'},
  {n:'Hawking Lectures',d:'physics, cosmology, theoretical physics, black holes'},
  // Literature
  {n:'Borges Ficciones',d:'literature, magical realism, metaphysics, writing'},
  {n:'Hemingway Letters',d:'literature, writing, narrative prose, modernism'},
  // Cognitive / risk
  {n:'Pinker Notes',d:'linguistics, human nature, rationality'},
  {n:'Taleb Antifragile',d:'risk, probability, antifragility, epistemology'},
  // Other knowledge bodies
  {n:'Chinese Cooking',d:'cooking, chinese cuisine, recipes, craft'},
  {n:'Coffee Brewing',d:'coffee, brewing, espresso, craft'},
  {n:'Hofstadter GEB',d:'recursion, formal systems, mathematics, cognitive science'},
];

// SVG icon snippets reused across landing sections. Line-only, no
// decorative emoji — matches the Feynman aesthetic rule in memory.
const _LP_ICO={
  upload:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  plug:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.72"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.72-1.72"/></svg>`,
  chat:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  compile:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20"/><path d="M2 12h20"/><circle cx="12" cy="12" r="9"/></svg>`,
  lock:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
  coin:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9 9.5a2.5 2.5 0 0 1 2.5-2.5h1a2.5 2.5 0 0 1 0 5h-3a2.5 2.5 0 0 0 0 5h1a2.5 2.5 0 0 0 2.5-2.5"/></svg>`,
  shield:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  home:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2h-4v-7h-6v7H5a2 2 0 0 1-2-2z"/></svg>`,
};

function renderLP(){const el=document.getElementById('page-landing');el.innerHTML=`<div class="lp">
  <nav class="lp-top"><span class="lp-brand"><svg width="17" height="17" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere</span><div class="lp-top-right"><a href="#/team" class="lp-top-link">For teams</a><button class="lp-dark-btn" id="lp-dark-btn" title="Toggle dark mode"><svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg><svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button></div></nav>

  <section class="lp-hero">
    <div class="lp-cv" id="lp-cv"></div>
    <div class="lp-ct">
      <div class="lp-h">
        <h1 class="lp-h1">Build your living knowledge wiki, publish to the agent internet.</h1>
        <p class="lp-sub">Turn your thoughts, skills, reading notes, and open questions into a living wiki — agent-readable, connected to and learning from a global agent network. Keep it private, share it free, or charge per query.</p>
        <button class="lp-go" id="lp-go">Get Started →</button>
      </div>
      <div class="lp-term" id="lp-term">
        <div class="lp-term-bar"><span class="lp-term-dot red"></span><span class="lp-term-dot ylw"></span><span class="lp-term-dot grn"></span><span class="lp-term-title">noosphere</span></div>
        <div class="lp-term-body" id="lp-term-body"></div>
      </div>
    </div>
    <div class="lp-hero-mission">Expand the scope and scale of collective enlightenment.</div>
  </section>

  <section class="lp-sec lp-sec-bring">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Build your living wiki.</h2>
      <p class="lp-sec-sub">Notes you write, questions you explore, files and feeds you bring in — Noosphere folds them all into living corpora that grow richer over time.</p>
      <div class="lp-cards">
        <div class="lp-card lp-card-ingest">
          <h3 class="lp-card-h">Ingest</h3>
          <div class="lp-card-body">
            <p class="lp-card-p">Every way knowledge gets in — you don't start from scratch. Whatever the method, each input becomes the same agent-readable document.</p>
            <ul class="lp-im">
              <li><span class="lp-im-k">Write</span><span class="lp-im-d">Original notes inline, in Markdown.</span></li>
              <li><span class="lp-im-k">Upload</span><span class="lp-im-d">PDFs, Markdown, or full archive exports.</span></li>
              <li><span class="lp-im-k">Add URL</span><span class="lp-im-d">Any web page, or an RSS / Atom feed.</span></li>
              <li><span class="lp-im-k">Connect</span><span class="lp-im-d">Your existing tools — one-shot import, or stay live-synced:</span></li>
            </ul>
            <div class="lp-mig-logos" id="lp-mig-logos"></div>
          </div>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Chat to enrich</h3>
          <p class="lp-card-p">Chat with your wiki and it grows from the conversation — Noosphere detects the insights worth keeping and folds them into the matching pages on its own. Drop in a URL, note, or file mid-chat and it's ingested, indexed, and cross-linked the same way. Nothing valuable is lost to chat history.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Compile</h3>
          <p class="lp-card-p">An LLM fuses retrieved passages into concept notes. Cross-references stay fresh as new sources arrive. Your wiki pages write themselves.</p>
        </div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-agent">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Agent-readable by design, automatically matched.</h2>
      <p class="lp-sec-sub">Publish a corpus to the network and every agent on it can describe, ask, cite. Legacy media ranked for attention — <strong>popular beat valuable</strong>. Agents only care about information value and verifiable provenance. Every Noosphere corpus speaks the same small toolbox — MCP-native, plus REST.</p>
      <div class="lp-tool-list">
        <div class="lp-tool"><code>manifest</code><span>Machine-readable capability card — scope, task types, license, and the requirements a caller must meet.</span></div>
        <div class="lp-tool"><code>ask</code><span>Full synthesized answer with inline [N] citations + calibrated confidence; respects the access gate.</span></div>
        <div class="lp-tool"><code>preview_ask</code><span>A free, truncated preview of that answer — so an agent judges fit before paying.</span></div>
        <div class="lp-tool"><code>kb_reputation</code><span>Earned from real citations, returns, and calibration — no pay-to-promote, no hidden ranking.</span></div>
        <div class="lp-tool"><code>standard interface</code><span>A public KB auto-advertises its access-friendly supply and the minimum a caller must meet, via the manifest or a well-known file — a standardized supply↔demand handshake.</span></div>
        <div class="lp-tool"><code>need-driven middle</code><span>A minimal base; the agent brings its own need, which drives discovery, compile/distill, and payment — automated, no broker.</span></div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-network">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Get connected, learn from a global agent network.</h2>
      <p class="lp-sec-sub">Every knowledge base is itself an agentic node. Networking is the substrate — every corpus is reachable in the network by default. Autonomy is the dial: three tiers controlling how much of the network the corpus consumes and acts on without prompting.</p>
      <div class="lp-autonomy">
        <div class="lp-level"><span class="lp-level-nm">Static</span><span class="lp-level-dc">Manual sources · manual compile. Answers queries on demand.</span></div>
        <div class="lp-level"><span class="lp-level-nm">Living</span><span class="lp-level-dc">Auto-ingests from connected feeds; keeps compiled Wiki, entities, and timelines in sync as sources change.</span></div>
        <div class="lp-level"><span class="lp-level-nm">Fully Autonomous</span><span class="lp-level-dc">Actively discovers peer corpora, subscribes, pays within owner-set policy, and grows knowledge over time.</span></div>
      </div>
      <p class="lp-sec-foot">Every inter-KB query carries provenance. Citations record in a directed graph weighted by the citing KB's own reputation — trust compounds recursively.</p>
      <div class="lp-callout">
        <strong>Self-host, still connected.</strong> Run Noosphere on your own machine — your documents, chunks, and embeddings stay local. Only metadata (name, tags, endpoint URL) publishes to the discovery registry. Agents find you; your content never leaves your infrastructure.
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-rules">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Set the access. Set the price. Keep the revenue.</h2>
      <p class="lp-sec-sub">You decide what lives in the network, what's free, what costs, and where the money goes.</p>
      <div class="lp-cards">
        <div class="lp-card">
          <h3 class="lp-card-h">Access controls</h3>
          <p class="lp-card-p">Public · Private · Token-gated · Paid. Switch anytime; the registry reconciles within seconds.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Four pricing shapes</h3>
          <p class="lp-card-p">Pay-per-query, subscription, corpus licensing (bulk / training data), agent-to-agent payment.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Anti copyright-laundering</h3>
          <p class="lp-card-p">Only content you originated is monetizable. Imported RSS or external URLs are filtered out for paying callers, by rule.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Direct revenue, no middleman</h3>
          <p class="lp-card-p">Self-hosted: your Stripe, your money — Noosphere never touches it. Cloud: 10% commission on platform-facilitated payments only. Free corpora pay nothing, ever.</p>
        </div>
      </div></div>
  </section>

  <section class="lp-sec lp-sec-market">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">A self-growing human knowledge layer. An autonomous AI data marketplace.</h2>
      <p class="lp-sec-sub">Noosphere changes how knowledge reaches AI: not free capture by platforms, not buyer-directed dispatch work, but living knowledge bases that stay with their creators and become agent-readable, discoverable, licensable, and paid.</p>

      <div class="lp-mech-map" aria-label="Creators own the supply, an automated market matches AI demand, and payment plus reputation return to the owner">
        <div class="lp-flow-row">
          <div class="lp-flow-node">
            <span class="lp-flow-k">Creators</span>
            <p class="lp-flow-d">Build and keep growing corpora for their own work.</p>
          </div>
          <div class="lp-flow-edge"><span class="lp-flow-arr" aria-hidden="true">→</span></div>
          <div class="lp-flow-node">
            <span class="lp-flow-k">Automated market</span>
            <p class="lp-flow-d">Discover, preview, pay — no broker. Matched on manifest · preview_ask · per-use reputation.</p>
          </div>
          <div class="lp-flow-edge"><span class="lp-flow-arr" aria-hidden="true">→</span></div>
          <div class="lp-flow-node">
            <span class="lp-flow-k">AI consumers</span>
            <p class="lp-flow-d">Read as runtime answers, post-training data, or bulk licenses.</p>
          </div>
        </div>
        <div class="lp-flow-return">
          <span class="lp-flow-arr" aria-hidden="true">←</span>
          <p>Payment and reputation return to the owner.</p>
        </div>
      </div>

      <div class="lp-advantage">
        <div class="lp-mech-eyebrow">Versus data vendors</div>
        <div class="lp-shift-list">
          <div class="lp-shift-row lp-shift-head">
            <div class="lp-shift-old"><span>Traditional data vendors</span></div>
            <div class="lp-shift-new"><span>Noosphere</span></div>
          </div>
          <div class="lp-shift-row">
            <div class="lp-shift-old">
              <span>Per-spec cost chain</span>
              <p>Every buyer spec re-runs recruiting, QA, and vendor operations — the buyer funds that chain each time.</p>
            </div>            <div class="lp-shift-new">
              <span>An order of magnitude cheaper</span>
              <p>The knowledge is produced autonomously by its creator, not commissioned, so there is no production chain for the buyer to pay for.</p>
            </div>
          </div>
          <div class="lp-shift-row">
            <div class="lp-shift-old">
              <span>Manual dispatch</span>
              <p>Post a job, recruit, dispatch, review, deliver — a human in every step.</p>
            </div>            <div class="lp-shift-new">
              <span>Fully automated, no broker</span>
              <p>An agent discovers, previews, and pays directly; that real usage is what earns the knowledge base its reputation — no one posting or dispatching work in between.</p>
            </div>
          </div>
          <div class="lp-shift-row">
            <div class="lp-shift-old">
              <span>Piecework for the maker</span>
              <p>One-off task income; the vendor keeps the catalog and the margin.</p>
            </div>            <div class="lp-shift-new">
              <span>Ownership and a compounding asset</span>
              <p>The creator keeps ownership and controls access and price. Because owned knowledge is reusable, both the knowledge and the revenue accumulate as they keep building for their own work.</p>
            </div>
          </div>
          <div class="lp-shift-row">
            <div class="lp-shift-old">
              <span>Generic, made to pass review</span>
              <p>Vendors can only produce generic to-spec data, and piecework drifts toward whatever just passes the buyer's review.</p>
            </div>            <div class="lp-shift-new">
              <span>First-party and true at the source</span>
              <p>Built for the creator's own work, learning, and research — knowledge vendors can't reach, and never shaped to pass someone's check.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-team-tile">
    <div class="lp-sec-inner">
      <div class="lp-team-tile">
        <div class="lp-team-tile-text">
          <h2 class="lp-sec-h">For teams →</h2>
          <p class="lp-sec-sub">A shared living brain for your team. Captures from Slack, meetings, and tickets at the edge; synthesized through compile and distill; readable and queryable by every member and every agent.</p>
        </div>
        <a href="#/team" class="lp-team-tile-cta">See Noosphere·Team →</a>
      </div>
    </div>
  </section>

  <footer class="lp-footer">
    <div class="lp-footer-row">
      <span class="lp-footer-brand"><svg width="14" height="14" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere · <span class="lp-footer-copy">© 2026</span></span>
      <span class="lp-footer-social">
        <a href="https://github.com/steveyeow/noosphere" target="_blank" rel="noopener" class="lp-footer-ico" title="GitHub"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg></a>
        <a href="https://discord.gg/8PAmqAU24R" target="_blank" rel="noopener" class="lp-footer-ico" title="Discord"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg></a>
      </span>
    </div>
  </footer>
</div>`;
  document.getElementById('lp-go').onclick=()=>{
    if(_cloudMode&&!_authUser){location.hash='#/login'}else{location.hash='#/main'}
  };
  const ctaCloud=document.getElementById('lp-cta-cloud');
  if(ctaCloud)ctaCloud.onclick=()=>{if(_cloudMode&&!_authUser){location.hash='#/login'}else{location.hash='#/main'}};
  document.getElementById('lp-dark-btn').onclick=toggleTheme;
  renderMigrateLogos();drawLPGraph();animateLPTerm()}

/* Connector logo wall inside the Ingest → Connect method. Display-only:
   no click handler, no status badge — it's purely a recognition cue
   ("your tool is supported"), not an interactive surface. Real bundled
   brand logos live in /static/logos (no third-party runtime dependency,
   works self-hosted/offline). Covers the product's connector set: note
   tools first, then live work sources, then feeds. RSS uses the universal
   feed mark in the product's RSS orange. Apple Notes and generic email
   forwarding are intentionally absent — no real brand logo exists for
   them; both still appear on the full /connectors page. */
const _MIG_LOGOS=[
  {name:'Obsidian',file:'obsidian.svg'},
  {name:'Notion',file:'notion.svg'},
  {name:'Readwise',file:'readwise.png'},
  {name:'Evernote',file:'evernote.svg'},
  {name:'Twitter / X',file:'x.svg'},
  {name:'GitHub',file:'github.svg'},
  {name:'Google Drive',file:'gdrive.svg'},
  {name:'Gmail',file:'gmail.svg'},
  {name:'Slack',file:'slack.svg'},
  {name:'RSS',file:'rss.svg'},
];
function renderMigrateLogos(){
  const el=document.getElementById('lp-mig-logos');if(!el)return;
  el.innerHTML=_MIG_LOGOS.map(l=>`<span class="lp-mig-logo" title="${esc(l.name)}">
      <span class="lp-mig-ico"><img src="/static/logos/${l.file}" alt="${esc(l.name)}" loading="lazy" /></span>
    </span>`).join('');
}

function renderLPTeam(){const el=document.getElementById('page-landing');el.innerHTML=`<div class="lp lp-team">
  <nav class="lp-top"><a href="#/" class="lp-brand"><svg width="17" height="17" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere</a><div class="lp-top-right"><a href="#/" class="lp-top-link">For solo creators</a><button class="lp-dark-btn" id="lp-team-dark-btn" title="Toggle dark mode"><svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg><svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button></div></nav>

  <section class="lp-hero lp-hero-team">
    <div class="lp-ct lp-ct-wide">
      <div class="lp-h">
        <span class="lp-eyebrow">Noosphere · Team</span>
        <h1 class="lp-h1">A shared living brain<br class="lp-h1-br"/>for your team.</h1>
        <p class="lp-sub">Capture from the edge — Slack, email, meetings, decisions, customer calls. Synthesize with compile and distill — readable and queryable by every agent your team runs. Learn from the global agent knowledge network. With full access control — keep private, share for free, or get paid. Build the intelligence layer for your team.</p>
        <button class="lp-go" id="lp-team-go">Start your team's Noosphere →</button>
      </div>
      <div class="lp-team-funnel">
        <div class="lp-funnel-col">
          <div class="lp-funnel-h">Sources</div>
          <ul class="lp-funnel-list">
            <li>Linear / Jira tickets</li>
            <li>Slack channels</li>
            <li>Customer feedback</li>
            <li>Sales calls &amp; transcripts</li>
            <li>Meeting notes</li>
            <li>Daily standups</li>
            <li>Design docs &amp; plans</li>
          </ul>
        </div>
        <div class="lp-funnel-arrow">→</div>
        <div class="lp-funnel-target">
          <span>Intelligence layer for your team</span>
          <ul class="lp-funnel-target-list">
            <li>Captures every edge</li>
            <li>Agent-readable</li>
            <li>Self-compiling</li>
            <li>Learns from the network</li>
            <li>You control access</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-bring">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Capture from the edge.</h2>
      <p class="lp-sec-sub">Knowledge enters at the point of work — not as a separate authoring task. Every member contributes by doing their job; the system attributes and indexes automatically.</p>
      <div class="lp-cards">
        <div class="lp-card">
          <h3 class="lp-card-h">Slack &amp; team chat</h3>
          <p class="lp-card-p">Save a thread, channel, or decision into the right corpus with a single slash command — auto-attributed to the contributor.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Email &amp; customer feedback</h3>
          <p class="lp-card-p">Each corpus gets its own forwarding address. Pipe customer email, sales notes, support threads, and alerts straight in.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Meetings &amp; calls</h3>
          <p class="lp-card-p">Paste or forward transcripts from Granola, Otter, or Fireflies. Decisions, customer calls, and standups stay queryable forever.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Docs, drives &amp; tickets</h3>
          <p class="lp-card-p">One OAuth covers Notion, Google Drive, GitHub, Linear, Jira, and Gmail across the whole team. Install once; every member benefits.</p>
        </div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-agent">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">A brain that compiles itself as the team works.</h2>
      <p class="lp-sec-sub">Every message, ticket, decision, and call extends the team brain. Compile recipes turn that raw substrate into briefings every member — and every agent — can ask against. The longer the team works, the smarter the brain gets.</p>
      <div class="lp-tool-list">
        <div class="lp-tool"><code>weekly digest</code><span>What shipped, what shifted, what's blocked — auto-compiled across all org corpora.</span></div>
        <div class="lp-tool"><code>decision log</code><span>Extract decisions and rationale from threads, meetings, design docs.</span></div>
        <div class="lp-tool"><code>customer-pain synthesis</code><span>Pattern-match across feedback, calls, support — surfacing what matters.</span></div>
        <div class="lp-tool"><code>onboarding pack</code><span>Auto-generated "what a new hire needs to know" from your org's actual record.</span></div>
        <div class="lp-tool"><code>ops dashboards</code><span>Saved queries rendered as cards: hiring, sales, eng, anything.</span></div>
        <div class="lp-tool"><code>distill</code><span>Org-aware interview templates capture tacit founder/expert knowledge before it leaves.</span></div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-network">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Plug into the global knowledge network.</h2>
      <p class="lp-sec-sub">Your team's brain isn't a silo. Every agent your team runs queries domain corpora, peer-team expertise, and public knowledge bases through the same interface that hits your internal record. External knowledge flows in — without leaving your workspace.</p>
      <div class="lp-team-funnel lp-network-funnel">
        <div class="lp-funnel-col">
          <div class="lp-funnel-h">Global knowledge network</div>
          <ul class="lp-funnel-list">
            <li>Domain expert corpora</li>
            <li>Peer-team expertise</li>
            <li>Public knowledge bases</li>
            <li>Specialty &amp; consulting practices</li>
            <li>Research labs &amp; archives</li>
            <li>Open-source documentation</li>
          </ul>
        </div>
        <div class="lp-funnel-arrow">→</div>
        <div class="lp-funnel-target"><span>Every agent your team runs</span><small>Queries the network through your team brain</small></div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-rules">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Self-host or run on cloud.</h2>
      <p class="lp-sec-sub">Same MIT/BSL line as personal: org primitives in open source; multi-tenant hosting and Stripe Connect in cloud.</p>
      <div class="lp-cards">
        <div class="lp-card">
          <h3 class="lp-card-h">Self-hosted Team</h3>
          <p class="lp-card-p">Single org per instance. Full org primitives, members, roles, audit log, contributor attribution. Bring your own Stripe and keep 100% of any paid-corpus revenue. Auth: single OIDC or basic password.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Cloud Team</h3>
          <p class="lp-card-p">Personal workspace plus N orgs, switchable from the top-left. Hosted billing, email invites, hosted SSO. Stripe Connect with 10% platform fee on paid-corpus revenue. $49 / seat / month, 3–50 seats.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">One product, one DB</h3>
          <p class="lp-card-p">Team is an extension of the same Noosphere — same MCP/REST, same compile/distill engine. A Pro user who later forms a team keeps everything; the corpus just gains an <code>org_id</code>.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Roles &amp; attribution</h3>
          <p class="lp-card-p">Owner / admin / editor / viewer apply across all org corpora. Every doc records who added it — queryable, audit-loggable, optionally usable for revenue weighting.</p>
        </div>
      </div>
    </div>
  </section>

  <section class="lp-sec lp-sec-archetypes">
    <div class="lp-sec-inner">
      <h2 class="lp-sec-h">Built for many kinds of teams.</h2>
      <p class="lp-sec-sub">Same Noosphere, different access-level mixes. Whether your knowledge stays private or goes to market, the global agent knowledge network compounds value for every team on it.</p>
      <div class="lp-cards">
        <div class="lp-card">
          <h3 class="lp-card-h">Startup &amp; internal teams</h3>
          <p class="lp-card-p">Engineering teams, startups, ops, customer success. The brain stays fully private — yet your agents still learn from the wider network: domain corpora, public expertise, peer teams' published knowledge. Contribute nothing outward, still get smarter from what others publish.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Research &amp; lab teams</h3>
          <p class="lp-card-p">Research labs, R&amp;D groups, academic teams. Private internal corpora alongside public research corpora. The same workspace that runs ongoing research becomes its own ambient distribution surface — every paper, dataset, and note queryable by any agent on the network.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Creator, newsletter &amp; MCN teams</h3>
          <p class="lp-card-p">Newsletter teams, content collectives, MCNs, indie media. The knowledge you produce becomes a living, queryable product. Free corpora attract readers; paid corpora capture subscriber and agent revenue. One workspace runs the team and publishes to the network.</p>
        </div>
        <div class="lp-card">
          <h3 class="lp-card-h">Consulting &amp; expert practices</h3>
          <p class="lp-card-p">Consulting firms, specialty practices, expert networks, investment teams. Build corpora explicitly to sell — to clients, to other teams' agents, to the open market. Per-contributor attribution makes collaborative authorship economically real; org-level Stripe lets the team capture revenue directly.</p>
        </div>
      </div>
    </div>
  </section>

  <footer class="lp-footer">
    <div class="lp-footer-row">
      <span class="lp-footer-brand"><svg width="14" height="14" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg> Noosphere · <span class="lp-footer-copy">© 2026</span></span>
      <span class="lp-footer-social">
        <a href="https://github.com/steveyeow/noosphere" target="_blank" rel="noopener" class="lp-footer-ico" title="GitHub"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg></a>
        <a href="https://discord.gg/8PAmqAU24R" target="_blank" rel="noopener" class="lp-footer-ico" title="Discord"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg></a>
      </span>
    </div>
  </footer>
</div>`;
  const goHandler=()=>{if(_cloudMode&&!_authUser){location.hash='#/login'}else{location.hash='#/main'}};
  const g1=document.getElementById('lp-team-go');if(g1)g1.onclick=goHandler;
  const dk=document.getElementById('lp-team-dark-btn');if(dk)dk.onclick=toggleTheme;
  window.scrollTo(0,0);
}

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
  // Demo narrative follows the hero loop: publish → connected → queried → paid.
  // Each block = one verb in that chain. Kept short so the whole loop runs in
  // roughly 10 seconds — no user waits more than a beat between payoffs.
  const lines=[
    {delay:400,type:'cmd',text:'> Publish: "Pricing for early-stage SaaS"'},
    {delay:900,type:'out',text:'Indexed · 12 concepts · 47 entities resolved from [[wikilinks]]'},
    {delay:500,type:'status',text:'LIVE',label:'Joined the agent internet'},
    {delay:800,type:'out',text:''},
    {delay:300,type:'cmd',text:'> Connect: rss.substack.com/lenny/feed'},
    {delay:900,type:'out',text:'Ingested 47 posts · knowledge base is growing'},
    {delay:700,type:'out',text:''},
    {delay:300,type:'cmd',text:'> Agent query from [coinbase-startup-agent]'},
    {delay:800,type:'out',text:'"what pricing model for B2B AI infra?"'},
    {delay:1100,type:'result',score:'0.88',text:'"For early-stage B2B AI infra, usage-based pricing with a minimum floor aligns incentives better than seat licenses..."',cite:'"Pricing for early-stage SaaS" — §2'},
    {delay:600,type:'out',text:''},
    {delay:400,type:'status',text:'PAID',label:'$0.05 → wallet $12.90 · kb_reputation 0.73'},
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
      const st=l.text==='INDEXED'?'#3b82f6':l.text==='CREATING'?'#f59e0b':l.text==='LIVE'?'#22c55e':l.text==='PAID'?'#d4a017':'#86868b';
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
function drawLPGraph(){
  const co=document.getElementById('lp-cv');if(!co)return;
  // Curated mock data only — live corpora from /corpora would have foreign
  // tags that don't overlap with the curated set, leaving them as orphan
  // nodes on the perimeter. The landing graph is a brand visual, not a
  // live snapshot. (Feynman does the same: hardcoded LP_MINDS list.)
  // 53 nodes, matching Feynman 1:1.
  const DM=DM_FALLBACK.slice(0,53);

  const tk=m=>(m.d||'').split(/[,;\/&]+/).map(d=>d.trim().toLowerCase()).filter(Boolean);
  const ns=DM.map((m,i)=>({
    id:'l'+i,
    name:m.n,
    dom:m.d||'',
    color:m.c||cC(m.n),
    ini:m.n.split(/\s+/).slice(0,2).map(w=>w[0]).join('').toUpperCase(),
    tk:tk(m),
  }));

  // Tag-overlap linking only — no random-edge floor. Edges come from real
  // domain overlap; if a node has no overlap it stays loosely tethered.
  const lk=[];
  for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){
    const shared=ns[i].tk.filter(t=>ns[j].tk.some(u=>t===u||t.includes(u)||u.includes(t)));
    if(shared.length)lk.push({source:ns[i].id,target:ns[j].id,s:shared.length});
  }
  // Star-fallback only when literally zero overlaps exist.
  if(!lk.length&&ns.length>1){
    for(let i=1;i<ns.length;i++)lk.push({source:ns[0].id,target:ns[i].id,s:.3});
  }

  const dp=devicePixelRatio||1;
  const W=co.clientWidth||800,H=co.clientHeight||600;
  // Match Feynman BASE_R = 20–30
  const BR=Math.max(20,Math.min(30,W/(ns.length*2)));
  const cv=document.createElement('canvas');
  cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';
  co.appendChild(cv);
  const cx=cv.getContext('2d');cx.scale(dp,dp);

  // Particles flowing along links — density scales with link strength
  const pts=[];
  lk.forEach(l=>{
    const count=Math.max(1,Math.round(l.s*1.5));
    for(let i=0;i<count;i++)pts.push({l,t:Math.random(),sp:.001+Math.random()*.003,sz:1+Math.random()*1.5,op:.3+Math.random()*.5});
  });

  // Feynman 1:1 — fixed avoid zone for hero text (heroW=300, heroH=200
  // positioned at W*0.06+150). Tried adapting to our actual .lp-h rect
  // (367×453) but that's 16% of the canvas vs Feynman's 3% — node
  // simulation can't escape such a large zone in our smaller canvas.
  // Some hero text spills outside this zone; the .lp-h::before radial
  // gradient softens any nodes that drift behind, which is the design.
  const heroW=300,heroH=200;
  const heroCx=W*0.06+heroW/2,heroCy=H/2;
  const heroHalfW=heroW/2+30,heroHalfH=heroH/2+10;
  const clearZones=[{cx:heroCx,cy:heroCy,hw:heroHalfW,hh:heroHalfH}];
  // Mission signature at hero bottom-left — protect it from node-label
  // overlap. Measured at runtime since left/bottom use clamp() values.
  const coRect=co.getBoundingClientRect();
  const missionEl=document.querySelector('.lp-hero-mission');
  if(missionEl){
    const mr=missionEl.getBoundingClientRect();
    if(mr.width>0){
      clearZones.push({
        cx:mr.left-coRect.left+mr.width/2,
        cy:mr.top-coRect.top+mr.height/2,
        hw:mr.width/2+20,
        hh:mr.height/2+15,
      });
    }
  }
  function makeAvoidForce(){
    let nodes;
    function force(){
      for(const n of nodes){
        for(const z of clearZones){
          const dx=n.x-z.cx,dy=n.y-z.cy;
          const ox=z.hw-Math.abs(dx),oy=z.hh-Math.abs(dy);
          if(ox>0&&oy>0){
            if(ox<oy){const sg=dx>=0?1:-1;n.vx+=sg*ox*0.08;n.vx*=.85;}
            else{const sg=dy>=0?1:-1;n.vy+=sg*oy*0.08;n.vy*=.85;}
          }
        }
      }
    }
    force.initialize=function(n){nodes=n;};
    return force;
  }

  // Spread initial positions across the canvas. d3's default phyllotaxis
  // packs everyone near (0,0); with Feynman's weak forceX/Y (.01) that
  // doesn't get redistributed before alpha decays. Random initial spread
  // gives the same final distribution Feynman gets organically on its
  // larger canvas.
  const graphCx=W*0.55;
  ns.forEach(n=>{n.x=graphCx+(Math.random()-.5)*W*.7;n.y=H/2+(Math.random()-.5)*H*.7;});
  const sim=d3.forceSimulation(ns)
    .force('link',d3.forceLink(lk).id(d=>d.id).distance(d=>Math.max(80,280-d.s*70)).strength(d=>.08+d.s*.15))
    .force('charge',d3.forceManyBody().strength(-600).distanceMax(800))
    .force('center',d3.forceCenter(graphCx,H/2).strength(.02))
    .force('collision',d3.forceCollide().radius(BR+20))
    .force('x',d3.forceX(graphCx).strength(.01))
    .force('y',d3.forceY(H/2).strength(.01))
    .force('avoid',makeAvoidForce())
    .alphaDecay(.03).velocityDecay(.35);

  let hov=null,mp=null;
  cv.addEventListener('mousemove',e=>{
    const r=cv.getBoundingClientRect();
    const mx=e.clientX-r.left,my=e.clientY-r.top;
    mp=[mx,my];hov=null;
    for(const n of ns){
      if(Math.hypot(n.x-mx,n.y-my)<BR+5){hov=n;break}
    }
    cv.style.cursor=hov?'pointer':'default';
  });
  cv.addEventListener('mouseleave',()=>{hov=null;mp=null});

  function draw(){
    const now=performance.now();
    const dk=isDark();
    cx.save();
    cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';
    cx.fillRect(0,0,W,H);

    // Links — match Feynman alpha/lineWidth
    for(const l of lk){
      const s=l.source,t=l.target;
      cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);
      cx.strokeStyle=dk?`rgba(170,185,210,${.12+l.s*.08})`:`rgba(140,155,180,${.12+l.s*.08})`;
      cx.lineWidth=.6+l.s*.4;
      cx.stroke();
    }

    // Particles — match Feynman 0.45 alpha
    for(const p of pts){
      p.t+=p.sp;if(p.t>1)p.t-=1;
      const s=p.l.source,t=p.l.target;
      const px=s.x+(t.x-s.x)*p.t,py=s.y+(t.y-s.y)*p.t;
      cx.beginPath();cx.arc(px,py,p.sz,0,Math.PI*2);
      cx.fillStyle=dk?`rgba(200,220,255,${p.op*.45})`:`rgba(130,150,200,${p.op*.45})`;
      cx.fill();
    }

    // Nodes — with mouse focus zoom (Feynman's trick: nodes near cursor grow)
    for(const n of ns){
      const hovered=hov===n;
      let r=BR;
      if(mp){
        const dx=n.x-mp[0],dy=n.y-mp[1];
        const dist=Math.sqrt(dx*dx+dy*dy);
        const focusR=250;
        if(dist<focusR){
          const t=1-dist/focusR;
          r=BR*(1+t*0.4);
        }else{
          r=BR*0.9;
        }
      }
      if(hovered)r=Math.max(r,BR*1.6);
      const pulse=1+Math.sin(now*.002+n.name.length)*.04;
      const rr=r*pulse;
      const[cr,cg,cb]=hR(n.color);

      // Glow — match Feynman alpha
      const glowR=rr*2.5;
      const grad=cx.createRadialGradient(n.x,n.y,rr*.5,n.x,n.y,glowR);
      grad.addColorStop(0,`rgba(${cr},${cg},${cb},${hovered?.15:.05})`);
      grad.addColorStop(1,'rgba(255,255,255,0)');
      cx.beginPath();cx.arc(n.x,n.y,glowR,0,Math.PI*2);cx.fillStyle=grad;cx.fill();

      // Hover ring
      if(hovered){
        cx.beginPath();cx.arc(n.x,n.y,rr+3,0,Math.PI*2);
        cx.strokeStyle=`rgba(${cr},${cg},${cb},.5)`;cx.lineWidth=2;cx.stroke();
      }

      // Node ball
      cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);
      cx.fillStyle=n.color;cx.fill();
      cx.strokeStyle='rgba(255,255,255,.25)';cx.lineWidth=1.5;cx.stroke();

      // Initials
      cx.fillStyle='rgba(255,255,255,.95)';
      cx.font=`700 ${rr*.6}px Inter,sans-serif`;
      cx.textAlign='center';cx.textBaseline='middle';
      cx.fillText(n.ini,n.x,n.y);

      // Name label — single line only. Feynman renders a domain subtitle
      // beneath each node but on our smaller canvas it doubles the visual
      // weight per node and the network reads as cluttered. Names alone
      // are enough to convey "this is a wiki on X".
      cx.fillStyle=dk?`rgba(245,245,247,${hovered?.95:.8})`:`rgba(30,35,50,${hovered?.9:.7})`;
      cx.font=`600 ${hovered?12:11}px 'Libre Baskerville',Georgia,serif`;
      cx.fillText(n.name,n.x,n.y+rr+14);
    }

    cx.restore();
    _lpAnim=requestAnimationFrame(draw);
  }

  sim.on('tick',()=>{});
  _lpAnim=requestAnimationFrame(draw);
}

/* ══════ HOME — Terminal (input top, output below) ══════ */
const TERM_STATUS_C={READY:'#10b981',INDEXED:'#3b82f6',CREATED:'#f59e0b'};
let _termCtx={};

function renderHome(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.classList.add('content--home');
  const _h=new Date().getHours();
  const _tod=_h<12?'Good morning':_h<18?'Good afternoon':'Good evening';
  // Preferred name (user-chosen, persisted) wins over the heuristic
  // first-name extraction; both fall through to the bare time-of-day
  // greeting so the page never reads as "Good evening, ".
  const greetName=(_userDisplayName||'').trim()||_firstName;
  const greetText=greetName?`${_tod}, ${greetName}`:_tod;

  ct.innerHTML=`<div class="home" id="home">
    ${workspaceEyebrowHTML()}
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
            <button class="composer-mode-label" id="home-mode-label" type="button" title="Composer mode">Enrich mode</button>
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
  const attachBtn=document.getElementById('home-attach');
  // Pass enterWrite as onWrite so the popover's "Write a note" item can flip
  // the composer into note-editor mode. Defined further down in this same
  // closure, but JS hoisting via the function declaration makes the
  // reference resolve at click time.
  if(attachBtn)attachBtn.onclick=(e)=>showAttachPopover(e.currentTarget,output,input,{onWrite:()=>enterWrite()});
  // Safety net — whenever term-output becomes empty, clear home--active.
  // Every panel that collapses the home greeting must render into
  // term-output; every panel's removal hits this observer. If a future
  // connector/panel forgets to remove home--active in its cancel handler,
  // the composer still recovers here. Install once per home mount.
  _installHomeActiveWatcher(output);
  // Mode label is the sole entry point for the mode picker now — the
  // separate sliders toggle was removed because the popover only controls
  // mode (sources moved into the + menu).
  const modeLabelBtn=document.getElementById('home-mode-label');
  if(modeLabelBtn)modeLabelBtn.onclick=(e)=>showSourcesPopover(e.currentTarget,{corpusId:null,corpusName:null});
  // Scoped corpus: null means "Any" (default). Persists across sends.
  // Hoisted to module-level _homeScope so the Recently compiled section and
  // the Compile picker can read the same selection. Consumes _pendingHomeScope
  // if a corpus page's "Chat with X" CTA pre-selected one before navigating here.
  _homeScope=_pendingHomeScope||null;
  _pendingHomeScope=null;
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
  // Initial paint — honors _homeScope set from _pendingHomeScope above.
  updateChip();
  // Resume an existing chat session — sidebar/Chats clicks navigate here
  // with ?session=<sid>. Fetch the session, scope the chip to its corpus,
  // replay messages into term-output, and arm _termCtx so the next user
  // turn extends the same session (instead of opening a fresh one in
  // chat_sessions). Failures fall through silently so a stale link just
  // leaves the user on a blank New Chat instead of an error screen.
  if(_pendingHomeSession){
    const sid=_pendingHomeSession;
    _pendingHomeSession=null;
    (async()=>{
      try{
        const r=await fetch(`${API}/chat-sessions/${sid}`);
        if(!r.ok)return;
        const session=await r.json();
        const msgs=Array.isArray(session.messages)?session.messages:[];
        if(session.corpus_id){
          _homeScope=session.corpus_id;
          updateChip();
        }
        _termCtx={session_id:sid};
        if(msgs.length){
          collapseToChat();
          for(const m of msgs){
            if(m.role==='user'){addLine(output,'prompt',m.content||'');continue}
            // Prefer the structured payload (resp / card / option / search_result
            // bubbles, one per addLine) so the resumed turn renders identically
            // to the original. Fall back to a single resp built from the
            // flattened content for pre-migration rows or non-/terminal chats.
            if(Array.isArray(m.lines)&&m.lines.length){
              for(const ln of m.lines){
                if(ln&&ln.type)addLine(output,ln.type,null,null,ln);
              }
            }else{
              addLine(output,'resp',m.content||'');
            }
          }
        }
      }catch(e){}
    })();
  }
  // Consume any pre-filled draft from a corpus-page chat dock. Auto-send fires
  // on next tick so placeholder/chip paint first and the send flow sees the
  // final state (otherwise scope might not be read yet by the send handler).
  if(_pendingHomeInput){
    const pending=_pendingHomeInput;const shouldSend=_pendingHomeAutoSend;
    _pendingHomeInput=null;_pendingHomeAutoSend=false;
    input.value=pending;
    autosize();
    if(shouldSend){setTimeout(()=>{sendBtn?.click()},0)}
    else{input.focus()}
  }
  // One-shot: corpus page's attach popover handed off to us. Corpus is already
  // pre-selected via _pendingHomeScope; now collapse home to chat mode and
  // render the matching panel (upload/url/archive/rss) into the chat stream
  // so the user lands directly on the right form, scoped to the corpus.
  if(_pendingHomeAttachAction){
    const action=_pendingHomeAttachAction;
    _pendingHomeAttachAction=null;
    setTimeout(()=>{
      // Only collapse home for actions that render INTO term-output.
      // add-source opens an overlay; the observer would eventually clear
      // a premature collapse, but skipping it avoids a flash.
      const collapseHome=()=>{const h=document.getElementById('home');if(h)h.classList.add('home--active')};
      if(action==='upload'){collapseHome();showTermUpload(output,input,_homeScope)}
      else if(action==='url'){collapseHome();showTermUpload(output,input,_homeScope);setTimeout(()=>{document.querySelector('.term-upload-tab[data-tab="url"]')?.click()},50)}
      else if(action==='rss'){collapseHome();showTermConnectRSS(output,input,_homeScope)}
      else if(action==='add-source'){showAddSourcePicker({corpusId:null})}
      // Write coming back from the corpus page — _homeScope was pre-set so
      // saveNote() on commit drops the note into the right KB.
      else if(action==='write'){enterWrite()}
    },0);
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
    // Note: a `slidersBtn` toggle used to live here but was removed when
    // the mode picker collapsed into the mode-label popover — see the
    // comment near `modeLabelBtn` setup. The lingering reference threw
    // a ReferenceError that aborted the rest of enterWrite, leaving the
    // hint visible and the cancel hidden in write mode.
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
      el.onclick=()=>{_homeScope=el.dataset.id||null;updateChip();closeChipMenu();_refreshComposerPlaceholder();input.focus()};
    });
    const nameEl=menu.querySelector('#chip-new-name'),goEl=menu.querySelector('#chip-new-go');
    const createNew=async()=>{
      const nm=nameEl.value.trim();if(!nm){nameEl.focus();return}
      goEl.disabled=true;goEl.textContent='…';
      try{
        const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm,access_level:'public'})});
        if(!r.ok){
          // Route through the unified quota handler so 429s render with an
          // Upgrade CTA (toast w/ action button for resource limits, full
          // paywall modal for daily quota_exceeded). 409 → "open existing"
          // affordance via handleDuplicateCorpus. Falls back to a plain toast
          // for everything else (auth, validation).
          const d=await r.json().catch(()=>({}));
          if(!handleQuotaError(r,d)&&!handleDuplicateCorpus(r,d)){
            const msg=(d.detail&&typeof d.detail==='object'?d.detail.message:d.detail)||`HTTP ${r.status}`;
            toast(msg,'error');
          }
          closeChipMenu();
          return;
        }
        const c=await r.json();
        await loadC();
        _homeScope=c.id;
        // Drop back to Enrich mode after spinning up a fresh KB — the
        // user's next action is almost always to feed it (chat / note /
        // URL / file), not to create another corpus. Without this flip,
        // the composer stays on Create mode and its placeholder + mode
        // label remain stuck on the create-prompt, even though the chip
        // correctly shows the new corpus. Mirrors the post-create UX of
        // the Create-mode terminal flow so both create paths feel
        // identical.
        _composerMode='enrich';
        updateChip();           // updates chip + calls _refreshComposerPlaceholder
        closeChipMenu();
        toast(`Created ${nm}`,'success');
        renderSBChats();
        input.focus();
      }catch(e){toast('Failed to create corpus: '+e.message,'error');goEl.disabled=false;goEl.textContent='Create'}
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
      else{addLine(output,'resp','Recent conversations:');_chatSessions.slice(0,10).forEach(c=>{const el=document.createElement('div');el.className='term-line term-option';el.innerHTML=NOOS_DOT+'<span><span style="color:var(--tx3);margin-right:8px">'+esc(c.corpus_name||'')+'</span>'+esc(c.title||'Untitled')+'</span>';el.onclick=()=>{location.hash='#/main?session='+c.id};output.appendChild(el)})}
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
      async function doCreate(){
        const name=ni.value.trim();if(!name)return;wrap.remove();
        try{
          const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,access_level:'public'})});
          if(!r.ok){
            const d=await r.json().catch(()=>({}));
            if(handleDuplicateCorpus(r,d)){input.focus();return}
            const msg=(d.detail&&typeof d.detail==='object'?d.detail.message:d.detail)||`HTTP ${r.status}`;
            addLine(output,'resp','Failed: '+msg);input.focus();return;
          }
          const c=await r.json();await loadC();
          addLine(output,'card',null,null,{type:'card',label:name,status:'CREATED',detail:'New knowledge base created',corpus_id:c.id});
          renderSBChats();
        }catch(e){addLine(output,'resp','Failed: '+e.message)}
        input.focus();
      }
      document.getElementById('new-corpus-btn').onclick=doCreate;ni.onkeydown=e=>{if(e.key==='Enter')doCreate();if(e.key==='Escape'){wrap.remove();input.focus()}};
      return;
    }
    _sending=true;input.value='';autosize();input.disabled=true;
    collapseToChat();
    addLine(output,'prompt',val);
    const loadId='ld-'+Date.now();
    addLine(output,'thinking','Thinking…',loadId);
    // Restore the typed text if the request fails — we cleared the input above
    // so the prompt line could echo it, but if the network fails the user has
    // nothing to retry with otherwise. Cleared once the request returns OK.
    const restoreDraft=()=>{
      if(input.value)return;  // user already typed something else, don't clobber
      input.value=val;
      autosize();
    };
    try{
      const r=await fetch(`${API}/terminal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:val,context:_termCtx,mode:_composerMode,corpus_id:_homeScope||null})});
      if(!r.ok){
        document.getElementById(loadId)?.remove();
        const errBody=await r.json().catch(()=>({}));
        const msg=(errBody.detail&&typeof errBody.detail==='object'?errBody.detail.message:errBody.detail)||`HTTP ${r.status}`;
        addLine(output,'resp','Error: '+msg+' — your message is restored, press Send to retry.');
        restoreDraft();
        input.disabled=false;input.focus();_sending=false;
        return;
      }
      const d=await r.json();
      document.getElementById(loadId)?.remove();
      _termCtx=d.context||{};
      // Surface freshly-persisted chat sessions in the sidebar — the backend
      // only writes a session when the request was scoped to a corpus, so
      // we re-render lazily on each turn that returns one.
      if(d.session_id)renderSBChats();
      for(const line of(d.lines||[]))addLine(output,line.type,null,null,line);
      if(d.context?.action==='open_write'){enterWrite()}
      if(d.context?.action==='open_upload'){showTermUpload(output,input,_homeScope)}
      // Quota tripped during Create-mode — the resp line above already
      // explains what happened, but the user needs the paywall CTA to
      // act on it. Open the same modal /corpora 429s use so the upsell
      // is unified across entry points.
      if(d.context?.action==='quota_exceeded'){
        showProModal(d.context.message||'Upgrade to Pro for higher limits.');
      }
      // Create-mode result: backend just spun up a new KB. Drop the user
      // back into Enrich with that KB pre-selected on the chip — so their
      // very next URL/file/note flows straight into the new corpus without
      // them having to manually pick it. Mirrors the post-create UX of the
      // /new slash flow above so the two paths feel consistent.
      if(d.context?.action==='corpus_created' && d.context.corpus_id){
        _composerMode='enrich';
        _homeScope=d.context.corpus_id;
        await loadC();
        updateChip();
        renderSBChats();
      }
    }catch(err){
      document.getElementById(loadId)?.remove();
      addLine(output,'resp','Error: '+err.message+' — your message is restored, press Send to retry.');
      restoreDraft();
    }
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
// Daily-produced content shapes — workspace-aware, since the moments worth
// capturing differ between solo creators and teams.
//
// Personal — individual reflective surfaces:
//   - Random thoughts          → volume capture; no judgment, just dump
//   - Skill I'm learning       → growth over time; the KB accumulates expertise
//   - Reading notes            → external input curation; you read, Noos keeps it
//   - Question I'm chewing on  → long-lived unfinished content; traditional notes
//                                apps are worst at this — Noosphere's retrieval
//                                + living wiki surfaces old open questions when
//                                new info arrives. Signals "you don't have to
//                                finish writing to save it."
//
// Team — edge-of-work moments worth sharing into the team brain:
//   - Meeting takeaway   → the artifact teams already produce daily; the brain
//                          grows from what was decided, not just what was said
//   - Decision we made   → context-rich rationale that future hires/agents need
//   - Customer signal    → frontline observations (sales / support / research)
//                          that otherwise stay in DMs and email
//   - What I shipped     → async standup tone; lightweight, builds the
//                          team's working memory without a status meeting
const WRITE_SUGGESTIONS_PERSONAL=[
  {title:'Random thoughts'},
  {title:"Skill I'm learning"},
  {title:'Reading notes'},
  {title:"Question I'm chewing on"},
];
const WRITE_SUGGESTIONS_TEAM=[
  {title:'Meeting takeaway'},
  {title:'Decision we made'},
  {title:'Customer signal'},
  {title:'What I shipped'},
];
function _writeSuggestions(){
  return _workspace.kind==='org'?WRITE_SUGGESTIONS_TEAM:WRITE_SUGGESTIONS_PERSONAL;
}
// Minimal line-icon SVGs (no decorative emoji — Feynman aesthetic)
const ICON_CHAT=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
const ICON_PEN=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`;
async function renderHomeTworow(enterWrite){
  // Suggested — workspace-aware list, render immediately
  const sugEl=document.getElementById('home-col-suggested');
  if(sugEl){
    sugEl.innerHTML=_writeSuggestions().map(s=>`<button class="home-col-item" type="button" data-title="${esc(s.title)}"><span class="home-col-ico">${ICON_PEN}</span><span class="home-col-nm">${esc(s.title)}</span></button>`).join('');
    sugEl.querySelectorAll('.home-col-item').forEach(btn=>{
      btn.onclick=()=>enterWrite(btn.dataset.title);
    });
  }
  // Recent corpora — sort by updated_at desc, show top 3. _corpora is kept
  // fresh by route() (which awaits loadC before calling renderHome) and by
  // every mutation path (upload, rename, delete, create), so we can render
  // synchronously here instead of re-fetching and flashing an empty slot.
  const recEl=document.getElementById('home-col-recent');
  if(!recEl)return;
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
    // Obsidian-style wikilinks — [[target]], [[target#section]], [[target|display]].
    // esc() above already encoded `[` and `]` as entities, so match those.
    // Click handler in _bindWikilinks resolves to an entity page or search.
    .replace(/\[\[([^\[\]|#]+?)(#[^\[\]|]+)?(?:\|([^\[\]]+))?\]\]/g,(_m,target,_frag,display)=>{
      const t=(target||'').trim();
      const d=(display||target||'').trim();
      return `<a href="#" class="wikilink" data-target="${esc(t)}">${esc(d)}</a>`;
    })
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}

/* Bind wikilink click handlers inside a container after it's rendered.
   Attempts to resolve `[[target]]` to an entity in the given corpus (by
   canonical_name or alias, case-insensitive). On match, navigate to the
   entity page. On miss, fall back to corpus-scoped search for the target
   so users never hit a dead link. Kept out of _mdToHtml so the renderer
   stays pure and sync. */
function _bindWikilinks(container,corpusId){
  if(!container)return;
  container.querySelectorAll('a.wikilink').forEach(a=>{
    a.onclick=async(e)=>{
      e.preventDefault();
      const t=a.dataset.target;if(!t)return;
      if(corpusId){
        try{
          const r=await fetch(`${API}/corpora/${corpusId}/entities`);
          if(r.ok){
            const body=await r.json();
            const ents=Array.isArray(body)?body:(body.entities||[]);
            const lc=t.toLowerCase();
            const hit=ents.find(en=>{
              if((en.canonical_name||'').toLowerCase()===lc)return true;
              const aliases=Array.isArray(en.aliases)?en.aliases:[];
              return aliases.some(al=>String(al).toLowerCase()===lc);
            });
            if(hit){location.hash=`#/corpus/${corpusId}/entity/${hit.id}`;return}
          }
        }catch(_e){/* fall through to search */}
        // Fallback: corpus-scoped search for the target text
        location.hash=`#/corpus/${corpusId}?q=${encodeURIComponent(t)}`;
        return;
      }
      toast(`No entity for "${t}" — open a corpus to resolve`,'info');
    };
  });
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
    _revealMarkdown(document.getElementById('cmp-body'),state.truth,()=>{renderSources();_bindWikilinks(document.getElementById('cmp-body'),state.corpusId)});
  }
  function applyEntity(ent){
    state.entityId=ent.id;state.title=ent.canonical_name||'Entity';
    state.truth=ent.description||'';
    document.getElementById('cmp-title').textContent=state.title;
    document.getElementById('cmp-meta').innerHTML=`<span class="cmp-meta-pill">${esc(ent.kind||'entity')}</span>${ent.mention_count?`<span class="cmp-meta-pill">${ent.mention_count} mentions</span>`:''}`;
    document.getElementById('cmp-status').textContent='';
    _revealMarkdown(document.getElementById('cmp-body'),state.truth,()=>{_bindWikilinks(document.getElementById('cmp-body'),state.corpusId)});
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
function showTermUpload(output,input,defaultCorpus,opts){
  opts=opts||{};
  // When lockCorpus is true, the panel is pinned to defaultCorpus and never
  // reads _homeScope — the corpus page uses this so the upload always targets
  // the corpus the user is viewing, regardless of the home chip's stale value.
  const lockCorpus=!!opts.lockCorpus;
  // onComplete replaces the chat-stream success feedback (addLine cards) with
  // a caller-provided callback — the corpus page passes renderCorpus(id) so
  // the Sources list refreshes inline instead of leaving a stray "Added …"
  // line behind.
  const onComplete=typeof opts.onComplete==='function'?opts.onComplete:null;
  const wrap=document.createElement('div');wrap.className='term-upload-wrap';
  let _uFiles=[];let _tab='files';
  wrap.innerHTML=`<div class="term-upload-tabs"><button class="term-upload-tab active" data-tab="files" type="button">Files</button><button class="term-upload-tab" data-tab="url" type="button">URL</button><button class="term-upload-tab" data-tab="paste" type="button">Paste</button></div><div class="term-upload-body" id="tu-body"></div>`;
  output.appendChild(wrap);
  const sc=document.getElementById('term-scroll');if(sc)sc.scrollTop=sc.scrollHeight;
  const body=wrap.querySelector('#tu-body');
  const tabsEl=wrap.querySelectorAll('.term-upload-tab');

  // Shared: resolve a corpus id. On the home composer, read _homeScope FRESH
  // on each call so chip changes between open-panel and submit are respected.
  // On the corpus page (lockCorpus), defaultCorpus is the only answer.
  // Fallbacks: single corpus → auto-create → inline picker.
  async function resolveCorpus(){
    if(lockCorpus)return defaultCorpus||null;
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
  // Report a failure. On home, it streams into the chat; on corpus page, the
  // output container isn't a terminal stream — toast instead.
  function reportErr(msg){
    if(onComplete)toast(msg,'error');
    else addLine(output,'resp',msg);
  }
  // Report a success. On home, stream a resp + card line pair; on corpus
  // page, fire the onComplete callback (e.g. renderCorpus(id)) so the caller
  // refreshes its own UI state.
  function reportOK(respLine,cardDef){
    if(onComplete){onComplete();return}
    addLine(output,'resp',respLine);
    if(cardDef)addLine(output,'card',null,null,cardDef);
  }
  function cancelAndReturn(){
    wrap.remove();
    // Only toggle home--active when we're actually on home. On corpus page
    // onComplete is set and there is no #home element; we'd still no-op but
    // skip the children.length check to be explicit.
    if(!onComplete){
      const home=document.getElementById('home');
      if(home&&!output.children.length)home.classList.remove('home--active');
    }
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
      if(!cid){wrap.remove();reportErr('No corpus selected.');if(input)input.focus();return}
      const fd=new FormData();
      for(const f of _uFiles)fd.append('files',f);
      fd.append('source_kind',body.querySelector('#tu-sk')?.value||'user_original');
      const nFiles=_uFiles.length;
      try{
        const r=await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){reportErr('Upload failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        // Per-file errors — surface them so the user knows which file(s)
        // didn't make it. We previously reported the batch count and the
        // user couldn't tell that, say, file 3 was a corrupted PDF.
        const failedList=d.errors||[];
        if(failedList.length){
          for(const fe of failedList){
            toast(`${fe.file}: ${fe.error}`,'error');
          }
        }
        // Fire-and-forget processing. Debouncer coalesces consecutive ingests
        // into one index run; corpus detail page has a Re-process button for
        // recovery if anything ever fails silently.
        ensureIndexed(cid);
        await loadC();
        const corpus=_corpora.find(c=>c.id===cid);
        const ok=d.uploaded||0;
        const okMsg=ok?`Added ${ok} file${ok>1?'s':''}`:'No files added';
        reportOK(okMsg,{type:'card',label:'Files Added',status:ok?'READY':'EMPTY',detail:corpus?corpus.name:'My Knowledge',val:failedList.length?`${ok} added · ${failedList.length} skipped`:`${ok} file${ok>1?'s':''} added — ingesting in background`,corpus_id:cid});
      }catch(e){wrap.remove();reportErr('Upload failed: '+e.message)}
      if(input&&!onComplete)input.focus();
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
      if(!onComplete){
        const home=document.getElementById('home');
        if(home)home.classList.add('home--active');
      }
      const nextCorpus=lockCorpus?defaultCorpus:(_homeScope||defaultCorpus);
      showTermConnectRSS(output,input,nextCorpus,opts);
      // Pre-fill the RSS panel with what they had typed
      setTimeout(()=>{const rssUrl=document.getElementById('tu-url');if(rssUrl)rssUrl.value=url;const goBtn=document.getElementById('tu-go');if(goBtn)goBtn.disabled=!url},50);
    };
    cancelBtn.onclick=cancelAndReturn;
    goBtn.onclick=async()=>{
      const url=urlEl.value.trim();if(!url)return;
      goBtn.disabled=true;goBtn.textContent='Importing...';cancelBtn.style.display='none';
      const cid=await resolveCorpus();
      if(!cid){wrap.remove();reportErr('No corpus selected.');if(input)input.focus();return}
      const sk=body.querySelector('#tu-sk')?.value||'external_public';
      try{
        const r=await fetch(`${API}/corpora/${cid}/ingest-url`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,source_kind:sk})});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){reportErr('Import failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        ensureIndexed(cid);
        await loadC();
        const corpus=_corpora.find(c=>c.id===cid);
        reportOK(`Imported: "${d.title||d.name||url}"`,{type:'card',label:'URL Imported',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:url,corpus_id:cid});
      }catch(e){wrap.remove();reportErr('Import failed: '+e.message)}
      if(input&&!onComplete)input.focus();
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
      if(!cid){wrap.remove();reportErr('No corpus selected.');if(input)input.focus();return}
      const firstLine=(text.split('\n').find(l=>l.trim())||'').replace(/^#+\s*/,'').trim();
      const title=firstLine.slice(0,80)||('Pasted '+new Date().toLocaleDateString('en-US',{month:'short',day:'numeric'}));
      const fd=new FormData();
      fd.append('files',new Blob(['---\ntitle: '+title+'\n---\n\n'+text],{type:'text/markdown'}),title.replace(/[^a-zA-Z0-9]/g,'-').slice(0,60)+'.md');
      fd.append('source_kind',body.querySelector('#tu-sk')?.value||'external_public');
      try{
        const r=await fetch(`${API}/corpora/${cid}/upload`,{method:'POST',body:fd});
        const d=await r.json();
        wrap.remove();
        if(!r.ok){reportErr('Save failed: '+(d.detail||r.statusText));if(input)input.focus();return}
        ensureIndexed(cid);
        await loadC();
        const corpus=_corpora.find(c=>c.id===cid);
        reportOK(`Saved: "${title}"`,{type:'card',label:'Text Saved',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:title,corpus_id:cid});
      }catch(e){wrap.remove();reportErr('Save failed: '+e.message)}
      if(input&&!onComplete)input.focus();
    };
  }
  // Archive tab removed — app-specific archive imports (Obsidian vault,
  // Notion export, Twitter archive) now live inside their per-app panel,
  // reachable via Composer + → Add a source / My sources, the chint logos,
  // or the Connectors directory. See showTermArchiveUpload + showAppPanel.
  function setTab(t){
    _tab=t;
    tabsEl.forEach(el=>el.classList.toggle('active',el.dataset.tab===t));
    if(t==='files')renderFiles();
    else if(t==='url')renderURL();
    else if(t==='paste')renderPaste();
  }
  tabsEl.forEach(el=>el.onclick=()=>setTab(el.dataset.tab));
  setTab('files');
}

/* ══════ CONNECT RSS FEED ══════
   Persistent source — the backend enrichment loop re-polls registered feeds,
   so this is the one connector that actually keeps flowing. */
function showTermConnectRSS(output,input,defaultCorpus,opts){
  opts=opts||{};
  const lockCorpus=!!opts.lockCorpus;
  const onComplete=typeof opts.onComplete==='function'?opts.onComplete:null;
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
  function reportErr(msg){
    if(onComplete)toast(msg,'error');
    else addLine(output,'resp',msg);
  }
  function reportOK(respLine,cardDef){
    if(onComplete){onComplete();return}
    addLine(output,'resp',respLine);
    if(cardDef)addLine(output,'card',null,null,cardDef);
  }
  cancelBtn.onclick=()=>{
    wrap.remove();
    if(!onComplete){
      const home=document.getElementById('home');
      if(home&&!output.children.length)home.classList.remove('home--active');
    }
    if(input)input.focus();
  };
  goBtn.onclick=async()=>{
    const url=urlEl.value.trim();if(!url)return;
    const maxItems=parseInt(maxEl.value)||25;
    goBtn.disabled=true;goBtn.textContent='Fetching feed...';cancelBtn.style.display='none';
    // On corpus page (lockCorpus), defaultCorpus is the only answer. On home,
    // read _homeScope fresh so late chip-changes are respected.
    let cid=lockCorpus?(defaultCorpus||null):(_homeScope||defaultCorpus||null);
    if(!cid){
      await loadC();
      if(_corpora.length===1){cid=_corpora[0].id}
      else if(_corpora.length===0){
        try{const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My Knowledge',access_level:'public'})});const c=await r.json();cid=c.id;await loadC()}
        catch(e){reportErr('Failed to create corpus.');wrap.remove();if(input)input.focus();return}
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
      if(!r.ok){reportErr('Add feed failed: '+(d.detail||r.statusText));if(input)input.focus();return}
      await loadC();
      const corpus=_corpora.find(c=>c.id===cid);
      const tierNow=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
      const tail=tierNow==='pro'?" Noos will check back every hour.":"";
      reportOK(`Noos read ${d.ingested||0} new post${d.ingested===1?'':'s'} from this feed.${tail}`,{type:'card',label:'Feed connected',status:'READY',detail:corpus?corpus.name:'My Knowledge',val:url,corpus_id:cid});
    }catch(e){wrap.remove();reportErr('Add feed failed: '+e.message)}
    if(input&&!onComplete)input.focus();
  };
}

/* ══════ CHATS PAGE ══════ */
function renderChats(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="mc-wrap mc-wrap--chats">
    ${workspaceEyebrowHTML()}<div class="mc-top"><h1 class="mc-title">Chats</h1></div>
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
      location.hash=`#/main?session=${row.dataset.id}`;
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
  // Graph mode lets the canvas span the full content area (matches the
  // /#/explore feel) while the header chrome stays centered at the same
  // 880px column the list view uses.
  const wrapMod=_mcView==='graph'?' mc-wrap--graph':'';
  ct.innerHTML=`<div class="mc-wrap${wrapMod}">
    ${workspaceEyebrowHTML()}
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
  document.getElementById('mc-new-btn').onclick=()=>{_termCtx={};const wasMain=location.hash==='#/main';location.hash='#/main';if(wasMain)renderHome()};
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
  if(!_corpora.length){
    // Workspace-aware empty state — invites rather than informs.
    if(_workspace.kind==='org'){
      const o=_orgs.find(o=>o.id===_workspace.org_id);
      const orgName=o?o.name:'this workspace';
      el.innerHTML=`<div class="mc-empty mc-empty--team">
        <h2 class="mc-empty-h">Your team's brain is just starting.</h2>
        <p class="mc-empty-p">Create the first knowledge base — anyone on ${esc(orgName)} can add to it as you work. Capture from Slack threads, customer email, or a meeting transcript; or start from a note or upload.</p>
        <div class="mc-empty-actions">
          <button class="mc-empty-cta mc-empty-cta--primary" id="mc-empty-create">Create first corpus →</button>
          <a class="mc-empty-cta" href="#/connectors">Browse capture sources</a>
        </div>
      </div>`;
      const create=document.getElementById('mc-empty-create');
      // The CTA's intent is to spin up a new KB — drop the user into the
      // composer in Create mode (not Enrich), so the placeholder + Send
      // behavior match what they came here to do.
      if(create)create.onclick=()=>{
        _termCtx={};
        _composerMode='create';
        const wasMain=location.hash==='#/main';
        location.hash='#/main';
        if(wasMain)renderHome();
      };
      return;
    }
    el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet. Click <strong>+ New</strong> to add your knowledge.</div>';
    return;
  }
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

async function renderMCGraph(){
  // Personal Corpora page: pass scope=mine so the Network toggle shows the
  // same set as the List toggle (the caller's own corpora). Without it the
  // endpoint defaults to the full Noosphere (every user + remote nodes),
  // which is what /#/explore wants but creates a confusing mismatch here.
  const el=document.getElementById('mc-content');el.innerHTML='';el.className='mc-graph';
  let nodes=_corpora;
  try{const r=await fetch(`${API}/corpora/network?scope=mine`);if(r.ok){const d=await r.json();if(Array.isArray(d.nodes)&&d.nodes.length)nodes=d.nodes}}catch(e){}
  if(!nodes.length){el.innerHTML='<div class="empty" style="margin-top:60px">No corpora yet.</div>';return}
  drawGraphIn(el,nodes);
}

/* ══════ NETWORK ══════ */
async function renderNet(){
  hideRP();const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  ct.innerHTML=`<div class="nv-wrap"><canvas id="nv-cv" class="nv-canvas"></canvas><div class="nv-tt hidden" id="nv-tt"></div></div>`;

  const cv=document.getElementById('nv-cv');if(!cv)return;
  let nodes=_corpora;
  try{const r=await fetch(`${API}/corpora/network`);if(r.ok){const d=await r.json();if(Array.isArray(d.nodes)&&d.nodes.length)nodes=d.nodes}}catch(e){}
  if(!nodes.length){const w=cv.parentElement;const e=document.createElement('div');e.className='empty';e.style.cssText='position:absolute;top:40%;left:50%;transform:translate(-50%,-50%)';e.innerHTML='The Noosphere is empty.<br>Click <strong>+ New</strong> to add knowledge.';w.appendChild(e);return}
  drawGraphIn(cv.parentElement,nodes,cv);
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
  // Draw the global network graph at the top. Explore is the world view —
  // every registered corpus shows as a node regardless of access_level.
  // Falls back to the user's local _corpora if /corpora/network errors.
  const cv=document.getElementById('nv-cv');
  if(cv){
    let nodes=[];
    try{
      const r=await fetch(`${API}/corpora/network`);
      if(r.ok){const d=await r.json();nodes=Array.isArray(d.nodes)?d.nodes:[]}
    }catch(e){}
    if(!nodes.length)nodes=_corpora;
    if(nodes.length)drawGraphIn(cv.parentElement,nodes,cv);
  }
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
    // /corpora is user-scoped in cloud mode (filters by owner_id), which
    // is wrong for a discovery surface — Explore should show every
    // KB on this node, not just the viewer's own. /corpora/network
    // returns the full network — all access levels — with private nodes
    // delivered as locked stubs (id+name+tags only, no content metadata).
    // The card / graph click handlers route to pay / token / detail
    // based on access_level.
    const r=await fetch(`${API}/corpora/network`);
    const data=await r.json();
    const all=Array.isArray(data)?data:(data.nodes||data.corpora||[]);
    if(!all.length){el.innerHTML='<div style="color:var(--muted)">No knowledge bases yet. Be the first — click <strong>+ New</strong>.</div>';return}
    el.innerHTML=all.map(c=>_exploreCard({
      corpus_id:c.id,corpus_name:c.name,description:c.description||'',
      author:c.author||c.author_name||'',tags:c.tags||[],document_count:c.document_count||0,
      access_level:c.access_level||'public',
      pricing:c.pricing||null,checkout_url:c.checkout_url||null,
      source:c.kind==='remote'?'remote':'local',score:1
    })).join('');
  }catch(e){el.innerHTML='<div style="color:var(--err)">Failed to load.</div>'}
}
function _exploreCard(c){
  const tags=(c.tags||[]).slice(0,5).map(t=>`<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:var(--bg-hover);font-size:11px;color:var(--muted)">${esc(t)}</span>`).join(' ');
  const q=c.quality||{};
  const docs=q.document_count||c.document_count||0;
  const words=q.word_count||0;
  const al=c.access_level||'public';
  const badge=al==='paid'?'<span style="color:var(--accent);font-size:11px;font-weight:600">PAID</span>':al==='token'?'<span style="color:#b5721a;font-size:11px;font-weight:600">TOKEN</span>':al==='private'?'<span style="color:var(--muted);font-size:11px">PRIVATE</span>':'';
  const src=c.source==='remote'?`<span style="font-size:11px;color:var(--muted)">remote</span>`:'';
  // Click is unified through window._handleCorpusClick — it routes to
  // detail / token modal / pay modal / private toast based on access_level.
  // The card payload is JSON-encoded into the onclick attribute; single
  // quotes in the JSON (e.g. apostrophes in a corpus name) are HTML-encoded
  // so the surrounding single-quoted attribute parses cleanly.
  const _payload=JSON.stringify({id:c.corpus_id,name:c.corpus_name,access_level:al,kind:c.source==='remote'?'remote':'local',pricing:c.pricing||null,checkout_url:c.checkout_url||null,node_endpoint:c.node_endpoint||'',api_endpoint:c.api_endpoint||''}).replace(/'/g,'&#39;');
  return `<div class="explore-card" onclick='window._handleCorpusClick(${_payload})' style="padding:16px 20px;border-radius:10px;border:1px solid var(--border);background:var(--bg-card);cursor:pointer;transition:border-color .15s" onmouseenter="this.style.borderColor='var(--accent)'" onmouseleave="this.style.borderColor='var(--border)'">
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

/* ══════ CORPUS CLICK ROUTER ══════
   Single entry point for "user clicked a corpus node/card". Routes by
   access_level so the same UX shows up whether the click came from the
   explore graph, the explore card list, or anywhere else that lands on a
   corpus reference. Mirrors the agent x402 flow on the human side:
     public  → navigate to detail
     token   → prompt for access token, store it, navigate
     paid    → show price + Pay-with-card (Stripe Checkout)
     private → toast (no detail navigation; node is visible, content isn't)
   Remote (federated) nodes get a brief origin toast since /corpus/:id
   isn't a local route for them. */

const _CORPUS_TOKEN_PREFIX='nph-corpus-token-';
function _getCorpusToken(corpusId){
  try{return sessionStorage.getItem(_CORPUS_TOKEN_PREFIX+corpusId)||''}catch(e){return ''}
}
function _setCorpusToken(corpusId,token){
  try{sessionStorage.setItem(_CORPUS_TOKEN_PREFIX+corpusId,token)}catch(e){}
}

window._handleCorpusClick=function(c){
  const al=(c&&c.access_level)||'public';
  if(c&&c.kind==='remote'){
    const origin=c.node_endpoint||'remote noosphere';
    toast(`${c.name} · from ${origin}`,'success');
    return;
  }
  // Owner bypass — corpora the viewer owns (in their workspace) always
  // open directly. Server-side _is_owner_request allows it; mirror the
  // same logic client-side so the gate UI doesn't fire on your own
  // private/paid/token corpora when seen from the Corpora menu's Network
  // view, the corpus-detail mini-network, or the global Explore page.
  const isOwn=Array.isArray(_corpora)&&_corpora.some(x=>x.id===c.id);
  if(isOwn){location.hash='#/corpus/'+c.id;return}
  if(al==='private'){
    toast(`${c.name} is private — owner access only`,'error');
    return;
  }
  if(al==='token'){_promptCorpusToken(c);return}
  if(al==='paid'){_payToAccessCorpus(c);return}
  location.hash='#/corpus/'+c.id;
};

function _promptCorpusToken(c){
  const existing=document.getElementById('corpus-access-overlay');
  if(existing)existing.remove();
  const ov=document.createElement('div');
  ov.id='corpus-access-overlay';
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
  ov.innerHTML=`<div style="background:var(--bg);border:1px solid var(--brd);border-radius:12px;padding:24px;max-width:420px;width:90%;color:var(--tx)">
    <div style="font-size:18px;font-weight:600;margin-bottom:6px">${esc(c.name)}</div>
    <div style="font-size:13px;color:var(--muted);margin-bottom:16px">This corpus requires an access token. Paste the token you received from the owner.</div>
    <input id="corpus-token-input" type="password" autocomplete="off" placeholder="Access token" style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--brd);background:var(--bg2);color:var(--tx);font-size:14px;margin-bottom:12px;box-sizing:border-box">
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button id="corpus-token-cancel" style="padding:8px 14px;border-radius:8px;border:1px solid var(--brd);background:transparent;color:var(--tx);cursor:pointer;font-size:13px">Cancel</button>
      <button id="corpus-token-ok" style="padding:8px 14px;border-radius:8px;border:none;background:var(--btnBg);color:var(--btnC);cursor:pointer;font-size:13px;font-weight:600">Open</button>
    </div>
  </div>`;
  document.body.appendChild(ov);
  const input=ov.querySelector('#corpus-token-input');
  input.focus();
  const close=()=>ov.remove();
  ov.addEventListener('click',e=>{if(e.target===ov)close()});
  ov.querySelector('#corpus-token-cancel').onclick=close;
  const submit=()=>{
    const t=(input.value||'').trim();
    if(!t){input.focus();return}
    _setCorpusToken(c.id,t);
    close();
    location.hash='#/corpus/'+c.id;
  };
  ov.querySelector('#corpus-token-ok').onclick=submit;
  input.onkeydown=e=>{if(e.key==='Enter')submit();if(e.key==='Escape')close()};
}

async function _payToAccessCorpus(c){
  const cents=c&&c.pricing&&typeof c.pricing.amount_cents==='number'?c.pricing.amount_cents:0;
  const priceLabel=cents>0?`$${(cents/100).toFixed(2)}${c.pricing.type==='per_query'?' per query':''}`:'See pricing';
  const existing=document.getElementById('corpus-access-overlay');
  if(existing)existing.remove();
  const ov=document.createElement('div');
  ov.id='corpus-access-overlay';
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
  ov.innerHTML=`<div style="background:var(--bg);border:1px solid var(--brd);border-radius:12px;padding:24px;max-width:420px;width:90%;color:var(--tx)">
    <div style="font-size:18px;font-weight:600;margin-bottom:6px">${esc(c.name)}</div>
    <div style="font-size:13px;color:var(--muted);margin-bottom:6px">Paid corpus</div>
    <div style="font-size:24px;font-weight:600;margin-bottom:16px">${priceLabel}</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:16px;line-height:1.5">Agents can also pay programmatically via x402 (USDC on Base, Stripe Agent Toolkit). The same access is granted regardless of rail.</div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button id="pay-cancel" style="padding:8px 14px;border-radius:8px;border:1px solid var(--brd);background:transparent;color:var(--tx);cursor:pointer;font-size:13px">Cancel</button>
      <button id="pay-go" style="padding:8px 14px;border-radius:8px;border:none;background:var(--btnBg);color:var(--btnC);cursor:pointer;font-size:13px;font-weight:600">Pay with card</button>
    </div>
  </div>`;
  document.body.appendChild(ov);
  const close=()=>ov.remove();
  ov.addEventListener('click',e=>{if(e.target===ov)close()});
  ov.querySelector('#pay-cancel').onclick=close;
  ov.querySelector('#pay-go').onclick=async()=>{
    const btn=ov.querySelector('#pay-go');btn.disabled=true;btn.textContent='Loading...';
    try{
      const successUrl=location.origin+'/#/corpus/'+c.id;
      const cancelUrl=location.origin+location.hash;
      const r=await fetch(`${API}/corpora/${c.id}/checkout`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({success_url:successUrl,cancel_url:cancelUrl})});
      const d=await r.json();
      if(r.ok&&d.checkout_url){window.location.href=d.checkout_url}
      else{toast(d.detail||'Could not start checkout','error');btn.disabled=false;btn.textContent='Pay with card'}
    }catch(e){toast('Checkout failed','error');btn.disabled=false;btn.textContent='Pay with card'}
  };
}

/* ══════ SHARED GRAPH DRAWING ══════ */
// Node color: name-hashed PAL palette (same as the LP/Feynman background)
// so the discovery graph reads as a thinking-network of distinct minds,
// not a uniform ACL-coded chart. Private stays muted gray — the lock
// signal — and remote nodes stay dim. paid/token still convey their
// state via the card badge + hover tooltip; the graph itself is for
// "how do these knowledge bases relate", not for status accounting.
const _ACL_COLOR={public:'#4a90e2',paid:'#22a06b',token:'#b5721a',private:'#94a3b8'};
function _aclNodeColor(level){return _ACL_COLOR[level||'public']||_ACL_COLOR.public}
function _nodeColor(c){
  if((c.access_level||'public')==='private')return _ACL_COLOR.private;
  return cC(c.name||c.id||'?');
}

async function drawGraphIn(container,corpora,existingCanvas){
  if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}
  const _activity={};
  // Server links (semantic + tag) come from /corpora/network. We fetch in
  // parallel with the per-corpus analytics calls so the graph isn't
  // serially blocked. Either fetch can fail (offline / endpoint error)
  // and we degrade gracefully — analytics → 0 queries, links → tag-only
  // computed client-side.
  const visibleIds=new Set(corpora.map(c=>c.id));
  const serverLinksP=fetch(`${API}/corpora/network`).then(r=>r.ok?r.json():null).catch(()=>null);
  await Promise.all(corpora.map(async c=>{try{const r=await fetch(`${API}/corpora/${c.id}/analytics?limit=1`);if(r.ok){const a=await r.json();_activity[c.id]=a.total_queries||0}else{_activity[c.id]=0}}catch(e){_activity[c.id]=0}}));
  const ns=corpora.map(c=>{const tg=Array.isArray(c.tags)?c.tags:[];const tk=[];tg.forEach(t=>tk.push(...t.toLowerCase().split(/[\s,]+/).filter(Boolean)));return{...c,color:_nodeColor(c),ini:(c.name||'?').split(/\s+/).slice(0,2).map(w=>w[0]).join(''),tk,queries:_activity[c.id]||0}});

  // Build links: prefer server-computed (semantic + tag layered), fall
  // back to client-side tag overlap if /corpora/network is unreachable.
  // Filter to edges whose endpoints are both visible — the server may
  // know about corpora the current view is scoped against (e.g. home
  // shows only the user's, explore shows all public). Without this filter
  // the force layout would have phantom anchors pulling at nothing.
  let lk=[];
  const serverData=await serverLinksP;
  if(serverData && Array.isArray(serverData.links)){
    for(const e of serverData.links){
      const sid=typeof e.source==='string'?e.source:e.source?.id;
      const tid=typeof e.target==='string'?e.target:e.target?.id;
      if(!sid||!tid)continue;
      if(!visibleIds.has(sid)||!visibleIds.has(tid))continue;
      // Map the server's strength scale onto the existing renderer's
      // `s` magnitude. Tag edges already use integer shared-tag count
      // (passes through). Semantic edges use cosine in [floor..1.0]
      // — rescale to a comparable visual range so a 0.6 cosine doesn't
      // render thinner than a 1-tag overlap. See _refreshComposerPlaceholder
      // for the analogous sizing tuning on text labels.
      const baseS=e.strength==null?1:Number(e.strength);
      const s=e.kind==='semantic'?Math.max(0.5,(baseS-0.4)*5):baseS;
      lk.push({source:sid,target:tid,s,kind:e.kind||'tag'});
    }
  }
  if(!lk.length){
    // Fallback: tag-only client-side computation. Keeps the graph
    // working when the network endpoint hiccups or the embedding
    // pipeline isn't configured (self-hosted no-API-key setups).
    for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){const s=new Set(ns[i].tk);const sh=[...new Set(ns[j].tk)].filter(t=>s.has(t));if(sh.length)lk.push({source:ns[i].id,target:ns[j].id,s:sh.length,kind:'tag'})}
  }
  // Adjacency for hover-dim + orphan detection. Each node is its own neighbor
  // (so hovering a node keeps it lit along with its 1-hop friends).
  const nbr={};ns.forEach(n=>{nbr[n.id]=new Set([n.id])});
  lk.forEach(l=>{nbr[l.source].add(l.target);nbr[l.target].add(l.source)});

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

  // Viewport pan+zoom — Obsidian/Feynman style. The simulation continues
  // to operate in "world space" (forces, node positions in raw px) while
  // the canvas applies a translate+scale transform at draw time, so the
  // physics doesn't have to know anything about the camera.
  //   view.k       — current zoom scale (1 = identity)
  //   view.tx/ty   — translation in screen pixels, applied AFTER scale
  //   ZOOM_MIN/MAX — clamps so a wheel-mash can't trash the layout
  // Auto-fit re-runs every tick while the simulation is still settling,
  // so the camera tracks the nodes as they spread. Stops as soon as the
  // user pans/zooms/drags (their framing wins) or alpha drops below the
  // settle threshold. Previously a single 600 ms fit captured the layout
  // mid-spread and nodes drifted off-screen by the time motion stopped.
  // Double-click on empty space re-runs autoFit on demand.
  const view={tx:0,ty:0,k:1};
  const ZOOM_MIN=0.25,ZOOM_MAX=4;
  let _userFramed=false;
  const toWorld=(sx,sy)=>[(sx-view.tx)/view.k,(sy-view.ty)/view.k];
  function autoFit(){
    if(!ns.length)return;
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    for(const n of ns){
      if(n.x==null||n.y==null)continue;
      if(n.x<minX)minX=n.x;if(n.x>maxX)maxX=n.x;
      if(n.y<minY)minY=n.y;if(n.y>maxY)maxY=n.y;
    }
    if(!isFinite(minX))return;
    const PAD=BR*3;  // give labels room
    minX-=PAD;maxX+=PAD;minY-=PAD;maxY+=PAD;
    const bw=Math.max(1,maxX-minX),bh=Math.max(1,maxY-minY);
    // Cap auto-zoom at 2× — past that a 2-node graph would look
    // ridiculous (giant orbs filling the screen).
    const k=Math.min(W/bw,H/bh,2);
    view.k=Math.max(ZOOM_MIN,Math.min(ZOOM_MAX,k));
    view.tx=W/2-((minX+maxX)/2)*view.k;
    view.ty=H/2-((minY+maxY)/2)*view.k;
  }
  sim.on('tick',()=>{if(!_userFramed&&sim.alpha()>0.02)autoFit()});

  let drag=null,hov=null,mp=null,pan=null,panMoved=0;
  const tt=container.querySelector('.nv-tt')||document.getElementById('nv-tt');
  // Hit-test in screen space — keeps click targets the same physical
  // size at every zoom level. World-space hit-test would shrink with
  // the nodes when zoomed out, leaving 4-pixel click targets.
  function getN_screen(sx,sy){
    for(const n of ns){
      const nsx=n.x*view.k+view.tx,nsy=n.y*view.k+view.ty;
      if(Math.hypot(nsx-sx,nsy-sy)<BR+6)return n;
    }
    return null;
  }
  cv.onmousedown=e=>{
    const r=cv.getBoundingClientRect();
    const sx=e.clientX-r.left,sy=e.clientY-r.top;
    drag=getN_screen(sx,sy);
    if(drag){drag.fx=drag.x;drag.fy=drag.y;sim.alphaTarget(.3).restart();_userFramed=true;return}
    // Empty space → start panning. Capture current view offsets so the
    // delta math in mousemove stays absolute (prevents jitter from
    // accumulating float error).
    pan={sx,sy,tx:view.tx,ty:view.ty};
    panMoved=0;
    cv.style.cursor='grabbing';
    _userFramed=true;
  };
  cv.onmousemove=e=>{
    const r=cv.getBoundingClientRect();
    const sx=e.clientX-r.left,sy=e.clientY-r.top;
    if(pan){
      const dx=sx-pan.sx,dy=sy-pan.sy;
      view.tx=pan.tx+dx;view.ty=pan.ty+dy;
      panMoved=Math.max(panMoved,Math.abs(dx)+Math.abs(dy));
      return;
    }
    const [wx,wy]=toWorld(sx,sy);
    mp=[wx,wy];  // world coords — magnet effect uses n.x/n.y which are world too
    if(drag){drag.fx=wx;drag.fy=wy;cv.style.cursor='grabbing';return}
    hov=getN_screen(sx,sy);
    cv.style.cursor=hov?'pointer':'grab';
    if(hov&&tt){
      // Tooltip in screen coords (CSS positions, unaffected by zoom).
      const ext=hov._isOwn===false?' · external':'';
      const al=hov.access_level||'public';
      const cta=al==='private'?'Locked':al==='paid'?'Click to pay':al==='token'?'Click for access':'Click to open';
      const meta=al==='private'?al:`${hov.document_count||0} documents · ${al}`;
      tt.innerHTML=`<div class="tt-n">${esc(hov.name)}</div><div class="tt-m">${meta}${ext} · ${cta}</div>`;
      tt.classList.remove('hidden');
      tt.style.left=(sx+12)+'px';
      tt.style.top=(sy-8)+'px';
    }else if(tt){tt.classList.add('hidden')}
  };
  cv.onmouseup=()=>{
    if(drag){drag.fx=null;drag.fy=null;sim.alphaTarget(0);drag=null}
    if(pan){pan=null;cv.style.cursor=hov?'pointer':'grab'}
  };
  // Suppress click navigation if the gesture was actually a pan — without
  // this guard, ending a pan on top of a node would teleport the user
  // into that corpus by accident.
  cv.onclick=()=>{
    if(drag||!hov||panMoved>=5)return;
    window._handleCorpusClick({
      id:hov.id,name:hov.name,access_level:hov.access_level||'public',
      kind:hov.kind||'local',pricing:hov.pricing||null,
      checkout_url:hov.checkout_url||null,
      node_endpoint:hov.node_endpoint||'',
    });
  };
  cv.ondblclick=e=>{e.preventDefault();_userFramed=false;autoFit()};
  cv.onmouseleave=()=>{hov=null;mp=null;if(tt)tt.classList.add('hidden');if(drag){drag.fx=null;drag.fy=null;sim.alphaTarget(0);drag=null}if(pan)pan=null};
  // Wheel = zoom anchored at cursor. The "exp(-deltaY * factor)" curve
  // gives smooth perceived speed across mouse wheels (large discrete
  // deltaY) and trackpad pinches (small continuous deltaY with ctrlKey).
  // After updating k, we adjust tx/ty so the world point under the
  // cursor stays under the cursor — same trick d3-zoom uses.
  cv.onwheel=e=>{
    e.preventDefault();
    const r=cv.getBoundingClientRect();
    const sx=e.clientX-r.left,sy=e.clientY-r.top;
    const [wx,wy]=toWorld(sx,sy);
    const factor=Math.exp(-e.deltaY*0.0015);
    const newK=Math.max(ZOOM_MIN,Math.min(ZOOM_MAX,view.k*factor));
    if(newK===view.k)return;
    view.tx=sx-wx*newK;view.ty=sy-wy*newK;view.k=newK;
    _userFramed=true;
  };

  function draw(){const now=performance.now();cx.save();cx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--cvBg').trim()||'#f5f5f7';cx.fillRect(0,0,W,H);
    // Apply the camera transform AFTER the dpi scale (set once outside the
    // loop). Everything below this point draws in world coordinates and
    // gets pan/zoom for free.
    cx.translate(view.tx,view.ty);cx.scale(view.k,view.k);
    const activeSet=hov?nbr[hov.id]:null; // hover-dim: keep hovered + neighbors at full opacity
    const dk=isDark();
    // Edges — uniform solid line, alpha scales with shared-tag count or
    // semantic strength. Matches the landing-page background network so
    // the discovery graph reads as the same visual fabric: no dashed
    // semantic-vs-tag distinction, just one quiet relational thread.
    for(const l of lk){const s=l.source,t=l.target;const sid=typeof s==='object'?s.id:s;const tid=typeof t==='object'?t.id:t;const touches=!activeSet||(activeSet.has(sid)&&activeSet.has(tid));const dim=activeSet&&!touches?.15:1;cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);cx.strokeStyle=dk?`rgba(170,185,210,${(.12+Math.min(l.s,6)*.08)*dim})`:`rgba(140,155,180,${(.12+Math.min(l.s,6)*.08)*dim})`;cx.lineWidth=.6+Math.min(l.s,6)*.4;cx.stroke()}
    for(const p of pts){p.t+=p.sp;if(p.t>1)p.t-=1;const s=p.l.source,t=p.l.target;const sid=typeof s==='object'?s.id:s;const tid=typeof t==='object'?t.id:t;const dim=activeSet&&!(activeSet.has(sid)&&activeSet.has(tid))?.15:1;cx.beginPath();cx.arc(s.x+(t.x-s.x)*p.t,s.y+(t.y-s.y)*p.t,p.sz,0,Math.PI*2);cx.fillStyle=dk?`rgba(200,220,255,${p.op*.45*dim})`:`rgba(130,150,200,${p.op*.45*dim})`;cx.fill()}
    for(const n of ns){const h=hov===n||drag===n;const isCenter=n._isCenter===true;const dim=activeSet&&!activeSet.has(n.id)?.25:1;let r=BR;if(mp&&!drag){const d=Math.hypot(n.x-mp[0],n.y-mp[1]);r=d<200?BR*(1+(1-d/200)*.5):BR*.85}if(h)r=Math.max(r,BR*1.4);if(isCenter)r=Math.max(r,BR*1.15);const rr=r*(1+Math.sin(now*.002+n.name.length)*.03);const[cr,cg,cb]=hR(n.color);
      const g=cx.createRadialGradient(n.x,n.y,rr*.3,n.x,n.y,rr*2);g.addColorStop(0,`rgba(${cr},${cg},${cb},${(h?.15:.05)*dim})`);g.addColorStop(1,'rgba(255,255,255,0)');cx.beginPath();cx.arc(n.x,n.y,rr*2,0,Math.PI*2);cx.fillStyle=g;cx.fill();
      if(h){cx.beginPath();cx.arc(n.x,n.y,rr+3,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},${.5*dim})`;cx.lineWidth=2;cx.stroke()}
      // Node ball — solid fill in access-level color, uniform white stroke.
      // Same shape as the LP background nodes; access_level palette stays
      // as the only encoded variation.
      cx.beginPath();cx.arc(n.x,n.y,rr,0,Math.PI*2);
      cx.fillStyle=`rgba(${cr},${cg},${cb},${dim})`;cx.fill();
      cx.strokeStyle=`rgba(255,255,255,${.25*dim})`;cx.lineWidth=1.5;cx.stroke();
      if(isCenter){cx.beginPath();cx.arc(n.x,n.y,rr+6,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},${.4*dim})`;cx.lineWidth=2;cx.stroke()}
      if(n.queries>0){const pulseR=rr+4+Math.sin(now*.003+n.queries)*(3+Math.min(n.queries,20)*.3);const pulseOp=.15+Math.sin(now*.004+n.name.length)*.1;cx.beginPath();cx.arc(n.x,n.y,pulseR,0,Math.PI*2);cx.strokeStyle=`rgba(${cr},${cg},${cb},${pulseOp*dim})`;cx.lineWidth=2;cx.stroke()}
      cx.fillStyle=`rgba(255,255,255,${.95*dim})`;cx.font=`700 ${rr*.55}px Inter,sans-serif`;cx.textAlign='center';cx.textBaseline='middle';cx.fillText(n.ini,n.x,n.y);
      cx.fillStyle=dk?`rgba(245,245,247,${(h?.95:.7)*dim})`:`rgba(30,35,50,${(h?.9:.6)*dim})`;cx.font=`600 ${h?12:11}px 'Libre Baskerville',Georgia,serif`;cx.fillText(n.name,n.x,n.y+rr+14);
      cx.fillStyle=dk?`rgba(200,200,210,${.4*dim})`:`rgba(100,110,130,${.4*dim})`;cx.font='400 9px Inter,sans-serif';
      // Private nodes ship without document_count (redacted server-side);
      // show the access state instead so the label isn't `undefined docs`.
      const subLabel=n.access_level==='private'?'private':(n.queries>0?n.queries+' queries':((n.document_count||0)+' docs'));
      cx.fillText(subLabel,n.x,n.y+rr+26)}
    cx.restore();_gAnim=requestAnimationFrame(draw)}
  sim.on('tick',()=>{});_gAnim=requestAnimationFrame(draw);
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
     'avail' — at least one method is wired
     'soon'  — every method is still coming, grayed out
   Pro-gating: every external connector is Pro (matches Notion Business),
   except Obsidian which is free (no account tier gating on local files).

   Each entry has a `methods[]` array grouped by category:
     group='archive' — one-shot import (ZIP, export file)
     group='live'    — persistent sync (CLI, OAuth, plugin)
   Method `status`: 'ready' | 'beta' | 'soon'.
   Method `action`: what to do on click — one of 'upload_archive',
     'copy_cli', 'open_oauth' (not wired), 'show_instructions'. */
const _SOURCE_CONNECTORS=[
  {kind:'obsidian',name:'Obsidian',desc:'Your local markdown vault — upload or keep live-synced.',mono:'O',bg:'#6c4fd5',fg:'#ffffff',status:'avail',pro:false,cta:'Open',
   methods:[
     {group:'archive',id:'zip',name:'Upload vault (ZIP)',status:'ready',action:'upload_archive',archiveKind:'obsidian',
      desc:'One-shot. Zip your vault folder and upload it. Wikilinks, tags, and folder structure are preserved. Vault and Noosphere diverge after this.'},
     {group:'archive',id:'path',name:'Connect local vault',status:'ready',action:'connect_local_path',
      desc:'Point Noosphere at your vault on disk — works when Noosphere is self-hosted on the same machine as Obsidian. Creates a corpus, imports the vault, and returns the corpus ID you can paste into the plugin.'},
     {group:'live',id:'cli',name:'CLI two-way sync',status:'beta',action:'copy_cli',
      cli:'noosphere sync ~/your-vault --corpus {CORPUS} --obsidian --watch',
      desc:'Watches your vault on disk. Every edit in Obsidian flows into Noosphere. Karpathy-style setup: files stay local, Noosphere keeps your index fresh.'},
     {group:'live',id:'plugin',name:'Obsidian plugin',status:'beta',action:'show_plugin_docs',
      desc:'One-click sync from inside Obsidian — ribbon icon, watch mode, settings UI. Self-hosted today; build from the repo\'s plugin/ folder.'},
   ]},
  {kind:'notion',name:'Notion',desc:'Your Notion workspace — one-shot export today, live sync coming.',mono:'N',bg:'#000000',fg:'#ffffff',status:'avail',pro:false,cta:'Open',
   methods:[
     {group:'archive',id:'zip',name:'Upload export (ZIP)',status:'ready',action:'upload_archive',archiveKind:'notion',
      desc:'Settings → Data export (Markdown & CSV). Pages land as user_original.'},
     {group:'live',id:'oauth',name:'OAuth live sync',status:'soon',action:'show_instructions',pro:true,
      desc:'Authorize Noosphere to read your pages and databases, and keep them in sync.'},
   ]},
  {kind:'twitter',name:'Twitter / X',desc:'Your Twitter/X data export.',mono:'𝕏',bg:'#000000',fg:'#ffffff',status:'avail',pro:false,cta:'Open',
   methods:[
     {group:'archive',id:'zip',name:'Upload data export (ZIP)',status:'ready',action:'upload_archive',archiveKind:'twitter',
      desc:'ZIP from twitter.com/settings/download_your_data. Tweets become documents.'},
   ]},
  {kind:'readwise',name:'Readwise',desc:'Highlights from books, articles, podcasts, and Kindle.',mono:'R',bg:'#e8a33d',fg:'#1a1a1a',status:'soon',pro:false,
   methods:[
     {group:'archive',id:'export',name:'Import highlights export',status:'soon',action:'show_instructions',
      desc:'Readwise → Export all highlights (Markdown / CSV). Each highlight lands as user_original, grouped by source. On the roadmap.'},
   ]},
  {kind:'evernote',name:'Evernote',desc:'Your notebooks and notes.',mono:'E',bg:'#00a82d',fg:'#ffffff',status:'soon',pro:false,
   methods:[
     {group:'archive',id:'enex',name:'Import .enex export',status:'soon',action:'show_instructions',
      desc:'Evernote → export notebooks as .enex. Notes and their attachments become documents. On the roadmap.'},
   ]},
  {kind:'apple_notes',name:'Apple Notes',desc:'Notes from the Apple Notes app.',mono:'AN',bg:'#f5b800',fg:'#1a1a1a',status:'soon',pro:false,
   methods:[
     {group:'archive',id:'export',name:'Import exported notes',status:'soon',action:'show_instructions',
      desc:'Export from Apple Notes and upload the folder. Notes become documents, folders become tags. On the roadmap.'},
   ]},
  {kind:'gdrive',name:'Google Drive',desc:'Docs, Sheets, and folders',mono:'D',bg:'#1a73e8',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'oauth',name:'OAuth live sync',status:'soon',action:'show_instructions',pro:true,desc:'Authorize Drive folder access; Noosphere indexes Docs and Sheets live.'},
   ]},
  {kind:'github',name:'GitHub',desc:'READMEs, issues, discussions',mono:'Gh',bg:'#1f2328',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'oauth',name:'OAuth live sync',status:'soon',action:'show_instructions',pro:true,desc:'Connect repos; pull READMEs, issues, and discussions.'},
   ]},
  {kind:'gmail',name:'Gmail',desc:'Threads filtered by label',mono:'M',bg:'#ea4335',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'oauth',name:'OAuth live sync',status:'soon',action:'show_instructions',pro:true,desc:'Authorize Gmail; pull threads matching labels you choose.'},
   ]},
  {kind:'slack',name:'Slack',desc:'Channels and direct messages',mono:'#',bg:'#4a154b',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'oauth',name:'OAuth live sync',status:'soon',action:'show_instructions',pro:true,desc:'Install the Noosphere app in your workspace; select channels to index.'},
   ]},
  {kind:'email_inbox',name:'Email forwarding',desc:'Forward emails to a unique inbox address',mono:'@',bg:'#6e6e73',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'forward',name:'Email forwarding address',status:'soon',action:'show_instructions',pro:true,desc:'Get a unique address per corpus; forward emails to ingest their content.'},
   ]},
  {kind:'rss_auto',name:'RSS (auto-sync)',desc:'Scheduled feed polling',mono:'≫',bg:'#f26522',fg:'#ffffff',status:'soon',pro:true,
   methods:[
     {group:'live',id:'feed',name:'Auto-polling feed',status:'soon',action:'show_instructions',pro:true,desc:'Register an RSS/Atom URL and Noosphere pulls new items on a schedule. Today only manual adds (via + → Add RSS feed) are wired.'},
   ]},
];

/* ══════ PER-APP PANEL ══════
   One unified modal per application. Takes a connector `kind` and renders
   every available ingest method for that app, grouped into:
     - Import archive — one-shot ZIP / export upload
     - Live connection — persistent sync (CLI, OAuth, plugin)
   Each method has a status badge (Ready / Beta / Soon) and a single action
   button. Clicking lands you on the actual flow (upload panel, CLI
   copy-to-clipboard, instructions). This is the single canonical surface
   for any app click, regardless of where the click originated (chint logos,
   source picker, Connectors page). */
function _closeAppPanel(){const p=document.getElementById('app-panel-overlay');if(p)p.remove()}
function showAppPanel(kind,ctx){
  ctx=ctx||{};
  const c=_SOURCE_CONNECTORS.find(x=>x.kind===kind);
  if(!c){toast(`Unknown app: ${kind}`,'error');return}
  _closeAppPanel();
  const STATUS_BADGES={
    ready:'<span class="app-m-badge app-m-badge-ready">Ready</span>',
    beta:'<span class="app-m-badge app-m-badge-beta">Beta</span>',
    soon:'<span class="app-m-badge app-m-badge-soon">Soon</span>',
  };
  const methods=c.methods||[];
  const archiveMethods=methods.filter(m=>m.group==='archive');
  const liveMethods=methods.filter(m=>m.group==='live');
  const renderMethod=m=>{
    const badge=STATUS_BADGES[m.status]||'';
    const pro=m.pro?'<span class="app-m-badge app-m-badge-pro">Pro</span>':'';
    const disabled=m.status==='soon'?'disabled':'';
    const actionLabel=m.status==='ready'?'Use':(m.status==='beta'?'Try':'Preview');
    return `<button class="app-m-row" data-mid="${m.id}" ${disabled}>
      <span class="app-m-main">
        <span class="app-m-top"><span class="app-m-name">${esc(m.name)}</span>${badge}${pro}</span>
        <span class="app-m-desc">${esc(m.desc||'')}</span>
      </span>
      <span class="app-m-action">${actionLabel}</span>
    </button>`;
  };
  const archiveHTML=archiveMethods.length
    ? `<div class="app-section-hd">Import archive</div><div class="app-section-body">${archiveMethods.map(renderMethod).join('')}</div>`
    : '';
  const liveHTML=liveMethods.length
    ? `<div class="app-section-hd">Live connection</div><div class="app-section-body">${liveMethods.map(renderMethod).join('')}</div>`
    : '';
  const ov=document.createElement('div');
  ov.id='app-panel-overlay';ov.className='srcs-pick-overlay app-panel-overlay';
  ov.innerHTML=`<div class="srcs-pick app-panel" style="position:relative">
    <button class="srcs-pick-close" id="app-panel-close" title="Close">×</button>
    <div class="app-panel-hd">
      <span class="app-panel-ico" style="background:${c.bg};color:${c.fg}">${c.mono}</span>
      <div class="app-panel-hd-text">
        <h2 class="srcs-pick-ttl">${esc(c.name)}</h2>
        <p class="srcs-pick-sub">${esc(c.desc||'')}</p>
      </div>
    </div>
    <div class="app-panel-body">${archiveHTML}${liveHTML}</div>
  </div>`;
  document.body.appendChild(ov);
  document.getElementById('app-panel-close').onclick=_closeAppPanel;
  ov.addEventListener('click',e=>{if(e.target===ov)_closeAppPanel()});
  ov.querySelectorAll('.app-m-row').forEach(btn=>{
    if(btn.disabled)return;
    btn.onclick=()=>{
      const mid=btn.dataset.mid;
      const m=methods.find(x=>x.id===mid);
      if(!m)return;
      if(m.pro&&gateProFeature&&gateProFeature(`${c.name} · ${m.name} is a Pro feature`))return;
      _closeAppPanel();
      _triggerAppMethod(c,m,ctx);
    };
  });
  const esc2=(e)=>{if(e.key==='Escape'){_closeAppPanel();document.removeEventListener('keydown',esc2)}};
  document.addEventListener('keydown',esc2);
}

/* Dispatch a method click to its concrete action. Kept separate so the
   panel rendering stays a pure view. */
function _triggerAppMethod(connector,method,ctx){
  if(method.action==='upload_archive'){
    // Open the focused archive-upload panel, pre-selected to this method's archiveKind.
    _openArchiveUpload(method.archiveKind,ctx);
    return;
  }
  if(method.action==='copy_cli'){
    // Show the command in a modal with a Copy button. More discoverable
    // than a silent clipboard write + toast, and works inside sandboxed
    // preview environments where navigator.clipboard might be blocked —
    // the modal's Copy button has an execCommand fallback, and the
    // command itself is visible/selectable even if copy fails.
    const corpusId=ctx.corpusId||_homeScope||'your-corpus';
    const slug=_corpora.find(c=>c.id===corpusId)?.slug||corpusId;
    const cmd=(method.cli||'').replace('{CORPUS}',slug);
    _showInfoModal({
      title:`${connector.name} · ${method.name}`,
      subtitle:method.desc||'',
      bodyHTML:`<p style="color:var(--tx3);font-size:12px;margin:0 0 10px">Run this in your terminal:</p>`,
      copyText:cmd,
    });
    return;
  }
  if(method.action==='show_instructions'){
    _showInfoModal({
      title:`${connector.name} · ${method.name}`,
      subtitle:'This integration is on the roadmap but not yet wired up.',
      bodyHTML:`<p style="font-size:13px;line-height:1.55">${esc(method.desc||'')}</p>`,
    });
    return;
  }
  if(method.action==='show_plugin_docs'){
    // Inline instructions, tuned for normal Obsidian users (not devs).
    // They expect to download a pre-built release — not `npm install`.
    // The plugin-release.yml workflow publishes the three artifacts to
    // the GitHub Releases page on every `plugin-v*` tag push.
    _showInfoModal({
      title:'Obsidian plugin — install',
      subtitle:'One-click sync from inside Obsidian. Standard Obsidian plugin install — no Node.js needed.',
      bodyHTML:`
        <ol style="padding-left:20px;font-size:13px;line-height:1.6;margin:0 0 10px">
          <li>Open the <a href="https://github.com/steveyeow/noosphere/releases" target="_blank" rel="noopener">Noosphere Releases page</a> — download <code>manifest.json</code>, <code>main.js</code>, <code>styles.css</code> from the latest release.</li>
          <li>Put them in your vault folder:
            <pre style="background:var(--bg2);padding:8px 12px;border-radius:5px;font-size:12px;margin:6px 0;word-break:break-all;white-space:pre-wrap">&lt;your-vault&gt;/.obsidian/plugins/noosphere-sync/</pre>
          </li>
          <li>In Obsidian → <b>Settings → Community plugins</b>
            <div style="font-size:11.5px;color:var(--tx3);margin-top:3px">First time? Click <i>"Turn on community plugins"</i> first — Obsidian's default safety gate.</div>
            → find <b>Noosphere</b> in Installed plugins → enable its toggle.
          </li>
          <li>A <b>Noosphere</b> tab appears in the left sidebar of Settings. Open it →
            <ul style="margin:4px 0 0 4px">
              <li>Fill <b>Server URL</b>: <code>http://localhost:8420</code> (self-hosted) or <code>https://noosphere.wiki</code> (cloud)</li>
              <li>Click <b>Create new</b> next to the Corpus ID field</li>
              <li>Click the Sync ribbon icon (top-left of Obsidian)</li>
            </ul>
          </li>
        </ol>
        <p style="font-size:12px;color:var(--tx3);margin:0">Dev build from source: see <code>plugin/README.md</code>.</p>
      `,
    });
    return;
  }
  if(method.action==='connect_local_path'){
    _openConnectLocalPath(connector,ctx);
    return;
  }
  toast('Unhandled action','error');
}

/* In-page modal helpers — replace native window.prompt / window.alert
   / window.open usage. Native dialogs are (a) inconsistent across
   browsers, (b) blocked inside sandboxed preview environments like
   Claude Preview, and (c) worse UX than a proper dialog we style
   ourselves. One generic dialog renderer handles all three shapes:
     - Input form  (fields[] + Submit)   → _showFormModal
     - Info-only with Copy (CLI snippet) → _showInfoModal (reuses)
     - Install instructions (markdown)   → _showInfoModal with html body */
function _closeModal(){const p=document.getElementById('generic-modal');if(p)p.remove()}
function _showModalShell(innerHTML){
  _closeModal();
  const ov=document.createElement('div');ov.id='generic-modal';ov.className='srcs-pick-overlay';
  ov.innerHTML=`<div class="srcs-pick app-panel" style="position:relative;max-width:520px"><button class="srcs-pick-close" id="generic-modal-close" title="Close">×</button>${innerHTML}</div>`;
  document.body.appendChild(ov);
  document.getElementById('generic-modal-close').onclick=_closeModal;
  ov.addEventListener('click',e=>{if(e.target===ov)_closeModal()});
  const esc=(e)=>{if(e.key==='Escape'){_closeModal();document.removeEventListener('keydown',esc)}};
  document.addEventListener('keydown',esc);
  return ov;
}
/* fields: [{id, label, placeholder?, value?, hint?}]
   onSubmit: (values) => void | Promise<void> (close modal on success) */
function _showFormModal(opts){
  const fieldsHTML=opts.fields.map(f=>`
    <div class="gm-field">
      <label class="gm-label" for="gm-${esc(f.id)}">${esc(f.label)}</label>
      <input type="text" class="gm-input" id="gm-${esc(f.id)}" placeholder="${esc(f.placeholder||'')}" value="${esc(f.value||'')}" />
      ${f.hint?`<div class="gm-hint">${esc(f.hint)}</div>`:''}
    </div>`).join('');
  const ov=_showModalShell(`
    <div class="app-panel-hd"><div class="app-panel-hd-text"><h2 class="srcs-pick-ttl">${esc(opts.title||'')}</h2>${opts.subtitle?`<p class="srcs-pick-sub">${esc(opts.subtitle)}</p>`:''}</div></div>
    <div class="app-panel-body"><form id="gm-form" class="gm-form">${fieldsHTML}<div class="gm-actions"><button type="button" class="btn-sm-ghost" id="gm-cancel">Cancel</button><button type="submit" class="btn-sm">${esc(opts.submitLabel||'Submit')}</button></div></form></div>
  `);
  document.getElementById('gm-cancel').onclick=_closeModal;
  const form=document.getElementById('gm-form');
  form.onsubmit=async(e)=>{
    e.preventDefault();
    const values={};
    for(const f of opts.fields){values[f.id]=(document.getElementById('gm-'+f.id)?.value||'').trim()}
    try{await opts.onSubmit(values)}
    catch(err){toast('Error: '+(err.message||err),'error')}
  };
  // Focus first field for immediate typing
  const first=opts.fields[0];if(first)setTimeout(()=>document.getElementById('gm-'+first.id)?.focus(),30);
  return ov;
}
/* Info-only modal with optional Copy button and freeform HTML body. */
function _showInfoModal(opts){
  const copyHTML=opts.copyText
    ? `<div class="gm-copy-row"><code class="gm-copy-code">${esc(opts.copyText)}</code><button class="btn-sm" id="gm-copy">Copy</button></div>`
    : '';
  const ov=_showModalShell(`
    <div class="app-panel-hd"><div class="app-panel-hd-text"><h2 class="srcs-pick-ttl">${esc(opts.title||'')}</h2>${opts.subtitle?`<p class="srcs-pick-sub">${esc(opts.subtitle)}</p>`:''}</div></div>
    <div class="app-panel-body">${opts.bodyHTML||''}${copyHTML}<div class="gm-actions" style="margin-top:14px"><button type="button" class="btn-sm-ghost" id="gm-close-btn">Close</button></div></div>
  `);
  document.getElementById('gm-close-btn').onclick=_closeModal;
  if(opts.copyText){
    document.getElementById('gm-copy').onclick=async()=>{
      try{
        // Try the modern API first. If the sandbox blocks it, fall back to
        // a hidden-textarea + execCommand('copy') trick which works even
        // when clipboard permissions aren't available.
        if(navigator.clipboard&&navigator.clipboard.writeText){
          await navigator.clipboard.writeText(opts.copyText);
          toast('Copied','success');
          return;
        }
        const ta=document.createElement('textarea');ta.value=opts.copyText;
        ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);
        ta.select();document.execCommand('copy');document.body.removeChild(ta);
        toast('Copied','success');
      }catch(e){toast('Copy failed — select the text manually','error')}
    };
  }
  return ov;
}

/* "Connect local vault" flow for Obsidian — B in the A/B/C one-click
   story. Uses an in-page modal so it works regardless of whether the
   host environment sandboxes native window.prompt. Creates a new
   corpus, runs sync-local against the given path, and navigates to
   the new corpus detail page on success. */
async function _openConnectLocalPath(connector,ctx){
  const defaultName=connector.name+' vault';
  _showFormModal({
    title:`Connect a local ${connector.name} vault`,
    subtitle:`Self-hosted only — Noosphere reads the folder directly from this machine. Cloud Noosphere can't see your local disk; use the Obsidian plugin or CLI for cloud.`,
    submitLabel:'Connect and sync',
    fields:[
      {id:'path',label:'Vault folder path',placeholder:'/Users/you/Documents/my-vault',hint:'Absolute path — the Noosphere server must be able to read this folder.'},
      {id:'name',label:'Corpus name',value:defaultName,hint:'Shown in Noosphere UI and (if non-private) in network discovery.'},
    ],
    onSubmit:async(v)=>{
      if(!v.path){toast('Vault path is required','error');return}
      if(!v.name){toast('Corpus name is required','error');return}
      _closeModal();
      toast(`Creating corpus "${v.name}"…`,'info');
      try{
        const r1=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.name,description:`Synced from ${connector.name} vault at ${v.path}`,access_level:'private'})});
        if(!r1.ok){toast(`Create failed: ${r1.status} ${await r1.text()}`,'error');return}
        const corpus=await r1.json();
        toast(`Syncing vault from ${v.path}…`,'info');
        const r2=await fetch(`${API}/corpora/${corpus.id}/sync-local`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:v.path,format:'obsidian',writeback:true})});
        if(!r2.ok){toast(`Sync failed: ${r2.status} ${await r2.text()}`,'error');return}
        const res=await r2.json();
        await loadC();
        toast(`${corpus.name}: ${res.sync.new} new, ${res.sync.updated} updated. Corpus ready.`,'success');
        location.hash=`#/corpus/${corpus.id}`;
      }catch(e){
        toast(`Connect failed: ${e.message||e}`,'error');
      }
    },
  });
}

/* Open a focused single-archive-kind uploader. No tabs, no radio picker —
   just a file input + Import button scoped to a specific app's archive
   format. Called from the per-app panel's "Upload archive (ZIP)" method. */
function _openArchiveUpload(archiveKind,ctx){
  const go=()=>{
    const input=document.getElementById('term-input');
    const output=document.getElementById('term-output');
    const home=document.getElementById('home');if(home)home.classList.add('home--active');
    if(!input||!output){setTimeout(go,120);return}
    const targetCorpus=ctx&&ctx.corpusId?ctx.corpusId:_homeScope;
    const panelOpts=ctx&&ctx.corpusId?{lockCorpus:true,onComplete:ctx.onComplete}:null;
    showTermArchiveUpload(output,input,targetCorpus,archiveKind,panelOpts);
  };
  if(location.hash!=='#/main'&&location.hash!==''){location.hash='#/main';setTimeout(go,200)}
  else go();
}

/* Focused single-archive uploader. Mirrors showTermUpload's card rendering
   (so the chat stream feedback stays consistent) but the body is one file
   picker labeled with the app name. */
const ARCHIVE_META={
  obsidian:{label:'Obsidian vault',hint:'ZIP your vault folder — wikilinks, tags, and folders are preserved.'},
  notion:{label:'Notion export',hint:'ZIP from Settings → Data export (Markdown & CSV).'},
  twitter:{label:'Twitter / X export',hint:'ZIP from twitter.com/settings/download_your_data.'},
};
function showTermArchiveUpload(output,input,defaultCorpus,archiveKind,opts){
  opts=opts||{};
  const lockCorpus=!!opts.lockCorpus;
  const onComplete=typeof opts.onComplete==='function'?opts.onComplete:null;
  const meta=ARCHIVE_META[archiveKind]||{label:archiveKind,hint:'Upload the archive ZIP.'};
  const wrap=document.createElement('div');wrap.className='term-upload-wrap';
  wrap.innerHTML=`<div class="term-upload-tabs"><div class="term-upload-tab active">${esc(meta.label)}</div></div><div class="term-upload-body"><div class="term-upload-txt-hint">${esc(meta.hint)} Every item lands as your own content.</div><input type="file" id="tu-fi" accept=".zip" class="term-upload-input" /><div class="term-upload-actions"><button class="btn-sm" id="tu-go" disabled>Import archive</button><button class="btn-sm-ghost" id="tu-cancel">Cancel</button></div></div>`;
  if(onComplete){const rp=document.getElementById('rpanel')||document.getElementById('content');rp?rp.appendChild(wrap):output.appendChild(wrap)}
  else output.appendChild(wrap);
  const reportOK=(msg,cardDef)=>{if(onComplete){onComplete();return}addLine(output,'resp',msg);if(cardDef)addLine(output,'card',null,null,cardDef)};
  const reportErr=(msg)=>{if(onComplete)toast(msg,'error');else addLine(output,'resp',msg)};
  const fi=wrap.querySelector('#tu-fi'),goBtn=wrap.querySelector('#tu-go'),cancelBtn=wrap.querySelector('#tu-cancel');
  fi.onchange=()=>{goBtn.disabled=!fi.files.length};
  // Cancel just removes the panel. The home--active collapse added by
  // _openArchiveUpload is cleared automatically by _installHomeActiveWatcher
  // once term-output is empty — no bespoke cleanup needed here, and any
  // future connector that wants a panel gets the same guarantee for free.
  cancelBtn.onclick=()=>{wrap.remove();if(input&&!onComplete)input.focus()};
  async function resolveCorpus(){
    if(lockCorpus)return defaultCorpus;
    if(defaultCorpus)return defaultCorpus;
    if(_corpora.length===1)return _corpora[0].id;
    // Fall back to a quick-create if no corpus chosen on home
    try{
      const nm='My Knowledge';
      const r=await fetch(`${API}/corpora`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm})});
      if(!r.ok)return null;
      const c=await r.json();await loadC();_homeScope=c.id;return c.id;
    }catch(e){return null}
  }
  goBtn.onclick=async()=>{
    if(!fi.files.length)return;
    goBtn.disabled=true;goBtn.textContent='Importing...';cancelBtn.style.display='none';
    const cid=await resolveCorpus();
    if(!cid){wrap.remove();reportErr('No corpus selected.');if(input)input.focus();return}
    const fd=new FormData();fd.append('file',fi.files[0]);
    try{
      const r=await fetch(`${API}/corpora/${cid}/import/${archiveKind}`,{method:'POST',body:fd});
      const d=await r.json().catch(()=>({}));
      wrap.remove();
      if(!r.ok){reportErr('Import failed: '+(d.detail||r.statusText));if(input)input.focus();return}
      ensureIndexed(cid);
      await loadC();
      const corpus=_corpora.find(c=>c.id===cid);
      reportOK(`Imported ${d.imported||0} of ${d.total||0} items${d.skipped?` (${d.skipped} skipped)`:''}.`,{type:'card',label:`${meta.label} imported`,status:'READY',detail:corpus?corpus.name:'My Knowledge',val:`${d.imported||0} items`,corpus_id:cid});
    }catch(e){wrap.remove();reportErr('Import failed: '+e.message)}
    if(input&&!onComplete)input.focus();
  };
}

/* Composer "+" attach menu — Notion pattern. Single unified entry point for
   adding content to a KB: file upload, paste text, import a URL, register
   an RSS feed, see connected sources, or browse apps. */
function _closeAttachPopover(){
  const p=document.getElementById('attach-pop');if(p)p.remove();
  document.querySelectorAll('.composer-attach.active').forEach(b=>b.classList.remove('active'));
}
function showAttachPopover(anchor,output,input,opts){
  // opts = {corpusId, onComplete}. When corpusId is set, the upload/RSS
  // panels are locked to that corpus and _homeScope is ignored — this is
  // how the corpus page reuses the home composer's attach flow without
  // leaking the home chip's state into a scoped page.
  opts=opts||{};
  if(document.getElementById('attach-pop')){_closeAttachPopover();return}
  anchor.classList.add('active');
  // Icon set — minimal line glyphs matching the rest of the popover family.
  const ICO_WRITE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`;
  const ICO_FILE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`;
  const ICO_LINK=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.72"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.72-1.72"/></svg>`;
  const ICO_FEED_LOCAL=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>`;
  const ICO_ARCHIVE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><line x1="10" y1="12" x2="14" y2="12"/></svg>`;

  const ICO_APPS=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>`;
  const ICO_SRCS=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><line x1="7.8" y1="7.2" x2="11" y2="16.2"/><line x1="16.2" y1="7.2" x2="13" y2="16.2"/></svg>`;
  const ICO_CHEV=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="srcs-chev"><polyline points="9 18 15 12 9 6"/></svg>`;

  // My sources count — empty for now until a connected-sources table lands;
  // when populated, the flyout lists each connected app and lets you jump
  // into its app panel.
  const connectedSources=[];

  // Mini-logo preview for the "Add a source" row — shows the first 4
  // connectors as quick chips so the menu hints at what's available
  // without opening the picker.
  const addLogos=_SOURCE_CONNECTORS.slice(0,4).map(c=>`<span class="srcs-mini-logo" style="background:${c.bg};color:${c.fg}">${c.mono}</span>`).join('');

  const pop=document.createElement('div');pop.id='attach-pop';pop.className='srcs-pop';
  // Write goes first — for a freshly-created KB the most natural next step
  // is jotting your own thinking, not hunting for a URL or file. enterWrite()
  // transforms the home composer in-place: on the empty greeting it feels
  // like a write page (greeting hides via home--writing); mid-chat it sits
  // below the existing transcript so context is preserved.
  pop.innerHTML=`<button class="srcs-pop-item" data-action="write"><span class="srcs-pop-ico">${ICO_WRITE}</span><span class="srcs-pop-nm">Write a note</span><span class="srcs-pop-aside"><span class="srcs-pop-val">Markdown</span></span></button>` +
    `<button class="srcs-pop-item" data-action="upload"><span class="srcs-pop-ico">${ICO_FILE}</span><span class="srcs-pop-nm">Upload file</span><span class="srcs-pop-aside"><span class="srcs-pop-val">PDF · MD · DOCX</span></span></button>` +
    `<button class="srcs-pop-item" data-action="url"><span class="srcs-pop-ico">${ICO_LINK}</span><span class="srcs-pop-nm">Import a page</span><span class="srcs-pop-aside"><span class="srcs-pop-val">URL or paste</span></span></button>` +
    `<button class="srcs-pop-item" data-action="rss"><span class="srcs-pop-ico">${ICO_FEED_LOCAL}</span><span class="srcs-pop-nm">Add RSS feed</span><span class="srcs-pop-aside"><span class="srcs-pop-val">living source</span></span></button>` +
    `<div class="srcs-pop-sep"></div>` +
    `<button class="srcs-pop-item" data-menu="my-sources"><span class="srcs-pop-ico">${ICO_SRCS}</span><span class="srcs-pop-nm">My sources</span><span class="srcs-pop-aside"><span class="srcs-pop-val">${connectedSources.length}</span>${ICO_CHEV}</span></button>` +
    `<button class="srcs-pop-item" data-action="add-source"><span class="srcs-pop-ico">${ICO_APPS}</span><span class="srcs-pop-nm">Add a source</span><span class="srcs-pop-aside"><span class="srcs-pop-logos">${addLogos}</span>${ICO_CHEV}</span></button>`;
  document.body.appendChild(pop);
  const r=anchor.getBoundingClientRect();const pw=pop.offsetWidth;const ph=pop.offsetHeight;
  let left=r.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;if(left<8)left=8;
  let top=r.bottom+6;if(top+ph>window.innerHeight-8)top=r.top-ph-6;
  pop.style.left=left+'px';pop.style.top=top+'px';

  // Two modes:
  //   - Home: no opts.corpusId. Default corpus is _homeScope (possibly null,
  //     meaning "let the upload flow resolve"). Panels render their own
  //     addLine feedback into the chat stream and we flip home--active so
  //     the injected panel has room.
  //   - Corpus page: opts.corpusId + opts.onComplete. Panels are locked to
  //     that corpus and on success call onComplete (renderCorpus) instead
  //     of streaming chat lines — the corpus page's output container isn't
  //     a terminal, so addLine would leave orphaned DOM behind.
  const lockedCorpus=opts.corpusId||null;
  const panelOpts=lockedCorpus?{lockCorpus:true,onComplete:opts.onComplete}:null;
  const targetCorpus=lockedCorpus||_homeScope;
  const appCtx={corpusId:lockedCorpus,onComplete:opts.onComplete};

  // Flyout for "My sources" — shows connected apps (empty state for now).
  function openMySourcesFlyout(rowBtn){
    _closeSrcsFlyout();
    rowBtn.classList.add('hover');
    const fl=document.createElement('div');fl.id='srcs-flyout';fl.className='srcs-flyout';
    if(connectedSources.length){
      fl.innerHTML=connectedSources.map(s=>`<button class="srcs-flyout-row" data-kind="${s.kind}"><span class="srcs-flyout-main"><span class="srcs-flyout-nm">${esc(s.name)}</span><span class="srcs-flyout-dc">${esc(s.detail||'')}</span></span></button>`).join('');
    }else{
      fl.innerHTML=`<div class="srcs-flyout-empty">No sources connected yet.<br/>Use <strong>Add a source</strong> below to import an Obsidian vault, a Notion export, or connect an app.</div>`;
    }
    document.body.appendChild(fl);
    const popR=pop.getBoundingClientRect();const rowR=rowBtn.getBoundingClientRect();
    const fw=fl.offsetWidth;const fh=fl.offsetHeight;
    let fLeft=popR.right+6;if(fLeft+fw>window.innerWidth-8)fLeft=popR.left-fw-6;
    let fTop=rowR.top-4;if(fTop+fh>window.innerHeight-8)fTop=window.innerHeight-fh-8;if(fTop<8)fTop=8;
    fl.style.left=fLeft+'px';fl.style.top=fTop+'px';
    fl.querySelectorAll('.srcs-flyout-row').forEach(btn=>{
      btn.onclick=()=>{_closeAttachPopover();showAppPanel(btn.dataset.kind,appCtx)};
    });
  }

  pop.querySelectorAll('.srcs-pop-item').forEach(btn=>{
    const menu=btn.dataset.menu;
    if(menu==='my-sources'){
      btn.addEventListener('mouseenter',()=>openMySourcesFlyout(btn));
      btn.addEventListener('click',()=>openMySourcesFlyout(btn));
      return;
    }
    // Close any open flyout when hovering a non-menu item
    btn.addEventListener('mouseenter',_closeSrcsFlyout);
    btn.onclick=()=>{
      const action=btn.dataset.action;
      _closeAttachPopover();
      // When opts.onAction is set (corpus page handoff), the popover is just
      // a picker — the caller takes over from here (typically navigates to
      // /main and re-fires the panel there). Skips the local panel render so
      // we don't double up with whatever the caller's about to show.
      if(opts.onAction){opts.onAction(action);return}
      // Only collapse home for actions that render a panel INTO term-output
      // (upload / url / rss). `add-source` opens an overlay — leaving
      // home--active on would pin the composer to the top with nothing
      // under it after the overlay is dismissed.
      const collapseHome=()=>{if(!lockedCorpus){const h=document.getElementById('home');if(h)h.classList.add('home--active')}};
      if(action==='write'){
        // enterWrite is closure-scoped to renderHome — caller passes it via
        // opts.onWrite. On the corpus page no onWrite is set, but onAction
        // above already short-circuited that path (navigates to /main with
        // _pendingHomeAttachAction='write'), so we never get here in that
        // mode.
        if(opts.onWrite)opts.onWrite();
      }
      else if(action==='upload'){collapseHome();showTermUpload(output,input,targetCorpus,panelOpts)}
      else if(action==='url'){collapseHome();showTermUpload(output,input,targetCorpus,panelOpts);setTimeout(()=>{const urlTab=document.querySelector('.term-upload-tab[data-tab="url"]');urlTab?.click()},50)}
      else if(action==='rss'){collapseHome();showTermConnectRSS(output,input,targetCorpus,panelOpts)}
      else if(action==='add-source'){showAddSourcePicker(appCtx)}
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
  document.querySelectorAll('.composer-mode-label.active').forEach(b=>b.classList.remove('active'));
}
function _closeSrcsFlyout(){
  const f=document.getElementById('srcs-flyout');if(f)f.remove();
  document.querySelectorAll('.srcs-pop-item.hover').forEach(b=>b.classList.remove('hover'));
}

/* Build compile-mode topic examples tailored to the picked corpus.
   Signal sources, in order of preference:
     1. tags          — user-curated, highest-signal, low-cost
     2. task_types    — LLM-derived answer shapes ("how-to", "advice", …)
     3. corpus name   — last resort so we always have something concrete
   Always returns two quoted suggestions for visual rhythm with the
   "Topic to compile — …" label; falls back to the generic pair when no
   corpus is picked. */
function _compileSuggestionsFor(corpus){
  if(!corpus)return '"Vision Pro reviews", "Team culture rituals"';
  const tags=Array.isArray(corpus.tags)?corpus.tags.filter(Boolean):[];
  const tts=Array.isArray(corpus.task_types)?corpus.task_types.filter(Boolean):[];
  const nm=(corpus.name||'').trim();
  const picks=[];
  // Tags read as subject matter — cleanest fit for a compile topic.
  for(const t of tags){if(picks.length<2)picks.push(`${t} overview`)}
  // Fall through to task_types if tags didn't fill; prefix with name so
  // the suggestion reads like a real question, not a bare word.
  if(picks.length<2){
    for(const t of tts){
      if(picks.length>=2)break;
      if(t==='how-to')picks.push(nm?`how ${nm} works`:'how this works');
      else if(t==='factual-lookup')picks.push(nm?`${nm} key facts`:'key facts');
      else if(t==='advice')picks.push(nm?`${nm} best practices`:'best practices');
      else if(t==='comparison')picks.push(nm?`${nm} comparison`:'comparisons');
      else if(t==='synthesis')picks.push(nm?`${nm} takeaways`:'key takeaways');
    }
  }
  // Last-ditch: derive two topics from the corpus name alone.
  if(picks.length<2 && nm){
    const fills=[`${nm} overview`,`${nm} key lessons`];
    for(const f of fills){if(picks.length<2)picks.push(f)}
  }
  if(picks.length===0)return '"overview", "key takeaways"';
  if(picks.length===1)return `"${picks[0]}"`;
  return `"${picks[0]}", "${picks[1]}"`;
}

function _refreshComposerPlaceholder(){
  // Retint the composer placeholder + the inline mode label so Send behavior
  // is legible at a glance (Notion "Plan mode" pattern). Compile + Enrich
  // placeholders now pull examples from the picked corpus so users see
  // suggestions that fit THEIR KB, not a hard-coded "Vision Pro" fallback.
  const input=document.getElementById('term-input');
  const composer=document.getElementById('home-composer');
  const isWrite=composer&&composer.classList.contains('home-composer-note');
  if(input&&!isWrite){
    const picked=_homeScope&&_corpora.find(c=>c.id===_homeScope);
    if(_composerMode==='compile'){
      const suggestions=_compileSuggestionsFor(picked);
      if(picked){
        input.placeholder=`Topic to compile for "${picked.name}" — e.g. ${suggestions}`;
      }else{
        input.placeholder=`Topic to compile — e.g. ${suggestions}`;
      }
    }else if(_composerMode==='create'){
      input.placeholder='What\'s on your mind? — "harness engineering", "founder playbook"';
    }else{
      // Enrich — talk to / grow a specific KB. Lead with the chat verb (the
      // primary affordance), then surface the three "add material" doors —
      // note / URL / file — in the same order the + popover lists them, so
      // the placeholder maps cleanly to the menu the user sees below.
      if(picked){
        input.placeholder=`Chat to enrich "${picked.name}" — or add a note, URL, or file`;
      }else{
        input.placeholder='Pick a knowledge base below — chat to enrich, or add a note, URL, or file';
      }
    }
  }
  const lbl=document.getElementById('home-mode-label');
  if(lbl){
    const m=COMPOSER_MODES.find(x=>x.id===_composerMode)||COMPOSER_MODES[1];
    lbl.textContent=m.name+' mode';
  }
}

/* Mode popover — anchored to the "Enrich mode" label. Minimal design:
   list the composer modes with name + description, click to pick.
   Sources (My / Add) moved into the + attach popover — see showAttachPopover.
   The separate sliders toggle was removed: the popover controls mode only,
   so the mode label itself is the entry point. */
function showSourcesPopover(anchor,ctx){
  if(document.getElementById('srcs-pop')){_closeSrcsPopover();return}
  anchor.classList.add('active');
  const pop=document.createElement('div');
  pop.id='srcs-pop';pop.className='srcs-pop';
  const modes=COMPOSER_MODES;
  pop.innerHTML=`<div class="srcs-pop-hd">Composer mode</div>`+
    modes.map(m=>{
      const active=m.id===_composerMode;
      return `<button class="srcs-pop-mode${active?' active':''}" data-mode="${m.id}">
        <span class="srcs-pop-mode-main">
          <span class="srcs-pop-mode-nm">${esc(m.name)}${active?' <span class="srcs-pop-mode-chk">✓</span>':''}</span>
          <span class="srcs-pop-mode-dc">${esc(m.desc)}</span>
        </span>
      </button>`;
    }).join('');
  document.body.appendChild(pop);
  const r=anchor.getBoundingClientRect();const pw=pop.offsetWidth;const ph=pop.offsetHeight;
  let left=r.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;if(left<8)left=8;
  let top=r.bottom+6;if(top+ph>window.innerHeight-8)top=r.top-ph-6;
  pop.style.left=left+'px';pop.style.top=top+'px';

  pop.querySelectorAll('.srcs-pop-mode').forEach(btn=>{
    btn.onclick=()=>{
      _composerMode=btn.dataset.mode;
      _closeSrcsPopover();
      _refreshComposerPlaceholder();
    };
  });

  setTimeout(()=>{
    const outside=(e)=>{
      if(pop.contains(e.target))return;
      if(e.target===anchor)return;
      _closeSrcsPopover();document.removeEventListener('click',outside,true);
    };
    document.addEventListener('click',outside,true);
    const esc=(e)=>{if(e.key==='Escape'){_closeSrcsPopover();document.removeEventListener('keydown',esc)}};
    document.addEventListener('keydown',esc);
  },0);
}

/* Connector-logos hint strip below composer — Notion-style "Get better
   answers from your apps" row. Dismissal is now session-scoped (returns
   next session) instead of permanent. Workspace-aware: order + label
   change so personal sees creator tools first, team sees edge-capture
   tools first. */
const _CHINT_FLAG='noosphere_chint_dismissed';

// Per-connector priority (lower = front). Personal favors creator tools;
// team favors edge-capture (Slack / email / meetings) and ticketing.
// Used by orderedConnectors() below; default 99 if missing.
const _CONNECTOR_PRIORITY={
  // kind        personal, team
  obsidian:    [1, 8],
  notion:      [2, 5],
  twitter:     [3, 12],
  readwise:    [4, 13],
  evernote:    [5, 14],
  apple_notes: [6, 15],
  rss_auto:    [7, 7],
  gdrive:      [8, 6],
  github:      [9, 4],
  gmail:       [10, 3],
  slack:       [11, 1],
  email_inbox: [12, 2],
};

function orderedConnectors(){
  const team=_workspace.kind==='org';
  return [..._SOURCE_CONNECTORS].sort((a,b)=>{
    const pa=(_CONNECTOR_PRIORITY[a.kind]||[99,99])[team?1:0];
    const pb=(_CONNECTOR_PRIORITY[b.kind]||[99,99])[team?1:0];
    return pa-pb;
  });
}

function renderChint(elId,ctx){
  const el=document.getElementById(elId);if(!el)return;
  if(sessionStorage.getItem(_CHINT_FLAG)==='1'){el.innerHTML='';return}
  const conns=orderedConnectors();
  const logos=conns.map(c=>`<button class="chint-logo" style="background:${c.bg};color:${c.fg}" title="${esc(c.name)}" data-kind="${c.kind}">${c.mono}</button>`).join('');
  // Strip label conveys the team-version core value (capture from where
  // you work) instead of the generic personal copy.
  const stripLabel=_workspace.kind==='org'
    ? 'Capture from where your team works'
    : 'Connect live sources';
  el.innerHTML=`<span class="chint-lbl">${esc(stripLabel)}</span><span class="chint-logos">${logos}</span><button class="chint-close" type="button" title="Hide for this session">×</button>`;
  el.querySelector('.chint-close').onclick=()=>{sessionStorage.setItem(_CHINT_FLAG,'1');el.innerHTML=''};
  el.querySelectorAll('.chint-logo').forEach(btn=>{btn.onclick=()=>{showAppPanel(btn.dataset.kind,ctx||{})}});
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
    // Per-connector CTA override (e.g. Obsidian uses "Import vault" today
    // because it's one-shot ZIP, not a persistent OAuth connection). Falls
    // back to "Connect" for OAuth-style connectors once they ship.
    const defaultCta=c.pro?'Connect · Pro':'Connect';
    const activeLabel=c.cta?(c.pro?`${c.cta} · Pro`:c.cta):defaultCta;
    // Panel opens for every app, including 'soon' ones — lets users see the
    // per-method roadmap. Soon-status apps get a "View" label instead of CTA.
    const btnLabel=isSoon?'View':activeLabel;
    const btnClass=isSoon?'ck-btn ck-btn-soon':'ck-btn ck-btn-connect';
    return `<div class="ck-card${isSoon?' ck-card-soon':''}"><div class="ck-card-top"><span class="ck-ico" style="background:${c.bg};color:${c.fg}">${c.mono}</span><div class="ck-card-meta"><div class="ck-nm">${esc(c.name)}</div><div class="ck-rank">#${i+1} popular</div></div></div><div class="ck-dc">${esc(c.desc)}</div><div class="ck-card-foot"><button class="${btnClass}" data-kind="${c.kind}">${btnLabel}</button></div></div>`;
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
  // Every card click opens the per-app panel — even for 'soon' apps, so
  // users can see the full roadmap (e.g. "OAuth live sync — Soon") per app.
  // Per-method Pro gating and status are handled inside showAppPanel.
  ct.querySelectorAll('.ck-btn').forEach(btn=>{
    btn.onclick=()=>{
      const kind=btn.dataset.kind;
      showAppPanel(kind,{});
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
    return `<button class="srcs-pick-row" data-kind="${c.kind}"><span class="srcs-pick-ico" style="background:${c.bg};color:${c.fg}">${c.mono}</span><span class="srcs-pick-main"><span class="srcs-pick-nm">${esc(c.name)}${tag}</span><span class="srcs-pick-dc">${esc(c.desc)}</span></span></button>`;
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
      close();
      showAppPanel(kind,ctx||{});
    };
  });
}

/* ══════ CORPUS DETAIL + CHAT ══════ */

// Safe wrapper around renderCorpus — when any inline doc editor is open, the
// full re-render would wipe in-progress edits. Skip the re-render in that
// case; callers should already toast their own success message, and stale
// counts/badges are an acceptable papercut compared to data loss.
function renderCorpusSafe(id, sessionId){
  if(document.querySelector('#content .doc-item.editing')){
    console.warn('[renderCorpus] skipped — inline editor is open; user data preserved');
    return;
  }
  return renderCorpus(id, sessionId);
}

/* ══════ Share dialog — corpus + doc → Twitter intent + Copy link ══════ */
// Opens a modal with the matching OG card preview, an editable tweet text,
// the canonical /c/{slug} URL, and a Tweet button that fires the Twitter
// intent URL. The OG card image is fetched from the same /og/c/.../*.png
// endpoint Twitter's scraper hits, so what the user sees here is what
// followers will see in their feed.
function openShareDialog(corpus,doc){
  const base=window.location.origin;
  // Slugs can be non-ASCII (CJK corpus names → "子瞻集"). Twitter's link
  // tokenizer ends the URL at the first non-ASCII byte, so an un-encoded
  // slug yields a broken/truncated link in the tweet. Percent-encode it.
  const slug=encodeURIComponent(corpus.slug||corpus.id);
  const url=doc?`${base}/c/${slug}/d/${doc.id}`:`${base}/c/${slug}`;
  const ogImg=doc?`/og/c/${slug}/d/${doc.id}.png`:`/og/c/${slug}.png`;
  // Subject label for the dialog header — "corpus" / "wiki entry" / "note"
  // gives the user a moment of confirmation about what they're actually
  // sharing before the tweet ships.
  const subjLabel=!doc?'Corpus':(doc.doc_type==='concept'?'Wiki entry':'Note');
  // Default tweet text: a sensible starting point the user will almost
  // always edit. Keep under ~260 chars so the URL has room (Twitter
  // reserves 23 chars for t.co shortening + 1 for the separating space).
  let defaultText;
  if(!doc){
    defaultText=(corpus.description||'').trim()||corpus.name||'';
  }else{
    const ttl=(doc.title||'').replace(/^Concept:\s+/,'').trim();
    let content=(doc.content||'')
      .replace(/^\s*#{1,6}\s+[^\n]{1,80}\n+/,'')
      .replace(/\*\*([^*]+)\*\*/g,'$1')
      .replace(/`([^`]+)`/g,'$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g,'$1')
      .trim();
    if(doc.doc_type==='concept'){
      const m=content.match(/#{2,3}\s+Summary\s*\n+([\s\S]*?)(?=\n+#{2,3}\s+\w|$)/);
      if(m)content=m[1].trim();
    }
    const body=content.replace(/\s+/g,' ').trim();
    if(ttl){
      const room=240-ttl.length-3;
      defaultText=`${ttl} — ${body.slice(0,room)}${body.length>room?'…':''}`;
    }else{
      defaultText=`"${body.slice(0,240)}${body.length>240?'…':''}"`;
    }
  }
  const MAX=256;
  if(defaultText.length>MAX)defaultText=defaultText.slice(0,MAX-1).trim()+'…';

  const overlay=document.createElement('div');
  overlay.className='share-overlay';
  overlay.innerHTML=`<div class="share-panel" role="dialog" aria-modal="true" aria-label="Share">
    <div class="share-hd">
      <div class="share-hd-text">
        <div class="share-title">Share to Twitter</div>
        <div class="share-sub">${esc(subjLabel)} · ${esc(corpus.name||'')}</div>
      </div>
      <button class="share-close" id="share-close" aria-label="Close">&times;</button>
    </div>
    <div class="share-body">
      <div class="share-preview"><div class="share-preview-loading" id="share-preview-loading">Rendering preview…</div><img class="share-preview-img" id="share-preview-img" alt="" style="display:none" /></div>
      <textarea class="share-text" id="share-text" rows="3" placeholder="What's this about?">${esc(defaultText)}</textarea>
      <div class="share-foot">
        <div class="share-url-row"><code class="share-url" title="${esc(url)}">${esc(url)}</code><button class="share-copy" id="share-copy" type="button">Copy link</button></div>
        <div class="share-count" id="share-count"></div>
      </div>
    </div>
    <div class="share-actions">
      <button class="btn-sm-ghost" id="share-cancel" type="button">Cancel</button>
      <button class="btn-sm" id="share-go" type="button">Tweet</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);

  const img=overlay.querySelector('#share-preview-img');
  const loading=overlay.querySelector('#share-preview-loading');
  img.onload=()=>{img.style.display='block';loading.style.display='none'};
  img.onerror=()=>{loading.textContent='Preview unavailable'};
  img.src=ogImg;

  const ta=overlay.querySelector('#share-text');
  const counter=overlay.querySelector('#share-count');
  const updateCount=()=>{
    const remain=280-ta.value.length-24;
    counter.textContent=`${remain} left`;
    counter.classList.toggle('share-count-over',remain<0);
  };
  ta.oninput=updateCount;updateCount();
  ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length);

  const close=()=>{overlay.remove();document.removeEventListener('keydown',escHandler)};
  const escHandler=(e)=>{if(e.key==='Escape')close()};
  document.addEventListener('keydown',escHandler);
  overlay.querySelector('#share-close').onclick=close;
  overlay.querySelector('#share-cancel').onclick=close;
  overlay.onclick=(e)=>{if(e.target===overlay)close()};

  overlay.querySelector('#share-copy').onclick=async()=>{
    try{await navigator.clipboard.writeText(url);toast('Link copied')}
    catch(e){toast('Copy failed — select and copy manually')}
  };
  overlay.querySelector('#share-go').onclick=()=>{
    const text=ta.value.trim();
    const intent=`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
    window.open(intent,'_blank','noopener,noreferrer');
    close();
  };
}

async function renderCorpus(id,sessionId){
  stopAll();_chatH=[];const ct=document.getElementById('content');ct.classList.remove('content--corpus');ct.innerHTML='<div class="empty">Loading...</div>';
  let c;try{const r=await fetch(`${API}/corpora/${id}`);if(!r.ok){const e=await r.json().catch(()=>({}));const msg=r.status===404?'Corpus not found':r.status===401?'Access denied — this corpus requires authentication':r.status===402?e.detail||'Payment required to access this corpus':r.status===403?e.detail||'Access denied':e.detail||'Corpus not found';ct.innerHTML=`<a class="cv-back" href="#/corpora">&larr; Corpora</a><div class="empty" style="margin-top:40px">${msg}</div>`;hideRP();return}c=await r.json()}catch(e){ct.innerHTML='<div class="empty">Not found</div>';hideRP();return}
  // Public corpora get structured metadata so AI/search crawlers can index
  // the corpus (Dataset schema). Private corpora skip this — there's nothing
  // to advertise to external crawlers.
  if((c.access_level||'public')!=='private')_setCorpusJsonLD(c);
  let docs=[];try{const r=await fetch(`${API}/corpora/${id}/documents`);if(r.ok)docs=await r.json()}catch(e){}
  let ents=[];try{const r=await fetch(`${API}/corpora/${id}/entities`);if(r.ok){const _ed=await r.json();ents=_ed.entities||(Array.isArray(_ed)?_ed:[])}}catch(e){}
  let an={};try{const r=await fetch(`${API}/corpora/${id}/analytics?limit=5`);if(r.ok)an=await r.json()}catch(e){}
  ct.classList.add('content--corpus');
  const al=c.access_level||'public';const tg=Array.isArray(c.tags)?c.tags:[];
  const badgeLabel=al==='token'?'Token-gated':al.charAt(0).toUpperCase()+al.slice(1);
  // Split docs:
  //   wiki = Manifest (pinned first) + AI-synthesized concept notes
  //   raw  = everything else (the Sources substrate)
  //
  // Manifest lives INSIDE the Wiki section as its first entry — this mirrors
  // GitHub's treatment of README.md (it's a file in the repo, just styled
  // specially and pinned to the top). Keeping it as a real doc rather than a
  // separate above-Wiki card gives it the same click-to-expand interaction as
  // every other wiki doc, and avoids adding a fourth section to the layout.
  const manifestDoc=docs.find(d=>d.doc_type==='manifest')||null;
  const conceptDocs=docs.filter(d=>d.doc_type==='concept');
  // Manifest always first; concept notes after.
  const wikiDocs=manifestDoc?[manifestDoc,...conceptDocs]:conceptDocs;
  // Entities are the synthesis/index layer — in the gbrain/Karpathy model an
  // entity page (compiled truth + timeline) is the same primitive as a
  // concept page, so they render in Wiki alongside concepts. The entity's own
  // page-doc (same title) is dropped from Sources to avoid a duplicate row —
  // it's still reachable under the entity's "Mentioned in".
  const entNameSet=new Set(ents.map(e=>(e.canonical_name||'').toLowerCase()).filter(Boolean));
  const rawDocs=docs.filter(d=>d.doc_type!=='concept'&&d.doc_type!=='manifest'&&!entNameSet.has((d.title||'').toLowerCase()));
  // Entity rows use the SAME row primitive as doc rows (.doc-item) for one
  // consistent Wiki rhythm — just an <a> to the entity page instead of an
  // expandable doc. Kind is carried in the meta line (like a doc's
  // source-kind), so no separate per-kind sub-headers are needed.
  const _ENT_LABELS={person:'Person',organization:'Company',concept:'Concept',work:'Work',place:'Place'};
  const _entRank={person:0,organization:1,concept:2,work:3,place:4};
  const entRows=ents.slice().sort((a,b)=>{
    const ra=_entRank[a.kind]??9,rb=_entRank[b.kind]??9;
    return ra!==rb?ra-rb:(b.mention_count||0)-(a.mention_count||0);
  });
  const entGroupsHTML=entRows.map(e=>{
    const n=e.mention_count||0;
    const meta=`${_ENT_LABELS[e.kind]||esc(e.kind)}${n?` · ${n} mention${n===1?'':'s'}`:''}`;
    return `<div class="doc-item doc-item--entity" data-entity-id="${e.id}"><div class="doc-hd"><span class="doc-tt">${esc(e.canonical_name)}</span><span class="doc-hd-right"><span class="doc-mt">${meta}</span><span class="doc-ar">▸</span></span></div></div>`;
  }).join('');
  const docItemHTML=(d)=>{
    const wc=d.word_count||0;const wlab=wc.toLocaleString()+' word'+(wc===1?'':'s');
    // Manifest renders with the same visual language as every other doc
    // (same title font, same meta layout, same source-kind pill) — the only
    // difference is a `system generated` origin tag (vs user_original etc.)
    // and no edit/delete buttons (the doc is auto-regenerated from corpus
    // fields; user-side edits would be thrown away on the next refresh).
    if(d.doc_type==='manifest'){
      return `<div class="doc-item" data-id="${d.id}"><div class="doc-hd"><span class="doc-tt">${esc(d.title||'Manifest')}</span><span class="doc-hd-right"><span class="doc-mt">${wlab} · <span class="doc-sk sk-system">system generated</span></span><span class="doc-ar">▸</span></span></div></div>`;
    }
    const sk=d.source_kind||'user_original';const skLabel=sk.replace('_',' ');
    // Show the contributor pill only in team workspaces — meaningless solo.
    const contribHTML=(_workspace.kind==='org'&&d.contributor_user_id)?(' · '+renderContributorPill(d.contributor_user_id)):'';
    return `<div class="doc-item" data-id="${d.id}"><div class="doc-hd"><span class="doc-tt">${esc(d.title)}</span><span class="doc-hd-right"><span class="doc-mt">${wlab}${d.date?' · '+d.date:''} · <span class="doc-sk sk-${sk}">${skLabel}</span>${contribHTML}</span><span class="doc-actions"><button class="doc-action-btn doc-share-btn" data-id="${d.id}" title="Share"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></button><button class="doc-action-btn doc-edit-btn" data-id="${d.id}" title="Edit"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button><button class="doc-action-btn doc-del-btn" data-id="${d.id}" title="Delete"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button></span><span class="doc-ar">▸</span></span></div></div>`;
  };
  // Wiki empty-state: phrase matters depending on whether the manifest is
  // already there. Even before the user compiles a single concept note, the
  // manifest is the first entry — so "No concept notes yet" is the accurate
  // framing (Wiki is never truly empty once the corpus exists).
  const wikiEmpty='<div class="empty">No concept notes yet — Compile to synthesize from your sources.</div>';
  const rawEmpty='<div class="empty">No sources yet — + Add to import URLs, upload files, or import an archive.</div>';
  // Tab strip — Overview (current) · Insights (coming soon shell). Route
  // via hash: #/corpus/{id} = Overview, #/corpus/{id}/insights = Insights.
  // Keeping the URL shape stable now so future Agent-activity data lands
  // without a migration.
  const tabStripHTML=`<div class="cv-tabs"><a href="#/corpus/${id}" class="cv-tab cv-tab--active">Overview</a><a href="#/corpus/${id}/insights" class="cv-tab">Insights</a><a href="#/corpus/${id}/settings" class="cv-tab">Settings</a></div>`;
  // Wiki sub-label counts EVERY item rendered in the section (manifest +
  // concept notes). Earlier version counted concepts only — users saw 2
  // rows with "1" in the header and reasonably asked "why 1?". Match the
  // visual truth. "synthesis" stays as descriptor since both qualify:
  // manifest = templated synthesis of corpus fields; concept = LLM
  // synthesis of sources.
  const wikiCount=wikiDocs.length+ents.length;
  const wikiSubLabel=wikiCount?`${wikiCount} · synthesis`:'synthesis';
  ct.innerHTML=`<div class="cv-layout"><div class="cv-scroll"><div class="cv-header"><div class="cv-header-top"><a class="cv-back" href="#/corpora">&larr; Corpora</a></div><div class="cv-identity"><h1 class="cv-name">${esc(c.name)}</h1><span class="mc-badge mc-badge-${al}">${badgeLabel}</span><button class="cv-share-btn" id="cv-share-btn" type="button" title="Share this corpus">Share</button></div><div class="cv-desc-wrap">${c.description?`<p class="cv-desc" id="cv-desc">${esc(c.description)}</p>`:`<p class="cv-desc cv-desc-empty" id="cv-desc">Add a description...</p>`}<button class="cv-desc-edit-btn" id="cv-desc-edit" title="Edit description"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></div>${tg.length?`<div class="cv-tags">${tg.map(t=>`<span class="mc-meta-tag">${esc(t)}</span>`).join('')}</div>`:''}</div>${tabStripHTML}<div class="cv-sec cv-sec-wiki"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Wiki</span><span class="cv-st-sub">${wikiSubLabel}</span></div><button class="btn-add" id="cv-compile-btn">Compile</button></div><div id="cv-wiki-docs">${(wikiDocs.length===0&&ents.length===0)?wikiEmpty:''}${wikiDocs.map(docItemHTML).join('')}${entGroupsHTML}</div></div><div class="cv-sec cv-sec-raw"><div class="cv-st"><div class="cv-st-main"><span class="cv-st-title">Sources</span><span class="cv-st-sub">${rawDocs.length?rawDocs.length+' · substrate':'substrate'}</span></div><button class="btn-add" id="cv-raw-add">+ Add</button></div><div id="cv-raw-docs">${rawDocs.length===0?rawEmpty:rawDocs.map(docItemHTML).join('')}</div></div><div class="cv-scroll-end"></div></div><div class="cv-chat-dock" id="cv-chat-dock" role="search"><div class="home-composer cv-composer" id="cv-composer"><textarea class="home-composer-input" id="cv-composer-input" placeholder="" rows="1" autocomplete="off"></textarea><div class="home-composer-foot"><span class="home-composer-left"><button class="composer-attach" id="cv-composer-attach" title="Add content" aria-label="Add content"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button><button class="composer-mode-label" id="cv-composer-mode" type="button">Enrich mode</button><span class="home-composer-hint" id="cv-composer-hint">Press Enter to chat</span></span><span class="home-composer-right"><span class="home-composer-model">Noos</span><button class="home-composer-send" id="cv-composer-send" title="Send" aria-label="Send"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></span></div><div class="home-composer-conn"><span class="home-chip home-chip-locked" aria-readonly="true"><span class="home-chip-label">Corpus: ${esc(c.name)}</span></span></div></div></div></div>`;
  showRP(c,an);
  // Description editor — surgical (no renderCorpus). Snapshot the read-only
  // markup, swap in the input, and restore (with the new value on save) so
  // any inline source editor open elsewhere on the page survives.
  const _DESC_EDIT_BTN_HTML=`<button class="cv-desc-edit-btn" id="cv-desc-edit" title="Edit description"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>`;
  const _renderCvDescReadOnly=(wrap,desc)=>{
    const safe=esc(desc||'');
    const cls=desc?'cv-desc':'cv-desc cv-desc-empty';
    const txt=desc?safe:'Add a description...';
    wrap.innerHTML=`<p class="${cls}" id="cv-desc">${txt}</p>${_DESC_EDIT_BTN_HTML}`;
    document.getElementById('cv-desc-edit').onclick=_bindDescEdit;
  };
  function _bindDescEdit(){
    const wrap=document.querySelector('.cv-desc-wrap');
    const cur=c.description||'';
    wrap.innerHTML=`<input type="text" class="cv-desc-input" id="cv-desc-inp" value="${esc(cur)}" placeholder="Add a description..." /><div class="cv-desc-inp-actions"><button class="btn-sm" id="cv-desc-sv">Save</button><button class="btn-sm-ghost" id="cv-desc-cc">Cancel</button></div>`;
    document.getElementById('cv-desc-inp').focus();
    document.getElementById('cv-desc-cc').onclick=()=>_renderCvDescReadOnly(wrap,cur);
    document.getElementById('cv-desc-sv').onclick=async()=>{
      const v=document.getElementById('cv-desc-inp').value.trim();
      if(v===cur){_renderCvDescReadOnly(wrap,cur);return}
      try{
        await fetch(`${API}/corpora/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:v})});
        c.description=v;
        await loadC();
        _renderCvDescReadOnly(wrap,v);
      }catch(e){toast('Failed to save description');_renderCvDescReadOnly(wrap,cur)}
    };
  }
  document.getElementById('cv-desc-edit').onclick=_bindDescEdit;
  const shareBtnEl=document.getElementById('cv-share-btn');
  if(shareBtnEl)shareBtnEl.onclick=()=>openShareDialog(c,null);
  // Composer is the SOLE action surface on the corpus page. Section "+ Add"
  // and "Compile" buttons are discoverable shortcuts that just trigger the
  // composer in the right state — no inline panels under those buttons.
  const rawAddBtn=document.getElementById('cv-raw-add');
  const compileBtn=document.getElementById('cv-compile-btn');
  const cvComposerInput=document.getElementById('cv-composer-input');
  const cvComposerSend=document.getElementById('cv-composer-send');
  const cvComposerAttach=document.getElementById('cv-composer-attach');
  const cvComposerMode=document.getElementById('cv-composer-mode');
  const cvComposerHint=document.getElementById('cv-composer-hint');

  // Local mode state — corpus dock only supports Enrich (chat) and Compile
  // (synthesize wiki). Create doesn't apply because the corpus is fixed.
  // Default Enrich; flips to Compile when user clicks Wiki "Compile" or the
  // mode label and picks Compile.
  let _cvDockMode='enrich';
  const _cvSetMode=m=>{
    _cvDockMode=m;
    if(cvComposerMode)cvComposerMode.textContent=(m==='compile'?'Compile':'Enrich')+' mode';
    if(cvComposerHint)cvComposerHint.textContent=m==='compile'?'Press Enter to compile':'Press Enter to chat';
    if(cvComposerInput){
      if(m==='compile'){
        const sug=_compileSuggestionsFor(c);
        cvComposerInput.placeholder=`Topic to compile for "${c.name}" — e.g. ${sug}`;
      }else{
        cvComposerInput.placeholder=`Chat to enrich ${c.name} — or add a note, URL, or file`;
      }
    }
  };
  _cvSetMode('enrich');

  // Mode picker — small popover with Enrich + Compile, anchored to the mode
  // label. Mirrors the home composer's mode flyout but trimmed to two options.
  function _cvOpenModePicker(anchor){
    const existing=document.getElementById('cv-mode-pop');
    if(existing){existing.remove();return}
    const opts=[
      {id:'enrich',name:'Enrich',desc:'Grow this knowledge base through conversation'},
      {id:'compile',name:'Compile',desc:'Synthesize a wiki page from this corpus'},
    ];
    const pop=document.createElement('div');
    pop.id='cv-mode-pop';pop.className='srcs-flyout';
    pop.innerHTML=opts.map(m=>`<button class="srcs-flyout-row${m.id===_cvDockMode?' active':''}" data-mode="${m.id}"><span class="srcs-flyout-main"><span class="srcs-flyout-nm">${esc(m.name)}</span><span class="srcs-flyout-dc">${esc(m.desc)}</span></span><span class="srcs-flyout-chk">${m.id===_cvDockMode?'\u2713':''}</span></button>`).join('');
    document.body.appendChild(pop);
    const r=anchor.getBoundingClientRect();const pw=pop.offsetWidth;const ph=pop.offsetHeight;
    let left=r.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;
    let top=r.top-ph-6;if(top<8)top=r.bottom+6;
    pop.style.left=left+'px';pop.style.top=top+'px';
    pop.querySelectorAll('.srcs-flyout-row').forEach(btn=>{
      btn.onclick=()=>{_cvSetMode(btn.dataset.mode);pop.remove();cvComposerInput?.focus()};
    });
    setTimeout(()=>{
      const outside=e=>{if(!pop.contains(e.target)&&e.target!==anchor){pop.remove();document.removeEventListener('click',outside,true)}};
      document.addEventListener('click',outside,true);
    },0);
  }
  if(cvComposerMode)cvComposerMode.onclick=()=>_cvOpenModePicker(cvComposerMode);

  // "+ Add" in Sources header AND the composer's + both open the same attach
  // popover anchored to the corpus composer's + (so the picker visually
  // points at the input). Picking an option doesn't render the panel here —
  // it hands off to the home chat: corpus is pre-selected on the chip, the
  // matching panel (upload/url/archive/rss) is pre-rendered into the chat
  // stream, and the user lands in chat mode ready to fill it in.
  const openCorpusAttach=anchor=>showAttachPopover(anchor,null,null,{
    onAction:(action)=>{
      _pendingHomeScope=id;
      _pendingHomeAttachAction=action;
      _termCtx={};
      location.hash='#/main';
    }
  });
  if(rawAddBtn)rawAddBtn.onclick=()=>{cvComposerInput?.focus();openCorpusAttach(cvComposerAttach||rawAddBtn)};
  if(cvComposerAttach)cvComposerAttach.onclick=()=>openCorpusAttach(cvComposerAttach);

  // "Compile" in Wiki header just flips the composer into Compile mode. Send
  // (or Enter) then routes to /compile with the typed topic — same as the home
  // composer's compile flow.
  if(compileBtn)compileBtn.onclick=()=>{_cvSetMode('compile');cvComposerInput?.focus()};

  // Textarea autosize — matches the home composer behavior so the corpus dock
  // grows as you type a longer prompt.
  if(cvComposerInput){
    const autosize=()=>{cvComposerInput.style.height='auto';cvComposerInput.style.height=Math.min(cvComposerInput.scrollHeight,200)+'px'};
    cvComposerInput.addEventListener('input',autosize);
    autosize();
  }

  // Send: mode-aware. Enrich hands off to the home chat (corpus pre-scoped,
  // draft auto-sent). Compile navigates straight to the canvas /compile route
  // with the topic. Empty submit = no-op (lets users open the dock without
  // accidentally bouncing pages).
  const doSend=()=>{
    const v=(cvComposerInput?.value||'').trim();
    if(!v)return;
    if(_cvDockMode==='compile'){
      location.hash='#/compile?fresh=1&corpus='+encodeURIComponent(id)+'&topic='+encodeURIComponent(v);
      return;
    }
    _pendingHomeScope=id;
    _pendingHomeInput=v;
    _pendingHomeAutoSend=true;
    _termCtx={};
    location.hash='#/main';
  };
  if(cvComposerSend)cvComposerSend.onclick=doSend;
  if(cvComposerInput)cvComposerInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  ct.querySelectorAll('.doc-share-btn').forEach(btn=>{btn.onclick=e=>{
    e.stopPropagation();
    const did=btn.dataset.id;
    const doc=docs.find(d=>d.id===did);
    if(doc)openShareDialog(c,doc);
  }});
  ct.querySelectorAll('.doc-del-btn').forEach(btn=>{btn.onclick=async e=>{
    e.stopPropagation();const did=btn.dataset.id;const doc=docs.find(d=>d.id===did);
    if(!confirm(`Delete "${doc?.title||did}"? This cannot be undone.`))return;
    try{
      await fetch(`${API}/corpora/${id}/documents/${did}`,{method:'DELETE'});
      // Surgical: pull the row out of the DOM and update the section count
      // instead of full-page renderCorpus (which would wipe any inline source
      // editor the user has open elsewhere).
      const item=btn.closest('.doc-item');
      const list=item?.parentElement;
      const isWiki=list?.id==='cv-wiki-docs';
      item?.remove();
      docs=docs.filter(d=>d.id!==did);
      const remaining=isWiki?docs.filter(d=>d.doc_type==='concept'||d.doc_type==='manifest').length
                             :docs.filter(d=>d.doc_type!=='concept'&&d.doc_type!=='manifest').length;
      const subEl=document.querySelector(isWiki?'.cv-sec-wiki .cv-st-sub':'.cv-sec-raw .cv-st-sub');
      if(subEl)subEl.textContent=isWiki?(remaining?remaining+' · synthesis':'synthesis'):(remaining?remaining+' · substrate':'substrate');
      // If the section just emptied out, drop in the empty-state copy. Mirrors
      // renderCorpus's empty-state for these sections.
      if(remaining===0&&list){
        list.innerHTML=isWiki
          ?'<div class="empty">No concept notes yet — Compile to synthesize from your sources.</div>'
          :'<div class="empty">No sources yet — + Add to import URLs, upload files, or import an archive.</div>';
      }
    }catch(e){toast('Failed to delete document')}
  }});
  ct.querySelectorAll('.doc-edit-btn').forEach(btn=>{btn.onclick=async e=>{
    e.stopPropagation();const did=btn.dataset.id;const item=btn.closest('.doc-item');if(!item)return;
    if(item.classList.contains('editing'))return;
    try{const r=await fetch(`${API}/corpora/${id}/documents/${did}`);const doc=await r.json();showDocInlineEdit(id,item,doc)}catch(e){toast('Failed to load document')}
  }});
  ct.querySelectorAll('.doc-item').forEach(item=>{item.addEventListener('click',async e=>{
    if(e.target.closest('.doc-actions')||e.target.closest('a.wikilink')||e.target.closest('.ent-fullpage-link')||item.classList.contains('editing'))return;
    if(item.classList.contains('expanded')){const b=item.querySelector('.doc-bd');if(b)b.remove();item.classList.remove('expanded');return}
    item.classList.add('expanded');
    const isEnt=item.classList.contains('doc-item--entity');
    try{
      const b=document.createElement('div');b.className='doc-bd doc-bd-md';
      if(isEnt){
        const eid=item.dataset.entityId;
        const r=await fetch(`${API}/corpora/${id}/entities/${eid}`);
        const en=await r.json();
        b.innerHTML=(en.description?_mdToHtml(en.description):'<p class="doc-bd-empty">No compiled truth yet.</p>')
          +`<a class="ent-fullpage-link" href="#/corpus/${id}/entity/${eid}">Open full page &rarr;</a>`;
      }else{
        const r=await fetch(`${API}/corpora/${id}/documents/${item.dataset.id}`);
        const d=await r.json();
        b.innerHTML=_mdToHtml(d.content||'');
        _bindWikilinks(b,id);
      }
      item.appendChild(b);
    }catch(e){}
  })});
}

/* ══════ INSIGHTS TAB — Agent activity ══════ */
// Funnel view of how external agents actually use this KB: describe → preview
// → ask, plus conversion and top citing KBs. Data comes from query_logs
// (action column) and corpus_citations (incoming edges). Owner-only.
async function renderCorpusInsights(id){
  stopAll();hideRP();
  const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  let c=null;try{const r=await fetch(`${API}/corpora/${id}`);if(r.ok)c=await r.json()}catch(e){}
  if(!c){ct.innerHTML='<div class="empty" style="padding:48px;text-align:center">Corpus not found</div>';return}
  const al=c.access_level||'public';
  const badgeLabel=al==='token'?'Token-gated':al.charAt(0).toUpperCase()+al.slice(1);
  const tg=Array.isArray(c.tags)?c.tags:[];
  const win=(new URLSearchParams(location.hash.split('?')[1]||'').get('w'))||'7d';
  const winOpts=[['7d','7 days'],['30d','30 days'],['all','All time']];
  const winBar=winOpts.map(([v,l])=>`<a href="#/corpus/${id}/insights?w=${v}" class="cv-ins-win${v===win?' cv-ins-win--active':''}">${l}</a>`).join('');

  ct.innerHTML=`<div class="cv-layout cv-layout--full"><div class="cv-scroll"><div class="cv-header"><div class="cv-header-top"><a class="cv-back" href="#/corpora">&larr; Corpora</a></div><div class="cv-identity"><h1 class="cv-name">${esc(c.name)}</h1><span class="mc-badge mc-badge-${al}">${badgeLabel}</span></div>${c.description?`<p class="cv-desc">${esc(c.description)}</p>`:''}${tg.length?`<div class="cv-tags">${tg.map(t=>`<span class="mc-meta-tag">${esc(t)}</span>`).join('')}</div>`:''}</div>
    <div class="cv-tabs"><a href="#/corpus/${id}" class="cv-tab">Overview</a><a href="#/corpus/${id}/insights" class="cv-tab cv-tab--active">Insights</a><a href="#/corpus/${id}/settings" class="cv-tab">Settings</a></div>
    <div class="cv-ins-wrap">
      <div class="cv-ins-head"><div class="cv-ins-title">Agent activity</div><div class="cv-ins-winbar">${winBar}</div></div>
      <div id="cv-ins-body" class="cv-ins-body"><div class="cv-ins-loading">Loading…</div></div>
    </div>
    <div class="cv-scroll-end"></div></div></div>`;

  let data=null;
  try{
    const r=await fetch(`${API}/corpora/${id}/insights?window=${encodeURIComponent(win)}`);
    if(r.status===403){document.getElementById('cv-ins-body').innerHTML='<div class="cv-ins-empty">Insights are owner-only. Sign in as the corpus owner to view.</div>';return}
    if(!r.ok)throw new Error('Insights fetch failed: '+r.status);
    data=await r.json();
  }catch(e){
    document.getElementById('cv-ins-body').innerHTML=`<div class="cv-ins-empty">Could not load insights: ${esc(e.message||String(e))}</div>`;
    return;
  }

  const k=data.counters||{describe:0,preview_ask:0,ask:0};
  const conv=data.conversion;
  const convPct=(conv==null)?'—':(Math.round(conv*100)+'%');
  const callers=data.unique_callers||0;
  const rev=data.revenue;
  const reach=data.discovery_reach;
  const rh=data.revenue_health;
  const totalEvents=(k.describe||0)+(k.preview_ask||0)+(k.ask||0);
  const reachAI=reach?(reach.ai_surfaces_total||0):0;
  const reachScore=reach?(reach.score||0):0;

  const cards=[
    {label:'Reach (score)',value:reachScore.toFixed(1),hint:'weighted external AI visibility'},
    {label:'AI surfaces',value:reachAI,hint:'distinct AI callers'},
    {label:'Describe calls',value:k.describe,hint:'authenticated agents'},
    {label:'preview_ask runs',value:k.preview_ask,hint:'evaluating fit'},
    {label:'ask queries',value:k.ask,hint:'actual usage'},
    {label:'preview → ask',value:convPct,hint:'conversion rate'},
    {label:'Unique callers',value:callers,hint:'distinct agent_ids'},
  ];
  if(rh&&rh.active_paid){
    cards.push({label:'Subscribers',value:rh.subscriber_count||0,hint:'active'});
    if((rh.mrr_cents||0)>0){
      cards.push({label:'MRR',value:'$'+(rh.mrr_cents/100).toFixed(2),hint:'monthly recurring'});
    }
    if((rh.window_revenue_cents||0)>0){
      cards.push({label:'Window revenue',value:'$'+(rh.window_revenue_cents/100).toFixed(2),hint:'payments + settlements'});
    }
    if(rh.retention_rate!=null){
      cards.push({label:'Retention',value:Math.round(rh.retention_rate*100)+'%',hint:'active vs cancelled'});
    }
  }else if(rev&&(rev.paid_queries>0||rev.total_cents>0)){
    cards.push({label:'Revenue',value:'$'+(rev.total_cents/100).toFixed(2),hint:`${rev.paid_queries} paid`});
  }

  const kpiHTML=cards.map(c=>`<div class="cv-ins-card"><div class="cv-ins-card-val">${esc(String(c.value))}</div><div class="cv-ins-card-lbl">${esc(c.label)}</div><div class="cv-ins-card-hint">${esc(c.hint)}</div></div>`).join('');

  // Funnel bar — relative widths of describe / preview / ask.
  const maxN=Math.max(k.describe||0,k.preview_ask||0,k.ask||0,1);
  const funnelRow=(label,n,cls)=>{
    const pct=Math.round((n/maxN)*100);
    return `<div class="cv-ins-fn-row"><div class="cv-ins-fn-lbl">${esc(label)}</div><div class="cv-ins-fn-bar"><div class="cv-ins-fn-fill cv-ins-fn-fill--${cls}" style="width:${pct}%"></div></div><div class="cv-ins-fn-n">${n}</div></div>`;
  };
  const funnelHTML=`<div class="cv-ins-section"><div class="cv-ins-section-hd">Authenticated agent funnel</div><div class="cv-ins-section-sub">describe → preview_ask → ask, from query_logs (callers with x-agent-id or token).</div><div class="cv-ins-fn">${funnelRow('describe',k.describe||0,'d')}${funnelRow('preview_ask',k.preview_ask||0,'p')}${funnelRow('ask',k.ask||0,'a')}</div></div>`;

  // Discovery Reach — external/anonymous AI traffic broken down by class.
  // Separate from KBR (network-internal trust). Inputs from access_logs:
  // hits on llms.txt / sitemap / describe / preview surfaces, classified
  // by User-Agent.
  const reachLabels={
    claude:'Claude / Anthropic', gpt:'ChatGPT / OpenAI', perplexity:'Perplexity',
    ai_search:'AI search aggregators', claude_code:'Claude Code', cursor:'Cursor / coding agents',
    search_bot:'Search engine bots', generic_bot:'Generic bots', human:'Humans', unknown:'Unclassified',
  };
  let reachHTML='';
  if(reach&&reach.by_class&&Object.keys(reach.by_class).length){
    const entries=Object.entries(reach.by_class).map(([klass,v])=>({
      klass, label:reachLabels[klass]||klass,
      hits:v.hits||0, ips:v.distinct_ips||0, weight:v.weight||0,
    }));
    entries.sort((a,b)=>(b.weight*Math.log1p(b.ips))-(a.weight*Math.log1p(a.ips)));
    const maxIps=Math.max(...entries.map(e=>e.ips),1);
    const rows=entries.map(e=>{
      const pct=Math.round((e.ips/maxIps)*100);
      return `<div class="cv-ins-fn-row"><div class="cv-ins-fn-lbl">${esc(e.label)}</div><div class="cv-ins-fn-bar"><div class="cv-ins-fn-fill cv-ins-fn-fill--d" style="width:${pct}%"></div></div><div class="cv-ins-fn-n" title="${e.hits} hits, ${e.ips} distinct IPs, weight ${e.weight}">${e.ips}</div></div>`;
    }).join('');
    reachHTML=`<div class="cv-ins-section"><div class="cv-ins-section-hd">Discovery Reach</div><div class="cv-ins-section-sub">External AI surface visibility — distinct callers per class hitting llms.txt, sitemap, describe, preview. Score = Σ weight × ln(1 + distinct_ips).</div><div class="cv-ins-fn">${rows}</div></div>`;
  }else{
    reachHTML=`<div class="cv-ins-section"><div class="cv-ins-section-hd">Discovery Reach</div><div class="cv-ins-empty-sm">No external traffic in this window yet. Share the corpus llms.txt URL — that's the surface AI agents probe first.</div></div>`;
  }

  // Top citing KBs.
  const citing=Array.isArray(data.top_citing)?data.top_citing:[];
  const citingHTML=citing.length
    ? `<ul class="cv-ins-citing">${citing.map(x=>{
        const link=x.local?`<a href="#/corpus/${x.corpus_id}" class="cv-ins-citing-nm">${esc(x.name)}</a>`:`<span class="cv-ins-citing-nm cv-ins-citing-nm--remote">${esc(x.name)}</span>`;
        return `<li>${link}<span class="cv-ins-citing-n">${x.count}</span></li>`;
      }).join('')}</ul>`
    : '<div class="cv-ins-empty-sm">No incoming citations yet.</div>';
  const citingSection=`<div class="cv-ins-section"><div class="cv-ins-section-hd">Top citing KBs</div>${citingHTML}</div>`;

  const empty=(totalEvents===0&&reachAI===0)
    ? '<div class="cv-ins-empty-sm" style="margin-bottom:18px">No agent activity in this window yet. Share the corpus endpoint or <a href="#/compose" class="rp-subtle-link">connect it from another KB</a> to drive traffic.</div>'
    : '';

  document.getElementById('cv-ins-body').innerHTML=`${empty}<div class="cv-ins-cards">${kpiHTML}</div>${reachHTML}${funnelHTML}${citingSection}`;
}

/* ══════ SETTINGS TAB — Connect endpoints + Maintenance ══════ */
// Pulled out of the right sidebar so the sidebar can stay focused on live
// status (mini-graph, access, autonomy, trust, content). Connect is set-once
// config (copy the endpoint, wire up an agent, forget); Maintenance is
// infrequent / destructive. Full-width layout — no right panel.
async function renderCorpusSettings(id){
  stopAll();hideRP();
  const ct=document.getElementById('content');ct.classList.remove('content--corpus');
  let c=null;try{const r=await fetch(`${API}/corpora/${id}`);if(r.ok)c=await r.json()}catch(e){}
  if(!c){ct.innerHTML='<div class="empty" style="padding:48px;text-align:center">Corpus not found</div>';return}
  const al=c.access_level||'public';
  const badgeLabel=al==='token'?'Token-gated':al.charAt(0).toUpperCase()+al.slice(1);
  const tg=Array.isArray(c.tags)?c.tags:[];
  const host=location.origin;
  const endpoints=[
    {l:'MCP',u:`${host}/mcp`,d:'Primary agent endpoint — MCP-aware agents connect here.'},
    {l:'describe',u:`${host}/api/v1/corpora/${c.id}/describe`,d:'Capability card — what this KB is good at.'},
    {l:'ask',u:`${host}/api/v1/corpora/${c.id}/ask`,d:'Full query — returns a cited answer.'},
    {l:'preview_ask',u:`${host}/api/v1/corpora/${c.id}/preview_ask`,d:'Cheap dry-run — tests fit before a paid ask.'},
    {l:'search',u:`${host}/api/v1/corpora/${c.id}/search`,d:'Raw chunk search — lower-level than ask.'},
  ];
  // Plain-text views for any LLM/agent that just wants to read this corpus
  // in one fetch — paste the URL into ChatGPT / Claude / Cursor with no
  // adapter. Slug-based URLs (per llmstxt.org convention) read better when
  // shared. Hidden for private corpora since the URL would 403 anyway.
  // Token/paid gates work the same as other endpoints (caller adds bearer).
  if(al!=='private'){
    const llmsHint=(al==='token'||al==='paid')?' Requires a bearer token.':' Any LLM can fetch directly.';
    const slug=encodeURIComponent(c.slug||c.id);
    endpoints.push(
      {l:'llms.txt',u:`${host}/c/${slug}/llms.txt`,d:'Markdown index for AI agents (per llmstxt.org).'+llmsHint},
      {l:'llms-full.txt',u:`${host}/c/${slug}/llms-full.txt`,d:'Full-text dump — paste into any LLM to load the whole corpus as context.'+llmsHint},
    );
  }
  // Unified row pattern (Obsidian-style settings list): name + description on
  // the left, primary control on the right. Connect rows put the URL + Copy
  // on the right; Maintenance rows put a single action button on the right.
  const epRows=endpoints.map(e=>`<div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm cv-set-row-nm--mono">${esc(e.l)}</span><span class="cv-set-row-dc" title="${esc(e.d)}">${esc(e.d)}</span></div><div class="cv-set-row-ctl"><code class="cv-set-row-url" title="${esc(e.u)}">${esc(e.u)}</code><button class="btn-sm" onclick="cp('${e.u}',this)">Copy</button></div></div>`).join('');
  ct.innerHTML=`<div class="cv-layout cv-layout--full"><div class="cv-scroll"><div class="cv-header"><div class="cv-header-top"><a class="cv-back" href="#/corpora">&larr; Corpora</a></div><div class="cv-identity"><h1 class="cv-name">${esc(c.name)}</h1><span class="mc-badge mc-badge-${al}">${badgeLabel}</span></div>${c.description?`<p class="cv-desc">${esc(c.description)}</p>`:''}${tg.length?`<div class="cv-tags">${tg.map(t=>`<span class="mc-meta-tag">${esc(t)}</span>`).join('')}</div>`:''}</div>
    <div class="cv-tabs"><a href="#/corpus/${id}" class="cv-tab">Overview</a><a href="#/corpus/${id}/insights" class="cv-tab">Insights</a><a href="#/corpus/${id}/settings" class="cv-tab cv-tab--active">Settings</a></div>
    <div class="cv-set-wrap">
      <section class="cv-set-sec">
        <div class="cv-set-hd"><h2 class="cv-set-h2">Connect</h2><p class="cv-set-sub">Endpoints agents use to discover and query this KB.</p></div>
        <div class="cv-set-list">${epRows}</div>
      </section>
      <section class="cv-set-sec">
        <div class="cv-set-hd"><h2 class="cv-set-h2">Maintenance</h2><p class="cv-set-sub">Infrequent operations on this corpus.</p></div>
        <div class="cv-set-list">
          <div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Re-embed</span><span class="cv-set-row-dc" title="Rebuild all embeddings. Use this if a recent upload didn\u2019t become searchable.">Rebuild all embeddings. Use this if a recent upload didn\u2019t become searchable.</span></div><div class="cv-set-row-ctl"><button class="btn-sm" id="cv-set-reindex">Re-embed</button></div></div>
          <div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Export</span><span class="cv-set-row-dc" title="Download a JSON archive of this corpus (documents + metadata).">Download a JSON archive of this corpus (documents + metadata).</span></div><div class="cv-set-row-ctl"><button class="btn-sm" id="cv-set-export">Export</button></div></div>
          <div class="cv-set-row cv-set-row--danger"><div class="cv-set-row-info"><span class="cv-set-row-nm">Delete corpus</span><span class="cv-set-row-dc" title="Permanently delete this corpus and all its documents. Cannot be undone.">Permanently delete this corpus and all its documents. Cannot be undone.</span></div><div class="cv-set-row-ctl"><button class="btn-sm cv-set-btn-danger" id="cv-set-delete">Delete</button></div></div>
        </div>
      </section>
    </div>
    <div class="cv-scroll-end"></div></div></div>`;

  document.getElementById('cv-set-reindex').onclick=async(e)=>{
    e.preventDefault();
    const btn=e.currentTarget;const orig=btn.textContent;
    btn.textContent='Embedding\u2026';btn.disabled=true;
    try{
      const r=await fetch(`${API}/corpora/${c.id}/index`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:true})});
      if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.detail||'Failed')}
      const d=await r.json();
      toast(`Re-embedded ${d.embedded||0} chunks`,'success');
      btn.textContent=orig;btn.disabled=false;
    }catch(err){toast('Re-embed failed: '+err.message,'error');btn.textContent=orig;btn.disabled=false}
  };
  document.getElementById('cv-set-export').onclick=(e)=>{
    e.preventDefault();window.open(`${API}/corpora/${c.id}/export`,'_blank');
  };
  document.getElementById('cv-set-delete').onclick=async(e)=>{
    e.preventDefault();
    if(!confirm(`Delete "${c.name}" and all its documents? This cannot be undone.`))return;
    try{await fetch(`${API}/corpora/${c.id}`,{method:'DELETE'});await loadC();location.hash='#/corpora'}
    catch(err){toast('Delete failed: '+err.message,'error')}
  };
}

// ── Manifest identity card (agent-facing capability card) ──────────────
// Per-KB manifest fields live on the corpus row: task_types, samples,
// description, calibration_policy. LLM-refreshed via manifest_autofill on
// corpus creation; /describe endpoint serves them to discovery agents.
// Creator-facing: rendered as a pinned "manifest" doc at the top of the
// Wiki section (the KB's README.md). No hand-editable UI for task_types /
// samples — the fields auto-derive from content via backend auto-apply.

// Licensing defaults derived from access_level. Plain-English labels —
// every label names who pays and how much.
const LIC_DEFAULTS={
  public:'Free for any agent to query',
  token:'Free after you issue a token',
  paid:'Agents pay per query',
  private:'Not licensed — private'
};
const LIC_HINTS={
  public:'Any external agent can query this KB at no cost. By convention agents cite the KB when they use an answer, but nothing is enforced.',
  token:'Agents can only query after you hand them an access token. Queries are free once a token is granted — the token itself is the license.',
  paid:'Each query costs the agent the fee you set in Pricing below. Noosphere bills via Stripe Connect and routes 90% to you.',
  private:'This KB is not exposed to external agents at all. Licensing does not apply because nothing is licensed out.'
};

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

function showAddSubscriptionModal(c,onSaved){
  // Minimal Phase-1 subscribe flow: pick a local peer corpus, a mode, and a
  // cadence. Remote (network) peers + budget/token auth are Phase 2+.
  const wrap=document.createElement('div');wrap.className='acm-overlay';
  wrap.innerHTML=`<div class="acm-panel" style="max-width:520px">
    <div class="acm-title">Subscribe to a peer KB</div>
    <div class="acm-sub">Periodically poll another corpus and absorb its updates as new source documents (source_kind=peer_subscription).</div>
    <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
      <label style="font-size:11px;color:var(--tx3)">Peer corpus
        <select id="asm-peer" class="fi" style="width:100%;margin-top:4px"><option value="">Loading…</option></select>
      </label>
      <label style="font-size:11px;color:var(--tx3)">Mode
        <select id="asm-mode" class="fi" style="width:100%;margin-top:4px">
          <option value="new_documents">Pull new documents</option>
          <option value="ask">Ask a recurring question</option>
          <option value="describe">Refresh capability card</option>
        </select>
      </label>
      <label id="asm-query-wrap" style="font-size:11px;color:var(--tx3);display:none">Question to ask each cycle
        <input type="text" id="asm-query" class="fi" style="width:100%;margin-top:4px" placeholder="e.g. What's new in AI alignment this week?" />
      </label>
      <label id="asm-topic-wrap" style="font-size:11px;color:var(--tx3)">Topic filter (optional — matches title/tags)
        <input type="text" id="asm-topic" class="fi" style="width:100%;margin-top:4px" placeholder="e.g. embeddings" />
      </label>
      <label style="font-size:11px;color:var(--tx3)">Cadence
        <select id="asm-cadence" class="fi" style="width:100%;margin-top:4px">
          <option value="60">Every hour</option>
          <option value="360">Every 6 hours</option>
          <option value="1440" selected>Daily</option>
          <option value="10080">Weekly</option>
        </select>
      </label>
      <label style="font-size:11px;color:var(--tx3)">Max docs per cycle
        <input type="number" id="asm-maxdocs" class="fi" value="5" min="1" max="50" style="width:100%;margin-top:4px" />
      </label>
    </div>
    <div class="acm-actions" style="margin-top:14px"><button class="btn-sm-ghost" id="asm-cancel">Cancel</button><button class="btn-sm" id="asm-save">Subscribe</button></div>
  </div>`;
  document.body.appendChild(wrap);
  const close=()=>wrap.remove();
  wrap.querySelector('#asm-cancel').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});

  const modeSel=wrap.querySelector('#asm-mode');
  const queryWrap=wrap.querySelector('#asm-query-wrap');
  const topicWrap=wrap.querySelector('#asm-topic-wrap');
  const syncModeFields=()=>{
    const m=modeSel.value;
    queryWrap.style.display=m==='ask'?'':'none';
    topicWrap.style.display=m==='new_documents'?'':'none';
  };
  modeSel.onchange=syncModeFields;syncModeFields();

  (async()=>{
    const peerSel=wrap.querySelector('#asm-peer');
    try{
      const r=await fetch(`${API}/corpora`);
      const corpora=await r.json();
      const opts=(Array.isArray(corpora)?corpora:corpora.corpora||[]).filter(x=>x.id!==c.id);
      if(!opts.length){peerSel.innerHTML='<option value="">No other corpora available</option>';return}
      peerSel.innerHTML=opts.map(x=>`<option value="${esc(x.id)}" data-slug="${esc(x.slug||'')}">${esc(x.name||x.slug||x.id)}</option>`).join('');
    }catch(e){peerSel.innerHTML='<option value="">Failed to load</option>'}
  })();

  wrap.querySelector('#asm-save').onclick=async()=>{
    const btn=wrap.querySelector('#asm-save');
    const peerSel=wrap.querySelector('#asm-peer');
    const target_corpus_id=peerSel.value;
    if(!target_corpus_id){toast('Pick a peer corpus','error');return}
    const target_slug=peerSel.options[peerSel.selectedIndex]?.dataset.slug||'';
    const mode=modeSel.value;
    const payload={
      mode,
      target_corpus_id,
      target_slug,
      auth_mode:'public',
      cadence_minutes:parseInt(wrap.querySelector('#asm-cadence').value,10)||1440,
      max_docs_per_cycle:parseInt(wrap.querySelector('#asm-maxdocs').value,10)||5,
    };
    if(mode==='ask'){
      const q=wrap.querySelector('#asm-query').value.trim();
      if(!q){toast('Ask mode needs a question','error');return}
      payload.query=q;
    }
    if(mode==='new_documents'){
      const t=wrap.querySelector('#asm-topic').value.trim();
      if(t)payload.topic_filter=t;
    }
    btn.disabled=true;btn.textContent='Subscribing…';
    try{
      const r=await fetch(`${API}/corpora/${c.id}/subscriptions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const body=await r.json().catch(()=>({}));
      if(!r.ok){toast(body.detail||'Failed to subscribe','error');btn.disabled=false;btn.textContent='Subscribe';return}
      toast('Subscription created — will run on its cadence','success');
      close();
      if(typeof onSaved==='function')onSaved();
    }catch(e){toast('Failed: '+e.message,'error');btn.disabled=false;btn.textContent='Subscribe'}
  };
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
    ? `<div class="ep-compiled"><div class="ep-compiled-hd"><span class="ep-compiled-lbl">Compiled truth</span><button class="btn-sm-ghost" id="ep-recompile-btn">Recompile</button></div><div class="ep-compiled-body doc-bd-md" id="ep-compiled-body">${_mdToHtml(ent.description||'')}</div></div>`
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

// Source kind options shown on Sources rows. Mirrors the upload panels at
// app.js:2393 / 2435 so import-time and edit-time vocabularies stay in sync.
const SOURCE_KIND_OPTIONS=[
  {value:'user_original',label:'My original content'},
  {value:'external_public',label:'Public external reference'},
  {value:'external_subscription',label:'Subscription / paid external'},
];

function showDocInlineEdit(corpusId,item,doc){
  const existing=item.querySelector('.doc-bd');if(existing)existing.remove();
  item.classList.remove('expanded');item.classList.add('editing');
  const ed=document.createElement('div');ed.className='doc-edit-inline';
  const curSk=doc.source_kind||'user_original';
  const skOptions=SOURCE_KIND_OPTIONS.map(o=>`<option value="${o.value}"${o.value===curSk?' selected':''}>${esc(o.label)}</option>`).join('');
  // metadata.author/date are extracted at ingest from <meta> tags / file
  // frontmatter and are often wrong. Surface them as editable fields so users
  // can correct without delete-and-reingest.
  let curMeta={};
  try{curMeta=typeof doc.metadata_json==='string'?JSON.parse(doc.metadata_json||'{}'):(doc.metadata_json||{})}catch(e){curMeta={}}
  if(typeof curMeta!=='object'||curMeta===null)curMeta={};
  const curAuthor=curMeta.author||'';
  const curDate=doc.date||'';
  ed.innerHTML=`<input type="text" class="doc-edit-title" value="${esc(doc.title||'')}" placeholder="Title" /><textarea class="doc-edit-content" rows="8" placeholder="Content (Markdown supported)...">${esc(doc.content||'')}</textarea><div class="doc-edit-meta"><div class="doc-edit-meta-row"><label>Author</label><input type="text" class="doc-edit-author" value="${esc(curAuthor)}" placeholder="(none)" /></div><div class="doc-edit-meta-row"><label>Date</label><input type="text" class="doc-edit-date" value="${esc(curDate)}" placeholder="YYYY-MM-DD" /></div></div><div class="doc-edit-origin"><label for="doc-edit-sk-${doc.id}">Origin</label><select id="doc-edit-sk-${doc.id}" class="doc-edit-sk">${skOptions}</select></div><div class="doc-edit-actions"><button class="btn-sm-ghost doc-edit-cancel">Cancel</button><button class="btn-sm doc-edit-save">Save</button></div>`;
  ed.onclick=e=>e.stopPropagation();
  item.appendChild(ed);
  ed.querySelector('.doc-edit-title').focus();
  ed.querySelector('.doc-edit-cancel').onclick=()=>{ed.remove();item.classList.remove('editing')};
  ed.querySelector('.doc-edit-save').onclick=async()=>{
    const title=ed.querySelector('.doc-edit-title').value.trim();
    const content=ed.querySelector('.doc-edit-content').value.trim();
    const sk=ed.querySelector('.doc-edit-sk').value;
    const author=ed.querySelector('.doc-edit-author').value.trim();
    const date=ed.querySelector('.doc-edit-date').value.trim();
    if(!title){toast('Title is required');return}
    const btn=ed.querySelector('.doc-edit-save');btn.disabled=true;btn.textContent='Saving...';
    const body={};
    if(title!==doc.title)body.title=title;
    if(content!==doc.content)body.content=content;
    if(sk!==(doc.source_kind||'user_original'))body.source_kind=sk;
    if(date!==(doc.date||''))body.date=date;
    if(author!==curAuthor)body.metadata={author};
    if(!Object.keys(body).length){ed.remove();item.classList.remove('editing');return}
    try{
      const r=await fetch(`${API}/corpora/${corpusId}/documents/${doc.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok)throw new Error((await r.json()).detail||'Failed');
      if(body.content)ensureIndexed(corpusId);
      // Surgical refresh — rebuild only THIS row's header from the freshly
      // saved doc so other inline editors on the page stay open. Falling
      // back to a full renderCorpus() (the previous behavior) wiped any
      // sibling editor in mid-edit.
      const fresh=await fetch(`${API}/corpora/${corpusId}/documents/${doc.id}`).then(rr=>rr.json()).catch(()=>null);
      ed.remove();item.classList.remove('editing');
      if(fresh)refreshDocItemRow(item,fresh);
    }catch(e){toast('Save failed: '+e.message);btn.disabled=false;btn.textContent='Save'}
  };
}

// Patch the visible parts of a .doc-item header in place. Called after a save
// so the row reflects the new title/word-count/source-kind without re-rendering
// the whole corpus page (which would blow away any other open inline editors).
function refreshDocItemRow(item,doc){
  const titleEl=item.querySelector('.doc-tt');
  if(titleEl)titleEl.textContent=doc.title||'';
  const skEl=item.querySelector('.doc-sk');
  if(skEl){
    const sk=doc.source_kind||'user_original';
    skEl.className='doc-sk sk-'+sk;
    skEl.textContent=sk.replace('_',' ');
  }
  const metaEl=item.querySelector('.doc-mt');
  if(metaEl){
    const wc=doc.word_count||0;
    const wlab=wc.toLocaleString()+' word'+(wc===1?'':'s');
    // Preserve the source-kind pill node we just patched; only swap the
    // word-count + date prefix that lives before it.
    const skNode=skEl?skEl.cloneNode(true):null;
    metaEl.innerHTML=wlab+(doc.date?' · '+doc.date:'')+' · ';
    if(skNode)metaEl.appendChild(skNode);
  }
}

function appendAssistantChatBlock(area,text,citations,corpusId,userQuestion,sessionId,autoCap){
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
  // Chat-to-enrich is automatic: the backend detects wiki-worthy knowledge in
  // the exchange and folds it in on its own. We only surface a quiet
  // confirmation (with Undo, so an unwanted auto-write is one click to remove).
  // Nothing is shown when nothing was saved — no manual "save" affordance.
  if(autoCap&&autoCap.saved&&autoCap.document_id){
    const note=document.createElement('div');
    note.className='chat-autosave';
    const chk='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    const ttl=autoCap.title?` · ${esc(autoCap.title)}`:'';
    note.innerHTML=`<span class="chat-autosave-lbl">${chk}Added to your wiki${ttl}</span><button type="button" class="chat-autosave-undo">Undo</button>`;
    note.querySelector('.chat-autosave-undo').onclick=async(e)=>{
      const b=e.currentTarget;b.disabled=true;
      try{
        const r=await fetch(`${API}/corpora/${corpusId}/documents/${autoCap.document_id}`,{method:'DELETE'});
        if(!r.ok)throw new Error('undo failed');
        note.innerHTML='<span class="chat-autosave-lbl chat-autosave-undone">Removed from your wiki</span>';
      }catch(err){b.disabled=false;toast('Undo failed','error')}
    };
    outer.appendChild(note);
  }
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
      appendAssistantChatBlock(area,d.response,d.citations||[],id,msg,_sessionId,d.auto_capture)}
    catch(e){document.getElementById('c-ld')?.remove();area.innerHTML+=`<div class="chat-msg assistant">${noosHd()}<div class="chat-err">${esc(e.message||'Failed to reach LLM provider.')}</div></div>`}send.disabled=false;area.scrollTop=area.scrollHeight}
  send.onclick=chat;ci.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chat()}};
}

// Access-level descriptions — describe WHO can query, not discovery. The
// Discovery row below handles registry visibility separately, so don't
// reuse "discoverable" here (it confused users into thinking access mode
// and registry status were the same thing).
const ACC_MSG={public:'Any agent can query this KB.',private:'Only you can query this KB from your endpoint.',token:'Requires an access token to query.',paid:'Agents pay per query or subscribe. Set pricing below.'};

/* Reputation formula explainer modal. Weights match KBR_WEIGHTS in
   noosphere/core/citations.py — keep in sync if the formula changes. */
function showKbrFormulaModal(corpusId,currentScore){
  const terms=[
    {w:0.4,name:'Citation PageRank',dc:'How often other KBs cite this one, weighted by the citing KB\u2019s own score. Canonical cross-KB authority signal.'},
    {w:0.3,name:'Query retention',dc:'Fraction of external agents that return to query this KB again within 30 days. Proxy for answer usefulness.'},
    {w:0.2,name:'Calibration accuracy',dc:'Agreement between the confidence this KB reports and observed answer correctness. Currently stubbed at 0.5 while feedback data accumulates.'},
    {w:0.1,name:'Satisfaction rate',dc:'Thumbs-up / thumbs-down feedback on ask responses.'},
  ];
  const rowsHTML=terms.map(t=>`<div class="kbr-f-row"><div class="kbr-f-w">${(t.w*100|0)}%</div><div class="kbr-f-body"><div class="kbr-f-nm">${esc(t.name)}</div><div class="kbr-f-dc">${esc(t.dc)}</div></div></div>`).join('');
  const wrap=document.createElement('div');wrap.className='acm-overlay';
  wrap.innerHTML=`<div class="acm-panel" style="max-width:520px"><div class="acm-title">How Reputation is computed</div><div class="acm-sub">Current score: <strong>${currentScore.toFixed(2)}</strong>. Reputation is a weighted blend of four signals agents use to weigh this KB against others.</div><div class="kbr-f-list">${rowsHTML}</div><div class="kbr-f-formula"><code>KBR = 0.4·citation + 0.3·retention + 0.2·calibration + 0.1·satisfaction</code></div><div class="acm-expl">All four terms range 0–1. The weighted sum is recomputed on each inbound query and cached in the corpus row.</div><div class="acm-actions"><button class="btn-sm" id="kbr-f-close">Got it</button></div></div>`;
  document.body.appendChild(wrap);
  const close=()=>wrap.remove();
  wrap.querySelector('#kbr-f-close').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
}

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

/* ══════ MINI NETWORK (right-sidebar widget) ══════
   Static snapshot of this corpus + 1-hop tag neighbors. Rendered once
   after d3 force settles — no animation loop. "Own" corpora (same owner)
   render solid; external neighbors render dashed + dimmer. Orphan state:
   lone center node with an inline hint. Click anywhere → showLocalGraphModal. */
let _miniNetworkCache=null;
async function _fetchCorpusNetwork(){
  if(_miniNetworkCache)return _miniNetworkCache;
  try{
    const r=await fetch(`${API}/corpora/network`);
    if(r.ok){_miniNetworkCache=await r.json();return _miniNetworkCache}
  }catch(e){}
  return {nodes:[],links:[]};
}
function _invalidateNetworkCache(){_miniNetworkCache=null}
function _ownIdSet(){return new Set((_corpora||[]).map(x=>x.id))}
async function drawMiniNetwork(c){
  const cv=document.getElementById('rp-mini-cv');
  const emptyEl=document.getElementById('rp-mini-empty');
  if(!cv)return;
  cv._nodes=[]; // hit-test target for click/hover
  const net=await _fetchCorpusNetwork();
  const byId=new Map(net.nodes.map(n=>[n.id,n]));
  const center=byId.get(c.id);
  // Tag-aware empty-state copy. Users confused by "add tags" — make it
  // explicit that tags are the mechanism and self-referential ("this corpus").
  const hasTags=Array.isArray(c.tags)?c.tags.length>0:false;
  const emptyCopy=hasTags
    ? 'No other corpora share these tags yet.'
    : 'Tag this corpus to find similar ones in the network.';
  if(emptyEl)emptyEl.textContent=emptyCopy;
  if(!center){if(emptyEl)emptyEl.classList.remove('hidden');return}
  const neighIds=new Set();
  for(const l of (net.links||[])){
    const s=typeof l.source==='object'?l.source.id:l.source;
    const t=typeof l.target==='object'?l.target.id:l.target;
    if(s===c.id)neighIds.add(t);else if(t===c.id)neighIds.add(s);
  }
  if(neighIds.size===0){
    const W=cv.parentElement.clientWidth,H=cv.parentElement.clientHeight;
    const dp=devicePixelRatio||1;cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';
    const cx=cv.getContext('2d');cx.scale(dp,dp);
    const[cr,cg,cb]=hR(_nodeColor(center));
    cx.beginPath();cx.arc(W/2,H/2,14,0,Math.PI*2);cx.fillStyle=`rgba(${cr},${cg},${cb},.9)`;cx.fill();
    cx.strokeStyle='rgba(255,255,255,.3)';cx.lineWidth=1.5;cx.stroke();
    cx.fillStyle='rgba(255,255,255,.95)';cx.font='700 10px Inter,sans-serif';cx.textAlign='center';cx.textBaseline='middle';
    cx.fillText((center.initials||center.name[0]||'?').slice(0,2),W/2,H/2);
    cv._nodes=[{x:W/2,y:H/2,r:14,id:c.id,name:center.name,isCenter:true}];
    if(emptyEl)emptyEl.classList.remove('hidden');
    return;
  }
  if(emptyEl)emptyEl.classList.add('hidden');
  const ownIds=_ownIdSet();
  const nodes=[center,...[...neighIds].map(id=>byId.get(id)).filter(Boolean)].map(n=>({...n,isCenter:n.id===c.id,isOwn:ownIds.has(n.id)}));
  const links=(net.links||[]).filter(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;
    const t=typeof l.target==='object'?l.target.id:l.target;
    return (s===c.id&&neighIds.has(t))||(t===c.id&&neighIds.has(s));
  }).map(l=>({source:typeof l.source==='object'?l.source.id:l.source,target:typeof l.target==='object'?l.target.id:l.target,s:l.strength||1}));
  const W=cv.parentElement.clientWidth,H=cv.parentElement.clientHeight;
  const dp=devicePixelRatio||1;cv.width=W*dp;cv.height=H*dp;cv.style.width=W+'px';cv.style.height=H+'px';
  const cx=cv.getContext('2d');cx.scale(dp,dp);
  const centerNode=nodes.find(n=>n.isCenter);if(centerNode){centerNode.fx=W/2;centerNode.fy=H/2}
  const sim=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(d=>d.id).distance(46).strength(.5)).force('charge',d3.forceManyBody().strength(-120)).force('center',d3.forceCenter(W/2,H/2).strength(.05)).force('collide',d3.forceCollide().radius(14)).stop();
  for(let i=0;i<120;i++)sim.tick();
  for(const n of nodes){n.x=Math.max(12,Math.min(W-12,n.x));n.y=Math.max(12,Math.min(H-12,n.y))}
  for(const l of links){
    const s=nodes.find(n=>n.id===(typeof l.source==='object'?l.source.id:l.source));
    const t=nodes.find(n=>n.id===(typeof l.target==='object'?l.target.id:l.target));
    if(!s||!t)continue;
    cx.beginPath();cx.moveTo(s.x,s.y);cx.lineTo(t.x,t.y);
    cx.strokeStyle=`rgba(140,155,180,${.18+Math.min(l.s,5)*.08})`;cx.lineWidth=.8+Math.min(l.s,5)*.3;cx.stroke();
  }
  for(const n of nodes){
    const r=n.isCenter?11:7;
    n.r=r;
    const[cr,cg,cb]=hR(_nodeColor(n));
    // Same uniform-stroke + alpha-by-ownership style as the LP background:
    // external (other-owner) nodes fade to .55 alpha, own nodes stay full,
    // center node gets a slightly brighter ring.
    const alpha=n.isOwn?(n.isCenter?1:.85):.55;
    cx.beginPath();cx.arc(n.x,n.y,r,0,Math.PI*2);
    cx.fillStyle=`rgba(${cr},${cg},${cb},${alpha})`;cx.fill();
    cx.strokeStyle=n.isCenter?'rgba(255,255,255,.5)':'rgba(255,255,255,.25)';
    cx.lineWidth=n.isCenter?2:1;cx.stroke();
    if(n.isCenter){
      cx.fillStyle='rgba(255,255,255,.95)';cx.font='700 9px Inter,sans-serif';cx.textAlign='center';cx.textBaseline='middle';
      cx.fillText((n.initials||n.name[0]||'?').slice(0,2),n.x,n.y);
    }
  }
  cv._nodes=nodes.map(n=>({x:n.x,y:n.y,r:n.r,id:n.id,name:n.name,isCenter:n.isCenter,isOwn:n.isOwn}));
}

/* ══════ LOCAL GRAPH MODAL (expand-from-sidebar) ══════
   Full-screen overlay with an interactive graph centered on the current
   corpus + its 1-hop tag neighbors. Reuses drawGraphIn for consistency
   with the global Explore view. Close via × or Esc. */
async function showLocalGraphModal(c){
  const existing=document.getElementById('lgm-overlay');if(existing)existing.remove();
  const net=await _fetchCorpusNetwork();
  const byId=new Map(net.nodes.map(n=>[n.id,n]));
  const center=byId.get(c.id);
  const neighIds=new Set();
  if(center){
    for(const l of (net.links||[])){
      const s=typeof l.source==='object'?l.source.id:l.source;
      const t=typeof l.target==='object'?l.target.id:l.target;
      if(s===c.id)neighIds.add(t);else if(t===c.id)neighIds.add(s);
    }
  }
  const hood=center?[center,...[...neighIds].map(id=>byId.get(id)).filter(Boolean)]:[];
  const wrap=document.createElement('div');wrap.id='lgm-overlay';wrap.className='lgm-overlay';
  const count=hood.length;
  // Tag-aware subtitle — same logic as the sidebar mini-graph. Avoids the
  // ambiguous "add tags" phrasing when the user has tags already but none
  // overlap with other corpora's tags.
  const hasTags=Array.isArray(c.tags)?c.tags.length>0:false;
  const subtitle=count>1
    ? (count-1)+(count===2?' neighbor':' neighbors')
    : (hasTags?'No other corpora share these tags yet.':'Tag this corpus to find similar ones in the network.');
  wrap.innerHTML=`<div class="lgm-panel"><div class="lgm-hd"><div class="lgm-ti"><span class="lgm-t1">${esc(c.name)}</span><span class="lgm-t2">${subtitle}</span></div><button class="lgm-cc" id="lgm-cc" title="Close">×</button></div><div class="nv-wrap lgm-canvas-wrap"><canvas id="lgm-cv" class="nv-canvas"></canvas><div class="nv-tt hidden" id="nv-tt"></div></div><div class="lgm-ft"><span class="lgm-ft-lbl">Color per corpus · line weight = shared tags · private nodes stay locked</span></div></div>`;
  document.body.appendChild(wrap);
  // Close via ×, Esc, backdrop click, OR route change. The route-change
  // close matters because drawGraphIn's node click handler navigates via
  // location.hash — without this listener the modal would stay on top of
  // the newly-loaded corpus page.
  const close=()=>{if(_gAnim){cancelAnimationFrame(_gAnim);_gAnim=null}wrap.remove();document.removeEventListener('keydown',escH);window.removeEventListener('hashchange',close)};
  const escH=e=>{if(e.key==='Escape')close()};
  document.addEventListener('keydown',escH);
  window.addEventListener('hashchange',close);
  wrap.querySelector('#lgm-cc').onclick=close;
  wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
  // Even the orphan case (just the center) gets a visible node — an empty
  // canvas with only a "no neighbors" subtitle made the modal feel broken.
  // drawGraphIn handles single-corpus input: no edges, just one bubble.
  if(hood.length>=1){
    const ownIds=_ownIdSet();
    const corporaShape=hood.map(n=>({
      id:n.id,name:n.name,slug:n.slug||'',description:n.description||'',
      tags:n.tags||[],document_count:n.document_count||0,
      access_level:n.access_level||'public',author_name:n.author||'',
      _isOwn:ownIds.has(n.id),_isCenter:n.id===c.id,
    }));
    const cv=wrap.querySelector('#lgm-cv');
    const container=wrap.querySelector('.lgm-canvas-wrap');
    setTimeout(()=>drawGraphIn(container,corporaShape,cv),0);
  }
}

async function showRP(c,an){const rp=document.getElementById('rpanel');rp.classList.remove('hidden');const host=location.origin;const al=c.access_level||'public';
  // Pull capability describe once — Autonomy stage, Reputation, Content mix
  // all live here (creator-facing controls + derived metrics). If /describe
  // fails we still render the panel; capability-specific rows empty-state.
  let cap=null;try{const dr=await fetch(`${API}/corpora/${c.id}/describe`);if(dr.ok)cap=await dr.json()}catch(e){}
  const showProUI=shouldShowProUI();
  const userTier=_authUser?(_authUser.user_metadata?.tier||'free'):'free';
  const isProUser=_cloudMode?(userTier==='pro'):true;
  // Autonomy — three tiers listed equally. Networking is the substrate
  // (every corpus is reachable in the network by default); autonomy is the
  // dial — how much of the network the corpus consumes and acts on without
  // prompting. No "current stage" highlight (it was reading as a tier ladder).
  // Access model:
  //   Self-hosted (!_cloudMode):      all three available (user brings own API key)
  //   Cloud Pro:                      all three available, no badges
  //   Cloud Free:                     Static free; Living + Fully Autonomous
  //                                   show a clickable Upgrade badge that opens
  //                                   the paywall modal
  const stages=[
    {key:'static',     label:'Static',           desc:'Manual sources · manual compile. Answers queries on demand.',                                                                                pro:false},
    {key:'living',     label:'Living',           desc:'Auto-ingests from connected feeds and keeps compiled Wiki, entities, and timelines in sync as sources change.',                              pro:true},
    {key:'autonomous', label:'Fully Autonomous', desc:'Actively discovers peer corpora across the network, subscribes to and pays for them within owner-set policy, and grows knowledge over time.', pro:true},
  ];
  const autonomyHTML=stages.map(s=>{
    let badge='';
    if(showProUI && s.pro && !isProUser){
      // Cloud Free — clickable upgrade pill. Cloud Pro sees no badge
      // (they already have access). Self-hosted sees no badge at all.
      badge=`<button type="button" class="rp-auto-tag rp-auto-tag--pro rp-auto-tag--link" data-pro-upsell="${esc(s.label)} autonomy is a Pro feature">Upgrade</button>`;
    }
    return `<div class="rp-stage"><div class="rp-stage-hd"><span class="rp-stage-nm">${s.label}</span>${badge}</div><div class="rp-stage-dc">${s.desc}</div></div>`;
  }).join('');

  const kbr=cap?Number(cap.kb_reputation||0):0;
  const kbrTier=kbr>=0.5?'high':kbr>=0.2?'mid':'low';
  // Fold Confidence into the Reputation row — a single trust line.
  // Possible suffixes: "calibrated" (third-party), "self-assessed", or "no
  // confidence reported". Calibration policy is low-churn; a separate row
  // was overkill.
  const calib=cap&&cap.calibration_policy;
  let confSuffix='no confidence reported',confHint='This KB does not report confidence scores on its answers.';
  if(calib&&typeof calib==='object'&&calib.reports_confidence){
    if((calib.confidence_source||'self')==='self'){
      confSuffix='self-assessed';confHint='This KB reports its own confidence — weaker signal than third-party calibration.';
    }else{
      confSuffix='calibrated';confHint='Confidence scores verified by an external calibrator — stronger trust signal.';
    }
  }
  // Content mix — now also carries the doc count (absorbs the old Stats section).
  const sc=(cap&&cap.source_composition)||{};
  const scEntries=Object.entries(sc).filter(([k,v])=>v>0).sort((a,b)=>b[1]-a[1]);
  const docCount=c.document_count||0;
  const mixHTML=scEntries.length
    ? `<div class="rp-mix-bar">${scEntries.map(([k,v])=>{const cls=k==='user_original'?'orig':k==='user_capture'?'cap':'ext';return `<div class="rp-mix-seg rp-mix-seg--${cls}" style="width:${(v*100).toFixed(1)}%" title="${esc(k)}: ${(v*100).toFixed(0)}%"></div>`}).join('')}</div><div class="rp-mix-leg">${scEntries.map(([k,v])=>`<span>${esc(k.replace(/_/g,' '))} ${(v*100).toFixed(0)}%</span>`).join('')}</div>`
    : '<span class="rp-sub-empty">no docs yet</span>';
  const licStr=LIC_DEFAULTS[al]||LIC_DEFAULTS.public;
  const licHint=LIC_HINTS[al]||LIC_HINTS.public;
  // Registry status — self-hosted and cloud nodes share the SAME Noosphere
  // network. Default config (NOOSPHERE_REGISTRY env var) points every node
  // to the shared registry automatically; opt-out via NOOSPHERE_REGISTRY=none.
  // So there's no "cloud-only" vs "self-hosted" distinction here — only
  // whether this node is participating in the shared discovery network.
  //   Private                              → "Private — not registered"
  //   Registration succeeded                → "Registered · discoverable"
  //   Registry reachable but POST rejected  → "Registry unreachable" (with reason)
  //   Registry unreachable                  → "Registering… (retrying)"
  //   Explicit opt-out (=none)              → "Standalone — not registered"
  //
  // registry_registration_ok is the authoritative signal — set by
  // register_with_registry() based on the real HTTP 200/201 from the
  // registry. registry_connected is a weaker probe (HEAD to root) that
  // can succeed while the POST is blocked by auth / middleware.
  let regStatus='',regHint='';
  if(al==='private'){
    regStatus='Private — not registered';
    regHint='Private corpora never publish to the discovery registry.';
  }else{
    let registrationOk=false,registryConnected=false,registryConfigured=false,isRegistry=false;
    try{const hr=await fetch(`${API}/health`);const h=await hr.json();registrationOk=!!h.registry_registration_ok;registryConnected=!!h.registry_connected;registryConfigured=!!h.registry_configured;isRegistry=!!h.is_registry}catch(e){}
    if(isRegistry){
      // This node IS the shared registry (e.g. noosphere.wiki). Corpora
      // live directly on the discovery DB, so they're already discoverable
      // without any outbound register step. The older "Standalone — not
      // registered" copy was technically true but actively misleading.
      regStatus='Live on registry · discoverable';
      regHint='This node is the shared Noosphere registry itself. The corpus is already in the discovery index — any agent on the network can find and query it.';
    }else if(registrationOk){
      regStatus='Registered · discoverable';
      regHint='This KB is listed in the shared Noosphere registry — any agent on the network can discover and query it.';
    }else if(!registryConfigured){
      regStatus='Standalone — not registered';
      regHint='This node has opted out of the shared Noosphere registry (NOOSPHERE_REGISTRY=none). Agents with the direct endpoint URL can still query this KB, but it won\u2019t show up in network-wide discovery.';
    }else if(registryConnected){
      // Registry is up, but we haven't successfully registered. Most
      // common cause is an auth/middleware 401 on POST — the earlier
      // check missed it because HEAD is allowed anonymously.
      regStatus='Registry reachable, registration pending';
      regHint='The Noosphere registry is up, but this node hasn\u2019t successfully registered yet. Registration runs on serve startup and after corpus changes; check the server logs for errors (auth, rate limits, or payload issues).';
    }else{
      regStatus='Registering… (retrying)';
      regHint='The Noosphere registry isn\u2019t reachable right now. This KB will register automatically once the connection comes back. Agents with the direct endpoint URL can still query now.';
    }
  }

  // Right-rail — status & identity only. Config (Connect endpoints) and
  // destructive ops (Maintenance) live in the Settings tab. Keeping here:
  //   Network  — mini-graph of this corpus + 1-hop tag neighbors (click to expand)
  //   Access   — who can query + licensing + discovery + tokens/pricing/revenue
  //   Autonomy — capability stages + subscriptions
  //   Trust    — KBR + calibration suffix
  //   Content  — doc count + source mix + entities
  rp.innerHTML=`<div class="rp-sec rp-sec-first"><div class="rp-lbl"><span>Network</span><a href="#" class="rp-mini-expand" id="rp-mini-expand" title="Expand">Expand</a></div><div class="rp-mini-wrap" id="rp-mini-wrap"><canvas class="rp-mini-cv" id="rp-mini-cv"></canvas><div class="rp-mini-empty hidden" id="rp-mini-empty">Add tags to connect with the network.</div></div></div>
    <div class="rp-sec"><div class="rp-lbl">Access</div><div class="rp-row"><select id="rp-acc"><option value="public" ${al==='public'?'selected':''}>Public</option><option value="private" ${al==='private'?'selected':''}>Private</option><option value="token" ${al==='token'?'selected':''}>Token-gated</option><option value="paid" ${al==='paid'?'selected':''}>Paid</option></select><button class="btn-sm" id="rp-sv" disabled>Save</button></div><div class="rp-msg info" id="rp-msg">${ACC_MSG[al]||''}</div><div class="rp-sub"><span class="rp-sub-lbl">Discovery</span><div class="rp-sub-val" id="rp-discovery" title="${esc(regHint)}">${esc(regStatus)}</div></div><div class="rp-sub"><span class="rp-sub-lbl">Licensing</span><div class="rp-sub-val" id="rp-licensing" title="${esc(licHint)}">${esc(licStr)}</div></div><div id="rp-tokens" class="rp-sub rp-sub--block" style="display:${al==='token'?'block':'none'}"><span class="rp-sub-lbl">Access tokens</span><div class="rp-sub-val"><button class="btn-sm" id="rp-gen-tk" style="margin-bottom:8px">+ Generate token</button><div id="rp-tk-list"></div></div></div><div id="rp-pricing" class="rp-sub rp-sub--block" style="display:${al==='paid'?'block':'none'}"><span class="rp-sub-lbl">Pricing</span><div class="rp-sub-val" id="rp-pricing-body"></div></div><div id="rp-revenue" class="rp-sub rp-sub--block" style="display:${al==='paid'?'block':'none'}"><span class="rp-sub-lbl">Revenue</span><div class="rp-sub-val" id="rp-revenue-body" style="font-size:12px;color:var(--tx3)">Loading…</div></div></div>
    <div class="rp-sec"><div class="rp-lbl" title="What this KB can do on its own.">Autonomy</div><div class="rp-stages">${autonomyHTML}</div><div class="rp-sub rp-sub--block"><div class="rp-sub-hd"><span class="rp-sub-lbl">Subscriptions <span class="rp-sub-cnt" id="rp-subs-count">(0)</span></span><button class="btn-xs" id="rp-subs-add" title="Subscribe to a peer KB">+ Add</button></div><div class="rp-subs-list" id="rp-subs-list"><span class="rp-sub-empty">Loading…</span></div></div></div>
    <div class="rp-sec"><div class="rp-lbl" title="Signals external agents use to weigh this KB's answers against others.">Trust</div><div class="rp-sub"><span class="rp-sub-lbl">Reputation <a href="#" class="rp-info-icon" id="rp-kbr-info" title="How is this computed?" aria-label="How is Reputation computed">&#9432;</a></span><div class="rp-sub-val rp-kbr rp-kbr--${kbrTier}" title="${esc(confHint)}">${kbr.toFixed(2)} <span class="rp-kbr-tier">${kbrTier}</span> <span class="rp-kbr-conf">· ${esc(confSuffix)}</span></div></div></div>
    <div class="rp-sec"><div class="rp-lbl" title="What's inside this KB — count, source mix, and extracted entities.">Content</div><div class="rp-sub"><span class="rp-sub-lbl">Documents</span><div class="rp-sub-val"><strong>${fmtN(docCount)}</strong> ${docCount===1?'doc':'docs'}</div></div><div class="rp-sub"><span class="rp-sub-lbl">Mix</span><div class="rp-sub-val">${mixHTML}</div></div></div>`;
  drawMiniNetwork(c);

  // Dirty-state tracking for the Save button. Without this the button
  // looked permanently "ready to save" even when the select still matched
  // the persisted value — clicking did nothing visible (just a "No change"
  // toast), so users assumed save was broken. The button now reflects
  // whether there's actually anything to commit.
  const _curAl=c.access_level||'public';
  const _saveBtn=document.getElementById('rp-sv');
  const _refreshSaveState=()=>{
    const v=document.getElementById('rp-acc').value;
    _saveBtn.disabled=(v===_curAl);
  };
  document.getElementById('rp-acc').onchange=()=>{
    const v=document.getElementById('rp-acc').value;
    document.getElementById('rp-msg').textContent=ACC_MSG[v]||'';
    document.getElementById('rp-tokens').style.display=v==='token'?'block':'none';
    document.getElementById('rp-pricing').style.display=v==='paid'?'block':'none';
    document.getElementById('rp-revenue').style.display=v==='paid'?'block':'none';
    // Keep licensing + discovery previews in sync so users see the effect
    // before they commit with Save.
    const licEl=document.getElementById('rp-licensing');
    if(licEl){
      licEl.textContent=LIC_DEFAULTS[v]||LIC_DEFAULTS.public;
      licEl.title=LIC_HINTS[v]||LIC_HINTS.public;
    }
    const discEl=document.getElementById('rp-discovery');
    if(discEl)discEl.textContent=v==='private'?'Private — not registered':'Will register in Noosphere registry after Save';
    if(v==='paid')loadPricingUI(c);
    _refreshSaveState();
  };
  _saveBtn.onclick=async()=>{
    const newAl=document.getElementById('rp-acc').value;
    const curAl=_curAl;
    // Belt-and-braces — button should already be disabled in this case,
    // but guard anyway in case something bypasses onchange.
    if(newAl===curAl){return}
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
    // Visual feedback during the PATCH — without this the click felt
    // inert on slow connections and users would mash the button.
    const _origLabel=_saveBtn.textContent;
    _saveBtn.disabled=true;_saveBtn.textContent='Saving…';
    try{
      const r=await fetch(`${API}/corpora/${c.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_level:newAl})});
      if(!r.ok){const d=await r.json().catch(()=>({}));toast(d.detail||'Failed to update access','error');_saveBtn.textContent=_origLabel;_refreshSaveState();return}
      // renderCorpus() rebuilds this whole panel from the freshly loaded
      // corpus, so the new disabled-by-default Save button takes over.
      // No need to restore label/state on this branch.
      toast('Access saved');
      await loadC();renderCorpusSafe(c.id);
    }catch(e){toast('Failed: '+e.message,'error');_saveBtn.textContent=_origLabel;_refreshSaveState()}
  };

  /* Reputation formula explainer — the score is a weighted blend; users kept
     asking "what goes into this?", so surface the full formula + each term's
     current value on demand. Values are the same ones the backend feeds into
     compute_kb_reputation() in core/citations.py. */
  const kbrInfoBtn=document.getElementById('rp-kbr-info');
  if(kbrInfoBtn)kbrInfoBtn.onclick=(e)=>{
    e.preventDefault();
    showKbrFormulaModal(c.id,kbr);
  };

  /* Pro badge clicks → open upgrade modal, not a page nav. Matches the
     self-hosted paywall pattern (Feynman-style): stay in flow, modal
     communicates value without yanking the user off the corpus page. */
  rp.querySelectorAll('[data-pro-upsell]').forEach(btn=>{
    btn.onclick=(e)=>{e.preventDefault();e.stopPropagation();showProModal(btn.dataset.proUpsell||'')};
  });

  /* Subscriptions — part of the Fully Autonomous tier (peer corpus
     subscription + active discovery + autonomous payment). Pulls the current
     list; inline row per peer with status dot + cadence + revoke. "+ Add"
     opens a modal that lets the owner pick a peer corpus (local only in
     Phase 1), a mode, and a cadence. */
  async function loadSubs(){
    const list=document.getElementById('rp-subs-list');
    const cnt=document.getElementById('rp-subs-count');
    if(!list)return;
    try{
      const r=await fetch(`${API}/corpora/${c.id}/subscriptions`);
      if(!r.ok){list.innerHTML='<span class="rp-sub-empty">Unavailable</span>';return}
      const d=await r.json();const subs=d.subscriptions||[];
      if(cnt)cnt.textContent=`(${subs.length})`;
      if(!subs.length){list.innerHTML='<span class="rp-sub-empty">None yet — subscribe to absorb updates from a peer KB.</span>';return}
      list.innerHTML=subs.map(s=>{
        const name=esc(s.target_slug||s.target_endpoint||s.target_corpus_id||'peer');
        const mode=esc(s.mode||'');
        const cad=Number(s.cadence_minutes||0);
        const cadTxt=cad>=10080?`${Math.round(cad/10080)}w`:cad>=1440?`${Math.round(cad/1440)}d`:`${cad}m`;
        const status=s.status||'active';
        return `<div class="rp-sub-row" data-sub-id="${esc(s.id)}"><span class="rp-sub-dot rp-sub-dot--${status}" title="${esc(status)}"></span><span class="rp-sub-peer">${name}</span><span class="rp-sub-meta">${mode} · ${cadTxt}</span><button class="rp-sub-act" data-sub-run="${esc(s.id)}" title="Run now">▶</button><button class="rp-sub-act rp-sub-act--rm" data-sub-rm="${esc(s.id)}" title="Revoke">×</button></div>`;
      }).join('');
      list.querySelectorAll('[data-sub-run]').forEach(b=>{
        b.onclick=async(ev)=>{
          ev.preventDefault();
          const id=b.dataset.subRun;b.disabled=true;b.textContent='…';
          try{
            const rr=await fetch(`${API}/corpora/${c.id}/subscriptions/${id}/run`,{method:'POST'});
            const body=await rr.json().catch(()=>({}));
            if(!rr.ok){toast(body.detail||'Run failed','error');b.disabled=false;b.textContent='▶';return}
            const ing=body.docs_ingested||0;
            toast(ing?`Ingested ${ing} doc${ing===1?'':'s'} (${body.outcome})`:`No new content (${body.outcome})`,ing?'success':'info');
            loadSubs();if(ing)renderCorpusSafe(c.id);
          }catch(e){toast('Run failed: '+e.message,'error');b.disabled=false;b.textContent='▶'}
        };
      });
      list.querySelectorAll('[data-sub-rm]').forEach(b=>{
        b.onclick=async(ev)=>{
          ev.preventDefault();
          if(!confirm('Revoke this subscription? Its run history will be deleted too.'))return;
          const id=b.dataset.subRm;
          try{
            const rr=await fetch(`${API}/corpora/${c.id}/subscriptions/${id}`,{method:'DELETE'});
            if(!rr.ok){toast('Revoke failed','error');return}
            toast('Subscription revoked','success');loadSubs();
          }catch(e){toast('Revoke failed: '+e.message,'error')}
        };
      });
    }catch(e){list.innerHTML='<span class="rp-sub-empty">Failed to load</span>'}
  }
  document.getElementById('rp-subs-add').onclick=(e)=>{e.preventDefault();showAddSubscriptionModal(c,loadSubs)};
  loadSubs();

  /* Mini-graph interactions:
     - Expand link → always open the local-graph modal
     - Wrap hover → pointer cursor over a neighbor node; default cursor otherwise
     - Wrap click → hit-test: neighbor node → navigate; center or miss → modal */
  const miniExpand=document.getElementById('rp-mini-expand');
  const miniWrap=document.getElementById('rp-mini-wrap');
  const miniCv=document.getElementById('rp-mini-cv');
  const hitTest=(ev)=>{
    const nodes=miniCv&&miniCv._nodes?miniCv._nodes:[];
    if(!nodes.length)return null;
    const r=miniCv.getBoundingClientRect();
    const x=ev.clientX-r.left,y=ev.clientY-r.top;
    let best=null,bestD=Infinity;
    for(const n of nodes){const d=Math.hypot(n.x-x,n.y-y);const hit=d<(n.r||8)+4;if(hit&&d<bestD){best=n;bestD=d}}
    return best;
  };
  if(miniExpand)miniExpand.onclick=(e)=>{e.preventDefault();e.stopPropagation();showLocalGraphModal(c)};
  if(miniWrap){
    miniWrap.onclick=(e)=>{
      const hit=hitTest(e);
      if(hit&&!hit.isCenter){location.hash='#/corpus/'+hit.id;return}
      showLocalGraphModal(c);
    };
    miniWrap.onmousemove=(e)=>{
      const hit=hitTest(e);
      if(hit&&!hit.isCenter){miniWrap.style.cursor='pointer';miniWrap.title=hit.name+' — click to open'}
      else{miniWrap.style.cursor='zoom-in';miniWrap.title='Click to expand'}
    };
  }

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
        <li><strong>Compile manually</strong> — one-off synthesis of Wiki concept notes on a topic you pick</li>
        <li><strong>Autonomy: Static</strong> — manual sources, manual compile, answers queries on demand</li>
      </ul>
      ${currentTier==='free'?'<div class="pg-badge">Current plan</div>':''}
    </div>
    <div class="pg-card pg-card-pro${currentTier==='pro'?' pg-current':''}">
      <div class="pg-tier-row"><span class="pg-tier">Pro</span>${currentTier==='pro'?'<span class="pg-tier-badge">Current</span>':''}</div>
      <div class="pg-price"><span class="pg-amt">$9.90</span><span class="pg-period">/mo</span></div>
      <div class="pg-desc">Living knowledge base</div>
      <ul class="pg-features">
        <li>Everything in Free, plus:</li>
        <li>Unlimited corpora & documents</li>
        <li><strong>Auto-add</strong> — connect a feed once, Noos pulls in new posts as they publish. Higher daily caps on manual uploads.</li>
        <li><strong>Embed at scale</strong> — no document cap; your entire growing library stays searchable</li>
        <li><strong>Chat</strong> — higher daily cap, enough for sustained building sessions</li>
        <li><strong>Auto-Compile</strong> — Noos keeps Wiki articles, Entity profiles, and Timelines evolving automatically as your sources change.</li>
        <li><strong>Autonomy: Living + Fully Autonomous</strong> — Living (auto-ingests from connected feeds, keeps Wiki in sync) + Fully Autonomous (actively discovers, subscribes to, pays for peer corpora; grows on its own within your policy).</li>
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
  // Payouts card: only relevant to Pro users running paid corpora. Shown
  // on the Pricing page (not just Account) so users evaluating the Pro
  // tier can see the monetization half of what they're buying before
  // upgrading. Click → POST /cloud/connect/onboard → Stripe-hosted onboarding.
  const payoutsHTML=(isAuth&&currentTier==='pro')?`
    <div class="pg-payouts">
      <div class="pg-payouts-hd">
        <h2 class="pg-payouts-title">Payouts</h2>
        <span class="pg-payouts-sub">Earn from paid corpora — Noos bills via Stripe Connect and routes 90% to you.</span>
      </div>
      <button class="pg-payouts-cta" id="pg-connect-btn">Set up payouts with Stripe</button>
    </div>`:'';
  ct.innerHTML=`<div class="pg-page">
    <div class="pg-hd"><h1 class="pg-title">Plans</h1><p class="pg-sub">Static corpus or living knowledge base.<br>Start free, upgrade when Noos should grow with you.</p></div>
    ${_tierCardsHTML(currentTier)}
    ${payoutsHTML}
    ${isAuth?`<div class="pg-footer"><div class="pg-footer-email">${esc(email)}</div><button class="pg-footer-signout" id="pg-signout-btn">Sign Out</button></div>`:''}
  </div>`;
  _wireTierCardButtons(ct);
  document.getElementById('pg-signout-btn')?.addEventListener('click',signOut);
  document.getElementById('pg-connect-btn')?.addEventListener('click',async function(){
    this.disabled=true;const prev=this.textContent;this.textContent='Loading…';
    try{
      const r=await fetch(`${API}/cloud/connect/onboard`,{method:'POST'});
      const d=await r.json();
      if(d.url){window.location.href=d.url;return}
      toast(d.detail||'Failed to start Stripe onboarding','error');
      this.disabled=false;this.textContent=prev;
    }catch(e){toast('Failed to reach Stripe Connect','error');this.disabled=false;this.textContent=prev}
  });
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
  document.getElementById('sb-new')?.addEventListener('click',()=>{_termCtx={};const wasMain=location.hash==='#/main';location.hash='#/main';if(wasMain)renderHome()});
  _loadWorkspace();_ensureSelfHostedUserId();_loadDisplayName();
  // Migrate the legacy permanent dismiss flag from localStorage to a
  // session-scoped one — anyone who hit × in the old build gets the
  // connector strip back next time they reload.
  if(localStorage.getItem(_CHINT_FLAG)==='1')localStorage.removeItem(_CHINT_FLAG);
  await initAuth();renderAuthUI();
  renderWorkspaceSwitcher();
  window.addEventListener('hashchange',route);route()});

/* ── Team workspaces UI ───────────────────────────────────────── */

// The "Noosphere" wordmark is brand space — it never gets replaced. In an
// org workspace we add a small muted "Team" footnote directly under it so
// the mode shift is legible without touching the logo itself; *which* team
// is surfaced by the bottom-left profile (avatar + popover card). Personal
// context has no footnote — just the bare wordmark, as before.
function renderSidebarBrand(){
  const logo=document.querySelector('.sb-logo');if(!logo)return;
  const inOrg=_workspace.kind==='org'&&_workspace.org_id&&_orgs.find(o=>o.id===_workspace.org_id);
  let stack=logo.querySelector('.sb-lt-stack');
  let plain=logo.querySelector('.sb-lt:not(.sb-lt--sub)');
  if(inOrg){
    if(!stack){
      // Wrap the existing "Noosphere" span in a column so we can hang the
      // footnote off it without disturbing the wordmark's own styling.
      stack=document.createElement('span');
      stack.className='sb-lt-stack';
      const sub=document.createElement('span');
      sub.className='sb-lt sb-lt--sub';
      sub.textContent='Team';
      if(plain){plain.replaceWith(stack);stack.appendChild(plain);}
      stack.appendChild(sub);
    }
    logo.classList.add('sb-logo--team');
  }else if(stack){
    // Unwrap: lift the wordmark back out, drop the footnote + column.
    const word=stack.querySelector('.sb-lt:not(.sb-lt--sub)');
    if(word)stack.replaceWith(word);else stack.remove();
    logo.classList.remove('sb-logo--team');
  }else{
    logo.classList.remove('sb-logo--team');
  }
}

function renderWorkspaceSwitcher(){
  // Refresh the chip whenever workspace identity or display name changes.
  // The chip is one row: avatar (workspace-aware) + user name. We can't
  // just text-swap an avatar element since cloud uses <img> while team
  // uses a span — replace the avatar node entirely each time.
  renderSidebarBrand();
  const profile=document.getElementById('sb-profile');
  if(profile){
    const oldAv=profile.querySelector('.sb-auth-avatar, .sb-auth-initial');
    if(oldAv){
      const tmp=document.createElement('div');tmp.innerHTML=_renderChipAvatarHTML();
      const next=tmp.firstElementChild;
      if(next)oldAv.replaceWith(next);
    }
    const nameEl=profile.querySelector('#sb-profile-name');
    if(nameEl)nameEl.textContent=_operatorChipText();
    // Chip label may need to swap on workspace change (org ↔ personal) or
    // after a Stripe upgrade mirrors a new tier into _authUser.user_metadata.
    // Keep the rule consistent with renderAuthUI: org → "Team", personal →
    // Pro/Free. If the chip element was never rendered (e.g. tierText was
    // empty at first paint and we now need one), inject it.
    let tierEl=profile.querySelector('.sb-profile-tier');
    if(_cloudMode&&_authUser){
      let nextText='';
      if(_workspace.kind==='org'&&_workspace.org_id){
        nextText='Team';
      }else{
        const t=(_authUser.user_metadata?.tier||'free').toLowerCase();
        nextText=t==='pro'?'Pro':'Free';
      }
      if(tierEl){
        tierEl.textContent=nextText;
      }else if(nextText){
        const span=document.createElement('span');
        span.className='sb-profile-tier sb-lb';
        span.textContent=nextText;
        const chev=profile.querySelector('.sb-profile-chev');
        if(chev)profile.insertBefore(span,chev);
        else profile.appendChild(span);
      }
    }
  }
  // Legacy hooks (kept harmless for any caller that still pokes at them).
  const lab=document.getElementById('sb-ws-label');
  if(lab)lab.textContent=_activeWorkspaceLabel();
  const sub=document.getElementById('sb-profile-sub');
  if(sub)sub.textContent=_operatorChipText();
}

async function setWorkspace(ws){
  if(_workspace.kind===ws.kind&&_workspace.org_id===ws.org_id)return;
  _workspace=ws;_saveWorkspace();renderWorkspaceSwitcher();
  // Stay on the page the user is on if it's already workspace-scoped (corpora,
  // home, network/explore — those reload via route()). Otherwise route to the
  // workspace's home (#/main).
  const h=location.hash||'';
  const contextAware=(h==='#/main'||h==='#/corpora'||h.startsWith('#/network')||h.startsWith('#/explore'));
  if(contextAware){route()}else{location.hash='#/main'}
  const label=_workspace.kind==='org'?(_orgs.find(o=>o.id===ws.org_id)?.name||'organization'):'Personal';
  toast('Workspace: '+label,'success');
}

function _showCreateOrgModal(){
  _showFormModal({
    title:'Create organization',
    subtitle:'A shared workspace for your team. Members ingest into the same corpora and contributor names show on every document.',
    submitLabel:'Create',
    fields:[
      {id:'name',label:'Name',placeholder:'Acme Research',hint:'Shown in the workspace switcher.'},
      {id:'slug',label:'URL slug',placeholder:'acme',hint:'Used in invite links. Lowercase letters, digits, hyphens.'}
    ],
    onSubmit:async(v)=>{
      if(!v.name){toast('Name is required');return}
      const r=await fetch(API+'/orgs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v.name,slug:v.slug||''})});
      if(!r.ok){const e=await r.json().catch(()=>({}));toast('Create failed: '+(e.detail||r.status));return}
      const org=await r.json();_closeModal();
      // member_count:1 — we are the sole member. Cached so the workspace card
      // and any team-aware surface (composer hint, suggested writes) render
      // with the right shape immediately, no Loading flash on first paint.
      _orgs=[...(_orgs||[]),{...org,role:'owner',member_count:1}];
      await setWorkspace({kind:'org',org_id:org.id});
      // Landing on the chat home (not the admin dashboard) is what the user
      // wants 99% of the time after creating a team: start writing. The team
      // dashboard at #/orgs/:slug is reachable from the workspace popover's
      // Manage pill and from settings → Team general.
      location.hash='#/main';
    }
  });
}

/* Settings — the single consolidated surface for personal + team config.
   Notion-style modal overlay: left nav with two groups (Personal:
   Account · Appearance · Subscription · cloud; Team · <name>: General ·
   Members · Invites · Connectors · Audit). There is no separate team
   dashboard page — #/orgs/:slug redirects in here. The modal is its own
   visual language (settings-*), it does NOT reuse cv-set-wrap. */

let _settingsSection='account';

// Sections the active context can show. Team sub-pages exist only in an
// org workspace; connectors + audit are admin-only (matches the API's
// role gate so we don't render a pane that will 403 on fetch).
function _settingsAllowedSections(){
  const a=['account','appearance'];
  if(_cloudMode&&_authUser)a.push('subscription');
  if(_workspace.kind==='org'&&_workspace.org_id){
    a.push('team-general','team-members','team-invites');
    if(_settingsIsOrgAdmin())a.push('team-connectors','team-audit');
  }
  return a;
}
function _settingsActiveOrg(){return _orgs.find(o=>o.id===_workspace.org_id)||null}
function _settingsIsOrgAdmin(){const o=_settingsActiveOrg();const r=o?.role||'';return r==='owner'||r==='admin'}
function _settingsCloseModal(){document.getElementById('settings-modal-overlay')?.remove()}
function _settingsNormalizeSection(){
  // Keep the active section valid for the current context. An invalid team
  // section in an org context falls back to Team → General (not Account) so
  // a #/orgs deep link or admin-only pill lands somewhere coherent.
  if(_settingsAllowedSections().includes(_settingsSection))return;
  _settingsSection=(_workspace.kind==='org'&&_workspace.org_id)?'team-general':'account';
}
function _ensureSettingsBackdrop(){
  // The modal floats over whatever page is rendered. On a cold URL hit there
  // is no backdrop, so fall back to home so it doesn't float on emptiness.
  if(!document.querySelector('#content > *'))renderHome();
}
async function _openTeamSettings(slug,tab){
  let org=_orgs.find(o=>o.slug===slug||o.id===slug)||null;
  if(!org){
    try{
      const r=await fetch(API+'/orgs/'+encodeURIComponent(slug));
      if(!r.ok)throw new Error('not found');
      org=await r.json();
      // Cold deep-link: cache it so the switcher/nav/sections resolve. Role
      // is unknown here (refined by loadMe); default to member.
      if(!_orgs.some(o=>o.id===org.id))_orgs=[...(_orgs||[]),{...org,role:org.role||'member'}];
    }catch(e){toast('Organization not found');location.hash='#/main';return}
  }
  // Don't use setWorkspace() — it re-routes non-context hashes to #/main and
  // would unwind us before the modal opens. Set workspace directly instead.
  if(_workspace.kind!=='org'||_workspace.org_id!==org.id){
    _workspace={kind:'org',org_id:org.id};_saveWorkspace();renderWorkspaceSwitcher();
  }
  const map={members:'team-members',invites:'team-invites',connectors:'team-connectors',audit:'team-audit'};
  _ensureSettingsBackdrop();
  _showSettingsModal(map[tab]||'team-general');
}

function _showSettingsModal(section){
  if(section)_settingsSection=section;
  const existing=document.getElementById('settings-modal-overlay');
  if(existing){
    // Already open (e.g. profile pill / #/orgs redirect while on Settings):
    // just re-point it at the requested section instead of stacking.
    _settingsNormalizeSection();
    _settingsRenderNav();_settingsRenderSection(_settingsSection);
    return;
  }
  const ov=document.createElement('div');
  ov.id='settings-modal-overlay';ov.className='settings-modal-overlay';
  ov.innerHTML=`
    <div class="settings-modal" role="dialog" aria-label="Settings">
      <div class="settings-modal-hd">
        <h2 class="settings-modal-title">Settings</h2>
        <button class="settings-modal-close" id="settings-modal-close" aria-label="Close" type="button">×</button>
      </div>
      <div class="settings-modal-body">
        <nav class="settings-nav" id="settings-nav"></nav>
        <div class="settings-pane" id="settings-pane"></div>
      </div>
    </div>`;
  document.body.appendChild(ov);
  const close=()=>{ov.remove();document.removeEventListener('keydown',onKey)};
  document.getElementById('settings-modal-close').onclick=close;
  ov.addEventListener('click',e=>{if(e.target===ov)close()});
  const onKey=e=>{if(e.key==='Escape')close()};
  document.addEventListener('keydown',onKey);
  _settingsNormalizeSection();
  _settingsRenderNav();
  _settingsRenderSection(_settingsSection);
}

function _settingsRenderNav(){
  const nav=document.getElementById('settings-nav');if(!nav)return;
  const inOrg=_workspace.kind==='org'&&_workspace.org_id;
  const orgName=inOrg?(_orgs.find(o=>o.id===_workspace.org_id)?.name||'Team'):'';
  const personalItems=[
    `<button class="settings-nav-item${_settingsSection==='account'?' is-active':''}" data-section="account" type="button">Account</button>`,
    `<button class="settings-nav-item${_settingsSection==='appearance'?' is-active':''}" data-section="appearance" type="button">Appearance</button>`,
  ];
  if(_cloudMode&&_authUser){
    personalItems.push(`<button class="settings-nav-item${_settingsSection==='subscription'?' is-active':''}" data-section="subscription" type="button">Subscription</button>`);
  }
  let html=`<div class="settings-nav-group">
    <div class="settings-nav-label">Personal</div>
    ${personalItems.join('')}
  </div>`;
  if(inOrg){
    const isAdmin=_settingsIsOrgAdmin();
    const teamItem=(sec,label)=>`<button class="settings-nav-item${_settingsSection===sec?' is-active':''}" data-section="${sec}" type="button">${label}</button>`;
    const teamItems=[teamItem('team-general','General'),teamItem('team-members','Members'),teamItem('team-invites','Invites')];
    if(isAdmin)teamItems.push(teamItem('team-connectors','Connectors'),teamItem('team-audit','Audit log'));
    html+=`<div class="settings-nav-group">
      <div class="settings-nav-label">Team · ${esc(orgName)}</div>
      ${teamItems.join('')}
    </div>`;
  }
  nav.innerHTML=html;
  nav.querySelectorAll('[data-section]').forEach(b=>b.onclick=()=>{
    _settingsSection=b.dataset.section;
    _settingsRenderNav();
    _settingsRenderSection(_settingsSection);
  });
}

function _settingsRenderSection(name){
  const p=document.getElementById('settings-pane');if(!p)return;
  if(name==='appearance')_settingsRenderAppearance(p);
  else if(name==='subscription')_settingsRenderSubscription(p);
  else if(name==='team-general')_settingsRenderTeamGeneral(p);
  else if(name==='team-members')_settingsRenderTeamMembers(p);
  else if(name==='team-invites')_settingsRenderTeamInvites(p);
  else if(name==='team-connectors')_settingsRenderTeamConnectors(p);
  else if(name==='team-audit')_settingsRenderTeamAudit(p);
  else _settingsRenderAccount(p);
}

function _settingsRenderAccount(p){
  const cloud=_cloudMode&&_authUser;
  const email=cloud?(_authUser.email||''):'';
  const fallback=cloud?(email.split('@')[0]||'You'):(_ownerName||'You');
  const fallbackDisplay=fallback.charAt(0).toUpperCase()+fallback.slice(1);
  const current=_userDisplayName||'';
  p.innerHTML=`
    <div class="settings-pane-hd">
      <h3 class="settings-pane-h">Account</h3>
      <p class="settings-pane-sub">Your identity. Used across personal and team workspaces.</p>
    </div>
    <div class="settings-rows">
      <div class="settings-row">
        <div class="settings-row-info">
          <div class="settings-row-nm">Preferred name</div>
          <div class="settings-row-dc">How you'd like Noosphere to greet you.</div>
        </div>
        <div class="settings-row-ctl settings-row-ctl--name">
          <input type="text" class="settings-input" id="settings-name-input"
            value="${esc(current)}" placeholder="${esc(fallbackDisplay)}" maxlength="60" />
          <button class="btn-sm" id="settings-name-save" type="button">Save</button>
        </div>
      </div>
      ${email?`<div class="settings-row">
        <div class="settings-row-info">
          <div class="settings-row-nm">Email</div>
          <div class="settings-row-dc">${esc(email)}</div>
        </div>
      </div>`:''}
      ${!cloud?`<div class="settings-row">
        <div class="settings-row-info">
          <div class="settings-row-nm">Mode</div>
          <div class="settings-row-dc">Self-hosted operator</div>
        </div>
      </div>`:''}
    </div>`;
  const input=document.getElementById('settings-name-input');
  const saveBtn=document.getElementById('settings-name-save');
  const persist=()=>{
    const v=(input.value||'').trim();
    _saveDisplayName(v);
    saveBtn.textContent='Saved';
    setTimeout(()=>saveBtn.textContent='Save',900);
    // Refresh surfaces that show the name immediately. The home greeting
    // is the most-visible target — re-render it if it's the page behind
    // the modal (hash will be #/settings after the user clicked Settings).
    renderWorkspaceSwitcher();
    if(document.querySelector('.home-greet'))renderHome();
  };
  saveBtn.onclick=persist;
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();persist()}});
}

function _settingsRenderAppearance(p){
  p.innerHTML=`
    <div class="settings-pane-hd">
      <h3 class="settings-pane-h">Appearance</h3>
      <p class="settings-pane-sub">Light or dark — applied immediately, remembered next session.</p>
    </div>
    <div class="settings-rows">
      <div class="settings-row">
        <div class="settings-row-info">
          <div class="settings-row-nm">Theme</div>
          <div class="settings-row-dc">${isDark()?'Dark':'Light'}</div>
        </div>
        <div class="settings-row-ctl"><button class="btn-sm" id="settings-theme-toggle" type="button">Toggle</button></div>
      </div>
    </div>`;
  document.getElementById('settings-theme-toggle').onclick=()=>{toggleTheme();_settingsRenderAppearance(p)};
}

function _settingsRenderSubscription(p){
  const tier=(_authUser?.user_metadata?.tier||'free').toLowerCase();
  const tierLabel=tier==='pro'?'Pro plan':'Free plan';
  p.innerHTML=`
    <div class="settings-pane-hd">
      <h3 class="settings-pane-h">Subscription</h3>
      <p class="settings-pane-sub">Plan, billing, and quota.</p>
    </div>
    <div class="settings-rows">
      <div class="settings-row">
        <div class="settings-row-info">
          <div class="settings-row-nm">Current plan</div>
          <div class="settings-row-dc">${esc(tierLabel)}</div>
        </div>
        <div class="settings-row-ctl"><a class="btn-sm" href="#/pricing" data-close>Manage</a></div>
      </div>
    </div>`;
  p.querySelectorAll('[data-close]').forEach(el=>el.onclick=()=>document.getElementById('settings-modal-overlay')?.remove());
}

function _settingsTeamHd(o,sub,actionHTML){
  // Shared pane header for every Team section: org name + calm meta line,
  // optional right-aligned action (e.g. "Invite people").
  const memberCount=(typeof o.member_count==='number')?o.member_count:null;
  // "Team" (not "Team plan") — org-level entitlements aren't a thing yet;
  // saying "plan" implies a choice that doesn't exist (organizations.tier
  // is hardcoded; the Stripe columns are unused).
  const meta=['Team'];
  if(memberCount!==null)meta.push(`${memberCount} member${memberCount===1?'':'s'}`);
  meta.push(`slug: ${esc(o.slug)}`);
  meta.push(`your role: ${esc(o.role||'member')}`);
  return `<div class="settings-pane-hd${actionHTML?' settings-pane-hd--bar':''}">
    <div class="settings-pane-hd-main">
      <h3 class="settings-pane-h">${esc(o.name)}</h3>
      <p class="settings-pane-sub">${sub||meta.join(' · ')}</p>
    </div>
    ${actionHTML||''}
  </div>`;
}

function _settingsRenderTeamGeneral(p){
  const o=_settingsActiveOrg();
  if(!o){p.innerHTML='<div class="settings-pane-hd"><h3 class="settings-pane-h">Team</h3></div><p class="settings-pane-sub">No team workspace.</p>';return}
  const isAdmin=_settingsIsOrgAdmin();
  const isOwner=(o.role||'')==='owner';
  const idRow=(label,desc,field,val)=>isAdmin
    ? `<div class="settings-row">
        <div class="settings-row-info"><div class="settings-row-nm">${label}</div><div class="settings-row-dc">${esc(desc)}</div></div>
        <div class="settings-row-ctl settings-row-ctl--name">
          <input type="text" class="settings-input" data-org-field="${field}" value="${esc(val)}" maxlength="60" />
          <button class="btn-sm" data-org-save="${field}" type="button">Save</button>
        </div>
      </div>`
    : `<div class="settings-row"><div class="settings-row-info"><div class="settings-row-nm">${label}</div><div class="settings-row-dc">${esc(val)}</div></div></div>`;
  const danger=isOwner
    ? `<div class="settings-row settings-row--danger">
        <div class="settings-row-info"><div class="settings-row-nm">Delete organization</div><div class="settings-row-dc">Removes the workspace, members, and invites. Org-owned corpora are not deleted. This cannot be undone.</div></div>
        <div class="settings-row-ctl"><button class="settings-danger-btn" id="org-delete-btn" type="button">Delete</button></div>
      </div>`
    : `<div class="settings-row settings-row--danger">
        <div class="settings-row-info"><div class="settings-row-nm">Leave organization</div><div class="settings-row-dc">You'll lose access to every corpus in this workspace. An admin can re-invite you later.</div></div>
        <div class="settings-row-ctl"><button class="settings-danger-btn" id="org-leave-btn" type="button">Leave</button></div>
      </div>`;
  p.innerHTML=`
    ${_settingsTeamHd(o)}
    <div class="settings-rows">
      ${idRow('Name','Shown in the workspace switcher and team header.','name',o.name)}
      ${idRow('URL slug','Used in invite links. Lowercase letters, digits, hyphens.','slug',o.slug)}
      <div class="settings-row"><div class="settings-row-info"><div class="settings-row-nm">Your role</div><div class="settings-row-dc">${esc(o.role||'member')}</div></div></div>
    </div>
    <div class="settings-section-label">Danger zone</div>
    <div class="settings-rows">${danger}</div>`;
  p.querySelectorAll('[data-org-save]').forEach(btn=>btn.onclick=async()=>{
    const field=btn.dataset.orgSave;
    const inp=p.querySelector(`[data-org-field="${field}"]`);
    const val=(inp.value||'').trim();
    if(!val){toast(field==='name'?'Name is required':'Slug is required');return}
    btn.disabled=true;
    const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[field]:val})});
    btn.disabled=false;
    if(!r.ok){const e=await r.json().catch(()=>({}));toast('Failed: '+(e.detail||r.status));return}
    const updated=await r.json();
    // Keep the local cache (drives nav label, switcher, header) in sync.
    const idx=_orgs.findIndex(x=>x.id===o.id);
    if(idx>=0)_orgs[idx]={..._orgs[idx],name:updated.name,slug:updated.slug};
    btn.textContent='Saved';setTimeout(()=>btn.textContent='Save',900);
    renderWorkspaceSwitcher();
    _settingsRenderNav();_settingsRenderSection('team-general');
  });
  const leaveBtn=document.getElementById('org-leave-btn');
  if(leaveBtn)leaveBtn.onclick=async()=>{
    if(!confirm(`Leave ${o.name}? You'll lose access to its corpora.`))return;
    const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/members/'+encodeURIComponent(_userId),{method:'DELETE'});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast('Failed: '+(e.detail||r.status));return}
    _settingsLeaveOrgCleanup(o,'Left '+o.name);
  };
  const delBtn=document.getElementById('org-delete-btn');
  if(delBtn)delBtn.onclick=async()=>{
    if(!confirm(`Delete ${o.name}? This permanently removes the workspace, its members, and invites. This cannot be undone.`))return;
    const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id),{method:'DELETE'});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast('Failed: '+(e.detail||r.status));return}
    _settingsLeaveOrgCleanup(o,'Deleted '+o.name);
  };
}

function _settingsLeaveOrgCleanup(o,msg){
  _orgs=(_orgs||[]).filter(x=>x.id!==o.id);
  _settingsCloseModal();
  toast(msg,'success');
  setWorkspace({kind:'personal',org_id:null});
}

async function _settingsRenderTeamMembers(p){
  const o=_settingsActiveOrg();
  if(!o){p.innerHTML='<div class="settings-empty">No team workspace.</div>';return}
  const isAdmin=_settingsIsOrgAdmin();
  const action=isAdmin?`<button class="btn-sm" id="org-members-invite" type="button">Invite people</button>`:'';
  p.innerHTML=_settingsTeamHd(o,'Roles control read and write access to every corpus in this workspace.',action)
    +`<div class="settings-rows" id="org-members-list"><div class="settings-empty">Loading members…</div></div>`;
  const inv=document.getElementById('org-members-invite');
  if(inv)inv.onclick=()=>{_settingsSection='team-invites';_settingsRenderNav();_settingsRenderSection('team-invites')};
  const list=document.getElementById('org-members-list');
  const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/members');
  if(!r.ok){list.innerHTML='<div class="settings-empty">Failed to load members.</div>';return}
  const members=await r.json();
  list.innerHTML=members.map(m=>{
    const me=m.user_id===_userId;
    const label=me?(m.display_name||'You'):(m.display_name||_renderUserPillName(m.user_id));
    const sub=m.display_name?(me?'You · '+m.user_id:m.user_id):m.user_id;
    const roleCtl=isAdmin&&!me
      ? `<select class="settings-sel" data-uid="${esc(m.user_id)}" data-role-sel>${['owner','admin','editor','viewer'].map(rr=>`<option value="${rr}"${m.role===rr?' selected':''}>${rr}</option>`).join('')}</select>`
      : `<span class="settings-tag">${esc(m.role)}</span>`;
    const rm=isAdmin&&!me&&m.role!=='owner'?`<button class="settings-x" data-uid="${esc(m.user_id)}" title="Remove" type="button">×</button>`:'';
    return `<div class="settings-row"><div class="settings-row-info"><div class="settings-row-nm">${esc(label)}</div><div class="settings-row-dc">${esc(sub)}</div></div><div class="settings-row-ctl">${roleCtl}${rm}</div></div>`;
  }).join('')||'<div class="settings-empty">No members.</div>';
  list.querySelectorAll('[data-role-sel]').forEach(sel=>sel.onchange=async()=>{
    const rr=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/members/'+encodeURIComponent(sel.dataset.uid),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:sel.value})});
    if(!rr.ok){const e=await rr.json().catch(()=>({}));toast('Failed: '+(e.detail||rr.status));return}
    toast('Role updated','success');
  });
  list.querySelectorAll('.settings-x').forEach(btn=>btn.onclick=async()=>{
    if(!confirm('Remove this member?'))return;
    const rr=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/members/'+encodeURIComponent(btn.dataset.uid),{method:'DELETE'});
    if(!rr.ok){const e=await rr.json().catch(()=>({}));toast('Failed: '+(e.detail||rr.status));return}
    toast('Removed','success');_settingsRenderTeamMembers(p);
  });
}

async function _settingsRenderTeamInvites(p){
  const o=_settingsActiveOrg();
  if(!o){p.innerHTML='<div class="settings-empty">No team workspace.</div>';return}
  if(!_settingsIsOrgAdmin()){p.innerHTML=_settingsTeamHd(o,'Invites')+'<div class="settings-empty">Admin only.</div>';return}
  const inviteUrl=t=>location.origin+'/#/invite/'+t;
  p.innerHTML=_settingsTeamHd(o,'Single-use shared links. Generate one per teammate; the role grants what they can do once they join.')
    +`<div class="settings-rows">
        <div class="settings-row">
          <div class="settings-row-info"><div class="settings-row-nm">New invite link</div><div class="settings-row-dc">Expires in 14 days · single-use.</div></div>
          <div class="settings-row-ctl">
            <select id="org-invite-role" class="settings-sel">${['admin','editor','viewer'].map(rr=>`<option value="${rr}"${rr==='editor'?' selected':''}>${rr}</option>`).join('')}</select>
            <button class="btn-sm" id="org-invite-go" type="button">Generate link</button>
          </div>
        </div>
      </div>
      <div class="settings-rows" id="org-invites-list"><div class="settings-empty">Loading invites…</div></div>`;
  const list=document.getElementById('org-invites-list');
  const load=async()=>{
    const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/invites');
    const invites=r.ok?await r.json():[];
    list.innerHTML=invites.length?invites.map(i=>`<div class="settings-row settings-row--line"><div class="settings-row-info"><span class="settings-tag">${esc(i.role)}</span><code class="settings-mono">${esc(inviteUrl(i.token))}</code></div><div class="settings-row-ctl"><button class="btn-sm settings-inv-copy" data-link="${esc(inviteUrl(i.token))}" type="button">Copy</button><button class="btn-sm-ghost settings-inv-revoke" data-id="${esc(i.id)}" type="button">Revoke</button></div></div>`).join(''):'<div class="settings-empty">No active invites.</div>';
    list.querySelectorAll('.settings-inv-copy').forEach(b=>b.onclick=()=>cp(b.dataset.link,b));
    list.querySelectorAll('.settings-inv-revoke').forEach(b=>b.onclick=async()=>{
      if(!confirm('Revoke this invite?'))return;
      const rr=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/invites/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});
      if(!rr.ok){const e=await rr.json().catch(()=>({}));toast('Failed: '+(e.detail||rr.status));return}
      toast('Revoked','success');load();
    });
  };
  document.getElementById('org-invite-go').onclick=async()=>{
    const role=document.getElementById('org-invite-role').value;
    const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/invites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,ttl_days:14})});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast('Failed: '+(e.detail||r.status));return}
    const i=await r.json();
    _showInfoModal({title:'Invite link created',subtitle:`Role: ${i.role}. Expires in 14 days. Single-use — share with one person.`,copyText:inviteUrl(i.token)});
    load();
  };
  load();
}

function _settingsRenderTeamConnectors(p){
  const o=_settingsActiveOrg();
  if(!o){p.innerHTML='<div class="settings-empty">No team workspace.</div>';return}
  if(!_settingsIsOrgAdmin()){p.innerHTML=_settingsTeamHd(o,'Connectors')+'<div class="settings-empty">Admin only.</div>';return}
  const conns=orderedConnectors();
  const cards=conns.map(c=>`<div class="settings-row settings-row--line"><div class="settings-row-info"><span class="conn-mono" style="background:${c.bg};color:${c.fg}" aria-hidden="true">${esc(c.mono||'?')}</span><div class="settings-row-nm">${esc(c.name)}</div><div class="settings-row-dc">${esc(c.desc||'')}</div></div><div class="settings-row-ctl"><span class="settings-tag settings-tag--plain">${c.status==='avail'?'Personal-scope ready':'Coming in T-2'}</span></div></div>`).join('');
  p.innerHTML=_settingsTeamHd(o,'Org-shared connectors: an admin connects once; data flows into team corpora and every member’s agent can query it.')
    +`<div class="settings-rows">${cards}</div>
      <p class="settings-pane-sub" style="margin-top:14px">Live OAuth ships in <strong>T-2</strong>. Personal-scope upload &amp; CLI sync work today via the home composer.</p>`;
}

async function _settingsRenderTeamAudit(p){
  const o=_settingsActiveOrg();
  if(!o){p.innerHTML='<div class="settings-empty">No team workspace.</div>';return}
  if(!_settingsIsOrgAdmin()){p.innerHTML=_settingsTeamHd(o,'Audit log')+'<div class="settings-empty">Admin only.</div>';return}
  p.innerHTML=_settingsTeamHd(o,'Every state change in this organization, newest first.')
    +`<div class="settings-rows" id="org-audit-list"><div class="settings-empty">Loading audit log…</div></div>`;
  const list=document.getElementById('org-audit-list');
  const r=await fetch(API+'/orgs/'+encodeURIComponent(o.id)+'/audit-logs?limit=200');
  if(!r.ok){list.innerHTML='<div class="settings-empty">Failed to load.</div>';return}
  const logs=await r.json();
  if(!logs.length){list.innerHTML='<div class="settings-empty">No activity yet.</div>';return}
  list.innerHTML=logs.map(l=>{
    const t=new Date(l.created_at).toLocaleString();
    const who=_renderUserPillName(l.actor_user_id);
    const res=l.resource_type?`${esc(l.resource_type)}:${esc((l.resource_id||'').slice(0,10))}`:'';
    const meta=l.metadata?Object.entries(l.metadata).map(([k,v])=>`${esc(k)}=${esc(typeof v==='string'?v:JSON.stringify(v))}`).join(' · '):'';
    const parts=[esc(who),esc(t)];if(res)parts.push(res);if(meta)parts.push(meta);
    return `<div class="settings-row"><div class="settings-row-info"><div class="settings-row-nm settings-row-nm--mono">${esc(l.action)}</div><div class="settings-row-dc">${parts.join(' · ')}</div></div></div>`;
  }).join('');
}

/* Shell for every invite-page state — fixes the brand mark top-left and
   vertically centers the card (biased slightly above the midline). */
function _invitePageHTML(inner){
  return `<div class="invite-page">`
    +`<a class="invite-brand" href="#/" title="Noosphere">`
    +`<svg width="20" height="20" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="3"/><circle cx="20" cy="24" r="5" fill="currentColor" opacity="0.7"/><circle cx="44" cy="20" r="4" fill="currentColor" opacity="0.6"/><circle cx="36" cy="42" r="6" fill="currentColor" opacity="0.8"/></svg>`
    +`<span>Noosphere</span></a>`
    +`<div class="cv-set-wrap">${inner}</div></div>`;
}

async function renderInviteAccept(token){
  const lp=document.getElementById('page-landing');if(!lp)return;
  lp.innerHTML=_invitePageHTML('<div class="cv-set-loading">Loading invite…</div>');
  let info=null;
  try{const r=await fetch(API+'/orgs/invites/'+encodeURIComponent(token));if(!r.ok)throw new Error('not found');info=await r.json()}
  catch(e){
    lp.innerHTML=_invitePageHTML(`<div class="cv-set-hd"><h2 class="cv-set-h2">Invite not found</h2><div class="cv-set-sub">This link is invalid or expired. Ask the organization admin for a new one.</div></div><div class="cv-set-list"><div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Back to home</span><span class="cv-set-row-dc">Pick up where you left off.</span></div><div class="cv-set-row-ctl"><a class="btn-sm" href="#/">Home</a></div></div></div>`);
    return;
  }
  const inv=info.invite||{};const org=info.org||{};
  const used=!!inv.accepted_at;const revoked=!!inv.revoked_at;
  const expired=inv.expires_at&&new Date(inv.expires_at)<new Date();
  const initial=esc((org.name?.[0]||'?').toUpperCase());
  // Header — same identity treatment as the org-settings header.
  const headerHTML=`
    <div class="cv-set-hd cv-set-hd--org">
      <span class="cv-set-org-avatar">${initial}</span>
      <div class="cv-set-org-text">
        <div class="cv-set-sub" style="text-transform:uppercase;letter-spacing:.12em">Organization invite</div>
        <h2 class="cv-set-h2 cv-set-h2--org">${esc(org.name||'Noosphere organization')}</h2>
        <div class="cv-set-sub">Role: ${esc(inv.role||'editor')}</div>
      </div>
    </div>`;
  let bodyHTML='';
  if(used){
    bodyHTML='<div class="cv-set-list"><div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Already used</span><span class="cv-set-row-dc">This invite has already been accepted by someone.</span></div></div></div>';
  }else if(revoked){
    bodyHTML='<div class="cv-set-list"><div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Revoked</span><span class="cv-set-row-dc">An admin revoked this invite. Ask for a fresh link.</span></div></div></div>';
  }else if(expired){
    bodyHTML='<div class="cv-set-list"><div class="cv-set-row"><div class="cv-set-row-info"><span class="cv-set-row-nm">Expired</span><span class="cv-set-row-dc">This invite has expired. Ask the admin for a new one.</span></div></div></div>';
  }else{
    bodyHTML=`
      <div class="cv-set-sub" style="line-height:1.65;margin-bottom:6px">
        In <strong>${esc(org.name||'this organization')}</strong>, the team's knowledge is shared and growing. Every member can capture from Slack, meetings, and the tools they use; every document is attributed to whoever added it; and every agent on the team can query the same brain.
      </div>
      <div class="cv-set-list">
        <div class="cv-set-row">
          <div class="cv-set-row-info">
            <span class="cv-set-row-nm">Your name <span class="cv-set-row-dc" style="margin-left:4px">(optional · shown to other members)</span></span>
          </div>
          <div class="cv-set-row-ctl">
            <input type="text" id="invite-name" class="cv-set-row-input" placeholder="e.g. Bob Chen" style="min-width:200px" />
          </div>
        </div>
      </div>
      <div class="invite-accept-row">
        <button class="btn invite-accept-btn" id="invite-accept-btn">Accept and join →</button>
      </div>
    `;
  }
  lp.innerHTML=_invitePageHTML(`${headerHTML}${bodyHTML}`);
  const btn=document.getElementById('invite-accept-btn');
  const nameInput=document.getElementById('invite-name');
  if(nameInput)setTimeout(()=>nameInput.focus(),60);
  async function doAccept(){
    if(btn){btn.disabled=true;btn.textContent='Joining…';}
    _ensureSelfHostedUserId();
    const display_name=(nameInput?.value||'').trim();
    let r;
    try{
      r=await fetch(API+'/orgs/invites/'+encodeURIComponent(token)+'/accept',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({display_name}),
      });
    }catch(e){toast('Failed: network error');if(btn){btn.disabled=false;btn.textContent='Accept and join →';}return}
    if(!r.ok){const e=await r.json().catch(()=>({}));toast('Failed: '+(e.detail||r.status));if(btn){btn.disabled=false;btn.textContent='Accept and join →';}return}
    try{localStorage.removeItem('nph-pending-invite')}catch(e){}
    const m=await r.json();
    _orgs=[...(_orgs||[]),{id:m.org_id,name:org.name,slug:org.slug,role:m.role}];
    _workspace={kind:'org',org_id:m.org_id};_saveWorkspace();
    toast('Joined '+(org.name||'organization'),'success');
    location.hash='#/main';
  }
  if(btn)btn.addEventListener('click',async()=>{
    // Cloud mode needs an authenticated identity to attribute membership.
    // An invitee who isn't signed in would otherwise hit a hard 401
    // ("Authentication required") with no recovery. Stash the invite,
    // send them through sign-in, and auto-complete the join on return.
    if(_cloudMode&&!_authUser){
      try{localStorage.setItem('nph-pending-invite',JSON.stringify({token,display_name:(nameInput?.value||'').trim()}))}catch(e){}
      toast('Sign in to accept your invite','info');
      location.hash='#/login';
      return;
    }
    doAccept();
  });
  // Returning from sign-in: consume a matching stashed invite once and,
  // if the invite is still acceptable, complete the join automatically.
  if(_cloudMode&&_authUser){
    try{
      const raw=localStorage.getItem('nph-pending-invite');
      if(raw){
        const p=JSON.parse(raw);
        if(p&&p.token===token){
          localStorage.removeItem('nph-pending-invite');
          if(!used&&!revoked&&!expired){
            if(nameInput&&p.display_name&&!nameInput.value)nameInput.value=p.display_name;
            doAccept();
          }
        }
      }
    }catch(e){}
  }
}

function _renderUserPillName(uid){
  if(!uid)return 'Unknown';
  if(uid===_userId)return 'You';
  if(uid==='local')return 'Local operator';
  return '@'+uid.slice(0,8);
}
function renderContributorPill(uid){
  if(!uid)return '';
  return `<span class="doc-contributor" title="Contributor: ${esc(uid)}">${esc(_renderUserPillName(uid))}</span>`;
}
