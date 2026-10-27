// Runs on Greenhouse, Lever and Ashby application pages. If the user approved
// an application for this job in GlassBox, it fills the form with those
// answers, attaches the tailored resume, and shows what still needs the user.
// It never submits by itself: the Submit button in the panel presses the
// form's own Submit, so the user sends it after seeing the filled form.

(async () => {
  const { packages = {} } = await chrome.storage.local.get('packages');
  const pkg = Object.values(packages)
    .filter(p => p.native_id && location.href.includes(p.native_id))
    .sort((a, b) => b.created - a.created)[0];
  if (!pkg) return;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const DONE = /thank you for (applying|your application)|application (has been )?(submitted|received)|we('ve| have) received your application/i;
  async function markSubmitted() {
    const { packages: all = {} } = await chrome.storage.local.get('packages');
    if (all[pkg.key] && !all[pkg.key].submitted_at) {
      all[pkg.key].submitted_at = Date.now();
      await chrome.storage.local.set({ packages: all });
    }
  }
  // A confirmation page after a full page load.
  await sleep(800);
  if (/confirmation/i.test(location.pathname) || DONE.test(document.body?.innerText.slice(0, 20000) || '')) {
    if (!document.querySelector('form input[type=file]')) {
      await markSubmitted();
      return;
    }
  }
  const norm = (s) => (s || '').toLowerCase().replace(/[*✱]/g, '').replace(/\s+/g, ' ').trim();

  async function waitForForm() {
    for (let i = 0; i < 40; i++) {
      if (document.querySelector('form input, form textarea')) return true;
      await sleep(250);
    }
    return false;
  }
  if (!(await waitForForm())) return;

  // React and other frameworks track input values themselves; the prototype
  // setter plus input/change events is what makes them see a typed value.
  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    if (el.getAttribute('role') === 'combobox') return;  // a change/blur would close its menu
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  }

  function attach(el, file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  const pdfFile = () => new File([Uint8Array.from(atob(pkg.resume.b64), c => c.charCodeAt(0))], pkg.resume.name, { type: 'application/pdf' });
  const coverFile = () => new File([pkg.cover_letter || ''], 'Cover_letter.txt', { type: 'text/plain' });

  // A whole press (pointer + mouse + click): dropdowns open on whichever of
  // these their library listens to.
  function press(target) {
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      const Ev = type.startsWith('pointer') ? PointerEvent : MouseEvent;
      target.dispatchEvent(new Ev(type, { bubbles: true, cancelable: true, button: 0 }));
    }
  }

  // Typeahead dropdowns (Greenhouse's react-select, Ashby's comboboxes): open
  // with the toggle, pick the option whose text matches; type to narrow long
  // lists (countries) only when the option isn't already showing.
  async function chooseCombo(el, wanted) {
    const want = norm(wanted);
    const options = () => {
      const list = document.getElementById(el.getAttribute('aria-controls') || '');
      return list ? [...list.querySelectorAll('[role="option"]')] : [];
    };
    const pick = () => {
      const o = options();
      return o.find(x => norm(x.textContent) === want) || o.find(x => norm(x.textContent).startsWith(want));
    };
    if (el.getAttribute('aria-expanded') !== 'true') {
      const control = el.closest('[class*="control"]') || el.parentElement;
      press(control.querySelector('button') || control);
      await sleep(200);
    }
    let hit = pick();
    if (!hit) {
      setValue(el, wanted);
      for (let i = 0; i < 10 && !hit; i++) {
        await sleep(120);
        hit = pick();
      }
    }
    if (!hit) {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return false;
    }
    press(hit);
    await sleep(150);
    return true;
  }

  function chooseNative(el, wanted) {
    const want = norm(wanted);
    const opt = [...el.options].find(o => norm(o.textContent) === want || norm(o.value) === want)
      || [...el.options].find(o => norm(o.textContent).startsWith(want));
    if (!opt) return false;
    el.value = opt.value;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  function chooseChoice(inputs, values) {
    const wanted = (Array.isArray(values) ? values : [values]).map(norm);
    let any = false;
    for (const inp of inputs) {
      const text = norm(inp.closest('label')?.textContent || document.querySelector(`label[for="${CSS.escape(inp.id)}"]`)?.textContent || inp.value);
      if (wanted.includes(text) && !inp.checked) {
        inp.click();
        any = true;
      }
    }
    return any;
  }

  // The form's own field for a question: by id or name first (Greenhouse and
  // Ashby use the API's field names), then by its visible label (Lever cards).
  function findField(f) {
    const byId = document.getElementById(f.id) || document.querySelector(`[name="${CSS.escape(f.id)}"]`);
    if (byId) return byId;
    const want = norm(f.label);
    if (!want) return null;
    const labels = [...document.querySelectorAll('label, legend, .application-label, .text, [class*="label"]')]
      .filter(l => norm(l.textContent) === want || (want.length > 12 && norm(l.textContent).startsWith(want)));
    for (const l of labels) {
      if (l.htmlFor && document.getElementById(l.htmlFor)) return document.getElementById(l.htmlFor);
      const box = l.closest('li, fieldset, .field, .application-question, [class*="field"], div');
      const el = box?.querySelector('input:not([type=hidden]), textarea, select');
      if (el) return el;
    }
    return null;
  }

  async function fillOne(f) {
    const v = f.value;
    const el = findField(f);
    if (!el) return 'missing';
    if (f.type === 'file') {
      const input = el.type === 'file' ? el : el.closest('div')?.querySelector('input[type=file]');
      if (!input) return 'missing';
      if (v === 'cover_letter' && !pkg.cover_letter) return 'empty';
      attach(input, v === 'cover_letter' ? coverFile() : pdfFile());
      return 'filled';
    }
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) return 'empty';
    if (el.type === 'radio' || el.type === 'checkbox') {
      const group = el.name ? [...document.querySelectorAll(`[name="${CSS.escape(el.name)}"]`)] : [el];
      return chooseChoice(group, v) ? 'filled' : 'unmatched';
    }
    if (el.tagName === 'SELECT') return chooseNative(el, Array.isArray(v) ? v[0] : v) ? 'filled' : 'unmatched';
    if (el.getAttribute('role') === 'combobox') {
      let ok = true;
      for (const one of Array.isArray(v) ? v : [v]) ok = (await chooseCombo(el, String(one))) && ok;
      return ok ? 'filled' : 'unmatched';
    }
    setValue(el, Array.isArray(v) ? v.join(', ') : String(v));
    return 'filled';
  }

  // Greenhouse's employment block and country picker aren't in its API, so
  // they're filled from the resume's most recent role and the phone's country.
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  function monthYear(s) {
    const m = String(s || '').match(/([A-Za-z]{3,})\.?\s*[-'’]?\s*(\d{4})/);
    if (!m) return null;
    const i = MONTHS.findIndex(x => x.toLowerCase().startsWith(m[1].slice(0, 3).toLowerCase()));
    return i < 0 ? null : { month: MONTHS[i], year: m[2] };
  }
  async function fillExtras(results) {
    const country = document.getElementById('country');
    if (country && country.getAttribute('role') === 'combobox' && pkg.country) {
      results.push({ label: 'Country', status: (await chooseCombo(country, pkg.country)) ? 'filled' : 'unmatched', el: country });
    }
    const job = (pkg.employment || [])[0];
    const company = document.getElementById('company-name-0');
    if (!job || !company) return;
    setValue(company, job.company || '');
    const title = document.getElementById('title-0');
    if (title) setValue(title, job.title || '');
    const start = monthYear(job.start);
    const current = /present|current|now/i.test(job.end || '');
    const end = current ? null : monthYear(job.end);
    if (start) {
      await chooseCombo(document.getElementById('start-date-month-0'), start.month);
      setValue(document.getElementById('start-date-year-0'), start.year);
    }
    if (current) {
      const box = document.querySelector('[name="current-role-0"]');
      if (box && !box.checked) box.click();
    } else if (end) {
      await chooseCombo(document.getElementById('end-date-month-0'), end.month);
      setValue(document.getElementById('end-date-year-0'), end.year);
    }
    results.push({ label: `Employment: ${job.title} at ${job.company}`, status: start ? 'filled' : 'empty', el: company });
  }

  // ---- Panel -------------------------------------------------------------
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:2147483647;';
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      .p{font:14px/1.45 system-ui,-apple-system,sans-serif;width:330px;max-height:70vh;display:flex;flex-direction:column;
         background:#f9f5ec;color:#2b2620;border:1px solid #c9bb9f;border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.22);overflow:hidden}
      .h{padding:12px 14px;border-bottom:1px solid #dbd0ba;display:flex;gap:8px;align-items:center}
      .h b{flex:1;font-size:14px}.x{border:0;background:none;font-size:18px;cursor:pointer;color:#6d6457}
      .s{padding:10px 14px;overflow:auto;flex:1}.row{display:flex;gap:8px;padding:4px 0;cursor:pointer}
      .ok{color:#3d7a4f}.no{color:#b5651d}.lab{flex:1}.sub{color:#6d6457;font-size:12px;margin:2px 0 8px}
      .f{padding:12px 14px;border-top:1px solid #dbd0ba;display:flex;gap:8px}
      button.b{flex:1;padding:9px 10px;border-radius:999px;border:1px solid #c9bb9f;background:#efe8da;cursor:pointer;font:600 13px system-ui}
      button.pr{background:#2b2620;color:#f9f5ec;border-color:#2b2620}button:disabled{opacity:.45;cursor:not-allowed}
    </style>
    <div class="p">
      <div class="h"><b>GlassBox · ${pkg.title ? pkg.title.replace(/</g, '&lt;') : 'Application'}</b><button class="x" title="Hide">×</button></div>
      <div class="s"><div class="sub">Filling the form with the answers you approved…</div><div class="list"></div></div>
      <div class="f"><button class="b refill">Fill again</button><button class="b pr submit" disabled>Submit application</button></div>
    </div>`;
  document.documentElement.appendChild(host);
  root.querySelector('.x').onclick = () => host.remove();

  async function run() {
    const results = [];
    for (const f of pkg.fields) {
      const status = await fillOne(f);
      results.push({ label: f.label, required: f.required, status, el: findField(f) });
    }
    await fillExtras(results);
    const blocking = results.filter(r => r.required && r.status !== 'filled');
    const done = results.filter(r => r.status === 'filled').length;
    root.querySelector('.sub').textContent = blocking.length
      ? `Filled ${done} of ${results.length}. ${blocking.length} required ${blocking.length > 1 ? 'fields need' : 'field needs'} you (in orange): fill ${blocking.length > 1 ? 'them' : 'it'} on the page, then submit.`
      : `Filled ${done} of ${results.length}. Look over the form, then submit.`;
    const list = root.querySelector('.list');
    list.innerHTML = '';
    for (const r of results) {
      const row = document.createElement('div');
      row.className = 'row';
      const ok = r.status === 'filled';
      row.innerHTML = `<span class="${ok ? 'ok' : 'no'}">${ok ? '✓' : '!'}</span><span class="lab"></span>`;
      row.querySelector('.lab').textContent = r.label + (ok ? '' : r.required ? ' (required)' : '');
      row.onclick = () => r.el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      list.appendChild(row);
    }
    root.querySelector('.submit').disabled = false;
  }

  root.querySelector('.refill').onclick = run;
  root.querySelector('.submit').onclick = async () => {
    const btn = [...document.querySelectorAll('form button[type=submit], form input[type=submit], button[type=submit]')]
      .find(b => /submit|apply|send/i.test(b.textContent || b.value || ''));
    if (!btn) {
      root.querySelector('.sub').textContent = "Couldn't find this form's Submit button. Press it on the page yourself.";
      return;
    }
    btn.scrollIntoView({ block: 'center' });
    btn.click();
    root.querySelector('.sub').textContent = 'Submitting… If the page shows errors or a CAPTCHA, finish those and press Submit there.';
    watchForConfirmation();
  };

  let watching = false;
  // Also when the user presses the page's own Submit.
  document.addEventListener('submit', () => watchForConfirmation(), true);

  // Counted as applied only once the ATS shows its confirmation page.
  async function watchForConfirmation() {
    if (watching) return;
    watching = true;
    for (let i = 0; i < 240; i++) {
      await sleep(500);
      if (/confirmation|thank/i.test(location.pathname) || DONE.test(document.body.innerText.slice(0, 20000))) {
        await markSubmitted();
        root.querySelector('.sub').textContent = 'Application submitted. GlassBox marks it as applied next time you open it.';
        root.querySelector('.submit').disabled = true;
        return;
      }
    }
    watching = false;
  }

  run();
})();
