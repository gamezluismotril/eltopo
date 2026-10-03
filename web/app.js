const API_URL = "https://eltopo-api.onrender.com";
const VISIBLE_DEFAULT = 5;

let allLong = [];
let allShort = [];
let longExpanded = false;
let shortExpanded = false;


/* ============================================================
   API: DESTACADOS
   ============================================================ */
async function fetchDestacados() {
    showToast("Actualizando datos...", "info");

    try {
        const res = await fetch(`${API_URL}/destacados`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        allLong = data.long || [];
        allShort = data.short || [];

        updateUpdateInfo(data.timestamp);
        renderLists();
        showToast("Datos actualizados", "success");

    } catch (err) {
        console.error("Error:", err);
        document.getElementById("longList").innerHTML =
            `<div class="loading">Error al cargar. Reintenta.</div>`;
        document.getElementById("shortList").innerHTML =
            `<div class="loading">Error al cargar. Reintenta.</div>`;
        showToast("Error al cargar datos", "error");
    }
}

function updateUpdateInfo(timestamp) {
    if (!timestamp) return;
    const date = new Date(timestamp);
    document.getElementById("updateInfo").textContent =
        `Última actualización: ${date.toLocaleString("es-ES")}`;
}


/* ============================================================
   RENDERIZADO DE LISTAS
   ============================================================ */
function renderLists() {
    renderList("long", allLong, longExpanded);
    renderList("short", allShort, shortExpanded);

    document.getElementById("longCount").textContent = allLong.length;
    document.getElementById("shortCount").textContent = allShort.length;

    const longBtn = document.getElementById("longMoreBtn");
    const shortBtn = document.getElementById("shortMoreBtn");

    if (allLong.length <= VISIBLE_DEFAULT) {
        longBtn.classList.add("hidden");
    } else {
        longBtn.classList.remove("hidden");
        longBtn.textContent = longExpanded
            ? "Ver menos"
            : `Ver más (${allLong.length - VISIBLE_DEFAULT})`;
    }

    if (allShort.length <= VISIBLE_DEFAULT) {
        shortBtn.classList.add("hidden");
    } else {
        shortBtn.classList.remove("hidden");
        shortBtn.textContent = shortExpanded
            ? "Ver menos"
            : `Ver más (${allShort.length - VISIBLE_DEFAULT})`;
    }
}

function renderList(side, data, expanded) {
    const container = document.getElementById(`${side}List`);
    if (!data || data.length === 0) {
        container.innerHTML = `<div class="loading">Sin datos</div>`;
        return;
    }

    const visible = expanded ? data : data.slice(0, VISIBLE_DEFAULT);

    container.innerHTML = visible.map(item => {
        const score = item.score || 0;
        const color = score >= 75 ? "green" : score >= 60 ? "yellow" : "red";
        const badgeClass = side === "long" ? "badge-long" : "badge-short";
        const badgeText = side === "long" ? "LONG" : "SHORT";

        return `
            <div class="ticker-card" data-ticker="${item.ticker}">
                <div class="ticker-left">
                    <div class="ticker-symbol">${item.ticker}</div>
                    <span class="ticker-badge ${badgeClass}">${badgeText}</span>
                </div>
                <div class="ticker-right">
                    <div class="ticker-score ${color}">${score}</div>
                    <div class="ticker-meta">${item.alignment || ""}</div>
                </div>
            </div>
        `;
    }).join("");

    container.querySelectorAll(".ticker-card").forEach(card => {
        card.addEventListener("click", () => {
            openTickerModal(card.dataset.ticker);
        });
    });
}


/* ============================================================
   BUSQUEDA (ticker o nombre)
   ============================================================ */
async function handleSearch() {
    const query = document.getElementById("searchInput").value.trim().toUpperCase();
    if (!query) return;

    // Si parece un ticker (2-5 letras sin espacios) → ir directo
    if (/^[A-Z]{1,5}$/.test(query)) {
        openTickerModal(query);
        return;
    }

    // Si no, buscar por nombre
    showToast(`Buscando "${query}"...`, "info");

    try {
        const res = await fetch(`${API_URL}/search/${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.count === 0) {
            showToast(`No se encontraron resultados para "${query}"`, "error");
            return;
        }

        if (data.count === 1) {
            openTickerModal(data.results[0].symbol);
            return;
        }

        showSearchResults(data.results);

    } catch (err) {
        console.error("Error:", err);
        showToast("Error en la busqueda", "error");
    }
}

function showSearchResults(results) {
    const modal = document.getElementById("modal");
    const body = document.getElementById("modalBody");

    modal.classList.remove("hidden");

    let html = `<h2 style="margin-bottom:15px;">Resultados (${results.length})</h2><div>`;
    for (const r of results) {
        html += `
            <div class="ticker-card" style="margin-bottom:8px;"
                 onclick="openTickerModal('${r.symbol}')">
                <div class="ticker-left">
                    <div class="ticker-symbol">${r.symbol}</div>
                    <div style="font-size:0.75rem; color:#8b949e;">${r.name}</div>
                </div>
                <div class="ticker-right">
                    <div style="font-size:0.7rem; color:#6e7681;">${r.exchange}</div>
                </div>
            </div>
        `;
    }
    html += `</div>`;

    body.innerHTML = html;
}


/* ============================================================
   MODAL DE DETALLE
   ============================================================ */
async function openTickerModal(ticker) {
    const modal = document.getElementById("modal");
    const body = document.getElementById("modalBody");

    modal.classList.remove("hidden");
    body.innerHTML = `<div class="loading">Analizando ${ticker}...</div>`;

    try {
        const res = await fetch(`${API_URL}/ticker/${ticker}`);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            const detail = errData.detail || `Error ${res.status}`;

            body.innerHTML = `
                <h2>${ticker}</h2>
                <p style="color:#f85149; margin-top:15px;">${detail}</p>
                <p style="color:#8b949e; margin-top:20px; font-size:0.85rem;">
                    💡 Consejo: prueba con un ticker del Top 15 LONG o SHORT que ves en la página principal.
                </p>
            `;
            return;
        }

        const data = await res.json();
        body.innerHTML = renderTickerDetail(data);

    } catch (err) {
        body.innerHTML = `
            <h2>${ticker}</h2>
            <p style="color:#f85149; margin-top:15px;">No se pudo conectar con el servidor.</p>
            <p style="color:#8b949e; margin-top:20px; font-size:0.85rem;">
                Revisa tu conexión e inténtalo de nuevo.
            </p>
        `;
    }
}

function renderTickerDetail(data) {
    if (data.error) {
        return `<h2>${data.ticker}</h2><p>${data.error}</p>`;
    }

    const score = data.score || 0;
    const color = score >= 75 ? "green" : score >= 60 ? "yellow" : "red";
    const sideBadge = data.side === "long"
        ? '<span class="ticker-badge badge-long">LONG</span>'
        : data.side === "short"
            ? '<span class="ticker-badge badge-short">SHORT</span>'
            : '';

    let html = `
        <h2 style="margin-bottom:10px;">${data.ticker} ${sideBadge}</h2>
        <div style="font-size:2.5rem; font-weight:700;" class="ticker-score ${color}">
            ${score}
        </div>
        <p style="color:#8b949e; margin-bottom:20px;">
            ${data.structure_bias || ""} · ${data.alignment || ""} · ${data.confluence || ""}
        </p>
    `;

    const tfs = data.timeframes || {};
    for (const [name, tf] of Object.entries(tfs)) {
        if (!tf) continue;
        html += `
            <div style="border-top:1px solid #30363d; padding-top:15px; margin-top:15px;">
                <h3 style="margin-bottom:10px;">${name.toUpperCase()} · Score ${tf.score}</h3>
                <div style="font-size:0.85rem; color:#8b949e;">
                    Bias: ${tf.structure_bias} · Régimen: ${tf.regime}
                </div>
            </div>
        `;
    }

    html += `
        <div style="border-top:1px solid #30363d; padding-top:15px; margin-top:15px;
                    font-size:0.8rem; color:#6e7681;">
            ${data.disclaimer || ""}
        </div>
    `;

    return html;
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}


/* ============================================================
   TOAST (notificaciones)
   ============================================================ */
function showToast(message, type = "info") {
    let toast = document.getElementById("toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast";
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 500;
            z-index: 2000;
            transition: opacity 0.3s;
            opacity: 0;
        `;
        document.body.appendChild(toast);
    }

    const colors = {
        info: "#58a6ff",
        success: "#3fb950",
        error: "#f85149",
    };

    toast.style.background = colors[type] || colors.info;
    toast.style.color = "#fff";
    toast.textContent = message;
    toast.style.opacity = "1";

    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.style.opacity = "0";
    }, 3000);
}


/* ============================================================
   EVENTOS
   ============================================================ */
document.addEventListener("DOMContentLoaded", () => {
    fetchDestacados();

    document.getElementById("scanButton").addEventListener("click", fetchDestacados);

    document.getElementById("longMoreBtn").addEventListener("click", () => {
        longExpanded = !longExpanded;
        renderLists();
    });

    document.getElementById("shortMoreBtn").addEventListener("click", () => {
        shortExpanded = !shortExpanded;
        renderLists();
    });

    document.getElementById("searchButton").addEventListener("click", handleSearch);

    document.getElementById("searchInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleSearch();
    });

    document.getElementById("modalClose").addEventListener("click", closeModal);
    document.getElementById("modal").addEventListener("click", (e) => {
        if (e.target.id === "modal") closeModal();
    });
});