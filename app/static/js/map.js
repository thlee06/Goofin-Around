/**
 * map.js — Leaflet.js map initialization for the events map view.
 *
 * Reads event data from the #map element's data-events attribute (JSON array).
 * Requires Leaflet CSS + JS to be loaded in the page (see map.html).
 */

document.addEventListener("DOMContentLoaded", function () {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;

  // Parse event data injected by the server
  let events = [];
  try {
    events = JSON.parse(mapEl.dataset.events || "[]");
  } catch (e) {
    console.error("Failed to parse events JSON:", e);
    return;
  }

  // Columbia University campus center
  const COLUMBIA_CENTER = [40.8075, -73.9626];

  const map = L.map("map").setView(COLUMBIA_CENTER, 15);

  // OpenStreetMap tiles — free, no API key needed
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  if (!events.length) {
    // Show a message overlay if no mappable events
    const info = L.control({ position: "topright" });
    info.onAdd = function () {
      const div = L.DomUtil.create("div", "leaflet-bar");
      div.style.cssText = "background:white;padding:8px 12px;font-size:13px;color:#555;";
      div.textContent = "No events with known locations found.";
      return div;
    };
    info.addTo(map);
    return;
  }

  // Add a marker for each event
  events.forEach(function (event) {
    if (!event.lat || !event.lon) return;

    const marker = L.marker([event.lat, event.lon]);

    const dateStr = event.start
      ? new Date(event.start).toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })
      : "Date TBA";

    marker.bindPopup(`
      <div style="min-width:180px;max-width:240px;">
        <p style="font-weight:600;margin:0 0 4px;">${event.title}</p>
        <p style="font-size:12px;color:#555;margin:0 0 2px;">${dateStr}</p>
        <p style="font-size:12px;color:#555;margin:0 0 6px;">${event.location || ""}</p>
        <p style="font-size:11px;color:#777;margin:0 0 4px;">${event.department || ""}</p>
        <a href="${event.url}" style="font-size:12px;color:#003087;font-weight:500;">
          View details &rarr;
        </a>
      </div>
    `);

    marker.addTo(map);
  });

  // Fit map bounds to all markers
  const coords = events
    .filter((e) => e.lat && e.lon)
    .map((e) => [e.lat, e.lon]);
  if (coords.length > 1) {
    map.fitBounds(coords, { padding: [40, 40] });
  }
});
