'use strict';

PAGES.tatt = { title:'Teacher Attendance', async render(){
  const role = state.user.role;
  const canEdit = role === 'principal' || role === 'super_admin';
  const isSA = role === 'super_admin';
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Teacher Attendance</h2><p>${canEdit ? 'Mark and submit teacher attendance (Principal, or Super Admin if not yet submitted).' : 'View teacher attendance.'}</p></div>
    </div>
    <div class="panel"><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        <input class="input" name="date" type="date" value="${new Date().toISOString().slice(0,10)}" style="max-width:180px">
        <button class="btn btn-primary btn-sm" data-load>Load</button>
      </div>
      <div id="tatt-body"><div class="empty">Pick a date and click Load.</div></div>
    </div></div>`;

  const dateInp = content.querySelector('[name="date"]');
  const loadBtn = content.querySelector('[data-load]');
  loadBtn.addEventListener('click', load);

  async function load(){
    const dt = dateInp.value;
    if(!dt){ toast('Pick a date', 'Choose a date before loading', 'error'); return; }

    loadBtn.disabled = true;
    const body = document.getElementById('tatt-body');
    body.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

    let d;
    try{
      d = await api('/api/attendance/teacher?date='+dt);
    }catch(err){
      body.innerHTML = `<div class="empty">Couldn't load attendance. ${esc(err.message)}</div>`;
      loadBtn.disabled = false;
      return;
    }
    loadBtn.disabled = false;

    const locked = d.locked;
    const rows = (d.teachers||[]);

    if(!rows.length){
      body.innerHTML = `<div class="empty">No teacher records found.</div>`;
      return;
    }

    const banner = locked
      ? `<div class="card" style="background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.35);color:#ffb3b3;padding:12px 16px;margin-bottom:14px;font-size:13px">
           🔒 Teacher attendance for this date is <b>locked</b>. ${isSA ? 'Use "Unlock" below to allow edits.' : 'Contact the Super Admin to unlock it.'}
         </div>`
      : '';

    const tableRows = rows.map(t => `<tr data-row-for="${t.id}">
        <td class="nowrap">${esc(t.employee_id||'-')}</td><td>${esc(t.name)}</td>
        <td>${['Present','Absent','Leave'].map(st=>`
          <label style="margin-right:10px;cursor:pointer">
            <input type="radio" name="tt_${t.id}" value="${st}" ${t.status===st?'checked':''} ${(locked && !isSA)?'disabled':''}> ${st}
          </label>`).join('')}
        </td>
        <td class="nowrap"><span class="mark-indicator" data-indicator-for="${t.id}">${t.status ? '✓ Marked' : ''}</span></td>
        </tr>`).join('');

    body.innerHTML = banner + `<div class="table-wrap"><table><thead><tr><th>Emp ID</th><th>Teacher</th><th>Status</th><th></th></tr></thead><tbody>${tableRows}</tbody></table></div>
      <div class="toolbar" style="margin-top:14px">
        ${canEdit && !locked ? `<button class="btn btn-ghost" data-draft>Save Draft</button><button class="btn btn-primary" data-submit>Submit &amp; Lock</button>` : ''}
        ${isSA && locked ? `<button class="btn btn-success" data-unlock>Unlock (requires reason)</button>` : ''}
        <button class="btn btn-ghost" data-pdf>Download PDF</button>
      </div>`;

    bindActions(dt, rows);
  }

  function bindActions(dt, rows){
    const bodyEl = document.getElementById('tatt-body');
    const draftBtn = bodyEl.querySelector('[data-draft]');
    const submitBtn = bodyEl.querySelector('[data-submit]');
    const pdfBtn = bodyEl.querySelector('[data-pdf]');
    const unlockBtn = bodyEl.querySelector('[data-unlock]');

    // Live "marked" indicator so it's obvious at a glance who still needs attention.
    bodyEl.querySelectorAll('input[type=radio]').forEach(r=>{
      r.addEventListener('change', ()=>{
        const teacherId = r.name.replace('tt_','');
        const indicator = bodyEl.querySelector(`[data-indicator-for="${teacherId}"]`);
        if(indicator) indicator.textContent = '✓ Marked';
      });
    });

    const collectRecords = ()=>{
      const records = [];
      bodyEl.querySelectorAll('input[type=radio]:checked').forEach(r=>{
        records.push({ teacher_id: r.name.replace('tt_',''), status: r.value });
      });
      return records;
    };

    const unmarkedCount = ()=> rows.length - collectRecords().length;

    if(draftBtn) draftBtn.addEventListener('click', async ()=>{
      draftBtn.disabled = true;
      try{
        await api('/api/attendance/teacher','POST',{date:dt, records:collectRecords(), submit:false});
        toast('Saved','Draft saved','success');
        load();
      }catch(err){
        toast('Error', err.message, 'error');
        draftBtn.disabled = false;
      }
    });

    if(submitBtn) submitBtn.addEventListener('click', ()=>{
      const records = collectRecords();
      if(!records.length){ toast('Nothing to submit','Mark at least one teacher first','error'); return; }

      const missing = unmarkedCount();
      const proceed = async ()=>{
        submitBtn.disabled = true;
        try{
          await api('/api/attendance/teacher','POST',{date:dt, records, submit:true});
          toast('Submitted','Teacher attendance locked','success');
          load();
        }catch(err){
          toast('Error', err.message, 'error');
          submitBtn.disabled = false;
        }
      };

      const warningLine = missing > 0
        ? `${missing} teacher(s) are not marked and will be left out. `
        : '';
      confirmDialog(
        'Submit & lock attendance',
        `${warningLine}Once submitted, this date locks and only a Super Admin can unlock it. Continue?`,
        proceed
      );
    });

    if(pdfBtn) pdfBtn.addEventListener('click', ()=>{
      download(`/api/reports/attendance/teacher/pdf?date=${dt}`);
    });

    if(unlockBtn) unlockBtn.addEventListener('click', ()=>{
      openModal({
        title: 'Unlock Teacher Attendance',
        body: field('reason','Reason for unlock','', 'text','e.g. correction needed'),
        onSave: async(scope)=>{
          const v = getVals(scope);
          const reason = (v.reason||'').trim();
          if(!reason) throw new Error('A reason is mandatory to unlock attendance');
          await api('/api/attendance/unlock','POST',{type:'teacher', date:dt, reason});
          toast('Unlocked','Teacher attendance unlocked','success');
          load();
        }
      });
    });
  }
}};