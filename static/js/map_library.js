/* Native projects remain in their original format; no editor conversion. */
(() => {
  const root = document.getElementById('map-library');
  const status = document.getElementById('library-status');
  const labels = {'gridmapper': 'Gridmapper', 'dungeon-mapper': 'Dungeon Mapper'};
  async function api(path, data) {
    const r = await fetch('/maps/api/' + path, {method: data ? 'POST' : 'GET',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': root.dataset.token},
      body: data ? JSON.stringify(data) : undefined});
    if (r.redirected || !r.headers.get('content-type')?.includes('application/json')) throw Error('Your login expired. Reload the library.');
    const result = await r.json(); if (!r.ok) throw Error(result.error); return result;
  }
  function el(tag, text, parent) { const item = document.createElement(tag); item.textContent = text; parent?.append(item); return item; }
  function action(parent, text, fn) {
    const button = el('button', text, parent); button.className = 'btn btn-secondary';
    button.onclick = async () => { button.disabled = true; try { await fn(); } catch (e) { status.textContent = e.message; } finally { button.disabled = false; } };
  }
  async function refresh() {
    const data = await api('library');
    const select = document.getElementById('campaign-choice'), selected = select.value;
    select.replaceChildren(); const list = document.getElementById('campaign-list'); list.replaceChildren();
    for (const campaign of data.campaigns) {
      const option = el('option', campaign.name, select); option.value = campaign.id;
      const section = el('section', '', list); section.className = 'map-campaign';
      el('h3', campaign.name, section);
      action(section, 'Rename campaign', async () => { const name = prompt('Campaign name', campaign.name); if (name !== null) { await api(`campaigns/${campaign.id}/rename`, {name}); await refresh(); } });
      const maps = el('div', '', section); maps.className = 'map-list';
      for (const map of data.maps.filter(m => m.campaign_id === campaign.id)) {
        const row = el('article', '', maps); el('strong', map.name, row); el('span', labels[map.editor] + (map.revision ? ` · revision ${map.revision}` : ' · not saved yet'), row);
        const open = el('a', 'Open editor', row); open.href = `/${map.editor}/?map=${map.id}`; open.className = 'btn btn-primary';
        action(row, 'Rename', async () => { const name = prompt('Map name', map.name); if (name !== null) { await api(`maps/${map.id}/rename`, {name, revision: map.revision}); await refresh(); } });
        action(row, 'Duplicate', async () => { const name = prompt('Copy name', map.name + ' copy'); if (name !== null) { await api(`maps/${map.id}/duplicate`, {name, revision: map.revision}); await refresh(); } });
        if (map.revision) { const download = el('a', 'Download project', row); download.href = `/maps/api/maps/${map.id}/export`; }
        action(row, 'Delete', async () => { if (confirm(`Delete “${map.name}” and its saved revisions? Download a backup first.`)) { await api(`maps/${map.id}/delete`, {revision: map.revision, confirm: true}); await refresh(); } });
      }
    }
    if ([...select.options].some(o => o.value === selected)) select.value = selected;
    if (!data.campaigns.length) el('p', 'Create a campaign to begin.', list);
  }
  for (const id of ['new-campaign', 'new-map']) document.getElementById(id).onsubmit = async event => {
    event.preventDefault(); const form = event.target, button = form.querySelector('button'); button.disabled = true;
    try {
      const data = new FormData(form), payload = {name: data.get('name')};
      if (id === 'new-campaign') { await api('campaigns', payload); form.reset(); await refresh(); }
      else {
        payload.campaign_id = Number(data.get('campaign_id')); payload.editor = data.get('editor');
        const file = data.get('file'); if (file.size) { if (file.size > 16 * 1024 * 1024) throw Error('Project exceeds 16 MiB.'); payload.project = await file.text(); }
        const created = await api('maps', payload); location.href = `/${payload.editor}/?map=${created.id}`;
      }
    } catch (e) { status.textContent = e.message; } finally { button.disabled = false; }
  };
  refresh().catch(e => { status.textContent = e.message; });
})();
