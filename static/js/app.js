/* Solo TTRPG Tools - Client JavaScript */

// Random Name Fetcher for New Dungeon screen
async function fetchRandomName() {
    const typeSelect = document.getElementById("dungeon_type");
    const nameInput = document.getElementById("dungeon-name-input");
    if (!typeSelect || !nameInput) return;

    const selectedType = typeSelect.value;
    try {
        const res = await fetch(`/api/random-name?type=${encodeURIComponent(selectedType)}`);
        if (res.ok) {
            const data = await res.json();
            nameInput.value = data.name;
        }
    } catch (err) {
        console.error("Failed to fetch random name:", err);
    }
}

// Log Modal Functions
async function openLogModal(dungeonId) {
    const modal = document.getElementById("log-modal");
    const container = document.getElementById("modal-log-entries");
    const title = document.getElementById("modal-dungeon-title");
    const exportTxt = document.getElementById("export-txt-link");
    const exportMd = document.getElementById("export-md-link");

    if (!modal || !container) return;

    modal.classList.remove("hidden");
    container.innerHTML = '<p class="text-muted">Loading exploration records...</p>';

    exportTxt.href = `/dungeon/${dungeonId}/export?format=txt`;
    exportMd.href = `/dungeon/${dungeonId}/export?format=md`;

    try {
        const res = await fetch(`/dungeon/${dungeonId}/log`);
        if (res.ok) {
            const data = await res.json();
            title.textContent = `${data.dungeon_name.toUpperCase()} — LOG`;

            if (!data.logs || data.logs.length === 0) {
                container.innerHTML = '<p class="text-muted">No log entries found.</p>';
                return;
            }

            container.innerHTML = data.logs.map(entry => `
                <div class="log-entry-item">
                    <span class="log-entry-time">${entry.formatted_time}</span>
                    <span class="log-entry-text">${entry.entry}</span>
                </div>
            `).join("");
        } else {
            container.innerHTML = '<p class="text-muted">Could not load logs.</p>';
        }
    } catch (err) {
        console.error("Error fetching logs:", err);
        container.innerHTML = '<p class="text-muted">Error retrieving log entries.</p>';
    }
}

function closeLogModal(event) {
    if (event && event.target && event.target.closest(".modal-card") && !event.target.classList.contains("btn-close")) {
        return;
    }
    const modal = document.getElementById("log-modal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

// Delete Confirmation Modal Functions
function confirmDeleteDungeon(dungeonId, dungeonName) {
    const modal = document.getElementById("delete-modal");
    const nameSpan = document.getElementById("delete-dungeon-name");
    const form = document.getElementById("delete-form");

    if (!modal || !form) return;

    if (nameSpan) nameSpan.textContent = dungeonName;
    form.action = `/dungeon/${dungeonId}/delete`;
    modal.classList.remove("hidden");
}

function closeDeleteModal(event) {
    if (event && event.target && event.target.closest(".modal-card") && !event.target.classList.contains("btn-close")) {
        return;
    }
    const modal = document.getElementById("delete-modal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

// Keyboard escape to close modals
document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
        closeLogModal();
        closeDeleteModal();
    }
});
