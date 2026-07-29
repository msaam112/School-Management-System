'use strict';

PAGES.audit = { title:'Audit Log', async render(){
  const content = document.getElementById('content');
  if(state.user.role !== 'super_admin'){
    content.innerHTML = '<div class="empty">Access denied.</div>';
    return;
  }

  content.innerHTML = `
    <div class="page-head"><div><h2>Audit Log</h2><p>Chronological record of all critical administrative actions</p></div></div>
    <div class="panel"><div class="panel-head"><h3 id="audit-count">Audit Log</h3></div><div class="panel-body">
      <div class="toolbar" style="margin-bottom:14px">
        <input class="input" id="audit-search" placeholder="Search user, module, action, details…" style="max-width:280px" autocomplete="off">
        <select class="input" id="audit-module-filter" style="max-width:180px"><option value="">All Modules</option></select>
        <select class="input" id="audit-action-filter" style="max-width:180px"><option value="">All Actions</option></select>
      </div>
      <div id="audit-table">${tableSkeletonRows(6)}</div>
    </div></div>`;

  let logs = [];
  try{
    const d = await api('/api/audit');
    logs = d.logs || [];
  }catch(err){
    document.getElementById('audit-table').innerHTML = `<div class="empty">Couldn't load the audit log. ${esc(err.message)}</div>`;
    return;
  }

  // Populate filter dropdowns from the actual data present.
  const modules = [...new Set(logs.map(l=>l.module).filter(Boolean))].sort();
  const actions = [...new Set(logs.map(l=>l.action).filter(Boolean))].sort();
  document.getElementById('audit-module-filter').innerHTML += modules.map(m=>`<option value="${esc(m)}">${esc(m)}</option>`).join('');
  document.getElementById('audit-action-filter').innerHTML += actions.map(a=>`<option value="${esc(a)}">${esc(a)}</option>`).join('');

  function applyFilters(){
    const q = document.getElementById('audit-search').value.trim().toLowerCase();
    const modFilter = document.getElementById('audit-module-filter').value;
    const actFilter = document.getElementById('audit-action-filter').value;

    const filtered = logs.filter(l=>{
      if(modFilter && l.module !== modFilter) return false;
      if(actFilter && l.action !== actFilter) return false;
      if(q){
        const hay = [l.user_name, l.module, l.action, l.description].join(' ').toLowerCase();
        if(!hay.includes(q)) return false;
      }
      return true;
    });

    document.getElementById('audit-count').textContent =
      filtered.length === logs.length ? `Audit Log (${logs.length} entries)` : `Audit Log (${filtered.length} of ${logs.length} entries)`;
    document.getElementById('audit-table').innerHTML = tableHTML(auditColumns(), filtered, 'No matching audit entries.');
  }

  document.getElementById('audit-search').addEventListener('input', debounce(applyFilters, 200));
  document.getElementById('audit-module-filter').addEventListener('change', applyFilters);
  document.getElementById('audit-action-filter').addEventListener('change', applyFilters);

  applyFilters();
}};

const SENSITIVE_ACTIONS = ['delete', 'unlock', 'permission change', 'remove'];
const POSITIVE_ACTIONS = ['create', 'add', 'register'];

function actionBadge(action){
  const a = String(action||'').toLowerCase();
  if(SENSITIVE_ACTIONS.some(s => a.includes(s))) return badge(action, 'red');
  if(POSITIVE_ACTIONS.some(s => a.includes(s))) return badge(action, 'green');
  return badge(action, 'gray');
}

function auditColumns(){
  return [
    {k:'date', l:'Date'}, {k:'time', l:'Time'}, {k:'user_name', l:'User'},
    {k:'role', l:'Role', fmt:r=>badge(r.role,'violet')}, {k:'module', l:'Module'},
    {k:'action', l:'Action', fmt:r=>actionBadge(r.action)}, {k:'description', l:'Details'},
  ];
}