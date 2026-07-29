'use strict';

async function parentStudent(){
  if(!state.studentId){
    throw new Error('Your account isn\'t linked to a student record. Please log out and log back in, or contact the school office.');
  }
  const d = await api('/api/students/'+state.studentId);
  return d.student;
}

function parentPageError(err){
  document.getElementById('content').innerHTML = `<div class="empty">${esc(err.message)}</div>`;
}

/* ============================ MY CHILD (profile) ============================ */
PAGES.mychild = { title:'Student Profile', async render(){
  const content = document.getElementById('content');
  content.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

  let s;
  try{ s = await parentStudent(); }
  catch(err){ parentPageError(err); return; }

  content.innerHTML = `
    <div class="page-head"><div><h2>${esc(s.name)}</h2><p>Student profile</p></div></div>
    <div class="panel"><div class="panel-body"><div class="kv">
      <b>Admission ID</b><span>${esc(s.admission_id||'-')}</span>
      <b>Roll Number</b><span>${esc(s.roll_number||'-')}</span>
      <b>Class</b><span>${esc(s.class_name||'-')} ${esc(s.section_name||'')}</span>
      <b>Gender</b><span>${esc(s.gender||'-')}</span>
      <b>Date of Birth</b><span>${esc(s.dob||'-')}</span>
      <b>Status</b><span>${statusBadge(s.status)}</span>
      <b>Parent</b><span>${esc(s.parent_name||'-')}</span>
      <b>Parent CNIC</b><span>${esc(s.parent_cnic||'-')}</span>
      <b>Parent Phone</b><span>${esc(s.parent_phone||'-')}</span>
    </div></div></div>`;
}};

/* ============================ MY ATTENDANCE ============================ */
PAGES.myatt = { title:'Attendance', async render(){
  const content = document.getElementById('content');
  content.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

  let s, dash;
  try{
    s = await parentStudent();
    dash = await api('/api/dashboard');
  }catch(err){ parentPageError(err); return; }

  const records = dash.attendance || [];
  const rows = records.map(a=>`<tr><td>${esc(a.date||'-')}</td><td>${statusBadge(a.status)}</td></tr>`).join('');

  content.innerHTML = `
    <div class="page-head"><div><h2>Attendance — ${esc(s.name)}</h2><p>${records.length ? `Showing the ${records.length} most recent record(s)` : ''}</p></div></div>
    <div class="panel"><div class="panel-body">
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Status</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="2" class="empty">No attendance records yet</td></tr>'}</tbody></table></div>
    </div></div>`;
}};

/* ============================ MY RESULTS ============================ */
PAGES.myresults = { title:'Results', async render(){
  const content = document.getElementById('content');
  content.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

  let s, d;
  try{
    s = await parentStudent();
    d = await api('/api/results/student?student_id='+state.studentId);
  }catch(err){ parentPageError(err); return; }

  const rows = d.results || [];
  const tableRows = rows.map(r=>`<tr>
    <td>${esc(r.exam_name||'-')}</td><td>${esc(r.subject_name||'-')}</td><td>${r.obtained ?? '-'}</td>
    <td>${r.percentage!=null ? r.percentage+'%' : '-'}</td><td>${badge(r.grade||'-','violet')}</td><td>${statusBadge(r.pass_fail)}</td>
    <td><button class="btn btn-ghost btn-sm" data-card="${r.exam_id}">Card</button></td>
    </tr>`).join('');

  content.innerHTML = `
    <div class="page-head"><div><h2>Results — ${esc(s.name)}</h2></div></div>
    <div class="panel"><div class="panel-body">
      <div class="table-wrap"><table><thead><tr><th>Exam</th><th>Subject</th><th>Obtained</th><th>%</th><th>Grade</th><th>Result</th><th></th></tr></thead>
      <tbody>${tableRows || '<tr><td colspan="7" class="empty">No results yet</td></tr>'}</tbody></table></div>
    </div></div>`;

  content.querySelectorAll('[data-card]').forEach(b=>b.addEventListener('click', ()=>{
    download(`/api/reports/results/card/pdf?student_id=${state.studentId}&exam_id=${b.dataset.card}`, {button:b});
  }));
}};

/* ============================ MY FEES ============================ */
PAGES.myfees = { title:'Fee Challans', async render(){
  const content = document.getElementById('content');
  content.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

  let s, d;
  try{
    s = await parentStudent();
    d = await api('/api/fees/challans');
  }catch(err){ parentPageError(err); return; }

  const rows = d.challans || [];
  const tableRows = rows.map(r=>`<tr>
    <td>${monthName(r.month)} ${r.year}</td><td>${money(r.total)}</td><td>${statusBadge(r.status)}</td>
    <td><button class="btn btn-ghost btn-sm" data-pdf="${r.id}">Download</button></td>
    </tr>`).join('');

  content.innerHTML = `
    <div class="page-head"><div><h2>Fee Challans — ${esc(s.name)}</h2></div></div>
    <div class="panel"><div class="panel-body">
      <div class="table-wrap"><table><thead><tr><th>Month</th><th>Amount</th><th>Status</th><th></th></tr></thead>
      <tbody>${tableRows || '<tr><td colspan="4" class="empty">No challans yet</td></tr>'}</tbody></table></div>
    </div></div>`;

  content.querySelectorAll('[data-pdf]').forEach(b=>b.addEventListener('click', ()=>{
    download('/api/reports/fees/challan/'+b.dataset.pdf+'/pdf', {button:b});
  }));
}};