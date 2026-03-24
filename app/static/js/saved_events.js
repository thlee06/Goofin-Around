/**
 * saved_events.js — localStorage-based event bookmarking.
 *
 * Saved event IDs are stored in localStorage under the key "savedEvents".
 * No login required. Note: saves are browser-local and device-specific.
 *
 * Public API:
 *   toggleSave(eventId, buttonEl)  — called by Save buttons (onclick)
 *   getSavedIds()                  — returns array of saved event IDs
 *   generateShareUrl()             — returns /saved?ids=1,2,3 URL
 */

const STORAGE_KEY = "savedEvents";

function getSavedIds() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function setSavedIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

function isSaved(eventId) {
  return getSavedIds().includes(Number(eventId));
}

function toggleSave(eventId, buttonEl) {
  const id = Number(eventId);
  let ids = getSavedIds();
  if (ids.includes(id)) {
    ids = ids.filter((x) => x !== id);
    if (buttonEl) buttonEl.textContent = "☆ Save";
  } else {
    ids.push(id);
    if (buttonEl) buttonEl.textContent = "★ Saved";
  }
  setSavedIds(ids);
}

function generateShareUrl() {
  const ids = getSavedIds();
  if (!ids.length) return window.location.origin;
  return `${window.location.origin}/saved?ids=${ids.join(",")}`;
}

/** Update all Save button states on page load */
function syncSaveButtons() {
  document.querySelectorAll(".save-btn").forEach((btn) => {
    const id = Number(btn.dataset.eventId);
    if (isSaved(id)) {
      btn.textContent = "★ Saved";
    }
  });
}

document.addEventListener("DOMContentLoaded", syncSaveButtons);

// Re-sync after HTMX swaps new content into the DOM
document.addEventListener("htmx:afterSwap", syncSaveButtons);
