const root = document.querySelector('#app');
const identity = document.querySelector('#identity');
const accountActions = document.querySelector('#account-actions');
const TAGLINE = 'A little preparation. A clear result.';

let user = null;
let data = {subjects: [], categories: [], questions: [], exams: []};
let subjectFilter = '';
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
  identity.textContent = TAGLINE;
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
  }
  render();
}

function render() {
  identity.textContent = user.email;
  accountActions.innerHTML = `${isAdmin() ? '<a class="header-admin" href="/admin/en/dashboard">Admin</a>' : ''}<button id="logout" class="header-logout">Sign out</button>`;
  document.querySelector('#logout').onclick = () => run(logout);

  const tabs = isInstructor() ? ['exams', 'questions', 'categories', 'subjects', 'reports'] : [];
  root.innerHTML = `<h1>Your exam workspace</h1><p>Build a question bank. Share an exam. See how everyone did.</p>
    <nav>${tabs.map(tab => `<button class="${tab === section ? '' : 'secondary'}" data-tab="${tab}">${title(tab)}</button>`).join('')}
    ${isAdmin() ? `<button data-tab="admin" class="${section === 'admin' ? '' : 'secondary'}">Users &amp; reports</button>` : ''}</nav>
    <div id="content"></div>`;
  root.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => { section = button.dataset.tab; run(refresh); });

  if (section === 'admin' || !isInstructor()) {
    if (isAdmin()) run(adminView);
    else document.querySelector('#content').textContent = 'No roles assigned. Contact an administrator.';
    return;
  }
  if (section === 'reports') { run(async () => reportsView(await api('GET', '/api/reports/'))); return; }
  listView();
}

const KINDS = {
  exams: {kind: 'exam', path: '/api/exams/', label: exam => esc(exam.title)},
  questions: {kind: 'question', path: '/api/questions/', label: question => math(question.question_text)},
  categories: {kind: 'category', path: '/api/categories/', label: category => esc(category.name)},
  subjects: {kind: 'subject', path: '/api/subjects/', label: subject => esc(subject.name)},
};

function recordDetails(record) {
  if (section === 'exams') {
    return `<p>${esc(subjectName(record.subject_id))} · ${plural(record.question_ids.length, 'question')} · Pass: ${record.pass_percentage}%</p>
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

function subjectFilterControl() {
  if (section === 'subjects' || !data.subjects.length) return '';
  return `<label class="subject-filter">Subject<select id="subject-filter">
    <option value="">All subjects</option>${options(data.subjects, subjectFilter)}</select></label>`;
}

function shareExam(exam) {
  return `<details><summary>Share exam · link & QR code</summary>
    <p><a href="/exam/${exam.id}" target="_blank" rel="noopener">${esc(location.origin)}/exam/${exam.id}</a></p>
    <img class="qr" src="/api/exams/${exam.id}/qr" alt="Exam QR code">
    <p><a href="/api/exams/${exam.id}/qr" download="exam-qr.svg">Download QR code</a></p></details>`;
}

function listView() {
  const {kind, path, label} = KINDS[section];
  const records = section !== 'subjects' && subjectFilter ? inSubject(data[section], subjectFilter) : data[section];
  document.querySelector('#content').innerHTML = `<div class="row between"><h2>${title(section)}</h2><button id="new">+ New ${kind}</button></div>
    ${subjectFilterControl()}
    <div id="editor"></div>
    ${records.length ? records.map(record => `<article class="card"><div class="row between">
      <div><h2>${label(record)}</h2>${recordDetails(record)}</div>
      <div class="row"><button data-edit="${record.id}" class="secondary">Edit</button><button data-delete="${record.id}" class="danger">Delete</button></div>
      </div>${section === 'exams' ? shareExam(record) : ''}</article>`).join('')
      : '<div class="card" id="empty-state"><h2>A fresh start</h2><p>Create your first item to get started.</p></div>'}`;

  document.querySelector('#new').onclick = () => editor(kind, section !== 'subjects' && subjectFilter ? {subject_id: subjectFilter} : {});
  const filter = document.querySelector('#subject-filter');
  if (filter) filter.onchange = () => { subjectFilter = filter.value; listView(); };
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
  return `<label><input name="random" type="checkbox">Generate a random selection from categories (replaces manual selection)</label>
    ${field('Number of random questions', 'count', 10, 'number', 'min="1" step="1"')}
    <p>Categories for random generation</p>
    ${categories.map(c => `<label><input type="checkbox" name="category_ids" value="${c.id}">${esc(c.name)}</label>`).join('')}
    <p>Or select questions manually</p>
    ${questions.map(q => `<label><input type="checkbox" name="question_ids" value="${q.id}" ${record.question_ids?.includes(q.id) ? 'checked' : ''}>${math(q.question_text)} <small>(${esc(categoryName(q.category_id))} · ${points(q.points)})</small></label>`).join('')}`;
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
    random: form.has('random') ? {category_ids: form.getAll('category_ids'), count: Number(form.get('count'))} : null,
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
    if (kind === 'exam') form.querySelector('#selection').innerHTML = examSelection(subject.value, {});
    update();
  };
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
    ${attempt.questions.map(q => `<fieldset><legend>${points(q.points)}</legend><p>${math(q.question_text)}</p>
      ${q.image ? `<img class="question-image" src="${esc(q.image)}" alt="Question image">` : ''}
      ${q.answers.map((answer, i) => `<p>${i === q.selected_answer ? 'Selected · ' : ''}${i === q.correct_answer ? 'Correct · ' : ''}${math(answer)}</p>`).join('')}
      </fieldset>`).join('')}</details>`;
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
