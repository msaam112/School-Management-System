'use strict';

async function subjectOptions(){ const d=await api('/api/subjects'); return d.subjects.map(s=>({value:s.id,label:s.name})); }
async function teacherOptions(){ const d=await api('/api/teachers'); return d.teachers.map(t=>({value:t.id,label:t.name})); }

/* ============================ SUBJECTS ============================ */
PAGES.subjects = { title:'Subjects', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.subjects._token = (PAGES.subjects._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Subjects</h2><p>Subjects taught across classes</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Subject</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="subject-count">Subjects</h3></div>
    <div class="panel-body" id="subject-table">${tableSkeletonRows(canWrite?2:1)}</div></div>`;

  let rows = [];
  try{
    const d = await api('/api/subjects');
    if(myToken !== PAGES.subjects._token) return;
    rows = d.subjects || [];
  }catch(err){
    if(myToken !== PAGES.subjects._token) return;
    document.getElementById('subject-table').innerHTML = `<div class="empty">Couldn't load subjects. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('subject-count').textContent = `Subjects (${rows.length})`;
  document.getElementById('subject-table').innerHTML = tableHTML(subjectColumns(canWrite), rows, 'No subjects yet.');
  bindSubjectTable(content, rows, canWrite);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openSubjectModal(null, rows));
  }
}};

function subjectColumns(canWrite){
  const cols = [{k:'name', l:'Subject'}];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Rename</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindSubjectTable(content, rows, canWrite){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openSubjectModal(r, rows);
  };
  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));
  content.querySelectorAll('tbody tr').forEach((tr,i)=>{
    if(!rows[i]) return;
    tr.style.cursor='pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete subject', `Remove "${r?r.name:'this subject'}"? Blocked if it's assigned to any teacher.`, async()=>{
      await api('/api/subjects/'+b.dataset.del, 'DELETE');
      toast('Deleted','Subject removed','success');
      PAGES.subjects.render();
    });
  }));
}

function openSubjectModal(rec, existingRows=[]){
  const body = field('name','Subject Name', rec?rec.name:'', 'text','Mathematics');
  openModal({
    title: rec ? 'Rename Subject' : 'Add Subject', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Subject name is required');

      const dup = existingRows.find(s => s.name.toLowerCase() === v.name.toLowerCase() && (!rec || s.id !== rec.id));
      if(dup) throw new Error(`A subject named "${v.name}" already exists`);

      if(rec){
        await api('/api/subjects/'+rec.id, 'PUT', v);
        toast('Updated','Subject renamed','success');
      } else {
        await api('/api/subjects','POST', v);
        toast('Added','Subject created','success');
      }
      PAGES.subjects.render();
    }
  });
}

/* ============================ TEACHER ASSIGNMENTS ============================ */
PAGES.assignments = { title:'Teacher Assignments', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.assignments._token = (PAGES.assignments._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Teacher Assignments</h2><p>Assign teachers to classes &amp; subjects</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Assignment</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="assign-count">Assignments</h3></div>
    <div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        <input class="input" id="assign-search" placeholder="Filter by teacher, class, or subject…" style="max-width:320px" autocomplete="off">
      </div>
      <div id="assign-table">${tableSkeletonRows(canWrite?4:3)}</div>
    </div></div>`;

  let rows = [], teachers = [], classes = [], subjects = [];
  try{
    const [d, t, c, s] = await Promise.all([
      api('/api/assignments'), teacherOptions(), classOptions(), subjectOptions()
    ]);
    if(myToken !== PAGES.assignments._token) return;
    rows = d.assignments || []; teachers = t; classes = c; subjects = s;
  }catch(err){
    if(myToken !== PAGES.assignments._token) return;
    document.getElementById('assign-table').innerHTML = `<div class="empty">Couldn't load assignments. ${esc(err.message)}</div>`;
    return;
  }

  function draw(filtered){
    document.getElementById('assign-count').textContent =
      filtered.length === rows.length ? `Assignments (${rows.length})` : `Assignments (${filtered.length} of ${rows.length})`;
    document.getElementById('assign-table').innerHTML = tableHTML(assignmentColumns(canWrite), filtered, 'No assignments match.');
    bindAssignmentTable(content, filtered, canWrite);
  }
  draw(rows);

  document.getElementById('assign-search').addEventListener('input', debounce(()=>{
    const q = document.getElementById('assign-search').value.trim().toLowerCase();
    if(!q){ draw(rows); return; }
    draw(rows.filter(r =>
      (r.teacher_name||'').toLowerCase().includes(q) ||
      (r.class_name||'').toLowerCase().includes(q) ||
      (r.subject_name||'').toLowerCase().includes(q)
    ));
  }, 200));

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openAssignmentModal(teachers, classes, subjects, rows));
  }
}};

function assignmentColumns(canWrite){
  const cols = [{k:'teacher_name', l:'Teacher'}, {k:'class_name', l:'Class'}, {k:'subject_name', l:'Subject'}];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-danger btn-sm" data-del="${r.id}">Remove</button>`});
  }
  return cols;
}

function bindAssignmentTable(content, rows, canWrite){
  if(!canWrite) return;
  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Remove assignment', `Unassign ${r?r.teacher_name:'this teacher'} from ${r?r.class_name+' / '+r.subject_name:'this class/subject'}?`, async()=>{
      await api('/api/assignments/'+b.dataset.del, 'DELETE');
      toast('Removed','Assignment removed','success');
      PAGES.assignments.render();
    });
  }));
}

function openAssignmentModal(teachers, classes, subjects, existingRows=[]){
  if(!teachers.length || !classes.length || !subjects.length){
    openModal({
      title: 'Add Assignment',
      body: `<p class="muted">You need at least one teacher, one class, and one subject before creating an assignment.</p>`,
      saveText: null,
    });
    return;
  }
  const body = `
    ${selectField('teacher_id','Teacher', teachers, teachers[0].value)}
    ${selectField('class_id','Class', classes, classes[0].value)}
    ${selectField('subject_id','Subject', subjects, subjects[0].value)}
  `;
  openModal({
    title: 'Add Assignment', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      const dup = existingRows.find(a => a.teacher_id === v.teacher_id && a.class_id === v.class_id && a.subject_id === v.subject_id);
      if(dup) throw new Error('This teacher is already assigned to this class and subject');

      await api('/api/assignments','POST', v);
      toast('Added','Assignment created','success');
      PAGES.assignments.render();
    }
  });
}