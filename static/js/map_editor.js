(() => {
  const root = document.getElementById('map-editor'), frame = document.getElementById('editor-frame');
  const status = document.getElementById('map-status'), lock = document.getElementById('editor-lock');
  const buttons = [...root.querySelectorAll('button'), document.getElementById('map-import'), document.getElementById('map-revision')];
  const id = new URLSearchParams(location.search).get('map');
  let record, adapter, baseline, busy = false, initialized = false, failed = false;
  function message(text, error = false) { status.textContent = text; status.classList.toggle('map-error', error); }
  function enable(value) { buttons.forEach(b => { b.disabled = !value; }); }
  function revisions(values) {
    const select = document.getElementById('map-revision'); select.replaceChildren();
    for (const value of values) { const option = document.createElement('option'); option.value = value; option.textContent = `Revision ${value}`; select.append(option); }
  }
  async function api(path, data) {
    const response = await fetch('/maps/api/' + path, {method: data ? 'POST' : 'GET',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': root.dataset.token},
      body: data ? JSON.stringify(data) : undefined});
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw Error('Your login expired. Download your work, then log in again.');
    const result = await response.json(); if (!response.ok) throw Error(result.error); return result;
  }
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function gridAdapter() {
    const w = frame.contentWindow, doc = frame.contentDocument;
    if (typeof w.getSource !== 'function' || !w.Map?.exportarea) throw Error('Gridmapper did not initialize.');
    // Upstream reads MouseEvent.pageX/pageY even for TouchEvent. Normalize real
    // touches here; NaN coordinates otherwise make its line-drawing loop hang.
    const position = w.Pen.position;
    w.Pen.position = function(event) {
      const point = event.touches?.[0] || event.changedTouches?.[0] || event;
      if (!Number.isFinite(point.pageX) || !Number.isFinite(point.pageY)) return {x:w.Pen.x, y:w.Pen.y};
      return position.call(w.Pen, point);
    };
    // The private wrapper does not publish maps to Campaign Wiki or its collaboration server.
    for (const id of ['join', 'host', 'wiki']) doc.getElementById(id)?.setAttribute('display', 'none');
    return {
      getProject: () => w.getSource(),
      async loadProject(source) {
        if (source && source.replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, '').includes(';')) throw Error('Import a native TXT export without demo pause commands.');
        w.autoWallOff(); w.Map.reset();
        if (source) {
          // Native exported projects are command text, never executable JavaScript.
          // Semicolon demo pauses are not part of getSource() exports.
          w.interpretMap(source);
        }
        w.Map.showLevelAnimation(); w.Pen.update(null);
      },
      async exportPNG() {
        w.download(); const link = doc.getElementById('download_png');
        // Clear stale output from a previous export while the current image renders.
        link.removeAttributeNS('http://www.w3.org/1999/xlink', 'href');
        for (let i = 0; i < 150; i++) {
          await delay(40);
          if (link.getAttributeNS('http://www.w3.org/1999/xlink', 'href')?.includes('data:image/png')) { link.dispatchEvent(new w.MouseEvent('click', {bubbles:true})); return; }
        }
        throw Error('PNG rendering did not finish. Try the editor’s Download menu.');
      },
    };
  }
  function download() {
    const source = adapter.getProject();
    const url = URL.createObjectURL(new Blob([source], {type: root.dataset.editor === 'gridmapper' ? 'text/plain' : 'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = `map-${record.id}-working.${root.dataset.editor === 'gridmapper' ? 'txt' : 'json'}`;
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  async function operation(fn) {
    if (!initialized || busy) return;
    busy = true; enable(false);
    try {
      if (record.editor === 'dungeon-mapper' && frame.contentWindow.hexworld !== adapter) throw Error('The editor changed workspace. Reopen this map from the library to use HexWorld saves. Run sessions remain saved on this device.');
      await fn();
    } catch (error) { failed = true; message(error.message, true); }
    finally { busy = false; enable(true); }
  }
  document.getElementById('map-save').onclick = () => operation(async () => {
    const source = adapter.getProject(); message('Saving to HexWorld…');
    const saved = await api(`maps/${record.id}/save`, {revision: record.revision, project: source});
    record.revision = saved.revision; baseline = source; failed = false;
    revisions((await api(`maps/${record.id}`)).revisions);
    message(`Saved to HexWorld · revision ${record.revision}`);
  });
  document.getElementById('map-copy').onclick = () => operation(async () => {
    const name = prompt('Name for the new copy', record.name + ' copy'); if (name === null) return;
    const source = adapter.getProject();
    const copy = await api('maps', {campaign_id: record.campaign_id, name, editor: record.editor, project: source});
    baseline = source; busy = false; initialized = false; location.href = `/${record.editor}/?map=${copy.id}`;
  });
  document.getElementById('map-download').onclick = () => operation(async () => { download(); });
  document.getElementById('map-png').onclick = () => operation(async () => { await adapter.exportPNG(); message('PNG exported. Save the image in your Obsidian vault.'); });
  document.getElementById('map-restore').onclick = () => operation(async () => {
    const revision = document.getElementById('map-revision').value; if (!revision) return;
    if (!confirm(`Load revision ${revision} into the editor? Download unsaved work first. The server version stays unchanged until you save.`)) return;
    const response = await fetch(`/maps/api/maps/${record.id}/export?revision=${revision}`);
    if (!response.ok || response.redirected) throw Error('Revision unavailable or login expired. Download your current work before reloading.');
    const before = adapter.getProject(); lock.hidden = false;
    try { await adapter.loadProject(await response.text()); failed = false; message('Revision loaded. Save to HexWorld to make it current.'); }
    catch (error) { await adapter.loadProject(before); throw error; }
    finally { lock.hidden = true; }
  });
  document.getElementById('map-import').onchange = event => operation(async () => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 16 * 1024 * 1024) throw Error('Project exceeds 16 MiB.');
      if (!confirm('Replace the editor workspace with this project? The server version stays saved until you press Save to HexWorld. Download any unsaved work first.')) return;
      // Decode first in Dungeon Mapper; retain an in-memory recovery snapshot for any failure.
      const before = adapter.getProject(); lock.hidden = false;
      try { await adapter.loadProject(await file.text()); }
      catch (error) { await adapter.loadProject(before); throw error; }
      failed = false; message('Imported into editor. Unsaved changes — Save to HexWorld.');
    } finally { event.target.value = ''; lock.hidden = true; }
  });
  function comparable(source) {
    // Gridmapper includes the live pen coordinates in TXT exports; hovering is not an edit.
    return root.dataset.editor === 'gridmapper' ? source.replace(/\([\d.]+,[\d.]+,(\d+)\)\n$/, '(0,0,$1)\n') : source;
  }
  function dirty() { return initialized && comparable(adapter.getProject()) !== comparable(baseline); }
  window.addEventListener('beforeunload', event => {
    if (busy || dirty()) { event.preventDefault(); event.returnValue = ''; }
  });
  document.querySelector('a[href="/maps/"]').addEventListener('click', event => {
    if ((busy || dirty()) && !confirm('Leave without saving to HexWorld? Download your work first if you need a backup.')) event.preventDefault();
  });
  async function start() {
    if (!id || !/^\d+$/.test(id)) return;
    record = await api(`maps/${id}`);
    if (record.editor !== root.dataset.editor) throw Error('This map belongs to the other editor. Open it from the map library.');
    document.getElementById('map-title').textContent = record.name;
    revisions(record.revisions);
    message('Loading saved project…'); frame.hidden = false; lock.hidden = false;
    frame.src = record.editor === 'gridmapper' ? '/gridmapper/app/gridmapper.svg' : `/dungeon-mapper/app/index.html?hexworld=${record.id}`;
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Editor loading timed out. Check that editor assets were built.')), 45000);
      frame.onload = () => { clearTimeout(timer); resolve(); };
    });
    if (record.editor === 'gridmapper') adapter = await gridAdapter();
    else {
      for (let i = 0; i < 1000; i++) {
        if (frame.contentWindow.hexworld?.ready) break;
        await delay(40);
      }
      adapter = frame.contentWindow.hexworld;
      if (!adapter?.ready) throw Error('Dungeon Mapper is not ready. Check browser storage and reload.');
    }
    await adapter.loadProject(record.project);
    baseline = adapter.getProject(); initialized = true; enable(true); lock.hidden = true;
    message(record.revision ? `Saved to HexWorld · revision ${record.revision}` : 'New map — Save to HexWorld to keep your work.');
    setInterval(() => {
      if (busy || failed) return;
      try { message(dirty() || record.revision === 0 ? 'Unsaved changes — Save to HexWorld.' : `Saved to HexWorld · revision ${record.revision}`); }
      catch (error) { failed = true; enable(false); message('Editor closed unexpectedly. Reload to reopen the saved server project.', true); }
    }, 1500);
  }
  start().catch(error => { message(error.message, true); lock.textContent = 'Project could not be opened. Your server copy has not changed.'; });
})();
