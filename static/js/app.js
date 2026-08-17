'use strict';

/* ===================================================================
   Global state
   =================================================================== */
const state = { user: null, school: null, studentId: null, page: 'dashboard' };
const PAGES = {}; // filled in by each screen file (auth.js, dashboard.js, etc.)

let _navToken = 0;        // guards against a slow/late page render overwriting a newer page
let _navBar = null;
const REQUEST_TIMEOUT_MS = 20000;

/* ----------------------------- Formatting helpers ----------------------------- */
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function el(html){ const t=document.createElement('template'); t.innerHTML=html.trim(); return t.content.firstElementChild; }
function money(n){ return 'Rs. ' + Number(n||0).toLocaleString(); }
function badge(text,type){ return `<span class="badge ${type||'gray'}">${esc(text)}</span>`; }
function statusBadge(s){
  s=String(s||'').toLowerCase();
  if(['active','paid','present','promoted'].includes(s)) return badge(s,'green');
  if(['inactive','unpaid','absent','fail','retained','disabled'].includes(s)) return badge(s,'red');
  if(['partially paid','leave'].includes(s)) return badge(s,'amber');
  return badge(s,'blue');
}
function debounce(fn, wait=300){
  let t;
  return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), wait); };
}
async function copyToClipboard(text){
  try{ await navigator.clipboard.writeText(text); toast('Copied','Copied to clipboard','success'); }
  catch(e){ toast('Copy failed','Please select and copy manually','error'); }
}

/* ----------------------------- Network layer ----------------------------- */
async function api(path, method='GET', body){
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), REQUEST_TIMEOUT_MS);
  const opt = { method, credentials:'same-origin', headers:{}, signal: controller.signal };
  if(body!==undefined){ opt.headers['Content-Type']='application/json'; opt.body=JSON.stringify(body); }

  let r;
  try{
    r = await fetch(path, opt);
  }catch(err){
    clearTimeout(timer);
    if(err.name === 'AbortError'){
      throw new Error('The request timed out. Please check your connection and try again.');
    }
    throw new Error('Could not reach the server. Please check your connection.');
  }
  clearTimeout(timer);

  const ct = r.headers.get('content-type')||'';
  let data=null;
  if(ct.includes('application/json')){
    try{ data = await r.json(); }
    catch(e){ data = null; } // malformed JSON body — fall back to a generic message below
  }

  if(!r.ok){
    const msg = (data && (data.error || data.detail)) || ('Request failed (' + r.status + ')');
    const error = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    if(r.status===401){ error.silent = true; logout(true); }
    throw error;
  }
  return data;
}

async function download(url, opts={}){
  const btn = opts.button;
  const originalText = btn ? btn.textContent : null;
  if(btn){ btn.disabled = true; btn.textContent = 'Generating…'; }

  try{
    const r = await fetch(url, { credentials:'same-origin' });
    if(!r.ok){
      let msg = 'Download failed (' + r.status + ')';
      try{
        const ct = r.headers.get('content-type')||'';
        if(ct.includes('application/json')){
          const data = await r.json();
          msg = data.error || data.detail || msg;
        }
      }catch(e){ /* keep generic message */ }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const cd = r.headers.get('content-disposition') || '';
    const match = cd.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'download';

    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(objUrl);
  }catch(err){
    toast('Download failed', err.message, 'error');
  }finally{
    if(btn){ btn.disabled = false; btn.textContent = originalText; }
  }
}

/* ----------------------------- Toasts ----------------------------- */
const MAX_TOASTS = 4;
function toast(title, msg, type='info'){
  const c=document.getElementById('toast-container');

  // Keep the stack bounded if several actions fire in quick succession.
  while(c.children.length >= MAX_TOASTS){ c.firstElementChild.remove(); }

  const t=el(`<div class="toast ${type}" role="status" aria-live="polite">
      <div><div class="t-title">${esc(title)}</div>${msg?`<div class="t-msg">${esc(msg)}</div>`:''}</div>
    </div>`);
  c.appendChild(t);

  let timer;
  const dismiss = ()=>{ t.style.opacity='0'; t.style.transform='translateX(30px)'; setTimeout(()=>t.remove(),300); };
  const arm = ()=>{ timer = setTimeout(dismiss, 3600); };
  arm();
  t.addEventListener('mouseenter', ()=>clearTimeout(timer));
  t.addEventListener('mouseleave', arm);
  t.addEventListener('click', dismiss); // click to dismiss early
  t.style.cursor='pointer';
}

/* ----------------------------- Loading indicators ----------------------------- */
function loading(){
  document.getElementById('content').innerHTML='<div class="loading"><div class="spinner"></div></div>';
}
async function refreshBrand(forceRefetch=false){
  // Always prefer a genuinely fresh school name over whatever's cached in
  // state — the login response's "name" field is the PERSON's display
  // name, not the school's name, and must never be used here.
  if(forceRefetch || !state.school || !state.school.name){
    try{
      const d = await api('/api/settings');
      state.school = d.school || state.school || {};
    }catch(e){ /* fall through to whatever we already have, if anything */ }
  }

  const name = (state.school && state.school.name) || 'School';
  const brandEl = document.getElementById('brand-name');
  if(brandEl) brandEl.textContent = name;

  const logoEl = document.getElementById('brand-logo-el');
  if(logoEl){
    if(state.school && state.school.logo){
      logoEl.innerHTML = `<img src="${esc(state.school.logo)}" alt="Logo" style="width:100%;height:100%;object-fit:cover">`;
    } else {
      logoEl.textContent = 'SMS';
    }
  }
}

function startNavProgress(){
  if(!_navBar){
    _navBar = document.createElement('div');
    _navBar.id = 'nav-progress';
    _navBar.style.cssText = 'position:fixed;top:0;left:0;height:3px;z-index:9998;background:var(--accent,#10B981);width:0%;opacity:1;';
    document.body.appendChild(_navBar);
  }
  _navBar.style.transition = 'none';
  _navBar.style.opacity = '1';
  _navBar.style.width = '0%';
  void _navBar.offsetWidth; // force reflow so the transition below actually animates
  _navBar.style.transition = 'width .4s ease-out, opacity .3s ease .15s';
  _navBar.style.width = '75%';
}
function finishNavProgress(){
  if(!_navBar) return;
  _navBar.style.width = '100%';
  setTimeout(()=>{ _navBar.style.opacity = '0'; }, 200);
}

/* ----------------------------- Modal ----------------------------- */
function openModal({title, body, saveText='Save', onSave, danger=false, wide=false}){
  const root=document.getElementById('modal-root');
  const overlay=el(`<div class="modal-overlay"></div>`);
  overlay.innerHTML=`<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="${wide?'max-width:760px':''}">
    <div class="modal-head"><h3>${esc(title)}</h3><button class="x-btn" data-x type="button">&times;</button></div>
    <div class="modal-body">${body}</div>
    <div class="modal-foot"><button class="btn btn-ghost" data-x type="button">Cancel</button>${onSave?`<button class="btn ${danger?'btn-danger':'btn-primary'}" data-save type="button">${esc(saveText)}</button>`:''}</div></div>`;
  root.appendChild(overlay);

  const previouslyFocused = document.activeElement;
  let saving = false;

  const close=()=>{
    if(saving) return; // block closing mid-save to avoid touching removed DOM afterward
    document.removeEventListener('keydown', onKeydown);
    overlay.remove();
    if(previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    document.body.style.overflow = '';
  };

  function onKeydown(e){
    if(e.key === 'Escape'){ close(); }
    if(e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && !saving){
      const saveBtn = overlay.querySelector('[data-save]');
      if(saveBtn) saveBtn.click();
    }
  }
  document.addEventListener('keydown', onKeydown);
  document.body.style.overflow = 'hidden'; // lock background scroll while modal is open

  overlay.addEventListener('click',e=>{ if(e.target===overlay||e.target.hasAttribute('data-x')) close(); });

  if(onSave){
    overlay.querySelector('[data-save]').addEventListener('click',async()=>{
      const btn=overlay.querySelector('[data-save]');
      saving = true; btn.disabled=true;
      try{
        await onSave(overlay);
        saving = false;
        close();
      }catch(err){
        saving = false;
        toast('Error',err.message,'error');
        btn.disabled=false;
      }
    });
  }

  // Autofocus the first editable field for a smoother keyboard-first workflow.
  const firstField = overlay.querySelector('input:not([readonly]), select, textarea');
  if(firstField) setTimeout(()=>firstField.focus(), 50);

  return overlay;
}
function confirmDialog(title, msg, onYes){
  openModal({ title, body:`<p class="muted">${esc(msg)}</p>`, saveText:'Yes, proceed', danger:true,
    onSave: async()=>{ await onYes(); toast('Done', title+' completed','success'); } });
}

/* ----------------------------- Form helpers ----------------------------- */
function getVals(scope){ const o={}; scope.querySelectorAll('[name]').forEach(i=>{ o[i.name]= i.type==='checkbox'? i.checked : i.value.trim(); }); return o; }
function field(name,label,val='',type='text',ph=''){ return `<div class="field"><label>${esc(label)}</label><input class="input" name="${name}" type="${type}" value="${esc(val)}" placeholder="${esc(ph)}"></div>`; }
function selectField(name,label,opts,val=''){ const o=opts.map(x=>`<option value="${esc(x.value)}" ${String(x.value)===String(val)?'selected':''}>${esc(x.label)}</option>`).join(''); return `<div class="field"><label>${esc(label)}</label><select class="input" name="${name}">${o}</select></div>`; }
function textareaField(name,label,val=''){ return `<div class="field"><label>${esc(label)}</label><textarea class="input" name="${name}" rows="2">${esc(val)}</textarea></div>`; }
function tableHTML(columns, rows, emptyText){
  if(!rows.length) return `<div class="empty">${esc(emptyText||'No records found.')}</div>`;
  const head=columns.map(c=>`<th>${esc(c.l)}</th>`).join('');
  const body=rows.map(r=>`<tr>${columns.map(c=>{
    const v=c.fmt?c.fmt(r):esc(r[c.k]); return `<td class="${c.nowrap?'nowrap':''}">${v}</td>`;}).join('')}</tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function tableSkeletonRows(cols=6, rows=4){
  const row = `<tr>${'<td><div style="height:14px;background:var(--border,#333);border-radius:4px;opacity:.3;animation:pulseSkeleton 1.4s ease-in-out infinite"></div></td>'.repeat(cols)}</tr>`;
  return `<div class="table-wrap"><table><tbody>${row.repeat(rows)}</tbody></table></div>`;
}

/* ----------------------------- Router ----------------------------- */
function go(page, opts={}){
  const token = ++_navToken;
  state.page=page;

  document.querySelectorAll('#nav a').forEach(a=>a.classList.toggle('active', a.dataset.nav===page));
  document.getElementById('page-title').textContent = (PAGES[page]&&PAGES[page].title)||page;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('show');

  if(!opts.silent){
    location.hash = page; // enables browser back/forward between visited pages this session
  }

  loading();
  startNavProgress();

  const renderResult = PAGES[page] ? PAGES[page].render() : Promise.reject(new Error('Page not found.'));
  Promise.resolve(renderResult)
    .catch(err=>{
      if(token !== _navToken) return; // a newer navigation already started — ignore this stale error
      document.getElementById('content').innerHTML = `<div class="empty">Something went wrong loading this page.</div>`;
      if(!err.silent) toast('Error', err.message, 'error');
    })
    .finally(()=>{ if(token === _navToken) finishNavProgress(); });
}

window.addEventListener('hashchange', ()=>{
  const page = location.hash.replace('#','');
  if(page && PAGES[page] && page !== state.page){ go(page, {silent:true}); }
});

/* ----------------------------- Global safety net ----------------------------- */
// Catches anything that slipped past a local try/catch anywhere in the app,
// so the user always sees something instead of a silently broken screen.
window.addEventListener('unhandledrejection', (e)=>{
  console.error('Unhandled error:', e.reason);
  toast('Unexpected error', (e.reason && e.reason.message) || 'Something went wrong.', 'error');
});

window.addEventListener('online', ()=> toast('Back online', 'Connection restored', 'success'));
window.addEventListener('offline', ()=> toast('No connection', 'You appear to be offline', 'error'));

/* ============================ BOOT ============================ */
async function boot(){
  try{
    const s = await api('/api/setup/status');
    if(!s.setup_done){ renderSetup(); return; }
  }catch(e){ /* ignore, fall through to login */ }

  // A valid session cookie may already exist (e.g. after a page refresh).
  try{
    await afterLogin();
    return;
  }catch(e){ /* not logged in, or session expired — fall through to login */ }

  renderLogin();
}

function logout(silent){
  // Reset the UI immediately rather than waiting on the network call, so a
  // slow or failed logout request never leaves the user stuck on a stale screen.
  state.user=null; state.school=null; state.studentId=null;
  document.getElementById('main-screen').hidden=true;
  document.getElementById('auth-screen').hidden=false;
  renderLogin();
  if(!silent) toast('Signed out','You have been logged out','info');

  fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'}).catch(()=>{});
}

document.getElementById('btn-menu').addEventListener('click',()=>{
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebar-overlay').classList.add('show');
});
document.getElementById('sidebar-overlay').addEventListener('click',()=>{
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('show');
});

boot();