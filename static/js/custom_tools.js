/* SQLite is authoritative: no browser storage is used. */
(() => {
    const token = document.querySelector('meta[name="custom-csrf"]').content;
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', event => {
            if (!confirm(form.dataset.confirm)) event.preventDefault();
        });
    });
    const viewer = document.getElementById('card-viewer');
    if (!viewer) return;
    document.getElementById('close-card-viewer').onclick = () => viewer.close();
    viewer.addEventListener('click', event => { if (event.target === viewer) viewer.close(); });
    document.querySelectorAll('.table-card').forEach(card => {
        const button = card.querySelector('button');
        let drag = null, moved = false;
        button.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            moved = false;
            drag = { px: event.clientX, py: event.clientY, x: +card.dataset.x, y: +card.dataset.y };
            button.setPointerCapture(event.pointerId);
            card.style.zIndex = '1';
        });
        button.addEventListener('pointermove', event => {
            if (!drag) return;
            const dx = event.clientX - drag.px, dy = event.clientY - drag.py;
            if (Math.abs(dx) + Math.abs(dy) > 6) moved = true;
            if (!moved) return;
            card.dataset.x = Math.max(-80, Math.min(80, drag.x + dx / card.offsetWidth * 100));
            card.dataset.y = Math.max(-200, Math.min(200, drag.y + dy));
            card.style.transform = `translate(${card.dataset.x}%,${card.dataset.y}px)`;
        });
        const finish = async () => {
            if (!drag) return;
            const previous = drag;
            drag = null;
            card.style.zIndex = '';
            if (!moved) return;
            button.disabled = true;
            const status = document.getElementById('tabletop-status');
            try {
                const response = await fetch(card.dataset.positionUrl, {
                    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': token},
                    body: JSON.stringify({x: +card.dataset.x, y: +card.dataset.y})
                });
                if (!response.ok || response.redirected) throw new Error('Save failed');
                status.textContent = 'Position saved.';
            } catch (_) {
                card.dataset.x = previous.x;
                card.dataset.y = previous.y;
                card.style.transform = `translate(${previous.x}%,${previous.y}px)`;
                status.textContent = 'Could not save position. Reload and try again.';
            } finally { button.disabled = false; }
        };
        button.addEventListener('pointerup', finish);
        button.addEventListener('pointercancel', finish);
        button.addEventListener('click', event => {
            if (moved && event.detail !== 0) return;
            const source = card.querySelector('img'), target = viewer.querySelector('img');
            target.src = source.src; target.alt = source.alt; target.className = source.className;
            target.style.rotate = `${card.dataset.rotation || 0}deg`;
            viewer.querySelector('p').textContent = card.querySelector('figcaption').firstChild.textContent.trim();
            viewer.showModal();
        });
        const rotateButton = card.querySelector('.rotate-card');
        if (rotateButton) rotateButton.addEventListener('click', async () => {
            const previous = +card.dataset.rotation || 0, next = (previous + 90) % 360;
            const status = document.getElementById('tabletop-status');
            card.dataset.rotation = next;
            button.style.setProperty('--card-rotation', `${next}deg`);
            rotateButton.disabled = true;
            try {
                const response = await fetch(card.dataset.rotateUrl, {
                    method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': token},
                    body: JSON.stringify({rotation: next})
                });
                if (!response.ok) throw new Error('Save failed');
                status.textContent = `Card turned to ${next}°.`;
            } catch (_) {
                card.dataset.rotation = previous;
                button.style.setProperty('--card-rotation', `${previous}deg`);
                status.textContent = 'Could not save rotation. Reload and try again.';
            } finally { rotateButton.disabled = false; }
        });
    });
})();
