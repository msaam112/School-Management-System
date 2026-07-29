'use strict';

PAGES.backup = { title:'Database Backup', async render(){
  const content = document.getElementById('content');
  if(state.user.role !== 'super_admin'){
    content.innerHTML = '<div class="empty">Access denied.</div>';
    return;
  }

  const lastBackup = PAGES.backup._lastBackupTime || null;

  content.innerHTML = `
    <div class="page-head">
      <div><h2>Database Backup</h2><p>Create a full downloadable backup of all school data</p></div>
      <button class="btn btn-primary" data-backup>Create Backup</button>
    </div>
    <div class="panel"><div class="panel-body">
      <div class="card" style="background:rgba(59,130,246,.1);border-color:rgba(59,130,246,.35);color:#bcd6ff;padding:14px 16px;margin-bottom:14px">
        Backups include students, parents, teachers, attendance, examinations, results, fees, promotions, audit logs, and system settings. Store the downloaded file securely. Larger schools may take a few seconds to generate.
      </div>
      <div id="last-backup-note" class="muted" style="font-size:13px">
        ${lastBackup ? `Last backup this session: ${esc(lastBackup)}` : 'No backup has been created yet this session.'}
      </div>
    </div></div>`;

  const btn = content.querySelector('[data-backup]');
  btn.addEventListener('click', async ()=>{
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Generating…';

    try{
      const r = await fetch('/api/backup', { method:'POST', credentials:'same-origin' });
      if(!r.ok){
        let msg = 'Backup failed (' + r.status + ')';
        try{
          const ct = r.headers.get('content-type')||'';
          if(ct.includes('application/json')){
            const data = await r.json();
            msg = data.error || data.detail || msg;
          }
        }catch(e){ /* keep generic message */ }
        throw new Error(msg);
      }

      const blob = await r.blob();
      const cd = r.headers.get('content-disposition') || '';
      const match = cd.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : 'sms_backup.json';

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);

      const now = new Date().toLocaleString();
      PAGES.backup._lastBackupTime = now;
      const note = document.getElementById('last-backup-note');
      if(note) note.textContent = `Last backup this session: ${now}`;

      toast('Backup created', 'Download started: '+filename, 'success');
    }catch(err){
      toast('Backup failed', err.message, 'error');
    }finally{
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}};