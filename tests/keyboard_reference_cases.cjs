'use strict';
// Minimal DOM exercises actual element creation and filter events without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const guide = require(path.join(root, 'static/guides/keyboard-shortcuts.js'));
const schema = JSON.parse(fs.readFileSync(path.join(root, 'static/reference/keyboard-shortcuts.schema.json')));
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/keyboard-shortcuts.json')));

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.handlers = {};
    this.value = '';
    this.checked = false;
    this.disabled = true;
    this.text = '';
  }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(_) { throw new Error('Catalog data must never be parsed as HTML'); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.text = ''; this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(type, handler) { this.handlers[type] = handler; }
}

function documentFixture() {
  const ids = ['filters', 'search', 'provider', 'scope', 'include-disabled', 'reset',
    'result-status', 'retry', 'catalog-notes', 'shortcuts'];
  const nodes = Object.fromEntries(ids.map(id => [id, new Element('div')]));
  nodes.filters.elements = ['search', 'provider', 'scope', 'include-disabled', 'reset'].map(id => nodes[id]);
  return {nodes, createElement: tag => new Element(tag), getElementById: id => nodes[id]};
}

function filterCases() {
  const requests = [{}, {includeDisabled: true}, {search: 'CMD+c'}, {search: 'fixture-shell', includeDisabled: true},
    {provider: 'Test BTT'}, {scope: 'Test terminal', includeDisabled: true}, {search: 'no match'},
    {search: ' mouse '}, {provider: 'Test zsh'}, {search: 'ab'}, {search: 'a b'}];
  return requests.map(options => guide.selectEntries(fixture, options).map(entry => entry.id));
}

function productionCases() {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'static/reference/keyboard-shortcuts.json')));
  guide.validateCatalog(catalog, schema);
  assert.deepEqual(guide.selectEntries(catalog, {search: 'cosnt'}).map(entry => entry.id),
    ['btt-f8df2b59-10f6-45ea-8c61-8d216dba2593']);
  assert.ok(guide.selectEntries(catalog, {search: 'Cmd+X', includeDisabled: true})
    .some(entry => entry.id === 'terminal-clipboard-cut'));
}

function validationCases() {
  const cases = [
    value => { value.entries.push(value.entries[0]); },
    value => { value.entries[0].status = 'planned'; },
    value => { value.entries[0].verified = '2026-02-30'; },
    value => { value.entries[0].keys = []; },
    value => { value.entries[0].conditions = ''; },
    value => { value.entries[0].action = '\x1b[31m'; },
    value => { value.entries[0].action = ' '; },
    value => { value.entries[0].private_payload = 'not allowed'; },
    value => { delete value.entries[0].sources; },
    value => { value.schema_version = true; }
  ];
  for (const modify of cases) {
    const value = JSON.parse(JSON.stringify(fixture));
    modify(value);
    assert.throws(() => guide.validateCatalog(value, schema));
  }
}

function renderCases() {
  const doc = documentFixture();
  const catalog = {...fixture, notes: [...fixture.notes, 'Additional coverage caveat.']};
  guide.mount(doc, guide.validateCatalog(catalog, schema));
  assert.deepEqual(doc.nodes['catalog-notes'].children.map(note => note.textContent), catalog.notes);
  assert.deepEqual(doc.nodes.shortcuts.children.map(row => row.dataset.mappingId), ['test-copy', 'test-sequence']);
  assert.match(doc.nodes.shortcuts.textContent, /<script>test-only text<\/script>/);
  assert.match(doc.nodes.shortcuts.textContent, /Conditions: Editable test field/);
  assert.match(doc.nodes.shortcuts.textContent, /fixture-copy.js/);
  assert.match(doc.nodes.shortcuts.textContent, /verified 2026-11-04/);
  const sequence = doc.nodes.shortcuts.children[1].children[0];
  assert.deepEqual(sequence.children.map(child => child.tagName), ['kbd', 'span', 'kbd']);
  assert.equal(sequence.attributes['aria-label'], 'a then b');
  assert.equal(sequence.attributes.role, 'group');
  assert.equal(doc.nodes.shortcuts.children[0].children[1].children[1].className, 'tag warn');
  assert.equal(doc.nodes.shortcuts.children[1].children[1].children[1].className, 'tag ok');
  doc.nodes['include-disabled'].checked = true;
  doc.nodes.filters.handlers.input();
  assert.equal(doc.nodes.shortcuts.children.length, 3);
  assert.equal(doc.nodes.shortcuts.children[2].className, 'shortcut disabled');
  doc.nodes.scope.value = 'Test terminal';
  doc.nodes.filters.handlers.input();
  assert.deepEqual(doc.nodes.shortcuts.children.map(row => row.dataset.mappingId), ['test-disabled']);
  doc.nodes.search.value = 'no match';
  doc.nodes.filters.handlers.input();
  assert.equal(doc.nodes.shortcuts.children.length, 0);
  assert.match(doc.nodes['result-status'].textContent, /No matching/);
  assert.doesNotMatch(doc.nodes['result-status'].textContent, /include disabled/);
  doc.nodes['include-disabled'].checked = false;
  doc.nodes.filters.handlers.input();
  assert.match(doc.nodes['result-status'].textContent, /include disabled/);
  assert.ok(doc.nodes.filters.elements.every(control => !control.disabled));
}

async function loadCases() {
  const doc = documentFixture();
  await guide.load(doc, async () => ({ok: false, status: 404}));
  assert.match(doc.nodes['result-status'].textContent, /unavailable.*404/);
  assert.equal(doc.nodes.retry.hidden, false);
  assert.ok(doc.nodes.filters.elements.every(control => control.disabled));
  const fetcher = async url => new Response(Buffer.from('﻿' + JSON.stringify(
    url.endsWith('.schema.json') ? schema : fixture), 'utf8'));
  await guide.load(doc, fetcher);
  assert.equal(doc.nodes.retry.hidden, true);
  assert.equal(doc.nodes.shortcuts.children.length, 2);
  const empty = {schema_version: 1, notes: [], entries: []};
  const fresh = documentFixture();
  guide.mount(fresh, empty);
  assert.match(fresh.nodes['result-status'].textContent, /No verified mappings.*Coverage and limitations/);
}

async function main() {
  if (process.argv.includes('--validate-catalogs')) {
    const catalogs = JSON.parse(fs.readFileSync(0, 'utf8'));
    const results = catalogs.map(catalog => {
      try { guide.validateCatalog(catalog, schema); return true; }
      catch (_) { return false; }
    });
    process.stdout.write(JSON.stringify(results));
    return;
  }
  validationCases();
  productionCases();
  renderCases();
  await loadCases();
  process.stdout.write(JSON.stringify(filterCases()));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
