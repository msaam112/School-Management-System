'use strict';

function renderAuthShell(inner){ document.getElementById('auth-card').innerHTML=inner; }

/* Reusable password field with a show/hide toggle. Self-contained inline
   styling so it doesn't require any CSS file changes. */
function passwordField(name, label, ph=''){
  return `<div class="field">
    <label>${esc(label)}</label>
    <div style="position:relative">
      <input class="input" name="${name}" type="password" placeholder="${esc(ph)}" style="padding-right:44px">
      <button type="button" data-toggle-pw="${name}" tabindex="-1"
        style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:0;cursor:pointer;color:var(--muted,#888);font-size:12px;padding:4px">Show</button>
    </div>
  </div>`;
}
function wirePasswordToggles(scope){
  scope.querySelectorAll('[data-toggle-pw]').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const input = scope.querySelector(`input[name="${btn.dataset.togglePw}"]`);
      if(!input) return;
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      btn.textContent = showing ? 'Show' : 'Hide';
    });
  });
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/* ============================ LOGIN ============================ */
function renderLogin(){
  document.getElementById('auth-screen').hidden=false;
  document.getElementById('main-screen').hidden=true;
  let tab='admin';
  let submitting=false;
  // Preserve whatever the user typed if they switch tabs and back.
  const savedValues = { email:'', cnic:'', roll:'' };

  function captureValues(){
    const form = document.getElementById('login-form');
    if(!form) return;
    const v = getVals(form);
    if(tab==='admin'){ savedValues.email = v.email||''; }
    else{ savedValues.cnic = v.cnic||''; savedValues.roll = v.roll||''; }
  }

  function draw(){
    renderAuthShell(`
      <div class="auth-logo">SMS</div>
      <h1>Welcome back</h1>
      <div class="sub">Sign in to the School Management System</div>
      <div class="tabs">
        <button class="${tab==='admin'?'active':''}" data-tab="admin" type="button" ${submitting?'disabled':''}>Staff Login</button>
        <button class="${tab==='parent'?'active':''}" data-tab="parent" type="button" ${submitting?'disabled':''}>Parent Login</button>
      </div>
      <form id="login-form" novalidate>
        ${tab==='admin'
          ? field('email','Email',savedValues.email,'email','you@school.edu') + passwordField('password','Password','••••••')
          : field('cnic','Parent CNIC',savedValues.cnic,'text','35202-XXXXXXX-X') + field('roll','Student Roll Number',savedValues.roll,'text','e.g. G5-001')}
        <div class="error-text" id="login-error" hidden></div>
        <button class="btn btn-primary btn-block" type="submit" style="margin-top:8px" ${submitting?'disabled':''}>
          ${submitting ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
      <p class="hint" style="margin-top:14px;text-align:center">Secure, role-based access · your session is encrypted.</p>
    `);

    const emailInput = document.querySelector('#login-form input[name="email"]');
    if(emailInput) emailInput.setAttribute('autocomplete','username');
    const pwInput = document.querySelector('#login-form input[name="password"]');
    if(pwInput) pwInput.setAttribute('autocomplete','current-password');
    wirePasswordToggles(document.getElementById('auth-card'));

    document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{
      if(submitting) return;
      captureValues();
      tab=b.dataset.tab;
      draw();
    }));

    const firstField = document.querySelector('#login-form input');
    if(firstField) setTimeout(()=>firstField.focus(), 50);

    document.getElementById('login-form').addEventListener('submit', async e=>{
      e.preventDefault();
      if(submitting) return;

      const v=getVals(e.target);
      const errEl = document.getElementById('login-error');
      errEl.hidden = true;

      // Light client-side validation before hitting the network.
      if(tab==='admin'){
        if(!v.email || !EMAIL_RE.test(v.email)){
          errEl.textContent = 'Enter a valid email address.'; errEl.hidden=false; return;
        }
        if(!v.password){
          errEl.textContent = 'Enter your password.'; errEl.hidden=false; return;
        }
      } else {
        if(!v.cnic || !v.roll){
          errEl.textContent = 'Enter both CNIC and roll number.'; errEl.hidden=false; return;
        }
      }

      submitting = true; draw();
      try{
        const body = tab==='admin' ? {type:'staff', email:v.email, password:v.password}
                                    : {type:'parent', cnic:v.cnic, roll:v.roll};
        await api('/api/auth/login','POST',body);
        await afterLogin();
      }catch(err){
        submitting = false; draw();
        toast('Login failed', err.message, 'error');
      }
    });
  }
  draw();
}

/* ============================ SETUP WIZARD ============================ */
function renderSetup(){
  document.getElementById('auth-screen').hidden=false;
  document.getElementById('main-screen').hidden=true;
  let classes=[{name:'',sections:['','']}];
  let submitting=false;

  // Critical: reads whatever is currently typed in the DOM back into the
  // `classes` array before we mutate it. Without this, adding/removing a
  // class row wipes out every class already typed in — a real data-loss bug.
  function syncClassesFromDOM(){
    const form = document.getElementById('setup-form');
    if(!form) return;
    const v = getVals(form);
    classes.forEach((c, ci)=>{
      if(v['cname'+ci] !== undefined) c.name = v['cname'+ci];
      c.sections = [0,1,2].map(si => v['sec'+ci+'_'+si] !== undefined ? v['sec'+ci+'_'+si] : (c.sections[si]||''));
    });
  }

  function classBlock(){
    return classes.map((c,ci)=>`
      <div class="card" style="margin-bottom:12px;padding:14px">
        <div class="row2">
          ${field('cname'+ci,'Class Name',c.name,'text','e.g. Grade 5')}
          <div class="field"><label>Sections (max 3)</label>
            <div class="row3">${[0,1,2].map(si=>`<input class="input" name="sec${ci}_${si}" value="${esc(c.sections[si]||'')}" placeholder="A">`).join('')}</div>
          </div>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" data-rmc="${ci}" ${classes.length<=1||submitting?'disabled':''}>Remove class</button>
      </div>`).join('');
  }

  function draw(){
    renderAuthShell(`
      <div class="auth-logo">SMS</div>
      <h1>School Setup</h1>
      <div class="sub">Configure your institution (one-time wizard)</div>
      <form id="setup-form" novalidate>
        ${field('school_name','School Name','', 'text','Bright Future School')}
        <div class="row2">${field('emis_code','EMIS Code','', 'text','EMIS-000')+field('contact_number','Contact','', 'text','+92-...')}</div>
        ${textareaField('address','Address','')}
        ${field('principal_name','Principal Name','', 'text','Mr. ...')}
        <div class="divider"></div>
        <div style="display:flex;justify-content:space-between;align-items:center"><b>Classes &amp; Sections</b>
          <button class="btn btn-ghost btn-sm" data-addc type="button" ${classes.length>=12||submitting?'disabled':''}>+ Add class</button></div>
        <div id="class-list" style="margin-top:10px">${classBlock()}</div>
        <div class="divider"></div>
        <b>Administrator Account</b>
        <div class="row2" style="margin-top:8px">${field('admin_email','Admin Email','', 'email','admin@school.edu')}${passwordField('admin_password','Admin Password','min 6 chars')}</div>
        <div class="error-text" id="setup-error" hidden></div>
        <button class="btn btn-primary btn-block" type="submit" style="margin-top:14px" ${submitting?'disabled':''}>
          ${submitting ? 'Setting up…' : 'Complete Setup'}
        </button>
      </form>`);

    const adminEmail = document.querySelector('#setup-form input[name="admin_email"]');
    if(adminEmail) adminEmail.setAttribute('autocomplete','username');
    wirePasswordToggles(document.getElementById('auth-card'));

    document.querySelector('[data-addc]').addEventListener('click',()=>{
      if(submitting) return;
      syncClassesFromDOM();
      if(classes.length<12){ classes.push({name:'',sections:['','']}); draw(); }
    });
    document.querySelectorAll('[data-rmc]').forEach(b=>b.addEventListener('click',()=>{
      if(submitting) return;
      syncClassesFromDOM();
      classes.splice(+b.dataset.rmc,1);
      draw();
    }));

    const firstField = document.querySelector('#setup-form input[name="school_name"]');
    if(firstField) setTimeout(()=>firstField.focus(), 50);

    document.getElementById('setup-form').addEventListener('submit', async e=>{
      e.preventDefault();
      if(submitting) return;

      syncClassesFromDOM();
      const v=getVals(e.target);
      const errEl = document.getElementById('setup-error');
      errEl.hidden = true;

      if(!v.school_name){
        errEl.textContent = 'School name is required.'; errEl.hidden=false; return;
      }
      if(!v.admin_email || !EMAIL_RE.test(v.admin_email)){
        errEl.textContent = 'Enter a valid administrator email.'; errEl.hidden=false; return;
      }
      if(!v.admin_password || v.admin_password.length < 6){
        errEl.textContent = 'Admin password must be at least 6 characters.'; errEl.hidden=false; return;
      }

      const cls=[];
      for(let i=0;i<classes.length;i++){
        const nm=(v['cname'+i]||'').trim(); if(!nm) continue;
        const secs=[0,1,2].map(si=>v['sec'+i+'_'+si]).filter(x=>x && x.trim());
        cls.push({name:nm, sections:secs.slice(0,3)});
      }
      if(!cls.length){
        errEl.textContent = 'Add at least one class.'; errEl.hidden=false; return;
      }

      // Catch duplicate class names client-side — the database rejects these,
      // and without this check the user would just see a raw server error.
      const seen = new Set();
      for(const c of cls){
        const key = c.name.toLowerCase();
        if(seen.has(key)){
          errEl.textContent = `Class name "${c.name}" is used more than once. Each class needs a unique name.`;
          errEl.hidden=false; return;
        }
        seen.add(key);
      }

      submitting = true; draw();
      try{
        await api('/api/setup','POST',{
          school_name:v.school_name, emis_code:v.emis_code, contact_number:v.contact_number,
          address:v.address, principal_name:v.principal_name,
          admin_email:v.admin_email, admin_password:v.admin_password, classes:cls
        });
        toast('Setup complete','Signing you in…','success');
        await afterLogin();
      }catch(err){
        submitting = false; draw();
        toast('Setup failed', err.message, 'error');
      }
    });
  }
  draw();
}

/* ============================ POST-LOGIN BOOT ============================ */
async function afterLogin(){
  const me=await api('/api/auth/me');
  state.user=me;
  if(me.role==='parent' && me.student) state.studentId=me.student.id;
  try{
    const d=await api('/api/dashboard');
    state.school=d.school||{};
  }catch(e){
    console.warn('Could not load school info after login:', e.message);
  }
  showApp();
}

function showApp(){
  document.getElementById('auth-screen').hidden=true;
  document.getElementById('main-screen').hidden=false;
  const u=state.user;
  document.getElementById('user-name').textContent=u.name||u.role;
  document.getElementById('user-role').textContent=(u.role||'').replace('_',' ');
  document.getElementById('user-avatar').textContent=(u.name||'U').charAt(0).toUpperCase();
  refreshBrand();
  document.getElementById('brand-role').textContent=(u.role||'').replace('_',' ');
  buildNav();
  go('dashboard');
}

document.getElementById('btn-logout').addEventListener('click',()=>logout());