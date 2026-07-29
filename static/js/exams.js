'use strict';

PAGES.exams = { title:'Examinations', async render(){
  const role = state.user.role;
  const canCreate = ['super_admin','principal','teacher','class_incharge'].includes(role);
  const canDelete = ['super_admin','principal'].includes(role);
  const content = document.getElementById('content');
  const myToken = (PAGES.exams._token = (PAGES.exams._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Examinations</h2><p>Create exams, enter marks and generate result cards</p></div>
      ${canCreate?`<button class="btn btn-primary" data-add>+ New Exam</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="exam-count">Examinations</h3></div>
    <div class="panel-body" id="exam-table">${tableSkeletonRows(4)}</div></div>`;

  let rows = [], classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/exams'), classOptions()]);
    if(myToken !== PAGES.exams._token) return;
    rows = d.exams || []; classes = cls;
  }catch(err){
    if(myToken !== PAGES.exams._token) return;
    document.getElementById('exam-table').innerHTML = `<div class="empty">Couldn't load exams. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('exam-count').textContent = `Examinations (${rows.length})`;
  document.getElementById('exam-table').innerHTML = tableHTML(examColumns(canDelete), rows, 'No exams yet.');
  bindExamTable(content, rows, canDelete);

  if(canCreate){
    content.querySelector('[data-add]').addEventListener('click', ()=>openExamModal(classes));
  }
}};

function examColumns(canDelete){
  const cols = [
    {k:'name', l:'Exam'}, {k:'exam_date', l:'Date'}, {k:'class_name', l:'Class'}, {k:'section_name', l:'Section'},
    {k:'_a', l:'Actions', nowrap:true, fmt:r=>`
      <button class="btn btn-ghost btn-sm" data-marks="${r.id}">Enter Marks</button>
      <button class="btn btn-ghost btn-sm" data-res="${r.id}">Results</button>
      ${canDelete?`<button class="btn btn-danger btn-sm" data-del="${r.id}">Delete</button>`:''}
    `},
  ];
  return cols;
}

function bindExamTable(content, rows, canDelete){
  content.querySelectorAll('[data-marks]').forEach(b=>b.addEventListener('click', ()=>openMarksModal(b.dataset.marks)));
  content.querySelectorAll('[data-res]').forEach(b=>b.addEventListener('click', ()=>openResultsModal(b.dataset.res)));
  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete exam', `Delete "${r?r.name:'this exam'}"? This removes the exam and all its recorded results. This cannot be undone.`, async()=>{
      await api('/api/exams/'+b.dataset.del, 'DELETE');
      toast('Deleted','Exam removed','success');
      PAGES.exams.render();
    });
  }));
}

function openExamModal(classes){
  const body = `
    ${field('name','Exam Name','', 'text','Mid Term Examination')}
    ${field('exam_date','Date','', 'date')}
    ${selectField('class_id','Class', classes, classes[0]?classes[0].value:'')}
  `;
  openModal({
    title: 'New Exam', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      if(!v.name) throw new Error('Exam name is required');
      if(!v.class_id) throw new Error('Select a class');
      await api('/api/exams','POST', v);
      toast('Created','Exam added','success');
      PAGES.exams.render();
    }
  });
}

/* ---------------- Marks Entry ---------------- */
async function openMarksModal(eid){
  let ex;
  try{
    ex = await api('/api/exams/'+eid);
  }catch(err){
    toast('Error', "Couldn't load exam details: " + err.message, 'error');
    return;
  }

  const subs = ex.subjects.length ? ex.subjects : (await api('/api/subjects')).subjects;
  const stuRows = ex.students;

  if(!subs.length){
    openModal({ title:'Enter Marks', body:`<p class="muted">No subjects are assigned to this class yet. Assign a subject to a teacher for this class first.</p>`, saveText:null });
    return;
  }

  let hasUnsavedChanges = false;
  // Cache existing marks per subject so switching subjects doesn't lose
  // anything already fetched, and so we can pre-fill known values.
  const existingMarksCache = {};

  async function fetchExistingMarks(subjectId){
    if(existingMarksCache[subjectId]) return existingMarksCache[subjectId];
    try{
      const results = await api(`/api/exams/${eid}/results`);
      const bySubject = {};
      (results.results||[]).forEach(r=>{
        if(!bySubject[r.subject_id]) bySubject[r.subject_id] = {};
        bySubject[r.subject_id][r.student_id] = r;
      });
      Object.assign(existingMarksCache, bySubject);
    }catch(e){ /* non-fatal — form just starts blank if this fails */ }
    return existingMarksCache[subjectId] || {};
  }

  function build(subjectId, existingForSubject, totalMarks){
    if(!stuRows.length) return `<div class="empty">No students found for this class/section.</div>`;
    const rows = stuRows.map(s=>{
      const existing = existingForSubject[s.id];
      const val = existing ? existing.obtained : '';
      return `<tr>
        <td class="nowrap">${esc(s.roll_number)}</td><td>${esc(s.name)}</td>
        <td><input class="input" name="mk_${s.id}" type="number" min="0" max="${totalMarks}" step="0.5" style="max-width:110px" value="${val}" placeholder="0"></td>
        </tr>`;
    }).join('');
    return `<div class="table-wrap"><table><thead><tr><th>Roll</th><th>Student</th><th>Obtained (out of <span id="mk-total-label">${totalMarks}</span>)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  const initialExisting = await fetchExistingMarks(subs[0].id);

  const overlay = openModal({
    title: 'Enter Marks — ' + ex.exam.name, wide:true,
    body: `<div class="row2" style="margin-bottom:12px">
             ${selectField('subject_id','Subject', subs.map(s=>({value:s.id,label:s.name})), subs[0].id)}
             ${field('total_marks','Total Marks', '100', 'number')}
           </div><div id="mk-body">${build(subs[0].id, initialExisting, 100)}</div>`,
    onSave: async(scope)=>{
      const subjectId = scope.querySelector('[name="subject_id"]').value;
      const totalMarks = parseFloat(scope.querySelector('[name="total_marks"]').value) || 100;
      const marks = [];
      let hasInvalid = false;

      scope.querySelectorAll('input[name^="mk_"]').forEach(i=>{
        if(i.value === '') return;
        const obtained = parseFloat(i.value);
        if(isNaN(obtained) || obtained < 0 || obtained > totalMarks){
          hasInvalid = true;
          i.style.borderColor = 'var(--danger, #ef4444)';
        } else {
          i.style.borderColor = '';
          marks.push({ student_id: i.name.replace('mk_',''), obtained, total: totalMarks });
        }
      });

      if(hasInvalid) throw new Error(`Each mark must be between 0 and ${totalMarks}. Fields in red need correcting.`);
      if(!marks.length) throw new Error('Enter at least one mark');

      await api('/api/exams/'+eid+'/marks','POST', {subject_id: subjectId, marks});
      hasUnsavedChanges = false;
      toast('Saved','Marks recorded','success');
    }
  });

  const subSel = overlay.querySelector('[name="subject_id"]');
  const totalInput = overlay.querySelector('[name="total_marks"]');
  const mkBody = overlay.querySelector('#mk-body');

  mkBody.addEventListener('input', ()=>{ hasUnsavedChanges = true; });

  totalInput.addEventListener('change', ()=>{
    const label = overlay.querySelector('#mk-total-label');
    if(label) label.textContent = totalInput.value || 100;
    overlay.querySelectorAll('input[name^="mk_"]').forEach(i=>{ i.max = totalInput.value || 100; });
  });

  subSel.addEventListener('change', async ()=>{
    if(hasUnsavedChanges && !confirm('You have unsaved marks for the current subject. Switch anyway and discard them?')){
      subSel.value = subSel.dataset.lastValue || subSel.value;
      return;
    }
    subSel.dataset.lastValue = subSel.value;
    const existing = await fetchExistingMarks(subSel.value);
    mkBody.innerHTML = build(subSel.value, existing, parseFloat(totalInput.value)||100);
    hasUnsavedChanges = false;
  });
  subSel.dataset.lastValue = subSel.value;
}

/* ---------------- Results ---------------- */
async function openResultsModal(eid){
  let ex, d;
  try{
    [ex, d] = await Promise.all([api('/api/exams/'+eid), api('/api/exams/'+eid+'/results')]);
  }catch(err){
    toast('Error', "Couldn't load results: " + err.message, 'error');
    return;
  }
  const rows = d.results || [];

  const tableRows = rows.map(r=>`<tr>
    <td class="nowrap">${esc(r.roll_number)}</td><td>${esc(r.student_name)}</td><td>${esc(r.subject_name)}</td>
    <td>${r.obtained}</td><td>${r.percentage}%</td><td>${badge(r.grade,'violet')}</td><td>${statusBadge(r.pass_fail)}</td>
    </tr>`).join('');

  const overlay = openModal({
    title: 'Results — ' + ex.exam.name, wide:true,
    body: `<div class="toolbar" style="margin-bottom:12px"><button type="button" class="btn btn-ghost btn-sm" data-card>Download a Result Card</button></div>
      <div class="table-wrap"><table><thead><tr><th>Roll</th><th>Student</th><th>Subject</th><th>Obtained</th><th>%</th><th>Grade</th><th>Result</th></tr></thead>
      <tbody>${tableRows || '<tr><td colspan="7" class="empty">No results yet</td></tr>'}</tbody></table></div>`,
    saveText: null,
  });

  overlay.querySelector('[data-card]').addEventListener('click', ()=>{
    if(!ex.students.length){ toast('No students','No students in this class','error'); return; }
    openModal({
      title: 'Download Result Card',
      body: selectField('student_id','Student', ex.students.map(s=>({value:s.id,label:s.name+' ('+s.roll_number+')'})), ex.students[0].id),
      saveText: 'Download',
      onSave: async(scope)=>{
        const sid = scope.querySelector('[name="student_id"]').value;
        download(`/api/reports/results/card/pdf?student_id=${sid}&exam_id=${eid}`);
      }
    });
  });
}