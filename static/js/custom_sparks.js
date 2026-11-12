/* Progressive enhancement: rolls and reset also work as ordinary POST forms. */
(() => {
    const forms = [...document.querySelectorAll('[data-spark-roll], [data-spark-reset]')];
    const status = document.getElementById('spark-status');
    const entries = document.getElementById('spark-log-entries');
    const empty = document.getElementById('spark-log-empty');
    const log = document.getElementById('spark-log');
    let busy = false;
    forms.forEach(form => form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        busy = true;
        forms.forEach(item => { item.querySelector('button').disabled = true; });
        status.textContent = form.hasAttribute('data-spark-reset') ? 'Resetting…' : 'Rolling…';
        try {
            const response = await fetch(form.action, {
                method: 'POST', body: new FormData(form),
                headers: {Accept: 'application/json'}
            });
            if (response.redirected) throw new Error('Please reload the page and sign in again.');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not save your roll. Please reload and try again.');
            if (form.hasAttribute('data-spark-reset')) {
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
                    entries.append(item);
                }
                empty.hidden = true;
                log.scrollTop = log.scrollHeight;
                status.textContent = 'Spark added.';
            }
        } catch (error) {
            status.textContent = error.message || 'Request failed. Reload to check the saved log before trying again.';
        } finally {
            busy = false;
            forms.forEach(item => { item.querySelector('button').disabled = false; });
        }
    }));
})();
