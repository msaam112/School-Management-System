'use strict';

PAGES.promotions = { title:'Promotions', async render(){
  const canWrite = ['super_admin','principal'].includes(state.user.role);
  const content = document.getElementById('content');
  const myToken = (PAGES.promotions._token = (PAGES.promotions._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Student Promotion</h2><p>Promote eligible students to the next class (based on latest exam results); failed students are automatically retained unless overridden</p></div>
      ${canWrite?`<button class="btn btn-primary" data-promote>Promote Students</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="promo-count">Promotion History</h3></div>
    <div class="panel-body" id="promo-table">${tableSkeletonRows(6)}</div></div>`;

  let rows = [], classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/promotions'), classOptions()]);
    if(myToken !== PAGES.promotions._token) return;
    rows = d.promotions || []; classes = cls;
  }catch(err){
    if(myToken !== PAGES.promotions._token) return;
    document.getElementById('promo-table').innerHTML = `<div class="empty">Couldn't load promotion history. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('promo-count').textContent = `Promotion History (${rows.length})`;
  document.getElementById('promo-table').innerHTML = tableHTML(promotionColumns(), rows, 'No promotions recorded yet.');

  if(canWrite){
    content.querySelector('[data-promote]').addEventListener('click', ()=>openPromoteModal(classes));
  }
}};

function promotionColumns(){
  return [
    {k:'student_name', l:'Student'}, {k:'from_name', l:'From'}, {k:'to_name', l:'To'},
    {k:'academic_year', l:'Year'}, {k:'status', l:'Status', fmt:r=>statusBadge(r.status)},
    {k:'promoted_at', l:'When'},
  ];
}

async function openPromoteModal(classes){
  const overlay = openModal({
    title: 'Promote Students', wide:true,
    body: `
      ${field('academic_year','Academic Year', String(new Date().getFullYear()), 'text')}
      <div class="row2">
        ${selectField('from_class','From Class', classes, classes[0]?classes[0].value:'')}
        ${selectField('to_class','To Class', classes, classes[1]?classes[1].value:(classes[0]?classes[0].value:''))}
      </div>
      <div class="error-text" id="same-class-warning" hidden>From and To class are the same — this will move students within the same class listing, which is unusual. Double-check before continuing.</div>
      <div class="field"><label>Override eligibility (promote even failing students)</label>
        <select class="input" name="override"><option value="">No — respect exam results</option><option value="true">Yes — promote everyone selected</option></select>
      </div>
      <div id="promo-hint" class="hint" style="margin-bottom:10px">Students who failed their most recent exam for this class will be marked "Retained" unless you enable the override above.</div>
      <div class="toolbar" style="margin-bottom:10px">
        <button type="button" class="btn btn-ghost btn-sm" data-select-all>Select All</button>
        <button type="button" class="btn btn-ghost btn-sm" data-select-eligible>Select Eligible Only</button>
        <button type="button" class="btn btn-ghost btn-sm" data-select-none>Clear</button>
        <span class="spacer"></span>
        <span class="muted" id="selection-summary" style="font-size:12.5px"></span>
      </div>
      <div id="stu-pick" class="toolbar" style="flex-wrap:wrap;gap:8px"></div>
    `,
    onSave: async(scope)=>{
      const v = getVals(scope);
      const picked = [...scope.querySelectorAll('#stu-pick input:checked')].map(i=>i.value);
      if(!picked.length) throw new Error('Select at least one student');
      const promotions = picked.map(sid => ({ student_id: sid, to_class_id: v.to_class, override: v.override === 'true' }));
      const r = await api('/api/promote','POST', {academic_year: v.academic_year, promotions});
      toast('Processed', r.message, 'success');
      PAGES.promotions.render();
    }
  });

  const fc = overlay.querySelector('[name="from_class"]');
  const tc = overlay.querySelector('[name="to_class"]');
  const sameWarning = overlay.querySelector('#same-class-warning');
  let studentStatus = {}; // student_id -> 'Pass' | 'Fail' | null (no exam yet)

  function checkSameClass(){
    sameWarning.hidden = fc.value !== tc.value;
  }
  fc.addEventListener('change', checkSameClass);
  tc.addEventListener('change', checkSameClass);
  checkSameClass();

  function updateSummary(){
    const boxes = [...overlay.querySelectorAll('#stu-pick input[type=checkbox]')];
    const checked = boxes.filter(b=>b.checked);
    const failing = checked.filter(b=>studentStatus[b.value] === 'Fail');
    const summary = overlay.querySelector('#selection-summary');
    if(!checked.length){ summary.textContent = 'No students selected'; return; }
    summary.textContent = failing.length
      ? `${checked.length} selected — ${failing.length} currently failing`
      : `${checked.length} selected — all currently eligible`;
    summary.style.color = failing.length ? 'var(--danger,#ef4444)' : '';
  }

  async function loadStudents(){
    const box = overlay.querySelector('#stu-pick');
    box.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

    let students;
    try{
      const d = await api('/api/students?class_id='+fc.value);
      students = d.students || [];
    }catch(err){
      box.innerHTML = `<span class="error-text">Couldn't load students: ${esc(err.message)}</span>`;
      return;
    }

    if(!students.length){
      box.innerHTML = `<span class="muted">No students in this class.</span>`;
      updateSummary();
      return;
    }

    // Fetch each student's most recent result to determine pass/fail eligibility.
    // Done in parallel; a failure for any one student just leaves their status unknown
    // rather than blocking the whole picker.
    studentStatus = {};
    await Promise.all(students.map(async s=>{
      try{
        const r = await api('/api/results/student?student_id='+s.id);
        const results = r.results || [];
        if(!results.length){ studentStatus[s.id] = null; return; }
        // Most recent exam's results — assume the API returns most-recent-first;
        // fall back to checking all entries for any Fail if ordering is uncertain.
        studentStatus[s.id] = results.some(x => x.pass_fail === 'Fail') ? 'Fail' : 'Pass';
      }catch(e){ studentStatus[s.id] = null; }
    }));

    box.innerHTML = students.map(s => {
      const status = studentStatus[s.id];
      const statusLabel = status === 'Fail' ? ' — Failing' : status === 'Pass' ? ' — Passing' : ' — No results yet';
      const color = status === 'Fail' ? 'var(--danger,#ef4444)' : status === 'Pass' ? 'var(--success,#22c55e)' : 'var(--muted)';
      return `<label class="badge gray" style="cursor:pointer;padding:6px 12px">
        <input type="checkbox" value="${s.id}" style="margin-right:6px">${esc(s.name)} (${esc(s.roll_number)})
        <span style="color:${color};font-size:11px">${statusLabel}</span>
      </label>`;
    }).join('');

    box.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change', updateSummary));
    updateSummary();
  }

  overlay.querySelector('[data-select-all]').addEventListener('click', ()=>{
    overlay.querySelectorAll('#stu-pick input[type=checkbox]').forEach(cb=>cb.checked=true);
    updateSummary();
  });
  overlay.querySelector('[data-select-eligible]').addEventListener('click', ()=>{
    overlay.querySelectorAll('#stu-pick input[type=checkbox]').forEach(cb=>{
      cb.checked = studentStatus[cb.value] !== 'Fail';
    });
    updateSummary();
  });
  overlay.querySelector('[data-select-none]').addEventListener('click', ()=>{
    overlay.querySelectorAll('#stu-pick input[type=checkbox]').forEach(cb=>cb.checked=false);
    updateSummary();
  });

  fc.addEventListener('change', loadStudents);
  await loadStudents();
}