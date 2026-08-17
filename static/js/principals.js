'use strict';

PAGES.principals = { title:'Headmasters', async render(){
  const content = document.getElementById('content');
  if(state.user.role !== 'super_admin'){
    content.innerHTML = '<div class="empty">Access denied.</div>';
    return;
  }
  content.innerHTML = `
    <div class="page-head">
      <div><h2>Headmasters</h2><p>Principal accounts — separate from Teacher management</p></div>
      <button class="btn btn-primary" data-add>+ Add Headmaster</button>
    </div>
    <div class="panel"><div class="panel-head"><h3 id="prin-count">Headmasters</h3></div>
    <div class="panel-body" id="prin-table">${tableSkeletonRows(6)}</div></div>`;

  let rows = [];
  try{
    const d = await api('/api/principals');
    rows = d.principals || [];
  }catch(err){
    document.getElementById('prin-table').innerHTML = `<div class="empty">Couldn't load headmasters. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('prin-count').textContent = `Headmasters (${rows.length})`;
  document.getElementById('prin-table').innerHTML = tableHTML(principalColumns(), rows, 'No headmaster accounts yet.');
  bindPrincipalTable(content, rows);

  content.querySelector('[data-add]').addEventListener('click', ()=>openPrincipalModal(null));
}};

function principalColumns(){
  return [
    {k:'employee_id', l:'Emp ID'}, {k:'name', l:'Name'}, {k:'email', l:'Email'},
    {k:'qualification', l:'Qualification'},
    {k:'user_status', l:'Login Status', fmt:r=>statusBadge(r.user_status)},
    {k:'employment_status', l:'Employment', fmt:r=>statusBadge(r.employment_status)},
    {k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}">Edit</button> <button class="btn btn-danger btn-sm" data-del="${r.id}">Delete</button>`},
  ];
}

function bindPrincipalTable(content, rows){
  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.edit);
    if(r) openPrincipalModal(r);
  }));
  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete headmaster', `Remove ${r?r.name:'this'} headmaster account and their login? This cannot be undone.`, async()=>{
      await api('/api/principals/'+b.dataset.del, 'DELETE');
      toast('Deleted','Headmaster removed','success');
      PAGES.principals.render();
    });
  }));
}

function openPrincipalModal(rec){
  const body = `
    ${field('name','Full Name', rec?rec.name:'', 'text')}
    <div class="row2">${field('employee_id','Employee ID', rec?rec.employee_id:'', 'text','HM-001 (auto if blank)')+field('email','Email', rec?rec.email:'', 'email')}</div>
    <div class="row2">${field('phone','Phone', rec?rec.phone:'', 'text')+field('qualification','Qualification', rec?rec.qualification:'', 'text','M.Ed')}</div>
    <div class="row2">${field('joining_date','Joining Date', rec?rec.joining_date:'', 'date')+selectField('employment_status','Status',[{value:'active',label:'Active'},{value:'inactive',label:'Inactive'}], rec?rec.employment_status:'active')}</div>
    ${rec ? '' : `<p class="hint">A login password will be auto-generated and shown once after saving.</p>`}
  `;
  openModal({
    title: rec ? 'Edit Headmaster' : 'Add Headmaster', body, wide:true,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Name is required');
      if(rec){
        await api('/api/principals/'+rec.id, 'PUT', v);
        toast('Updated','Headmaster saved','success');
        PAGES.principals.render();
      } else {
        const r = await api('/api/principals','POST', v);
        PAGES.principals.render();
        if(r.password) showGeneratedPassword(v.name, v.email, r.password);
        else toast('Added','Headmaster created','success');
      }
    }
  });
}