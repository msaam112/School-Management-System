'use strict';

PAGES.reports = { title:'Reports', async render(){
  const role = state.user.role;
  const content = document.getElementById('content');
  const statuses = [{value:'',label:'All'},{value:'Paid',label:'Paid'},{value:'Unpaid',label:'Unpaid'},{value:'Partially Paid',label:'Partial'}];
  const today = new Date().toISOString().slice(0,10);

  const isAdmin = ['super_admin','principal'].includes(role);
  const isWide = ['super_admin','principal','teacher','class_incharge'].includes(role);

  let classes = [];
  try{
    classes = await classOptions();
  }catch(err){
    content.innerHTML = `<div class="empty">Couldn't load report options. ${esc(err.message)}</div>`;
    return;
  }

  const groups = []; // { title, cards: [...] }

  const studentCards = [];
  if(isWide) studentCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Student List</h3>
      ${selectField('rclass','Class', [{value:'',label:'All Classes'}].concat(classes), '')}
      <button class="btn btn-primary btn-sm" data-r="students" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) studentCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Teacher List</h3>
      <button class="btn btn-primary btn-sm" data-r="teachers" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) studentCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Teacher Assignments</h3>
      <button class="btn btn-primary btn-sm" data-r="teacher-assignments" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) studentCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Class-wise Report</h3>
      <button class="btn btn-primary btn-sm" data-r="classwise" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) studentCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Promotion Report</h3>
      <button class="btn btn-primary btn-sm" data-r="promotions" style="margin-top:10px">Download PDF</button></div>`);
  if(studentCards.length) groups.push({title:'Student & Academic', cards:studentCards});

  const attCards = [];
  if(isWide) attCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Student Attendance</h3>
      ${selectField('attclass','Class', [{value:'',label:'All Classes'}].concat(classes), '')}
      <input class="input" name="attdate" type="date" value="${today}" style="margin:10px 0">
      <button class="btn btn-primary btn-sm" data-r="satt">Download PDF</button></div>`);
  if(isAdmin) attCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Teacher Attendance</h3>
      <input class="input" name="tattdate" type="date" value="${today}" style="margin-bottom:10px">
      <button class="btn btn-primary btn-sm" data-r="tatt">Download PDF</button></div>`);
  if(isAdmin) attCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Attendance Summary</h3>
      <input class="input" name="summarydate" type="date" value="${today}" style="margin-bottom:10px">
      <button class="btn btn-primary btn-sm" data-r="summary">Download PDF</button></div>`);
  if(attCards.length) groups.push({title:'Attendance', cards:attCards});

  const feeCards = [];
  if(isAdmin) feeCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Fee Collection</h3>
      ${selectField('rstatus','Status', statuses, '')}
      <button class="btn btn-primary btn-sm" data-r="fee" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) feeCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Paid Fee Report</h3>
      <button class="btn btn-primary btn-sm" data-r="paidfee" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) feeCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Unpaid Fee Report</h3>
      <button class="btn btn-primary btn-sm" data-r="unpaidfee" style="margin-top:10px">Download PDF</button></div>`);
  if(isAdmin) feeCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Monthly Collection</h3>
      <button class="btn btn-primary btn-sm" data-r="collection" style="margin-top:10px">Download PDF</button></div>`);
  if(feeCards.length) groups.push({title:'Financial', cards:feeCards});

  const sysCards = [];
  if(role==='super_admin') sysCards.push(`
    <div class="card"><h3 style="margin-bottom:10px">Dashboard Statistics</h3>
      <button class="btn btn-primary btn-sm" data-r="dashstats" style="margin-top:10px">Download PDF</button></div>`);
  if(sysCards.length) groups.push({title:'System', cards:sysCards});

  if(!groups.length){
    content.innerHTML = `
      <div class="page-head"><div><h2>Reports</h2></div></div>
      <div class="empty">No reports are available for your role.</div>`;
    return;
  }

  content.innerHTML = `
    <div class="page-head"><div><h2>Reports</h2><p>Generate downloadable PDF reports — click Download, then open the file to view or print</p></div></div>
    ${groups.map(g => `
      <h3 style="margin:18px 0 10px;font-size:15px">${esc(g.title)}</h3>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr));margin-bottom:8px">${g.cards.join('')}</div>
    `).join('')}`;

  content.querySelectorAll('[data-r]').forEach(btn=>btn.addEventListener('click', ()=>{
    const t = btn.dataset.r;

    if(t==='students'){
      const c = content.querySelector('[name="rclass"]').value;
      download('/api/reports/students/pdf'+(c?'?class_id='+c:''), {button:btn});
    } else if(t==='teachers') download('/api/reports/teachers/pdf', {button:btn});
    else if(t==='teacher-assignments') download('/api/reports/teacher-assignments/pdf', {button:btn});
    else if(t==='satt'){
      const c = content.querySelector('[name="attclass"]').value;
      const dt = content.querySelector('[name="attdate"]').value;
      if(!dt){ toast('Pick a date', 'Choose a date for the attendance report', 'error'); return; }
      download(`/api/reports/attendance/student/pdf?${c?'class_id='+c+'&':''}date=${dt}`, {button:btn});
    } else if(t==='tatt'){
      const dt = content.querySelector('[name="tattdate"]').value;
      if(!dt){ toast('Pick a date', 'Choose a date for the attendance report', 'error'); return; }
      download(`/api/reports/attendance/teacher/pdf?date=${dt}`, {button:btn});
    } else if(t==='summary'){
      const dt = content.querySelector('[name="summarydate"]').value;
      if(!dt){ toast('Pick a date', 'Choose a date for the summary', 'error'); return; }
      download(`/api/reports/attendance-summary/pdf?date=${dt}`, {button:btn});
    } else if(t==='classwise') download('/api/reports/class-wise/pdf', {button:btn});
    else if(t==='dashstats') download('/api/reports/dashboard-stats/pdf', {button:btn});
    else if(t==='promotions') download('/api/reports/promotions/pdf', {button:btn});
    else if(t==='fee'){
      const s = content.querySelector('[name="rstatus"]').value;
      download('/api/fees/report/pdf'+(s?'?status='+encodeURIComponent(s):''), {button:btn});
    } else if(t==='paidfee') download('/api/reports/fees/paid/pdf', {button:btn});
    else if(t==='unpaidfee') download('/api/reports/fees/unpaid/pdf', {button:btn});
    else if(t==='collection') download('/api/reports/fees/collection/pdf', {button:btn});
  }));
}};