const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');

function setup() {
  const calls = [];
  const payload = new Blob(['ZIP fixture']);
  const http = {
    interceptors: { request: { use() {} }, response: { use() {} } },
    async get(url, options) { calls.push({ url, options }); return { data: payload }; },
    async post(url, data, options) { calls.push({ url, data, options }); return { data: { zip_url: 'fixture' } }; },
  };
  const axios = { create: () => http, isAxiosError: e => Boolean(e?.isAxiosError) };
  let clicks = 0;
  const document = { body: { appendChild() {} }, createElement() { return { click() { clicks++; }, remove() {} }; } };
  const window = { setTimeout: fn => fn() };
  const source = fs.readFileSync('src/api.ts', 'utf8').replace('import.meta.env.VITE_API_URL', 'undefined');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', 'document', 'window', 'crypto', code)(
    () => axios, module, module.exports, document, window, webcrypto);
  return { api: module.exports, calls, payload, http, clicks: () => clicks };
}

async function generation(payload) {
  const digest = await webcrypto.subtle.digest('SHA-256', await payload.arrayBuffer());
  return { zip_url: 'https://other.example/api/generador/descargar/00000000-0000-0000-0000-000000000001.zip/',
    tamano_bytes: payload.size, sha256: Buffer.from(digest).toString('hex') };
}

test('POST uses the saved diagram and delivery endpoint', async () => {
  const s = setup();
  await s.api.prepareBackend(7, true, true);
  assert.equal(s.calls[0].url, '/generar-backend/');
  assert.equal(s.calls[0].data.diagrama_id, 7);
  assert.equal(s.calls[0].data.alcance, 'completo');
  assert.equal(s.calls[0].data.completar_pk, true);
  assert.equal(s.calls[0].data.autocorregir, true);
});

test('generation and validation honor the current diagram and explicit PK option', async () => {
  const s = setup();
  await s.api.prepareBackend(6, true, true, 'completo', false, false);
  await s.api.validateBackend(6, false, false);
  assert.equal(s.calls[0].data.diagrama_id, 6);
  assert.equal(s.calls[0].data.completar_pk, false);
  assert.equal(s.calls[1].data.diagrama_id, 6);
  assert.equal(s.calls[1].data.completar_pk, false);
  assert.equal(s.calls[0].data.autocorregir, false);
  assert.equal(s.calls[1].data.autocorregir, false);
});

test('download stays on authenticated API and clicks only after digest verification', async () => {
  const s = setup();
  await s.api.downloadBackend(await generation(s.payload));
  assert.equal(s.calls[0].url, '/generador/descargar/00000000-0000-0000-0000-000000000001.zip/');
  assert.equal(s.clicks(), 1);
});

test('corrupt or truncated downloads never trigger a file click', async () => {
  const s = setup();
  const record = await generation(s.payload);
  await assert.rejects(s.api.downloadBackend({ ...record, sha256: '0'.repeat(64) }), /integridad/);
  await assert.rejects(s.api.downloadBackend({ ...record, tamano_bytes: 999 }), /incompleto/);
  assert.equal(s.clicks(), 0);
});

test('JSON blob errors preserve expiration messages for retry UI', async () => {
  const s = setup();
  s.http.get = async () => { throw { isAxiosError: true, response: { data: new Blob([JSON.stringify({ error: 'El archivo expiró' })]) } }; };
  try { await s.api.downloadBackend(await generation(s.payload)); assert.fail('expected error'); }
  catch (error) { assert.equal(s.api.errorMessage(error, 'fallback'), 'El archivo expiró'); }
  assert.equal(s.clicks(), 0);
});
