import { firebaseConfig } from './firebase-config.js';

(() => {
  'use strict';

  const SDK_VERSION = '13.4.0';
  const OWNER_KEY = 'forma-firebase-owner-v1';
  const DEFAULT_SETTINGS = {
    name: 'Athlete',
    height: '',
    sound: false,
    membershipStartDate: '',
    membershipEndDate: ''
  };

  let firebaseAuth = null;
  let firestore = null;
  let currentUser = null;
  let stopItemsListener = null;
  let bootstrapped = false;
  let bootstrapping = false;
  let pendingLocalChange = false;
  let applyingRemote = false;
  let lastSyncedState = null;
  let saveTimer = null;
  let saveChain = Promise.resolve();
  let firebaseReady = false;
  let statusLabel = 'Setup required';
  let statusMessage = 'Cloud sync is ready in the code, but this Firebase project still needs its web configuration. Follow CLOUD_SETUP.md.';
  let statusTone = 'warning';

  const bridge = () => window.FORMACloudBridge || null;
  const clone = value => JSON.parse(JSON.stringify(value));
  const stableStringify = value => {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}';
  };
  const isSame = (left, right) => stableStringify(left) === stableStringify(right);
  const validRecord = item => item && typeof item === 'object' && !Array.isArray(item) && item.id != null && String(item.id) !== '';
  const safeKey = value => encodeURIComponent(String(value)).replaceAll('.', '%2E');

  function setStatus(label, message, tone) {
    statusLabel = label;
    statusMessage = message;
    statusTone = tone || '';
    const pill = document.getElementById('cloud-sync-status-pill');
    const copy = document.getElementById('cloud-sync-status');
    const top = document.getElementById('cloud-top-status');
    if (pill) {
      pill.textContent = label;
      pill.classList.toggle('cloud-status-online', tone === 'online');
      pill.classList.toggle('cloud-status-warning', tone === 'warning');
    }
    if (copy) copy.textContent = message;
    if (top) top.textContent = '☁ ' + label;
  }

  function refreshControls() {
    const pill = document.getElementById('cloud-sync-status-pill');
    const copy = document.getElementById('cloud-sync-status');
    const top = document.getElementById('cloud-top-status');
    if (pill) {
      pill.textContent = statusLabel;
      pill.classList.toggle('cloud-status-online', statusTone === 'online');
      pill.classList.toggle('cloud-status-warning', statusTone === 'warning');
    }
    if (copy) copy.textContent = statusMessage;
    if (top) top.textContent = '☁ ' + statusLabel;
    const signIn = document.getElementById('cloud-auth-button');
    const signOut = document.getElementById('cloud-signout-button');
    const account = document.getElementById('cloud-account-info');
    const hint = document.getElementById('cloud-setup-hint');
    if (signIn) {
      signIn.hidden = Boolean(currentUser);
      signIn.disabled = !firebaseReady;
      signIn.textContent = firebaseReady ? 'Continue with Google' : 'Firebase setup required';
    }
    if (signOut) signOut.hidden = !currentUser;
    if (account) {
      account.hidden = !currentUser;
      account.textContent = currentUser ? 'Signed in as ' + (currentUser.email || currentUser.displayName || 'Google account') : '';
    }
    if (hint) hint.hidden = firebaseReady;
  }

  function notify(message) {
    const api = bridge();
    if (api && typeof api.notify === 'function') api.notify(message);
  }

  function isConfigured(config) {
    const required = ['apiKey', 'authDomain', 'projectId', 'appId'];
    return required.every(key => typeof config[key] === 'string' &&
      config[key].trim() !== '' &&
      !/YOUR_|REPLACE_|PASTE_/i.test(config[key]));
  }

  function stateToEntries(state) {
    const entries = new Map();
    const add = (id, type, payload) => {
      if (payload !== undefined && payload !== null) {
        entries.set(id, { type, payload: clone(payload) });
      }
    };

    (Array.isArray(state.sessions) ? state.sessions : []).forEach(item => {
      if (validRecord(item)) add('session_' + safeKey(item.id), 'session', item);
    });
    (Array.isArray(state.exercises) ? state.exercises : []).forEach(item => {
      if (validRecord(item)) add('exercise_' + safeKey(item.id), 'exercise', item);
    });
    (Array.isArray(state.routines) ? state.routines : []).forEach(item => {
      if (validRecord(item)) add('routine_' + safeKey(item.id), 'routine', item);
    });
    (Array.isArray(state.bodyWeightHistory) ? state.bodyWeightHistory : []).forEach(item => {
      if (item && typeof item.date === 'string' && item.date) {
        add('weight_' + safeKey(item.date), 'weight', item);
      }
    });

    add('settings', 'settings', state.settings || DEFAULT_SETTINGS);
    if (state.draft && typeof state.draft === 'object') add('draft', 'draft', state.draft);
    return entries;
  }

  function stateFromSnapshot(snapshot) {
    const state = {
      sessions: [],
      exercises: [],
      routines: [],
      bodyWeightHistory: [],
      settings: null,
      draft: null
    };
    snapshot.forEach(documentSnapshot => {
      const record = documentSnapshot.data();
      if (!record || !record.payload) return;
      if (record.type === 'session') state.sessions.push(record.payload);
      else if (record.type === 'exercise') state.exercises.push(record.payload);
      else if (record.type === 'routine') state.routines.push(record.payload);
      else if (record.type === 'weight') state.bodyWeightHistory.push(record.payload);
      else if (record.type === 'settings') state.settings = record.payload;
      else if (record.type === 'draft') state.draft = record.payload;
    });
    return state;
  }

  function recordTime(item) {
    if (!item || typeof item !== 'object') return 0;
    const value = item.updatedAt || item.createdAt || item.recordedAt || '';
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : 0;
  }

  function mergeLists(localItems, remoteItems) {
    const merged = new Map();
    (Array.isArray(remoteItems) ? remoteItems : []).forEach(item => {
      if (validRecord(item)) merged.set(String(item.id), item);
    });
    (Array.isArray(localItems) ? localItems : []).forEach(item => {
      if (!validRecord(item)) return;
      const id = String(item.id);
      const remote = merged.get(id);
      if (!remote || recordTime(item) > recordTime(remote)) merged.set(id, item);
    });
    return Array.from(merged.values());
  }

  function mergeInitialState(local, remote) {
    return {
      sessions: mergeLists(local.sessions, remote.sessions),
      exercises: mergeLists(local.exercises, remote.exercises),
      routines: mergeLists(local.routines, remote.routines),
      bodyWeightHistory: mergeLists(
        (local.bodyWeightHistory || []).map(item => ({ ...item, id: item.date })),
        (remote.bodyWeightHistory || []).map(item => ({ ...item, id: item.date }))
      ).map(({ id, ...item }) => item),
      settings: remote.settings ? { ...DEFAULT_SETTINGS, ...remote.settings } : { ...DEFAULT_SETTINGS, ...(local.settings || {}) },
      draft: remote.draft || local.draft || null
    };
  }

  function mergeRemoteWithLocalEdits(remote, local, base) {
    const remoteEntries = stateToEntries(remote);
    const localEntries = stateToEntries(local);
    const baseEntries = stateToEntries(base || {});

    const allKeys = new Set([...baseEntries.keys(), ...localEntries.keys()]);
    allKeys.forEach(key => {
      const before = baseEntries.get(key);
      const now = localEntries.get(key);
      if (isSame(before || null, now || null)) return;
      if (now) remoteEntries.set(key, now);
      else remoteEntries.delete(key);
    });

    const merged = {
      sessions: [],
      exercises: [],
      routines: [],
      bodyWeightHistory: [],
      settings: { ...DEFAULT_SETTINGS },
      draft: null
    };
    remoteEntries.forEach(entry => {
      const payload = clone(entry.payload);
      if (entry.type === 'session') merged.sessions.push(payload);
      else if (entry.type === 'exercise') merged.exercises.push(payload);
      else if (entry.type === 'routine') merged.routines.push(payload);
      else if (entry.type === 'weight') merged.bodyWeightHistory.push(payload);
      else if (entry.type === 'settings') merged.settings = { ...DEFAULT_SETTINGS, ...payload };
      else if (entry.type === 'draft') merged.draft = payload;
    });
    return merged;
  }

  function mapsEqual(left, right) {
    if (left.size !== right.size) return false;
    for (const [key, value] of left.entries()) {
      const other = right.get(key);
      if (!other || value.type !== other.type || !isSame(value.payload, other.payload)) return false;
    }
    return true;
  }

  function documentReference(uid, id) {
    return window.FORMAFirebaseFirestore.doc(firestore, 'users', uid, 'items', id);
  }

  async function writeMapDiff(uid, before, after) {
    const operations = [];
    after.forEach((entry, id) => {
      const previous = before.get(id);
      if (!previous || previous.type !== entry.type || !isSame(previous.payload, entry.payload)) {
        operations.push({ kind: 'set', id, entry });
      }
    });
    before.forEach((entry, id) => {
      if (!after.has(id)) operations.push({ kind: 'delete', id });
    });

    for (let offset = 0; offset < operations.length; offset += 400) {
      const batch = window.FORMAFirebaseFirestore.writeBatch(firestore);
      operations.slice(offset, offset + 400).forEach(operation => {
        const reference = documentReference(uid, operation.id);
        if (operation.kind === 'delete') {
          batch.delete(reference);
        } else {
          batch.set(reference, {
            type: operation.entry.type,
            payload: operation.entry.payload,
            updatedAt: window.FORMAFirebaseFirestore.serverTimestamp()
          });
        }
      });
      await batch.commit();
    }
    return operations.length;
  }

  async function bootstrapFromCloud(snapshot) {
    const api = bridge();
    if (!api) throw new Error('FORMA did not finish loading.');
    const local = api.getState();
    const remote = stateFromSnapshot(snapshot);
    const merged = mergeInitialState(local, remote);
    const remoteMap = stateToEntries(remote);
    const mergedMap = stateToEntries(merged);

    bootstrapped = true;
    bootstrapping = true;
    lastSyncedState = clone(remote);
    api.applyCloudState(merged);
    setStatus('Syncing', 'Merging this device with your cloud records. Keep this page open until the first sync finishes.', 'warning');

    try {
      const count = await writeMapDiff(currentUser.uid, remoteMap, mergedMap);
      lastSyncedState = clone(merged);
      localStorage.setItem(OWNER_KEY, currentUser.uid);
      setStatus('Synced', count ? 'Your existing device data has been added to your private cloud account.' : 'Your FORMA data is connected to your private cloud account.', 'online');
    } catch (error) {
      lastSyncedState = clone(remote);
      bootstrapped = false;
      throw error;
    } finally {
      bootstrapping = false;
      if (pendingLocalChange) {
        pendingLocalChange = false;
        queueLocalSync();
      }
      refreshControls();
    }
  }

  function queueLocalSync() {
    if (!currentUser || !bootstrapped || applyingRemote) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveChain = saveChain.catch(() => {}).then(async () => {
        if (!currentUser || !bootstrapped || !lastSyncedState) return;
        const api = bridge();
        if (!api) return;
        const current = api.getState();
        const previousMap = stateToEntries(lastSyncedState);
        const currentMap = stateToEntries(current);
        setStatus(navigator.onLine ? 'Syncing' : 'Offline', navigator.onLine ? 'Sending your latest changes to your cloud account…' : 'Changes are saved on this device and will sync when internet returns.', 'warning');
        const count = await writeMapDiff(currentUser.uid, previousMap, currentMap);
        lastSyncedState = clone(current);
        setStatus('Synced', count ? 'Your latest changes are saved to your cloud account.' : 'Your cloud records are up to date.', 'online');
      }).catch(error => {
        setStatus('Sync error', 'Your device copy is safe. Cloud sync could not finish: ' + (error.message || 'Unknown error'), 'warning');
        console.error('FORMA Cloud Sync failed:', error);
        notify('Cloud sync could not finish. Your local records are still saved on this device.');
      });
    }, 350);
  }

  function handleSnapshot(snapshot) {
    if (snapshot.metadata.fromCache) {
      if (!bootstrapped && !snapshot.metadata.hasPendingWrites && snapshot.size > 0) {
        const api = bridge();
        if (api) {
          const local = api.getState();
          const cached = stateFromSnapshot(snapshot);
          api.applyCloudState(mergeInitialState(local, cached));
          setStatus('Offline cache', 'Showing this device’s saved data. Cloud changes will be checked when internet returns.', 'warning');
        }
      }
      return;
    }
    if (snapshot.metadata.hasPendingWrites) return;

    if (!bootstrapped) {
      if (bootstrapping) return;
      bootstrapFromCloud(snapshot).catch(error => {
        bootstrapped = false;
        bootstrapping = false;
        setStatus('Sync error', 'Could not initialize cloud sync: ' + (error.message || 'Unknown error'), 'warning');
        console.error('FORMA initial cloud sync failed:', error);
        notify('Cloud sync setup failed. Your local workout data has not been deleted.');
        refreshControls();
      });
      return;
    }

    const api = bridge();
    if (!api) return;
    const remote = stateFromSnapshot(snapshot);
    const local = api.getState();
    const merged = mergeRemoteWithLocalEdits(remote, local, lastSyncedState);
    const hasLocalChanges = !mapsEqual(stateToEntries(merged), stateToEntries(remote));

    lastSyncedState = clone(remote);
    if (!isSame(merged, local)) {
      applyingRemote = true;
      api.applyCloudState(merged);
      applyingRemote = false;
    }
    if (hasLocalChanges) queueLocalSync();
    setStatus('Synced', 'Your signed-in devices are connected to the same FORMA data.', 'online');
  }

  async function startForUser(user) {
    if (stopItemsListener) {
      stopItemsListener();
      stopItemsListener = null;
    }
    currentUser = user;
    bootstrapped = false;
    bootstrapping = false;
    pendingLocalChange = false;
    lastSyncedState = null;

    const linkedOwner = localStorage.getItem(OWNER_KEY);
    if (linkedOwner && linkedOwner !== user.uid) {
      setStatus('Account mismatch', 'This browser’s local FORMA data is linked to a different Google account. Sign back into that account here, or use a separate browser profile for another account.', 'warning');
      refreshControls();
      return;
    }

    setStatus('Connecting', 'Connecting FORMA to your private cloud database…', 'warning');
    refreshControls();

    const items = window.FORMAFirebaseFirestore.collection(firestore, 'users', user.uid, 'items');
    stopItemsListener = window.FORMAFirebaseFirestore.onSnapshot(
      items,
      { includeMetadataChanges: true },
      handleSnapshot,
      error => {
        setStatus('Sync error', 'Cloud database access failed: ' + (error.message || 'Check your Firestore rules.'), 'warning');
        console.error('FORMA Firestore listener failed:', error);
      }
    );
  }

  function stopForUser() {
    if (stopItemsListener) {
      stopItemsListener();
      stopItemsListener = null;
    }
    currentUser = null;
    bootstrapped = false;
    bootstrapping = false;
    lastSyncedState = null;
    clearTimeout(saveTimer);
    setStatus('Not signed in', 'Sign in with the same Google account on your laptop and iPhone to enable automatic sync.', '');
    refreshControls();
  }

  async function initializeFirebase() {
    const modules = await Promise.all([
      import('https://www.gstatic.com/firebasejs/' + SDK_VERSION + '/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/' + SDK_VERSION + '/firebase-auth.js'),
      import('https://www.gstatic.com/firebasejs/' + SDK_VERSION + '/firebase-firestore.js')
    ]);
    const appSdk = modules[0];
    const authSdk = modules[1];
    const firestoreSdk = modules[2];
    const app = appSdk.initializeApp(firebaseConfig);
    firebaseAuth = authSdk.getAuth(app);
    try {
      firestore = firestoreSdk.initializeFirestore(app, {
        localCache: firestoreSdk.persistentLocalCache({
          tabManager: firestoreSdk.persistentMultipleTabManager()
        })
      });
    } catch (error) {
      console.warn('FORMA could not enable multi-tab Firestore cache; using the default cache.', error);
      firestore = firestoreSdk.getFirestore(app);
    }

    window.FORMAFirebaseFirestore = firestoreSdk;
    await authSdk.setPersistence(firebaseAuth, authSdk.browserLocalPersistence).catch(error => {
      console.warn('FORMA could not set browser auth persistence.', error);
    });

    authSdk.onAuthStateChanged(firebaseAuth, user => {
      if (user) startForUser(user).catch(error => {
        setStatus('Sync error', error.message || 'Could not connect this account.', 'warning');
      });
      else stopForUser();
    });
    authSdk.getRedirectResult(firebaseAuth).catch(error => {
      setStatus('Sign-in error', error.message || 'Google sign-in did not complete.', 'warning');
    });

    document.addEventListener('click', async event => {
      const button = event.target.closest('[data-cloud-action]');
      if (!button) return;
      const action = button.dataset.cloudAction;
      if (action === 'sign-in') {
        if (!firebaseReady) return;
        button.disabled = true;
        try {
          const provider = new authSdk.GoogleAuthProvider();
          provider.setCustomParameters({ prompt: 'select_account' });
          const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
          if (isMobile) await authSdk.signInWithRedirect(firebaseAuth, provider);
          else await authSdk.signInWithPopup(firebaseAuth, provider);
        } catch (error) {
          setStatus('Sign-in error', error.message || 'Google sign-in failed.', 'warning');
          notify('Google sign-in failed. Please try again.');
        } finally {
          button.disabled = false;
        }
      } else if (action === 'sign-out' && firebaseAuth) {
        button.disabled = true;
        try {
          await authSdk.signOut(firebaseAuth);
        } catch (error) {
          setStatus('Sign-out error', error.message || 'Could not sign out.', 'warning');
        } finally {
          button.disabled = false;
        }
      }
    });

    window.addEventListener('forma:local-change', () => {
      if (applyingRemote) return;
      if (bootstrapping) {
        pendingLocalChange = true;
        return;
      }
      queueLocalSync();
    });
    window.addEventListener('forma:rendered', refreshControls);
    window.addEventListener('online', () => {
      if (currentUser && bootstrapped) queueLocalSync();
      else if (currentUser) setStatus('Connecting', 'Internet restored. Checking your cloud data…', 'warning');
    });
    window.addEventListener('offline', () => {
      if (currentUser) setStatus('Offline', 'Your device keeps a local copy. Pending changes will sync when internet returns.', 'warning');
    });
    refreshControls();
  }

  if (!isConfigured(firebaseConfig)) {
    setStatus('Setup required', 'Cloud sync is ready in the code, but this Firebase project still needs its web configuration. Follow CLOUD_SETUP.md.', 'warning');
    refreshControls();
    console.info('FORMA Cloud Sync is waiting for js/firebase-config.js to be configured.');
    return;
  }

  firebaseReady = true;
  initializeFirebase().then(() => {
    if (!currentUser) setStatus('Not signed in', 'Your Firebase project is connected. Sign in with the same Google account on each device.', '');
    refreshControls();
  }).catch(error => {
    firebaseReady = false;
    setStatus('Setup error', 'Firebase could not start: ' + (error.message || 'Check the web app configuration.'), 'warning');
    console.error('FORMA Firebase initialization failed:', error);
    refreshControls();
  });
})();
