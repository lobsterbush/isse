/**
 * ISSE Global States of Emergency Dashboard
 * Renders Leaflet world map, filterable emergencies table,
 * and reverse-chronological event stream from JSON data files.
 */

(function () {
  "use strict";

  /* ── Constants ── */
  const TYPE_COLORS = {
    disaster: "#f0523d",
    public_health: "#10B981",
    conflict: "#E85D04",
    migration: "#ae81ff",
    governance: "#00b2ff",
  };

  const TYPE_LABELS = {
    disaster: "Disaster",
    public_health: "Public Health",
    conflict: "Conflict / Security",
    migration: "Migration",
    governance: "Governance",
  };

  const GEOJSON_URL = "data/countries.geojson";

  const EVENTS_PER_PAGE = 50;

  /* ── State ── */
  let emergenciesData = [];
  let eventsData = [];
  let geoJsonLayer = null;
  let map = null;
  let tableSort = { key: "confidence", asc: false };
  let eventsShown = EVENTS_PER_PAGE;
  let storedGeoData = null;

  /* ── Helpers ── */
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function confidenceLabel(conf) {
    const pct = Math.round((conf || 0) * 100);
    if (pct >= 90) return { label: "Verified", cls: "conf-verified" };
    if (pct >= 75) return { label: "Likely Active", cls: "conf-likely" };
    return { label: "Unconfirmed", cls: "conf-unconfirmed" };
  }

  function durationText(startDate) {
    if (!startDate) return "";
    const start = new Date(startDate);
    if (isNaN(start)) return "";
    const now = new Date();
    const diffMs = now - start;
    const days = Math.floor(diffMs / 86400000);
    if (days < 1) return "<1 day";
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);
    const parts = [];
    if (years > 0) parts.push(`${years}y`);
    if (months > 0) parts.push(`${months}m`);
    if (years === 0 && months === 0) parts.push(`${days}d`);
    return parts.join(" ");
  }

  /* ── Data Loading ── */
  async function loadData() {
    try {
      const [emergResp, eventsResp] = await Promise.all([
        fetch("data/emergencies.json"),
        fetch("data/events.json"),
      ]);

      if (emergResp.ok) {
        const data = await emergResp.json();
        emergenciesData = data.emergencies || [];
        const ts = data.generated_at;
        if (ts) {
          const d = new Date(ts);
          document.getElementById("last-updated").textContent =
            `Data updated: ${d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} at ${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
        }
      } else {
        document.getElementById("last-updated").textContent =
          "Could not load emergency data. Run the data pipeline to generate data files.";
      }

      if (eventsResp.ok) {
        const data = await eventsResp.json();
        eventsData = data.events || [];
      }
    } catch (err) {
      console.error("Failed to load data:", err);
      document.getElementById("last-updated").textContent =
        "Error loading data. Run the Python pipeline first.";
    }
  }

  /* ── Filtering ── */
  function getFilters() {
    return {
      search: document.getElementById("search-input").value.toLowerCase(),
      type: document.getElementById("filter-type").value,
      continent: document.getElementById("filter-continent").value,
    };
  }

  function filteredEmergencies() {
    const f = getFilters();
    return emergenciesData.filter((e) => {
      if (f.type && e.emergency_type !== f.type) return false;
      if (f.continent && e.continent !== f.continent) return false;
      if (f.search) {
        const hay = `${e.country} ${e.title} ${e.emergency_type} ${e.declared_by}`.toLowerCase();
        if (!hay.includes(f.search)) return false;
      }
      return true;
    });
  }

  /* ── Summary Cards ── */
  function updateCards(data) {
    document.getElementById("card-active").textContent = data.length;
    document.getElementById("card-countries").textContent =
      new Set(data.map((e) => e.iso3)).size;

    const byType = {};
    data.forEach((e) => {
      byType[e.emergency_type] = (byType[e.emergency_type] || 0) + 1;
    });

    document.getElementById("card-conflict").textContent = byType.conflict || 0;
    document.getElementById("card-governance").textContent = byType.governance || 0;
    document.getElementById("card-disaster").textContent = byType.disaster || 0;
    document.getElementById("card-health").textContent =
      byType.public_health || 0;
  }

  /* ── Map ── */
  async function initMap() {
    map = L.map("map", {
      center: [20, 0],
      zoom: 2,
      minZoom: 2,
      maxZoom: 7,
      zoomControl: true,
      scrollWheelZoom: true,
    });

    // Dark tile layer
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }
    ).addTo(map);

    // Labels layer on top
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png",
      {
        subdomains: "abcd",
        maxZoom: 19,
        pane: "shadowPane",
      }
    ).addTo(map);

    // Load GeoJSON
    try {
      const resp = await fetch(GEOJSON_URL);
      if (resp.ok) {
        storedGeoData = await resp.json();
        renderGeoJson();
      }
    } catch (err) {
      console.warn("Could not load GeoJSON:", err);
    }
  }

  function getEmergencyByISO3(iso3) {
    return emergenciesData.find((e) => e.iso3 === iso3);
  }

  function renderGeoJson() {
    if (!storedGeoData || !map) return;
    if (geoJsonLayer) {
      map.removeLayer(geoJsonLayer);
    }

    const filtered = filteredEmergencies();
    const filteredISOs = new Set(filtered.map((e) => e.iso3));

    geoJsonLayer = L.geoJSON(storedGeoData, {
      style: (feature) => {
        const iso = feature.properties["ISO3166-1-Alpha-3"];
        const emerg = getEmergencyByISO3(iso);
        if (emerg && filteredISOs.has(iso)) {
          const color = TYPE_COLORS[emerg.emergency_type] || "#E85D04";
          return {
            fillColor: color,
            fillOpacity: 0.55,
            color: color,
            weight: 1.5,
            opacity: 0.8,
          };
        }
        if (emerg) {
          return {
            fillColor: "#333",
            fillOpacity: 0.15,
            color: "#3e3e3e",
            weight: 0.5,
            opacity: 0.4,
          };
        }
        return {
          fillColor: "#1a1a1a",
          fillOpacity: 0.3,
          color: "#3e3e3e",
          weight: 0.5,
          opacity: 0.5,
        };
      },
      onEachFeature: (feature, layer) => {
        const iso = feature.properties["ISO3166-1-Alpha-3"];
        const emerg = getEmergencyByISO3(iso);
        if (emerg) {
          const shortTitle = emerg.title && emerg.title.length > 80
            ? emerg.title.substring(0, 77) + "…" : emerg.title;
          layer.bindTooltip(
            `<strong>${escapeHtml(emerg.country)}</strong><br>` +
              `<span style="color:${TYPE_COLORS[emerg.emergency_type]}">${escapeHtml(TYPE_LABELS[emerg.emergency_type] || emerg.emergency_type)}</span><br>` +
              escapeHtml(shortTitle),
            { className: "dark-tooltip" }
          );
          layer.on("click", () => openCountryModal(emerg));
        } else {
          layer.bindTooltip(escapeHtml(feature.properties.name || iso));
        }
      },
    }).addTo(map);
  }

  /* ── Emergencies Table ── */
  function renderTable() {
    let data = filteredEmergencies();

    // Sort
    data.sort((a, b) => {
      let va = a[tableSort.key] ?? "";
      let vb = b[tableSort.key] ?? "";
      if (typeof va === "string") {
        return tableSort.asc
          ? va.localeCompare(vb)
          : vb.localeCompare(va);
      }
      return tableSort.asc ? va - vb : vb - va;
    });

    const tbody = document.getElementById("emergencies-tbody");

    if (data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">
        ${emergenciesData.length === 0 ? "No data available — run the data pipeline to populate." : "No emergencies match the current filters."}
      </td></tr>`;
      document.getElementById("table-count").textContent = "0 emergencies";
      return;
    }

    tbody.innerHTML = data
      .map((e) => {
        const conf = confidenceLabel(e.confidence);
        const confPct = Math.round((e.confidence || 0) * 100);
        const dur = durationText(e.start_date);
        const topSource = e.source_urls && e.source_urls[0];
        return `<tr data-iso3="${escapeHtml(e.iso3)}" style="cursor:pointer">
          <td><strong>${escapeHtml(e.country || e.iso3)}</strong></td>
          <td><span class="type-badge ${escapeHtml(e.emergency_type)}">${escapeHtml(TYPE_LABELS[e.emergency_type] || e.emergency_type)}</span></td>
          <td title="${escapeHtml(e.title)}">${escapeHtml(e.title ? (e.title.length > 60 ? e.title.substring(0, 57) + "…" : e.title) : "") || "—"}</td>
          <td style="font-family:var(--font-mono);font-size:0.75rem">${escapeHtml(e.start_date) || "—"}${dur ? ` <span style="color:var(--text-muted);font-size:0.65rem">(${dur})</span>` : ""}</td>
          <td>
            <span class="conf-label ${conf.cls}" title="${confPct}% confidence">${conf.label}</span>
          </td>
          <td>${topSource ? `<a href="${escapeHtml(topSource.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml((topSource.title || "").substring(0, 30))}…</a>` : "—"}</td>
        </tr>`;
      })
      .join("");

    document.getElementById("table-count").textContent =
      `${data.length} emergencies`;

    // Row click → modal
    tbody.querySelectorAll("tr").forEach((tr) => {
      tr.addEventListener("click", () => {
        const emerg = emergenciesData.find(
          (e) => e.iso3 === tr.dataset.iso3
        );
        if (emerg) openCountryModal(emerg);
      });
    });
  }

  /* ── Event Stream ── */
  function getStreamFilters() {
    return {
      type: document.getElementById("stream-filter-type").value,
      source: document.getElementById("stream-filter-source").value,
    };
  }

  function filteredEvents() {
    const f = getStreamFilters();
    return eventsData.filter((ev) => {
      if (f.type && ev.emergency_type !== f.type) return false;
      if (f.source && ev.source !== f.source) return false;
      return true;
    });
  }

  function renderEventStream() {
    const events = filteredEvents();
    const toShow = events.slice(0, eventsShown);
    const listEl = document.getElementById("event-list");

    if (toShow.length === 0) {
      listEl.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:2rem;">
        ${eventsData.length === 0 ? "No news events available yet." : "No events match the current filters."}
      </div>`;
      document.getElementById("load-more-btn").style.display = "none";
      return;
    }

    listEl.innerHTML = toShow
      .map((ev) => {
        return `<div class="event-item">
          <div class="event-date">${escapeHtml(ev.date) || "—"}</div>
          <div class="event-body">
            <div class="event-title">
              <span class="type-badge ${escapeHtml(ev.emergency_type)}" style="margin-right:0.4rem">${escapeHtml(TYPE_LABELS[ev.emergency_type] || ev.emergency_type)}</span>
              ${ev.url ? `<a href="${escapeHtml(ev.url)}" target="_blank" rel="noopener">${escapeHtml(ev.title)}</a>` : escapeHtml(ev.title)}
            </div>
            <div class="event-meta">
              ${escapeHtml(ev.country || ev.iso3 || "")} · ${escapeHtml(ev.source_name || ev.source)}
            </div>
          </div>
        </div>`;
      })
      .join("");

    const btn = document.getElementById("load-more-btn");
    btn.style.display = events.length > eventsShown ? "block" : "none";
  }

  /* ── Country Modal ── */
  function openCountryModal(emerg) {
    document.getElementById("modal-country-name").textContent =
      emerg.country || emerg.iso3;

    const meta = document.getElementById("modal-meta");
    const conf = confidenceLabel(emerg.confidence);
    const dur = durationText(emerg.start_date);
    meta.innerHTML = `
      <span class="tag type-badge ${escapeHtml(emerg.emergency_type)}">${escapeHtml(TYPE_LABELS[emerg.emergency_type] || emerg.emergency_type)}</span>
      ${emerg.continent ? `<span class="tag">${escapeHtml(emerg.continent)}</span>` : ""}
      ${emerg.start_date ? `<span class="tag">Since ${escapeHtml(emerg.start_date)}${dur ? ` (${dur})` : ""}</span>` : ""}
      ${emerg.declared_by ? `<span class="tag">${escapeHtml(emerg.declared_by)}</span>` : ""}
      <span class="tag ${conf.cls}">${conf.label}</span>
      ${emerg.scope ? `<span class="tag">Scope: ${escapeHtml(emerg.scope)}</span>` : ""}
      ${emerg.legal_basis ? `<span class="tag">Legal basis: ${escapeHtml(emerg.legal_basis)}</span>` : ""}
    `;

    document.getElementById("modal-notes").textContent = emerg.notes || emerg.title || "";

    const srcEl = document.getElementById("modal-sources");
    const urls = emerg.source_urls || [];
    srcEl.innerHTML = urls.length
      ? `<h3>Sources</h3>` +
        urls
          .map((s) => {
            const isWiki = s.url && s.url.includes("wikipedia.org");
            const label = isWiki ? `📖 ${escapeHtml(s.title || "Wikipedia")}` : escapeHtml(s.title || s.url);
            return `<div class="modal-source-item"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${label}</a> <span style="color:var(--text-muted);font-size:0.7rem">${escapeHtml(s.date || "")}</span></div>`;
          })
          .join("")
      : "";

    document.getElementById("country-modal").style.display = "flex";
  }

  function closeModal() {
    document.getElementById("country-modal").style.display = "none";
  }

  /* ── Render All ── */
  function renderAll() {
    const data = filteredEmergencies();
    updateCards(data);
    renderTable();
    renderEventStream();
    renderGeoJson();
  }

  /* ── Event Listeners ── */
  function initEvents() {
    // Table/map filters
    document.getElementById("search-input").addEventListener("input", renderAll);
    document.getElementById("filter-type").addEventListener("change", renderAll);
    document.getElementById("filter-continent").addEventListener("change", renderAll);
    document.getElementById("clear-filters").addEventListener("click", () => {
      document.getElementById("search-input").value = "";
      document.getElementById("filter-type").value = "";
      document.getElementById("filter-continent").value = "";
      renderAll();
    });

    // Table sorting
    document.querySelectorAll("#emergencies-table th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (tableSort.key === key) tableSort.asc = !tableSort.asc;
        else {
          tableSort.key = key;
          tableSort.asc = true;
        }
        renderTable();
      });
    });

    // Stream filters
    document.getElementById("stream-filter-type").addEventListener("change", () => {
      eventsShown = EVENTS_PER_PAGE;
      renderEventStream();
    });
    document.getElementById("stream-filter-source").addEventListener("change", () => {
      eventsShown = EVENTS_PER_PAGE;
      renderEventStream();
    });

    // Load more
    document.getElementById("load-more-btn").addEventListener("click", () => {
      eventsShown += EVENTS_PER_PAGE;
      renderEventStream();
    });

    // Modal
    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("country-modal").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal();
    });
  }

  /* ── CSV Download ── */
  function downloadCSV() {
    const headers = ["iso3", "country", "continent", "emergency_type", "title", "start_date", "declared_by", "confidence", "verification", "duration", "scope", "legal_basis", "notes"];
    const rows = emergenciesData.map((e) => {
      const conf = confidenceLabel(e.confidence);
      return headers.map((h) => {
        let val = "";
        if (h === "verification") val = conf.label;
        else if (h === "duration") val = durationText(e.start_date);
        else val = e[h] ?? "";
        // Escape CSV
        val = String(val).replace(/"/g, '""');
        return `"${val}"`;
      }).join(",");
    });
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `isse_emergencies_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /* ── Citation ── */
  function initCitation() {
    const dateEl = document.getElementById("cite-date");
    if (dateEl) {
      dateEl.textContent = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
    }
    const yearEl = document.getElementById("cite-year");
    if (yearEl) yearEl.textContent = new Date().getFullYear();

    const copyBtn = document.getElementById("copy-citation-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const text = document.getElementById("citation-text").textContent;
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
        });
      });
    }

    const csvBtn = document.getElementById("download-csv-btn");
    if (csvBtn) csvBtn.addEventListener("click", downloadCSV);
  }

  /* ── Init ── */
  async function init() {
    initEvents();
    initCitation();
    await loadData();
    await initMap();
    renderAll();
    // Remove loading class after first render
    document.body.classList.add("loaded");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
