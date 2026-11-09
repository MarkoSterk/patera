const root = document.querySelector('#app');
const identity = document.querySelector('#identity');
const accountActions = document.querySelector('#account-actions');

let user = null;
let data = {subjects: [], categories: [], questions: [], exams: []};
let subjectFilter = '';
let categoryFilter = []; // category ids shown in the Questions list; empty = all
let section = new URLSearchParams(location.search).get('view') === 'admin' ? 'admin' : 'exams';
let imageData = '';

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const title = text => text[0].toUpperCase() + text.slice(1);
const pct = value => `${value.toFixed(1)}%`;
const when = value => esc(new Date(value).toLocaleString());
const math = value => `<span class="math-text">${esc(value)}</span>`;
const MATH_HINT = '<p><small>Write math in LaTeX between $…$, or $$…$$ for a centred line. Type \\$ for a dollar sign.</small></p>';

function notice(message) {
  const box = document.querySelector('#notice');
  box.textContent = message;
  box.hidden = !message;
}

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(method, path, body) {
  const options = {method, headers: {}};
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const result = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = Array.isArray(result?.data) && result.data[0]?.msg;
    throw new ApiError(response.status, detail ? detail.replace(/^Value error, /, '') : result?.message || 'Request failed');
  }
  return result;
}

function run(work) {
  notice('');
  Promise.resolve().then(work).catch(error => {
    if (error.status === 401 && user) { user = null; showLogin(); }
    notice(error.message);
  });
}

const field = (label, name, value = '', type = 'text', extra = '') =>
  `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const options = (items, selected) =>
  items.map(item => `<option value="${item.id}" ${item.id === selected ? 'selected' : ''}>${esc(item.name)}</option>`).join('');
const choose = (prompt, items, selected) =>
  `<option value="" ${selected ? '' : 'selected'} disabled>${prompt}</option>${options(items, selected)}`;
const subjectName = id => data.subjects.find(s => s.id === id)?.name;
const categoryName = id => data.categories.find(c => c.id === id)?.name;
const inSubject = (items, subjectId) => items.filter(item => item.subject_id === subjectId);
const plural = (count, noun) => `${count} ${noun}${count === 1 ? '' : 's'}`;
const points = value => plural(value, 'point');

function localDate(value) {
  const date = value ? new Date(value) : new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function showLogin() {
  identity.textContent = '';
  accountActions.replaceChildren();
  root.innerHTML = `<section class="card narrow"><p>INSTRUCTOR WORKSPACE</p><h1>Ready for the next exam?</h1>
    <p>Sign in to manage your question bank, publish exams, and review results.</p>
    <form id="login">${field('Email', 'email', '', 'email', 'required autocomplete="username"')}
    ${field('Password', 'password', '', 'password', 'required autocomplete="current-password"')}<button>Sign in</button></form></section>`;
  document.querySelector('#login').onsubmit = event => {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.target));
    run(async () => {
      user = (await api('POST', '/api/auth/login', form)).user;
      await refresh();
    });
  };
}

async function logout() {
  await api('GET', '/api/auth/logout');
  user = null;
  showLogin();
}

const isInstructor = () => user.roles.includes('INSTRUCTOR');
const isAdmin = () => user.roles.includes('ADMIN');

async function refresh() {
  user = await api('GET', '/api/auth/me');
  if (isInstructor()) {
    const [subjects, categories, questions, exams] = await Promise.all(
      ['subjects', 'categories', 'questions', 'exams'].map(name => api('GET', `/api/${name}/`)));
    data = {subjects, categories, questions, exams};
    if (!subjects.some(s => s.id === subjectFilter)) subjectFilter = '';
    categoryFilter = categoryFilter.filter(id => categories.some(c => c.id === id));
  }
  render();
}

// The signed-in user's email opens a menu with account actions.
function accountMenu() {
  return `<details class="account-menu">
    <summary title="Account"><span class="account-email">${esc(user.email)}</span></summary>
    <div class="account-menu-items">
      <button type="button" data-account="password">Change password</button>
      <button type="button" data-account="logout">Sign out</button>
    </div></details>`;
}

function render() {
  identity.textContent = '';
  accountActions.innerHTML = `${isAdmin() ? '<a class="header-admin" href="/admin/en/dashboard">Admin</a>' : ''}${accountMenu()}`;
  accountActions.querySelector('[data-account="logout"]').onclick = () => run(logout);
  accountActions.querySelector('[data-account="password"]').onclick = () => {
    accountActions.querySelector('.account-menu').open = false;
    section = 'password';
    notice('');
    render();
  };

  const tabs = isInstructor() ? ['exams', 'questions', 'categories', 'subjects', 'reports'] : [];
  root.innerHTML = `<h1>Your exam workspace</h1><p>Build a question bank. Share an exam. See how everyone did.</p>
    <nav>${tabs.map(tab => `<button class="${tab === section ? '' : 'secondary'}" data-tab="${tab}">${title(tab)}</button>`).join('')}
    ${isAdmin() ? `<button data-tab="admin" class="${section === 'admin' ? '' : 'secondary'}">Users &amp; reports</button>` : ''}</nav>
    <div id="content"></div>`;
  root.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => { section = button.dataset.tab; run(refresh); });

  if (section === 'password') { passwordView(); return; }

  if (section === 'admin' || !isInstructor()) {
    if (isAdmin()) run(adminView);
    else document.querySelector('#content').textContent = 'No roles assigned. Contact an administrator.';
    return;
  }
  if (section === 'reports') { run(async () => reportsView(await api('GET', '/api/reports/'))); return; }
  listView();
}

function passwordView() {
  const content = document.querySelector('#content');
  content.innerHTML = `<form class="card narrow-form" id="password-form"><h2>Change password</h2>
    <p>Signed in as ${esc(user.email)}. Changing your password signs you out everywhere else.</p>
    <input type="email" name="username" value="${esc(user.email)}" autocomplete="username" hidden>
    ${field('Current password', 'current_password', '', 'password', 'required autocomplete="current-password"')}
    ${field('New password <small>(at least 12 characters)</small>', 'new_password', '', 'password', 'required minlength="12" maxlength="1024" autocomplete="new-password"')}
    ${field('Repeat the new password', 'confirm_password', '', 'password', 'required minlength="12" maxlength="1024" autocomplete="new-password"')}
    <div class="row"><button>Change password</button><button type="button" id="cancel" class="secondary">Cancel</button></div></form>`;
  const form = content.querySelector('#password-form');
  const confirm = form.querySelector('[name="confirm_password"]');
  const matches = () => confirm.setCustomValidity(
    confirm.value && confirm.value !== form.querySelector('[name="new_password"]').value ? 'The passwords do not match' : '');
  form.querySelector('[name="new_password"]').addEventListener('input', matches);
  confirm.addEventListener('input', matches);
  content.querySelector('#cancel').onclick = () => { section = 'exams'; render(); };
  form.onsubmit = event => {
    event.preventDefault();
    const values = new FormData(form);
    run(async () => {
      const response = await api('POST', '/api/auth/password', {
        current_password: values.get('current_password'),
        new_password: values.get('new_password'),
      });
      user = response.user;
      content.innerHTML = `<section class="card narrow-form" role="status"><h2>Password changed</h2>
        <p>Your new password is active. Other browsers and devices where you were signed in have been signed out.</p>
        <button type="button" id="back">Back to the workspace</button></section>`;
      content.querySelector('#back').onclick = () => { section = isInstructor() ? 'exams' : 'admin'; run(refresh); };
    });
  };
}

const KINDS = {
  exams: {kind: 'exam', path: '/api/exams/', label: exam => esc(exam.title)},
  questions: {kind: 'question', path: '/api/questions/', label: question => math(question.question_text)},
  categories: {kind: 'category', path: '/api/categories/', label: category => esc(category.name)},
  subjects: {kind: 'subject', path: '/api/subjects/', label: subject => esc(subject.name)},
};

function recordDetails(record) {
  if (section === 'exams') {
    const selection = record.random_per_attempt
      ? `Random per attempt: ${plural(record.random_count, 'question')} from ${record.category_ids.length} ${record.category_ids.length === 1 ? 'category' : 'categories'}`
      : plural(record.question_ids.length, 'question');
    return `<p>${esc(subjectName(record.subject_id))} · ${selection} · Pass: ${record.pass_percentage}%</p>
      <p>${when(record.available_from)} – ${when(record.available_until)}</p>`;
  }
  if (section === 'questions') {
    return `<p>${esc(subjectName(record.subject_id))} · ${esc(categoryName(record.category_id))} · ${points(record.points)}</p>`;
  }
  if (section === 'categories') {
    return `<p>${esc(subjectName(record.subject_id))} · ${plural(inSubject(data.questions, record.subject_id).filter(q => q.category_id === record.id).length, 'question')}</p>`;
  }
  if (section === 'subjects') {
    const counts = [['categories', 'category'], ['questions', 'question'], ['exams', 'exam']]
      .map(([key, noun]) => plural(inSubject(data[key], record.id).length, noun)).join(' · ');
    return `${record.description ? `<p>${esc(record.description)}</p>` : ''}<p>${counts}</p>`;
  }
  return '';
}

// A dropdown (details/summary) holding one checkbox per category.
function categoryDropdown(name, categories, selected, emptyLabel, withSubject = false) {
  const label = c => esc(c.name) + (withSubject ? ` <small>(${esc(subjectName(c.subject_id))})</small>` : '');
  return `<details class="multiselect" data-multiselect="${name}" data-empty="${esc(emptyLabel)}">
    <summary>${multiselectSummary(categories.filter(c => selected.includes(c.id)), categories.length, emptyLabel)}</summary>
    <div class="multiselect-menu">
      ${categories.length ? `<div class="row multiselect-actions"><button type="button" class="secondary" data-select="all">Select all</button>
        <button type="button" class="secondary" data-select="none">Clear</button></div>
        ${categories.map(c => `<label><input type="checkbox" name="${name}" value="${c.id}" ${selected.includes(c.id) ? 'checked' : ''}><span>${label(c)}</span>
          <small class="count">${inSubject(data.questions, c.subject_id).filter(q => q.category_id === c.id).length}</small></label>`).join('')}`
        : '<p><small>No categories.</small></p>'}
    </div></details>`;
}

function multiselectSummary(chosen, total, emptyLabel) {
  if (!chosen.length) return esc(emptyLabel);
  if (chosen.length === total && total > 1) return `All categories (${total})`;
  return chosen.length <= 2 ? chosen.map(c => esc(c.name)).join(', ') : `${chosen.length} categories selected`;
}

// Wires a dropdown: select all/clear, a live summary, and onChange(selected ids).
function wireCategoryDropdown(box, onChange) {
  const boxes = () => [...box.querySelectorAll('input[type="checkbox"]')];
  const changed = () => {
    const ids = boxes().filter(b => b.checked).map(b => b.value);
    const chosen = data.categories.filter(c => ids.includes(c.id));
    box.querySelector('summary').innerHTML = multiselectSummary(chosen, boxes().length, box.dataset.empty);
    onChange(ids);
  };
  boxes().forEach(b => b.onchange = changed);
  box.querySelectorAll('[data-select]').forEach(button => button.onclick = () => {
    boxes().forEach(b => b.checked = button.dataset.select === 'all');
    changed();
  });
}

// Close open dropdowns on an outside click or Escape.
document.addEventListener('click', event => {
  if (!event.target.isConnected) return; // the click re-rendered its own dropdown
  document.querySelectorAll('details.multiselect[open], details.account-menu[open]').forEach(box => { if (!box.contains(event.target)) box.open = false; });
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelectorAll('details.multiselect[open], details.account-menu[open]').forEach(box => { box.open = false; });
});

function categoryFilterControl() {
  if (section !== 'questions' || !data.categories.length) return '';
  const categories = subjectFilter ? inSubject(data.categories, subjectFilter) : data.categories;
  return `<div class="category-filter"><span class="filter-label">Categories</span>
    ${categoryDropdown('category_filter', categories, categoryFilter, 'All categories', !subjectFilter)}</div>`;
}

function subjectFilterControl() {
  if (section === 'subjects' || !data.subjects.length) return '';
  return `<label class="subject-filter">Subject<select id="subject-filter">
    <option value="">All subjects</option>${options(data.subjects, subjectFilter)}</select></label>`;
}

function shareExam(exam) {
  return `<details><summary>Share exam · link & QR code</summary>
    <p><a href="/exam/${exam.id}" target="_blank" rel="noopener">${esc(location.origin)}/exam/${exam.id}</a></p>
    <button type="button" class="qr-button" data-qr="${exam.id}" title="Show a larger QR code" aria-label="Show a larger QR code for ${esc(exam.title)}">
      <img class="qr" src="/api/exams/${exam.id}/qr" alt="Exam QR code"></button>
    <p><a href="/api/exams/${exam.id}/qr" download="exam-qr.svg">Download QR code</a></p></details>`;
}

// A large QR code in a modal dialog, for showing on a projector or screen.
function showQrDialog(exam) {
  let dialog = document.querySelector('#qr-dialog');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.id = 'qr-dialog';
    dialog.className = 'qr-dialog';
    document.body.append(dialog);
    // A click outside the content (on the backdrop) closes the dialog.
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  }
  const link = `${location.origin}/exam/${exam.id}`;
  dialog.setAttribute('aria-label', `QR code for ${exam.title}`);
  dialog.innerHTML = `<div class="qr-dialog-body">
    <h2>${esc(exam.title)}</h2>
    <img class="qr-large" src="/api/exams/${exam.id}/qr" alt="Exam QR code">
    <p><a href="${esc(link)}" target="_blank" rel="noopener">${esc(link)}</a></p>
    <div class="row qr-dialog-actions"><a class="button secondary" href="/api/exams/${exam.id}/qr" download="exam-qr.svg">Download QR code</a>
    <button type="button" id="qr-close">Close</button></div></div>`;
  dialog.querySelector('#qr-close').onclick = () => dialog.close();
  dialog.showModal();
}

function listView() {
  const {kind, path, label} = KINDS[section];
  let records = section !== 'subjects' && subjectFilter ? inSubject(data[section], subjectFilter) : data[section];
  if (section === 'questions' && categoryFilter.length) records = records.filter(q => categoryFilter.includes(q.category_id));
  document.querySelector('#content').innerHTML = `<div class="row between"><h2>${title(section)}</h2><button id="new">+ New ${kind}</button></div>
    <div class="row filters">${subjectFilterControl()}${categoryFilterControl()}</div>
    <div id="editor"></div>
    ${records.length ? records.map(record => `<article class="card"><div class="row between">
      <div><h2>${label(record)}</h2>${recordDetails(record)}</div>
      <div class="row"><button data-edit="${record.id}" class="secondary">Edit</button><button data-delete="${record.id}" class="danger">Delete</button></div>
      </div>${section === 'exams' ? shareExam(record) : ''}</article>`).join('')
      : '<div class="card" id="empty-state"><h2>A fresh start</h2><p>Create your first item to get started.</p></div>'}`;

  document.querySelector('#new').onclick = () => editor(kind, section !== 'subjects' && subjectFilter ? {subject_id: subjectFilter} : {});
  const filter = document.querySelector('#subject-filter');
  if (filter) filter.onchange = () => { subjectFilter = filter.value; categoryFilter = []; listView(); };
  const categoryBox = document.querySelector('[data-multiselect="category_filter"]');
  if (categoryBox) wireCategoryDropdown(categoryBox, ids => { categoryFilter = ids; listView(); document.querySelector('[data-multiselect="category_filter"]').open = true; });
  root.querySelectorAll('[data-qr]').forEach(button => button.onclick = () => showQrDialog(records.find(r => r.id === button.dataset.qr)));
  root.querySelectorAll('[data-edit]').forEach(button => button.onclick = () => editor(kind, records.find(r => r.id === button.dataset.edit)));
  root.querySelectorAll('[data-delete]').forEach(button => button.onclick = () => {
    if (confirm('Delete this item? Archived submissions will remain.')) {
      run(async () => { await api('DELETE', path + button.dataset.delete); await refresh(); });
    }
  });
}

function subjectFields(record) {
  return `${field('Subject name', 'name', record.name, 'text', 'required maxlength="100"')}
    <label>Description <small>(optional)</small><textarea name="description" maxlength="2000">${esc(record.description)}</textarea></label>`;
}

const subjectSelect = record =>
  `<label>Subject<select name="subject_id" required>${choose('Choose a subject', data.subjects, record.subject_id)}</select></label>`;

function categoryFields(record) {
  return `${subjectSelect(record)}
    <fieldset class="plain" data-needs-subject ${record.subject_id ? '' : 'disabled'}>
    ${field('Category name', 'name', record.name, 'text', 'required maxlength="100"')}</fieldset>`;
}

const categoryOptions = (subjectId, selected) =>
  choose(subjectId ? 'Choose a category' : 'Choose a subject first', inSubject(data.categories, subjectId), selected);

function questionFields(record) {
  const placed = Boolean(record.subject_id && record.category_id);
  return `${subjectSelect(record)}
    <label>Category<select name="category_id" required ${record.subject_id ? '' : 'disabled'}>${categoryOptions(record.subject_id, record.category_id)}</select></label>
    <p id="no-categories" ${record.subject_id && !inSubject(data.categories, record.subject_id).length ? '' : 'hidden'}><small>This subject has no categories yet. Create one under Categories first.</small></p>
    <fieldset class="plain" data-needs-category ${placed ? '' : 'disabled'}>
    <label>Question<textarea name="question_text" required maxlength="5000">${esc(record.question_text)}</textarea></label>
    <div class="math-preview" data-preview="question_text" aria-live="polite"></div>${MATH_HINT}
    ${field('Maximum points', 'points', record.points ?? 1, 'number', 'required min="0.01" max="100000" step="any"')}
    <fieldset><legend>Four answers · select the correct answer</legend>
    ${[0, 1, 2, 3].map(i => `<div class="row"><label><input type="radio" name="correct_answer" value="${i}" ${record.correct_answer === i ? 'checked' : ''} required>Correct ${i + 1}</label></div>
      ${field('Answer ' + (i + 1), 'answer' + i, record.answers?.[i] || '', 'text', 'required maxlength="2000"')}
      <div class="math-preview" data-preview="answer${i}" aria-live="polite"></div>`).join('')}</fieldset>
    <label>Optional image <small>(PNG, JPEG, GIF, WebP; up to 2 MB)</small><input id="image" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label>
    <img id="preview" class="question-image" ${imageData ? `src="${esc(imageData)}"` : 'hidden'} alt="Question image preview">
    <button type="button" id="clear-image" class="secondary">Remove image</button></fieldset>`;
}

function examSelection(subjectId, record) {
  const categories = inSubject(data.categories, subjectId);
  const questions = inSubject(data.questions, subjectId);
  if (!questions.length) return '<p><small>This subject has no questions yet.</small></p>';
  return `<div class="exam-categories"><span class="filter-label">Categories <small>(filter the questions below and choose the pool for random generation)</small></span>
    ${categoryDropdown('category_ids', categories, record.category_ids || [], 'All categories')}</div>
    <label><input name="random" type="checkbox" ${record.random_per_attempt ? 'checked' : ''}>Generate a random selection from the selected categories (replaces manual selection)</label>
    <label class="sub-option"><input name="per_attempt" type="checkbox" ${record.random_per_attempt ? 'checked' : ''}>Random for each attempt <small>– every student gets a different random set, drawn from the selected categories when they start</small></label>
    ${field('Number of random questions', 'count', record.random_count || 10, 'number', 'min="1" step="1"')}
    <p id="random-pool"><small></small></p>
    <fieldset class="plain" id="manual-selection">
    <p>Or select questions manually · <small id="manual-count"></small></p>
    <div id="exam-questions">
    ${questions.map(q => `<label data-category="${q.category_id}"><input type="checkbox" name="question_ids" value="${q.id}" ${record.question_ids?.includes(q.id) ? 'checked' : ''}>${math(q.question_text)} <small>(${esc(categoryName(q.category_id))} · ${points(q.points)})</small></label>`).join('')}
    </div></fieldset>`;
}

// Shows only the questions of the selected categories; hidden ticked questions stay selected.
function wireExamSelection(form) {
  const box = form.querySelector('[data-multiselect="category_ids"]');
  if (!box) return;
  const apply = ids => {
    const items = [...form.querySelectorAll('#exam-questions [data-category]')];
    items.forEach(item => item.hidden = ids.length > 0 && !ids.includes(item.dataset.category));
    const visible = items.filter(item => !item.hidden);
    const ticked = items.filter(item => item.querySelector('input').checked);
    const hiddenTicked = ticked.filter(item => item.hidden).length;
    form.querySelector('#manual-count').textContent = `${visible.length} shown · ${ticked.length} selected`
      + (hiddenTicked ? ` (${hiddenTicked} in categories not shown)` : '');
    form.querySelector('#random-pool small').textContent = ids.length
      ? `Random pool: ${visible.length} questions in ${ids.length} selected ${ids.length === 1 ? 'category' : 'categories'}.`
      : 'Select at least one category to generate a random selection.';
  };
  wireCategoryDropdown(box, apply);
  form.querySelectorAll('#exam-questions input').forEach(input => input.addEventListener('change', () =>
    apply([...box.querySelectorAll('input:checked')].map(b => b.value))));
  // "Random for each attempt" implies a random selection and makes the manual list irrelevant.
  const random = form.querySelector('[name="random"]');
  const perAttempt = form.querySelector('[name="per_attempt"]');
  const syncRandom = () => { form.querySelector('#manual-selection').disabled = perAttempt.checked; };
  random.addEventListener('change', () => { if (!random.checked) perAttempt.checked = false; syncRandom(); });
  perAttempt.addEventListener('change', () => { if (perAttempt.checked) random.checked = true; syncRandom(); });
  syncRandom();
  apply([...box.querySelectorAll('input:checked')].map(b => b.value));
}

function examFields(record) {
  const until = record.available_until || new Date(Date.now() + 86400000).toISOString();
  return `${subjectSelect(record)}
    <fieldset class="plain" data-needs-subject ${record.subject_id ? '' : 'disabled'}>
    ${field('Exam title', 'title', record.title, 'text', 'required maxlength="200"')}
    <div class="grid">${field('Available from (your local time)', 'available_from', localDate(record.available_from), 'datetime-local', 'required')}
    ${field('Available until (your local time)', 'available_until', localDate(until), 'datetime-local', 'required')}
    ${field('Points needed to pass (%)', 'pass_percentage', record.pass_percentage ?? 50, 'number', 'required min="0" max="100" step="any"')}</div>
    <fieldset><legend>Question selection · from the exam's subject</legend>
    <div id="selection">${record.subject_id ? examSelection(record.subject_id, record) : ''}</div>
    </fieldset></fieldset>`;
}

function readImage(event) {
  run(async () => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) throw new Error('Image must be at most 2 MB');
    imageData = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('Image could not be read'));
      reader.readAsDataURL(file);
    });
    const preview = document.querySelector('#preview');
    preview.src = imageData;
    preview.hidden = false;
  });
}

function formBody(kind, form) {
  if (kind === 'subject') return {name: form.get('name'), description: form.get('description')};
  if (kind === 'category') return {subject_id: form.get('subject_id'), name: form.get('name')};
  if (kind === 'question') {
    return {
      subject_id: form.get('subject_id'),
      category_id: form.get('category_id'),
      question_text: form.get('question_text'),
      answers: [0, 1, 2, 3].map(i => form.get('answer' + i)),
      correct_answer: Number(form.get('correct_answer')),
      points: Number(form.get('points')),
      image: imageData,
    };
  }
  return {
    subject_id: form.get('subject_id'),
    title: form.get('title'),
    available_from: new Date(form.get('available_from')).toISOString(),
    available_until: new Date(form.get('available_until')).toISOString(),
    pass_percentage: Number(form.get('pass_percentage')),
    question_ids: form.getAll('question_ids'),
    random: form.has('random')
      ? {category_ids: form.getAll('category_ids'), count: Number(form.get('count')), per_attempt: form.has('per_attempt')}
      : null,
  };
}

function needSubjectFirst(editorBox) {
  editorBox.innerHTML = `<div class="card"><h2>Create a subject first</h2>
    <p>Categories, questions and exams belong to a subject.</p>
    <div class="row"><button type="button" id="to-subjects">Go to subjects</button><button type="button" id="cancel" class="secondary">Cancel</button></div></div>`;
  document.querySelector('#to-subjects').onclick = () => { section = 'subjects'; render(); editor('subject', {}); };
  document.querySelector('#cancel').onclick = render;
}

function wireSubjectChoice(kind, record, form) {
  const subject = form.querySelector('[name="subject_id"]');
  const category = form.querySelector('[name="category_id"]');
  const update = () => {
    const chosen = subject.value;
    form.querySelectorAll('[data-needs-subject]').forEach(part => part.disabled = !chosen);
    if (kind === 'question') {
      category.disabled = !chosen;
      form.querySelector('#no-categories').hidden = !chosen || inSubject(data.categories, chosen).length > 0;
      form.querySelector('[data-needs-category]').disabled = !(chosen && category.value);
    }
  };
  subject.onchange = () => {
    if (kind === 'question') category.innerHTML = categoryOptions(subject.value, '');
    if (kind === 'exam') {
      form.querySelector('#selection').innerHTML = examSelection(subject.value, {});
      wireExamSelection(form);
    }
    update();
  };
  if (kind === 'exam') wireExamSelection(form);
  if (category) category.onchange = update;
  update();
}

function editor(kind, record) {
  const emptyState = document.querySelector('#empty-state');
  if (emptyState) emptyState.hidden = true;
  const editorBox = document.querySelector('#editor');
  if (kind !== 'subject' && !data.subjects.length) {
    needSubjectFirst(editorBox);
    return;
  }
  imageData = record.image || '';
  const fields = {subject: subjectFields, category: categoryFields, question: questionFields, exam: examFields}[kind](record);
  editorBox.innerHTML = `<form class="card" id="edit"><h2>${record.id ? 'Edit' : 'Create'} ${kind}</h2>${fields}
    <div class="row"><button>Save ${kind}</button><button type="button" id="cancel" class="secondary">Cancel</button></div></form>`;
  document.querySelector('#cancel').onclick = render;
  if (kind !== 'subject') wireSubjectChoice(kind, record, document.querySelector('#edit'));
  if (kind === 'question') {
    document.querySelector('#clear-image').onclick = () => {
      imageData = '';
      document.querySelector('#preview').hidden = true;
      document.querySelector('#image').value = '';
    };
    document.querySelector('#image').onchange = readImage;
    editorBox.querySelectorAll('[data-preview]').forEach(preview => {
      const input = editorBox.querySelector(`[name="${preview.dataset.preview}"]`);
      const update = () => QuickExamsMath.render(input.value, preview);
      input.addEventListener('input', update);
      update();
    });
  }
  document.querySelector('#edit').onsubmit = event => {
    event.preventDefault();
    const body = formBody(kind, new FormData(event.target));
    const path = KINDS[section].path;
    run(async () => {
      await (record.id ? api('PUT', path + record.id, body) : api('POST', path, body));
      await refresh();
    });
  };
  editorBox.scrollIntoView({behavior: 'smooth'});
}

function attemptDetails(attempt) {
  const {result} = attempt;
  return `<details><summary>${esc(attempt.student_email)} · ${pct(result.percentage)} · ${result.passed ? 'Pass' : 'Fail'} · ${when(attempt.submitted_at)}</summary>
    <p>${result.points} / ${result.maximum} points · Pass threshold: ${attempt.pass_percentage}%</p>
    ${attempt.questions.map(q => `<fieldset><legend>${points(q.points)}</legend>${answerOutcome(q)}<p>${math(q.question_text)}</p>
      ${q.image ? `<img class="question-image" src="${esc(q.image)}" alt="Question image">` : ''}
      ${q.answers.map((answer, i) => reviewedAnswer(q, i, answer)).join('')}
      </fieldset>`).join('')}</details>`;
}

// Archived answer outcome: shown at the top of each reviewed question.
function answerOutcome(q) {
  if (q.selected_answer === null || q.selected_answer === undefined) {
    return '<span class="outcome unanswered">Not answered</span>';
  }
  return q.selected_answer === q.correct_answer
    ? `<span class="outcome correct">${mark('correct')} Correct answer</span>`
    : `<span class="outcome wrong">${mark('wrong')} Incorrect answer</span>`;
}

// A green check marks the correct answer, a red cross a wrong selection.
function mark(kind) {
  const label = kind === 'correct' ? 'Correct' : 'Selected, incorrect';
  return `<span class="mark ${kind}" role="img" aria-label="${label}" title="${label}">${kind === 'correct' ? '✓' : '✕'}</span>`;
}

function reviewedAnswer(q, i, answer) {
  const selected = i === q.selected_answer;
  const correct = i === q.correct_answer;
  const marker = correct ? mark('correct') : selected ? mark('wrong') : '<span class="mark none"></span>';
  const classes = ['reviewed-answer', selected ? 'selected' : '', selected && !correct ? 'wrong' : '', correct ? 'correct' : '']
    .filter(Boolean).join(' ');
  const note = selected ? '<span class="visually-hidden"> (selected)</span>' : '';
  return `<p class="${classes}">${marker}<span>${math(answer)}${note}</span></p>`;
}

function reportsView(reports, target = '#content') {
  document.querySelector(target).innerHTML = `<h2>Report archive</h2>
    <p>Each submission preserves the exam as the student received it, even after its source is deleted.</p>
    ${reports.length ? reports.map(report => `<article class="card"><h2>${esc(report.exam_title)}</h2>
      <div class="grid"><div><div class="metric">${report.count}</div>Submissions</div>
      <div><div class="metric">${pct(report.pass_rate)}</div>Pass rate</div>
      <div><div class="metric">${pct(report.average)}</div>Average score</div></div>
      <p>Score range: ${pct(report.lowest)} – ${pct(report.highest)}</p>
      <button class="secondary" data-export="${report.exam_id}">Download complete report (JSON)</button>
      ${report.attempts.map(attemptDetails).join('')}</article>`).join('')
      : '<div class="card">No submissions yet.</div>'}`;
  document.querySelectorAll('[data-export]').forEach(button => button.onclick = () => {
    const report = reports.find(r => r.exam_id === button.dataset.export);
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'exam-report.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

function userEditor(existing = {}) {
  document.querySelector('#user-editor').innerHTML = `<form id="user-form">
    ${field('Email', 'email', existing.email, 'email', 'required')}
    ${field(existing.id ? 'New password (leave blank to keep)' : 'Password (12+ characters)', 'password', '', 'password',
      (existing.id ? '' : 'required ') + 'minlength="12" autocomplete="new-password"')}
    ${['INSTRUCTOR', 'ADMIN'].map(role => `<label><input name="roles" type="checkbox" value="${role}" ${existing.roles?.includes(role) ? 'checked' : ''}>${role}</label>`).join('')}
    <button>Save user</button></form>`;
  document.querySelector('#user-form').onsubmit = event => {
    event.preventDefault();
    const form = new FormData(event.target);
    const body = {email: form.get('email'), password: form.get('password'), roles: form.getAll('roles')};
    run(async () => {
      await (existing.id ? api('PUT', `/api/admin/users/${existing.id}`, body) : api('POST', '/api/admin/users', body));
      await adminView();
    });
  };
}

async function adminView() {
  const overview = await api('GET', '/api/admin/overview');
  const {counts, users} = overview;
  document.querySelector('#content').innerHTML = `<h2>Administration</h2>
    <p>${counts.questions} questions · ${counts.exams} exams · ${counts.attempts} attempts</p>
    <div class="card"><h2>User access</h2><p>Assign either or both roles. Clear both roles to disable staff access.</p>
    <div class="scroll"><table><thead><tr><th>Email</th><th>Roles</th><th></th></tr></thead><tbody>
    ${users.map(u => `<tr><td>${esc(u.email)}</td><td>${esc(u.roles.join(', '))}</td><td><button data-user="${u.id}" class="secondary">Edit</button></td></tr>`).join('')}
    </tbody></table></div><button id="add-user">Add user</button><div id="user-editor"></div></div><div id="admin-reports"></div>`;
  document.querySelector('#add-user').onclick = () => userEditor();
  root.querySelectorAll('[data-user]').forEach(button => button.onclick = () => userEditor(users.find(u => u.id === button.dataset.user)));
  reportsView(overview.reports, '#admin-reports');
}

function studentStart(examId) {
  root.innerHTML = `<section class="card narrow"><p>QUICK EXAM</p><h1>Let’s get started.</h1>
    <p>Enter your email to begin. Your score is shown only to you and authorized staff. You must submit before the exam closes.</p>
    <form id="start">${field('Your email', 'email', '', 'email', 'required autocomplete="email"')}<button>Start exam</button></form></section>`;
  document.querySelector('#start').onsubmit = event => {
    event.preventDefault();
    const email = new FormData(event.target).get('email');
    run(async () => studentQuestions(await api('POST', '/api/attempts/', {exam_id: examId, email})));
  };
}

function studentQuestions(attempt) {
  root.innerHTML = `<h1>${esc(attempt.exam_title)}</h1><p>Closes ${when(attempt.available_until)}. Select one answer for every question.</p>
    <form id="answers">${attempt.questions.map((q, i) => `<fieldset class="card"><legend>Question ${i + 1} · ${points(q.points)}</legend><p>${math(q.question_text)}</p>
      ${q.image ? `<img class="question-image" src="${esc(q.image)}" alt="Question image">` : ''}
      ${q.answers.map((answer, n) => `<label class="answer"><input type="radio" name="${q.id}" value="${n}" required>${math(answer)}</label>`).join('')}
      </fieldset>`).join('')}<button id="submit">Submit exam</button></form>`;
  document.querySelector('#answers').onsubmit = event => {
    event.preventDefault();
    const answers = Object.fromEntries([...new FormData(event.target)].map(([key, value]) => [key, Number(value)]));
    const button = document.querySelector('#submit');
    run(async () => {
      button.disabled = true;
      try {
        const result = await api('POST', `/api/attempts/${attempt.id}/submit`, {answers});
        root.innerHTML = `<section class="card narrow"><p>YOUR RESULT</p><h1>${result.passed ? 'You passed.' : 'Not passed this time.'}</h1>
          <div class="metric">${pct(result.percentage)}</div><p>${result.points} of ${result.maximum} points</p>
          <p>Your submission has been saved. You can close this page.</p></section>`;
      } finally {
        button.disabled = false;
      }
    });
  };
}

QuickExamsMath.observe(root);

const examId = location.pathname.match(/^\/exam\/([^/]+)$/)?.[1];
if (examId) {
  studentStart(examId);
} else {
  refresh().catch(error => {
    showLogin();
    if (error.status !== 401) notice(error.message);
  });
}
