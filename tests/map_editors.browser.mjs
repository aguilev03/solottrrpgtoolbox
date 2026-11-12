// Run against an isolated, LOGIN_DISABLED staging server; never production.
import { chromium, firefox, webkit } from '../build/dungeon-mapper-work/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

const base = process.env.MAP_TEST_URL || 'http://127.0.0.1:5088';
assert.match(base, /^http:\/\/127\.0\.0\.1:/, 'Browser tests must use an isolated localhost server.');
const results = process.env.MAP_TEST_RESULTS || '/tmp/hexworld-editor-stage/browser';
await mkdir(results, {recursive:true});
const engines = {chromium, firefox, webkit};
for (const name of (process.env.MAP_TEST_ENGINES || 'chromium').split(',')) {
  const browser = await engines[name].launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1050}, acceptDownloads:true});
  context.setDefaultTimeout(20000);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (['document','script','stylesheet','image','font'].includes(response.request().resourceType()) && response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
  });
  await page.goto(base + '/maps/');
  const token = await page.locator('#map-library').getAttribute('data-token');
  async function api(path, data) {
    const response = await context.request.fetch(base + '/maps/api/' + path, {method:data ? 'POST':'GET', data,
      headers:{'X-CSRF-Token':token, 'Accept':'application/json'}});
    assert.equal(response.status(),200,await response.text()); return response.json();
  }
  const campaign = await api('campaigns', {name:`Browser ${name}`});
  for (const editor of ['gridmapper','dungeon-mapper']) {
    const record = await api('maps', {campaign_id:campaign.id, name:`${editor} acceptance`, editor});
    await page.goto(`${base}/${editor}/?map=${record.id}`);
    await page.locator('#map-save').waitFor({state:'visible'});
    await page.waitForFunction(() => !document.getElementById('map-save').disabled, {timeout:60000});
    const frame = page.frames().find(f => f.url().includes('/app/'));
    assert.ok(frame);
    if (editor === 'gridmapper') {
      await frame.locator('svg').first().click({position:{x:200,y:100}});
      await page.keyboard.press('f'); await page.keyboard.press('ArrowRight'); await page.keyboard.press('f');
      const source = await page.evaluate(() => document.getElementById('editor-frame').contentWindow.getSource());
      assert.ok(source.includes('f'),source);
      await page.evaluate(() => { document.getElementById('editor-frame').contentWindow.interpretMap('z(2,2)fff'); });
    } else {
      // Real pointer drawing with the default selected brush.
      const canvas = frame.locator('canvas[role="application"]');
      await canvas.waitFor({state:'visible'});
      const before = await frame.evaluate(() => window.hexworld.getProject());
      await canvas.click({position:{x:120,y:120}});
      await canvas.click({position:{x:150,y:120}});
      const after = await frame.evaluate(() => window.hexworld.getProject());
      assert.notEqual(after,before,'Canvas drawing should change the native project');
      await frame.getByRole('button', {name:'Add a new level', exact:true}).click();
      await frame.waitForFunction(() => JSON.parse(window.hexworld.getProject()).project.levels.length === 2);
      await canvas.click({position:{x:160,y:160}});
    }
    await page.locator('#map-save').click();
    await page.waitForFunction(() => document.getElementById('map-status').textContent.includes('revision 1'));
    const saved = await api(`maps/${record.id}`);
    assert.ok(saved.project);
    const native = await context.request.get(`${base}/maps/api/maps/${record.id}/export`);
    assert.equal(await native.text(),saved.project);
    await writeFile(`${results}/${name}-${editor}.${editor === 'gridmapper'?'txt':'json'}`,saved.project);
    const pngEvent = page.waitForEvent('download');
    await page.locator('#map-png').click();
    const png = await pngEvent; await png.saveAs(`${results}/${name}-${editor}.png`);
    await page.screenshot({path:`${results}/${name}-${editor}.png-screen.png`,fullPage:true});
    await page.reload();
    await page.waitForFunction(() => !document.getElementById('map-save').disabled);
    const reopened = page.frames().find(f=>f.url().includes('/app/'));
    const source = await page.evaluate(kind => { const w = document.getElementById('editor-frame').contentWindow; return kind === 'gridmapper' ? w.getSource() : w.hexworld.getProject(); }, editor);
    if (editor === 'gridmapper') {
      const geometry = s => s.replace(/\([\d.]+,[\d.]+,(\d+)\)\n$/, '(0,0,$1)\n');
      assert.equal(geometry(source),geometry(saved.project));
    }
    else assert.deepEqual(JSON.parse(source),JSON.parse(saved.project));
    // A stale page must preserve local work and display a conflict on server save.
    await api(`maps/${record.id}/save`, {revision:1, project:saved.project});
    await page.locator('#map-save').click();
    await page.waitForFunction(() => document.getElementById('map-status').textContent.includes('Another tab'));
    assert.equal((await api(`maps/${record.id}`)).revision,2);
    await page.reload(); await page.waitForFunction(() => !document.getElementById('map-save').disabled);
    await page.setViewportSize({width:820,height:1180});
    await page.screenshot({path:`${results}/${name}-${editor}-tablet.png`,fullPage:true});
    assert.ok(await page.locator('#map-save').isVisible());
    // Native export and PNG remain usable at a tablet viewport.
    const nativeEvent = page.waitForEvent('download'); await page.locator('#map-download').click();
    assert.ok((await nativeEvent).suggestedFilename().endsWith(editor === 'gridmapper'?'.txt':'.json'));
    await page.setViewportSize({width:1440,height:1050});
    if (name === 'chromium') {
      const tablet = await browser.newContext({viewport:{width:820,height:1180},hasTouch:true,isMobile:true,
        deviceScaleFactor:2,storageState:await context.storageState()});
      tablet.setDefaultTimeout(20000);
      console.log(`CHECK ${name} ${editor}: touch emulation`);
      const touchPage = await tablet.newPage();
      await touchPage.goto(`${base}/${editor}/?map=${record.id}`);
      await touchPage.waitForFunction(() => !document.getElementById('map-save').disabled);
      const touchFrame = touchPage.frames().find(f=>f.url().includes('/app/'));
      const getNative = () => touchPage.evaluate(kind=>{const w=document.getElementById('editor-frame').contentWindow;return kind==='gridmapper'?w.getSource():w.hexworld.getProject();},editor);
      const beforeTouch = await getNative();
      if (editor === 'gridmapper') {
        await touchPage.evaluate(()=>document.getElementById('editor-frame').contentDocument.getElementById('help').setAttribute('visibility','hidden'));
        await touchPage.locator('#editor-frame').scrollIntoViewIfNeeded();
        const box = await touchPage.locator('#editor-frame').boundingBox();
        const cdp = await tablet.newCDPSession(touchPage);
        await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+120,y:box.y+140}]});
        await new Promise(resolve=>setTimeout(resolve,380));
        await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
      } else await touchFrame.locator('canvas[role="application"]').tap({position:{x:120,y:180}});
      const comparable = source => editor === 'gridmapper' ? source.replace(/\([\d.]+,[\d.]+,(\d+)\)\n$/, '(0,0,$1)\n') : source;
      assert.notEqual(comparable(await getNative()),comparable(beforeTouch),`${editor} touch drawing changed map content`);
      console.log(`CHECK ${editor}: touch stroke captured; saving`);
      await touchPage.locator('#map-save').click();
      await touchPage.waitForFunction(()=>document.getElementById('map-status').textContent.includes('revision 3'));
      console.log(`PASS ${editor}: touch edit saved`);
      await tablet.close();
    }
    await page.reload(); await page.waitForFunction(()=>!document.getElementById('map-save').disabled);
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#map-import').setInputFiles({name:`backup.${editor === 'gridmapper'?'txt':'json'}`,
      mimeType:editor === 'gridmapper'?'text/plain':'application/json',buffer:Buffer.from(saved.project)});
    await page.waitForFunction(()=>document.getElementById('map-status').textContent.includes('Imported'));
    const next = (await api(`maps/${record.id}`)).revision + 1;
    await page.locator('#map-save').click();
    await page.waitForFunction(revision=>document.getElementById('map-status').textContent.includes(`revision ${revision}`),next);
    await page.locator('#map-revision').selectOption('1');
    page.once('dialog',dialog=>dialog.accept()); await page.locator('#map-restore').click();
    await page.waitForFunction(()=>document.getElementById('map-status').textContent.includes('Revision loaded'));
    page.once('dialog',dialog=>dialog.accept('Browser working copy')); await page.locator('#map-copy').click();
    await page.waitForURL(url=>url.searchParams.has('map') && url.searchParams.get('map')!==String(record.id));
    await page.waitForFunction(()=>!document.getElementById('map-save').disabled);
    const copy = await api(`maps/${new URL(page.url()).searchParams.get('map')}`);
    assert.equal(copy.editor,editor); assert.equal(copy.campaign_id,campaign.id); assert.ok(copy.project);
    console.log(`PASS ${name} ${editor}: draw, levels, save, PNG, native export/import, refresh, conflict, revision recovery, copy, tablet viewport`);
  }
  assert.deepEqual(errors,[], 'Browser page errors');
  await context.close(); await browser.close();
}
