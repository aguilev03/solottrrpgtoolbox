// Isolated end-to-end checks. Creates a temporary SQLite database, never production.
import { chromium } from '../build/dungeon-mapper-work/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

const staging = await mkdtemp(join(tmpdir(), 'custom-sparks-browser-'));
let base;
const server = spawn('.venv/bin/python', ['-c', `
from app import app, db
from werkzeug.security import generate_password_hash
db.create_user('spark-tester', generate_password_hash('browser-test-password'))
from werkzeug.serving import make_server
server = make_server('127.0.0.1', 0, app, threaded=True)
print(f'SPARK_BROWSER_PORT={server.server_port}', flush=True)
server.serve_forever()
`], {env: {...process.env, SOLO_TOOLS_DB: join(staging, 'tools.db'), LOGIN_DISABLED: 'false', CARD_UPLOAD_DIR: join(staging, 'uploads')}, stdio: ['ignore', 'pipe', 'pipe']});
let serverOutput = '';
server.stderr.on('data', chunk => { serverOutput += chunk; });
server.stdout.on('data', chunk => { serverOutput += chunk; });
let browser;
try {
    // Read the ephemeral port from this child, avoiding any existing local app.
    base = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error(serverOutput || 'Test server did not start.')), 15000);
        const check = () => {
            const match = serverOutput.match(/SPARK_BROWSER_PORT=(\d+)/);
            if (match) { clearTimeout(timeout); resolve(`http://127.0.0.1:${match[1]}`); }
        };
        server.stdout.on('data', check);
        server.once('exit', () => { clearTimeout(timeout); reject(new Error(serverOutput)); });
        check();
    });
    browser = await chromium.launch({headless: true, executablePath: '/usr/bin/chromium'});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/login');
    await page.locator('[name=username]').fill('spark-tester');
    await page.locator('[name=password]').fill('browser-test-password');
    await Promise.all([page.waitForURL(base + '/'), page.locator('button[type=submit]').click()]);
    await page.goto(base + '/sparks');
    let token = await page.locator('meta[name=custom-csrf]').getAttribute('content');
    async function post(path, form) {
        const response = await context.request.post(base + path, {form, headers: {'X-CSRF-Token': token, Accept: 'application/json'}});
        assert.equal(response.status(), 200, await response.text());
        return response.json();
    }
    const first = (await post('/sparks', {name: 'Omens', entries: 'A bell'})).id;
    const second = (await post('/sparks', {name: 'Places', entries: 'A tower'})).id;
    for (let i = 0; i < 34; i++) await post('/sparks', {name: `Table ${String(i).padStart(2, '0')} with a readable label`, entries: `Spark ${i}`});
    await post('/sparks', {name: '<script>unbrokenlonglabel'.repeat(6), entries: '<script>window.bad=true</script>'});
    await page.reload();
    const favorite = page.locator(`[data-table-id="${first}"]`);
    await favorite.locator('[data-spark-favorite] button').click();
    await page.waitForFunction(() => document.getElementById('spark-favorites').children.length === 1);
    assert.equal(await page.locator('#spark-log-entries li').count(), 0, 'Star must not roll.');
    assert.equal(await page.locator(`[data-table-id="${first}"]`).count(), 1);
    assert.equal(await page.locator('#spark-regular-tables').locator(`[data-table-id="${first}"]`).count(), 0);
    await page.locator('#spark-search').fill('  PLACES  ');
    assert.equal(await page.locator('#spark-regular-tables .spark-table:visible').count(), 1);
    assert.equal(await favorite.isVisible(), true);
    await page.locator('#spark-search').fill('not a matching table');
    assert.equal(await page.locator('#spark-search-empty').isVisible(), true);
    assert.equal(await favorite.isVisible(), true);
    await favorite.locator('[data-spark-roll] button').click();
    await page.waitForFunction(() => document.querySelectorAll('#spark-log-entries li').length === 1);
    assert.match(await page.locator('#spark-log-entries li').first().innerText(), /A bell/);
    await page.locator('#spark-search').fill('Places');
    await page.locator(`[data-table-id="${second}"] [data-spark-roll] button`).click();
    await page.waitForFunction(() => document.querySelectorAll('#spark-log-entries li').length === 2);
    assert.match(await page.locator('#spark-log-entries li').first().innerText(), /A tower/);
    await page.reload();
    assert.match(await page.locator('#spark-log-entries li').first().innerText(), /A tower/);
    assert.equal(await page.locator('#spark-favorites .spark-table').count(), 1);
    await page.goto(base + '/logout');
    await page.locator('[name=username]').fill('spark-tester');
    await page.locator('[name=password]').fill('browser-test-password');
    await Promise.all([page.waitForURL(base + '/'), page.locator('button[type=submit]').click()]);
    await page.goto(base + '/sparks');
    assert.equal(await page.locator('#spark-favorites .spark-table').count(), 1);
    token = await page.locator('meta[name=custom-csrf]').getAttribute('content');
    await post(`/sparks/${first}/generate`, {count: 20});
    await post(`/sparks/${second}/generate`, {count: 20});
    await page.reload();
    for (const [width, height, columns] of [[1440, 1000, 3], [1000, 900, 2], [768, 1024, 2], [390, 844, 1], [360, 800, 1]]) {
        await page.setViewportSize({width, height});
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const layout = await page.evaluate(() => {
            const workspace = document.querySelector('.spark-workspace');
            const tables = document.querySelector('[aria-labelledby="spark-tables-title"]');
            const panel = document.querySelector('.spark-log-panel');
            const log = document.getElementById('spark-log');
            return {
                columns: getComputedStyle(document.getElementById('spark-regular-tables')).gridTemplateColumns.split(' ').length,
                overflow: document.documentElement.scrollWidth > innerWidth,
                table: tables.getBoundingClientRect().toJSON(), panel: panel.getBoundingClientRect().toJSON(),
                ratio: tables.clientWidth / (workspace.clientWidth - parseFloat(getComputedStyle(workspace).columnGap || 0)),
                position: getComputedStyle(panel).position,
                logScrolls: log.scrollHeight > log.clientHeight,
                panelFits: panel.getBoundingClientRect().bottom <= innerHeight,
            };
        });
        assert.equal(layout.columns, columns, JSON.stringify({width, layout}));
        assert.equal(layout.overflow, false, `Horizontal overflow at ${width}`);
        assert.equal(layout.logScrolls, true, `Log should scroll at ${width}`);
        if (width > 760) {
            assert.equal(layout.position, 'sticky');
            assert.equal(layout.panelFits, true, `Initial log fits viewport at ${width}`);
            assert.ok(layout.panel.left > layout.table.right, 'Log beside tables.');
            assert.ok(Math.abs(layout.ratio - .65) < .02, '65% table area.');
            await page.evaluate(() => window.scrollTo(0, 450));
            await page.waitForTimeout(100);
            const sticky = await page.evaluate(() => {
                const panel = document.querySelector('.spark-log-panel');
                const bounds = panel.getBoundingClientRect();
                return {top: bounds.top, offset: parseFloat(getComputedStyle(panel).top), bottom: bounds.bottom, height: innerHeight};
            });
            assert.ok(Math.abs(sticky.top - sticky.offset) < 2, JSON.stringify(sticky));
            assert.ok(sticky.bottom <= sticky.height, JSON.stringify(sticky));
        } else {
            assert.equal(layout.position, 'static');
            assert.ok(layout.panel.top >= layout.table.bottom, 'Mobile log below tables.');
        }
        await page.screenshot({path: join(staging, `sparks-${width}.png`), fullPage: true});
    }
    await page.setViewportSize({width: 1440, height: 1000});
    await page.evaluate(() => window.scrollTo(0, 0));
    await favorite.locator('[data-spark-favorite] button').click();
    await page.waitForFunction(() => document.getElementById('spark-favorites').children.length === 0);
    assert.equal(await page.locator('#spark-regular-tables').locator(`[data-table-id="${first}"]`).count(), 1);
    assert.equal(await page.locator('#spark-log-entries li').count(), 42);
    await page.locator('[data-spark-reset] button').click();
    await page.waitForFunction(() => document.querySelectorAll('#spark-log-entries li').length === 0);
    await page.reload();
    assert.equal(await page.locator('#spark-log-entries li').count(), 0);
    assert.deepEqual(errors, []);
    // Server forms still roll and favorite without JavaScript.
    const noJS = await browser.newContext({javaScriptEnabled: false, storageState: await context.storageState()});
    const plain = await noJS.newPage();
    await plain.goto(base + '/sparks?q=places');
    assert.equal(await plain.locator('#spark-regular-tables .spark-table:visible').count(), 1);
    await plain.locator(`[data-table-id="${second}"] [data-spark-favorite] button`).click();
    assert.equal(await plain.locator('#spark-favorites .spark-table').count(), 1);
    await plain.locator(`#spark-favorites [data-spark-roll] button`).click();
    assert.equal(await plain.locator('#spark-log-entries li').count(), 1);
    const nativeOracle = plain.locator('[data-fate-roll]');
    await nativeOracle.locator('select').selectOption('Impossible');
    await nativeOracle.locator('button').click();
    assert.equal(await plain.locator('#spark-log-entries li').count(), 2);
    assert.match(await plain.locator('#spark-log-entries li').first().innerText(), /Fate Oracle[\s\S]*Odds: Impossible[\s\S]*d100: \d+/);
    await noJS.close();
    await page.reload();
    const oracle = page.locator('[data-fate-roll]');
    assert.equal(await oracle.locator('select, button, input:not([type=hidden])').count(), 2);
    assert.equal(await oracle.locator('option').count(), 9);
    await oracle.locator('select').selectOption('Certain');
    await oracle.locator('button').click();
    await page.waitForFunction(() => document.getElementById('spark-status').textContent === 'Fate Oracle result added.');
    assert.equal(await page.locator('#spark-log-entries li').count(), 3);
    assert.match(await page.locator('#spark-log-entries li').first().innerText(), /Fate Oracle[\s\S]*Odds: Certain[\s\S]*d100: \d+/);
    await page.reload();
    assert.equal(await oracle.locator('select').inputValue(), 'Certain');
    for (const width of [1440, 1000, 768, 390, 360]) {
        await page.setViewportSize({width, height: 900});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        const fits = await oracle.evaluate(form => {
            const bounds = form.getBoundingClientRect();
            return [...form.querySelectorAll('select, button')].every(control => {
                const rect = control.getBoundingClientRect();
                return rect.left >= bounds.left && rect.right <= bounds.right + 1;
            });
        });
        assert.equal(fits, true, `Compact oracle fits at ${width}`);
    }
    await page.locator('[data-spark-reset] button').click();
    await page.waitForFunction(() => document.querySelectorAll('#spark-log-entries li').length === 0);

    console.log(`PASS: favorites, isolation-safe staging, search, spark and oracle rolls, newest-first log, reset, responsive grid and sticky scrolling. Screenshots: ${staging}`);
} finally {
    if (browser) await browser.close();
    if (server.exitCode === null) {
        const stopped = once(server, 'exit');
        server.kill();
        await stopped;
    }
}
