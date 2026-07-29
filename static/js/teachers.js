'use strict';

const TEACHER_EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

PAGES.teachers = { title:'Teachers', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.teachers._token = (PAGES.teachers._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Teachers</h2><p>Staff accounts, qualifications and class-incharge assignment</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Teacher</button>`:'<span class="badge blue">View only</span>'}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="teacher-count">Teachers</h3></div>
    <div class="panel-body" id="teacher-table">${tableSkeletonRows(canWrite?7:6)}</div></div>`;

  let rows = [], classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/teachers'), classOptions()]);
    if(myToken !== PAGES.teachers._token) return;
    rows = d.teachers || [];
    classes = cls;
  }catch(err){
    if(myToken !== PAGES.teachers._token) return;
    document.getElementById('teacher-table').innerHTML = `<div class="empty">Couldn't load teachers. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('teacher-count').textContent = `Teachers (${rows.length})`;
  document.getElementById('teacher-table').innerHTML = tableHTML(teacherColumns(canWrite), rows, 'No teachers yet.');
  bindTeacherTable(content, rows, canWrite, classes);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openTeacherModal(null, classes));
  }
}};

function teacherColumns(canWrite){
  const cols = [
    {k:'employee_id', l:'Emp ID'}, {k:'name', l:'Name'}, {k:'email', l:'Email'},
    {k:'qualification', l:'Qualification'},
    {k:'is_class_incharge', l:'Incharge', fmt:r=>r.is_class_incharge?badge('Yes','violet'):badge('No','gray')},
    {k:'class_name', l:'Class'},
    {k:'employment_status', l:'Status', fmt:r=>statusBadge(r.employment_status)},
  ];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Edit</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindTeacherTable(content, rows, canWrite, classes){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openTeacherModal(r, classes);
  };

  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));
  content.querySelectorAll('tbody tr').forEach((tr,i)=>{
    if(!rows[i]) return;
    tr.style.cursor='pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog(
      'Delete teacher',
      `Remove ${r?r.name:'this teacher'}'s login account? Their class/subject assignments will also be removed. This cannot be undone.`,
      async()=>{
        await api('/api/teachers/'+b.dataset.del, 'DELETE');
        toast('Deleted','Teacher removed','success');
        PAGES.teachers.render();
      }
    );
  }));
}

function openTeacherModal(rec, classes){
  const isCurrentlyIncharge = !!(rec && rec.is_class_incharge);
  const body = `
    ${field('name','Full Name', rec?rec.name:'', 'text')}
    <div class="row2">${field('employee_id','Employee ID', rec?rec.employee_id:'', 'text','EMP-001 (auto if blank)')+field('email','Email', rec?rec.email:'', 'email')}</div>
    <div class="row2">${field('phone','Phone', rec?rec.phone:'', 'text')+field('qualification','Qualification', rec?rec.qualification:'', 'text','M.Sc')}</div>
    <div class="row2">${field('joining_date','Joining Date', rec?rec.joining_date:'', 'date')+selectField('employment_status','Status',[{value:'active',label:'Active'},{value:'inactive',label:'Inactive'}], rec?rec.employment_status:'active')}</div>
    <div class="row2">
      ${selectField('is_class_incharge','Class Incharge',[{value:'',label:'No'},{value:'true',label:'Yes'}], isCurrentlyIncharge?'true':'')}
      <div id="class-assign-wrap" style="${isCurrentlyIncharge?'':'visibility:hidden'}">
        ${selectField('class_id','Assigned Class', classes, rec?rec.class_id:'')}
      </div>
    </div>
    ${rec ? '' : `<p class="hint">A login password will be auto-generated and shown once after saving.</p>`}
  `;
  const overlay = openModal({
    title: rec ? 'Edit Teacher' : 'Add Teacher', body, wide:true,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Teacher name is required');
      if(!v.email || !TEACHER_EMAIL_RE.test(v.email)) throw new Error('A valid email is required');
      const isIncharge = v.is_class_incharge === 'true';
      if(isIncharge && !v.class_id) throw new Error('Select a class for the Class Incharge assignment');

      const payload = {
        name:v.name, employee_id:v.employee_id||undefined, email:v.email, phone:v.phone,
        qualification:v.qualification, joining_date:v.joining_date,
        employment_status:v.employment_status,
        is_class_incharge: isIncharge,
        class_id: isIncharge ? (v.class_id || undefined) : null,
      };
      if(rec){
        await api('/api/teachers/'+rec.id, 'PUT', payload);
        toast('Updated','Teacher saved','success');
        PAGES.teachers.render();
      } else {
        const r = await api('/api/teachers','POST', payload);
        PAGES.teachers.render();
        if(r.password) showGeneratedPassword(v.name, v.email, r.password);
        else toast('Added','Teacher created','success');
      }
    }
  });

  // Show/hide the class dropdown live, instead of leaving an irrelevant
  // control visible when "Class Incharge" is set to No.
  const inchargeSel = overlay.querySelector('[name="is_class_incharge"]');
  const classWrap = overlay.querySelector('#class-assign-wrap');
  inchargeSel.addEventListener('change', ()=>{
    classWrap.style.visibility = inchargeSel.value === 'true' ? 'visible' : 'hidden';
  });
}

function showGeneratedPassword(name, email, password){
  openModal({
    title: 'Teacher account created',
    body: `
      <p style="margin-bottom:14px">Login credentials for <b>${esc(name)}</b> — copy these now, the password will not be shown again.</p>
      <div class="field">
        <label>Email</label>
        <div style="display:flex;gap:8px">
          <input class="input" readonly value="${esc(email)}" id="gen-email" style="flex:1">
          <button type="button" class="btn btn-ghost btn-sm" data-copy="gen-email">Copy</button>
        </div>
      </div>
      <div class="field">
        <label>Password</label>
        <div style="display:flex;gap:8px">
          <input class="input" readonly value="${esc(password)}" id="gen-password" style="flex:1;font-family:monospace">
          <button type="button" class="btn btn-ghost btn-sm" data-copy="gen-password">Copy</button>
        </div>
      </div>
      <p class="hint">Tip: click either field to select its full value if you'd rather copy manually.</p>
    `,
    saveText: 'Done',
    onSave: async()=>{}
  });

  // Wired up after the modal is in the DOM (openModal returns synchronously
  // after insertion, so a microtask delay isn't needed — querySelector below
  // runs against document, which already contains the new modal).
  document.querySelectorAll('[data-copy]').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const input = document.getElementById(btn.dataset.copy);
      if(input) copyToClipboard(input.value);
    });
  });
  ['gen-email','gen-password'].forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.addEventListener('click', ()=>el.select());
  });
}