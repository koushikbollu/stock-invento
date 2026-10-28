/* Optional developer verification: node tests/ui_refresh.test.cjs
 * Executes the real browser queue function with controlled asynchronous reads.
 * Node built-ins only; the application itself does not require Node.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../inventory/static/app.js'), 'utf8');
const marked = source.match(/\/\/ Report request queue: begin\n([\s\S]*?)\/\/ Report request queue: end/);
assert.ok(marked, 'the queue under test must come from the actual application source');
// Use this Promise realm: cross-realm assimilation hides the settling-tail race.
const createReportLoader = Function(`${marked[1]}\nreturn createReportLoader;`)();
const flush = () => new Promise((resolve) => setImmediate(resolve));
function fixture() {
  const reads = [];
  const busy = [];
  const load = createReportLoader(() => new Promise((resolve, reject) => reads.push({ resolve, reject })), (state) => busy.push(state));
  return { reads, busy, load };
}
async function ordinaryRefreshesCoalesce() {
  const { reads, busy, load } = fixture();
  const first = load();
  assert.equal(load(), first);
  await flush();
  assert.equal(reads.length, 1);
  reads[0].resolve('snapshot');
  assert.equal(await first, 'snapshot');
  assert.deepEqual(busy, [true, false]);
}
async function mutationQueuesANewRead() {
  const { reads, busy, load } = fixture();
  const oldRefresh = load();
  await flush();
  const afterMutation = load({ afterMutation: true });
  assert.notEqual(oldRefresh, afterMutation);
  assert.equal(load(), afterMutation, 'ordinary refreshes wait for the current final tail');
  assert.equal(reads.length, 1, 'do not race another read against the older snapshot');
  reads[0].resolve('pre-mutation snapshot');
  assert.equal(await oldRefresh, 'pre-mutation snapshot');
  await flush();
  assert.equal(reads.length, 2, 'a fresh read must start after the mutation request');
  assert.deepEqual(busy, [true], 'controls must stay busy across the queued read');
  reads[1].resolve('post-mutation snapshot');
  assert.equal(await afterMutation, 'post-mutation snapshot');
  assert.deepEqual(busy, [true, false]);
}
async function eachMutationAppendsASerializedRead() {
  const { reads, busy, load } = fixture();
  const oldRefresh = load();
  await flush();
  const mutationOne = load({ afterMutation: true });
  const mutationTwo = load({ afterMutation: true });
  assert.equal(load(), mutationTwo);
  reads[0].resolve('old');
  await flush();
  assert.equal(reads.length, 2);
  const mutationThree = load({ afterMutation: true });
  reads[1].resolve('after-first-mutation');
  assert.equal(await mutationOne, 'after-first-mutation');
  await flush();
  assert.equal(reads.length, 3);
  reads[2].resolve('after-second-mutation');
  assert.equal(await mutationTwo, 'after-second-mutation');
  await flush();
  assert.equal(reads.length, 4, 'every mutation appends a read, including while a queued read is running');
  reads[3].resolve('latest');
  assert.equal(await mutationThree, 'latest');
  assert.equal(await oldRefresh, 'old');
  assert.deepEqual(busy, [true, false]);
}
async function olderFailureDoesNotDropForcedRefresh() {
  const { reads, busy, load } = fixture();
  const first = load();
  const firstFailure = assert.rejects(first, /old read failed/);
  await flush();
  const forced = load({ afterMutation: true });
  reads[0].reject(new Error('old read failed'));
  await firstFailure;
  await flush();
  assert.equal(reads.length, 2);
  assert.deepEqual(busy, [true]);
  reads[1].resolve('recovered');
  assert.equal(await forced, 'recovered');
  assert.deepEqual(busy, [true, false]);
}
async function failedLatestReadUnlocksForRetry() {
  const { reads, busy, load } = fixture();
  const first = load();
  await flush();
  const forced = load({ afterMutation: true });
  const rejected = assert.rejects(forced, /latest read failed/);
  reads[0].resolve('old');
  await flush();
  reads[1].reject(new Error('latest read failed'));
  await rejected;
  assert.equal(await first, 'old');
  assert.deepEqual(busy, [true, false]);
  const retry = load();
  await flush();
  assert.equal(reads.length, 3);
  reads[2].resolve('retry success');
  assert.equal(await retry, 'retry success');
  assert.deepEqual(busy, [true, false, true, false]);
}
async function forcedReadDuringSettlingTailIsNotLost() {
  let resolveFirst;
  let resolveSecond;
  const firstRead = { promise: new Promise((resolve) => { resolveFirst = resolve; }) };
  const secondRead = new Promise((resolve) => { resolveSecond = resolve; });
  let reads = 0;
  const load = createReportLoader(() => ++reads === 1 ? firstRead.promise : secondRead);
  const old = load();
  let forced;
  // Same-realm registration order reproduces the old loop/finally boundary.
  const mutationCallback = firstRead.promise.then(() => { forced = load({ afterMutation: true }); });
  resolveFirst('old');
  await mutationCallback;
  await flush();
  assert.equal(reads, 2, 'the mutation request made while the old tail settles must start a second read');
  resolveSecond('fresh-after-mutation');
  assert.equal(await old, 'old');
  assert.equal(await forced, 'fresh-after-mutation');
}
const toggleSource = source.match(/\/\/ Balance example toggle: begin\n([\s\S]*?)\/\/ Balance example toggle: end/);
assert.ok(toggleSource, 'the toggle under test must come from the actual application source');
function toggleFixture() {
  let metadataPresent = true;
  let button = { textContent: 'View this example', attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } };
  const nodes = {
    'item-filter': { value: 'ITEM-B', options: ['', 'ITEM-A', 'ITEM-B'].map((value) => ({ value })) },
    'location-filter': { value: 'WH-B', options: ['', 'WH-A', 'WH-B'].map((value) => ({ value })) },
    'from-filter': { value: '2025-12-10' }, 'through-filter': { value: '2026-01-15' },
    'demo-balances-hint': { querySelector: () => button },
  };
  const api = vm.runInNewContext(`let page = 2;\n${toggleSource[1]}\n({ open: openBalanceExample, toggle: toggleBalanceExample, exit: exitBalanceExample, reconcile: reconcileBalanceExample, updateButton: updateBalanceExampleButton, view: captureBalanceView, isOpen: () => Boolean(balanceExampleView) });`, {
    $: (id) => nodes[id], report: { balances: [{ item_id: 'ITEM-A', location_id: 'WH-A' }] },
    demoMetadata: () => metadataPresent ? { version: 1 } : null, applyFilters: () => {},
  });
  return { api, nodes, button: () => button, removeMetadata: () => { metadataPresent = false; },
    replaceButton: () => { button = { textContent: '', attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } }; } };
}
const plain = (value) => JSON.parse(JSON.stringify(value));
function exampleOpenCloseRestoresPriorView() {
  const { api, button } = toggleFixture();
  const prior = plain(api.view());
  api.toggle();
  assert.deepEqual(plain(api.view()), { item: 'ITEM-A', location: 'WH-A', from: '2026-01-01', through: '2026-01-04', page: 0 });
  assert.equal(button().textContent, 'Close example');
  assert.equal(button().attributes['aria-pressed'], 'true');
  api.open(); // Bottom navigation must not overwrite the captured original view.
  api.toggle();
  assert.deepEqual(plain(api.view()), prior);
  assert.equal(button().textContent, 'View this example');
  assert.equal(button().attributes['aria-pressed'], 'false');
}
function manualFiltersExitWithoutRestoringOverThem() {
  const { api, nodes, button } = toggleFixture();
  api.open();
  nodes['item-filter'].value = 'ITEM-B';
  nodes['from-filter'].value = '2026-01-03';
  api.exit(false); // The actual manual change/reset handlers use this mode.
  assert.equal(api.isOpen(), false);
  assert.equal(nodes['item-filter'].value, 'ITEM-B');
  assert.equal(nodes['from-filter'].value, '2026-01-03');
  assert.equal(button().textContent, 'View this example');
}
function reportRefreshKeepsTheOpenExample() {
  const { api, button, replaceButton } = toggleFixture();
  api.open();
  replaceButton(); // A report render recreates this dynamic hint action.
  api.reconcile();
  api.updateButton();
  assert.equal(api.isOpen(), true);
  assert.equal(button().textContent, 'Close example');
  assert.equal(api.view().item, 'ITEM-A');
  api.toggle();
  assert.equal(api.view().item, 'ITEM-B');
}
function missingMetadataRestoresAndStopsTheToggle() {
  const { api, removeMetadata, button } = toggleFixture();
  const prior = plain(api.view());
  api.open();
  removeMetadata();
  api.reconcile();
  assert.equal(api.isOpen(), false);
  assert.deepEqual(plain(api.view()), prior);
  assert.equal(button().textContent, 'View this example');
  api.open();
  assert.equal(api.isOpen(), false);
}
function removedPriorOptionsRestoreToAll() {
  const { api, nodes } = toggleFixture();
  api.open();
  nodes['item-filter'].options = [{ value: '' }, { value: 'ITEM-A' }];
  nodes['location-filter'].options = [{ value: '' }, { value: 'WH-A' }];
  api.toggle();
  assert.equal(api.view().item, '');
  assert.equal(api.view().location, '');
  assert.equal(api.view().from, '2025-12-10');
}
(async () => {
  for (const test of [ordinaryRefreshesCoalesce, mutationQueuesANewRead, eachMutationAppendsASerializedRead, olderFailureDoesNotDropForcedRefresh, failedLatestReadUnlocksForRetry, forcedReadDuringSettlingTailIsNotLost]) await test();
  for (const test of [exampleOpenCloseRestoresPriorView, manualFiltersExitWithoutRestoringOverThem, reportRefreshKeepsTheOpenExample, missingMetadataRestoresAndStopsTheToggle, removedPriorOptionsRestoreToAll]) test();
  process.stdout.write('PASS: 6 same-realm report-queue cases and 5 example-toggle cases (11 total)\n');
})().catch((error) => { console.error(error); process.exitCode = 1; });
