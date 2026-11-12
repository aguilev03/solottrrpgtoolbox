/* Dealer's table: a large, pannable, growable surface shared by every deck.
   SQLite is authoritative; nothing is kept in browser storage. */
(() => {
    const felt = document.getElementById('dealer-felt');
    if (!felt) return;

    const token = document.querySelector('meta[name="custom-csrf"]').content;
    const viewport = document.getElementById('dealer-viewport');
    const sizer = document.getElementById('dealer-sizer');
    const status = document.getElementById('dealer-status');
    const actions = document.getElementById('card-actions');
    const viewer = document.getElementById('table-card-viewer');
    const zoomLabel = document.getElementById('zoom-label');
    const sizeLabel = document.getElementById('table-size');
    const faceDownToggle = document.getElementById('deal-face-down');

    const CARD_W = 140;            // card width on the table, in table pixels
    const GROW_X = 800, GROW_Y = 600, EDGE = 220, MAX = 20000, MIN_W = 800, MIN_H = 600;
    const ZOOMS = [0.25, 0.4, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2];

    let width = +felt.dataset.width, height = +felt.dataset.height;
    let zoom = 1;
    let selected = null;
    let topZ = 0;
    let dealt = 0;                 // cascades consecutive draws so they don't stack exactly
    const cards = new Map();       // id -> {el, data}

    const urlFor = (template, id) => template.replace(/\/0(\/|$)/, `/${id}$1`);
    const say = text => { status.textContent = text; };

    async function post(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': token},
            body: JSON.stringify(body || {}),
        });
        let data = {};
        try { data = await response.json(); } catch (_) { /* non-JSON error page */ }
        if (!response.ok) throw new Error(data.error || 'Something went wrong. Reload and try again.');
        return data;
    }

    // ---------------------------------------------------------------- layout
    function applySize() {
        felt.style.width = `${width}px`;
        felt.style.height = `${height}px`;
        sizer.style.width = `${width * zoom}px`;
        sizer.style.height = `${height * zoom}px`;
        felt.style.transform = `scale(${zoom})`;
        sizeLabel.textContent = `${width} × ${height}`;
    }

    let sizeTimer = null;
    function saveSize() {
        clearTimeout(sizeTimer);
        sizeTimer = setTimeout(async () => {
            try {
                const result = await post(felt.dataset.tableUrl, {width, height});
                width = result.width; height = result.height; applySize();
            } catch (error) { say(error.message); }
        }, 300);
    }

    function grow(axis) {
        if (axis === 'x') width = Math.min(MAX, width + GROW_X);
        if (axis === 'y') height = Math.min(MAX, height + GROW_Y);
        applySize();
        saveSize();
    }

    function fitToCards() {
        let maxX = 0, maxY = 0;
        cards.forEach(({el, data}) => {
            maxX = Math.max(maxX, data.x + el.offsetWidth);
            maxY = Math.max(maxY, data.y + el.offsetHeight);
        });
        width = Math.max(MIN_W, Math.ceil(maxX + EDGE));
        height = Math.max(MIN_H, Math.ceil(maxY + EDGE));
        applySize();
        saveSize();
        say('Table resized to fit the cards.');
    }

    function setZoom(next, anchor) {
        const rect = viewport.getBoundingClientRect();
        const ax = anchor ? anchor.x - rect.left : viewport.clientWidth / 2;
        const ay = anchor ? anchor.y - rect.top : viewport.clientHeight / 2;
        const tableX = (viewport.scrollLeft + ax) / zoom, tableY = (viewport.scrollTop + ay) / zoom;
        zoom = next;
        applySize();
        viewport.scrollLeft = tableX * zoom - ax;
        viewport.scrollTop = tableY * zoom - ay;
        zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
        placeActions();
    }

    function stepZoom(direction, anchor) {
        if (direction === 0) return setZoom(1, anchor);
        const index = ZOOMS.findIndex(z => z >= zoom - 0.001);
        const next = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, index + direction))];
        if (next !== zoom) setZoom(next, anchor);
    }

    // ----------------------------------------------------------------- cards
    function describe(data) {
        if (data.face_down) return `Face-down card from ${data.deck_name}`;
        const label = data.name || `Card ${data.order}`;
        return `${label} from ${data.deck_name}${data.reversed ? ', reversed' : ''}${data.rotation ? `, turned ${data.rotation}°` : ''}`;
    }

    function render(entry) {
        const {el, data} = entry;
        el.style.left = `${data.x}px`;
        el.style.top = `${data.y}px`;
        el.style.zIndex = data.z;
        el.style.setProperty('--card-rotation', `${data.rotation}deg`);
        el.classList.toggle('is-face-down', data.face_down);
        el.setAttribute('aria-label', describe(data));
        el.title = describe(data);
    }

    function build(data) {
        const el = document.createElement('div');
        el.className = 'dealer-card';
        el.tabIndex = 0;
        el.setAttribute('role', 'button');
        el.dataset.id = data.id;
        el.style.width = `${CARD_W}px`;

        const inner = document.createElement('div');
        inner.className = 'dealer-card-inner';

        const face = document.createElement('img');
        face.className = 'dealer-card-face' + (data.reversed ? ' reversed' : '');
        face.src = data.image;
        face.alt = '';
        face.draggable = false;

        const back = document.createElement(data.back ? 'img' : 'div');
        back.className = 'dealer-card-back';
        if (data.back) { back.src = data.back; back.alt = ''; back.draggable = false; }

        inner.append(face, back);
        el.append(inner);
        felt.append(el);

        const entry = {el, data};
        cards.set(data.id, entry);
        topZ = Math.max(topZ, data.z || 0);
        render(entry);
        wireCard(entry);
        return entry;
    }

    async function saveCard(entry, changes, previous) {
        try {
            const result = await post(urlFor(felt.dataset.cardUrl, entry.data.id), changes);
            Object.assign(entry.data, {x: result.x, y: result.y, rotation: result.rotation, face_down: result.face_down, z: result.z});
            topZ = Math.max(topZ, result.z);
            render(entry);
            placeActions();
            return true;
        } catch (error) {
            if (previous) { Object.assign(entry.data, previous); render(entry); placeActions(); }
            say(`Could not save: ${error.message}`);
            return false;
        }
    }

    function snapshot(data) {
        return {x: data.x, y: data.y, rotation: data.rotation, face_down: data.face_down, z: data.z};
    }

    function rotate(entry, delta) {
        const previous = snapshot(entry.data);
        entry.data.rotation = (entry.data.rotation + delta + 360) % 360;
        render(entry);
        placeActions();
        saveCard(entry, {rotation: entry.data.rotation}, previous);
    }

    function flip(entry) {
        const previous = snapshot(entry.data);
        entry.data.face_down = !entry.data.face_down;
        render(entry);
        saveCard(entry, {face_down: entry.data.face_down}, previous);
    }

    async function giveBack(entry) {
        try {
            const result = await post(urlFor(felt.dataset.returnUrl, entry.data.id));
            entry.el.remove();
            cards.delete(entry.data.id);
            select(null);
            updateStack(result.deck_id, result.remaining);
            say(`Returned a card to ${entry.data.deck_name} and shuffled it in.`);
        } catch (error) { say(error.message); }
    }

    function enlarge(entry) {
        const img = viewer.querySelector('img');
        const source = entry.data.face_down ? entry.el.querySelector('.dealer-card-back') : entry.el.querySelector('.dealer-card-face');
        if (source.tagName === 'IMG') {
            img.hidden = false;
            img.src = source.src;
            img.className = source.className;
            img.style.transform = `rotate(${entry.data.rotation}deg)`; // .reversed uses the separate 'rotate' property
        } else {
            img.hidden = true;
        }
        img.alt = describe(entry.data);
        viewer.querySelector('p').textContent = describe(entry.data);
        viewer.showModal();
    }

    // -------------------------------------------------------------- selection
    function select(entry) {
        if (selected) selected.el.classList.remove('is-selected');
        selected = entry;
        if (entry) {
            entry.el.classList.add('is-selected');
            actions.hidden = false;
            placeActions();
        } else {
            actions.hidden = true;
        }
    }

    function placeActions() {
        if (!selected || actions.hidden) return;
        const card = selected.el.getBoundingClientRect();
        const view = viewport.getBoundingClientRect();
        const bar = actions.getBoundingClientRect();
        const visible = card.bottom > view.top && card.top < view.bottom && card.right > view.left && card.left < view.right;
        actions.style.visibility = visible ? 'visible' : 'hidden';
        // Never tuck the bar under the sticky site header.
        const header = document.querySelector('.site-header');
        const ceiling = Math.max(view.top, header ? header.getBoundingClientRect().bottom : 0) + 4;
        let top = card.top - bar.height - 8;
        if (top < ceiling) top = Math.min(card.bottom + 8, view.bottom - bar.height - 4);
        top = Math.max(ceiling, top);
        let left = card.left + card.width / 2 - bar.width / 2;
        left = Math.max(view.left + 4, Math.min(left, view.right - bar.width - 4));
        actions.style.top = `${top}px`;
        actions.style.left = `${Math.max(4, left)}px`;
    }

    actions.addEventListener('click', event => {
        const button = event.target.closest('[data-act]');
        if (!button || !selected) return;
        const entry = selected;
        ({
            cw: () => rotate(entry, 90),
            ccw: () => rotate(entry, -90),
            flip: () => flip(entry),
            zoom: () => enlarge(entry),
            return: () => giveBack(entry),
        })[button.dataset.act]();
    });

    // ------------------------------------------------------------- dragging
    // How far past the viewport edge the pointer is, as a scroll speed (px/frame).
    function edgeSpeed(event) {
        const rect = viewport.getBoundingClientRect(), margin = 56, max = 22;
        const ramp = d => Math.min(max, Math.round((margin - d) / margin * max) + 4);
        let vx = 0, vy = 0;
        if (event.clientX > rect.right - margin) vx = ramp(rect.right - event.clientX);
        else if (event.clientX < rect.left + margin) vx = -ramp(event.clientX - rect.left);
        if (event.clientY > rect.bottom - margin) vy = ramp(rect.bottom - event.clientY);
        else if (event.clientY < rect.top + margin) vy = -ramp(event.clientY - rect.top);
        return {vx, vy};
    }

    function wireCard(entry) {
        const {el} = entry;
        let drag = null;

        // Position follows the pointer plus however far the view has scrolled since the drag began.
        function follow() {
            const dx = drag.cx - drag.px + (viewport.scrollLeft - drag.startScroll.left);
            const dy = drag.cy - drag.py + (viewport.scrollTop - drag.startScroll.top);
            entry.data.x = Math.max(0, Math.min(width - 40, drag.previous.x + dx / zoom));
            entry.data.y = Math.max(0, Math.min(height - 40, drag.previous.y + dy / zoom));
            // The table grows as cards approach its far edges.
            if (entry.data.x + el.offsetWidth + EDGE > width && width < MAX) { width = Math.min(MAX, width + GROW_X); applySize(); saveSize(); }
            if (entry.data.y + el.offsetHeight + EDGE > height && height < MAX) { height = Math.min(MAX, height + GROW_Y); applySize(); saveSize(); }
            el.style.left = `${entry.data.x}px`;
            el.style.top = `${entry.data.y}px`;
            placeActions();
        }

        // While a card is held near the edge of the view, keep scrolling (and growing).
        function tick() {
            if (!drag || !drag.moved) return;
            const {vx, vy} = drag.speed;
            if (vx || vy) {
                viewport.scrollLeft += vx;
                viewport.scrollTop += vy;
                follow();
            }
            drag.frame = requestAnimationFrame(tick);
        }

        el.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            event.stopPropagation();
            const startScroll = {left: viewport.scrollLeft, top: viewport.scrollTop};
            drag = {px: event.clientX, py: event.clientY, cx: event.clientX, cy: event.clientY, startScroll,
                    previous: snapshot(entry.data), moved: false, speed: {vx: 0, vy: 0}, frame: 0};
            el.setPointerCapture(event.pointerId);
            el.classList.add('is-dragging');
            el.style.zIndex = topZ + 1;
        });

        el.addEventListener('pointermove', event => {
            if (!drag) return;
            drag.cx = event.clientX;
            drag.cy = event.clientY;
            if (!drag.moved && Math.abs(drag.cx - drag.px) + Math.abs(drag.cy - drag.py) < 6) return;
            if (!drag.moved) { drag.moved = true; drag.frame = requestAnimationFrame(tick); }
            drag.speed = edgeSpeed(event);
            follow();
        });

        const finish = () => {
            if (!drag) return;
            const {moved, previous, frame} = drag;
            cancelAnimationFrame(frame);
            drag = null;
            el.classList.remove('is-dragging');
            if (moved) {
                saveCard(entry, {x: entry.data.x, y: entry.data.y, raise: true}, previous);
            } else {
                el.style.zIndex = entry.data.z;
            }
            select(entry);
        };
        el.addEventListener('pointerup', finish);
        el.addEventListener('pointercancel', finish);
        el.addEventListener('dblclick', () => enlarge(entry));

        el.addEventListener('focus', () => { if (selected !== entry) select(entry); });
        el.addEventListener('keydown', event => {
            const key = event.key;
            if (key === 'r' || key === 'R') { event.preventDefault(); rotate(entry, event.shiftKey ? -90 : 90); }
            else if (key === 'f' || key === 'F') { event.preventDefault(); flip(entry); }
            else if (key === 'Enter' || key === ' ') { event.preventDefault(); enlarge(entry); }
            else if (key === 'Escape') { select(null); el.blur(); }
            else if (key.startsWith('Arrow')) {
                event.preventDefault();
                const step = event.shiftKey ? 50 : 10;
                const previous = snapshot(entry.data);
                if (key === 'ArrowLeft') entry.data.x = Math.max(0, entry.data.x - step);
                if (key === 'ArrowRight') entry.data.x = Math.min(width - 40, entry.data.x + step);
                if (key === 'ArrowUp') entry.data.y = Math.max(0, entry.data.y - step);
                if (key === 'ArrowDown') entry.data.y = Math.min(height - 40, entry.data.y + step);
                render(entry);
                placeActions();
                clearTimeout(entry.nudgeTimer);
                entry.nudgeTimer = setTimeout(() => saveCard(entry, {x: entry.data.x, y: entry.data.y}, previous), 250);
            }
        });
    }

    // --------------------------------------------------------------- panning
    // Mouse/pen: drag empty felt to pan. Touch: the viewport scrolls natively.
    let pan = null;
    viewport.addEventListener('pointerdown', event => {
        if (event.pointerType === 'touch' || event.button !== 0) return;
        if (event.target.closest('.dealer-card')) return;
        select(null);
        pan = {x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop};
        viewport.setPointerCapture(event.pointerId);
        viewport.classList.add('is-panning');
    });
    viewport.addEventListener('pointermove', event => {
        if (!pan) return;
        viewport.scrollLeft = pan.left - (event.clientX - pan.x);
        viewport.scrollTop = pan.top - (event.clientY - pan.y);
    });
    const endPan = () => { pan = null; viewport.classList.remove('is-panning'); };
    viewport.addEventListener('pointerup', endPan);
    viewport.addEventListener('pointercancel', endPan);
    viewport.addEventListener('click', event => {
        if (event.pointerType === 'touch' && !event.target.closest('.dealer-card')) select(null);
    });
    viewport.addEventListener('scroll', placeActions, {passive: true});
    window.addEventListener('resize', placeActions);

    // Ctrl/⌘ + wheel (and trackpad pinch) zooms around the pointer.
    viewport.addEventListener('wheel', event => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        stepZoom(event.deltaY < 0 ? 1 : -1, {x: event.clientX, y: event.clientY});
    }, {passive: false});

    // ---------------------------------------------------------------- drawing
    function updateStack(deckId, remaining) {
        const stack = document.querySelector(`.deck-stack[data-deck-id="${deckId}"]`);
        if (!stack) return;
        stack.dataset.remaining = remaining;
        stack.querySelector('[data-count]').textContent = remaining;
        stack.disabled = remaining < 1;
    }

    document.querySelectorAll('.deck-stack').forEach(stack => {
        stack.addEventListener('click', async () => {
            stack.disabled = true;
            // Deal into the middle of whatever part of the table is in view.
            const offset = (dealt++ % 6) * 24;
            const x = Math.max(0, Math.min(width - CARD_W, (viewport.scrollLeft + viewport.clientWidth / 2) / zoom - CARD_W / 2 + offset));
            const y = Math.max(0, Math.min(height - 200, (viewport.scrollTop + viewport.clientHeight / 2) / zoom - 100 + offset));
            try {
                const data = await post(felt.dataset.drawUrl, {deck_id: +stack.dataset.deckId, x, y, face_down: faceDownToggle.checked});
                const entry = build(data);
                entry.el.classList.add('is-new');
                select(entry);
                updateStack(data.deck_id, data.remaining);
                say(`Drew ${data.face_down ? 'a face-down card' : (data.name || `card ${data.order}`)} from ${data.deck_name}.`);
            } catch (error) {
                say(error.message);
                stack.disabled = +stack.dataset.remaining < 1;
            }
        });
    });

    // --------------------------------------------------------------- toolbar
    document.querySelectorAll('[data-zoom]').forEach(button => {
        button.addEventListener('click', () => stepZoom(+button.dataset.zoom));
    });
    document.querySelectorAll('[data-grow]').forEach(button => {
        button.addEventListener('click', () => (button.dataset.grow === 'fit' ? fitToCards() : grow(button.dataset.grow)));
    });

    viewer.querySelector('[data-close]').addEventListener('click', () => viewer.close());
    viewer.addEventListener('click', event => { if (event.target === viewer) viewer.close(); });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && selected && !viewer.open) select(null);
    });

    // ------------------------------------------------------------------ init
    applySize();
    JSON.parse(document.getElementById('table-cards').textContent).forEach(build);
})();
