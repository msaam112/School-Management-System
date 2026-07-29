'use strict';

PAGES.satt = { title:'Student Attendance', async render(){
  const role = state.user.role;
  const isCI = role === 'class_incharge';
  const isSA = role === 'super_admin';
  const canEdit = isCI;
  const content = document.getElementById('content');

  let classes = [];
  try{
    classes = await classOptions();
  }catch(err){
    content.innerHTML = `<div class="empty">Couldn't load classes. ${esc(err.message)}</div>`;
    return;
  }

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Student Attendance</h2><p>Mark daily attendance · locked after submission (Super Admin can unlock with a reason)</p></div>
    </div>
    <div class="panel"><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        ${selectField('class_id','Class', classes, '')}
        <select class="input" name="section_id" style="max-width:160px"><option value="">All Sections</option></select>
        <input class="input" name="date" type="date" value="${new Date().toISOString().slice(0,10)}" style="max-width:180px">
        <button class="btn btn-primary btn-sm" data-load>Load</button>
      </div>
      <div id="satt-body"><div class="empty">Select a class and click Load.</div></div>
    </div></div>`;

  const clsSel = content.querySelector('[name="class_id"]');
  const secSel = content.querySelector('[name="section_id"]');
  const dateInp = content.querySelector('[name="date"]');
  const loadBtn = content.querySelector('[data-load]');

  async function refreshSections(){
    secSel.innerHTML = '<option value="">Loading sections…</option>';
    secSel.disabled = true;
    try{
      const secs = await api('/api/sections?class_id='+clsSel.value);
      secSel.innerHTML = '<option value="">All Sections</option>' + secs.sections.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
    }catch(err){
      secSel.innerHTML = '<option value="">All Sections</option>';
      toast('Error', 'Could not load sections: ' + err.message, 'error');
    }finally{
      secSel.disabled = false;
    }
  }

  // Any change of class/section/date invalidates the currently displayed
  // table, so it can't be mistaken for reflecting the new selection.
  function markStale(){
    document.getElementById('satt-body').innerHTML = `<div class="empty">Selection changed — click Load to refresh.</div>`;
  }

  clsSel.addEventListener('change', async ()=>{
    await refreshSections();
    markStale();
  });
  secSel.addEventListener('change', markStale);
  dateInp.addEventListener('change', markStale);
  loadBtn.addEventListener('click', load);

  async function load(){
    const cls = clsSel.value, sec = secSel.value, dt = dateInp.value;
    if(!cls){ toast('Select class','Choose a class first','error'); return; }
    if(!dt){ toast('Select date','Choose a date first','error'); return; }

    loadBtn.disabled = true;
    const body = document.getElementById('satt-body');
    body.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

    let d;
    try{
      d = await api(`/api/attendance/student?class_id=${cls}${sec?'&section_id='+sec:''}&date=${dt}`);
    }catch(err){
      body.innerHTML = `<div class="empty">Couldn't load attendance. ${esc(err.message)}</div>`;
      loadBtn.disabled = false;
      return;
    }
    loadBtn.disabled = false;

    const locked = d.locked;
    const banner = locked
      ? `<div class="card" style="background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.35);color:#ffb3b3;padding:12px 16px;margin-bottom:14px;font-size:13px">
           🔒 Attendance for this date is <b>locked</b>. ${isSA ? 'Use "Unlock" below to allow edits.' : 'Contact the Super Admin to unlock it.'}
         </div>`
      : '';
    body.innerHTML = banner + attTable(d.students, locked);
    bindActions(cls, sec, dt, d.students||[]);
  }

  function attTable(students, locked){
    if(!students.length) return `<div class="empty">No students found for this class/section.</div>`;
    const rows = students.map(s => `<tr>
        <td class="nowrap">${esc(s.roll_number||'-')}</td><td>${esc(s.name)}</td>
        <td>${['Present','Absent','Leave'].map(st=>`
          <label style="margin-right:10px;cursor:pointer">
            <input type="radio" name="st_${s.id}" value="${st}" ${s.status===st?'checked':''} ${(locked && !canEdit)?'disabled':''}> ${st}
          </label>`).join('')}
        </td>
        <td class="nowrap"><span class="mark-indicator" data-indicator-for="${s.id}">${s.status ? '✓ Marked' : ''}</span></td>
        </tr>`).join('');

    return `<div class="table-wrap"><table><thead><tr><th>Roll</th><th>Student</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="toolbar" style="margin-top:14px">
        ${isSA && locked ? `<button class="btn btn-success" data-unlock>Unlock (requires reason)</button>` : ''}
        ${canEdit && !locked ? `<button class="btn btn-ghost" data-save-draft>Save Draft</button><button class="btn btn-primary" data-submit>Submit &amp; Lock</button>` : ''}
        <button class="btn btn-ghost" data-pdf>Download PDF</button>
      </div>`;
  }

  function bindActions(cls, sec, dt, students){
    const bodyEl = document.getElementById('satt-body');

    const saveBtn = bodyEl.querySelector('[data-save-draft]');
    const submitBtn = bodyEl.querySelector('[data-submit]');
    const pdfBtn = bodyEl.querySelector('[data-pdf]');
    const unlockBtn = bodyEl.querySelector('[data-unlock]');

    bodyEl.querySelectorAll('input[type=radio]').forEach(r=>{
      r.addEventListener('change', ()=>{
        const studentId = r.name.replace('st_','');
        const indicator = bodyEl.querySelector(`[data-indicator-for="${studentId}"]`);
        if(indicator) indicator.textContent = '✓ Marked';
      });
    });

    const collectRecords = ()=>{
      const records = [];
      bodyEl.querySelectorAll('input[type=radio]:checked').forEach(r=>{
        records.push({ student_id: r.name.replace('st_',''), status: r.value });
      });
      return records;
    };

    if(saveBtn) saveBtn.addEventListener('click', async ()=>{
      saveBtn.disabled = true;
      try{
        await api('/api/attendance/student','POST',{class_id:cls, section_id:sec||null, date:dt, records:collectRecords(), submit:false});
        toast('Saved','Draft saved','success');
        load();
      }catch(err){
        toast('Error', err.message, 'error');
        saveBtn.disabled = false;
      }
    });

    if(submitBtn) submitBtn.addEventListener('click', ()=>{
      const records = collectRecords();
      if(!records.length){ toast('Nothing to submit','Mark at least one student first','error'); return; }

      const missing = students.length - records.length;
      const proceed = async ()=>{
        submitBtn.disabled = true;
        try{
          await api('/api/attendance/student','POST',{class_id:cls, section_id:sec||null, date:dt, records, submit:true});
          toast('Submitted','Attendance locked','success');
          load();
        }catch(err){
          toast('Error', err.message, 'error');
          submitBtn.disabled = false;
        }
      };

      const warningLine = missing > 0 ? `${missing} student(s) are not marked and will be left out. ` : '';
      confirmDialog(
        'Submit & lock attendance',
        `${warningLine}Once submitted, this date locks and only a Super Admin can unlock it. Continue?`,
        proceed
      );
    });

    if(pdfBtn) pdfBtn.addEventListener('click', ()=>{
      download(`/api/reports/attendance/student/pdf?class_id=${cls}${sec?'&section_id='+sec:''}&date=${dt}`);
    });

    if(unlockBtn) unlockBtn.addEventListener('click', ()=>{
      openModal({
        title: 'Unlock Attendance',
        body: field('reason','Reason for unlock','', 'text','e.g. correction of mis-mark'),
        onSave: async(scope)=>{
          const v = getVals(scope);
          const reason = (v.reason||'').trim();
          if(!reason) throw new Error('A reason is mandatory to unlock attendance');
          await api('/api/attendance/unlock','POST',{type:'student', date:dt, class_id:cls, section_id:sec||null, reason});
          toast('Unlocked','Attendance unlocked','success');
          load();
        }
      });
    });
  }

  // Class Incharge: auto-select and lock their own class, then load —
  // properly sequenced so the section dropdown finishes populating first.
  if(isCI){
    try{
      const dd = await api('/api/dashboard');
      if(dd.class_id){
        clsSel.value = dd.class_id;
        clsSel.disabled = true;
        await refreshSections();
        await load();
      }
    }catch(e){
      console.warn('Could not auto-load class incharge attendance:', e.message);
    }
  }
}};