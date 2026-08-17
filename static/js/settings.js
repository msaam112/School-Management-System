'use strict';

PAGES.settings = { title:'System Settings', async render(){
  const content = document.getElementById('content');
  if(state.user.role !== 'super_admin'){
    content.innerHTML = '<div class="empty">Access denied.</div>';
    return;
  }

  content.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

  let d, usersResp;
  try{
    [d, usersResp] = await Promise.all([api('/api/settings'), api('/api/settings/users')]);
  }catch(err){
    content.innerHTML = `<div class="empty">Couldn't load settings. ${esc(err.message)}</div>`;
    return;
  }

  const s = d.school || {};
  const settings = d.settings || {};
  const users = usersResp.users || [];
  state.school = s;
  await refreshBrand();

  content.innerHTML = `
    <div class="page-head"><div><h2>System Settings</h2><p>School profile and general configuration (Super Admin only)</p></div></div>

    <div class="panel" style="margin-bottom:20px"><div class="panel-head"><h3>School Profile</h3></div><div class="panel-body">
      <form id="settings-form">
        ${field('name','School Name', s.name||'')}
        <div class="row2">${field('emis_code','EMIS Code', s.emis_code||'')+field('contact_number','Contact', s.contact_number||'')}</div>
        ${textareaField('address','Address', s.address||'')}
        <div class="row2">${field('principal_name','Principal Name', s.principal_name||'')+field('established_year','Established Year', s.established_year||'')}</div>
        ${textareaField('motto','Motto', s.motto||'')}
      <div class="divider"></div>
      <b>School Logo</b>
      <div class="toolbar" style="margin-top:10px;align-items:center">
        <div style="width:56px;height:56px;border-radius:12px;overflow:hidden;background:var(--surface-2);display:flex;align-items:center;justify-content:center;border:1px solid var(--border)" id="logo-preview">
          ${s.logo ? `<img src="${esc(s.logo)}" style="width:100%;height:100%;object-fit:cover">` : `<span class="muted" style="font-size:10px">No logo</span>`}
        </div>
        <input type="file" id="logo-file" accept="image/*" style="max-width:220px">
        <button type="button" class="btn btn-ghost btn-sm" id="logo-upload-btn">Upload Logo</button>
      </div>
      <div class="divider"></div><b>General</b>
        <div class="row2" style="margin-top:8px">
          ${field('academic_year','Current Academic Year', settings.academic_year||'')}
          ${field('pass_mark','Pass Mark %', settings.pass_mark||'33', 'number')}
        </div>
        <button type="submit" class="btn btn-primary" id="save-settings" style="margin-top:14px">Save Settings</button>
      </form>
    </div></div>

    <div class="panel"><div class="panel-head"><h3 id="user-count">User Privileges</h3></div><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        <input class="input" id="user-search" placeholder="Search name or email…" style="max-width:280px" autocomplete="off">
      </div>
      <div id="user-table">${tableHTML(userColumns(), users, 'No users found.')}</div>
    </div></div>`;

  document.getElementById('user-count').textContent = `User Privileges (${users.length})`;

  const form = document.getElementById('settings-form');
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const v = getVals(form);

    const passMark = parseFloat(v.pass_mark);
    if(v.pass_mark !== '' && (isNaN(passMark) || passMark < 0 || passMark > 100)){
      toast('Invalid pass mark', 'Pass mark must be a number between 0 and 100', 'error');
      return;
    }
    if(!v.name){
      toast('School name required', 'The school name cannot be empty', 'error');
      return;
    }

    const saveBtn = document.getElementById('save-settings');
    saveBtn.disabled = true;
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';

    try{
      await api('/api/settings','PUT', {
        name:v.name, emis_code:v.emis_code, contact_number:v.contact_number, address:v.address,
        principal_name:v.principal_name, established_year:v.established_year, motto:v.motto,
        settings: { academic_year:v.academic_year, pass_mark:v.pass_mark }
      });
      toast('Saved','Settings updated','success');
      PAGES.settings.render();
    }catch(err){
      toast('Error', err.message, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = originalText;
    }
  });

  const searchInput = document.getElementById('user-search');
  searchInput.addEventListener('input', debounce(()=>{
    const q = searchInput.value.trim().toLowerCase();
    const filtered = !q ? users : users.filter(u =>
      (u.display_name||'').toLowerCase().includes(q) || (u.email||'').toLowerCase().includes(q)
    );
    document.getElementById('user-count').textContent =
      filtered.length === users.length ? `User Privileges (${users.length})` : `User Privileges (${filtered.length} of ${users.length})`;
    document.getElementById('user-table').innerHTML = tableHTML(userColumns(), filtered, 'No matching users.');
    bindUserActions(content, filtered);
  }, 200));

  const logoBtn = document.getElementById('logo-upload-btn');
  if(logoBtn) logoBtn.addEventListener('click', async ()=>{
    const fileInput = document.getElementById('logo-file');
    const file = fileInput.files[0];
    if(!file){ toast('Choose a file', 'Select an image first', 'error'); return; }
    logoBtn.disabled = true;
    try{
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/settings/logo', { method:'POST', credentials:'same-origin', body: fd });
      if(!r.ok){
        const d = await r.json().catch(()=>({}));
        throw new Error(d.error || 'Upload failed');
      }
      const result = await r.json();
      state.school = state.school || {};
      state.school.logo = result.logo;
      await refreshBrand();
      document.getElementById('logo-preview').innerHTML = `<img src="${esc(result.logo)}" style="width:100%;height:100%;object-fit:cover">`;
      toast('Uploaded', 'School logo updated', 'success');
    }catch(err){
      toast('Upload failed', err.message, 'error');
    }finally{
      logoBtn.disabled = false;
    }
  });

  bindUserActions(content, users);
}};

const REASSIGNABLE_ROLES = [
  {value:'super_admin',label:'Super Admin'}, {value:'principal',label:'Principal'},
  {value:'teacher',label:'Teacher'}, {value:'class_incharge',label:'Class Incharge'},
];

function userColumns(){
  return [
    {k:'display_name', l:'Name'}, {k:'email', l:'Email'},
    {k:'role', l:'Role', fmt:r=>`
      <select class="input" data-role-select="${r.id}" style="max-width:150px;padding:6px 10px;font-size:12px">
        ${REASSIGNABLE_ROLES.map(x=>`<option value="${x.value}" ${x.value===r.role?'selected':''}>${x.label}</option>`).join('')}
      </select>`},
    {k:'status', l:'Status', fmt:r=>statusBadge(r.status)},
    {k:'_a', l:'', nowrap:true, fmt:r=>`
      <button class="btn btn-ghost btn-sm" data-setpw="${r.id}">Set Password</button>
      <button class="btn btn-ghost btn-sm" data-reset="${r.id}">Random Reset</button>
      ${r.status==='active'
        ? `<button class="btn btn-danger btn-sm" data-disable="${r.id}">Disable</button>`
        : `<button class="btn btn-success btn-sm" data-enable="${r.id}">Enable</button>`}
    `},
  ];
}
function bindUserActions(content, users){
  content.querySelectorAll('[data-role-select]').forEach(sel=>{
    sel.addEventListener('change', ()=>{
      const u = users.find(x=>x.id===sel.dataset.roleSelect);
      const newRole = sel.value;
      confirmDialog('Change role', `Change ${u?u.display_name:'this user'}'s role to "${newRole.replace('_',' ')}"?`, async()=>{
        const result = await api('/api/settings/users/'+sel.dataset.roleSelect+'/role', 'PUT', {role: newRole});
        if(result.warning) toast('Role changed (note)', result.warning, 'error');
        PAGES.settings.render();
      });
    });
  });

  content.querySelectorAll('[data-setpw]').forEach(b=>b.addEventListener('click', ()=>{
    const u = users.find(x=>x.id===b.dataset.setpw);
    openModal({
      title: 'Set Custom Password',
      body: `<p class="hint" style="margin-bottom:14px">Set a specific password for <b>${esc(u?u.display_name:'')}</b> (min 8 characters).</p>${field('password','New Password','', 'password')}`,
      onSave: async(scope)=>{
        const v = getVals(scope);
        if(!v.password || v.password.length < 8) throw new Error('Password must be at least 8 characters');
        await api('/api/settings/users/'+b.dataset.setpw+'/set-password', 'POST', {password: v.password});
        toast('Password set', `${u?u.display_name:'User'}'s password has been updated`, 'success');
      }
    });
  }));

  content.querySelectorAll('[data-reset]').forEach(b=>b.addEventListener('click', async ()=>{
    const u = users.find(x=>x.id===b.dataset.reset);
    b.disabled = true;
    try{
      const r = await api('/api/settings/users/'+b.dataset.reset+'/reset-password','POST');
      openModal({
        title: 'Password Reset',
        body: `
          <p style="margin-bottom:14px">New login credentials for <b>${esc(u.display_name)}</b> — copy these now, the password will not be shown again.</p>
          <div class="field">
            <label>Email</label>
            <div style="display:flex;gap:8px">
              <input class="input" readonly value="${esc(u.email)}" id="reset-email" style="flex:1">
              <button type="button" class="btn btn-ghost btn-sm" data-copy="reset-email">Copy</button>
            </div>
          </div>
          <div class="field">
            <label>New Password</label>
            <div style="display:flex;gap:8px">
              <input class="input" readonly value="${esc(r.password)}" id="reset-password" style="flex:1;font-family:monospace">
              <button type="button" class="btn btn-ghost btn-sm" data-copy="reset-password">Copy</button>
            </div>
          </div>`,
        saveText: 'Done', onSave: async()=>{}
      });
      document.querySelectorAll('[data-copy]').forEach(btn=>{
        btn.addEventListener('click', ()=>{
          const input = document.getElementById(btn.dataset.copy);
          if(input) copyToClipboard(input.value);
        });
      });
    }catch(err){
      toast('Error', err.message, 'error');
    }finally{
      b.disabled = false;
    }
  }));

  content.querySelectorAll('[data-disable]').forEach(b=>b.addEventListener('click', ()=>{
    const u = users.find(x=>x.id===b.dataset.disable);
    confirmDialog('Disable account', `${u?u.display_name:'This user'} will no longer be able to log in. Continue?`, async()=>{
      await api('/api/settings/users/'+b.dataset.disable+'/status','PUT', {status:'disabled'});
      toast('Disabled', `${u?u.display_name:'Account'} can no longer log in`, 'success');
      PAGES.settings.render();
    });
  }));

  content.querySelectorAll('[data-enable]').forEach(b=>b.addEventListener('click', async ()=>{
    try{
      await api('/api/settings/users/'+b.dataset.enable+'/status','PUT', {status:'active'});
      toast('Enabled','Account re-activated','success');
      PAGES.settings.render();
    }catch(err){ toast('Error', err.message, 'error'); }
  }));
}