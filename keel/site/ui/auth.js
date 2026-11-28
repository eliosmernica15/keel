/* Keel local-first authentication — no hosted backend is required.
 *
 * Pure core: guarded, versioned localStorage records, PBKDF2-SHA256 password
 * hashing (WebCrypto), expiring local sessions, one-time recovery codes, and
 * in-browser verification of Google Identity Services ID tokens against
 * Google's JWKS. No plaintext password, recovery code or token is ever stored
 * or logged. Plain strings are UI messages, not security claims: this is a
 * local convenience layer, not a server-side identity provider.
 *
 * UMD so the same file runs as a browser script (window.KeelAuth) and can be
 * required by the Node tests without a package.json type change.
 */
(function (root) {
  'use strict';

  var VERSION = 1;
  var KEYS = {
    accounts: 'keel.auth.v1.accounts',
    session: 'keel.auth.v1.session',
    settings: 'keel.auth.v1.settings'
  };
  var SESSION_TTL_MS = 12 * 60 * 60 * 1000;
  var PBKDF2_ITERATIONS = 180000;
  var GOOGLE_ISSUERS = ['https://accounts.google.com', 'accounts.google.com'];
  var GOOGLE_CERTS_URL = 'https://www.googleapis.com/oauth2/v3/certs';
  var GOOGLE_GIS_URL = 'https://accounts.google.com/gsi/client';
  var DEFAULT_NEXT = '/new';
  var encoder = typeof TextEncoder !== 'undefined' ? new TextEncoder() : null;
  var decoder = typeof TextDecoder !== 'undefined' ? new TextDecoder() : null;

  /* ------------------------------- storage ------------------------------- */

  function memoryStorage() {
    var map = Object.create(null);
    return {
      getItem: function (key) { return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : null; },
      setItem: function (key, value) { map[key] = String(value); },
      removeItem: function (key) { delete map[key]; }
    };
  }

  function browserStorage() {
    try {
      var store = root.localStorage;
      if (!store || typeof store.getItem !== 'function') return null;
      var probe = '__keel_auth_probe__';
      store.setItem(probe, '1');
      store.removeItem(probe);
      return store;
    } catch (e) {
      return null; /* private mode / disabled storage */
    }
  }

  function readJSON(storage, key, fallback) {
    if (!storage || typeof storage.getItem !== 'function') return fallback;
    try {
      var raw = storage.getItem(key);
      if (typeof raw !== 'string' || !raw) return fallback;
      var value = JSON.parse(raw);
      if (!value || typeof value !== 'object' || value.v !== VERSION) return fallback;
      return value;
    } catch (e) {
      return fallback; /* corrupt or foreign data is ignored, never trusted */
    }
  }

  function writeJSON(storage, key, value) {
    if (!storage || typeof storage.setItem !== 'function') return false;
    try {
      storage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false; /* quota / private mode */
    }
  }

  function removeKey(storage, key) {
    try {
      if (storage && typeof storage.removeItem === 'function') storage.removeItem(key);
    } catch (e) { /* best effort */ }
  }

  function getCrypto(explicit) {
    if (explicit && explicit.subtle) return explicit;
    if (root.crypto && root.crypto.subtle) return root.crypto;
    return null;
  }

  function requireCrypto(explicit) {
    var crypto = getCrypto(explicit);
    if (!crypto || !crypto.subtle) {
      throw new Error('Secure browser cryptography is unavailable. Use a current browser over HTTPS.');
    }
    return crypto;
  }

  /* ------------------------------- encoding ------------------------------ */

  function bytesToB64(bytes) {
    var binary = '';
    for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    if (typeof btoa === 'function') return btoa(binary);
    if (typeof Buffer !== 'undefined') return Buffer.from(bytes).toString('base64');
    throw new Error('No base64 encoder is available.');
  }

  function b64ToBytes(value) {
    var binary;
    if (typeof atob === 'function') binary = atob(value);
    else if (typeof Buffer !== 'undefined') binary = Buffer.from(value, 'base64').toString('binary');
    else throw new Error('No base64 decoder is available.');
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function bytesToText(bytes) {
    if (decoder) return decoder.decode(bytes);
    return decodeURIComponent(Array.prototype.map.call(bytes, function (b) {
      return '%' + ('0' + b.toString(16)).slice(-2);
    }).join(''));
  }

  function bytesToB64Url(bytes) {
    return bytesToB64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function b64UrlToBytes(value) {
    if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('Invalid base64url value.');
    var padded = value.replace(/-/g, '+').replace(/_/g, '/');
    while (padded.length % 4) padded += '=';
    return b64ToBytes(padded);
  }

  function randomBytes(size, explicitCrypto) {
    var crypto = requireCrypto(explicitCrypto);
    var bytes = new Uint8Array(size);
    crypto.getRandomValues(bytes);
    return bytes;
  }

  /* ------------------------------ validation ----------------------------- */

  function validEmail(value) {
    var email = String(value || '').trim();
    return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function normalizeEmail(value) {
    return String(value || '').trim().toLowerCase();
  }

  function passwordError(value) {
    var password = String(value || '');
    if (password.length < 8) return 'Use at least 8 characters for your password.';
    if (password.length > 200) return 'That password is too long.';
    return '';
  }

  function constantTimeEqual(a, b) {
    var left = String(a || '');
    var right = String(b || '');
    if (left.length !== right.length) return false;
    var diff = 0;
    for (var i = 0; i < left.length; i++) {
      diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
    }
    return diff === 0;
  }

  /* ---------------------------- password crypto -------------------------- */

  function derive(password, saltB64, iterations, explicitCrypto) {
    var crypto = requireCrypto(explicitCrypto);
    var keyPromise;
    if (!encoder) throw new Error('TextEncoder is unavailable.');
    keyPromise = crypto.subtle.importKey(
      'raw', encoder.encode(String(password)), 'PBKDF2', false, ['deriveBits']
    );
    return keyPromise.then(function (key) {
      return crypto.subtle.deriveBits({
        name: 'PBKDF2',
        salt: b64ToBytes(saltB64),
        iterations: iterations,
        hash: 'SHA-256'
      }, key, 256);
    }).then(function (bits) {
      return bytesToB64(new Uint8Array(bits));
    });
  }

  function hashPassword(password, explicitCrypto, iterations) {
    var error = passwordError(password);
    if (error) return Promise.reject(new Error(error));
    var rounds = iterations || PBKDF2_ITERATIONS;
    var salt = bytesToB64(randomBytes(16, explicitCrypto));
    return derive(password, salt, rounds, explicitCrypto).then(function (hash) {
      return { algo: 'pbkdf2-sha256', iterations: rounds, salt: salt, hash: hash };
    });
  }

  function verifyPassword(password, account, explicitCrypto) {
    if (!account || !account.hash || !account.salt || !account.algo) {
      return Promise.resolve(false);
    }
    if (account.algo !== 'pbkdf2-sha256') return Promise.resolve(false);
    return derive(password, account.salt, account.iterations || PBKDF2_ITERATIONS, explicitCrypto)
      .then(function (hash) { return constantTimeEqual(hash, account.hash); },
        function () { return false; });
  }

  function generateRecoveryCode(explicitCrypto) {
    var bytes = randomBytes(12, explicitCrypto);
    var hex = Array.prototype.map.call(bytes, function (byte) {
      return ('0' + byte.toString(16)).slice(-2);
    }).join('').toUpperCase();
    return 'KEEL-' + hex.slice(0, 4) + '-' + hex.slice(4, 8) + '-' +
      hex.slice(8, 12) + '-' + hex.slice(12, 16);
  }

  function normalizeRecoveryCode(value) {
    return String(value || '').trim().toUpperCase();
  }

  function hashRecoveryCode(code, saltB64, iterations, explicitCrypto) {
    return derive(normalizeRecoveryCode(code), saltB64, iterations, explicitCrypto);
  }

  /* ------------------------------- accounts ------------------------------ */

  function accountMap(storage) {
    var data = readJSON(storage, KEYS.accounts, { v: VERSION, users: {} });
    if (!data.users || typeof data.users !== 'object' || Array.isArray(data.users)) {
      data.users = {};
    }
    return data;
  }

  function findAccount(storage, email) {
    var users = accountMap(storage).users;
    return users[normalizeEmail(email)] || null;
  }

  function createAccount(storage, input, explicitCrypto) {
    input = input || {};
    if (!validEmail(input.email)) {
      return Promise.resolve({ ok: false, error: 'Enter a valid email address.' });
    }
    var passwordCheck = passwordError(input.password);
    if (passwordCheck) return Promise.resolve({ ok: false, error: passwordCheck });

    var email = normalizeEmail(input.email);
    var data = accountMap(storage);
    if (data.users[email]) {
      return Promise.resolve({
        ok: false,
        error: 'An account for this email already exists in this browser. Sign in or reset your password.'
      });
    }

    var code = generateRecoveryCode(explicitCrypto);
    var recoverySalt = bytesToB64(randomBytes(16, explicitCrypto));
    return hashPassword(input.password, explicitCrypto)
      .then(function (password) {
        return hashRecoveryCode(code, recoverySalt, PBKDF2_ITERATIONS, explicitCrypto)
          .then(function (recoveryHash) {
            data.users[email] = {
              email: email,
              provider: 'email',
              algo: password.algo,
              iterations: password.iterations,
              salt: password.salt,
              hash: password.hash,
              recovery: {
                algo: 'pbkdf2-sha256',
                iterations: PBKDF2_ITERATIONS,
                salt: recoverySalt,
                hash: recoveryHash
              },
              createdAt: Date.now()
            };
            if (!writeJSON(storage, KEYS.accounts, data)) {
              throw new Error('This browser could not save the account. Check that local storage is enabled.');
            }
            return { ok: true, email: email, recoveryCode: code };
          });
      })
      .catch(function (err) {
        return { ok: false, error: err && err.message ? err.message : 'The account could not be created.' };
      });
  }

  function ensureGoogleAccount(storage, email, explicitCrypto) {
    if (!validEmail(email)) return Promise.resolve({ ok: false, error: 'Google did not return a valid email address.' });
    var normalized = normalizeEmail(email);
    var data = accountMap(storage);
    if (data.users[normalized]) return Promise.resolve({ ok: true, email: normalized, created: false });
    data.users[normalized] = {
      email: normalized,
      provider: 'google',
      createdAt: Date.now()
    };
    if (!writeJSON(storage, KEYS.accounts, data)) {
      return Promise.resolve({ ok: false, error: 'This browser could not save the account. Check that local storage is enabled.' });
    }
    return Promise.resolve({ ok: true, email: normalized, created: true });
  }

  /* ------------------------------- sessions ------------------------------ */

  function createSession(storage, options, explicitCrypto, now) {
    options = options || {};
    var email = normalizeEmail(options.email);
    if (!email) return Promise.reject(new Error('A signed-in session needs an email address.'));
    var issued = typeof now === 'number' && isFinite(now) ? now : Date.now();
    var token = bytesToB64Url(randomBytes(18, explicitCrypto));
    var session = {
      v: VERSION,
      token: token,
      email: email,
      method: options.method === 'google' ? 'google' : 'email',
      iat: issued,
      exp: issued + SESSION_TTL_MS
    };
    if (!writeJSON(storage, KEYS.session, session)) {
      return Promise.reject(new Error('This browser could not save the session. Check that local storage is enabled.'));
    }
    return Promise.resolve(session);
  }

  function sessionIsValid(session, current) {
    return !!session && typeof session.token === 'string' && session.token.length >= 20 &&
      typeof session.email === 'string' && validEmail(session.email) &&
      (session.method === 'google' || session.method === 'email') &&
      typeof session.iat === 'number' && typeof session.exp === 'number' &&
      session.exp > current && session.iat <= current + 60000;
  }

  function getSession(storage, now) {
    var session = readJSON(storage, KEYS.session, null);
    var current = typeof now === 'number' && isFinite(now) ? now : Date.now();
    if (!sessionIsValid(session, current)) {
      removeKey(storage, KEYS.session);
      return null;
    }
    return session;
  }

  function signOut(storage) {
    removeKey(storage, KEYS.session);
    return true;
  }

  function signIn(storage, input, explicitCrypto, now) {
    input = input || {};
    if (!validEmail(input.email)) return Promise.resolve({ ok: false, error: 'Enter a valid email address.' });
    var account = findAccount(storage, input.email);
    if (!account) {
      return Promise.resolve({
        ok: false,
        error: 'No account for this email exists in this browser. Create one or use Google sign-in.'
      });
    }
    if (!account.hash) {
      return Promise.resolve({ ok: false, error: 'This account uses Google sign-in. Choose Continue with Google.' });
    }
    return verifyPassword(input.password, account, explicitCrypto).then(function (matches) {
      if (!matches) {
        return { ok: false, error: 'That password is incorrect. Try again or reset it with your recovery code.' };
      }
      return createSession(storage, { email: account.email, method: 'email' }, explicitCrypto, now)
        .then(function (session) { return { ok: true, session: session }; });
    }, function () {
      return { ok: false, error: 'Secure browser cryptography is unavailable. Use a current browser over HTTPS.' };
    });
  }

  function resetPassword(storage, input, explicitCrypto) {
    input = input || {};
    if (!validEmail(input.email)) return Promise.resolve({ ok: false, error: 'Enter a valid email address.' });
    var check = passwordError(input.newPassword);
    if (check) return Promise.resolve({ ok: false, error: check });
    var data = accountMap(storage);
    var email = normalizeEmail(input.email);
    var account = data.users[email];
    if (!account || !account.recovery || !account.recovery.hash) {
      return Promise.resolve({
        ok: false,
        error: 'No password account for this email has a recovery code in this browser.'
      });
    }
    var recovery = account.recovery;
    return hashRecoveryCode(input.recoveryCode, recovery.salt, recovery.iterations || PBKDF2_ITERATIONS, explicitCrypto)
      .then(function (hash) {
        if (!constantTimeEqual(hash, recovery.hash)) {
          return { ok: false, error: 'That recovery code does not match. Check the code from signup.' };
        }
        return hashPassword(input.newPassword, explicitCrypto).then(function (password) {
          account.algo = password.algo;
          account.iterations = password.iterations;
          account.salt = password.salt;
          account.hash = password.hash;
          if (!writeJSON(storage, KEYS.accounts, data)) {
            return { ok: false, error: 'This browser could not save the new password.' };
          }
          signOut(storage); /* a reset invalidates the old local session */
          return { ok: true, email: email };
        });
      })
      .catch(function (err) {
        return { ok: false, error: err && err.message ? err.message : 'The password could not be reset.' };
      });
  }

  function changePassword(storage, input, explicitCrypto) {
    input = input || {};
    var check = passwordError(input.newPassword);
    if (check) return Promise.resolve({ ok: false, error: check });
    var session = getSession(storage);
    var email = normalizeEmail(input.email || (session && session.email));
    if (!email) return Promise.resolve({ ok: false, error: 'Sign in before changing your password.' });
    if (session && session.email !== email) {
      return Promise.resolve({ ok: false, error: 'You can only change the password for the signed-in account.' });
    }
    var data = accountMap(storage);
    var account = data.users[email];
    if (!account || !account.hash) {
      return Promise.resolve({ ok: false, error: 'This account uses Google sign-in and has no password to change.' });
    }
    return verifyPassword(input.currentPassword, account, explicitCrypto).then(function (matches) {
      if (!matches) return { ok: false, error: 'Your current password is incorrect.' };
      return hashPassword(input.newPassword, explicitCrypto).then(function (password) {
        account.algo = password.algo;
        account.iterations = password.iterations;
        account.salt = password.salt;
        account.hash = password.hash;
        if (!writeJSON(storage, KEYS.accounts, data)) {
          return { ok: false, error: 'This browser could not save the new password.' };
        }
        return { ok: true, email: email };
      });
    }, function () {
      return { ok: false, error: 'Secure browser cryptography is unavailable. Use a current browser over HTTPS.' };
    });
  }

  /* ------------------------------- settings ------------------------------ */

  function getConfig(storage) {
    var config = readJSON(storage, KEYS.settings, { v: VERSION, googleClientId: '' });
    return {
      v: VERSION,
      googleClientId: typeof config.googleClientId === 'string' ? config.googleClientId : ''
    };
  }

  function setGoogleClientId(storage, value) {
    var clientId = String(value || '').trim();
    if (!clientId) return { ok: false, error: 'Enter your Google Client ID first.' };
    if (!/^[A-Za-z0-9._-]{10,200}$/.test(clientId)) {
      return {
        ok: false,
        error: 'That does not look like a Google Client ID (for example 123-abc.apps.googleusercontent.com).'
      };
    }
    var config = getConfig(storage);
    config.googleClientId = clientId;
    if (!writeJSON(storage, KEYS.settings, config)) {
      return { ok: false, error: 'This browser could not save that setting.' };
    }
    return { ok: true, googleClientId: clientId };
  }

  function loadRemoteConfig(fetchImpl, url) {
    var fetcher = typeof fetchImpl === 'function' ? fetchImpl : (typeof fetch === 'function' ? fetch : null);
    if (!fetcher) return Promise.resolve({ googleClientId: '' });
    try {
      return Promise.resolve(fetcher(url || '/config/auth.json', { cache: 'no-store' }))
        .then(function (response) {
          if (!response || !response.ok) return { googleClientId: '' };
          var parsed = response.json();
          return parsed && typeof parsed.catch === 'function'
            ? parsed.catch(function () { return {}; })
            : Promise.resolve(parsed || {});
        })
        .then(function (data) {
          return {
            googleClientId: data && typeof data.googleClientId === 'string' ? data.googleClientId.trim() : ''
          };
        }, function () { return { googleClientId: '' }; });
    } catch (e) {
      return Promise.resolve({ googleClientId: '' });
    }
  }

  function googleButtonState(config) {
    var clientId = config && typeof config.googleClientId === 'string' ? config.googleClientId.trim() : '';
    if (!clientId) {
      return {
        configured: false,
        message: 'Google sign-in needs a Client ID',
        action: 'settings'
      };
    }
    return { configured: true, message: 'Google sign-in is ready', clientId: clientId };
  }

  /* ---------------------------- route helpers ---------------------------- */

  function safeNext(raw, fallback) {
    var target = String(raw || '');
    var base = fallback && /^\/(?![\/\\])/.test(fallback) && !/[\r\n\\]/.test(fallback)
      ? fallback : DEFAULT_NEXT;
    if (!target || !/^\/(?![\/\\])/.test(target) || /[\r\n\\]/.test(target)) return base;
    try {
      var decoded = decodeURIComponent(target);
      if (decoded.split('/').indexOf('..') !== -1) return base;
    } catch (e) {
      return base;
    }
    return target;
  }

  function gateDecision(options) {
    options = options || {};
    var current = typeof options.now === 'number' ? options.now : Date.now();
    var session = options.session !== undefined
      ? options.session
      : getSession(options.storage, current);
    if (session && !sessionIsValid(session, current)) session = null;
    if (session) return { allow: true, session: session };
    var pathname = options.pathname || DEFAULT_NEXT;
    var next = safeNext(options.next || pathname, pathname);
    return { allow: false, redirect: '/login?next=' + encodeURIComponent(next) };
  }

  /* --------------------------- Google ID tokens -------------------------- */

  function decodeIdToken(token) {
    var parts = String(token || '').split('.');
    if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) {
      throw new Error('Malformed Google ID token.');
    }
    var header = JSON.parse(bytesToText(b64UrlToBytes(parts[0])));
    var payload = JSON.parse(bytesToText(b64UrlToBytes(parts[1])));
    if (!header || !payload || typeof header !== 'object' || typeof payload !== 'object') {
      throw new Error('Malformed Google ID token.');
    }
    return {
      header: header,
      payload: payload,
      signature: b64UrlToBytes(parts[2]),
      signingInput: parts[0] + '.' + parts[1]
    };
  }

  function assertionFailure(message) {
    return { ok: false, error: message };
  }

  function verifyGoogleIdToken(options) {
    options = options || {};
    var crypto;
    try {
      crypto = requireCrypto(options.crypto);
      var token = decodeIdToken(options.idToken);
      var clientId = String(options.clientId || '').trim();
      if (!clientId) return Promise.resolve(assertionFailure('No Google Client ID is configured.'));
      if (token.header.alg !== 'RS256') {
        return Promise.resolve(assertionFailure('Google ID token uses an unsupported algorithm.'));
      }
      var keys = options.jwks && Array.isArray(options.jwks.keys) ? options.jwks.keys : [];
      var jwk = keys.filter(function (candidate) {
        return candidate && candidate.kid === token.header.kid &&
          candidate.kty === 'RSA' && candidate.n && candidate.e &&
          (!candidate.alg || candidate.alg === 'RS256') &&
          (!candidate.use || candidate.use === 'sig');
      })[0];
      if (!jwk) return Promise.resolve(assertionFailure('No matching Google signing key was found.'));

      var key = awaitImport(crypto, jwk);
      return key.then(function (publicKey) {
        return crypto.subtle.verify(
          'RSASSA-PKCS1-v1_5', publicKey, token.signature,
          encoder.encode(token.signingInput)
        );
      }).then(function (valid) {
        if (!valid) return assertionFailure('The Google ID token signature is invalid.');
        var nowSec = Math.floor((typeof options.now === 'number' ? options.now : Date.now()) / 1000);
        var claims = token.payload;
        if (GOOGLE_ISSUERS.indexOf(claims.iss) === -1) {
          return assertionFailure('The Google ID token has an unexpected issuer.');
        }
        var audience = claims.aud;
        if (Array.isArray(audience)) {
          if (audience.length !== 1 || audience[0] !== clientId) {
            return assertionFailure('The Google ID token was issued for a different Client ID.');
          }
        } else if (audience !== clientId) {
          return assertionFailure('The Google ID token was issued for a different Client ID.');
        }
        if (typeof claims.exp !== 'number' || claims.exp <= nowSec) {
          return assertionFailure('The Google ID token has expired. Try signing in again.');
        }
        if (typeof claims.iat !== 'number' || claims.iat > nowSec + 60) {
          return assertionFailure('The Google ID token has an invalid issue time.');
        }
        if (claims.email_verified !== true || typeof claims.email !== 'string' || !claims.email) {
          return assertionFailure('Google did not confirm a verified email address.');
        }
        return { ok: true, claims: claims };
      }, function () {
        return assertionFailure('The Google ID token could not be verified.');
      });
    } catch (e) {
      return Promise.resolve(assertionFailure('The Google ID token could not be read.'));
    }
  }

  function awaitImport(crypto, jwk) {
    try {
      return Promise.resolve(crypto.subtle.importKey(
        'jwk',
        { kty: 'RSA', n: jwk.n, e: jwk.e, alg: 'RS256', use: 'sig', ext: false },
        { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
        false,
        ['verify']
      ));
    } catch (e) {
      return Promise.reject(e);
    }
  }

  function fetchJwks(fetchImpl) {
    var fetcher = typeof fetchImpl === 'function' ? fetchImpl : (typeof fetch === 'function' ? fetch : null);
    if (!fetcher) return Promise.reject(new Error('Google certificate download is unavailable in this browser.'));
    return Promise.resolve(fetcher(GOOGLE_CERTS_URL, { cache: 'no-store' })).then(function (response) {
      if (!response || !response.ok) throw new Error('Google certificates could not be downloaded.');
      return response.json();
    });
  }

  /* -------------------------------- browser ------------------------------ */

  function byId(id) {
    return typeof document === 'undefined' ? null : document.getElementById(id);
  }

  function all(selector) {
    if (typeof document === 'undefined') return [];
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function showNote(message, isError) {
    var note = byId('login-demo-note') || byId('auth-status');
    if (!note) return;
    note.textContent = message || '';
    note.hidden = !message;
    if (note.classList) note.classList.toggle('is-error', !!isError);
  }

  function setError(id, message) {
    var field = byId(id);
    var error = byId(id + '-error');
    if (error) {
      error.textContent = message || '';
      error.hidden = !message;
    }
    if (field) {
      if (message) field.setAttribute('aria-invalid', 'true');
      else field.removeAttribute('aria-invalid');
    }
  }

  function readValue(id) {
    var field = byId(id);
    return field ? String(field.value || '').trim() : '';
  }

  function setBusy(panel, busy) {
    all('button').forEach(function (button) {
      if (panel && !panel.contains(button)) return;
      if (button.getAttribute('data-auth-tab')) return;
      button.disabled = !!busy;
    });
  }

  function params() {
    try { return new URLSearchParams(root.location.search); }
    catch (e) { return new URLSearchParams(''); }
  }

  function destination(paramValue) {
    var next = safeNext(paramValue, DEFAULT_NEXT);
    if (/^\/login(?:[\/?]|$)/.test(next)) next = DEFAULT_NEXT;
    return next;
  }

  function finish(method, nextValue) {
    try {
      var url = new URL(destination(nextValue), root.location.href);
      url.searchParams.set('auth', method === 'google' ? 'google' : 'email');
      root.location.assign(url.pathname + url.search + url.hash);
    } catch (e) {
      root.location.assign(DEFAULT_NEXT + '?auth=' + (method === 'google' ? 'google' : 'email'));
    }
  }

  function runGate() {
    var decision = gateDecision({ storage: browserStorage(), pathname: root.location.pathname || DEFAULT_NEXT });
    if (!decision.allow) root.location.replace(decision.redirect);
    return decision;
  }

  function selectTab(key) {
    all('[data-auth-tab]').forEach(function (tab) {
      var active = tab.getAttribute('data-auth-tab') === key;
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.tabIndex = active ? 0 : -1;
    });
    all('[data-auth-panel]').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-auth-panel') !== key;
    });
    var recovery = byId('auth-recovery');
    if (recovery) recovery.hidden = true;
  }

  function openSettings() {
    var details = byId('auth-settings');
    if (details) {
      details.open = true;
      if (typeof details.scrollIntoView === 'function') {
        try { details.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
        catch (e) { details.scrollIntoView(); }
      }
    }
    var input = byId('auth-client-id');
    if (input && typeof input.focus === 'function') input.focus();
  }

  function setClientId(inputId, statusId) {
    var input = byId(inputId);
    var status = byId(statusId);
    var result = setGoogleClientId(browserStorage(), input ? input.value : '');
    if (status) {
      status.textContent = result.ok
        ? 'Saved in this browser. Google sign-in is now available.'
        : (result.error || 'The setting could not be saved.');
    }
    if (result.ok && inputId === 'auth-client-id') {
      showNote('Google Client ID saved. Continue with Google is now enabled.', false);
      setupGoogleButton(getConfig(browserStorage()));
    }
    return result;
  }

  function loadGisScript() {
    if (root.google && root.google.accounts && root.google.accounts.id) {
      return Promise.resolve(root.google);
    }
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-keel-gis]');
      if (existing && !existing.dataset.loaded) {
        existing.addEventListener('load', function () { resolve(root.google); });
        existing.addEventListener('error', function () { reject(new Error('GIS script failed to load.')); });
        return;
      }
      if (existing) return resolve(root.google);
      var script = document.createElement('script');
      script.src = GOOGLE_GIS_URL;
      script.async = true;
      script.defer = true;
      script.setAttribute('data-keel-gis', '');
      script.addEventListener('load', function () {
        script.dataset.loaded = 'true';
        resolve(root.google);
      });
      script.addEventListener('error', function () {
        reject(new Error('GIS script failed to load.'));
      });
      (document.head || document.documentElement).appendChild(script);
    });
  }

  function setupGoogleButton(config) {
    var button = byId('auth-google-button') || document.querySelector('[data-auth-google]');
    var label = button ? button.querySelector('[data-auth-google-label]') : null;
    var host = byId('auth-google-host');
    if (!button || !host) return;
    var state = googleButtonState(config || getConfig(browserStorage()));
    if (!state.configured) {
      button.hidden = false;
      button.disabled = false;
      if (label) label.textContent = 'Continue with Google';
      host.hidden = true;
      host.innerHTML = '';
      return;
    }
    button.hidden = false;
    button.disabled = true;
    if (label) label.textContent = 'Loading Google sign-in…';
    loadGisScript().then(function (google) {
      if (!google || !google.accounts || !google.accounts.id) {
        throw new Error('Google Identity Services is unavailable.');
      }
      google.accounts.id.initialize({
        client_id: state.clientId,
        callback: function (response) { completeGoogle(response, state.clientId); },
        auto_select: false,
        ux_mode: 'popup'
      });
      host.innerHTML = '';
      google.accounts.id.renderButton(host, {
        theme: 'outline', size: 'large', width: 312, text: 'continue_with'
      });
      host.hidden = false;
      button.hidden = true;
    }).catch(function () {
      button.disabled = false;
      if (label) label.textContent = 'Continue with Google';
      showNote('Google sign-in could not load. Check your connection or use email sign-in.', true);
    });
  }

  function completeGoogle(response, clientId) {
    var credential = response && response.credential;
    var next = params().get('next');
    if (!credential) {
      showNote('Google did not return a sign-in token. Try again or use email sign-in.', true);
      return;
    }
    setBusy(null, true);
    showNote('Verifying Google sign-in…', false);
    fetchJwks().then(function (jwks) {
      return verifyGoogleIdToken({ idToken: credential, clientId: clientId, jwks: jwks });
    }).then(function (verified) {
      if (!verified.ok) throw new Error(verified.error);
      var session = getSession(browserStorage());
      if (session) return session;
      return ensureGoogleAccount(browserStorage(), verified.claims.email)
        .then(function (account) {
          if (!account.ok) throw new Error(account.error);
          return createSession(browserStorage(), {
            email: verified.claims.email, method: 'google'
          });
        });
    }).then(function () {
      finish('google', next);
    }).catch(function (err) {
      setBusy(null, false);
      showNote((err && err.message ? err.message : 'Google sign-in could not be completed.') +
        ' Use email sign-in or check your Client ID in Settings.', true);
    });
  }

  function initLoginPage() {
    var storage = browserStorage();
    if (!storage) {
      showNote('This browser blocks local storage, so sign-in cannot work here. Enable site data and reload.', true);
      return;
    }
    var query = params();
    var existing = getSession(storage);
    if (existing) {
      root.location.replace(destination(query.get('next')));
      return;
    }

    var intent = String(query.get('intent') || 'login').toLowerCase();
    var initial = intent === 'signup' || intent === 'trial' ? 'signup'
      : intent === 'reset' ? 'reset' : 'signin';
    selectTab(initial);
    if (intent === 'sales') {
      showNote('For sales questions write to sales@keel.software, or create a local account to get started.', false);
    }

    all('[data-auth-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () { selectTab(tab.getAttribute('data-auth-tab')); });
      tab.addEventListener('keydown', function (event) {
        if (!event || (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft')) return;
        var tabs = all('[data-auth-tab]');
        var index = tabs.indexOf(tab);
        var next = tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        if (next) { event.preventDefault(); selectTab(next.getAttribute('data-auth-tab')); next.focus(); }
      });
    });

    all('[data-auth-switch]').forEach(function (button) {
      button.addEventListener('click', function () { selectTab(button.getAttribute('data-auth-switch')); });
    });

    var signInForm = document.querySelector('[data-auth-form="signin"]');
    if (signInForm) {
      signInForm.addEventListener('submit', function (event) {
        event.preventDefault();
        setError('auth-signin-email', '');
        var email = readValue('auth-signin-email');
        if (!validEmail(email)) {
          setError('auth-signin-email', 'Please enter a valid email address.');
          return;
        }
        setBusy(signInForm, true);
        showNote('Checking your password…', false);
        signIn(storage, { email: email, password: byId('auth-signin-password').value })
          .then(function (result) {
            if (!result.ok) {
              setBusy(null, false);
              showNote(result.error, true);
              return;
            }
            finish('email', query.get('next'));
          })
          .catch(function () {
            setBusy(null, false);
            showNote('Sign-in could not be completed in this browser.', true);
          });
      });
    }

    var signUpForm = document.querySelector('[data-auth-form="signup"]');
    if (signUpForm) {
      signUpForm.addEventListener('submit', function (event) {
        event.preventDefault();
        setError('auth-signup-email', '');
        setError('auth-signup-password', '');
        var email = readValue('auth-signup-email');
        if (!validEmail(email)) {
          setError('auth-signup-email', 'Please enter a valid email address.');
          return;
        }
        var password = byId('auth-signup-password').value;
        if (byId('auth-signup-confirm').value !== password) {
          setError('auth-signup-password', 'The passwords do not match.');
          return;
        }
        setBusy(signUpForm, true);
        showNote('Creating your local account…', false);
        createAccount(storage, { email: email, password: password })
          .then(function (result) {
            setBusy(null, false);
            if (!result.ok) { showNote(result.error, true); return; }
            byId('auth-recovery-code').textContent = result.recoveryCode;
            byId('auth-recovery').hidden = false;
            showNote('Account created. Save your recovery code before continuing.', false);
            return createSession(storage, { email: result.email, method: 'email' })
              .catch(function () {
                showNote('Account created, but this browser could not start a session. Sign in to continue.', true);
              });
          })
          .catch(function () {
            setBusy(null, false);
            showNote('The account could not be created in this browser.', true);
          });
      });
    }

    var done = byId('auth-recovery-done');
    if (done) {
      done.addEventListener('click', function () { finish('email', query.get('next')); });
    }

    var resetForm = document.querySelector('[data-auth-form="reset"]');
    if (resetForm) {
      resetForm.addEventListener('submit', function (event) {
        event.preventDefault();
        setBusy(resetForm, true);
        showNote('Checking your recovery code…', false);
        resetPassword(storage, {
          email: readValue('auth-reset-email'),
          recoveryCode: readValue('auth-reset-code'),
          newPassword: byId('auth-reset-password').value
        }).then(function (result) {
          setBusy(null, false);
          if (!result.ok) { showNote(result.error, true); return; }
          selectTab('signin');
          if (byId('auth-signin-email')) byId('auth-signin-email').value = result.email;
          showNote('Password reset. Sign in with your new password.', false);
        }).catch(function () {
          setBusy(null, false);
          showNote('The password could not be reset in this browser.', true);
        });
      });
    }

    var apple = document.querySelector('[data-auth-apple]');
    if (apple) {
      apple.addEventListener('click', function () {
        showNote('Apple sign-in is not available yet. Use Google or create an account with email instead.', true);
      });
    }

    var google = byId('auth-google-button') || document.querySelector('[data-auth-google]');
    if (google) {
      google.addEventListener('click', function () {
        var state = googleButtonState(getConfig(storage));
        if (!state.configured) {
          showNote('Google sign-in needs a Client ID. Add your own in Settings below, then save.', true);
          openSettings();
        }
      });
    }

    byId('auth-save-client-id') && byId('auth-save-client-id').addEventListener('click', function () {
      setClientId('auth-client-id', 'auth-settings-status');
    });

    loadRemoteConfig().then(function (remote) {
      var config = getConfig(storage);
      if (!config.googleClientId && remote.googleClientId) {
        config.googleClientId = remote.googleClientId;
      }
      setupGoogleButton(config);
    });
  }

  function showSignedIn(method) {
    var status = byId('n-auth-status');
    if (!status) return;
    var session = getSession(browserStorage());
    if (!session) return;
    status.textContent = method === 'google' ? 'Signed in with Google' : 'Signed in';
    status.hidden = false;
    if (status.classList) {
      root.requestAnimationFrame(function () { status.classList.add('is-visible'); });
      root.setTimeout(function () {
        status.classList.remove('is-visible');
        root.setTimeout(function () { status.hidden = true; }, 180);
      }, 2400);
    } else {
      root.setTimeout(function () { status.hidden = true; }, 2400);
    }
  }

  function initNewPage() {
    var storage = browserStorage();
    var query = params();
    var method = query.get('auth');
    if (method === 'google' || method === 'email') showSignedIn(method);

    function leave() {
      if (storage) signOut(storage);
      root.location.assign('/login');
    }
    var signout = byId('n-account-signout');
    if (signout) signout.addEventListener('click', leave);
    var dialogSignout = byId('n-account-dialog-signout');
    if (dialogSignout) dialogSignout.addEventListener('click', leave);

    var save = byId('auth-save-client-id-new');
    if (save) {
      save.addEventListener('click', function () {
        setClientId('auth-client-id-new', 'auth-settings-status-new');
      });
      var field = byId('auth-client-id-new');
      if (field) field.value = getConfig(storage).googleClientId;
    }

    var change = byId('auth-change-password');
    if (change) {
      change.addEventListener('click', function () {
        var status = byId('auth-password-status');
        if (!storage) {
          if (status) status.textContent = 'This browser blocks local storage, so passwords cannot be changed here.';
          return;
        }
        changePassword(storage, {
          currentPassword: byId('auth-current-password').value,
          newPassword: byId('auth-new-password').value
        }).then(function (result) {
          if (status) status.textContent = result.ok ? 'Password changed.' : result.error;
          if (result.ok) {
            byId('auth-current-password').value = '';
            byId('auth-new-password').value = '';
          }
        }, function () {
          if (status) status.textContent = 'Password change is unavailable in this browser.';
        });
      });
    }
  }

  function initPage() {
    try {
      if (document.body && document.body.classList.contains('login-page')) initLoginPage();
      else if (document.body && document.body.classList.contains('n-page')) initNewPage();
    } catch (e) {
      /* An enhancement failure must never break the underlying page. */
    }
  }

  var Auth = {
    VERSION: VERSION,
    KEYS: KEYS,
    SESSION_TTL_MS: SESSION_TTL_MS,
    PBKDF2_ITERATIONS: PBKDF2_ITERATIONS,
    GOOGLE_CERTS_URL: GOOGLE_CERTS_URL,
    GOOGLE_GIS_URL: GOOGLE_GIS_URL,
    memoryStorage: memoryStorage,
    browserStorage: browserStorage,
    readJSON: readJSON,
    writeJSON: writeJSON,
    validEmail: validEmail,
    hashPassword: hashPassword,
    verifyPassword: verifyPassword,
    generateRecoveryCode: generateRecoveryCode,
    createAccount: createAccount,
    findAccount: findAccount,
    ensureGoogleAccount: ensureGoogleAccount,
    createSession: createSession,
    getSession: getSession,
    signIn: signIn,
    signOut: signOut,
    resetPassword: resetPassword,
    changePassword: changePassword,
    getConfig: getConfig,
    setGoogleClientId: setGoogleClientId,
    loadRemoteConfig: loadRemoteConfig,
    googleButtonState: googleButtonState,
    safeNext: safeNext,
    gateDecision: gateDecision,
    decodeIdToken: decodeIdToken,
    verifyGoogleIdToken: verifyGoogleIdToken,
    fetchJwks: fetchJwks,
    runGate: runGate
  };

  if (typeof module === 'object' && module && module.exports) module.exports = Auth;
  else root.KeelAuth = Auth;

  if (typeof document !== 'undefined') {
    try {
      if (document.documentElement && document.documentElement.getAttribute('data-auth-gate')) runGate();
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPage, { once: true });
      } else {
        initPage();
      }
    } catch (e) { /* gate and enhancements are best effort */ }
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
