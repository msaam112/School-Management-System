'use strict';

async function classOptions(){ const d=await api('/api/classes'); return d.classes.map(c=>({value:c.id,label:c.name})); }
async function sectionsByClass(){
  const d=await api('/api/sections');
  const map={};
  d.sections.forEach(s=>{ (map[s.class_id]=map[s.class_id]||[]).push(s); });
  return map;
}

function tableSkeletonRows(cols=6, rows=4){
  const row = `<tr>${'<td><div style="height:14px;background:var(--border,#333);border-radius:4px;opacity:.3;animation:pulseSkeleton 1.4s ease-in-out infinite"></div></td>'.repeat(cols)}</tr>`;
  return `<div class="table-wrap"><table><tbody>${row.repeat(rows)}</tbody></table></div>`;
}

PAGES.students = { title:'Students', async render(){
  const canWrite = state.user.role === 'super_admin';
  const viewOnly = ['teacher','class_incharge'].includes(state.user.role);
  const content = document.getElementById('content');
  const myToken = (PAGES.students._token = (PAGES.students._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Students</h2><p>Manage student records, roll numbers and parent linkage</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Student</button>`:''}
      ${viewOnly?`<span class="badge blue">View only</span>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="stu-count">Students</h3></div><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        <input class="input" id="stu-search" placeholder="Search by name / roll / admission id…" style="max-width:320px" autocomplete="off">
        <button class="btn btn-ghost btn-sm" data-search>Search</button>
        <button class="btn btn-ghost btn-sm" data-clear hidden>Clear</button>
      </div>
      <div id="stu-table">${tableSkeletonRows(canWrite?7:6)}</div>
    </div></div>`;

  let allRows = [];
  let classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/students'), classOptions()]);
    if(myToken !== PAGES.students._token) return; // a newer render started — abandon this one
    allRows = d.students||[];
    classes = cls;
  }catch(err){
    if(myToken !== PAGES.students._token) return;
    document.getElementById('stu-table').innerHTML = `<div class="empty">Couldn't load students. ${esc(err.message)}</div>`;
    return;
  }

  renderRows(allRows);

  const searchInput = document.getElementById('stu-search');
  const clearBtn = content.querySelector('[data-clear]');

  searchInput.addEventListener('keydown', e=>{ if(e.key==='Enter') doSearch(); });
  content.querySelector('[data-search]').addEventListener('click', doSearch);
  clearBtn.addEventListener('click', ()=>{
    searchInput.value = '';
    clearBtn.hidden = true;
    renderRows(allRows);
  });

  // Instant client-side filter of already-loaded rows for a snappy feel,
  // while the authoritative server-side search request is still resolving.
  searchInput.addEventListener('input', debounce(()=>{
    const q = searchInput.value.trim().toLowerCase();
    if(!q){ clearBtn.hidden = true; renderRows(allRows); return; }
    clearBtn.hidden = false;
    const filtered = allRows.filter(s =>
      (s.name||'').toLowerCase().includes(q) ||
      (s.roll_number||'').toLowerCase().includes(q) ||
      (s.admission_id||'').toLowerCase().includes(q)
    );
    renderRows(filtered, true);
  }, 200));

  async function doSearch(){
    const q = searchInput.value.trim();
    if(!q){ renderRows(allRows); return; }
    const searchBtn = content.querySelector('[data-search]');
    searchBtn.disabled = true;
    try{
      const r = await api('/api/students/search?q='+encodeURIComponent(q));
      if(myToken !== PAGES.students._token) return;
      clearBtn.hidden = false;
      renderRows(r.students);
    }catch(err){
      toast('Search failed', err.message, 'error');
    }finally{
      searchBtn.disabled = false;
    }
  }

  function renderRows(rows, isLiveFilter=false){
    document.getElementById('stu-count').textContent =
      `Students${isLiveFilter ? ` (${rows.length} matching)` : ` (${rows.length})`}`;
    document.getElementById('stu-table').innerHTML = tableHTML(studentColumns(canWrite), rows, 'No students found.');
    bindStudentTable(content, rows, canWrite, classes);
  }

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openStudentModal(null, classes));
  }
}};

function studentColumns(canWrite){
  const cols = [
    {k:'roll_number', l:'Roll'}, {k:'name', l:'Name'}, {k:'gender', l:'Gender'},
    {k:'class_name', l:'Class'}, {k:'section_name', l:'Sec'}, {k:'parent_name', l:'Parent'},
    {k:'status', l:'Status', fmt:r=>statusBadge(r.status)},
  ];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Edit</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindStudentTable(content, rows, canWrite, classes){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openStudentModal(r, classes);
  };

  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));

  // Whole-row click also opens Edit (buttons stop propagation above so
  // Delete stays a deliberate, separate click rather than accidental).
  content.querySelectorAll('tbody tr').forEach((tr, i)=>{
    if(!rows[i]) return;
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete student', `Remove ${r?r.name:'this student'}'s record? This cannot be undone.`, async()=>{
      await api('/api/students/'+b.dataset.del, 'DELETE');
      toast('Deleted','Student removed','success');
      PAGES.students.render();
    });
  }));
}

async function openStudentModal(rec, classes){
  const secByClass = await sectionsByClass();
  function secOptions(cid, sel){
    const opts = secByClass[cid]||[];
    if(!opts.length) return `<option value="">No sections for this class</option>`;
    return opts.map(s=>`<option value="${s.id}" ${s.id===sel?'selected':''}>${esc(s.name)}</option>`).join('');
  }
  const cid = rec ? rec.class_id : (classes[0] ? classes[0].value : '');

  const body = `
    ${field('name','Full Name', rec?rec.name:'', 'text','Full name')}
    <div class="row2">${field('roll_number','Roll Number', rec?rec.roll_number:'', 'text','G5-001')+field('admission_id','Admission ID', rec?rec.admission_id:'', 'text','ADM-0001 (optional)')}</div>
    <div class="row3">
      ${selectField('gender','Gender',[{value:'Male',label:'Male'},{value:'Female',label:'Female'}], rec?rec.gender:'Male')}
      ${field('dob','Date of Birth', rec?rec.dob:'', 'date')}
      ${selectField('status','Status',[{value:'active',label:'Active'},{value:'inactive',label:'Inactive'}], rec?rec.status:'active')}
    </div>
    <div class="row2">
      ${selectField('class_id','Class', classes, cid)}
      <div class="field"><label>Section</label><select class="input" name="section_id">${secOptions(cid, rec?rec.section_id:'')}</select></div>
    </div>
    ${rec ? `
    <div class="divider"></div>
    <p class="hint">Parent details (name, CNIC, phone) can't be edited from here yet — they're managed on the Parents page.</p>
    ` : `
    <div class="divider"></div><b>Parent / Guardian</b>
    ${field('parent_name','Parent Name','', 'text','Guardian name')}
    <div class="row2">${field('parent_cnic','Parent CNIC','', 'text','35202-XXXXXXX-X')+field('parent_phone','Phone','', 'text','+92...')}</div>
    `}`;

  const overlay = openModal({
    title: rec ? 'Edit Student' : 'Add Student', body, wide:true,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Student name is required');
      if(!v.roll_number) throw new Error('Roll number is required');
      if(!v.section_id) throw new Error('This class has no sections yet — add a section first');
      if(!rec){
        if(!v.parent_name) throw new Error('Parent name is required');
        if(!v.parent_cnic) throw new Error('Parent CNIC is required');
      }
      if(rec){
        await api('/api/students/'+rec.id, 'PUT', {
          name:v.name, roll_number:v.roll_number, gender:v.gender, dob:v.dob,
          status:v.status, class_id:v.class_id, section_id:v.section_id
        });
        toast('Updated','Student saved','success');
      } else {
        await api('/api/students','POST', v);
        toast('Registered','Student added','success');
      }
      PAGES.students.render();
    }
  });

  const clsSel = overlay.querySelector('[name="class_id"]');
  clsSel.addEventListener('change', ()=>{
    const secSel = overlay.querySelector('[name="section_id"]');
    secSel.innerHTML = secOptions(clsSel.value, '');
  });
}