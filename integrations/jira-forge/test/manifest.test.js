import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import yaml from 'js-yaml';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

const require = createRequire(import.meta.url);

test('manifest.yml is valid against the @forge/manifest schema', () => {
  const schema = require('@forge/manifest/out/schema/manifest-schema.json');
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);
  const validate = ajv.compile(schema);
  const manifest = yaml.load(readFileSync(new URL('../manifest.yml', import.meta.url), 'utf8'));
  assert.ok(validate(manifest), JSON.stringify(validate.errors, null, 1));
});

test('every function handler referenced by the manifest is exported', async () => {
  const manifest = yaml.load(readFileSync(new URL('../manifest.yml', import.meta.url), 'utf8'));
  const src = readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
  for (const fn of manifest.modules.function) {
    const name = fn.handler.split('.')[1];
    assert.match(src, new RegExp(`export (const|async function|function) ${name}\\b`), `${fn.handler} not exported`);
  }
});
