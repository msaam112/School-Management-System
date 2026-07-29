'use strict';

/* Small reusable animated counter — counts up from 0 to the target value.
   Skips animation for non-numeric values (names, "Yes/No", etc.) since
   those don't make sense to "count up". */
function animateCount(el, target){
  const num = Number(target);
  if(el === null || isNaN(num)){ el.textContent = target; return; }
  const duration = 700;
  const start = performance.now();
  function tick(now){
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = Math.round(num * eased).toLocaleString();
    if(progress < 1) requestAnimationFrame(tick);
    else el.textContent = num.toLocaleString();
  }
  requestAnimationFrame(tick);
}

function greeting(){
  const h = new Date().getHours();
  if(h < 12) return 'Good morning';
  if(h < 17) return 'Good afternoon';
  return 'Good evening';
}

function dashboardSkeleton(){
  const card = `<div class="card stat" style="pointer-events:none">
    <div style="height:32px;width:60%;background:var(--border,#333);border-radius:6px;opacity:.35;animation:pulseSkeleton 1.4s ease-in-out infinite"></div>
    <div style="height:12px;width:40%;margin-top:10px;background:var(--border,#333);border-radius:4px;opacity:.25;animation:pulseSkeleton 1.4s ease-in-out infinite"></div>
  </div>`;
  return `<div style="height:18px;width:220px;background:var(--border,#333);border-radius:6px;opacity:.25;margin-bottom:20px;animation:pulseSkeleton 1.4s ease-in-out infinite"></div>
    <div class="grid stats-grid">${card.repeat(4)}</div>`;
}

PAGES.dashboard = { title:'Dashboard', async render(){
  const c=document.getElementById('content');
  c.innerHTML = dashboardSkeleton();

  let d;
  try{
    d = await api('/api/dashboard');
  }catch(err){
    c.innerHTML = `<div class="empty">Couldn't load the dashboard. ${esc(err.message)}</div>`;
    return;
  }
  state.school=d.school||{};
  refreshBrand();

  const role=d.role;
  const stats = d.stats || {};
  const todayAtt = d.today_attendance || {};

  // id lets us target each number for the count-up animation after insertion.
  let statId = 0;
  const stat=(v,l,col,animated=true)=>{
    const id = `stat-${statId++}`;
    return `<div class="card stat">
      <div class="v" id="${id}" style="color:${esc(col)}" data-animated="${animated}" data-target="${esc(String(v))}">${animated?0:esc(v)}</div>
      <div class="l">${esc(l)}</div>
    </div>`;
  };

  let cards='';
  let statusChip = '';

  if(role==='super_admin'){
    cards = stat(stats.students ?? 0,'Students','#6d5efc')
          + stat(stats.teachers ?? 0,'Teachers','#22d3ee')
          + stat(stats.classes ?? 0,'Classes','#f59e0b')
          + stat(stats.parents ?? 0,'Parents','#22c55e')
          + stat((todayAtt.present ?? 0)+'/'+(todayAtt.total ?? 0),'Present Today','#3b82f6', false)
          + stat(stats.pending_fees ?? 0,'Pending Fees','#ef4444');
  } else if(role==='principal'){
    cards = stat(d.students ?? 0,'Students','#6d5efc')
          + stat(d.teacher_attendance_today ?? 0,'Teacher Attendance Today','#22d3ee')
          + stat(d.exams ?? 0,'Exams','#f59e0b')
          + stat(d.classes ?? 0,'Classes','#22c55e');
  } else if(role==='teacher'){
    const assignments = d.assignments||[];
    cards = stat(assignments.length,'Subjects Assigned','#6d5efc')
          + stat(new Set(assignments.map(a=>a.class_id)).size,'Classes','#22d3ee')
          + stat((d.exams||[]).length,'Exams','#f59e0b');
  } else if(role==='class_incharge'){
    const present = todayAtt.present ?? null;
    const total = todayAtt.total ?? null;
    cards = stat(d.students ?? 0,'Students','#6d5efc')
          + stat((present!=null && total!=null) ? `${present}/${total}` : '-','Present Today','#22d3ee', false)
          + stat(d.class_id?'Yes':'No','Class Assigned','#22c55e', false);
    if(present!=null && total!=null){
      statusChip = present === total && total > 0
        ? `<span class="badge green">🔥 Attendance fully marked today</span>`
        : `<span class="badge amber">⏳ Attendance pending for today</span>`;
    }
  } else if(role==='parent'){
    const s=d.student||{};
    const hasDue = (d.fees||[]).some(f=>f.status!=='Paid');
    cards = stat(s.name||'-','Child','#6d5efc', false)
          + stat(((s.class_name||'')+' '+(s.section_name||'')).trim()||'-','Class','#22d3ee', false)
          + stat(hasDue?'Due':'Clear','Fee Status','#f59e0b', false)
          + stat((d.attendance&&d.attendance[0])?d.attendance[0].status:'-','Last Attendance','#22c55e', false);
    statusChip = hasDue
      ? `<span class="badge red">A fee payment is currently due</span>`
      : `<span class="badge green">✓ All fees up to date</span>`;
  } else {
    cards = `<div class="empty">No dashboard data is configured for this role yet.</div>`;
  }

  const qa = quickActions(role);

  c.innerHTML=`
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:6px">
      <div style="color:var(--muted);font-size:15px">${greeting()}, <b style="color:var(--text)">${esc(d.name||'User')}</b> — here is your ${esc((role||'').replace('_',' '))} overview.</div>
      ${statusChip}
    </div>
    <div class="grid stats-grid" style="margin-top:16px">${cards}</div>
    ${qa ? `<div class="panel"><div class="panel-head"><h3>Quick Actions</h3></div><div class="panel-body toolbar">${qa}</div></div>` : ''}`;

  // Trigger the count-up animation for every numeric stat now that the
  // elements are actually in the DOM.
  c.querySelectorAll('[data-animated="true"]').forEach(el=>{
    animateCount(el, el.dataset.target);
  });

  c.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.nav)));
}};

function quickActions(role){
  const map={
    super_admin:[['students','Manage Students','students'],['satt','Mark Attendance','satt'],['exams','Examinations','exams'],['challans','Fee Challans','challans'],['backup','Backup DB','backup'],['settings','Settings','settings']],
    principal:[['tatt','Teacher Attendance','tatt'],['exams','Examinations','exams'],['reports','Reports','reports'],['students','Students','students']],
    teacher:[['exams','Enter Marks','exams'],['students','My Students','students'],['reports','Reports','reports']],
    class_incharge:[['satt','Student Attendance','satt'],['students','My Students','students'],['exams','Examinations','exams']],
    parent:[['mychild','Profile','mychild'],['myatt','Attendance','myatt'],['myresults','Results','myresults'],['myfees','Challans','myfees']]
  };
  const items = map[role]||[];
  if(!items.length) return '';
  return items.map(([k,l,icon])=>
    `<button class="btn btn-ghost btn-sm" data-nav="${k}">${typeof navIcon==='function'?navIcon(icon):''}${esc(l)}</button>`
  ).join('');
}