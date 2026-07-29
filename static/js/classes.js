'use strict';

const MAX_SECTIONS = 3;

/* ============================ CLASSES ============================ */
PAGES.classes = { title:'Classes', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.classes._token = (PAGES.classes._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Classes</h2><p>Academic classes (each may have up to ${MAX_SECTIONS} sections)</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Class</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="class-count">Classes</h3></div>
    <div class="panel-body" id="class-table">${tableSkeletonRows(canWrite?3:2)}</div></div>`;

  let rows = [];
  try{
    const d = await api('/api/classes');
    if(myToken !== PAGES.classes._token) return;
    rows = d.classes || [];
  }catch(err){
    if(myToken !== PAGES.classes._token) return;
    document.getElementById('class-table').innerHTML = `<div class="empty">Couldn't load classes. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('class-count').textContent = `Classes (${rows.length})`;
  document.getElementById('class-table').innerHTML = tableHTML(classColumns(canWrite), rows, 'No classes yet.');
  bindClassTable(content, rows, canWrite);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openClassModal(null, rows));
  }
}};

function classColumns(canWrite){
  const cols = [
    {k:'name', l:'Class'},
    {k:'sections', l:'Sections', fmt:r=>badge(r.sections+' / '+MAX_SECTIONS,'blue')},
    {k:'students', l:'Students', fmt:r=>badge(r.students,'gray')},
  ];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Rename</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindClassTable(content, rows, canWrite){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openClassModal(r, rows);
  };

  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));
  content.querySelectorAll('tbody tr').forEach((tr,i)=>{
    if(!rows[i]) return;
    tr.style.cursor='pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    const reasons = [];
    if(r && r.students > 0) reasons.push(`${r.students} enrolled student(s)`);
    const msg = reasons.length
      ? `${r.name} has ${reasons.join(', ')} and cannot be deleted until they're moved or removed.`
      : `Remove ${r?r.name:'this class'}? This is blocked if it has students, assignments, fee structures, or exams.`;
    confirmDialog('Delete class', msg, async()=>{
      await api('/api/classes/'+b.dataset.del, 'DELETE');
      toast('Deleted','Class removed','success');
      PAGES.classes.render();
    });
  }));
}

function openClassModal(rec, existingRows=[]){
  const body = field('name','Class Name', rec?rec.name:'', 'text','Grade 5');
  openModal({
    title: rec ? 'Rename Class' : 'Add Class', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Class name is required');

      const dup = existingRows.find(c => c.name.toLowerCase() === v.name.toLowerCase() && (!rec || c.id !== rec.id));
      if(dup) throw new Error(`A class named "${v.name}" already exists`);

      if(rec){
        await api('/api/classes/'+rec.id, 'PUT', v);
        toast('Updated','Class renamed','success');
      } else {
        await api('/api/classes','POST', v);
        toast('Added','Class created','success');
      }
      PAGES.classes.render();
    }
  });
}

/* ============================ SECTIONS ============================ */
PAGES.sections = { title:'Sections', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.sections._token = (PAGES.sections._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Sections</h2><p>Sections per class (maximum ${MAX_SECTIONS})</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Section</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="section-count">Sections</h3></div>
    <div class="panel-body" id="section-table">${tableSkeletonRows(canWrite?3:2)}</div></div>`;

  let rows = [], classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/sections'), classOptions()]);
    if(myToken !== PAGES.sections._token) return;
    rows = d.sections || [];
    classes = cls;
  }catch(err){
    if(myToken !== PAGES.sections._token) return;
    document.getElementById('section-table').innerHTML = `<div class="empty">Couldn't load sections. ${esc(err.message)}</div>`;
    return;
  }

  const countByClass = {};
  rows.forEach(s => { countByClass[s.class_id] = (countByClass[s.class_id]||0) + 1; });

  document.getElementById('section-count').textContent = `Sections (${rows.length})`;
  document.getElementById('section-table').innerHTML = tableHTML(sectionColumns(canWrite), rows, 'No sections yet.');
  bindSectionTable(content, rows, canWrite);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openSectionModal(classes, countByClass, rows));
  }
}};

function sectionColumns(canWrite){
  const cols = [{k:'name', l:'Section'}, {k:'class_name', l:'Class'}];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-danger btn-sm" data-del="${r.id}">Delete</button>`});
  }
  return cols;
}

function bindSectionTable(content, rows, canWrite){
  if(!canWrite) return;
  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete section', `Remove section ${r?r.name:''} from ${r?r.class_name:'this class'}? Blocked if it has enrolled students.`, async()=>{
      await api('/api/sections/'+b.dataset.del, 'DELETE');
      toast('Deleted','Section removed','success');
      PAGES.sections.render();
    });
  }));
}

function openSectionModal(classes, countByClass, existingRows=[]){
  const available = classes.filter(c => (countByClass[c.value]||0) < MAX_SECTIONS);

  if(!available.length){
    openModal({
      title: 'Add Section',
      body: `<p class="muted">Every class already has the maximum of ${MAX_SECTIONS} sections. Add a new class first if you need more sections.</p>`,
      saveText: null,
    });
    return;
  }

  const body = `
    ${selectField('class_id','Class', available, available[0].value)}
    ${field('name','Section Name','', 'text','A')}
    <p class="hint" id="sec-count-hint"></p>
  `;
  const overlay = openModal({
    title: 'Add Section', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.class_id || !v.name) throw new Error('Class and section name are required');

      const used = countByClass[v.class_id]||0;
      if(used >= MAX_SECTIONS) throw new Error(`This class already has the maximum of ${MAX_SECTIONS} sections`);

      const dup = existingRows.find(s => s.class_id === v.class_id && s.name.toLowerCase() === v.name.toLowerCase());
      if(dup) throw new Error(`Section "${v.name}" already exists for this class`);

      await api('/api/sections','POST', v);
      toast('Added','Section created','success');
      PAGES.sections.render();
    }
  });

  const updateHint = ()=>{
    const cid = overlay.querySelector('[name="class_id"]').value;
    const used = countByClass[cid]||0;
    overlay.querySelector('#sec-count-hint').textContent = `${used} of ${MAX_SECTIONS} sections used for this class.`;
  };
  overlay.querySelector('[name="class_id"]').addEventListener('change', updateHint);
  updateHint();
}