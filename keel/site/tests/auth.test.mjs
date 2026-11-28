/* Local-first auth tests: sessions, password hashing, recovery, Google ID
 * token verification, honest client-ID state and the /new gate.
 * Run: node --test keel/site/tests/auth.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { webcrypto } from "node:crypto";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const Auth = require("../ui/auth.js");
const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => fs.readFileSync(path.join(SITE, relative), "utf8");
const PASSWORD = "correct horse battery 42";
const EMAIL = "elios@example.test";

async function account(password = PASSWORD) {
  const storage = Auth.memoryStorage();
  const created = await Auth.createAccount(storage, { email: EMAIL, password }, webcrypto);
  assert.equal(created.ok, true, created.error);
  return { storage, created };
}

function b64url(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

async function signedToken(overrides = {}, options = {}) {
  const { privateKey, publicKey } = await webcrypto.subtle.generateKey({
    name: "RSASSA-PKCS1-v1_5",
    modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]),
    hash: "SHA-256"
  }, true, ["sign", "verify"]);
  const jwk = await webcrypto.subtle.exportKey("jwk", publicKey);
  jwk.kid = options.kid || "test-key";
  jwk.alg = "RS256";
  jwk.use = "sig";
  const now = Math.floor(Date.now() / 1000);
  const claims = {
    iss: "https://accounts.google.com",
    aud: "client.apps.googleusercontent.com",
    exp: now + 600,
    iat: now - 10,
    email: "google@example.test",
    email_verified: true,
    ...overrides
  };
  const header = { alg: "RS256", kid: jwk.kid, typ: "JWT" };
  const input = b64url(header) + "." + b64url(claims);
  const signature = Buffer.from(await webcrypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", privateKey, Buffer.from(input)
  )).toString("base64url");
  return { token: input + "." + signature, jwks: { keys: [jwk] }, claims };
}

test("session: create, verify and expire", async () => {
  const storage = Auth.memoryStorage();
  const start = 1_700_000_000_000;
  const session = await Auth.createSession(
    storage, { email: EMAIL, method: "email" }, webcrypto, start
  );
  assert.equal(session.email, EMAIL);
  assert.equal(session.exp - session.iat, Auth.SESSION_TTL_MS);
  assert.equal(Auth.getSession(storage, start + 1000).token, session.token);

  // Expired sessions are rejected and cleared, not silently renewed.
  assert.equal(Auth.getSession(storage, session.exp + 1), null);
  assert.equal(storage.getItem(Auth.KEYS.session), null);
});

test("tampered, malformed and future sessions are rejected", async () => {
  const storage = Auth.memoryStorage();
  const now = 1_700_000_000_000;
  await Auth.createSession(storage, { email: EMAIL, method: "email" }, webcrypto, now);
  storage.setItem(Auth.KEYS.session, JSON.stringify({
    v: Auth.VERSION, token: "short", email: EMAIL,
    method: "email", iat: now, exp: now + 1000
  }));
  assert.equal(Auth.getSession(storage, now), null);

  storage.setItem(Auth.KEYS.session, "{not json");
  assert.equal(Auth.getSession(storage, now), null);

  storage.setItem(Auth.KEYS.session, JSON.stringify({
    v: Auth.VERSION, token: "abcdefghijklmnopqrstuvwx", email: EMAIL,
    method: "email", iat: now + 120000, exp: now + 200000
  }));
  assert.equal(Auth.getSession(storage, now), null);
});

test("password hashing never stores the plaintext password", async () => {
  const { storage } = await account();
  const raw = storage.getItem(Auth.KEYS.accounts);
  assert.ok(raw && !raw.includes(PASSWORD), "plaintext password must not be stored");
  const accountData = JSON.parse(raw).users[EMAIL];
  assert.equal(accountData.algo, "pbkdf2-sha256");
  assert.equal(accountData.iterations, Auth.PBKDF2_ITERATIONS);
  assert.ok(accountData.salt && accountData.hash && accountData.salt !== accountData.hash);
  assert.equal(await Auth.verifyPassword(PASSWORD, accountData, webcrypto), true);
  assert.equal(await Auth.verifyPassword("wrong-password", accountData, webcrypto), false);
});

test("wrong password is rejected and a correct one signs in", async () => {
  const { storage } = await account();
  const wrong = await Auth.signIn(storage, { email: EMAIL, password: "not-my-password" }, webcrypto);
  assert.equal(wrong.ok, false);
  assert.match(wrong.error, /incorrect/i);
  assert.equal(storage.getItem(Auth.KEYS.session), null);

  const right = await Auth.signIn(storage, { email: EMAIL, password: PASSWORD }, webcrypto);
  assert.equal(right.ok, true);
  assert.equal(right.session.method, "email");
  assert.ok(Auth.getSession(storage), "a session is created only after success");
});

test("recovery code resets the password and is shown only at signup", async () => {
  const { storage, created } = await account();
  assert.match(created.recoveryCode, /^KEEL-[0-9A-F]{4}(-[0-9A-F]{4}){3}$/);
  const raw = storage.getItem(Auth.KEYS.accounts);
  assert.ok(!raw.includes(created.recoveryCode), "recovery code must not be stored in plaintext");

  const bad = await Auth.resetPassword(storage, {
    email: EMAIL, recoveryCode: "KEEL-0000-0000-0000-0000", newPassword: "another-password"
  }, webcrypto);
  assert.equal(bad.ok, false);
  assert.match(bad.error, /does not match/i);

  const reset = await Auth.resetPassword(storage, {
    email: EMAIL, recoveryCode: created.recoveryCode, newPassword: "another-password"
  }, webcrypto);
  assert.equal(reset.ok, true);
  assert.equal((await Auth.signIn(storage, { email: EMAIL, password: PASSWORD }, webcrypto)).ok, false);
  assert.equal((await Auth.signIn(storage, { email: EMAIL, password: "another-password" }, webcrypto)).ok, true);
});

test("signed-in users can change their password", async () => {
  const { storage } = await account();
  await Auth.signIn(storage, { email: EMAIL, password: PASSWORD }, webcrypto);
  const bad = await Auth.changePassword(storage, {
    currentPassword: "wrong", newPassword: "yet-another-password"
  }, webcrypto);
  assert.equal(bad.ok, false);
  const good = await Auth.changePassword(storage, {
    currentPassword: PASSWORD, newPassword: "yet-another-password"
  }, webcrypto);
  assert.equal(good.ok, true);
  assert.equal((await Auth.signIn(storage, { email: EMAIL, password: "yet-another-password" }, webcrypto)).ok, true);
});

test("Google button is honest without a Client ID and never fakes a login", () => {
  const config = JSON.parse(read("config/auth.json"));
  assert.equal(config.googleClientId, "");
  const state = Auth.googleButtonState(config);
  assert.equal(state.configured, false);
  assert.equal(state.message, "Google sign-in needs a Client ID");
  assert.equal(state.action, "settings");

  const login = read("login.html");
  assert.match(login, /id="auth-client-id"/);
  assert.match(login, /id="auth-google-host"/);
  const script = read("ui/auth.js");
  assert.match(script, /Google sign-in needs a Client ID/);
  assert.match(script, /accounts\.google\.com\/gsi\/client/);
  assert.match(script, /verifyGoogleIdToken/);
  assert.match(script, /Apple sign-in is not available yet/);
  assert.ok(!/data-demo="google"/.test(login), "no demo-only Google button remains");
  assert.match(login, /data-auth-apple/, "the existing Apple button stays visible");
});

test("configured client ID is saved locally and rejected when malformed", () => {
  const storage = Auth.memoryStorage();
  const bad = Auth.setGoogleClientId(storage, "not a client id");
  assert.equal(bad.ok, false);
  const good = Auth.setGoogleClientId(storage, "123-abc.apps.googleusercontent.com");
  assert.equal(good.ok, true);
  assert.equal(Auth.googleButtonState(Auth.getConfig(storage)).configured, true);
  assert.ok(!storage.getItem(Auth.KEYS.settings).includes(PASSWORD));
});

test("remote config falls back honestly when unavailable", async () => {
  const remote = await Auth.loadRemoteConfig(async () => ({ ok: false }));
  assert.deepEqual(remote, { googleClientId: "" });
  const configured = await Auth.loadRemoteConfig(async () => ({
    ok: true, json: async () => ({ googleClientId: "456-xyz.apps.googleusercontent.com" })
  }));
  assert.equal(configured.googleClientId, "456-xyz.apps.googleusercontent.com");
});

test("CSP allows exactly the Google origins needed for sign-in", () => {
  const vercel = JSON.parse(read("vercel.json"));
  const header = vercel.headers.find((entry) => entry.source === "/(.*)")
    .headers.find((entry) => entry.key === "Content-Security-Policy").value;
  const directive = (name) => (header.match(new RegExp(name + " ([^;]+)")) || [])[1] || "";
  assert.ok(directive("script-src").split(/\s+/).includes("https://accounts.google.com"));
  const connect = directive("connect-src").split(/\s+/);
  assert.ok(connect.includes("https://accounts.google.com"));
  assert.ok(connect.includes("https://www.googleapis.com"));
  assert.ok(directive("frame-src").split(/\s+/).includes("https://accounts.google.com"));
  assert.equal(Auth.GOOGLE_CERTS_URL, "https://www.googleapis.com/oauth2/v3/certs");
  assert.equal(Auth.GOOGLE_GIS_URL, "https://accounts.google.com/gsi/client");
});

test("new page gate: no or expired session redirects to /login", () => {
  const storage = Auth.memoryStorage();
  const denied = Auth.gateDecision({ storage, pathname: "/new" });
  assert.equal(denied.allow, false);
  assert.equal(denied.redirect, "/login?next=%2Fnew");

  const fresh = { v: Auth.VERSION, token: "abcdefghijklmnopqrstuvwx", email: EMAIL,
    method: "email", iat: 1000, exp: 2000 };
  assert.equal(Auth.gateDecision({ session: fresh, now: 1500 }).allow, true);
  const expired = Auth.gateDecision({ session: fresh, now: 2001, storage });
  assert.equal(expired.allow, false);

  const html = read("new.html");
  assert.match(html, /data-auth-gate="new"/);
  assert.match(html, /<script src="\/ui\/auth\.js"><\/script>/);
  assert.match(html, /id="n-auth-status"/);
  assert.match(html, /id="n-account-signout"/);
});

test("safeNext only accepts same-origin absolute paths", () => {
  assert.equal(Auth.safeNext("/", "/new"), "/");
  assert.equal(Auth.safeNext("/new?x=1", "/new"), "/new?x=1");
  assert.equal(Auth.safeNext("//evil.example", "/new"), "/new");
  assert.equal(Auth.safeNext("https://evil.example", "/new"), "/new");
  assert.equal(Auth.safeNext("/new/../../etc", "/new"), "/new");
  assert.equal(Auth.safeNext("/new\r\nX: y", "/new"), "/new");
});

test("Google ID token: valid signature and claims are accepted", async () => {
  const { token, jwks } = await signedToken();
  const result = await Auth.verifyGoogleIdToken({
    idToken: token,
    clientId: "client.apps.googleusercontent.com",
    jwks,
    crypto: webcrypto
  });
  assert.equal(result.ok, true, result.error);
  assert.equal(result.claims.email, "google@example.test");
});

test("Google ID token: wrong audience, issuer, expiry or signature is rejected", async () => {
  const valid = await signedToken();
  const verify = (token, options = {}) => Auth.verifyGoogleIdToken({
    idToken: token,
    clientId: options.clientId || "client.apps.googleusercontent.com",
    jwks: options.jwks || valid.jwks,
    now: options.now,
    crypto: webcrypto
  });

  assert.match((await verify(valid.token, { clientId: "someone-else" })).error, /Client ID/);
  const wrongIssuer = await signedToken({ iss: "https://evil.example" });
  assert.match((await verify(wrongIssuer.token, { jwks: wrongIssuer.jwks })).error, /issuer/);
  const expired = await signedToken({ exp: 1 });
  assert.match((await verify(expired.token, { jwks: expired.jwks })).error, /expired/);
  const unverified = await signedToken({ email_verified: false });
  assert.match((await verify(unverified.token, { jwks: unverified.jwks })).error, /verified email/);

  const parts = valid.token.split(".");
  const tampered = parts[0] + "." + parts[1] + "." + parts[2].slice(0, -2) + "AA";
  assert.match((await verify(tampered)).error, /signature|could not be read/);
  assert.match((await verify(valid.token, { jwks: { keys: [] } })).error, /signing key/);
});
