// Talks to the GlassBox Autofill browser extension (extension/ in this repo)
// through window messages; its content script on this site relays them.
import { useEffect, useState } from 'react';

const listeners = new Set();
let state = { ready: false, version: null, submitted: [] };

if (typeof window !== 'undefined') {
  window.addEventListener('message', (e) => {
    if (e.source !== window || e.data?.source !== 'glassbox-extension') return;
    if (e.data.type === 'ready') {
      state = { ready: true, version: e.data.version, submitted: e.data.submitted || [] };
      listeners.forEach(fn => fn(state));
    }
  });
  window.postMessage({ source: 'glassbox-app', type: 'ping' }, window.location.origin);
}

export function useExtension() {
  const [s, setS] = useState(state);
  useEffect(() => {
    listeners.add(setS);
    window.postMessage({ source: 'glassbox-app', type: 'ping' }, window.location.origin);
    return () => listeners.delete(setS);
  }, []);
  return s;
}

// Hands an approved application to the extension; resolves once it's stored.
export function queueApplication(pkg) {
  return new Promise((resolve, reject) => {
    const done = (e) => {
      if (e.source !== window || e.data?.source !== 'glassbox-extension' || e.data.type !== 'queued' || e.data.key !== pkg.key) return;
      window.removeEventListener('message', done);
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      window.removeEventListener('message', done);
      reject(new Error('The GlassBox Autofill extension did not respond.'));
    }, 4000);
    window.addEventListener('message', done);
    window.postMessage({ source: 'glassbox-app', type: 'queue', pkg }, window.location.origin);
  });
}
