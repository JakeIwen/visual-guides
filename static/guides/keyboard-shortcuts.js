/* The shared JSON schema owns the record vocabulary for browser and CLI. */
(() => {
  'use strict';
  const catalogURL = '../reference/keyboard-shortcuts.json';
  const schemaURL = '../reference/keyboard-shortcuts.schema.json';

  function validateValue(value, rule, location = 'catalog') {
    const types = {
      object: v => v !== null && typeof v === 'object' && !Array.isArray(v),
      array: Array.isArray, string: v => typeof v === 'string', integer: Number.isInteger
    };
    const fail = message => { throw new Error(`${location}: ${message}`); };
    if (rule.type && !types[rule.type](value)) fail(`expected ${rule.type}`);
    if ('const' in rule && value !== rule.const) fail('unsupported value');
    if (rule.enum && !rule.enum.includes(value)) fail(`expected one of ${rule.enum.join(', ')}`);
    if (rule.type === 'object') {
      for (const key of rule.required || []) if (!(key in value)) fail(`missing ${key}`);
      for (const [key, child] of Object.entries(value)) {
        if (!Object.prototype.hasOwnProperty.call(rule.properties, key)) fail(`unknown field ${key}`);
        validateValue(child, rule.properties[key], `${location}.${key}`);
      }
    } else if (rule.type === 'array') {
      if (value.length < (rule.minItems || 0)) fail('must not be empty');
      value.forEach((child, index) => validateValue(child, rule.items, `${location}[${index}]`));
    } else if (rule.type === 'string') {
      if (value.trim().length < (rule.minLength || 0)) fail('must not be blank');
      if (rule.pattern && !(new RegExp(rule.pattern)).test(value)) fail('invalid format');
      if (/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(value)) fail('control/format characters are not allowed');
      if (rule.format === 'date') {
        const date = new Date(value + 'T00:00:00Z');
        if (value.startsWith('0000') || !Number.isFinite(date.getTime()) ||
            date.toISOString().slice(0, 10) !== value) fail('invalid date');
      }
    }
  }

  function validateCatalog(catalog, schema) {
    validateValue(catalog, schema);
    const ids = new Set();
    for (const entry of catalog.entries) {
      if (ids.has(entry.id)) throw new Error(`Duplicate mapping id: ${entry.id}`);
      ids.add(entry.id);
      if (entry.status === 'conditional' && !entry.conditions.trim()) {
        throw new Error(`${entry.id}: conditional mapping needs conditions`);
      }
    }
    return catalog;
  }

  function selectEntries(catalog, {search = '', includeDisabled = false, provider = '', scope = ''} = {}) {
    const query = search.trim().toLowerCase();
    return catalog.entries.filter(entry =>
      (includeDisabled || entry.status !== 'disabled') &&
      (!provider || entry.provider === provider) && (!scope || entry.scope === scope) &&
      (!query || Object.values(entry).flat().concat(entry.keys.length > 1 ? [entry.keys.join('')] : [])
        .join(' ').toLowerCase().includes(query)));
  }

  function element(doc, tag, text, className) {
    const node = doc.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function renderEntry(doc, entry) {
    const row = element(doc, 'li', undefined, entry.status === 'disabled' ? 'shortcut disabled' : 'shortcut');
    row.id = `mapping-${entry.id}`;
    row.dataset.mappingId = entry.id;
    const keys = element(doc, 'div', undefined, 'shortcut-keys');
    keys.setAttribute('role', 'group');
    keys.setAttribute('aria-label', entry.keys.join(' then '));
    entry.keys.forEach((key, index) => {
      if (index) keys.append(element(doc, 'span', '→'));
      keys.append(element(doc, 'kbd', key));
    });
    const body = element(doc, 'div');
    body.append(element(doc, 'h2', entry.action));
    const statusStyle = {enabled: 'tag ok', conditional: 'tag warn', disabled: 'tag'};
    body.append(element(doc, 'span', entry.status, statusStyle[entry.status]));
    body.append(element(doc, 'p', `${entry.provider} · ${entry.scope}`, 'small'));
    if (entry.conditions) body.append(element(doc, 'p', `Conditions: ${entry.conditions}`));
    if (entry.limitations) body.append(element(doc, 'p', `Limitations: ${entry.limitations}`));
    const sources = element(doc, 'details');
    sources.append(element(doc, 'summary', `Source · verified ${entry.verified}`));
    const list = element(doc, 'ul');
    for (const source of entry.sources) {
      const item = element(doc, 'li');
      item.append(element(doc, 'code', source));
      list.append(item);
    }
    sources.append(list);
    body.append(sources);
    row.append(keys, body);
    return row;
  }

  function mount(doc, catalog) {
    const get = id => doc.getElementById(id);
    for (const field of ['provider', 'scope']) {
      const values = [...new Set(catalog.entries.map(entry => entry[field]))].sort();
      for (const value of values) {
        const option = element(doc, 'option', value);
        option.value = value;
        get(field).append(option);
      }
    }
    get('catalog-notes').replaceChildren(...catalog.notes.map(note => element(doc, 'p', note)));
    const update = () => {
      const entries = selectEntries(catalog, {
        search: get('search').value, provider: get('provider').value, scope: get('scope').value,
        includeDisabled: get('include-disabled').checked
      });
      get('shortcuts').replaceChildren(...entries.map(entry => renderEntry(doc, entry)));
      get('result-status').textContent = entries.length
        ? `${entries.length} of ${catalog.entries.length} mappings. Disabled mappings ${get('include-disabled').checked ? 'included' : 'hidden'}.`
        : catalog.entries.length ? `No matching shortcuts. ${get('include-disabled').checked ? 'Broaden the filters.' : 'Broaden the filters or include disabled mappings.'}`
          : 'No verified mappings are listed yet. Open Coverage and limitations.';
    };
    get('filters').addEventListener('submit', event => event.preventDefault());
    get('filters').addEventListener('input', update);
    get('filters').addEventListener('reset', () => setTimeout(update, 0));
    for (const control of get('filters').elements) control.disabled = false;
    update();
    return update;
  }

  async function load(doc, fetcher) {
    const status = doc.getElementById('result-status');
    const retry = doc.getElementById('retry');
    retry.hidden = true;
    status.textContent = 'Loading keyboard reference…';
    try {
      const read = async url => {
        const response = await fetcher(url, {cache: 'no-cache'});
        if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
        return response.json();
      };
      const [catalog, schema] = await Promise.all([read(catalogURL), read(schemaURL)]);
      mount(doc, validateCatalog(catalog, schema));
    } catch (error) {
      status.textContent = `Keyboard reference unavailable: ${error.message}. Retry, or use the terminal command below.`;
      retry.hidden = false;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {validateCatalog, selectEntries, renderEntry, mount, load};
  }
  if (typeof document !== 'undefined') {
    document.getElementById('retry').addEventListener('click', () => load(document, fetch));
    load(document, fetch);
  }
})();
