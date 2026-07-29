'use strict';

PAGES.parents = { title:'Parents', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.parents._token = (PAGES.parents._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Parents</h2><p>Guardians linked to students (CNIC + Roll used for parent login)</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Parent</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="parent-count">Parents</h3></div>
    <div class="panel-body" id="parent-table">${tableSkeletonRows(canWrite?5:4)}</div></div>`;

  let rows = [], childrenByParent = {};
  try{
    const [d, studentsResp] = await Promise.all([api('/api/parents'), api('/api/students')]);
    if(myToken !== PAGES.parents._token) return;
    rows = d.parents || [];
    (studentsResp.students||[]).forEach(s=>{
      if(!s.parent_id) return;
      (childrenByParent[s.parent_id] = childrenByParent[s.parent_id] || []).push(s);
    });
  }catch(err){
    if(myToken !== PAGES.parents._token) return;
    document.getElementById('parent-table').innerHTML = `<div class="empty">Couldn't load parents. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('parent-count').textContent = `Parents (${rows.length})`;
  document.getElementById('parent-table').innerHTML = tableHTML(parentColumns(canWrite, childrenByParent), rows, 'No parents yet.');
  bindParentTable(content, rows, canWrite, childrenByParent);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openParentModal(null));
  }
}};

function childrenCell(parent, childrenByParent){
  const kids = childrenByParent[parent.id] || [];
  if(!kids.length) return `<span class="muted">No linked students</span>`;
  return kids.map(k => `${esc(k.name)} <span class="muted">(${esc(k.roll_number)})</span>`).join('<br>');
}

function parentColumns(canWrite, childrenByParent={}){
  const cols = [
    {k:'name', l:'Name'}, {k:'cnic', l:'CNIC'}, {k:'phone', l:'Phone'},
    {k:'_children', l:'Children', fmt:r=>childrenCell(r, childrenByParent)},
  ];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Edit</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindParentTable(content, rows, canWrite, childrenByParent){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openParentModal(r);
  };

  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));
  content.querySelectorAll('tbody tr').forEach((tr,i)=>{
    if(!rows[i]) return;
    tr.style.cursor='pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    const kids = childrenByParent[b.dataset.del] || [];
    if(kids.length){
      toast('Cannot delete', `${r?r.name:'This parent'} is linked to ${kids.length} student(s). Reassign or remove those students first.`, 'error');
      return;
    }
    confirmDialog('Delete parent', `Remove ${r?r.name:'this'} parent record? This cannot be undone.`, async()=>{
      await api('/api/parents/'+b.dataset.del, 'DELETE');
      toast('Deleted','Parent removed','success');
      PAGES.parents.render();
    });
  }));
}

const CNIC_HINT_RE = /^\d{5}-\d{7}-\d$/;

function openParentModal(rec){
  const body = `
    ${field('name','Full Name', rec?rec.name:'', 'text','Guardian name')}
    ${field('cnic','CNIC', rec?rec.cnic:'', 'text','35202-XXXXXXX-X')}
    <div class="hint" id="cnic-hint" style="margin-top:-10px;margin-bottom:14px"></div>
    ${field('phone','Phone', rec?rec.phone:'', 'text','+92...')}
    ${textareaField('address','Address', rec?rec.address:'')}
  `;
  const overlay = openModal({
    title: rec ? 'Edit Parent' : 'Add Parent', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Parent name is required');
      if(!v.cnic || v.cnic.length < 5) throw new Error('A valid CNIC is required');
      if(rec){
        await api('/api/parents/'+rec.id, 'PUT', v);
        toast('Updated','Parent saved','success');
      } else {
        await api('/api/parents','POST', v);
        toast('Added','Parent added','success');
      }
      PAGES.parents.render();
    }
  });

  const cnicInput = overlay.querySelector('[name="cnic"]');
  const hintEl = overlay.querySelector('#cnic-hint');
  const checkCnicFormat = ()=>{
    const v = cnicInput.value.trim();
    hintEl.textContent = (v && !CNIC_HINT_RE.test(v)) ? 'Expected format: 35202-1234567-1 (double-check before saving).' : '';
  };
  cnicInput.addEventListener('input', checkCnicFormat);
  checkCnicFormat();
}