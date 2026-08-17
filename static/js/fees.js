'use strict';

function monthName(n){
  const m=['','January','February','March','April','May','June','July','August','September','October','November','December'];
  return m[parseInt(n)]||n;
}

/* ============================ FEE STRUCTURES ============================ */
PAGES.feestruct = { title:'Fee Structures', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const myToken = (PAGES.feestruct._token = (PAGES.feestruct._token||0) + 1);

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Fee Structures</h2><p>Per-class fee configuration used for automatic monthly challans</p></div>
      ${canWrite?`<button class="btn btn-primary" data-add>+ Add Fee Structure</button>`:''}
    </div>
    <div class="panel"><div class="panel-head"><h3 id="fs-count">Fee Structures</h3></div>
    <div class="panel-body" id="fs-table">${tableSkeletonRows(canWrite?6:5)}</div></div>`;

  let rows = [], classes = [];
  try{
    const [d, cls] = await Promise.all([api('/api/fee-structures'), classOptions()]);
    if(myToken !== PAGES.feestruct._token) return;
    rows = d.structures || []; classes = cls;
  }catch(err){
    if(myToken !== PAGES.feestruct._token) return;
    document.getElementById('fs-table').innerHTML = `<div class="empty">Couldn't load fee structures. ${esc(err.message)}</div>`;
    return;
  }

  document.getElementById('fs-count').textContent = `Fee Structures (${rows.length})`;
  document.getElementById('fs-table').innerHTML = tableHTML(feeStructColumns(canWrite), rows, 'No fee structures yet.');
  bindFeeStructTable(content, rows, canWrite, classes);

  if(canWrite){
    content.querySelector('[data-add]').addEventListener('click', ()=>openFeeStructModal(null, classes, rows));
  }
}};

function feeStructColumns(canWrite){
  const cols = [
    {k:'class_name', l:'Class'},
    {k:'admission_fee', l:'Admission', fmt:r=>money(r.admission_fee)},
    {k:'tuition_fee', l:'Tuition', fmt:r=>money(r.tuition_fee)},
    {k:'exam_fee', l:'Exam', fmt:r=>money(r.exam_fee)},
    {k:'custom_fee', l:'Other', fmt:r=>r.custom_fee?`${money(r.custom_fee)} (${esc(r.custom_name||'')})`:'-'},
  ];
  if(canWrite){
    cols.push({k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-edit="${r.id}" onclick="event.stopPropagation()">Edit</button> <button class="btn btn-danger btn-sm" data-del="${r.id}" onclick="event.stopPropagation()">Delete</button>`});
  }
  return cols;
}

function bindFeeStructTable(content, rows, canWrite, classes){
  if(!canWrite) return;

  const openEdit = (id)=>{
    const r = rows.find(x=>x.id===id);
    if(r) openFeeStructModal(r, classes, rows);
  };
  content.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click', ()=>openEdit(b.dataset.edit)));
  content.querySelectorAll('tbody tr').forEach((tr,i)=>{
    if(!rows[i]) return;
    tr.style.cursor='pointer';
    tr.addEventListener('click', ()=>openEdit(rows[i].id));
  });

  content.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.del);
    confirmDialog('Delete fee structure', `Remove the fee structure for ${r?r.class_name:'this class'}? Future challans won't auto-generate for this class until a new one is added.`, async()=>{
      const result = await api('/api/fee-structures/'+b.dataset.del, 'DELETE');
      if(result.warning){
        toast('Removed (with a note)', result.warning, 'error');
      } else {
        toast('Deleted','Fee structure removed','success');
      }
      PAGES.feestruct.render();
    });
  }));
}

function openFeeStructModal(rec, classes, existingRows=[]){
  const body = `
    ${rec ? '' : selectField('class_id','Class', classes, classes[0]?classes[0].value:'')}
    <div class="row3">
      ${field('admission_fee','Admission Fee', rec?rec.admission_fee:0, 'number')}
      ${field('tuition_fee','Tuition Fee', rec?rec.tuition_fee:0, 'number')}
      ${field('exam_fee','Exam Fee', rec?rec.exam_fee:0, 'number')}
    </div>
    <div class="row2">
      ${field('custom_name','Other Fee Name', rec?rec.custom_name:'', 'text','Lab Fee')}
      ${field('custom_fee','Other Fee Amount', rec?rec.custom_fee:0, 'number')}
    </div>
  `;
  openModal({
    title: rec ? 'Edit Fee Structure' : 'Add Fee Structure', body, wide:true,
    onSave: async(scope)=>{
      const v = getVals(scope);

      if(!rec){
        const dup = existingRows.find(fs => fs.class_id === v.class_id);
        if(dup) throw new Error('This class already has a fee structure — edit it instead of adding a new one.');
      }

      const amounts = {
        admission_fee: parseFloat(v.admission_fee), tuition_fee: parseFloat(v.tuition_fee),
        exam_fee: parseFloat(v.exam_fee), custom_fee: parseFloat(v.custom_fee),
      };
      for(const [key, val] of Object.entries(amounts)){
        if(isNaN(val) || val < 0) throw new Error(`${key.replace('_',' ')} must be a non-negative number`);
      }

      const payload = { ...amounts, custom_name: v.custom_name };
      if(rec){
        await api('/api/fee-structures/'+rec.id, 'PUT', payload);
        toast('Updated','Fee structure saved','success');
      } else {
        payload.class_id = v.class_id;
        await api('/api/fee-structures','POST', payload);
        toast('Added','Fee structure created','success');
      }
      PAGES.feestruct.render();
    }
  });
}

/* ============================ FEE CHALLANS ============================ */
PAGES.challans = { title:'Fee Challans', async render(){
  const canWrite = state.user.role === 'super_admin';
  const content = document.getElementById('content');
  const statusOpts = [{value:'',label:'All'},{value:'Paid',label:'Paid'},{value:'Unpaid',label:'Unpaid'},{value:'Partially Paid',label:'Partial'}];

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Fee Challans</h2><p>Auto-generated monthly challans, manual charges &amp; payments</p></div>
      ${canWrite?`<button class="btn btn-primary" data-gen>+ Generate Challans</button>`:''}
    </div>
    <div class="panel"><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        ${selectField('status','Status', statusOpts, '')}
        <button class="btn btn-ghost btn-sm" data-filter>Filter</button>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" data-reppdf>Collection Report PDF</button>
      </div>
      <div id="challan-list">${tableSkeletonRows(canWrite?7:5)}</div>
    </div></div>`;

  let classes = [];
  try{ classes = await classOptions(); }catch(e){ /* non-fatal for this page */ }

  async function draw(){
    const list = content.querySelector('#challan-list');
    list.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
    const st = content.querySelector('[name="status"]').value;
    try{
      const dd = await api('/api/fees/challans' + (st?'?status='+encodeURIComponent(st):''));
      list.innerHTML = tableHTML(challanColumns(canWrite), dd.challans, 'No challans yet. Generate for a month.');
      bindChallanList(list, canWrite, dd.challans);
    }catch(err){
      list.innerHTML = `<div class="empty">Couldn't load challans. ${esc(err.message)}</div>`;
    }
  }
  await draw();

  content.querySelector('[data-filter]').addEventListener('click', draw);
  content.querySelector('[name="status"]').addEventListener('change', draw);
  content.querySelector('[data-reppdf]').addEventListener('click', ()=>download('/api/reports/fees/collection/pdf'));

  if(canWrite){
    content.querySelector('[data-gen]').addEventListener('click', ()=>openGenerateModal(classes, draw));
  }
}};

function challanColumns(canWrite){
  const cols = [
    {k:'roll_number', l:'Roll'}, {k:'student_name', l:'Student'}, {k:'class_name', l:'Class'},
    {k:'month', l:'Month', fmt:r=>monthName(r.month)+' '+r.year},
    {k:'total', l:'Amount', fmt:r=>money(r.total)},
    {k:'status', l:'Status', fmt:r=>statusBadge(r.status)},
    {k:'_a', l:'', nowrap:true, fmt:r=>`<button class="btn btn-ghost btn-sm" data-pdf="${r.id}">PDF</button>
      ${canWrite?`<button class="btn btn-ghost btn-sm" data-manual="${r.id}">+Charge</button><button class="btn btn-success btn-sm" data-pay="${r.id}">Pay</button>`:''}`},
  ];
  return cols;
}

function bindChallanList(list, canWrite, rows){
  list.querySelectorAll('[data-pdf]').forEach(b=>b.addEventListener('click', ()=>download('/api/reports/fees/challan/'+b.dataset.pdf+'/pdf')));
  if(!canWrite) return;
  list.querySelectorAll('[data-manual]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.manual);
    openManualChargeModal(b.dataset.manual, r, ()=>PAGES.challans.render());
  }));
  list.querySelectorAll('[data-pay]').forEach(b=>b.addEventListener('click', ()=>{
    const r = rows.find(x=>x.id===b.dataset.pay);
    openPayModal(b.dataset.pay, r, ()=>PAGES.challans.render());
  }));
}

function openGenerateModal(classes, onDone){
  const body = `
    ${field('month','Month (1-12)', String(new Date().getMonth()+1), 'number','7')}
    ${field('year','Year', String(new Date().getFullYear()), 'number','2026')}
    ${selectField('class_id','Class (optional)', [{value:'',label:'All Classes'}].concat(classes), '')}
    <p class="hint">If a class has no fee structure configured yet (see the Fee Structures page), no challans will be generated for its students.</p>
  `;
  openModal({
    title: 'Generate Monthly Challans', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      const month = parseInt(v.month), year = parseInt(v.year);
      if(isNaN(month) || month < 1 || month > 12) throw new Error('Month must be between 1 and 12');
      if(isNaN(year) || year < 2000) throw new Error('Enter a valid year');

      const r = await api('/api/fees/generate','POST', {month, year, class_id: v.class_id||null});
      if(r.count === 0){
        toast('No new challans generated',
          'Every eligible student already has a challan for this period, or the selected class(es) have no fee structure configured yet.',
          'error');
      } else {
        toast('Generated', r.message, 'success');
      }
      onDone();
    }
  });
}

function openManualChargeModal(chid, challan, onDone){
  const context = challan
    ? `<p class="hint" style="margin-bottom:14px">Adding a charge to <b>${esc(challan.student_name)}</b>'s ${monthName(challan.month)} ${challan.year} challan (current total: ${money(challan.total)}).</p>`
    : '';
  const body = context + `
    ${selectField('charge_type','Type', [{value:'Fine',label:'Fine'},{value:'Transport',label:'Transport'},{value:'Library',label:'Library'},{value:'Extra Exam',label:'Extra Exam'},{value:'Custom',label:'Custom'}], 'Fine')}
    ${field('amount','Amount','', 'number')}
    ${textareaField('description','Description','')}
  `;
  openModal({
    title: 'Add Manual Charge', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      const amount = parseFloat(v.amount);
      if(isNaN(amount) || amount <= 0) throw new Error('Enter a valid amount greater than zero');
      const result = await api('/api/fees/challan/'+chid+'/manual','POST', {charge_type:v.charge_type, description:v.description, amount});
      if(result.note){
        toast('Charge added — status updated', result.note, 'error');
      } else {
        toast('Added','Charge added','success');
      }
      onDone();
    }
  });
}

function openPayModal(chid, challan, onDone){
  const context = challan
    ? `<p class="hint" style="margin-bottom:14px"><b>${esc(challan.student_name)}</b> — ${monthName(challan.month)} ${challan.year} — Total: ${money(challan.total)} — Currently: ${challan.status} (Rs. ${challan.amount_paid||0} paid so far)</p>`
    : '';
  const body = context
    + selectField('status','New Status', [{value:'Paid',label:'Paid'},{value:'Unpaid',label:'Unpaid'},{value:'Partially Paid',label:'Partially Paid'}], challan?challan.status:'Paid')
    + `<div class="field" id="partial-amount-wrap" style="${challan && challan.status==='Partially Paid' ? '' : 'display:none'}">
         <label>Amount Paid</label>
         <input class="input" name="amount_paid" type="number" min="0" value="${challan?challan.amount_paid||'':''}">
       </div>`;
  const overlay = openModal({
    title: 'Update Payment', body,
    onSave: async(scope)=>{
      const v = getVals(scope);
      const payload = { status: v.status };
      if(v.status === 'Partially Paid'){
        const amt = parseFloat(v.amount_paid);
        if(isNaN(amt) || amt <= 0) throw new Error('Enter a valid amount paid for a partial payment');
        payload.amount_paid = amt;
      }
      const result = await api('/api/fees/challan/'+chid+'/pay','POST', payload);
      toast('Updated','Payment status set','success');
      onDone();
    }
  });

  const statusSel = overlay.querySelector('[name="status"]');
  const partialWrap = overlay.querySelector('#partial-amount-wrap');
  statusSel.addEventListener('change', ()=>{
    partialWrap.style.display = statusSel.value === 'Partially Paid' ? '' : 'none';
  });
}