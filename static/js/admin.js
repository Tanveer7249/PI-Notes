/**
 * admin.js
 * ───────────────────────────────────────────────────────────────────────────
 * Handles all admin-side dynamic UI:
 *   1. Dynamic option field management (add/remove options on question form)
 *   2. Correct-option radio group sync
 *   3. CSV file preview before upload
 *   4. Delete confirmation dialogs
 *   5. Test publish toggle confirmation
 *   6. Character counter for question text
 * ───────────────────────────────────────────────────────────────────────────
 */

// ─────────────────────────────────────────────────────────────────────────────
// 1. DYNAMIC OPTION FIELDS
// The question form starts with 4 option inputs.
// Admin can add up to 6 options or remove down to 2.
// ─────────────────────────────────────────────────────────────────────────────
const optionsContainer = document.getElementById("options-container");
const addOptionBtn     = document.getElementById("add-option-btn");
const MAX_OPTIONS      = 6;
const MIN_OPTIONS      = 2;

/**
 * Count current option rows.
 */
function getOptionCount() {
    if (!optionsContainer) return 0;
    return optionsContainer.querySelectorAll(".option-row").length;
}

/**
 * Re-index all option rows so labels, names, and values stay consistent
 * after adding or removing a row.
 */
function reindexOptions() {
    if (!optionsContainer) return;
    const rows = optionsContainer.querySelectorAll(".option-row");
    rows.forEach((row, idx) => {
        const label  = row.querySelector(".option-label");
        const input  = row.querySelector("input[type='text']");
        const radio  = row.querySelector("input[type='radio']");
        const letter = String.fromCharCode(65 + idx); // A, B, C, D…

        if (label)  label.textContent   = `Option ${letter}`;
        if (input)  input.name          = "option_text";
        if (radio)  radio.value         = String(idx);

        // Update remove-button visibility
        const removeBtn = row.querySelector(".remove-option-btn");
        if (removeBtn) {
            removeBtn.style.display = getOptionCount() <= MIN_OPTIONS ? "none" : "inline-flex";
        }
    });

    // Update add-button visibility
    if (addOptionBtn) {
        addOptionBtn.style.display = getOptionCount() >= MAX_OPTIONS ? "none" : "inline-flex";
    }
}

/**
 * Create a new option row DOM element.
 */
function createOptionRow(index) {
    const letter = String.fromCharCode(65 + index);
    const row    = document.createElement("div");
    row.className = "option-row flex items-center gap-3 mb-3";
    row.innerHTML = `
        <input type="radio"
               name="correct_option"
               value="${index}"
               class="w-4 h-4 text-indigo-600 border-gray-300 focus:ring-indigo-500"
               title="Mark as correct answer" />
        <span class="option-label w-20 text-sm font-medium text-gray-600">Option ${letter}</span>
        <input type="text"
               name="option_text"
               placeholder="Enter option ${letter}"
               required
               class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm
                      focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500" />
        <button type="button"
                class="remove-option-btn inline-flex items-center justify-center
                       w-8 h-8 rounded-full bg-red-100 text-red-600
                       hover:bg-red-200 transition-colors text-sm font-bold"
                title="Remove this option">
            ✕
        </button>
    `;

    // Wire up remove button
    row.querySelector(".remove-option-btn").addEventListener("click", () => {
        if (getOptionCount() <= MIN_OPTIONS) return;
        row.remove();
        reindexOptions();
    });

    return row;
}

// Wire up the "Add Option" button
if (addOptionBtn) {
    addOptionBtn.addEventListener("click", () => {
        if (getOptionCount() >= MAX_OPTIONS) return;
        const idx = getOptionCount();
        const row = createOptionRow(idx);
        optionsContainer.appendChild(row);
        reindexOptions();
    });
}

// Wire up remove buttons that already exist in the DOM (first 4 options)
if (optionsContainer) {
    optionsContainer.querySelectorAll(".remove-option-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (getOptionCount() <= MIN_OPTIONS) return;
            btn.closest(".option-row").remove();
            reindexOptions();
        });
    });

    // Initial visibility pass
    reindexOptions();
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. CORRECT OPTION HIGHLIGHT
// When admin selects a radio for the correct option, highlight that row.
// ─────────────────────────────────────────────────────────────────────────────
function syncCorrectHighlight() {
    if (!optionsContainer) return;
    optionsContainer.querySelectorAll(".option-row").forEach((row) => {
        const radio  = row.querySelector("input[type='radio']");
        const input  = row.querySelector("input[type='text']");
        if (radio && radio.checked) {
            row.classList.add("bg-green-50", "border", "border-green-300", "rounded-lg", "px-2");
            if (input) input.classList.add("border-green-400");
        } else {
            row.classList.remove("bg-green-50", "border", "border-green-300", "rounded-lg", "px-2");
            if (input) input.classList.remove("border-green-400");
        }
    });
}

document.querySelectorAll("input[name='correct_option']").forEach((radio) => {
    radio.addEventListener("change", syncCorrectHighlight);
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. CSV FILE PREVIEW
// When admin selects a CSV file for import, show a preview of the first 5 rows.
// ─────────────────────────────────────────────────────────────────────────────
const csvInput   = document.getElementById("csv-file-input");
const csvPreview = document.getElementById("csv-preview");

if (csvInput && csvPreview) {
    csvInput.addEventListener("change", () => {
        const file = csvInput.files[0];
        if (!file) {
            csvPreview.innerHTML = "";
            return;
        }

        if (!file.name.endsWith(".csv")) {
            csvPreview.innerHTML = `<p class="text-sm text-red-600 mt-2">⚠️ Please select a .csv file.</p>`;
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const lines = e.target.result.split("\n").filter((l) => l.trim() !== "");
            if (lines.length < 2) {
                csvPreview.innerHTML = `<p class="text-sm text-red-600 mt-2">CSV appears to be empty.</p>`;
                return;
            }

            const headers = lines[0].split(",").map((h) => h.trim());
            const preview = lines.slice(1, 6); // First 5 data rows

            let html = `
                <div class="mt-4">
                    <p class="text-sm font-medium text-gray-700 mb-2">
                        Preview (first ${Math.min(5, preview.length)} of ${lines.length - 1} rows):
                    </p>
                    <div class="overflow-x-auto rounded-lg border border-gray-200">
                        <table class="min-w-full text-xs divide-y divide-gray-200">
                            <thead class="bg-gray-50">
                                <tr>
                                    ${headers.map((h) => `<th class="px-3 py-2 text-left font-medium text-gray-500 uppercase tracking-wider">${escapeHtml(h)}</th>`).join("")}
                                </tr>
                            </thead>
                            <tbody class="bg-white divide-y divide-gray-100">
            `;

            preview.forEach((line) => {
                const cells = line.split(",").map((c) => c.trim());
                html += `<tr>${cells.map((c) => `<td class="px-3 py-2 text-gray-700 max-w-xs truncate">${escapeHtml(c)}</td>`).join("")}</tr>`;
            });

            html += `
                            </tbody>
                        </table>
                    </div>
                    <p class="text-xs text-gray-400 mt-1">
                        Showing ${Math.min(5, preview.length)} of ${lines.length - 1} data rows.
                    </p>
                </div>
            `;

            csvPreview.innerHTML = html;
        };
        reader.readAsText(file);
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. DELETE CONFIRMATION DIALOGS
// All delete forms require a typed confirmation before submitting.
// ─────────────────────────────────────────────────────────────────────────────
document.querySelectorAll(".delete-form").forEach((form) => {
    form.addEventListener("submit", (e) => {
        const itemName = form.dataset.itemName || "this item";
        const confirmed = confirm(`Are you sure you want to delete "${itemName}"? This cannot be undone.`);
        if (!confirmed) e.preventDefault();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. PUBLISH TOGGLE CONFIRMATION
// ─────────────────────────────────────────────────────────────────────────────
document.querySelectorAll(".publish-form").forEach((form) => {
    form.addEventListener("submit", (e) => {
        const action     = form.dataset.published === "true" ? "unpublish" : "publish";
        const testName   = form.dataset.testName || "this test";
        const confirmed  = confirm(`Are you sure you want to ${action} "${testName}"?`);
        if (!confirmed) e.preventDefault();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. CHARACTER COUNTER FOR QUESTION TEXT
// ─────────────────────────────────────────────────────────────────────────────
const questionTextarea = document.getElementById("question-text");
const charCounter      = document.getElementById("char-counter");

if (questionTextarea && charCounter) {
    const MAX_CHARS = 1000;

    function updateCounter() {
        const remaining = MAX_CHARS - questionTextarea.value.length;
        charCounter.textContent = `${questionTextarea.value.length} / ${MAX_CHARS}`;
        if (remaining < 100) {
            charCounter.classList.add("text-red-500");
            charCounter.classList.remove("text-gray-400");
        } else {
            charCounter.classList.remove("text-red-500");
            charCounter.classList.add("text-gray-400");
        }
    }

    questionTextarea.addEventListener("input", updateCounter);
    updateCounter(); // Initialize on load
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. AUTO-DISMISS FLASH MESSAGES
// Flask flash messages auto-hide after 5 seconds.
// ─────────────────────────────────────────────────────────────────────────────
document.querySelectorAll(".flash-message").forEach((el) => {
    setTimeout(() => {
        el.style.transition = "opacity 0.5s";
        el.style.opacity    = "0";
        setTimeout(() => el.remove(), 500);
    }, 5000);
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. MARKS INPUT — Prevent negative values
// ─────────────────────────────────────────────────────────────────────────────
document.querySelectorAll("input[name='marks']").forEach((input) => {
    input.addEventListener("change", () => {
        if (parseInt(input.value) < 1) input.value = 1;
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// UTILITY
// ─────────────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}