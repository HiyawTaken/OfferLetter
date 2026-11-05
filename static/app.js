'use strict';
/* OfferLetter UI: first-run setup, a minimal home page, and a separate settings page.
   All job, company and question text comes from the web and is inserted as text, never as HTML. */

let token = '';
const state = { profile: {}, rules: {}, resumes: [], openJob: null, filter: 'all', runTimer: null, outputs: {} };

/* ---------- helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c instanceof Node ? c : String(c));
  return e;
}
async function api(path, options = {}, retried = false) {
  options.headers = { ...(options.headers || {}), 'X-OfferLetter-Token': token };
  if (options.body && !(options.body instanceof FormData)) options.headers['Content-Type'] = 'application/json';
  const r = await fetch(path, options);
  let data = {};
  try { data = await r.json(); } catch { data = {}; }
  // The server makes a new token each time it starts; pick it up once and retry instead of failing.
  if (r.status === 403 && data.error === 'Invalid request token' && !retried) {
    token = (await (await fetch('/api/session')).json()).token;
    return api(path, options, true);
  }
  if (!r.ok) throw Error(data.error || 'Something went wrong. Try again.');
  return data;
}
const post = (path, body) => api(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body || {}) });
let toastTimer;
function toast(message, bad) {
  const t = $('#toast'); t.textContent = message; t.className = bad ? 'bad' : ''; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), bad ? 6000 : 3000);
}
async function busy(button, work) {
  // Re-enable afterwards unless the work itself changed the button (for example to “Chrome is open”).
  const label = button.textContent; button.disabled = true;
  try { return await work(); } catch (e) { toast(e.message, true); if (button.textContent !== label) button.textContent = label; button.disabled = false; return; } finally { if (button.textContent === label) button.disabled = false; }
}
function field(label, name, opts = {}) {
  let input;
  if (opts.options) {
    input = h('select', { name });
    for (const o of opts.options) { const [value, text] = Array.isArray(o) ? o : [o, o]; input.append(h('option', { value, text })); }
  } else if (opts.type === 'textarea') input = h('textarea', { name, rows: opts.rows || 4, placeholder: opts.placeholder });
  else input = h('input', { name, type: opts.type || 'text', placeholder: opts.placeholder, min: opts.min, max: opts.max, required: opts.required, autocomplete: opts.autocomplete });
  return h('label', { class: 'field' }, h('span', { text: label }), input, opts.hint && h('small', { text: opts.hint }));
}
const check = (label, name, hint) => h('label', { class: 'check' }, h('input', { type: 'checkbox', name }), h('div', {}, h('div', { text: label }), hint && h('div', { class: 'small muted', text: hint })));
function fillForm(form, data) {
  for (const [k, v] of Object.entries(data || {})) {
    const el = form.elements[k]; if (!el || el instanceof RadioNodeList) continue;
    if (el.type === 'checkbox') el.checked = !!v;
    else if (el.tagName === 'SELECT' && v && ![...el.options].some(o => o.value === String(v))) { el.append(h('option', { value: v, text: v })); el.value = v; }
    else if (el.type !== 'file' && el.type !== 'password') el.value = v ?? '';
    if (el.dataset && el.dataset.choice) el.dispatchEvent(new Event('sync'));
  }
}
function readForm(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.type === 'file' || el.type === 'submit') continue;
    if (el.type === 'checkbox') out[el.name] = el.checked;
    else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; }
    else out[el.name] = el.value.trim();
  }
  return out;
}
// The mark is a folded letter drawn in one line, in the text color.
const LETTER_MARK = '<svg class="brand-mark" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><rect x="2.75" y="4.75" width="14.5" height="10.5" rx="2"/><path d="M3.5 6l6.5 5 6.5-5"/></svg>';
const brand = () => { const a = h('a', { class: 'brand', href: '#/' }); a.innerHTML = LETTER_MARK; a.append('OfferLetter'); return a; };

/* ---------- shared data ---------- */
async function loadBasics() {
  const [profile, rules, resumes] = await Promise.all([api('/api/profile'), api('/api/rules'), api('/api/resumes')]);
  state.profile = profile; state.rules = rules; state.resumes = resumes;
}
const saveProfile = async patch => { state.profile = { ...state.profile, ...patch }; await post('/api/profile', state.profile); };
const saveRules = async patch => { state.rules = { ...state.rules, ...patch }; state.rules = await post('/api/rules', state.rules); };
async function uploadResume(form) {
  const file = form.elements.file.files[0]; if (!file) throw Error('Choose a PDF first.');
  const body = new FormData(); body.append('file', file); body.append('titles', form.elements.titles.value.trim());
  await post('/api/resumes', body); state.resumes = await api('/api/resumes'); form.reset();
}

/* ---------- field groups (shared by setup and settings) ---------- */
const contactFields = () => [
  h('div', { class: 'grid2' }, field('First name', 'first_name', { required: true, autocomplete: 'given-name' }), field('Last name', 'last_name', { required: true, autocomplete: 'family-name' })),
  field('Email', 'email', { type: 'email', required: true, autocomplete: 'email' }),
  h('div', { class: 'grid2' }, field('Phone', 'phone', { type: 'tel', autocomplete: 'tel' }), field('City and state', 'location', { placeholder: 'Austin, TX' })),
  h('div', { class: 'grid2' }, field('LinkedIn', 'linkedin', { type: 'url', placeholder: 'https://linkedin.com/in/…' }), field('Website or portfolio', 'website', { type: 'url' })),
];
const yesNo = [['', 'Not set'], 'Yes', 'No'];
const eligibilityFields = () => [
  field('Are you authorized to work in the United States?', 'work_authorization', { options: yesNo }),
  field('Will you now or in the future need visa sponsorship?', 'sponsorship', { options: yesNo }),
];
// Degree names as Greenhouse and Workday list them.
const DEGREES = ['High School Diploma', 'Associate’s Degree', 'Bachelor’s Degree', 'Master’s Degree', 'Master of Business Administration (M.B.A.)', 'Doctor of Philosophy (Ph.D.)', 'Juris Doctor (J.D.)', 'Doctor of Medicine (M.D.)'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const educationFields = () => [
  h('h3', { style: 'margin:0 0 12px', text: 'Education' }),
  field('School', 'school', { placeholder: 'Arizona State University', hint: 'Write the full name, the way the school spells it.' }),
  h('div', { class: 'grid2' }, choiceField('Degree', 'degree', DEGREES), field('Major or field of study', 'discipline', { placeholder: 'Computer Science' })),
  h('div', { class: 'grid2' }, field('Graduation month', 'grad_month', { options: [['', 'Not set'], ...MONTHS] }), field('Graduation year', 'grad_year', { type: 'number', min: 1950, max: 2100, placeholder: '2027' })),
  field('GPA', 'gpa', { placeholder: '3.6', hint: 'Leave empty to be asked on each application.' }),
];

function experienceEditor(entries = []) {
  const root = h('div', { class: 'experience-editor' });
  const list = h('div');
  const empty = h('p', { class: 'small muted', text: 'No work experience yet? You can continue without adding a job. Internships and part-time jobs count too.' });
  function add(entry = {}) {
    const card = h('fieldset', { class: 'card experience-entry', style: 'margin:0 0 20px;min-width:0' },
      h('legend', { text: 'Employment' }),
      h('div', { class: 'grid2' }, field('Job title', 'title', { required: true }), field('Company / employer', 'employer', { required: true })),
      h('div', { class: 'grid2' }, field('Location', 'location', { placeholder: 'City, state, country' }), field('Employment type', 'employment_type', { options: [['', 'Not set'], 'Full-time', 'Part-time', 'Internship', 'Contract', 'Temporary', 'Volunteer', 'Self-employed'] })),
      h('div', { class: 'grid2' }, field('Start date', 'start_date', { type: 'month', required: true }), field('End date', 'end_date', { type: 'month', required: true })),
      check('I currently work here', 'currently_working'),
      field('Role description and responsibilities', 'description', { type: 'textarea', rows: 4, placeholder: 'What you did, tools you used, and results you achieved.' }));
    // Each entry owns its controls, so repeated field names never overwrite another job.
    const controls = name => card.querySelector('[name="' + name + '"]');
    for (const [key,value] of Object.entries(entry)) { const el=controls(key);if(el){if(el.type==='checkbox')el.checked=!!value;else el.value=value || '';} }
    const sync = () => { const current=controls('currently_working').checked;controls('end_date').disabled=current;controls('end_date').required=!current;if(current)controls('end_date').value=''; };
    controls('currently_working').onchange=sync;sync();
    card.append(h('button', { class: 'btn quiet sm', type: 'button', text: 'Remove this job', onclick: () => { card.remove();empty.hidden=!!list.children.length; } }));
    list.append(card);empty.hidden=true;
  }
  root.append(empty,list,h('button',{class:'btn ghost',type:'button',text:'Add work experience',onclick:()=>add()}));
  for(const entry of entries || [])add(entry);
  root.read = () => [...list.children].map(card => Object.fromEntries([...card.querySelectorAll('[name]')].map(el => [el.name,el.type==='checkbox'?el.checked:el.value.trim()])));
  return root;
}
/* A dropdown of standard answers plus "Other (type your own)". The text input holds the saved value. */
const OTHER = 'Other (type your own)';
function choiceField(label, name, choices) {
  const select = h('select', {}, h('option', { value: '', text: 'Not set' }), choices.map(c => h('option', { value: c, text: c })), h('option', { value: OTHER, text: OTHER }));
  const input = h('input', { name, 'data-choice': '1', placeholder: 'Type your answer', hidden: true, 'aria-label': label + ' (your own words)' });
  select.onchange = () => { const other = select.value === OTHER; input.hidden = !other; input.value = other ? '' : select.value; if (other) input.focus(); };
  input.addEventListener('sync', () => { const v = input.value.trim(); const known = !v || choices.includes(v); select.value = known ? v : OTHER; input.hidden = known; });
  return h('label', { class: 'field' }, h('span', { text: label }), select, h('div', { class: 'other-input' }, input));
}
// Standard wording used on US applications (EEO-1 race categories, VEVRAA veteran status, form CC-305 disability), as Workday shows them.
const DECLINE = 'I do not wish to self-identify';
const selfIdFields = () => h('section', { class: 'selfid' },
  h('h3', { text: 'Voluntary self-identification' }),
  h('p', { class: 'small muted', text: 'Optional. Used only to answer these questions on applications, and never affects whether a job is prepared. Leave any of them on Not set and OfferLetter will ask you on each application instead.' }),
  h('div', { class: 'grid2' },
    choiceField('Gender', 'eeo_gender', ['Male', 'Female', 'Non-binary', DECLINE]),
    choiceField('Are you Hispanic or Latino?', 'eeo_hispanic', ['Yes', 'No', DECLINE])),
  choiceField('Race or ethnicity', 'eeo_race', ['American Indian or Alaska Native (Not Hispanic or Latino)', 'Asian (Not Hispanic or Latino)', 'Black or African American (Not Hispanic or Latino)', 'Hispanic or Latino',
    'Native Hawaiian or Other Pacific Islander (Not Hispanic or Latino)', 'White (Not Hispanic or Latino)', 'Two or More Races (Not Hispanic or Latino)', DECLINE]),
  choiceField('Veteran status', 'eeo_veteran', ['I am not a protected veteran', 'I identify as one or more of the classifications of protected veteran', DECLINE]),
  choiceField('Disability status', 'eeo_disability', ['Yes, I have a disability, or have had one in the past', 'No, I do not have a disability and have not had one in the past', 'I do not want to answer']));
const remoteOptions = [['', 'No preference'], ['remote only', 'Remote only']];
const preferenceFields = () => [
  field('Career stage', 'career_stage', { options: [['', 'Choose one'], ['internship', 'Internship'], ['new_grad', 'New graduate'], ['experienced', 'Experienced']] }),
  field('Job titles you want', 'titles', { placeholder: 'Software Engineer Intern, Backend Engineer', hint: 'Separate titles with commas.' }),
  h('div', { class: 'grid2' }, field('Locations', 'locations', { placeholder: 'San Francisco, CA, New York, NY', hint: 'Add the state to also see nearby cities as close matches.' }), field('Remote', 'remote', { options: remoteOptions })),
];

function resumeList(onChange) {
  const ul = h('ul', { class: 'filelist' });
  const draw = () => {
    ul.replaceChildren();
    if (!state.resumes.length) ul.append(h('li', { class: 'muted', text: 'No resumes yet' }));
    for (const r of state.resumes) ul.append(h('li', {}, h('div', { style: 'flex:1;min-width:0' }, h('div', { text: r.name }), h('div', { class: 'small muted', text: r.titles || 'No target titles' })),
      h('button', { class: 'btn quiet sm', type: 'button', text: 'Remove', onclick: async () => { await api('/api/resumes/' + r.id, { method: 'DELETE' }); state.resumes = await api('/api/resumes'); draw(); onChange && onChange(); } })));
  };
  draw(); ul.redraw = draw; return ul;
}

/* ---------- onboarding ---------- */
const STEPS = [
  { key: 'welcome' }, { key: 'about', nav: 'About you', title: 'About you', lead: 'This is what OfferLetter types into the basic fields of every application.' },
  { key: 'eligibility', nav: 'Work eligibility', title: 'Work eligibility', lead: 'Applications ask these every time. You can change them later.' },
  { key: 'education', nav: 'Education', title: 'Education', lead: 'Applications ask for your school, degree and graduation date. Fill these once and OfferLetter answers them.' },
  { key: 'experience', nav: 'Work experience', title: 'Work experience', lead: 'Add your employment history: roles, employers, dates and responsibilities. You can add more than one job.' },
  { key: 'resume', nav: 'Resume', title: 'Your resume', lead: 'Add a text-based PDF. You can add more versions for different roles later.' },
  { key: 'prefs', nav: 'Jobs you want', title: 'What you’re looking for', lead: 'Used to find jobs and check whether they fit you.' },
  { key: 'model', nav: 'AI model', title: 'AI model', lead: 'Used to check fit and draft cover letters. It never submits anything.' },
  { key: 'browser', nav: 'Browser', title: 'Your browser', lead: 'OfferLetter fills applications in its own Chrome window, separate from your everyday browser.' },
];
/* A filled-in application, drawn in code, so the welcome screen shows what the product does. */
function applicationPreview() {
  const row = (label, value, kind) => h('div', { class: 'ap-row' + (kind ? ' ' + kind : '') }, h('span', { class: 'ap-label', text: label }),
    h('span', { class: 'ap-value', text: value }), h('span', { class: 'mark ' + (kind === 'ask' ? 'unclear' : 'met'), text: kind === 'ask' ? '?' : '✓' }));
  return h('div', { class: 'ap', 'aria-hidden': 'true' },
    h('div', { class: 'ap-head' }, h('span', { class: 'ap-site', text: 'job-boards.greenhouse.io' }), h('b', { text: 'Product Designer, New Grad' }), h('span', { class: 'small muted', text: 'Northwind Health · Chicago, IL' })),
    row('First name', 'Maya'), row('Email', 'maya.chen@example.com'), row('Resume', 'maya-chen-resume.pdf'),
    row('Authorized to work in the US?', 'Yes'), row('Why Northwind?', 'Asks you', 'ask'),
    h('div', { class: 'ap-foot' }, h('span', { class: 'small muted', text: 'Submit waits for your approval' }), h('span', { class: 'ap-submit', text: 'Submit application' })));
}
async function renderOnboarding(index) {
  index = Math.max(0, Math.min(STEPS.length - 1, index || 0));
  const step = STEPS[index];
  const go = i => (location.hash = '#/welcome/' + i);
  const total = STEPS.length - 1;
  const rail = h('aside', { class: 'ob-rail' }, brand(),
    h('ol', { class: 'ob-steps' }, STEPS.slice(1).map((s, i) => {
      const n = i + 1, done = n < index;
      const inner = [h('span', { class: 'ob-num', text: done ? '✓' : String(n) }), s.nav];
      return h('li', { class: done ? 'done' : n === index ? 'on' : null }, done ? h('a', { href: '#/welcome/' + n }, inner) : h('span', {}, inner));
    })),
    h('p', { class: 'ob-foot', text: 'Everything stays on this computer' }));
  const card = h('div', { class: 'ob-body' });
  $('#app').replaceChildren(h('div', { class: 'ob' + (index === 0 ? ' intro' : '') }, rail, h('main', { class: 'ob-main' }, card)));

  if (step.key === 'welcome') {
    card.append(h('div', { class: 'intro-split' },
      h('div', { class: 'intro-text' },
        h('h1', { text: 'Fill job applications from your resume, and submit only what you approve' }),
        h('p', { class: 'lead', text: 'OfferLetter fills each form in a Chrome window you can watch, asks you whenever it isn’t sure, and never clicks Submit until you say so.' }),
        h('div', { class: 'ob-actions' }, h('button', { class: 'btn lg', type: 'button', text: 'Set up OfferLetter', onclick: () => go(1) }), h('span', { class: 'small muted', text: 'About three minutes' }))),
      applicationPreview()));
    return;
  }
  card.append(h('p', { class: 'ob-count', text: `Step ${index} of ${total}` }), h('h1', { text: step.title }), h('p', { class: 'lead', text: step.lead }));
  const form = h('form', { novalidate: false });
  const back = h('button', { class: 'btn quiet', type: 'button', text: 'Back', onclick: () => go(index - 1) });
  const next = h('button', { class: 'btn', type: 'submit', text: index === STEPS.length - 1 ? 'Finish' : 'Continue' });
  const skip = h('button', { class: 'btn quiet', type: 'button', text: 'Skip for now', onclick: () => go(index + 1) });
  let save = async () => {};
  let optional = false;

  if (step.key === 'about') { form.append(...contactFields()); fillForm(form, state.profile); save = () => saveProfile(readForm(form)); }
  if (step.key === 'education') { form.append(...educationFields()); fillForm(form, state.profile); save = () => saveProfile(readForm(form)); optional = true; }
  if (step.key === 'experience') { const editor=experienceEditor(state.profile.experience);form.append(editor);save=()=>saveProfile({experience:editor.read()});optional=true; }
  if (step.key === 'eligibility') { form.append(...eligibilityFields(), selfIdFields()); fillForm(form, state.profile); save = () => saveProfile(readForm(form)); optional = true; }
  if (step.key === 'resume') {
    const up = h('div', {}, field('Resume PDF', 'file', { type: 'file' }), field('Roles this resume is for (optional)', 'titles', { placeholder: 'Software Engineer, Data Engineer' }));
    up.querySelector('input[type=file]').accept = 'application/pdf';
    const list = resumeList(() => {});
    const add = h('button', { class: 'btn ghost sm', type: 'button', text: 'Upload' });
    add.onclick = () => busy(add, async () => { await uploadResume(form); list.redraw(); toast('Resume added'); });
    form.append(up, h('div', { class: 'row' }, add), list);
    save = async () => {
      if (form.elements.file.files.length) { await uploadResume(form); list.redraw(); }
      if (!state.resumes.length) throw Error('Add a resume, or choose Skip for now.');
    };
    optional = true;
  }
  if (step.key === 'prefs') {
    form.append(...preferenceFields());
    fillForm(form, state.rules);
    if (!form.elements.titles.value && state.resumes[0]?.titles) form.elements.titles.value = state.resumes[0].titles;
    save = async () => { const d = readForm(form); if (!d.titles) throw Error('Add at least one job title.'); await saveRules(d); };
  }
  if (step.key === 'model') {
    const cfg = await api('/api/settings/model').catch(() => ({}));
    const local = h('label', { class: 'choice' }, h('input', { type: 'radio', name: 'kind', value: 'local' }), h('div', {}, h('b', { text: 'On this computer (recommended)' }), h('span', { class: 'small muted', text: 'Uses a local model server such as Ollama. Your resume never leaves your machine.' })));
    const cloud = h('label', { class: 'choice' }, h('input', { type: 'radio', name: 'kind', value: 'cloud' }), h('div', {}, h('b', { text: 'A cloud provider' }), h('span', { class: 'small muted', text: 'OpenAI, Claude, Gemini or OpenRouter. Your resume and job text are sent to them.' })));
    const localBox = h('div', {}, field('Model name', 'model_local', { placeholder: 'qwen3:8b' }), field('Server address', 'base_url', { hint: 'Ollama’s default is http://127.0.0.1:11434/v1' }));
    const cloudBox = h('div', {}, field('Provider', 'provider', { options: [['openai', 'OpenAI'], ['claude', 'Claude'], ['gemini', 'Gemini'], ['openrouter', 'OpenRouter']] }), field('Model name', 'model_cloud'), field('API key', 'api_key', { type: 'password', hint: 'Stored in your system’s credential store.' }), check('I understand my resume and job text will be sent to this provider.', 'cloud_consent'));
    form.append(local, cloud, localBox, cloudBox);
    const isCloud = cfg.provider && cfg.provider !== 'local';
    form.elements.base_url.value = cfg.base_url || 'http://127.0.0.1:11434/v1';
    form.elements[isCloud ? 'model_cloud' : 'model_local'].value = cfg.model || '';
    if (isCloud) form.elements.provider.value = cfg.provider;
    form.querySelector(`input[value=${isCloud ? 'cloud' : 'local'}]`).checked = true;
    const sync = () => { const c = form.querySelector('input[value=cloud]').checked; localBox.hidden = c; cloudBox.hidden = !c; };
    form.addEventListener('change', sync); sync();
    save = async () => {
      const d = readForm(form);
      const body = d.kind === 'cloud'
        ? { provider: d.provider, model: d.model_cloud, api_key: d.api_key, cloud_consent: form.elements.cloud_consent.checked, map_fields: !!cfg.map_fields }
        : { provider: 'local', model: d.model_local, base_url: d.base_url, map_fields: !!cfg.map_fields };
      if (!body.model) throw Error('Enter a model name, or choose Skip for now.');
      await post('/api/settings/model', body);
    };
    optional = true;
  }
  if (step.key === 'browser') {
    const s = await api('/api/session');
    const status = h('p', { class: 'small muted', text: s.browser_open ? 'Chrome is open' : '' });
    const open = h('button', { class: 'btn ghost', type: 'button', text: s.browser_open ? 'Chrome is open' : 'Open Chrome' });
    open.disabled = !!s.browser_open;
    open.onclick = () => busy(open, async () => { await post('/api/browser/open'); status.textContent = 'Chrome is open. Sign in to LinkedIn or any job sites you use, then come back here.'; open.textContent = 'Chrome is open'; open.disabled = true; });
    form.append(h('div', { class: 'note', style: 'margin-bottom:16px', text: 'Sign in to the job sites you use once in that window. Your sign-ins stay on this computer. You can also do this later from Settings.' }), h('div', { class: 'row' }, open), status);
    save = async () => { await post('/api/onboarding', { done: true }); };
  }
  form.append(h('div', { class: 'ob-actions' }, back, h('span', { class: 'spacer' }), optional && skip, next));
  form.onsubmit = e => { e.preventDefault(); busy(next, async () => { await save(); if (index === STEPS.length - 1) { location.hash = '#/'; toast('Setup complete'); } else go(index + 1); }); };
  card.append(form);
  form.querySelector('input:not([type=radio]),select')?.focus();
}

/* ---------- shared: statuses and the top bar ---------- */
const STATUS = {
  'found': ['Queued', ''], 'screening': ['Screening', ''], 'approved': ['Approved', 'info'], 'check match': ['Check match', 'warn'], 'waiting on user': ['Needs you', 'warn'], 'ready for review': ['Ready to review', 'info'],
  'review fit': ['Check fit', 'warn'], 'submitted': ['Submitted', 'good'], 'submission pending': ['Submitting…', 'info'],
  'submission uncertain': ['Check outcome', 'warn'], 'skipped': ['Skipped', ''], 'failed': ['Failed', 'bad'],
  'rejected': ['Rejected', 'bad'], 'interview': ['Interview', 'good'],
};
const FIT = { pass: ['Good fit', 'good'], borderline: ['Borderline', 'warn'], fail: ['Not a fit', 'bad'] };
const statusPill = s => { const [t, c] = STATUS[s] || [s || 'Queued', '']; return h('span', { class: 'pill ' + c, text: t }); };
const fitPill = f => f && FIT[f] ? h('span', { class: 'pill ' + FIT[f][1], text: FIT[f][0] }) : null;
const NEEDS = ['check match', 'waiting on user', 'review fit', 'submission uncertain'];
const FILTERS = [['all', 'All'], ['needs', 'Needs you'], ['queued', 'Queued'], ['review', 'To review'], ['done', 'Submitted'], ['skipped', 'Skipped']];
const inFilter = (j, f) => f === 'all' || (f === 'needs' && NEEDS.includes(j.status)) || (f === 'queued' && ['found', 'approved', 'screening'].includes(j.status)) || (f === 'review' && j.status === 'ready for review')
  || (f === 'done' && ['submitted', 'interview', 'rejected'].includes(j.status)) || (f === 'skipped' && j.status === 'skipped');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

function topBar(active) {
  const link = (href, text, key) => h('a', { class: 'nav-link' + (active === key ? ' on' : ''), href, text, 'aria-current': active === key ? 'page' : null });
  return h('header', { class: 'top' }, h('div', { class: 'top-in wide' }, brand(), h('nav', { class: 'nav' }, link('#/', 'Home', 'home'), link('#/jobs', 'Jobs', 'jobs')),
    h('span', { class: 'spacer' }), h('a', { class: 'btn ghost sm', href: '#/settings', text: 'Settings' })));
}

/* Run status in words, from /api/runs. Short phrases, no trailing periods. */
const num = n => Number(n || 0).toLocaleString();
const clean = t => String(t || '').replace(/\.\s*$/, '').replace(/^Waiting for a free tab: (\d+) of (\d+) open.*$/, 'Waiting for a free tab, $1 of $2 open');
function when(ts) {
  if (!ts) return '';
  const d = new Date(ts.replace(' ', 'T') + (ts.includes('Z') || ts.includes('+') ? '' : 'Z'));  // SQLite stores UTC
  return isNaN(d) ? '' : d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
function describeRun(r) {
  const s = r.summary || {};
  const running = r.status === 'running' || r.status === 'pausing';
  const done = [s.prepared && `${num(s.prepared)} filled`, s.needs_attention && `${num(s.needs_attention)} need you`, s.skipped && `${num(s.skipped)} skipped`].filter(Boolean);
  if (r.status === 'pausing') return { running, line: 'Pausing after the current step' };
  if (running && s.phase === 'searching') return { running, line: 'Searching job sites' + (s.sources_total ? `, ${s.sources_done || 0} of ${s.sources_total} done` : '') };
  const screening = s.screen_total && s.screened < s.screen_total ? `Screening ${num(s.screened)} of ${num(s.screen_total)}` : '';
  if (running) return { running, line: [screening, clean(s.reason) || (screening ? '' : 'Filling applications'), ...done].filter(Boolean).join(' · ') };
  if (!r.status || r.status === 'not started') return { running, line: '' };
  const found = s.found == null ? '' : s.screen_total != null ? `found ${num(s.found)}, ${num(s.screen_apply)} to apply and ${num(s.screen_close)} close` : `found ${num(s.found)}, ${num(s.clear)} clear and ${num(s.gray)} close`;
  const problem = ['failed', 'blocked', 'waiting'].includes(r.status);
  const last = when(r.finished_at || r.started_at);
  return { running, tone: problem ? 'warn' : '', line: problem ? clean(s.reason) : ['Last run' + (last ? ' ' + last : ''), found, ...done].filter(Boolean).join(' · ') };
}

/* ---------- home: one button, what needs you, and the assistant ---------- */
async function renderHome() {
  // The one action leads the row of counts as a bigger, filled tile.
  const runLabel = h('b', { text: 'Find and apply' });
  const runSub = h('span');
  const runBtn = h('button', { class: 'run-tile', type: 'button' }, h('span', { class: 'run-text' }, runLabel, runSub), h('span', { class: 'run-arrow', 'aria-hidden': 'true', text: '→' }));
  const runLine = h('p', { class: 'run-line' });
  const stats = h('div', { class: 'tally-counts' });
  const inbox = h('div', { class: 'inbox' });
  const chat = assistantPanel();

  const sources = ['LinkedIn', 'Indeed'];
  if (['internship', 'new_grad'].includes(state.rules.career_stage)) sources.push('Simplify');
  const tabs = Number(state.rules.tab_limit) || 3;
  const intro = `Searches ${sources.join(', ').replace(/, ([^,]*)$/, ' and $1')}, fills clear matches ${plural(tabs, 'tab')} at a time, and never submits without you`;

  const titles = (state.rules.titles || '').split(',').map(t => t.trim()).filter(Boolean);
  const place = (state.rules.locations || '').split(/,\s*(?=[^,]+,\s*[A-Z]{2}\b)|;/)[0].trim();
  const idleSub = titles.length ? [plural(titles.length, 'title'), place].filter(Boolean).join(' · ') : 'Add job titles in Settings first';
  const head = h('header', { class: 'home-head' }, h('h1', { text: 'Job search' }), runLine);
  $('#app').replaceChildren(topBar('home'), h('main', { class: 'wrap wide' }, head, h('div', { class: 'tally' }, runBtn, stats),
    h('div', { class: 'home-grid' }, h('section', { class: 'needs' }, h('div', { class: 'section-head' }, h('h2', { text: 'Needs you' })), inbox), chat.el)));

  let running = false;
  async function refreshRun() {
    const r = await api('/api/runs').catch(() => ({}));
    const d = describeRun(r); running = d.running;
    runLabel.textContent = r.status === 'pausing' ? 'Pausing…' : running ? 'Pause' : 'Find and apply';
    runSub.textContent = running ? 'Running now' : idleSub;
    runBtn.className = 'run-tile' + (running ? ' running' : '');
    runBtn.disabled = r.status === 'pausing';
    runLine.textContent = d.line || intro;  // the explanation only until there is a first run
    runLine.className = 'run-line' + (d.tone ? ' ' + d.tone : '') + (running ? ' live' : '');
    return running;
  }
  runBtn.onclick = () => busy(runBtn, async () => {
    if (running) await post('/api/runs/pause');
    else { if (!(state.rules.titles || '').trim()) throw Error('Add the job titles you want in Settings → Job preferences first'); await post('/api/find-and-apply'); toast('Searching. Clear matches will start filling in Chrome'); }
    await refreshRun();
  });

  async function drawInbox() {
    const [qs, jobs] = await Promise.all([api('/api/questions'), api('/api/jobs')]);
    const count = s => jobs.filter(j => s.includes(j.status)).length;
    const tally = [['Need you', count(NEEDS) + qs.length, 'needs'], ['Queued', count(['found', 'approved']), 'queued'], ['To review', count(['ready for review']), 'review'], ['Submitted', count(['submitted', 'interview', 'rejected']), 'done']];
    stats.replaceChildren(...tally.map(([label, n, f]) => h('a', { class: 'tally-item', href: '#/jobs', onclick: () => (state.filter = f) }, h('b', { text: num(n) }), h('span', { text: label }))));
    const groups = [];
    if (qs.length) {
      // One block per application, so a long form doesn't bury everything else.
      const byJob = new Map();
      for (const q of qs) { const key = [q.company, q.title].filter(Boolean).join(' · ') || 'Application'; if (!byJob.has(key)) byJob.set(key, []); byJob.get(key).push(q); }
      const wasOpen = new Set([...inbox.querySelectorAll('.qjob')].filter(d => d.open).map(d => d.dataset.key));
      const first = !inbox.querySelector('.qjob');
      const blocks = [...byJob].map(([key, list], i) => h('details', { class: 'qjob', 'data-key': key, open: wasOpen.has(key) || (first && i === 0) }, h('summary', {}, h('span', { text: key }), h('span', { class: 'count', text: list.length })), list.map(q => questionCard(q, drawInbox))));
      groups.push(group('Questions', 'OfferLetter wasn’t sure about these. Your answer is filled in and remembered.', blocks, '', null, qs.length));
    }
    const close = jobs.filter(j => j.status === 'check match');
    if (close.length) {
      const all = (status, label) => { const b = h('button', { class: 'btn quiet sm', type: 'button', text: label }); b.onclick = () => busy(b, async () => {
        for (const j of close) await post('/api/jobs/' + j.id + '/status', { status });
        if (status === 'found') await post('/api/runs').catch(() => {});
        toast(status === 'found' ? `${plural(close.length, 'job')} queued to fill` : `${plural(close.length, 'job')} skipped`); await drawInbox(); }); return b; };
      groups.push(group('Close matches', 'Not quite what you asked for. Apply to the ones you want and they’ll be filled next. To always include a nearby city, add it to your locations in Settings.',
        close.slice(0, 20).map(j => matchCard(j, drawInbox)), close.length > 20 ? `${close.length - 20} more on the Jobs page` : '', [all('skipped', 'Skip all'), all('found', `Apply to all ${close.length}`)], close.length));
    }
    const review = jobs.filter(j => j.status === 'ready for review');
    if (review.length) groups.push(group('Ready to review', 'Check every answer, then approve the submit.', review.map(j => jobCardRow(j, h('button', { class: 'btn sm', type: 'button', text: 'Review', onclick: () => openReview(j.id, drawInbox).catch(e => toast(e.message, true)) })))));
    const unsure = jobs.filter(j => j.status === 'review fit');
    if (unsure.length) groups.push(group('Fit unclear', 'Your resume may not cover everything these ask for. Apply anyway or skip.', unsure.slice(0, 20).map(j => matchCard(j, drawInbox)), unsure.length > 20 ? `${unsure.length - 20} more on the Jobs page` : '', null, unsure.length));
    const blocked = jobs.filter(j => ['waiting on user', 'submission uncertain'].includes(j.status));
    if (blocked.length) groups.push(group('Waiting on you', 'Filled as far as OfferLetter could go. Finish these in Chrome, or open one for its steps.', blocked.slice(0, 10).map(j => jobCardRow(j, h('a', { class: 'btn ghost sm', href: '#/jobs', text: 'Open', onclick: () => { state.openJob = j.id; state.filter = 'needs'; } })))));
    inbox.replaceChildren(...(groups.length ? groups : [h('div', { class: 'empty card' }, h('p', { text: jobs.length ? 'Nothing needs you right now' : 'No jobs yet' }), h('p', { class: 'small', text: jobs.length ? 'New questions and close matches show up here.' : 'Press Find and apply, or paste a link on the Jobs page.' }))]));
  }

  await Promise.all([drawInbox(), refreshRun()]);
  let wasRunning = running;
  clearInterval(state.runTimer);
  state.runTimer = setInterval(async () => {
    if (!document.body.contains(runBtn)) return clearInterval(state.runTimer);
    await refreshRun();
    const editing = inbox.contains(document.activeElement) && document.activeElement.matches('input,select,textarea');
    if ((running || wasRunning) && !editing) await drawInbox().catch(() => {});
    wasRunning = running;
  }, 4000);
}

const group = (title, note, items, more, actions, total) => h('div', { class: 'group' }, h('div', { class: 'group-head' }, h('h3', { text: title }), h('span', { class: 'count', text: total || items.length }), actions && h('span', { class: 'spacer' }), actions),
  h('p', { class: 'small muted group-note', text: note }), h('div', { class: 'list' }, items), more && h('a', { class: 'small more-link', href: '#/jobs', text: more, onclick: () => (state.filter = 'needs') }));

// Company · location, then pay when the posting gives it.
const jobMeta = j => h('div', { class: 'job-meta' }, h('span', { class: 'meta-text', text: [j.company, j.location].filter(Boolean).join(' · ') || hostOf(j.url) }), j.pay ? h('span', { class: 'pay', text: j.pay }) : null);
function jobCardRow(j, action) {
  return h('div', { class: 'mini' }, h('div', { class: 'job-main' }, h('div', { class: 'job-title', text: j.title || 'Untitled role' }),
    jobMeta(j), j.match_note ? h('div', { class: 'why', text: j.match_note }) : null), action);
}

function matchCard(j, after) {
  const set = (status, note) => async () => {
    await post('/api/jobs/' + j.id + '/status', { status });
    if (status !== 'skipped') await post('/api/runs').catch(() => {});  // already running: it picks the job up
    toast(note); await after();
  };
  // Apply on a fit-unclear job approves it, so the next run fills it without asking again.
  const yes = h('button', { class: 'btn sm', type: 'button', text: 'Apply' }); yes.onclick = () => busy(yes, set(j.status === 'review fit' ? 'approved' : 'found', 'Queued to fill'));
  const no = h('button', { class: 'btn quiet sm', type: 'button', text: 'Skip' }); no.onclick = () => busy(no, set('skipped', 'Skipped'));
  return h('div', { class: 'mini match' }, h('div', { class: 'job-main' },
    h('a', { class: 'job-title', href: j.url, target: '_blank', rel: 'noopener noreferrer', text: j.title || 'Untitled role' }),
    jobMeta(j),
    j.match_note ? h('div', { class: 'why', text: j.match_note }) : null), h('div', { class: 'mini-actions' }, no, yes));
}

/* ---------- assistant ---------- */
function assistantPanel() {
  const log = h('div', { class: 'chat-log', 'aria-live': 'polite' });
  const input = h('textarea', { rows: 1, maxlength: 2000, placeholder: 'Ask about your jobs or applications', 'aria-label': 'Message the assistant' });
  const send = h('button', { class: 'btn sm', type: 'submit', text: 'Send' });
  const form = h('form', { class: 'chat-form' }, input, send);
  const clear = h('button', { class: 'btn quiet sm', type: 'button', text: 'Clear' });
  const el = h('aside', { class: 'chat' }, h('div', { class: 'chat-head' }, h('h2', { text: 'Assistant' }), h('span', { class: 'spacer' }), clear), log, form);
  const bubble = (role, text) => h('div', { class: 'msg ' + role }, h('div', { class: 'msg-body', text }));
  const suggestions = ['What needs me right now?', 'Why were some jobs skipped?', 'Summarize the last search'];
  const empty = () => h('div', { class: 'chat-empty' }, h('p', { class: 'small muted', text: 'Ask anything about your search. The assistant sees your jobs, fit checks, questions and activity, but it can’t click or submit anything.' }),
    h('div', { class: 'suggest' }, suggestions.map(s => h('button', { class: 'chip', type: 'button', text: s, onclick: () => ask(s) }))));
  const scroll = () => (log.scrollTop = log.scrollHeight);
  async function load() {
    const rows = await api('/api/assistant').catch(() => []);
    log.replaceChildren(...(rows.length ? rows.map(r => bubble(r.role, r.text)) : [empty()])); scroll();
  }
  async function ask(text) {
    text = text.trim(); if (!text) return;
    if (log.querySelector('.chat-empty')) log.replaceChildren();
    log.append(bubble('user', text)); const pending = bubble('assistant pending', 'Thinking…'); log.append(pending); scroll();
    input.value = ''; input.style.height = ''; send.disabled = true;
    try { const r = await post('/api/assistant', { message: text }); pending.replaceWith(bubble('assistant', r.reply)); }
    catch (e) { pending.replaceWith(bubble('assistant error', e.message)); }
    finally { send.disabled = false; scroll(); input.focus(); }
  }
  form.onsubmit = e => { e.preventDefault(); if (!send.disabled) ask(input.value); };
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; });
  clear.onclick = () => busy(clear, async () => { await api('/api/assistant', { method: 'DELETE' }); await load(); });
  load();
  return { el };
}

/* ---------- jobs page: every job, add a link, search one source ---------- */
async function renderJobs() {
  const url = h('input', { name: 'url', type: 'url', required: true, placeholder: 'Paste a job link to add it' });
  const addBtn = h('button', { class: 'btn', text: 'Add job' });
  const extra = h('details', { class: 'more' }, h('summary', { text: 'Add details (company, title, description)' }),
    h('div', { class: 'grid2' }, field('Company', 'company'), field('Job title', 'title')), field('Location', 'location'),
    field('Job description', 'description', { type: 'textarea', rows: 4, hint: 'Paste it to get a fit check.' }));
  const addForm = h('form', {}, h('div', { class: 'addbar' }, url, addBtn), extra);
  addForm.onsubmit = e => { e.preventDefault(); busy(addBtn, async () => { const d = readForm(addForm); const r = await post('/api/jobs', d); addForm.reset(); extra.open = false; state.openJob = r.id; toast('Job added'); await drawJobs(); }); };
  const findBtn = h('button', { class: 'btn ghost', type: 'button', text: 'Search one source', onclick: openFind });
  const summary = h('p', { class: 'summary' });
  const chips = h('div', { class: 'chips' });
  const jobsList = h('div', { class: 'list' });
  $('#app').replaceChildren(topBar('jobs'), h('main', { class: 'wrap' }, h('div', { class: 'page-head' }, h('div', {}, h('h1', { text: 'Jobs' }), summary), findBtn), addForm,
    h('section', { class: 'section' }, h('div', { class: 'section-head' }, chips), jobsList)));

  async function drawJobs() {
    const [jobs, tracker] = await Promise.all([api('/api/jobs'), api('/api/tracker').catch(() => [])]);
    const fit = Object.fromEntries(tracker.map(t => [t.id, t]));
    chips.replaceChildren(...FILTERS.map(([k, t]) => { const n = jobs.filter(j => inFilter(j, k)).length; return h('button', { class: 'chip' + (state.filter === k ? ' on' : ''), type: 'button', onclick: () => { state.filter = k; drawJobs(); } }, t, h('span', { class: 'chip-n', text: n })); }));
    const shown = jobs.filter(j => inFilter(j, state.filter));
    jobsList.replaceChildren();
    if (!jobs.length) jobsList.append(h('div', { class: 'empty' }, h('p', { text: 'No jobs yet' }), h('p', { class: 'small', text: 'Use Find and apply on Home, or paste a job link above.' })));
    else if (!shown.length) jobsList.append(h('div', { class: 'empty', text: 'Nothing in this view' }));
    for (const j of shown) jobsList.append(jobRow(j, fit[j.id] || {}, drawJobs));
    summary.textContent = jobs.length ? `${plural(jobs.length, 'job')} tracked` : '';
  }
  await drawJobs();
  clearInterval(state.runTimer);
  state.runTimer = setInterval(() => { if (!document.body.contains(jobsList)) return clearInterval(state.runTimer); if (!state.openJob) drawJobs().catch(() => {}); }, 8000);
}

function questionCard(q, after) {
  const options = (q.options || []).filter(Boolean);
  const input = options.length && (q.field_type === 'select-one' || q.field_type === 'combobox')
    ? h('select', { class: 'answer', required: true }, h('option', { value: '', text: 'Choose…' }), options.map(o => h('option', { value: o, text: o })))
    : h('input', { required: true, placeholder: 'Your answer' });
  const scope = h('select', { class: 'scope', title: 'Where to reuse this answer' }, h('option', { value: 'job', text: 'This job only' }), h('option', { value: 'role', text: 'Similar roles' }), h('option', { value: 'global', text: 'Every job' }));
  const expires = h('input', { type: 'date', title: 'Forget this answer after (optional)', hidden: true });
  scope.onchange = () => (expires.hidden = scope.value === 'job');
  const save = h('button', { class: 'btn ghost sm', text: 'Save' });
  const form = h('form', { class: 'q' }, h('div', { class: 'q-label', text: q.label }), h('div', { class: 'q-job', text: [q.company, q.title].filter(Boolean).join(' · ') || 'Application question' }),
    h('div', { class: 'q-row' }, input, scope, expires, save));
  if (q.suggestion) form.append(h('div', { class: 'hint' }, 'Similar saved answer: “' + q.suggestion.answer + '”', h('button', { class: 'btn ghost sm', type: 'button', text: 'Use it', onclick: () => (input.value = q.suggestion.answer) })));
  form.onsubmit = e => { e.preventDefault(); busy(save, async () => {
    await post('/api/questions/' + q.id + '/answer', { answer: input.value.trim(), scope: scope.value, role_type: scope.value === 'role' ? (q.title || '') : '', expires_at: expires.hidden ? null : (expires.value || null) });
    toast('Answer saved and filled'); await after();
  }); };
  return form;
}

function resumePicker() {
  const sel = h('select', { title: 'Resume to use' });
  if (!state.resumes.length) sel.append(h('option', { value: '', text: 'No resume yet' }));
  for (const r of state.resumes) sel.append(h('option', { value: r.id, text: r.name }));
  return sel;
}

function jobRow(j, t, after) {
  const open = state.openJob === j.id;
  const head = h('button', { class: 'job-head', type: 'button' },
    h('div', { class: 'job-main' }, h('div', { class: 'job-title', text: j.title || 'Untitled role' }), jobMeta(j)),
    fitPill(t.fit), statusPill(j.status), h('span', { class: 'chev', text: '▶' }));
  const row = h('div', { class: 'job' + (open ? ' open' : '') }, head);
  head.onclick = () => { state.openJob = open ? null : j.id; row.replaceWith(jobRow(j, t, after)); };
  if (open) row.append(jobBody(j, t, after));
  return row;
}
const hostOf = u => { try { return new URL(u).hostname; } catch { return u; } };

function jobBody(j, t, after) {
  const id = j.id;
  // Keep the last result for this job across list refreshes.
  const out = h('div', { class: 'output' }, state.outputs[id] || []);
  const show = (...nodes) => { state.outputs[id] = nodes.filter(Boolean); out.replaceChildren(...state.outputs[id]); };
  const resume = resumePicker();
  api('/api/jobs/' + id + '/resume-match').then(r => { const best = r.ranking?.[0]?.id; if (best) resume.value = best; }).catch(() => {});
  const needResume = () => { if (!resume.value) throw Error('Add a resume in Settings first.'); return resume.value; };
  const b = (text, fn, cls = 'btn ghost sm') => { const el = h('button', { class: cls, type: 'button', text }); el.onclick = () => busy(el, fn); return el; };

  const openBtn = b('1 · Open in Chrome', async () => { await post('/api/browser/open').catch(() => {}); await post('/api/jobs/' + id + '/open'); toast('Opened in Chrome'); }, 'btn ghost sm');
  const fillBtn = b('2 · Fill the form', async () => {
    const r = await post('/api/jobs/' + id + '/fields');
    const f = r.fields || []; const filled = f.filter(x => x.value || (x.files && x.files.length)).length;
    const missing = f.filter(x => !x.value && !(x.files && x.files.length) && x.label);
    show(h('p', {}, h('b', { text: `Filled ${filled} of ${f.length} fields.` }), missing.length ? ' Anything left is waiting for you under “Needs your answer”, or needs a file.' : ' Everything on this page is filled.'),
      missing.length ? h('ul', { class: 'small muted', style: 'margin:8px 0 0;padding-left:18px' }, missing.slice(0, 12).map(x => h('li', { text: x.label }))) : null);
    await after();
  }, 'btn ghost sm');
  const reviewBtn = b('3 · Review and submit', () => openReview(id, after), 'btn ghost sm');
  const steps = h('div', { class: 'steps' }, openBtn, fillBtn, reviewBtn);

  const fitBtn = b('Check fit', async () => { const r = await post('/api/jobs/' + id + '/fit', { resume_id: needResume() }); show(renderFit(r)); });
  const attachBtn = b('Attach resume', async () => { const r = await post('/api/jobs/' + id + '/attach-resume', { resume_id: needResume() }); toast('Attached ' + (r.name || 'resume') + ' in Chrome'); });
  const coverBtn = b('Cover letter', async () => {
    const d = await post('/api/jobs/' + id + '/cover-letter', { resume_id: needResume() });
    const put = b('Attach this letter', async () => { await post('/api/jobs/' + id + '/cover-letter/attach', { cover_id: d.id }); toast('Cover letter attached in Chrome'); }, 'btn sm');
    show(h('p', { class: 'small muted', style: 'margin-bottom:8px', text: d.notice }), h('pre', { text: d.text }), h('div', { class: 'row', style: 'margin-top:10px' }, put));
  });

  const menuItems = [
    ['Continue to next page', async () => { const r = await post('/api/jobs/' + id + '/next'); toast(r.message || 'Moved to the next page'); }],
    ['Compare my resumes', async () => { const r = await api('/api/jobs/' + id + '/resume-match'); show(h('p', { class: 'small muted', text: 'Ranked by ' + r.method }), h('ol', { style: 'margin:8px 0 0;padding-left:20px' }, (r.ranking || []).map(x => h('li', { text: (x.name || 'Resume ' + x.id) + (x.score != null ? ` — ${Math.round(x.score * 100) / 100}` : '') })))); }],
    ['Find verification email', async () => { const r = await post('/api/jobs/' + id + '/gmail-verification'); show(h('p', { class: 'small muted', text: r.notice }), h('pre', { text: JSON.stringify(r.messages, null, 2) })); }],
    ['Check for status emails', async () => { const r = await post('/api/jobs/' + id + '/gmail-status'); show(h('p', { class: 'small muted', text: r.notice }), h('pre', { text: JSON.stringify(r.matches, null, 2) })); await after(); }],
    ['Create a job-site account', () => accountFlow(id, show)],
    ['Sign in with a saved account', () => signInFlow(id, show)],
  ];
  const statusMenu = [['found', 'New'], ['skipped', 'Skipped'], ['submitted', 'Submitted (I did it myself)'], ['interview', 'Interview'], ['rejected', 'Rejected']];
  const pop = h('div', { class: 'menu-pop' },
    menuItems.map(([text, fn]) => h('button', { type: 'button', text, onclick: async () => { menu.open = false; try { await fn(); } catch (e) { toast(e.message, true); } } })),
    h('div', { class: 'small muted', style: 'padding:8px 10px 4px', text: 'Mark as' }),
    statusMenu.map(([s, text]) => h('button', { type: 'button', text, onclick: async () => { menu.open = false; try { await post('/api/jobs/' + id + '/status', { status: s }); await after(); } catch (e) { toast(e.message, true); } } })));
  const menu = h('details', { class: 'menu' }, h('summary', { class: 'btn quiet sm', text: 'More ▾' }), pop);

  const meta = h('p', { class: 'small muted', style: 'margin-top:12px' }, h('a', { href: j.url, target: '_blank', rel: 'noopener noreferrer', text: 'View posting ↗' }), j.created_at ? ' · Added ' + j.created_at.slice(0, 10) : '', t.resume ? ' · Fit checked with ' + t.resume : '');
  const decide = ['check match', 'review fit'].includes(j.status) || (j.status === 'waiting on user' && j.match_note)
    ? h('div', { class: 'decide' }, h('span', { class: 'why', text: j.match_note || 'Not quite what you asked for' }), h('span', { class: 'spacer' }),
        b('Skip', async () => { await post('/api/jobs/' + id + '/status', { status: 'skipped' }); toast('Skipped'); await after(); }, 'btn quiet sm'),
        j.status === 'waiting on user' ? null : b('Apply', async () => { await post('/api/jobs/' + id + '/status', { status: j.status === 'review fit' ? 'approved' : 'found' }); await post('/api/runs').catch(() => {}); toast('Queued to fill'); await after(); }, 'btn sm'))
    : null;
  return h('div', { class: 'job-body' }, meta, decide, steps, h('div', { class: 'tools' }, resume, fitBtn, attachBtn, coverBtn, h('span', { class: 'spacer' }), menu), out);
}

function renderFit(r) {
  const [label, cls] = FIT[r.result] || [r.result, ''];
  const reqs = (r.requirements || []).map(x => h('li', {}, h('span', { class: 'mark ' + x.assessment, text: x.assessment === 'met' ? '✓' : x.assessment === 'not_met' ? '✕' : '?' }),
    h('div', {}, h('div', {}, x.requirement, x.kind === 'preferred' ? h('span', { class: 'small muted', text: ' · nice to have' }) : null), h('div', { class: 'small muted', text: x.reason }), x.evidence ? h('q', { text: x.evidence }) : null)));
  const rules = (r.rule_checks || []).filter(x => x.result !== 'pass').map(x => h('li', {}, h('span', { class: 'mark ' + (x.result === 'fail' ? 'not_met' : 'unclear'), text: '!' }), h('div', {}, h('div', { text: x.rule || x.name || 'Your rules' }), h('div', { class: 'small muted', text: x.reason || x.detail || '' }))));
  return h('div', {}, h('div', { class: 'row' }, h('span', { class: 'pill ' + cls, text: label }), h('span', { class: 'small muted', text: 'Based on your resume. Check anything marked “?” yourself.' })), h('ul', { class: 'reqs' }, rules, reqs));
}

async function accountFlow(id, show) {
  const email = h('input', { type: 'email', value: state.profile.email || '', placeholder: 'Account email' });
  const note = h('p', { class: 'small muted', style: 'margin-top:8px' });
  const prepare = h('button', { class: 'btn sm', type: 'button', text: 'Generate and fill' });
  prepare.onclick = () => busy(prepare, async () => {
    const r = await post('/api/jobs/' + id + '/account/prepare', { email: email.value });
    note.textContent = r.notice + ' Site: ' + r.domain;
    const create = h('button', { class: 'btn sm', type: 'button', text: 'Create account on ' + r.domain });
    create.onclick = () => busy(create, async () => { const x = await post('/api/jobs/' + id + '/account/register'); note.textContent = x.status + ': ' + x.notice; });
    note.after(create);
  });
  show(h('p', { class: 'small', text: 'Creates a strong password, saves it in your system credential store and fills the sign-up form. Nothing is created until you confirm.' }), h('div', { class: 'row', style: 'margin-top:8px' }, email, prepare), note);
}
async function signInFlow(id, show) {
  const accounts = await api('/api/accounts');
  if (!accounts.length) throw Error('No saved job-site accounts yet.');
  const sel = h('select', {}, accounts.map(a => h('option', { value: a.id, text: a.domain + ' · ' + a.email })));
  const go = h('button', { class: 'btn sm', type: 'button', text: 'Sign in' });
  go.onclick = () => busy(go, async () => { const r = await post('/api/jobs/' + id + '/account/sign-in', { account_id: sel.value }); toast(r.notice); });
  show(h('div', { class: 'row' }, sel, go));
}

/* Review table. Kept as a global function: tests render it directly. */
function renderReview(snapshot) {
  const container = h('div', {});
  const sensitive = /authoriz|sponsor|salary|compensation|gender|race|ethnic|hispanic|latino|veteran|disab/i;
  const tableFor = (title, items) => {
    const table = h('table', { class: 'review-table' }, h('tr', {}, h('th', { text: 'Question' }), h('th', { text: 'Answer' }), h('th', { text: 'Required' })));
    for (const f of items || []) table.append(h('tr', { class: f.high_stakes || sensitive.test(f.label || '') ? 'high-stakes' : null },
      h('td', { text: f.label || 'Unlabeled field' }), h('td', { text: f.value || (f.files && f.files.join(', ')) || '—' }), h('td', { text: f.required ? 'Yes' : '' })));
    container.append(h('h3', { style: 'margin:18px 0 6px', text: title }), table);
  };
  for (const [i, page] of (snapshot.previous_pages || []).entries()) tableFor('Earlier page ' + (i + 1), page.snapshot.fields);
  tableFor((snapshot.previous_pages || []).length ? 'This page' : 'Answers', snapshot.fields);
  const notes = [...(snapshot.salary_notes || [])];
  for (const p of snapshot.previous_pages || []) notes.push(...(p.snapshot.salary_notes || []));
  if (notes.length) container.append(h('p', { class: 'small muted', style: 'margin-top:10px', text: 'Salary source: ' + notes.map(x => (x.label ? x.label + ' — ' : '') + x.source).join('; ') }));
  if (snapshot.cover_draft) container.append(h('details', { class: 'more', style: 'margin-top:12px' }, h('summary', { text: 'Cover letter draft' }), h('pre', { style: 'white-space:pre-wrap;font-size:13px', text: snapshot.cover_draft.text })));
  container.append(h('p', { class: 'small muted', style: 'margin-top:12px', text: 'Page: ' + (snapshot.url || '') + ((snapshot.submit_controls || []).length ? ' · Submit button: ' + snapshot.submit_controls.map(x => x.label).join(', ') : '') }));
  return container;
}

async function openReview(id, after) {
  const r = await post('/api/jobs/' + id + '/review');
  const confirm = h('input', { type: 'checkbox' });
  const submit = h('button', { class: 'btn', type: 'button', text: 'Submit application', disabled: true });
  const result = h('p', { class: 'small', style: 'margin-top:10px' });
  confirm.onchange = () => (submit.disabled = !confirm.checked);
  submit.onclick = () => busy(submit, async () => {
    const x = await post('/api/jobs/' + id + '/approve-submit', { review_id: r.id, approve: true });
    result.textContent = (STATUS[x.status]?.[0] || x.status) + ' — ' + (x.message || ''); submit.textContent = 'Done'; submit.disabled = true; confirm.disabled = true; await after();
  });
  const shots = [...(r.snapshot.previous_pages || []).map(p => p.screenshot), r.screenshot].filter(Boolean);
  modal(h('h2', { id: 'modal-title', text: 'Review before submitting' }),
    h('p', { class: 'small muted', text: 'Highlighted answers are sensitive. Check them, and the form itself in Chrome, before you submit.' }),
    r.snapshot.fit ? h('div', { style: 'margin-top:12px' }, fitPill(r.snapshot.fit.result)) : null,
    h('details', { class: 'more', style: 'margin-top:14px' }, h('summary', { text: 'Screenshots of the form' }), shots.map(s => h('img', { class: 'shot', src: s, alt: 'Application page', style: 'margin-bottom:8px' }))),
    renderReview(r.snapshot),
    h('div', { style: 'margin-top:20px;padding-top:16px;border-top:1px solid var(--line)' },
      h('label', { class: 'check' }, confirm, h('div', { text: 'I checked every answer and want OfferLetter to click Submit once.' })), h('div', { class: 'row' }, submit), result));
}

/* ---------- find jobs ---------- */
function openFind() {
  const pane = h('div', {});
  const tabs = [['board', 'Company career page'], ['sites', 'Job sites'], ['simplify', 'Student lists']];
  const bar = h('div', { class: 'tabs' });
  const draw = key => {
    bar.replaceChildren(...tabs.map(([k, t]) => h('button', { class: 'tab' + (k === key ? ' on' : ''), type: 'button', text: t, onclick: () => draw(k) })));
    pane.replaceChildren(findPane(key));
  };
  modal(h('h2', { id: 'modal-title', text: 'Find jobs' }), h('p', { class: 'small muted', text: 'Only jobs that match your titles and locations are added.' }), bar, pane);
  draw('board');
}
function findPane(key) {
  const status = h('p', { class: 'small muted', style: 'margin-top:10px' });
  const ready = !!(state.rules.titles || '').trim();
  const done = async r => { status.textContent = `Found ${r.found}, added ${r.added}.`; if (r.added) refreshHomeSoon(); };
  if (key === 'board') {
    const form = h('form', {}, h('div', { class: 'grid2' }, field('Careers site', 'provider', { options: [['greenhouse', 'Greenhouse'], ['lever', 'Lever'], ['ashby', 'Ashby']] }), field('Company board name', 'board', { required: true, placeholder: 'figma', hint: 'The name in the URL, e.g. boards.greenhouse.io/figma' })));
    const go = h('button', { class: 'btn', text: 'Find jobs' });
    form.append(go, status);
    form.onsubmit = e => { e.preventDefault(); busy(go, async () => { status.textContent = 'Checking…'; await done(await post('/api/discover', readForm(form))); }); };
    return form;
  }
  if (key === 'sites') {
    const form = h('form', {}, h('div', { class: 'grid2' }, field('Search for', 'query', { required: true }), field('Location', 'location')),
      h('div', { class: 'grid2' }, field('Results per site', 'limit', { type: 'number', min: 1, max: 100 }), field('Posted within (hours)', 'hours_old', { type: 'number', min: 1 })),
      h('div', { class: 'row', style: 'gap:16px;margin-bottom:8px' }, [['linkedin', 'LinkedIn', true], ['indeed', 'Indeed', true], ['glassdoor', 'Glassdoor'], ['google', 'Google Jobs'], ['zip_recruiter', 'ZipRecruiter']].map(([v, t, on]) => h('label', { class: 'check', style: 'margin:0' }, h('input', { type: 'checkbox', name: 'site', value: v, checked: !!on }), on ? t : t + ' (often blocked)'))),
      h('p', { class: 'small muted', style: 'margin-bottom:12px', text: 'Google Jobs, Glassdoor and ZipRecruiter currently block or ignore these searches, so they usually return nothing.' }),
      check('Also fetch full descriptions (slower)', 'fetch_description'),
      h('div', { class: 'note warn', style: 'margin-bottom:14px', text: 'Your search terms are sent to these sites. Some use browser-style connections and may rate-limit or block searches.' }));
    form.elements.query.value = (state.rules.titles || '').split(',')[0].trim();
    form.elements.location.value = (state.rules.locations || '').split(',')[0].trim();
    form.elements.limit.value = 20;
    const go = h('button', { class: 'btn', text: 'Search', disabled: !ready });
    if (!ready) status.textContent = 'Add job titles in Settings → Job preferences first.';
    form.append(go, status);
    form.onsubmit = e => { e.preventDefault(); busy(go, async () => {
      status.textContent = 'Searching job sites…';
      const r = await post('/api/discover/jobspy', { query: form.elements.query.value, location: form.elements.location.value, limit: form.elements.limit.value, hours_old: form.elements.hours_old.value, sites: [...form.querySelectorAll('input[name=site]:checked')].map(x => x.value), fetch_description: form.elements.fetch_description.checked });
      status.textContent = r.sources.map(x => `${x.source}: ${x.added} added` + (x.error ? ` (${x.error})` : '')).join(' · '); refreshHomeSoon();
    }); };
    return form;
  }
  const stage = { internship: 'internships', new_grad: 'new_grad' }[state.rules.career_stage];
  const go = h('button', { class: 'btn', type: 'button', text: stage === 'internships' ? 'Import internships' : 'Import new-grad roles', disabled: !ready || !stage });
  go.onclick = () => busy(go, async () => { status.textContent = 'Importing…'; await done(await post('/api/discover/simplify', { list: stage })); });
  if (!stage) status.textContent = 'Set your career stage to Internship or New graduate in Settings → Job preferences to use these lists.';
  return h('div', {}, h('p', { class: 'small', style: 'margin-bottom:14px', text: 'Public lists of internship and new-graduate roles maintained by SimplifyJobs on GitHub. Many entries have no full description.' }), go, status);
}
let homeTimer;
function refreshHomeSoon() { clearTimeout(homeTimer); homeTimer = setTimeout(() => { if (!location.hash.startsWith('#/settings') && $('#modal').hidden) route(); }, 300); }

/* ---------- modal ---------- */
function modal(...nodes) { $('#modal-body').replaceChildren(...nodes.flat().filter(n => n != null && n !== false)); $('#modal').hidden = false; document.body.style.overflow = 'hidden'; }
function closeModal() { $('#modal').hidden = true; document.body.style.overflow = ''; if (!location.hash.startsWith('#/settings')) route(); }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal' || e.target.closest('[data-close]')) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });

/* ---------- settings ---------- */
const SECTIONS = [
  ['profile', 'Profile'], ['experience', 'Work experience'], ['resumes', 'Resumes'], ['preferences', 'Job preferences'], ['salary', 'Salary'],
  ['sources', 'Job sources'], ['model', 'AI model'], ['answers', 'Saved answers'], ['accounts', 'Accounts & email'], ['browser', 'Browser'], ['activity', 'Activity'],
];
async function renderSettings(key) {
  if (!SECTIONS.some(s => s[0] === key)) key = 'profile';
  const top = h('header', { class: 'top' }, h('div', { class: 'top-in' }, brand(), h('span', { class: 'spacer' }), h('a', { class: 'btn ghost sm', href: '#/', text: 'Done' })));
  const nav = h('nav', { class: 'snav' }, SECTIONS.map(([k, t]) => h('a', { href: '#/settings/' + k, class: k === key ? 'on' : null, text: t })), h('hr'),
    h('a', { href: '#', text: 'Run setup again', onclick: async e => { e.preventDefault(); await post('/api/onboarding', { done: false }); location.hash = '#/welcome/1'; } }));
  const panel = h('div', { class: 'spanel' });
  $('#app').replaceChildren(top, h('main', { class: 'wrap' }, h('div', { class: 'settings' }, nav, panel)));
  const title = SECTIONS.find(s => s[0] === key)[1];
  panel.append(h('h1', { text: title }));
  await (SETTINGS[key])(panel);
}
function savingForm(children, onSave, label = 'Save changes') {
  const btn = h('button', { class: 'btn', text: label });
  const form = h('form', { class: 'card' }, children, h('div', { class: 'form-foot' }, btn));
  form.onsubmit = e => { e.preventDefault(); busy(btn, async () => { await onSave(readForm(form), form); toast('Saved'); }); };
  return form;
}
const lead = text => h('p', { class: 'lead', text });
const SETTINGS = {
  async experience(p) {
    p.append(lead('Your employment history, including internships, contracts and part-time work.'));
    const editor=experienceEditor(state.profile.experience);
    p.append(savingForm([editor],()=>saveProfile({experience:editor.read()})));
  },
  async profile(p) {
    p.append(lead('Used to fill the standard fields on every application.'));
    const f = savingForm([...contactFields(), h('h3', { style: 'margin:8px 0 12px', text: 'Eligibility' }), ...eligibilityFields(), h('div', { style: 'height:16px' }), ...educationFields(), selfIdFields()], d => saveProfile(d));
    fillForm(f, state.profile); p.append(f);
  },
  async resumes(p) {
    p.append(lead('Keep a version for each kind of role. OfferLetter picks the closest match for each job, and you can change it.'));
    const list = resumeList();
    const form = h('form', { class: 'card' }, field('Resume PDF', 'file', { type: 'file' }), field('Roles this resume is for', 'titles', { placeholder: 'Software Engineer, Data Engineer' }));
    form.querySelector('input[type=file]').accept = 'application/pdf';
    const btn = h('button', { class: 'btn', text: 'Upload resume' }); form.append(h('div', { class: 'form-foot' }, btn));
    form.onsubmit = e => { e.preventDefault(); busy(btn, async () => { await uploadResume(form); list.redraw(); toast('Resume added'); }); };
    p.append(h('div', { class: 'card' }, list), form);
  },
  async preferences(p) {
    p.append(lead('Which jobs OfferLetter looks for, and how it treats ones that don’t clearly fit.'));
    const f = savingForm([...preferenceFields(),
      h('div', { class: 'grid2' }, field('Skip postings older than (days)', 'max_age_days', { type: 'number', min: 0 }), field('Never apply to', 'excluded_companies', { placeholder: 'Company names, comma separated' })),
      field('When a job is a borderline fit', 'strictness', { options: [['flag', 'Ask me'], ['skip', 'Skip it'], ['apply', 'Prepare it anyway']] })], d => saveRules(d));
    fillForm(f, state.rules); p.append(f);
  },
  async salary(p) {
    p.append(lead('How to answer salary questions. Only clearly labeled annual USD fields are filled automatically.'));
    const fixed = h('div', {}, field('Annual salary (USD)', 'fixed_salary', { type: 'number', min: 1 }));
    const role = h('div', {}, field('Salary by role', 'role_salaries', { type: 'textarea', rows: 3, placeholder: 'Software Engineer=100000', hint: 'One exact job title = amount per line.' }));
    const market = h('div', {}, field('Occupation code', 'bls_soc', { placeholder: '15-1252', hint: 'From the U.S. Bureau of Labor Statistics. National medians can be coarse for entry-level roles.' }));
    const f = savingForm([field('Answer salary questions by', 'salary_mode', { options: [['ask', 'Asking me each time'], ['fixed', 'Using one fixed amount'], ['role', 'Using an amount per role'], ['posting', 'Using the middle of the posted range'], ['market', 'Using a market estimate'], ['optional', 'Leaving optional fields blank']] }),
      fixed, role, market,
      h('details', { class: 'more' }, h('summary', { text: 'Advanced' }), h('div', { class: 'grid2' }, field('Skip jobs paying less than (USD/yr)', 'salary_floor', { type: 'number', min: 0 }), field('If that fails, try', 'salary_fallback', { placeholder: 'posting, ask' })))], d => saveRules(d));
    fillForm(f, state.rules);
    const sync = () => { const m = f.elements.salary_mode.value; fixed.hidden = m !== 'fixed'; role.hidden = m !== 'role'; market.hidden = m !== 'market'; };
    f.elements.salary_mode.onchange = sync; sync(); p.append(f);
  },
  async sources(p) {
    p.append(lead('Check company career pages automatically while OfferLetter is open. Use Find jobs on the home page for a one-off search.'));
    const cfg = await api('/api/schedule');
    const f = savingForm([check('Check for new jobs automatically', 'enabled'),
      field('Career pages to check', 'boards', { type: 'textarea', rows: 4, placeholder: 'greenhouse:figma\nlever:company\nsimplify:new_grad', hint: 'One per line, as site:name. Sites: greenhouse, lever, ashby, simplify, jobspy.' }),
      field('Check every (minutes)', 'interval_minutes', { type: 'number', min: 1, max: 10080 }),
      check('Prepare matching jobs after each check', 'prepare_jobs', 'Preparation still stops for your questions and review.')],
    async d => {
      const boards = d.boards.split('\n').map(x => x.trim()).filter(Boolean).map(x => { const parts = x.split(':'); if (parts.length !== 2) throw Error('Write each line as site:name.'); return { provider: parts[0].trim(), board: parts[1].trim() }; });
      await post('/api/schedule', { boards, enabled: d.enabled, prepare_jobs: d.prepare_jobs, interval_minutes: d.interval_minutes });
    });
    fillForm(f, { enabled: cfg.enabled, prepare_jobs: !!cfg.prepare_jobs, interval_minutes: cfg.interval_minutes, boards: (cfg.boards || []).map(x => x.provider + ':' + x.board).join('\n') });
    const runNow = h('button', { class: 'btn ghost', type: 'button', text: 'Check now' });
    const last = h('span', { class: 'small muted', text: cfg.last_run ? 'Last checked ' + cfg.last_run : '' });
    runNow.onclick = () => busy(runNow, async () => { const r = await post('/api/schedule/run'); last.textContent = (Array.isArray(r.boards) ? r.boards : []).map(b => typeof b !== 'object' ? String(b) : [b.provider && b.board ? b.provider + ':' + b.board : '', b.added != null ? b.added + ' added' : '', b.error || ''].filter(Boolean).join(' ')).join(' · ') || 'Checked'; });
    f.querySelector('.form-foot').append(runNow, last); p.append(f);
  },
  async model(p) {
    p.append(lead('Used for fit checks and cover letters. A model on this computer keeps your resume private.'));
    const cfg = await api('/api/settings/model');
    const cloudBits = h('div', {}, field('API key', 'api_key', { type: 'password', hint: 'Leave blank to keep the saved key. Stored in your system credential store.' }), check('I understand my resume and job text will be sent to this provider.', 'cloud_consent'));
    const localBits = h('div', {}, field('Server address', 'base_url'));
    const f = savingForm([h('div', { class: 'grid2' }, field('Provider', 'provider', { options: [['local', 'On this computer'], ['openai', 'OpenAI'], ['claude', 'Claude'], ['gemini', 'Gemini'], ['openrouter', 'OpenRouter']] }), field('Model name', 'model', { required: true })),
      localBits, cloudBits, check('Let the model help recognize simple form fields', 'map_fields', 'Only names, email, phone and links. Never sensitive questions.')],
    async d => { await post('/api/settings/model', { ...d, base_url: d.base_url || 'http://127.0.0.1:11434/v1' }); f.elements.api_key.value = ''; });
    fillForm(f, { ...cfg, base_url: cfg.base_url || 'http://127.0.0.1:11434/v1' });
    const sync = () => { const local = f.elements.provider.value === 'local'; localBits.hidden = !local; cloudBits.hidden = local; };
    f.elements.provider.onchange = sync; sync();
    const emb = await api('/api/settings/embeddings');
    const g = savingForm([check('Match new questions to answers I’ve saved', 'enabled', 'Uses a small local model. Close matches are filled; others are suggested for you to confirm.'),
      h('div', { class: 'grid2' }, field('Embedding model', 'model'), field('Server address', 'base_url'))], d => post('/api/settings/embeddings', d));
    fillForm(g, emb);
    p.append(f, h('h3', { style: 'margin:26px 0 10px', text: 'Answer matching' }), g);
  },
  async answers(p) {
    p.append(lead('Answers you’ve given to application questions. OfferLetter reuses them only where you allowed.'));
    const card = h('div', { class: 'card' });
    const draw = async () => {
      const rows = await api('/api/answers'); card.replaceChildren();
      if (!rows.length) return card.append(h('p', { class: 'muted', text: 'No saved answers yet. They appear here as you answer questions.' }));
      const scope = { job: 'This job', role: 'Similar roles', global: 'Every job' };
      card.append(h('ul', { class: 'kv' }, rows.map(a => h('li', {}, h('div', { style: 'flex:1;min-width:0' }, h('div', { style: 'font-weight:550', text: a.question }), h('div', { class: 'small muted', text: a.answer })),
        h('span', { class: 'pill', text: scope[a.scope] || a.scope }), h('button', { class: 'btn quiet sm', type: 'button', text: 'Delete', onclick: async () => { await api('/api/answers/' + a.id, { method: 'DELETE' }); draw(); } })))));
    };
    await draw(); p.append(card);
  },
  async accounts(p) {
    p.append(lead('Accounts OfferLetter created on job sites, and optional Gmail access for verification codes.'));
    const acc = h('div', { class: 'card' });
    const rows = await api('/api/accounts').catch(() => []);
    if (!rows.length) acc.append(h('p', { class: 'muted', text: 'No job-site accounts yet. Create one from a job’s More menu when a site needs it.' }));
    else acc.append(h('ul', { class: 'kv' }, rows.map(a => { const li = h('li', {}, h('div', { style: 'flex:1' }, h('div', { text: a.domain }), h('div', { class: 'small muted', text: a.email + ' · ' + a.status })));
      const reveal = h('button', { class: 'btn quiet sm', type: 'button', text: 'Show password' });
      reveal.onclick = () => busy(reveal, async () => { const r = await post('/api/accounts/' + a.id + '/reveal'); const c = h('code', { text: r.password }); reveal.replaceWith(c); setTimeout(() => c.replaceWith(reveal), 30000); });
      li.append(reveal); return li; })));
    const gs = await api('/api/gmail/settings').catch(() => ({}));
    const gstatus = h('span', { class: 'pill ' + (gs.connected ? 'good' : ''), text: gs.connected ? 'Connected' : 'Not connected' });
    const client = field('Google desktop OAuth client (JSON)', 'client_json', { type: 'textarea', rows: 3, hint: 'Create one in Google Cloud with the Gmail API enabled. Access is read-only.' });
    const connect = h('button', { class: 'btn ghost', type: 'button', text: 'Connect Gmail' });
    const disconnect = h('button', { class: 'btn quiet', type: 'button', text: 'Disconnect' });
    connect.onclick = () => busy(connect, async () => { const popup = window.open('about:blank', '_blank'); try { const r = await post('/api/gmail/connect', { client_json: client.querySelector('textarea').value }); client.querySelector('textarea').value = ''; if (popup) popup.location.href = r.authorization_url; else window.location.href = r.authorization_url; } catch (e) { popup && popup.close(); throw e; } });
    disconnect.onclick = () => busy(disconnect, async () => { const r = await post('/api/gmail/disconnect'); toast(r.notice); });
    const gform = savingForm([h('div', { class: 'row', style: 'margin-bottom:14px' }, h('h3', { text: 'Gmail' }), gstatus), gs.connected ? null : client, h('div', { class: 'row', style: 'margin-bottom:16px' }, gs.connected ? disconnect : connect),
      check('Find verification codes', 'codes'), check('Find verification links', 'links', 'Shown to you, never clicked automatically.'), check('Update job status from interview and rejection emails', 'status_updates')],
    d => post('/api/gmail/settings', { codes: d.codes, links: d.links, status_updates: d.status_updates }));
    fillForm(gform, gs);
    p.append(h('h3', { style: 'margin:0 0 10px', text: 'Job-site accounts' }), acc, h('div', { style: 'height:18px' }), gform);
  },
  async browser(p) {
    p.append(lead('OfferLetter uses its own Chrome profile. Sign in to job sites there once; your sign-ins stay on this computer.'));
    const s = await api('/api/session');
    const btn = h('button', { class: 'btn', type: 'button', text: s.browser_open ? 'Chrome is open' : 'Open Chrome', disabled: s.browser_open });
    btn.onclick = () => busy(btn, async () => { await post('/api/browser/open'); btn.textContent = 'Chrome is open'; btn.disabled = true; });
    p.append(h('div', { class: 'card' }, h('div', { class: 'row' }, btn, h('span', { class: 'small muted', text: s.browser_open ? 'It’s running now' : 'A separate window opens' }))));
    const tabs = savingForm([field('Chrome tabs open at once', 'tab_limit', { type: 'number', min: 1, max: 10, hint: 'Find and apply fills up to this many applications at the same time, then waits until you finish or close one.' }),
      field('Model calls at once', 'screen_parallel', { type: 'number', min: 0, max: 16, hint: 'How many jobs the model screens at the same time. 0 picks for you: 2 for a local model, 6 for a hosted one.' })],
      d => saveRules({ tab_limit: Math.max(1, Math.min(10, parseInt(d.tab_limit, 10) || 3)), screen_parallel: Math.max(0, Math.min(16, parseInt(d.screen_parallel, 10) || 0)) }));
    fillForm(tabs, { tab_limit: state.rules.tab_limit || 3, screen_parallel: state.rules.screen_parallel || 0 });
    p.append(h('h3', { style: 'margin:24px 0 12px', text: 'Tabs' }), tabs);
  },
  async activity(p) {
    p.append(lead('What OfferLetter has done, and a check that nothing was ever submitted without your approval.'));
    const m = await api('/api/metrics').catch(() => null);
    if (m) {
      const cov = m.form_coverage || {};
      p.append(h('div', { class: 'stats' },
        h('div', { class: 'stat' }, h('b', { text: m.applications }), h('span', { text: 'Applications submitted' })),
        h('div', { class: 'stat' }, h('b', { text: (m.submits_without_approval || []).length }), h('span', { text: 'Submitted without approval' + (m.audit_ok ? ' · audit passed' : ' · audit failed') })),
        h('div', { class: 'stat' }, h('b', { text: `${cov.succeeded ?? 0}/${cov.attempted ?? 0}` }), h('span', { text: 'Forms filled' })),
        h('div', { class: 'stat' }, h('b', { text: m.fit_checks_run }), h('span', { text: 'Fit checks' }))));
      const curve = (m.questions_per_application || []).map(x => x.questions);
      if (curve.length) p.append(h('p', { class: 'small muted', style: 'margin-bottom:16px', text: 'Questions asked per application, first ten: ' + curve.join(', ') }));
    }
    const reply = h('p', { class: 'small', style: 'margin-top:10px' });
    const ask = h('input', { name: 'message', maxlength: 500, required: true, placeholder: 'What is waiting on me?' });
    const askBtn = h('button', { class: 'btn ghost', text: 'Ask' });
    const chat = h('form', { class: 'card' }, h('h3', { style: 'margin-bottom:10px', text: 'Ask OfferLetter' }), h('div', { class: 'addbar', style: 'margin:0' }, ask, askBtn), reply);
    chat.onsubmit = e => { e.preventDefault(); busy(askBtn, async () => { const r = await post('/api/chat', { message: ask.value }); reply.textContent = r.reply; ask.value = ''; }); };
    const events = await api('/api/events').catch(() => []);
    const list = h('ul', { class: 'events' }, events.length ? events.map(e => h('li', {}, h('time', { text: (e.created_at || '').slice(5, 16) }), h('span', { text: e.detail }))) : h('li', { class: 'muted', text: 'Nothing yet' }));
    p.append(chat, h('h3', { style: 'margin:24px 0 6px', text: 'Recent activity' }), h('div', { class: 'card', style: 'padding:6px 20px' }, list));
  },
};

/* ---------- router ---------- */
let routing = Promise.resolve();
function route() { routing = routing.then(doRoute).catch(e => toast(e.message, true)); return routing; }
async function doRoute() {
  const hash = location.hash.replace(/^#/, '') || '/';
  const parts = hash.split('/').filter(Boolean);
  const ob = await api('/api/onboarding').catch(() => ({ done: true }));
  if (!ob.done && parts[0] !== 'welcome') { location.hash = '#/welcome'; return; }
  if (parts[0] === 'welcome') return renderOnboarding(Number(parts[1] || 0));
  if (parts[0] === 'settings') return renderSettings(parts[1]);
  if (parts[0] === 'jobs') return renderJobs();
  return renderHome();
}
window.addEventListener('hashchange', () => { if (!$('#modal').hidden) { $('#modal').hidden = true; document.body.style.overflow = ''; } route(); });

(async () => {
  try { token = (await api('/api/session')).token; await loadBasics(); } catch (e) { $('#app').replaceChildren(h('p', { class: 'boot', text: 'Could not reach OfferLetter. Is the server running?' })); return; }
  route();
})();
