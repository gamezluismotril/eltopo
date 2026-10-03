const API_URL = "https://eltopo-api.onrender.com";
const VISIBLE_DEFAULT = 5;

let allLong = [];
let allShort = [];
let longExpanded = false;
let shortExpanded = false;


async function fetchDestacados() {
    try {
        const res = await fetch(`${API_URL}/destacados`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        allLong = data.long || [];
        allShort = data.short || [];

        updateUpdateInfo(data.timestamp);
        renderLists();

    } catch (err) {
        console.error("Error:", err);
        document.getElementById("longList").innerHTML =
            `<div class="loading">Error al cargar. Reintenta.</div>`;
        document.getElementById("shortList").innerHTML =
            `<div class="loading">Error al cargar. Reintenta.</div>`;
    }
}

function updateUpdateInfo(timestamp) {
    if (!timestamp) return;
    const date = new Date(timestamp);
    document.getElementById("updateInfo").textContent =
        `Última actualización: ${date.toLocaleString("es-ES")}`;
}


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


async function openTickerModal(ticker) {
    const modal = document.getElementById("modal");
    const body = document.getElementById("modalBody");

    modal.classList.remove("hidden");
    body.innerHTML = `<div class="loading">Analizando ${ticker}...</div>`;

    try {
        const res = await fetch(`${API_URL}/ticker/${ticker}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        body.innerHTML = renderTickerDetail(data);
    } catch (err) {
        body.innerHTML = `<div class="loading">Error al cargar ${ticker}</div>`;
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

    document.getElementById("searchButton").addEventListener("click", () => {
        const q = document.getElementById("searchInput").value.trim().toUpperCase();
        if (q) openTickerModal(q);
    });

    document.getElementById("searchInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") document.getElementById("searchButton").click();
    });

    document.getElementById("modalClose").addEventListener("click", closeModal);
    document.getElementById("modal").addEventListener("click", (e) => {
        if (e.target.id === "modal") closeModal();
    });
});