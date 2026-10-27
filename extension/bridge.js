// Runs on the GlassBox site. Receives the application the user approved and
// keeps it for the job's form page; reports back which forms were submitted.
// Only messages from this same window are accepted.

const KEEP_DAYS = 14;

function reply(type, payload) {
  window.postMessage({ source: 'glassbox-extension', type, ...payload }, window.location.origin);
}

async function submittedList() {
  const { packages = {} } = await chrome.storage.local.get('packages');
  return Object.values(packages)
    .filter(p => p.submitted_at)
    .map(p => ({ id: p.job_id, submitted_at: p.submitted_at }));
}

window.addEventListener('message', async (event) => {
  if (event.source !== window || event.data?.source !== 'glassbox-app') return;
  const msg = event.data;
  if (msg.type === 'ping') {
    reply('ready', { version: chrome.runtime.getManifest().version, submitted: await submittedList() });
  }
  if (msg.type === 'queue' && msg.pkg?.key) {
    const { packages = {} } = await chrome.storage.local.get('packages');
    const cutoff = Date.now() - KEEP_DAYS * 864e5;
    for (const [k, p] of Object.entries(packages)) if (p.created < cutoff) delete packages[k];
    packages[msg.pkg.key] = { ...msg.pkg, created: Date.now(), submitted_at: null };
    await chrome.storage.local.set({ packages });
    reply('queued', { key: msg.pkg.key });
  }
});

// Announce on load, so the app can show "Autofill ready" without asking.
submittedList().then(submitted => reply('ready', { version: chrome.runtime.getManifest().version, submitted }));
