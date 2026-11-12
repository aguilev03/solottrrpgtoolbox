/* Progressive enhancement: all mutations also work as ordinary POST forms. */
(() => {
    const status = document.getElementById('spark-status');
    const entries = document.getElementById('spark-log-entries');
    const empty = document.getElementById('spark-log-empty');
    const log = document.getElementById('spark-log');
    const favorites = document.getElementById('spark-favorites');
    const regular = document.getElementById('spark-regular-tables');
    const search = document.getElementById('spark-search');
    const filter = () => {
        const query = search.value.trim().toLowerCase();
        let matches = 0;
        regular.querySelectorAll('.spark-table').forEach(table => {
            table.hidden = !table.dataset.tableName.toLowerCase().includes(query);
            if (!table.hidden) matches++;
        });
        favorites.querySelectorAll('.spark-table').forEach(table => { table.hidden = false; });
        document.getElementById('spark-search-empty').hidden = matches > 0;
        document.getElementById('spark-favorites-empty').hidden = favorites.children.length > 0;
    };
    search.addEventListener('input', filter);
    document.getElementById('spark-search-form').addEventListener('submit', event => {
        event.preventDefault();
        filter();
    });
    filter();

    // Account for the navigation height, including wrapping at tablet widths.
    const header = document.querySelector('.site-header');
    const panel = document.querySelector('.spark-log-panel');
    const updateLogHeight = () => panel.style.setProperty('--spark-log-available',
        `${Math.max(0, window.innerHeight - Math.max(0, panel.getBoundingClientRect().top) - 16)}px`);
    const updateOffset = () => {
        document.querySelector('.custom-tools').style.setProperty(
            '--spark-sticky-top', `${Math.ceil(header.getBoundingClientRect().height) + 16}px`);
        updateLogHeight();
    };
    updateOffset();
    if (window.ResizeObserver) new ResizeObserver(updateOffset).observe(header);
    window.addEventListener('resize', updateOffset);
    let heightFrame = null;
    window.addEventListener('scroll', () => {
        if (heightFrame !== null) return;
        heightFrame = requestAnimationFrame(() => { updateLogHeight(); heightFrame = null; });
    }, {passive: true});

    const forms = [...document.querySelectorAll('[data-spark-roll], [data-spark-reset], [data-spark-favorite], [data-fate-roll]')]
        .filter(form => !form.querySelector('button').disabled);
    let busy = false;
    forms.forEach(form => form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        busy = true;
        forms.forEach(item => { item.querySelector('button').disabled = true; });
        status.textContent = form.hasAttribute('data-spark-reset') ? 'Resetting…' :
            form.hasAttribute('data-spark-favorite') ? 'Saving favorite…' : 'Rolling…';
        try {
            const response = await fetch(form.action, {
                method: 'POST', body: new FormData(form),
                headers: {Accept: 'application/json'}
            });
            if (response.redirected) throw new Error('Please reload the page and sign in again.');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not save. Please reload and try again.');
            if (form.hasAttribute('data-spark-favorite')) {
                const table = form.closest('.spark-table');
                const button = form.querySelector('button');
                table.dataset.favorite = String(data.favorite);
                form.elements.favorite.value = data.favorite ? '0' : '1';
                button.setAttribute('aria-pressed', String(data.favorite));
                button.title = data.favorite ? 'Remove from favorites' : 'Add to favorites';
                button.querySelector('span').textContent = data.favorite ? '★' : '☆';
                const target = data.favorite ? favorites : regular;
                target.append(table);
                [...target.children].sort((a, b) =>
                    a.dataset.tableName.localeCompare(b.dataset.tableName) || Number(a.dataset.tableId) - Number(b.dataset.tableId)
                ).forEach(item => target.append(item));
                filter();
                status.textContent = data.favorite ? 'Table added to favorites.' : 'Table removed from favorites.';
            } else if (form.hasAttribute('data-spark-reset')) {
                entries.replaceChildren();
                empty.hidden = false;
                status.textContent = 'Log reset.';
            } else {
                for (const entry of data.log_entries) {
                    const item = document.createElement('li');
                    const name = document.createElement('strong');
                    const result = document.createElement('p');
                    name.textContent = entry.table_name;
                    result.textContent = entry.result;
                    item.append(name, result);
                    entries.prepend(item);
                }
                empty.hidden = true;
                log.scrollTop = 0;
                status.textContent = form.hasAttribute('data-fate-roll') ? 'Fate Oracle result added.' : 'Spark added.';
            }
        } catch (error) {
            status.textContent = error.message || 'Request failed. Reload to check the saved state before trying again.';
        } finally {
            busy = false;
            forms.forEach(item => { item.querySelector('button').disabled = false; });
        }
    }));
})();
