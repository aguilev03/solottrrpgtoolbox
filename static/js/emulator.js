/**
 * Solo TTRPG Tools — Character Emulator Frontend JavaScript
 */

let allNpcLibrary = [];
let pendingDeleteNpcId = null;

document.addEventListener("DOMContentLoaded", () => {
    // Initialization if needed
});

/* ==========================================
   MODAL UTILITIES
   ========================================== */

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove("hidden");
        // Focus first input
        const firstInput = modal.querySelector("input, select, textarea");
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 50);
        }
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add("hidden");
    }
}

function closeModalOnBackdrop(event, modalId) {
    if (event.target && event.target.id === modalId) {
        closeModal(modalId);
    }
}

/* ==========================================
   CARD STATUS TOGGLING (CURRENT & PARTY)
   ========================================== */

function showCardFeedback(npcId, message, isError = true) {
    const feedback = document.getElementById(`card-feedback-${npcId}`);
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className = `card-feedback-msg ${isError ? "error" : "success"}`;
    feedback.classList.remove("hidden");
    setTimeout(() => {
        feedback.classList.add("hidden");
    }, 4000);
}

async function handleCardCurrentToggle(npcId, checkbox) {
    const partyCheckbox = document.getElementById(`card-chk-party-${npcId}`);
    const isParty = partyCheckbox && partyCheckbox.checked;

    // RULE: Party Members are always Current. Prevent unchecking while Party Member is active!
    if (!checkbox.checked && isParty) {
        checkbox.checked = true; // Revert checkbox
        showCardFeedback(npcId, "Party Members are always Current. Uncheck Party Member first.", true);
        return;
    }

    try {
        const res = await fetch(`/emulator/npc/${npcId}/toggle-status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ current: checkbox.checked })
        });
        const data = await res.json();
        if (!data.success) {
            checkbox.checked = !checkbox.checked;
            showCardFeedback(npcId, data.error || "Failed to update status.", true);
        } else {
            // If removed from current, reload to cleanly reflow sections
            if (!checkbox.checked) {
                window.location.reload();
            }
        }
    } catch (err) {
        checkbox.checked = !checkbox.checked;
        showCardFeedback(npcId, "Network error updating status.", true);
    }
}

async function handleCardPartyToggle(npcId, checkbox) {
    const currentCheckbox = document.getElementById(`card-chk-current-${npcId}`);

    // RULE: If Party Member becomes true, Current MUST become true
    if (checkbox.checked && currentCheckbox) {
        currentCheckbox.checked = true;
    }

    try {
        const payload = { party_member: checkbox.checked };
        if (checkbox.checked) {
            payload.current = true;
        }
        const res = await fetch(`/emulator/npc/${npcId}/toggle-status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) {
            checkbox.checked = !checkbox.checked;
            showCardFeedback(npcId, data.error || "Failed to update status.", true);
        } else {
            // Reload page to move between Party Members and Current NPCs sections
            window.location.reload();
        }
    } catch (err) {
        checkbox.checked = !checkbox.checked;
        showCardFeedback(npcId, "Network error updating status.", true);
    }
}

/* ==========================================
   ROLL ACTION
   ========================================== */

async function handleRollAction(npcId) {
    const select = document.getElementById(`action-select-${npcId}`);
    const resultsContainer = document.getElementById(`action-results-${npcId}`);
    const btn = document.getElementById(`btn-roll-act-${npcId}`);

    if (!select || !resultsContainer) return;
    const actionType = select.value;

    if (btn) btn.disabled = true;

    try {
        const res = await fetch(`/emulator/npc/${npcId}/roll-action`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action_type: actionType })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to roll action.");
            return;
        }

        renderActionResults(resultsContainer, data.results, actionType, npcId);
    } catch (err) {
        alert("Error rolling action: " + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderActionResults(container, results, actionType, npcId) {
    const numIcons = ["①", "②", "③"];
    let html = `
        <div class="action-results-card">
            <div class="action-results-header">
                <span class="action-header-type">${escapeHtml(actionType.toUpperCase())}</span>
            </div>
            <div class="action-results-list">
    `;

    results.forEach((item, idx) => {
        const num = numIcons[idx] || `${idx + 1}.`;
        const trait = item.trait;
        const isPlaceholder = trait.is_placeholder;

        let statusClass = "badge-default";
        if (trait.status && trait.status.toLowerCase() === "prevalent") statusClass = "badge-prevalent";
        if (trait.status && trait.status.toLowerCase() === "temporary") statusClass = "badge-temporary";

        let toClass = "badge-option";
        if (item.triple_o_classification === "THE ODD") toClass = "badge-odd";
        if (item.triple_o_classification === "THE OBVIOUS") toClass = "badge-obvious";

        html += `
            <div class="action-prompt-item">
                <div class="prompt-header">
                    <span class="prompt-num">${num}</span>
                    <span class="prompt-trait-meta">
                        <span class="prompt-trait-status ${statusClass}">${escapeHtml(trait.status.toUpperCase())}</span>
                        ${trait.category ? `<span class="prompt-meta-sep">•</span><span class="prompt-trait-cat">${escapeHtml(trait.category)}</span>` : ""}
                    </span>
                </div>
                <div class="prompt-trait-name">${escapeHtml(trait.trait)}</div>
                <div class="prompt-action-line">
                    <span class="prompt-d66">${item.d66}</span>
                    <span class="prompt-dash">—</span>
                    <span class="prompt-action-text">${escapeHtml(item.action)}</span>
                </div>
                <div class="prompt-triple-o-line">
                    <span class="triple-o-badge ${toClass}">Triple-O: ${item.triple_o_roll} — ${item.triple_o_classification}</span>
                </div>
            </div>
        `;
    });

    html += `
            </div>
            <div class="action-results-footer">
                <button type="button" class="btn btn-xs btn-outline" onclick="handleRollAction(${npcId})">&#8635; Roll Again</button>
            </div>
        </div>
    `;

    container.innerHTML = html;
    container.classList.remove("hidden");
}

/* ==========================================
   ROLL SPARK
   ========================================== */

async function handleRollSpark(npcId) {
    const select = document.getElementById(`spark-select-${npcId}`);
    const resultsContainer = document.getElementById(`spark-results-${npcId}`);
    const btn = document.getElementById(`btn-roll-spk-${npcId}`);

    if (!select || !resultsContainer) return;
    const sparkType = select.value;

    if (btn) btn.disabled = true;

    try {
        const res = await fetch(`/emulator/npc/${npcId}/roll-spark`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ spark_type: sparkType })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to roll spark.");
            return;
        }

        renderSparkResults(resultsContainer, data.spark, npcId);
    } catch (err) {
        alert("Error rolling spark: " + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderSparkResults(container, spark, npcId) {
    let rollsHtml = "";
    const isCombo = spark.type === "combination";

    spark.rolls.forEach(r => {
        rollsHtml += `
            <div class="spark-roll-line">
                ${isCombo ? `<span class="spark-line-table">${escapeHtml(r.table)}:</span>` : ""}
                <span class="spark-line-d66">${r.d66}</span>
                <span class="spark-line-sep">—</span>
                <span class="spark-line-result">${escapeHtml(r.result)}</span>
            </div>
        `;
    });

    const html = `
        <div class="spark-result-card">
            <div class="spark-result-header">
                <span class="spark-label">SPARK</span>
                <span class="spark-table-name">${escapeHtml(spark.display_name)}</span>
                <button type="button" class="btn-spark-reroll" title="Roll another Spark" onclick="handleRollSpark(${npcId})">&#8635;</button>
            </div>
            <div class="spark-rolls-body">
                ${rollsHtml}
            </div>
        </div>
    `;

    container.innerHTML = html;
    container.classList.remove("hidden");
}

/* ==========================================
   ADD NPC MODAL
   ========================================== */

function openAddNpcModal() {
    const form = document.getElementById("form-add-npc");
    if (form) form.reset();
    document.getElementById("add-npc-current").checked = true;
    document.getElementById("add-npc-party").checked = false;
    document.getElementById("add-traits-container").innerHTML = "";
    const feedback = document.getElementById("add-npc-feedback");
    if (feedback) feedback.classList.add("hidden");
    openModal("modal-add-npc");
}

function handleAddCurrentChange() {
    const currentChk = document.getElementById("add-npc-current");
    const partyChk = document.getElementById("add-npc-party");
    const feedback = document.getElementById("add-npc-feedback");

    if (!currentChk.checked && partyChk.checked) {
        currentChk.checked = true;
        if (feedback) {
            feedback.textContent = "Party Members are always Current. Uncheck Party Member first.";
            feedback.classList.remove("hidden");
            setTimeout(() => feedback.classList.add("hidden"), 3500);
        }
    }
}

function handleAddPartyChange() {
    const currentChk = document.getElementById("add-npc-current");
    const partyChk = document.getElementById("add-npc-party");

    if (partyChk.checked) {
        currentChk.checked = true;
    }
}

function addTraitRowToBuilder(containerId, status = "default", trait = "", category = "PR") {
    const container = document.getElementById(containerId);
    if (!container) return;

    const rowId = "trait-builder-" + Math.random().toString(36).substr(2, 9);
    const row = document.createElement("div");
    row.className = "trait-builder-row";
    row.id = rowId;

    row.innerHTML = `
        <select class="form-select trait-builder-status">
            <option value="default" ${status === "default" ? "selected" : ""}>Default</option>
            <option value="prevalent" ${status === "prevalent" ? "selected" : ""}>Prevalent</option>
            <option value="temporary" ${status === "temporary" ? "selected" : ""}>Temporary</option>
        </select>
        <input type="text" class="form-input trait-builder-text" placeholder="Trait description..." value="${escapeHtml(trait)}" required>
        <select class="form-select trait-builder-cat">
            <option value="PR" ${category === "PR" ? "selected" : ""}>PR</option>
            <option value="SK" ${category === "SK" ? "selected" : ""}>SK</option>
            <option value="BG" ${category === "BG" ? "selected" : ""}>BG</option>
            <option value="CL" ${category === "CL" ? "selected" : ""}>CL</option>
            <option value="CN" ${category === "CN" ? "selected" : ""}>CN</option>
            <option value="MT" ${category === "MT" ? "selected" : ""}>MT</option>
            ${!["PR","SK","BG","CL","CN","MT"].includes(category) && category ? `<option value="${escapeHtml(category)}" selected>${escapeHtml(category)}</option>` : ""}
            <option value="CUSTOM">Custom...</option>
        </select>
        <button type="button" class="btn btn-xs btn-outline btn-builder-del" onclick="removeTraitRow('${rowId}')">&times;</button>
    `;

    container.appendChild(row);
}

function removeTraitRow(rowId) {
    const elem = document.getElementById(rowId);
    if (elem) elem.remove();
}

async function submitAddNpc(event) {
    event.preventDefault();
    const nameInput = document.getElementById("add-npc-name");
    const detailsInput = document.getElementById("add-npc-details");
    const currentChk = document.getElementById("add-npc-current");
    const partyChk = document.getElementById("add-npc-party");
    const container = document.getElementById("add-traits-container");

    const name = nameInput.value.trim();
    if (!name) return;

    // Collect traits
    const traits = [];
    if (container) {
        const rows = container.querySelectorAll(".trait-builder-row");
        rows.forEach(r => {
            const status = r.querySelector(".trait-builder-status").value;
            const text = r.querySelector(".trait-builder-text").value.trim();
            const catSelect = r.querySelector(".trait-builder-cat");
            let cat = catSelect.value;
            if (cat === "CUSTOM") cat = "PR";
            if (text) {
                traits.push({ status, trait: text, category: cat });
            }
        });
    }

    try {
        const res = await fetch("/emulator/npc/new", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                details: detailsInput.value.trim(),
                current: currentChk.checked,
                party_member: partyChk.checked,
                traits
            })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to create NPC.");
            return;
        }
        closeModal("modal-add-npc");
        window.location.reload();
    } catch (err) {
        alert("Network error: " + err.message);
    }
}

/* ==========================================
   QUICK ADD TRAIT MODAL
   ========================================== */

function openQuickAddTraitModal(npcId, npcName) {
    document.getElementById("quick-trait-npc-id").value = npcId;
    document.getElementById("quick-trait-modal-title").textContent = `ADD TRAIT — ${npcName.toUpperCase()}`;
    document.getElementById("quick-trait-text").value = "";
    document.getElementById("quick-trait-status").value = "default";
    document.getElementById("quick-trait-category").value = "PR";
    document.getElementById("quick-trait-custom-cat").classList.add("hidden");
    document.getElementById("quick-trait-custom-cat").value = "";
    openModal("modal-quick-trait");
}

function handleCategorySelectChange(selectElem, customInputId) {
    const customInput = document.getElementById(customInputId);
    if (!customInput) return;
    if (selectElem.value === "CUSTOM") {
        customInput.classList.remove("hidden");
        customInput.focus();
    } else {
        customInput.classList.add("hidden");
    }
}

async function submitQuickTrait(event) {
    event.preventDefault();
    const npcId = document.getElementById("quick-trait-npc-id").value;
    const status = document.getElementById("quick-trait-status").value;
    const traitText = document.getElementById("quick-trait-text").value.trim();
    const catSelect = document.getElementById("quick-trait-category");
    let category = catSelect.value;

    if (category === "CUSTOM") {
        const customCat = document.getElementById("quick-trait-custom-cat").value.trim().toUpperCase();
        category = customCat || "PR";
    }

    if (!traitText) return;

    try {
        const res = await fetch(`/emulator/npc/${npcId}/traits/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status, trait: traitText, category })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to add trait.");
            return;
        }

        // Add to DOM list immediately
        const list = document.getElementById(`traits-list-${npcId}`);
        if (list) {
            const placeholder = list.querySelector(".no-traits-placeholder");
            if (placeholder) placeholder.remove();

            const statusClass = `badge-${status.toLowerCase()}`;
            const row = document.createElement("div");
            row.className = "trait-row";
            row.id = `card-trait-${data.trait.id}`;
            row.innerHTML = `
                <span class="trait-status-badge ${statusClass}">${escapeHtml(data.trait.status)}</span>
                <span class="trait-text">${escapeHtml(data.trait.trait)}</span>
                <span class="trait-category-tag">${escapeHtml(data.trait.category)}</span>
            `;
            list.appendChild(row);
        }

        closeModal("modal-quick-trait");
    } catch (err) {
        alert("Network error adding trait: " + err.message);
    }
}

/* ==========================================
   EDIT NPC MODAL
   ========================================== */

async function openEditNpcModal(npcId) {
    try {
        const res = await fetch(`/emulator/api/npcs?q=`);
        const data = await res.json();
        if (!data.success) return;

        const npc = data.npcs.find(n => n.id === npcId);
        if (!npc) {
            alert("Character not found.");
            return;
        }

        document.getElementById("edit-npc-id").value = npc.id;
        document.getElementById("edit-npc-name").value = npc.name;
        document.getElementById("edit-npc-details").value = npc.details || "";
        document.getElementById("edit-npc-current").checked = npc.current;
        document.getElementById("edit-npc-party").checked = npc.party_member;
        document.getElementById("edit-npc-modal-title").textContent = `EDIT NPC — ${npc.name.toUpperCase()}`;

        const container = document.getElementById("edit-traits-container");
        container.innerHTML = "";

        if (npc.traits && npc.traits.length > 0) {
            npc.traits.forEach(t => {
                addTraitRowToBuilder("edit-traits-container", t.status.toLowerCase(), t.trait, t.category);
            });
        }

        const feedback = document.getElementById("edit-npc-feedback");
        if (feedback) feedback.classList.add("hidden");

        openModal("modal-edit-npc");
    } catch (err) {
        alert("Error loading character details: " + err.message);
    }
}

function handleEditCurrentChange() {
    const currentChk = document.getElementById("edit-npc-current");
    const partyChk = document.getElementById("edit-npc-party");
    const feedback = document.getElementById("edit-npc-feedback");

    if (!currentChk.checked && partyChk.checked) {
        currentChk.checked = true;
        if (feedback) {
            feedback.textContent = "Party Members are always Current. Uncheck Party Member first.";
            feedback.classList.remove("hidden");
            setTimeout(() => feedback.classList.add("hidden"), 3500);
        }
    }
}

function handleEditPartyChange() {
    const currentChk = document.getElementById("edit-npc-current");
    const partyChk = document.getElementById("edit-npc-party");

    if (partyChk.checked) {
        currentChk.checked = true;
    }
}

async function submitEditNpc(event) {
    event.preventDefault();
    const npcId = document.getElementById("edit-npc-id").value;
    const name = document.getElementById("edit-npc-name").value.trim();
    const details = document.getElementById("edit-npc-details").value.trim();
    const current = document.getElementById("edit-npc-current").checked;
    const partyMember = document.getElementById("edit-npc-party").checked;
    const container = document.getElementById("edit-traits-container");

    if (!name) return;

    // Collect traits
    const traits = [];
    if (container) {
        const rows = container.querySelectorAll(".trait-builder-row");
        rows.forEach(r => {
            const status = r.querySelector(".trait-builder-status").value;
            const text = r.querySelector(".trait-builder-text").value.trim();
            const catSelect = r.querySelector(".trait-builder-cat");
            let cat = catSelect.value;
            if (cat === "CUSTOM") cat = "PR";
            if (text) {
                traits.push({ status, trait: text, category: cat });
            }
        });
    }

    try {
        const res = await fetch(`/emulator/npc/${npcId}/edit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                details,
                current,
                party_member: partyMember,
                traits
            })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to update NPC.");
            return;
        }

        closeModal("modal-edit-npc");
        window.location.reload();
    } catch (err) {
        alert("Network error updating NPC: " + err.message);
    }
}

/* ==========================================
   FIND NPC MODAL
   ========================================== */

async function openFindNpcModal() {
    openModal("modal-find-npc");
    const searchInput = document.getElementById("find-npc-search");
    if (searchInput) searchInput.value = "";
    await loadFindNpcList("");
}

async function loadFindNpcList(query) {
    const container = document.getElementById("find-npc-results");
    if (!container) return;

    try {
        const res = await fetch(`/emulator/api/npcs?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (!data.success) return;

        allNpcLibrary = data.npcs;
        renderFindNpcList(data.npcs);
    } catch (err) {
        container.innerHTML = `<p class="text-danger">Failed to load characters.</p>`;
    }
}

function handleFindNpcSearch() {
    const query = document.getElementById("find-npc-search").value.toLowerCase().trim();
    if (!allNpcLibrary) return;

    const filtered = allNpcLibrary.filter(n => {
        if (n.name.toLowerCase().includes(query)) return true;
        if (n.details && n.details.toLowerCase().includes(query)) return true;
        if (n.traits && n.traits.some(t => t.trait.toLowerCase().includes(query))) return true;
        return false;
    });

    renderFindNpcList(filtered);
}

function renderFindNpcList(npcs) {
    const container = document.getElementById("find-npc-results");
    if (!container) return;

    if (!npcs || npcs.length === 0) {
        container.innerHTML = `<p class="text-muted text-center" style="padding: 1.5rem 0;">No matching characters found.</p>`;
        return;
    }

    let html = "";
    npcs.forEach(npc => {
        const traitCount = npc.traits ? npc.traits.length : 0;
        const traitText = traitCount === 1 ? "1 Trait" : `${traitCount} Traits`;

        html += `
            <div class="find-npc-item">
                <div class="find-npc-info">
                    <div class="find-npc-title-row">
                        <strong class="find-npc-name">${escapeHtml(npc.name)}</strong>
                        ${npc.party_member ? `<span class="badge-party-member">Party</span>` : ""}
                        ${npc.current ? `<span class="badge-current-tag">Current</span>` : `<span class="badge-library-tag">Library</span>`}
                    </div>
                    ${npc.details ? `<p class="find-npc-details">${escapeHtml(npc.details)}</p>` : ""}
                    <div class="find-npc-meta">${traitText}</div>
                </div>
                <div class="find-npc-actions">
                    ${!npc.current ? `<button type="button" class="btn btn-sm btn-primary" onclick="makeCurrentFromFindModal(${npc.id})">Make Current</button>` : `<span class="status-active-label">In Scene</span>`}
                    <button type="button" class="btn btn-sm btn-secondary" onclick="closeModal('modal-find-npc'); openEditNpcModal(${npc.id})">Edit</button>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

async function makeCurrentFromFindModal(npcId) {
    try {
        const res = await fetch(`/emulator/npc/${npcId}/make-current`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to make NPC current.");
            return;
        }
        closeModal("modal-find-npc");
        window.location.reload();
    } catch (err) {
        alert("Network error: " + err.message);
    }
}

/* ==========================================
   MANAGE NPCs MODAL
   ========================================== */

async function openManageNpcsModal() {
    openModal("modal-manage-npcs");
    const searchInput = document.getElementById("manage-npc-search");
    if (searchInput) searchInput.value = "";
    await loadManageNpcTable("");
}

async function loadManageNpcTable(query) {
    const tbody = document.getElementById("manage-npc-tbody");
    if (!tbody) return;

    try {
        const res = await fetch(`/emulator/api/npcs?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (!data.success) return;

        allNpcLibrary = data.npcs;
        renderManageNpcTable(data.npcs);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-danger text-center">Failed to load characters.</td></tr>`;
    }
}

function handleManageNpcSearch() {
    const query = document.getElementById("manage-npc-search").value.toLowerCase().trim();
    if (!allNpcLibrary) return;

    const filtered = allNpcLibrary.filter(n => {
        if (n.name.toLowerCase().includes(query)) return true;
        if (n.details && n.details.toLowerCase().includes(query)) return true;
        if (n.traits && n.traits.some(t => t.trait.toLowerCase().includes(query))) return true;
        return false;
    });

    renderManageNpcTable(filtered);
}

function renderManageNpcTable(npcs) {
    const tbody = document.getElementById("manage-npc-tbody");
    if (!tbody) return;

    if (!npcs || npcs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-muted text-center" style="padding: 1.5rem 0;">No characters in library.</td></tr>`;
        return;
    }

    let html = "";
    npcs.forEach(npc => {
        const traitCount = npc.traits ? npc.traits.length : 0;
        const partyChecked = npc.party_member ? "&#10003;" : "&mdash;";
        const currentChecked = npc.current ? "&#10003;" : "&mdash;";

        html += `
            <tr class="manage-row">
                <td class="manage-cell-name">
                    <strong>${escapeHtml(npc.name)}</strong>
                    ${npc.details ? `<div class="manage-npc-subdetails">${escapeHtml(npc.details)}</div>` : ""}
                </td>
                <td class="text-center font-bold">${partyChecked}</td>
                <td class="text-center font-bold">${currentChecked}</td>
                <td class="text-center">${traitCount}</td>
                <td class="manage-cell-actions text-right">
                    ${npc.current ? 
                        `<button type="button" class="btn btn-xs btn-outline" onclick="removeCurrentFromManageModal(${npc.id})">Remove Current</button>` : 
                        `<button type="button" class="btn btn-xs btn-primary" onclick="makeCurrentFromManageModal(${npc.id})">Make Current</button>`}
                    <button type="button" class="btn btn-xs btn-secondary" onclick="closeModal('modal-manage-npcs'); openEditNpcModal(${npc.id})">Edit</button>
                    <button type="button" class="btn btn-xs btn-danger" onclick="promptDeleteNpc(${npc.id}, '${escapeHtml(npc.name)}')">Delete</button>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

async function makeCurrentFromManageModal(npcId) {
    try {
        const res = await fetch(`/emulator/npc/${npcId}/make-current`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to make current.");
            return;
        }
        await loadManageNpcTable(document.getElementById("manage-npc-search").value);
    } catch (err) {
        alert("Network error: " + err.message);
    }
}

async function removeCurrentFromManageModal(npcId) {
    try {
        const res = await fetch(`/emulator/npc/${npcId}/remove-current`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to remove from current.");
            return;
        }
        await loadManageNpcTable(document.getElementById("manage-npc-search").value);
    } catch (err) {
        alert("Network error: " + err.message);
    }
}

/* ==========================================
   PERMANENT DELETION WITH CONFIRMATION
   ========================================== */

function promptDeleteNpc(npcId, npcName) {
    pendingDeleteNpcId = npcId;
    document.getElementById("delete-npc-name-display").textContent = `"${npcName}"`;
    const confirmBtn = document.getElementById("btn-confirm-delete-action");
    confirmBtn.onclick = executePendingDelete;
    openModal("modal-confirm-delete");
}

async function executePendingDelete() {
    if (!pendingDeleteNpcId) return;

    try {
        const res = await fetch(`/emulator/npc/${pendingDeleteNpcId}/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || "Failed to delete character.");
            return;
        }

        closeModal("modal-confirm-delete");
        pendingDeleteNpcId = null;

        // If manage modal is open, refresh table
        const manageModal = document.getElementById("modal-manage-npcs");
        if (manageModal && !manageModal.classList.contains("hidden")) {
            await loadManageNpcTable(document.getElementById("manage-npc-search").value);
        } else {
            window.location.reload();
        }
    } catch (err) {
        alert("Network error deleting character: " + err.message);
    }
}

/* ==========================================
   ESCAPE HTML UTILITY
   ========================================== */

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
