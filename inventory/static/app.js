'use strict';

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 25;
let report = { balances: [], runs: [], rejects: [], reconciliation: [], metrics: {} };
let filteredBalances = [];
let page = 0;
let loading = false;
let csrfToken = null;
let csrfPromise = null;
let authRedirecting = false;
let mutationBusy = false;
let impactRunId = '';
let impactOffset = 0;
let impactTotal = 0;
let impactRequest = 0;
const IMPACT_PAGE_SIZE = 100;
const MAX_CSV_BYTES = 10 * 1024 * 1024;
const selectedFiles = { movement: null, items: null, locations: null };

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function display(value) {
  if (value === null || value === undefined || value === '') return '—';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}
function number(value) { return new Intl.NumberFormat().format(Number(value || 0)); }
function negative(value) { return /^-/.test(String(value)) && Number(value) !== 0; }
function cell(row, value, className = '') {
  const td = element('td', className, display(value));
  row.append(td);
  return td;
}
function emptyTable(bodyId, columns, message) {
  const row = element('tr');
  const td = element('td', 'empty-cell', message);
  td.colSpan = columns;
  row.append(td);
  $(bodyId).replaceChildren(row);
}
function badge(value, kind) { return element('span', `badge${kind ? ' ' + kind : ''}`, value); }
function addPairCell(row, primary, secondary, className = '') {
  const td = element('td', className);
  td.append(element('span', 'cell-main', display(primary)), element('span', 'cell-sub', display(secondary)));
  row.append(td);
  return td;
}
function fillOptions(id, values, label) {
  const select = $(id);
  const current = select.value;
  const first = element('option', '', label);
  first.value = '';
  const nodes = [first];
  [...new Set(values)].filter((v) => v !== null && v !== undefined).sort().forEach((value) => {
    const option = element('option', '', String(value));
    option.value = String(value);
    nodes.push(option);
  });
  select.replaceChildren(...nodes);
  select.value = nodes.some((o) => o.value === current) ? current : '';
}
function renderMetrics() {
  const m = report.metrics || {};
  const dates = [...new Set(report.balances.map((r) => r.balance_date))].sort();
  const rejected = report.runs.reduce((total, r) => total + Number(r.rejected_count || 0), 0);
  const negativeDays = m.negative_balance_days ?? report.balances.filter((r) => negative(r.closing)).length;
  $('metric-events').textContent = number(m.current_events ?? report.movements?.length ?? 0);
  $('metric-balances').textContent = number(m.daily_rows ?? report.balances.length);
  $('metric-rejects').textContent = number(rejected);
  $('metric-rejects').classList.toggle('warning-number', rejected > 0);
  $('metric-negative').textContent = number(negativeDays);
  $('metric-negative').classList.toggle('danger-number', negativeDays > 0);
  $('metric-range').textContent = dates.length ? `${dates[0]} → ${dates[dates.length - 1]}` : 'No dates published';
  $('version-count').textContent = `${number(m.history_versions || 0)} archived versions`;
  $('reject-tab-count').textContent = number(rejected);

  const failedChecks = report.reconciliation.filter((r) => r.passed === false).length;
  const failedRuns = report.runs.filter((r) => r.status === 'failed').length;
  const warnings = [];
  if (failedChecks) warnings.push(`${number(failedChecks)} reconciliation check${failedChecks === 1 ? '' : 's'} failed`);
  if (rejected) warnings.push(`${number(rejected)} rejected source row${rejected === 1 ? '' : 's'}`);
  if (Number(negativeDays)) warnings.push(`${number(negativeDays)} negative balance day${Number(negativeDays) === 1 ? '' : 's'}`);
  if (failedRuns) warnings.push(`${number(failedRuns)} failed ingestion run${failedRuns === 1 ? '' : 's'} in audit history`);
  $('status').className = `status-bar${failedChecks ? ' error' : warnings.length ? ' warning' : ''}`;
  if (warnings.length) {
    $('status-label').textContent = 'Review required';
    $('status-text').textContent = warnings.join(' · ');
  } else if (!report.runs.length) {
    $('status-label').textContent = 'Ready';
    $('status-text').textContent = 'Ready for ingestion · no pipeline runs recorded yet';
  } else {
    $('status-label').textContent = 'Up to date';
    const checks = report.reconciliation.length;
    $('status-text').textContent = checks ? `Published ledger · ${checks} reconciliation checks passed` : 'Published ledger · no reconciliation checks available';
  }
}
function applyFilters() {
  const item = $('item-filter').value;
  const location = $('location-filter').value;
  const from = $('from-filter').value;
  const through = $('through-filter').value;
  filteredBalances = report.balances.filter((row) =>
    (!item || String(row.item_id) === item) &&
    (!location || String(row.location_id) === location) &&
    (!from || row.balance_date >= from) &&
    (!through || row.balance_date <= through)
  ).sort((a, b) => String(a.balance_date).localeCompare(String(b.balance_date)) || String(a.item_id).localeCompare(String(b.item_id)) || String(a.location_id).localeCompare(String(b.location_id)));
  page = Math.min(page, Math.max(0, Math.ceil(filteredBalances.length / PAGE_SIZE) - 1));
  renderBalances();
  renderTrend();
}
function renderBalances() {
  const rows = filteredBalances.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  if (!rows.length) {
    emptyTable('balances-body', 9, report.balances.length ? 'No balances match these filters. Adjust the dates or reset the view.' : 'No published balances yet. Ingest the sample data with the CLI, then refresh.');
  } else {
    $('balances-body').replaceChildren(...rows.map((record) => {
      const row = element('tr');
      cell(row, record.balance_date);
      addPairCell(row, record.item_id, record.location_id);
      ['opening', 'receipts', 'issues', 'transfers_in', 'transfers_out', 'adjustments'].forEach((key) => cell(row, record[key], 'numeric'));
      const closing = cell(row, record.closing, `numeric closing-cell${negative(record.closing) ? ' negative-cell' : ''}`);
      if (negative(record.closing)) closing.title = 'Negative inventory: review stock availability';
      return row;
    }));
  }
  $('balance-count').textContent = `${number(filteredBalances.length)} daily balance row${filteredBalances.length === 1 ? '' : 's'}`;
  const start = filteredBalances.length ? page * PAGE_SIZE + 1 : 0;
  const end = Math.min((page + 1) * PAGE_SIZE, filteredBalances.length);
  $('pagination-summary').textContent = `Showing ${number(start)}–${number(end)} of ${number(filteredBalances.length)}`;
  $('previous-page').disabled = page === 0;
  $('next-page').disabled = (page + 1) * PAGE_SIZE >= filteredBalances.length;
  $('download').disabled = filteredBalances.length === 0;
}
function svgElement(tag, attributes, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderTrend() {
  // Do not sum unlike units. A trend is available only at one item/location grain.
  const keys = new Set(filteredBalances.map((r) => JSON.stringify([r.item_id, r.location_id])));
  $('trend').hidden = filteredBalances.length === 0 || keys.size !== 1;
  if ($('trend').hidden) return;
  const values = filteredBalances.map((r) => Number(r.closing));
  const min = values.reduce((a, value) => Math.min(a, value), 0);
  const max = values.reduce((a, value) => Math.max(a, value), 0);
  const span = max - min || 1;
  const x = (index) => 16 + (values.length === 1 ? 0.5 : index / (values.length - 1)) * 608;
  const y = (value) => 92 - (value - min) / span * 74;
  const points = values.map((value, i) => `${x(i).toFixed(2)},${y(value).toFixed(2)}`);
  const zero = y(0);
  const first = filteredBalances[0];
  const last = filteredBalances[filteredBalances.length - 1];
  $('trend-title').textContent = `${first.item_id} / ${first.location_id}`;
  const title = svgElement('title', { id: 'chart-title' }, `Closing stock for ${first.item_id} at ${first.location_id}: ${first.balance_date}, ${first.closing}, through ${last.balance_date}, ${last.closing}. Chart is approximate; the table shows exact quantities.`);
  const baseline = svgElement('line', { x1: 10, x2: 630, y1: zero, y2: zero, class: 'chart-baseline' });
  const area = svgElement('polygon', { points: `${x(0)},${zero} ${points.join(' ')} ${x(values.length - 1)},${zero}`, class: 'chart-area' });
  const line = svgElement('polyline', { points: points.join(' '), class: 'chart-line' });
  const dot = svgElement('circle', { cx: x(values.length - 1), cy: y(values[values.length - 1]), r: 4, class: 'chart-dot' });
  const dateStart = svgElement('text', { x: 12, y: 116, class: 'chart-label' }, first.balance_date);
  const dateEnd = svgElement('text', { x: 628, y: 116, 'text-anchor': 'end', class: 'chart-label' }, last.balance_date);
  $('trend-chart').replaceChildren(title, baseline, area, line, dot, dateStart, dateEnd);
}
function renderReconciliation() {
  const checks = report.reconciliation;
  if (!checks.length) return emptyTable('reconciliation-body', 6, 'No reconciliation checks available. Ingest data and refresh.');
  $('reconciliation-body').replaceChildren(...checks.map((check) => {
    const row = element('tr');
    cell(row, String(check.check_name || 'Unnamed check').replaceAll('_', ' '));
    ['expected', 'actual', 'variance'].forEach((key) => cell(row, check[key], 'numeric'));
    const result = cell(row, '');
    result.replaceChildren(badge(check.passed === true ? 'Passed' : check.passed === false ? 'Failed' : 'Unknown', check.passed === false ? 'failed' : check.passed === true ? '' : 'warning'));
    cell(row, check.details, 'wrap-cell');
    return row;
  }));
}
function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
function renderRuns() {
  if (!report.runs.length) return emptyTable('runs-body', 9, 'No ingestion runs recorded yet.');
  $('runs-body').replaceChildren(...[...report.runs].sort((a, b) => String(b.started_at).localeCompare(String(a.started_at))).map((run) => {
    const row = element('tr');
    const source = String(run.source_file || '').split(/[\\/]/).pop();
    const id = String(run.run_id || '');
    const td = addPairCell(row, id.length > 18 ? id.slice(0, 15) + '…' : id, source, 'run-id');
    td.title = id;
    const impactButton = element('button', 'run-impact-link', 'View balance impact');
    impactButton.type = 'button';
    impactButton.addEventListener('click', () => openChangeRun(id));
    td.append(impactButton);
    cell(row, formatTime(run.started_at));
    const state = cell(row, '');
    const failed = run.status === 'failed';
    const warning = Number(run.rejected_count) > 0 || String(run.status).includes('reject');
    state.replaceChildren(badge(String(run.status || 'unknown').replaceAll('_', ' '), failed ? 'failed' : warning ? 'warning' : ''));
    if (run.error) {
      state.title = String(run.error);
      const explanation = element('details', 'run-error');
      explanation.append(element('summary', '', 'Failure reason'), element('div', 'run-error-text', String(run.error)));
      state.append(explanation);
    }
    ['input_count', 'accepted_count', 'duplicate_count', 'rejected_count', 'rolled_back_count'].forEach((key) => cell(row, number(run[key]), 'numeric'));
    cell(row, run.duration_ms === undefined ? '—' : `${number(Math.round(Number(run.duration_ms)))} ms`, 'numeric');
    return row;
  }));
}
function renderRejects() {
  const rejects = report.rejects || [];
  const total = report.runs.reduce((sum, r) => sum + Number(r.rejected_count || 0), 0);
  $('reject-note').textContent = total > rejects.length ? `Showing ${number(rejects.length)} of ${number(total)} rejected rows. Query or export the database for the full source audit.` : `${number(rejects.length)} quarantined source row${rejects.length === 1 ? '' : 's'} shown.`;
  if (!rejects.length) {
    $('reject-list').replaceChildren(element('p', 'empty-cell', 'No rejected records in this report.'));
    return;
  }
  $('reject-list').replaceChildren(...rejects.map((record) => {
    const details = element('details', 'reject-row');
    const summary = element('summary');
    const text = element('div');
    text.append(element('div', 'reject-reason', display(record.reason)), element('div', 'reject-source', `${display(record.source_file)} · row ${display(record.row_number)} · run ${display(record.run_id)}`));
    summary.append(text);
    let raw = record.raw_json ?? record.raw_record ?? '';
    if (typeof raw === 'string') {
      try { raw = JSON.stringify(JSON.parse(raw), null, 2); } catch (_) { /* Preserve malformed input verbatim. */ }
    } else { raw = JSON.stringify(raw, null, 2); }
    details.append(summary, element('pre', '', raw));
    return details;
  }));
}
function renderMovements() {
  const hasMovements = Array.isArray(report.movements);
  $('tab-movements').hidden = !hasMovements;
  if (!hasMovements) return;
  const records = report.movements;
  const shown = records.slice(0, 2000);
  $('movement-note').textContent = `Showing ${number(shown.length)} of ${number(report.metrics?.history_versions ?? records.length)} archived movement versions. The report may cap displayed history; the CSV export contains every version.`;
  if (!shown.length) return emptyTable('movements-body', 9, 'No source movement records.');
  $('movements-body').replaceChildren(...shown.map((record) => {
    const row = element('tr');
    ['event_id', 'revision', 'effective_date', 'movement_type', 'item_id', 'location_id', 'to_location_id'].forEach((key) => cell(row, record[key]));
    cell(row, record.quantity ?? (record.quantity_milli === undefined ? '—' : (Number(record.quantity_milli) / 1000).toFixed(3)), 'numeric');
    const isVoid = record.is_void === true || record.is_void === 1 || record.is_void === 'true';
    const isCurrent = record.is_current === true || record.is_current === 1;
    const state = cell(row, '');
    state.replaceChildren(badge(record.is_current === undefined ? (isVoid ? 'Voided' : 'Recorded') : !isCurrent ? (isVoid ? 'Superseded · void' : 'Superseded') : isVoid ? 'Voided' : 'Current', isVoid ? 'warning' : ''));
    return row;
  }));
}
function renderAll() {
  renderMetrics();
  fillOptions('item-filter', report.balances.map((r) => r.item_id), 'All items');
  fillOptions('location-filter', report.balances.map((r) => r.location_id), 'All locations');
  applyFilters();
  renderReconciliation();
  renderRuns();
  renderRejects();
  renderMovements();
  renderRunChooser();
  renderDemoExamples();
}
// Report request queue: begin
function createReportLoader(read, onBusyChange = () => {}) {
  let tail = null;
  return function request(options = {}) {
    if (tail && options.afterMutation !== true) return tail;
    const prior = tail;
    if (!prior) onBusyChange(true);
    // Register the new tail now, including when the prior read is settling.
    // Every mutation gets a read started after its predecessor, even on failure.
    const work = prior ? prior.catch(() => {}).then(() => read()) : Promise.resolve().then(() => read());
    let next;
    next = work.finally(() => {
      if (tail === next) {
        tail = null;
        onBusyChange(false);
      }
    });
    tail = next;
    return next;
  };
}
// Report request queue: end
const requestReport = createReportLoader(readReport, (busy) => {
  loading = busy;
  $('refresh').disabled = busy;
  if (busy) $('refresh').setAttribute('aria-busy', 'true');
  else $('refresh').removeAttribute('aria-busy');
});
function loadData(options = {}) { return requestReport(options); }
async function readReport() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch('/api/report', { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
    requireAuthenticatedResponse(response);
    if (!response.ok) throw new Error(`Report request failed (HTTP ${response.status}).`);
    const next = await response.json();
    if (next.error) throw new Error(next.error);
    ['balances', 'runs', 'rejects', 'reconciliation'].forEach((key) => { if (!Array.isArray(next[key])) throw new Error(`Invalid report: missing ${key} list.`); });
    report = next;
    $('error').hidden = true;
    renderAll();
    const now = new Date();
    $('refreshed-at').dateTime = now.toISOString();
    $('refreshed-at').textContent = `Refreshed ${now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
  } catch (error) {
    if (error.authenticationRequired) return;
    $('error').hidden = false;
    $('error').textContent = `Could not refresh data. ${error.name === 'AbortError' ? 'The request timed out.' : error.message} Verify that the local server is running, then retry. Previously loaded data, if any, remains visible.`;
    $('status').className = 'status-bar error';
    $('status-label').textContent = 'Connection unavailable';
    $('status-text').textContent = 'Connection unavailable · displayed data may be stale';
  } finally {
    clearTimeout(timeout);
  }
}
function selectTab(tab, focus = false) {
  document.querySelectorAll('[role=tab]').forEach((button) => {
    const selected = button === tab;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(button.getAttribute('aria-controls')).hidden = !selected;
  });
  if (focus) tab.focus();
  if (tab.id === 'tab-changes' && impactRunId) loadChanges();
}
function exportView() {
  const fields = ['balance_date', 'item_id', 'location_id', 'opening', 'receipts', 'issues', 'transfers_in', 'transfers_out', 'adjustments', 'closing'];
  const quote = (value, field) => {
    let text = String(value ?? '');
    // IDs are source-controlled strings: prevent spreadsheet formula interpretation.
    if (['item_id', 'location_id'].includes(field) && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const text = [fields.join(','), ...filteredBalances.map((row) => fields.map((field) => quote(row[field], field)).join(','))].join('\r\n') + '\r\n';
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
  const link = element('a');
  link.href = url;
  link.download = 'inventory-balances.csv';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('refresh').addEventListener('click', () => { loadData(); loadShowcase(); loadCatalogs(); });
$('filters').addEventListener('submit', (event) => event.preventDefault());
['item-filter', 'location-filter', 'from-filter', 'through-filter'].forEach((id) => $(id).addEventListener('change', () => { exitBalanceExample(false); page = 0; applyFilters(); }));
$('reset-filters').addEventListener('click', () => { exitBalanceExample(false); $('filters').reset(); page = 0; applyFilters(); });
$('previous-page').addEventListener('click', () => { page = Math.max(0, page - 1); renderBalances(); });
$('next-page').addEventListener('click', () => { page += 1; renderBalances(); });
$('download').addEventListener('click', exportView);
document.querySelectorAll('[role=tab]').forEach((tab) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', (event) => {
    const tabs = [...document.querySelectorAll('[role=tab]')].filter((button) => !button.hidden);
    const index = tabs.indexOf(tab);
    let target;
    if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
    if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
    if (event.key === 'Home') target = tabs[0];
    if (event.key === 'End') target = tabs[tabs.length - 1];
    if (target) { event.preventDefault(); selectTab(target, true); }
  });
});

function requireAuthenticatedResponse(response) {
  if (response.status === 401) {
    csrfToken = null;
    if (!authRedirecting) {
      authRedirecting = true;
      window.location.replace('/login');
    }
    const error = new Error('Your session has ended. Sign in again.');
    error.authenticationRequired = true;
    throw error;
  }
  return response;
}
async function getJSON(path) {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
  requireAuthenticatedResponse(response);
  let data;
  try { data = await response.json(); } catch (_) { throw new Error(`The local server returned an invalid response (HTTP ${response.status}).`); }
  if (!response.ok || data.error) {
    const error = new Error(data.error || `Request failed (HTTP ${response.status}).`);
    error.runId = data.run_id;
    throw error;
  }
  return data;
}
function evidenceText(id, value, available) {
  $(id).textContent = value;
  $(id).classList.toggle('unavailable', !available);
}
async function loadShowcase() {
  try {
    const data = await getJSON('/api/showcase');
    $('showcase-version').textContent = data.version ? `v${data.version}` : 'Version unavailable';
    const features = Array.isArray(data.features) ? data.features : [];
    $('feature-grid').replaceChildren(...(features.length ? features.map((feature, index) => {
      const card = element('article', 'feature-card');
      const top = element('div', 'feature-top');
      top.append(element('span', 'feature-number', String(index + 1).padStart(2, '0')), element('h3', '', display(feature.title)));
      card.append(top, element('p', '', display(feature.description)), element('span', 'feature-status', feature.status || 'Status unavailable'));
      return card;
    }) : [element('p', 'evidence-unavailable', 'Capability details are unavailable. You can still use the local workspace.')]));
    const evidence = data.evidence || {};
    const tests = evidence.tests || {};
    const testAvailable = tests.count !== null && tests.count !== undefined && tests.passed !== undefined;
    let testText = 'Unavailable';
    if (testAvailable && tests.passed === true) testText = `${number(tests.count)} tests passing`;
    else if (testAvailable && typeof tests.passed === 'number') testText = `${number(tests.passed)} / ${number(tests.count)} passing`;
    else if (testAvailable) testText = 'Review test evidence';
    evidenceText('showcase-tests', testText, testAvailable);
    $('showcase-test-scope').textContent = tests.scope || 'No recorded automated test evidence is available.';
    const benchmark = evidence.benchmark || {};
    const benchmarkAvailable = benchmark.physical_rows !== null && benchmark.physical_rows !== undefined && benchmark.seconds !== null && benchmark.seconds !== undefined && Number.isFinite(Number(benchmark.seconds));
    evidenceText('showcase-benchmark', benchmarkAvailable ? `${number(benchmark.physical_rows)} rows · ${Number(benchmark.seconds).toFixed(2)} s` : 'Unavailable', benchmarkAvailable);
    $('showcase-benchmark-scope').textContent = benchmarkAvailable ? 'Recorded synthetic batch · separate from the open ledger' : 'No recorded benchmark result is available.';
    const generator = evidence.generator || {};
    const generatorAvailable = Object.keys(generator).length > 0 && generator.available !== false;
    const seed = generator.seed ?? generator.fixed_seed;
    evidenceText('showcase-generator', generatorAvailable ? (seed === undefined ? 'Available locally' : `Fixed seed ${seed}`) : 'Unavailable', generatorAvailable);
    const coverage = generator.normal_coverage || {};
    const catalogSize = generator.catalog_items;
    const sourceLocations = generator.catalog_locations;
    $('showcase-generator-scope').textContent = generator.scope || generator.description || (generatorAvailable ? [catalogSize === undefined ? null : `${number(catalogSize)} catalog items`, sourceLocations === undefined ? null : `${number(sourceLocations)} locations`, generator.physical_rows === undefined ? null : `${number(generator.physical_rows)} physical rows`].filter(Boolean).join(' · ') || 'Configurable synthetic CSV batches · documented CLI' : 'No recorded generator details are available.');
    $('generator-evidence').hidden = Object.keys(coverage).length === 0;
    const coverageParts = [];
    if (coverage.items_with_all_movement_types !== undefined) coverageParts.push(`${number(coverage.items_with_all_movement_types)}${catalogSize === undefined ? '' : '/' + number(catalogSize)} items cover every movement type`);
    if (coverage.items_with_all_source_locations !== undefined) coverageParts.push(`${number(coverage.items_with_all_source_locations)}${catalogSize === undefined ? '' : '/' + number(catalogSize)} items cover all source locations`);
    if (coverage.distinct_item_source_locations !== undefined) coverageParts.push(`${number(coverage.distinct_item_source_locations)} distinct item / source-location pairs`);
    if (coverage.adjustment_signs !== undefined) {
      const signs = coverage.adjustment_signs;
      if (signs && !Array.isArray(signs) && typeof signs === 'object' && signs.positive !== undefined && signs.negative !== undefined) {
        coverageParts.push(`${number(signs.positive)} positive and ${number(signs.negative)} negative adjustments`);
      } else {
        coverageParts.push(`Adjustment signs: ${Array.isArray(signs) ? signs.join(', ') : display(signs)}`);
      }
    }
    $('generator-coverage').textContent = coverageParts.join(' · ') || 'Coverage detail was supplied without summary fields.';
    const counts = generator.counts || {};
    $('generator-counts').textContent = Object.keys(counts).map((key) => `${key.replaceAll('_', ' ')}: ${number(counts[key])}`).join(' · ');
    const detailFields = [
      ['Physical rows', benchmark.physical_rows], ['Accepted / duplicates / rejected', benchmarkAvailable ? `${display(benchmark.accepted)} / ${display(benchmark.duplicates)} / ${display(benchmark.rejected)}` : null],
      ['Published daily rows', benchmark.daily_rows], ['Python', benchmark.python], ['System / machine', [benchmark.system, benchmark.machine].filter(Boolean).join(' / ')],
      ['Random seed', benchmark.seed], ['Measured at', benchmark.measured_at], ['Measurement scope', benchmark.scope],
    ];
    const details = [];
    detailFields.forEach(([label, value]) => { details.push(element('dt', '', label), element('dd', '', value === null || value === undefined || value === '' ? 'Unavailable' : String(value))); });
    $('benchmark-details').replaceChildren(...details);
    const limitations = Array.isArray(data.limitations) ? data.limitations : [];
    $('showcase-limitations').replaceChildren(...(limitations.length ? limitations.map((text) => element('li', '', String(text))) : [element('li', '', 'No limitations were supplied by the local evidence endpoint.')]));
  } catch (error) {
    $('showcase-version').textContent = 'Evidence unavailable';
    $('feature-grid').replaceChildren(element('p', 'evidence-unavailable', `Implementation evidence could not be loaded. ${error.message}`));
    evidenceText('showcase-tests', 'Unavailable', false);
    evidenceText('showcase-benchmark', 'Unavailable', false);
    evidenceText('showcase-generator', 'Unavailable', false);
    $('showcase-test-scope').textContent = 'Recorded evidence endpoint unavailable';
    $('showcase-benchmark-scope').textContent = 'No benchmark claim is shown';
    $('showcase-generator-scope').textContent = 'See local run instructions';
    $('generator-evidence').hidden = true;
    $('showcase-limitations').replaceChildren(element('li', '', 'Evidence unavailable. Use the documentation to review current limitations.'));
  }
}
function renderRunChooser() {
  const runs = [...report.runs].sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)));
  const chooser = $('change-run');
  const oldRunId = impactRunId;
  if (!runs.length) {
    const option = element('option', '', 'No ingestion runs available');
    option.value = '';
    chooser.replaceChildren(option);
    chooser.disabled = true;
    impactRunId = '';
    $('change-message').textContent = 'Import a movement CSV to retain its before-and-after balance comparison.';
    emptyTable('changes-body', 7, 'No run selected.');
    return;
  }
  chooser.disabled = false;
  chooser.replaceChildren(...runs.map((run) => {
    const source = String(run.source_file || 'unknown source').split(/[\\/]/).pop();
    const shortId = String(run.run_id).slice(0, 8);
    const seededRuns = demoMetadata()?.runs || {};
    const seedLabels = { initial: 'Demo initial load', correction: 'Demo receipt correction', cancellation: 'Demo cancellation', restoration: 'Demo restoration', validation: 'Demo validation', failure: 'Demo schema failure', recovery: 'Demo safe replay' };
    const scenario = Object.keys(seedLabels).find((key) => seededRuns[key] === String(run.run_id));
    const type = scenario ? seedLabels[scenario] : 'CSV ingestion';
    const option = element('option', '', `${type} · ${source} · ${formatTime(run.started_at)} · ${shortId}`);
    option.value = String(run.run_id);
    return option;
  }));
  if (!runs.some((run) => String(run.run_id) === impactRunId)) {
    const correctionId = demoMetadata()?.runs?.correction;
    const sampleCorrection = runs.find((run) => String(run.run_id) === correctionId);
    impactRunId = String((sampleCorrection || runs[0]).run_id);
    impactOffset = 0;
  }
  chooser.value = impactRunId;
  const run = runs.find((r) => String(r.run_id) === impactRunId);
  $('change-run-status').textContent = String(run.status || 'unknown').replaceAll('_', ' ');
  if (oldRunId !== impactRunId || !$('panel-changes').hidden) loadChanges();
}
function openChangeRun(runId) {
  if ($('import-drawer').open) $('import-drawer').close();
  impactRunId = String(runId);
  impactOffset = 0;
  $('change-run').value = impactRunId;
  selectTab($('tab-changes'), true);
  $('tab-changes').scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}
async function loadChanges() {
  if (!impactRunId) return;
  const requestId = ++impactRequest;
  const selectedId = impactRunId;
  $('change-message').textContent = 'Loading the retained before-and-after comparison…';
  $('changes-previous').disabled = true;
  $('changes-next').disabled = true;
  $('change-run').setAttribute('aria-busy', 'true');
  try {
    const data = await getJSON(`/api/changes?run_id=${encodeURIComponent(selectedId)}&limit=${IMPACT_PAGE_SIZE}&offset=${impactOffset}`);
    if (requestId !== impactRequest) return;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const summary = data.summary || {};
    impactTotal = Number(data.total || 0);
    const run = data.run || report.runs.find((r) => String(r.run_id) === selectedId) || {};
    $('change-run-status').textContent = String(run.status || 'unknown').replaceAll('_', ' ');
    $('change-summary').hidden = data.has_snapshot === false;
    $('change-count').textContent = number(summary.changed_rows ?? impactTotal);
    $('change-series').textContent = number(summary.affected_series || 0);
    $('change-range').textContent = summary.from_date ? `${summary.from_date} → ${summary.through_date || summary.from_date}` : 'No changed dates';
    if (data.has_snapshot === false) {
      $('change-message').textContent = 'No retained comparison is available for this run. It may predate impact tracking or have failed before publication. New successful imports retain their balance changes.';
      emptyTable('changes-body', 7, 'No retained comparison for this run.');
    } else if (impactTotal === 0) {
      $('change-message').textContent = 'No published balance values changed in this run. Identical event revisions and safe reruns leave balances unchanged.';
      emptyTable('changes-body', 7, 'No balance changes.');
    } else {
      $('change-message').textContent = `Showing the balance changes caused by ${display(run.source_file)}. Before and after refer to this run, not to the latest ledger state.`;
      $('changes-body').replaceChildren(...rows.map((record) => {
        const row = element('tr');
        cell(row, record.balance_date);
        addPairCell(row, record.item_id, record.location_id);
        const before = cell(row, record.before_closing, 'numeric');
        before.title = `Before opening: ${display(record.before_opening)}`;
        const after = cell(row, record.after_closing, 'numeric');
        after.title = `After opening: ${display(record.after_opening)}`;
        const delta = record.closing_delta;
        cell(row, delta, `numeric${Number(delta) > 0 ? ' change-delta-positive' : Number(delta) < 0 ? ' change-delta-negative' : ''}`);
        const change = cell(row, '');
        change.replaceChildren(badge(String(record.change_type || 'changed').replaceAll('_', ' '), record.change_type === 'removed' ? 'warning' : ''));
        cell(row, Array.isArray(record.changed_fields) ? record.changed_fields.join(', ') : display(record.changed_fields), 'field-list');
        return row;
      }));
    }
    const start = impactTotal ? impactOffset + 1 : 0;
    const end = Math.min(impactOffset + rows.length, impactTotal);
    $('changes-pagination-summary').textContent = `Showing ${number(start)}–${number(end)} of ${number(impactTotal)} changed daily rows`;
    $('changes-previous').disabled = impactOffset === 0 || data.has_snapshot === false;
    $('changes-next').disabled = impactOffset + IMPACT_PAGE_SIZE >= impactTotal || data.has_snapshot === false;
  } catch (error) {
    if (requestId !== impactRequest) return;
    $('change-summary').hidden = true;
    $('change-message').textContent = `Could not load this comparison. ${error.message}`;
    emptyTable('changes-body', 7, 'Comparison unavailable. Select another run or refresh data.');
    $('changes-pagination-summary').textContent = 'Comparison unavailable';
  } finally {
    if (requestId === impactRequest) $('change-run').removeAttribute('aria-busy');
  }
}
function readableBytes(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(2)} MiB` : `${Math.max(1, Math.ceil(bytes / 1024))} KiB`;
}
function previewLines(text) { return text.split(/\r\n|\n|\r/).slice(0, 6).join('\n'); }
function resultMessage(id, message, kind = 'failed') {
  const box = $(id);
  box.hidden = false;
  box.className = `import-result${kind ? ' ' + kind : ''}`;
  box.replaceChildren(element('p', 'result-meta', message));
}
function updateMutationControls() {
  document.querySelectorAll('.mutation-control').forEach((control) => {
    control.disabled = mutationBusy;
    control.setAttribute('aria-busy', String(mutationBusy));
  });
  $('import-submit').disabled = mutationBusy || !selectedFiles.movement;
  $('catalog-submit').disabled = mutationBusy || !selectedFiles.items || !selectedFiles.locations;
  $('import-submit').textContent = mutationBusy ? 'Working…' : 'Import & publish';
  $('catalog-submit').textContent = mutationBusy ? 'Working…' : 'Validate & load catalogs';
}
async function chooseFile(kind, input) {
  selectedFiles[kind] = null;
  updateMutationControls();
  const file = input.files[0];
  if (kind === 'movement') {
    $('movement-preview').hidden = true;
    $('import-result').hidden = true;
  } else {
    $(`${kind}-file-info`).textContent = 'No file selected';
    $('catalog-result').hidden = true;
  }
  if (!file) { renderCatalogPreview(); return; }
  const resultId = kind === 'movement' ? 'import-result' : 'catalog-result';
  if (file.size > MAX_CSV_BYTES) {
    resultMessage(resultId, `${file.name} is larger than 10 MiB. Use the CLI for larger batches, or choose a smaller CSV.`);
    renderCatalogPreview();
    return;
  }
  if (!file.size) {
    resultMessage(resultId, `${file.name} is empty. Choose a CSV with its required header row.`);
    renderCatalogPreview();
    return;
  }
  try {
    const bytes = await file.arrayBuffer();
    const csvText = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    if (input.files[0] !== file) return;
    selectedFiles[kind] = { filename: file.name, csv_text: csvText, size: file.size };
    if (kind === 'movement') {
      $('movement-preview').hidden = false;
      $('movement-file-name').textContent = file.name;
      $('movement-file-size').textContent = readableBytes(file.size);
      $('movement-file-preview').textContent = previewLines(csvText);
    } else {
      $(`${kind}-file-info`).textContent = `${file.name} · ${readableBytes(file.size)}`;
    }
    renderCatalogPreview();
  } catch (_) {
    resultMessage(resultId, 'This file could not be read as UTF-8 CSV. Save it with UTF-8 encoding, then choose it again.');
  }
  updateMutationControls();
}
function renderCatalogPreview() {
  const chosen = ['items', 'locations'].filter((kind) => selectedFiles[kind]);
  $('catalog-preview').hidden = chosen.length === 0;
  $('catalog-file-preview').textContent = chosen.map((kind) => `${selectedFiles[kind].filename}\n${previewLines(selectedFiles[kind].csv_text)}`).join('\n\n');
}
async function getToken() {
  if (csrfToken) return csrfToken;
  if (!csrfPromise) {
    csrfPromise = getJSON('/api/session').then((session) => {
      if (!session.csrf_token) throw new Error('The local session is unavailable. Refresh this page before importing.');
      csrfToken = session.csrf_token;
      if (session.username) {
        $('account-username').textContent = String(session.username);
        $('account-initial').textContent = String(session.username).charAt(0).toUpperCase();
      }
      return csrfToken;
    }).finally(() => { csrfPromise = null; });
  }
  return csrfPromise;
}
async function postJSON(path, payload) {
  const token = await getToken();
  let response;
  try {
    response = await fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Stockline-Token': token }, body: JSON.stringify(payload) });
  } catch (_) {
    throw new Error(path === '/api/logout' ? 'The local sign-out request was interrupted. Check the server connection and try again.' : 'The local request was interrupted. Refresh pipeline runs and check the ledger before retrying; the server may have completed the import.');
  }
  requireAuthenticatedResponse(response);
  let data;
  try { data = await response.json(); } catch (_) { throw new Error(path === '/api/logout' ? 'The sign-out response could not be read. Try again.' : 'The server response could not be read. Refresh pipeline runs before retrying.'); }
  if (!response.ok || data.error) {
    if (response.status === 403) csrfToken = null;
    const error = new Error(data.error || `${path === '/api/logout' ? 'Sign out' : 'Import'} failed (HTTP ${response.status}).`);
    error.runId = data.run_id;
    throw error;
  }
  return data;
}
function appendResultStats(box, run) {
  const stats = element('div', 'result-stats');
  [['Accepted', run.accepted_count], ['Duplicates', run.duplicate_count], ['Quarantined', run.rejected_count], ['Input rows', run.input_count]].forEach(([label, value]) => {
    const item = element('div');
    item.append(element('strong', '', number(value)), element('span', '', label));
    stats.append(item);
  });
  box.append(stats);
}
function renderImportResult(data) {
  const run = data.run || {};
  const box = $('import-result');
  const warning = Number(run.rejected_count) > 0;
  box.hidden = false;
  box.className = `import-result${run.status === 'failed' ? ' failed' : warning ? ' warning' : ''}`;
  const heading = element('div', 'result-heading');
  heading.append(element('strong', '', run.status === 'failed' ? 'Import failed' : warning ? 'Published with quarantined rows' : 'Import published'), badge(String(run.status || 'unknown').replaceAll('_', ' '), warning ? 'warning' : run.status === 'failed' ? 'failed' : ''));
  box.replaceChildren(heading);
  appendResultStats(box, run);
  const impact = data.impact || {};
  const summary = impact.summary || impact;
  const impactDescription = summary.changed_rows === undefined ? 'Open the retained balance comparison to inspect the result.' : `${number(summary.changed_rows)} daily balance rows changed across ${number(summary.affected_series || 0)} item / location pairs.`;
  box.append(element('p', 'result-meta', impactDescription), element('p', 'result-meta', `Run ${display(run.run_id)} · ${display(run.source_file)}`));
  if (warning) box.append(element('p', 'result-meta', 'Review the quarantined rows and correct their source data. Valid records were published.'));
  if (run.run_id) {
    const view = element('button', 'secondary-button', 'View this run’s balance impact →');
    view.type = 'button';
    view.addEventListener('click', () => openChangeRun(run.run_id));
    box.append(view);
  }
}
async function importMovements(event) {
  event.preventDefault();
  if (mutationBusy || !selectedFiles.movement || !$('import-form').reportValidity()) return;
  const selected = selectedFiles.movement;
  const payload = { filename: selected.filename, csv_text: selected.csv_text };
  if ($('import-through').value) payload.through = $('import-through').value;
  mutationBusy = true;
  updateMutationControls();
  resultMessage('import-result', 'Validating the CSV and publishing accepted rows…', '');
  try {
    const data = await postJSON('/api/import', payload);
    renderImportResult(data);
    await loadData({ afterMutation: true });
    const importedRunId = String(data.run?.run_id || '');
    if (report.runs.some((run) => String(run.run_id) === importedRunId)) {
      // An older queued response may have changed selection; restore this import.
      impactRunId = importedRunId;
      impactOffset = 0;
      renderRunChooser();
    }
  } catch (error) {
    resultMessage('import-result', `${error.message}${error.runId ? ` Run ${error.runId} is recorded in pipeline runs.` : ''}`);
    await loadData({ afterMutation: true });
  } finally {
    mutationBusy = false;
    updateMutationControls();
  }
}
async function loadCatalogs() {
  try {
    const catalogs = await getJSON('/api/catalogs');
    const items = Array.isArray(catalogs.items) ? catalogs.items : [];
    const locations = Array.isArray(catalogs.locations) ? catalogs.locations : [];
    $('catalog-count').textContent = `${number(items.length)} items · ${number(locations.length)} locations`;
    const itemNodes = items.slice(0, 200).map((item) => element('li', '', `${display(item.item_id)} · ${display(item.unit)}`));
    const locationNodes = locations.slice(0, 200).map((location) => element('li', '', display(location.location_id)));
    if (!itemNodes.length) itemNodes.push(element('li', '', 'No items loaded'));
    if (!locationNodes.length) locationNodes.push(element('li', '', 'No locations loaded'));
    if (items.length > 200) itemNodes.push(element('li', '', `${number(items.length - 200)} more IDs in the catalog`));
    if (locations.length > 200) locationNodes.push(element('li', '', `${number(locations.length - 200)} more IDs in the catalog`));
    $('current-items').replaceChildren(...itemNodes);
    $('current-locations').replaceChildren(...locationNodes);
  } catch (error) {
    $('catalog-count').textContent = 'Catalog list unavailable';
    $('current-items').replaceChildren(element('li', '', error.message));
    $('current-locations').replaceChildren(element('li', '', 'Refresh data to retry.'));
  }
}
async function importCatalogs(event) {
  event.preventDefault();
  if (mutationBusy || !selectedFiles.items || !selectedFiles.locations) return;
  mutationBusy = true;
  updateMutationControls();
  resultMessage('catalog-result', 'Validating both catalogs together…', '');
  try {
    const data = await postJSON('/api/catalogs', {
      items_filename: selectedFiles.items.filename, items_csv: selectedFiles.items.csv_text,
      locations_filename: selectedFiles.locations.filename, locations_csv: selectedFiles.locations.csv_text,
    });
    const itemResult = typeof data.items === 'object' ? JSON.stringify(data.items) : display(data.items);
    const locationResult = typeof data.locations === 'object' ? JSON.stringify(data.locations) : display(data.locations);
    resultMessage('catalog-result', `Catalog step completed. Items: ${itemResult}. Locations: ${locationResult}. You can now import their movements.`, '');
    await Promise.all([loadCatalogs(), loadData({ afterMutation: true })]);
  } catch (error) {
    resultMessage('catalog-result', `Catalogs were not loaded. ${error.message}`);
  } finally {
    mutationBusy = false;
    updateMutationControls();
  }
}

$('change-run').addEventListener('change', () => { impactRunId = $('change-run').value; impactOffset = 0; loadChanges(); });
$('changes-previous').addEventListener('click', () => { impactOffset = Math.max(0, impactOffset - IMPACT_PAGE_SIZE); loadChanges(); });
$('changes-next').addEventListener('click', () => { if (impactOffset + IMPACT_PAGE_SIZE < impactTotal) { impactOffset += IMPACT_PAGE_SIZE; loadChanges(); } });
// Native modal dialog provides keyboard focus containment and Escape handling.
// Keep the form mounted so closing, reopening, or refreshing data retains drafts.
function openImportDrawer() {
  const drawer = $('import-drawer');
  if (drawer.open) return;
  drawer.showModal();
  document.body.classList.add('import-drawer-open');
  document.querySelectorAll('[data-open-import]').forEach((button) => button.setAttribute('aria-expanded', 'true'));
}
document.querySelectorAll('[data-open-import]').forEach((button) => button.addEventListener('click', openImportDrawer));
$('close-import').addEventListener('click', () => $('import-drawer').close());
$('import-drawer').addEventListener('close', () => {
  // A queued close event must not unlock a drawer that has already reopened.
  if ($('import-drawer').open) return;
  document.body.classList.remove('import-drawer-open');
  document.querySelectorAll('[data-open-import]').forEach((button) => button.setAttribute('aria-expanded', 'false'));
  if (window.location.hash === '#import-section') {
    window.history.replaceState(null, '', '#main');
    syncWorkspaceNavigation();
  }
});
let importBackdropPressed = false;
function outsideImportDrawer(event) {
  const bounds = $('import-drawer').getBoundingClientRect();
  return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
}
$('import-drawer').addEventListener('pointerdown', (event) => {
  importBackdropPressed = event.target === $('import-drawer') && outsideImportDrawer(event);
});
$('import-drawer').addEventListener('click', (event) => {
  if (importBackdropPressed && event.target === $('import-drawer') && outsideImportDrawer(event)) $('import-drawer').close();
  importBackdropPressed = false;
});

$('movement-file').addEventListener('change', (event) => chooseFile('movement', event.target));
$('items-file').addEventListener('change', (event) => chooseFile('items', event.target));
$('locations-file').addEventListener('change', (event) => chooseFile('locations', event.target));
$('import-form').addEventListener('submit', importMovements);
$('catalog-form').addEventListener('submit', importCatalogs);

// Balance example toggle: begin
let balanceExampleView = null;
function balanceExampleAvailable() {
  return Boolean(demoMetadata()) && report.balances.some((row) => row.item_id === 'ITEM-A' && row.location_id === 'WH-A') &&
    [...$('item-filter').options].some((option) => option.value === 'ITEM-A') &&
    [...$('location-filter').options].some((option) => option.value === 'WH-A');
}
function captureBalanceView() {
  return { item: $('item-filter').value, location: $('location-filter').value,
    from: $('from-filter').value, through: $('through-filter').value, page };
}
function restoreBalanceView(view) {
  $('item-filter').value = [...$('item-filter').options].some((option) => option.value === view.item) ? view.item : '';
  $('location-filter').value = [...$('location-filter').options].some((option) => option.value === view.location) ? view.location : '';
  $('from-filter').value = view.from;
  $('through-filter').value = view.through;
  page = view.page;
}
function updateBalanceExampleButton() {
  const button = $('demo-balances-hint').querySelector('.demo-hint-action');
  if (button) {
    button.textContent = balanceExampleView ? 'Close example' : 'View this example';
    button.setAttribute('aria-pressed', String(Boolean(balanceExampleView)));
  }
}
function openBalanceExample() {
  if (balanceExampleView || !balanceExampleAvailable()) return;
  balanceExampleView = captureBalanceView();
  $('item-filter').value = 'ITEM-A';
  $('location-filter').value = 'WH-A';
  $('from-filter').value = '2026-01-01';
  $('through-filter').value = '2026-01-04';
  page = 0;
  applyFilters();
  updateBalanceExampleButton();
}
function exitBalanceExample(restore = true) {
  if (!balanceExampleView) return;
  const prior = balanceExampleView;
  balanceExampleView = null;
  if (restore) {
    restoreBalanceView(prior);
    applyFilters();
  }
  updateBalanceExampleButton();
}
function toggleBalanceExample() {
  if (balanceExampleView) exitBalanceExample(true);
  else openBalanceExample();
}
function reconcileBalanceExample() {
  if (balanceExampleView && !balanceExampleAvailable()) exitBalanceExample(true);
}
// Balance example toggle: end

function demoMetadata() {
  const demo = report.demo_examples;
  return demo && demo.version === 1 && demo.runs && typeof demo.runs === 'object' ? demo : null;
}
function setDemoWorkspaceNote(text) {
  const box = $('demo-workspace-note');
  if (!text) {
    if (box.contains(document.activeElement)) document.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    box.hidden = true;
    return;
  }
  box.hidden = false;
  let disclosure = box.querySelector('.context-disclosure');
  if (!disclosure) {
    disclosure = element('details', 'context-disclosure');
    const summary = element('summary', 'context-summary');
    const chevron = svgElement('svg', { class: 'context-chevron', viewBox: '0 0 24 24',
      'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7',
      'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    chevron.append(svgElement('path', { d: 'm6 9 6 6 6-6' }));
    summary.append(element('span', '', 'Seeded demo'), chevron);
    disclosure.append(summary, element('p', 'context-detail'));
    box.append(disclosure);
  }
  disclosure.querySelector('.context-detail').textContent = text;
}
function setDemoHint(view, text, actionLabel, action) {
  const box = $(`demo-${view}-hint`);
  if (!text) {
    if (box.contains(document.activeElement)) {
      document.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    }
    box.hidden = true;
    return;
  }
  box.hidden = false;
  let disclosure = box.querySelector('.demo-hint-disclosure');
  if (!disclosure) {
    disclosure = element('details', 'demo-hint-disclosure');
    const summary = element('summary', 'demo-hint-summary');
    const chevron = svgElement('svg', { class: 'demo-hint-chevron', viewBox: '0 0 24 24',
      'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7',
      'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    chevron.append(svgElement('path', { d: 'm6 9 6 6 6-6' }));
    summary.append(element('span', 'demo-hint-label', 'Demo example'), chevron);
    const body = element('div', 'demo-hint-body');
    body.append(element('p', 'demo-hint-message'));
    disclosure.append(summary, body);
    box.append(disclosure);
  }
  // Reuse native disclosure and action nodes: refresh must not close help or
  // replace the keyboard user's currently focused summary/action.
  const body = disclosure.querySelector('.demo-hint-body');
  body.querySelector('.demo-hint-message').textContent = text;
  let button = body.querySelector('.demo-hint-action');
  if (actionLabel && action) {
    if (!button) {
      button = element('button', 'demo-hint-action');
      button.type = 'button';
      body.append(button);
    }
    button.hidden = false;
    button.textContent = actionLabel;
    button.onclick = action;
  } else if (button) {
    if (document.activeElement === button) disclosure.querySelector('summary').focus();
    button.hidden = true;
    button.onclick = null;
  }
}
function showDemoView(view) {
  const demo = demoMetadata();
  const tab = $(`tab-${view}`);
  if (!demo || !tab || tab.hidden) return;
  if (view === 'changes' && demo.runs.correction) {
    openChangeRun(demo.runs.correction);
  } else {
    selectTab(tab);
    if (view === 'balances') openBalanceExample();
  }
  tab.focus({ preventScroll: true });
  $('report-section').scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}
function renderDemoExamples() {
  reconcileBalanceExample();
  const demo = demoMetadata();
  $('demo-scenarios').hidden = !demo;
  if (!demo) {
    ['balances', 'changes', 'reconciliation', 'runs', 'rejects', 'movements'].forEach((view) => setDemoHint(view, ''));
    setDemoWorkspaceNote('');
    return;
  }
  const shortageExample = report.balances.find((row) => negative(row.closing) &&
    ((row.item_id === 'ITEM-D' && row.location_id === 'WH-C' && row.balance_date === '2026-01-02') ||
     (row.item_id === 'ITEM-E' && row.location_id === 'WH-B' && row.balance_date === '2026-01-04')));
  const demoKinds = shortageExample ? 'validation and stock-shortage examples' : 'validation examples';
  setDemoWorkspaceNote(`This workspace includes intentional ${demoKinds}. The tabs explain those specific cases; all run alerts remain visible.`);
  const balance = report.balances.find((row) => row.item_id === 'ITEM-A' && row.location_id === 'WH-A' && row.balance_date === '2026-01-04');
  const closingText = balance ? `Its current closing balance is ${display(balance.closing)}; later imports can change it.` : 'Follow its receipts, issue, and transfer across the four dates.';
  const canOpenBalanceExample = balanceExampleAvailable();
  const shortageText = shortageExample ? ` Shortage example: ${shortageExample.item_id} / ${shortageExample.location_id} on ${shortageExample.balance_date} currently closes ${display(shortageExample.closing)} in red; availability still needs review.` : '';
  setDemoHint('balances', `Start with ITEM-A / WH-A on 2026-01-04. ${closingText}${shortageText}`, canOpenBalanceExample ? (balanceExampleView ? 'Close example' : 'View this example') : null, canOpenBalanceExample ? toggleBalanceExample : null);
  updateBalanceExampleButton();
  setDemoHint('changes', 'Open the seeded receipt correction to see its before-and-after balances and the later days affected by a backdated change.', demo.runs.correction ? 'Open receipt correction' : null, demo.runs.correction ? () => openChangeRun(demo.runs.correction) : null);
  setDemoHint('reconciliation', 'The seeded validation batch quarantines bad rows before publication. Reconciliation checks valid published data, so those checks can pass while rejected rows still need review. Accepted issues can also create negative closing stock: the arithmetic can reconcile while availability warnings remain. Later import errors and shortages still require review.');
  setDemoHint('runs', `The seeded schema example, based on demo_expected_schema_failure.csv, intentionally tests a changed header. Its recorded recovery safely replays the ${number(demo.initial_movement_count)} movements as duplicates. Other failed runs still require review.`, demo.runs.recovery ? 'Open recovery comparison' : null, demo.runs.recovery ? () => openChangeRun(demo.runs.recovery) : null);
  setDemoHint('rejects', `The seeded validation example, based on demo_quality_examples.csv, contains ${number(demo.expected_rejected_rows)} invalid rows: excessive precision, an unknown item, and a transfer within one warehouse. Expand their source payloads. This description applies to that seeded example, not to later rejected imports.`);
  setDemoHint('movements', `Transfer ${display(demo.transfer_event_id)} was cancelled at revision 2 and restored at revision 3. Its superseded void version stays visible so the cancellation history is not lost.`);
}
document.querySelectorAll('[data-demo-view]').forEach((button) => {
  button.addEventListener('click', () => showDemoView(button.dataset.demoView));
});

async function signOut() {
  const button = $('sign-out');
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  try {
    await postJSON('/api/logout', {});
    authRedirecting = true;
    csrfToken = null;
    window.location.replace('/login');
  } catch (error) {
    if (!error.authenticationRequired) {
      $('error').hidden = false;
      $('error').textContent = `Could not sign out. ${error.message} Please try again.`;
      $('error').setAttribute('tabindex', '-1');
      $('error').focus();
    }
  } finally {
    if (!authRedirecting) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  }
}
$('sign-out').addEventListener('click', signOut);

function syncWorkspaceNavigation() {
  const destination = window.location.hash || '#main';
  if (destination === '#import-section') openImportDrawer();
  document.querySelectorAll('.sidebar-link').forEach((link) => {
    const active = link.getAttribute('href') === destination;
    link.classList.toggle('sidebar-active', active);
    if (active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
}
[['#achievements-dropdown', 'achievements-dropdown'], ['#process-dropdown', 'process-dropdown']].forEach(([href, id]) => {
  document.querySelectorAll(`a[href="${href}"]`).forEach((link) => {
    link.addEventListener('click', () => { $(id).open = true; });
  });
});
window.addEventListener('hashchange', syncWorkspaceNavigation);
window.addEventListener('pageshow', (event) => {
  // A restored history snapshot must revalidate the protected document/cookie.
  if (event.persisted) window.location.reload();
});
syncWorkspaceNavigation();
getToken().catch(() => { /* A 401 redirects; other read errors remain retryable. */ });
renderAll();
loadData();
loadShowcase();
loadCatalogs();
