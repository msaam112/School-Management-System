'use strict';

/* Inline SVG icon set — self-contained, no CDN dependency, no risk of a
   mistyped icon name silently failing to render. Uses currentColor so
   icons automatically match the surrounding text color/theme. */
const NAV_ICONS = {
  dashboard: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  students: '<path d="M22 10 12 5 2 10l10 5 10-5Z"/><path d="M6 12v5c0 1.5 2.5 3 6 3s6-1.5 6-3v-5"/>',
  parents: '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><path d="M2 20c0-3 2.5-5 6-5s6 2 6 5"/><path d="M10 20c0-2.5 2-4.5 6-4.5s6 2 6 4.5"/>',
  teachers: '<rect x="3" y="4" width="18" height="12" rx="1"/><path d="M8 20h8M12 16v4"/>',
  classes: '<path d="M3 21V9l9-6 9 6v12"/><path d="M9 21v-6h6v6"/>',
  sections: '<rect x="4" y="4" width="16" height="6" rx="1"/><rect x="4" y="14" width="16" height="6" rx="1"/>',
  subjects: '<path d="M4 5c0-1 1-2 2-2h12v18H6c-1 0-2-1-2-2Z"/><path d="M6 3v18"/>',
  assignments: '<path d="m7 17 4-10 4 10"/><path d="M8.5 13h5"/><circle cx="19" cy="6" r="2"/><circle cx="5" cy="18" r="2"/>',
  satt: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="m9 12 2 2 4-4"/>',
  tatt: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4l2.5 2.5"/>',
  exams: '<path d="M4 20V6a2 2 0 0 1 2-2h9l5 5v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/><path d="M14 4v5h5"/><path d="M9 14h6M9 17h4"/>',
  promotions: '<path d="M7 17V7m0 0-3 3m3-3 3 3"/><path d="M17 7v10m0 0 3-3m-3 3-3-3"/>',
  feestruct: '<circle cx="8" cy="8" r="5"/><circle cx="16" cy="16" r="5"/>',
  challans: '<path d="M6 2h12v20l-3-2-3 2-3-2-3 2Z"/><path d="M9 8h6M9 12h6"/>',
  reports: '<path d="M21 12A9 9 0 1 1 12 3"/><path d="M21 12A9 9 0 0 0 12 3v9Z"/>',
  audit: '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  backup: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.65 1.65 0 0 0-1.9-.3 1.65 1.65 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.65 1.65 0 0 0-1-1.5 1.65 1.65 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.65 1.65 0 0 0 .3-1.9 1.65 1.65 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.65 1.65 0 0 0 1.5-1 1.65 1.65 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.65 1.65 0 0 0 1.9.3H9a1.65 1.65 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.65 1.65 0 0 0 1 1.5 1.65 1.65 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.65 1.65 0 0 0-.3 1.9V9a1.65 1.65 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.65 1.65 0 0 0-1.5 1Z"/>',
  mychild: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M6 17c0-2 1.5-3 3-3s3 1 3 3"/><path d="M14 9h4M14 13h4"/>',
  myatt: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16"/><path d="m9 14 2 2 4-4"/>',
  myresults: '<path d="M9 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="m9 14 2 2 4-4"/>',
  myfees: '<path d="M6 2h12v20l-3-2-3 2-3-2-3 2Z"/><path d="M9 8h6M9 12h6"/>',
  principals: '<path d="M12 2 3 7v2h18V7Z"/><path d="M5 10v9h14v-9"/><path d="M9 22v-6h6v6"/>',
};

/* Deterministic color per icon — same nav item is always the same color,
   regardless of which role's (shorter/longer) menu it appears in. */
const NAV_ICON_COLORS = {
  dashboard:'blue', students:'green', parents:'purple', teachers:'orange',
  classes:'teal', sections:'indigo', subjects:'pink', assignments:'red',
  satt:'green', tatt:'orange', exams:'purple', promotions:'blue',
  feestruct:'teal', challans:'pink', reports:'indigo', audit:'red',
  backup:'orange', settings:'blue',
  mychild:'green', myatt:'purple', myresults:'teal', myfees:'pink',
  principals:'purple',
};

function navIcon(key){
  const paths = NAV_ICONS[key];
  if(!paths) return '';
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true" style="flex-shrink:0">${paths}</svg>`;
}

/* Navigation menu per role — mirrors the SRS §9 permission matrix. */
const NAVCFG = {
  super_admin:[
    {k:'dashboard',l:'Dashboard', icon:'dashboard'},
    {sep:'MANAGEMENT'},
    {k:'students',l:'Students', icon:'students'},
    {k:'parents',l:'Parents', icon:'parents'},
    {k:'teachers',l:'Teachers', icon:'teachers'},
    {k:'principals',l:'Headmasters', icon:'principals'},
    {k:'classes',l:'Classes', icon:'classes'},
    {k:'sections',l:'Sections', icon:'sections'},
    {k:'subjects',l:'Subjects', icon:'subjects'},
    {k:'assignments',l:'Teacher Assignments', icon:'assignments'},
    {sep:'ACADEMICS'},
    {k:'satt',l:'Student Attendance', icon:'satt'},
    {k:'tatt',l:'Teacher Attendance', icon:'tatt'},
    {k:'exams',l:'Examinations', icon:'exams'},
    {k:'promotions',l:'Promotions', icon:'promotions'},
    {sep:'FINANCE'},
    {k:'feestruct',l:'Fee Structures', icon:'feestruct'},
    {k:'challans',l:'Fee Challans', icon:'challans'},
    {sep:'SYSTEM'},
    {k:'reports',l:'Reports', icon:'reports'},
    {k:'audit',l:'Audit Log', icon:'audit'},
    {k:'backup',l:'Database Backup', icon:'backup'},
    {k:'settings',l:'System Settings', icon:'settings'}
  ],
 principal:[
    {k:'dashboard',l:'Dashboard', icon:'dashboard'},
    {sep:'OVERSIGHT'},
    {k:'students',l:'Students', icon:'students'},
    {k:'teachers',l:'Teachers', icon:'teachers'},
    {k:'classes',l:'Classes', icon:'classes'},
    {k:'subjects',l:'Subjects', icon:'subjects'},
    {sep:'ACADEMICS'},
    {k:'tatt',l:'Teacher Attendance', icon:'tatt'},
    {k:'exams',l:'Examinations', icon:'exams'},
    {k:'promotions',l:'Promotions', icon:'promotions'},
    {sep:'REPORTS'},
    {k:'reports',l:'Reports', icon:'reports'}
  ],
  teacher:[
    {k:'dashboard',l:'Dashboard', icon:'dashboard'},
    {sep:'ACADEMICS'},
    {k:'exams',l:'Examinations & Marks', icon:'exams'},
    {k:'students',l:'My Students', icon:'students'},
    {sep:'REPORTS'},
    {k:'reports',l:'Reports', icon:'reports'}
  ],
  class_incharge:[
    {k:'dashboard',l:'Dashboard', icon:'dashboard'},
    {sep:'MY CLASS'},
    {k:'satt',l:'Student Attendance', icon:'satt'},
    {k:'students',l:'My Students', icon:'students'},
    {k:'exams',l:'Examinations', icon:'exams'},
    {sep:'REPORTS'},
    {k:'reports',l:'Reports', icon:'reports'}
  ],
  parent:[
    {k:'dashboard',l:'Dashboard', icon:'dashboard'},
    {sep:'MY CHILD'},
    {k:'mychild',l:'Student Profile', icon:'mychild'},
    {k:'myatt',l:'Attendance', icon:'myatt'},
    {k:'myresults',l:'Results', icon:'myresults'},
    {k:'myfees',l:'Fee Challans', icon:'myfees'}
  ]
};

function buildNav(){
  const role = state.user.role;
  const nav = document.getElementById('nav');
  if(!nav) return;

  nav.innerHTML = '';
  const items = NAVCFG[role] || [];

  if(!items.length){
    nav.innerHTML = '<div class="nav-sep">No menu items available</div>';
    return;
  }

  items.forEach((item, index)=>{
    if(item.sep){
      const sep = document.createElement('div');
      sep.className = 'nav-sep';
      sep.textContent = item.sep;
      nav.appendChild(sep);
      return;
    }

    const a = document.createElement('a');
    const color = NAV_ICON_COLORS[item.icon] || 'blue';
    a.className = 'nav-item nav-color-' + color;
    a.dataset.nav = item.k;
    a.tabIndex = 0;                 // reachable via Tab key (plain <a> without href isn't)
    a.setAttribute('role', 'button');
    a.style.animationDelay = (index * 30) + 'ms';
    a.innerHTML = navIcon(item.icon) + `<span>${esc(item.l)}</span>`;

    if(item.k === state.page){
      a.classList.add('active');
      a.setAttribute('aria-current', 'page');
    }

    const activate = ()=>go(item.k);
    a.addEventListener('click', activate);
    a.addEventListener('keydown', e=>{
      if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); activate(); }
    });

    nav.appendChild(a);
  });
}