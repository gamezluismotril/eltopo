/* ============================================================
   ELTOPO · Lógica de la web
   - Tema claro/oscuro con localStorage
   - Pestañas (Top 15 / Por Sector / Índices)
   - Sparklines en SVG
   - Chart de velas 5d
   - Modal de detalle con "¿Por qué?"
   - Índices clickables (abren el modal del ticker)
   ============================================================ */

const API_URL = "https://eltopo-api.onrender.com";
const VISIBLE_DEFAULT = 5;

// Estado global
let allLong = [];
let allShort = [];
let allIndices = [];
let topBySector = { long: {}, short: {} };
let longExpanded = false;
let shortExpanded = false;

// ============================================================
// UTILIDADES
// ============================================================
function escapeHTML(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function scoreClass(score) {
    if (score >= 75) return "green";
    if (score >= 60) return "yellow";
    return "red";
}

function strengthClass(strength) {
    if (!strength) return "gray";
    const s = strength.toUpperCase();
    if (s.includes("MUY") || s === "FUERTE") return "green";
    if (s === "MEDIA") return "yellow";
    return "gray";
}

// ============================================================
// TEMA (claro/oscuro)
// ============================================================
function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const btn = document.getElementById("themeToggle");
    if (btn) {
        btn.textContent = theme === "dark" ? "☀️" : "🌙";
    }
    localStorage.setItem("eltopo-theme", theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(current === "dark" ? "light" : "dark");
}

function initTheme() {
    const saved = localStorage.getItem("eltopo-theme") || "light";
    applyTheme(saved);
}

// ============================================================
// SPARKLINE (SVG inline)
// ============================================================
function drawSparkline(data, options = {}) {
    const width = options.width || 70;
    const height = options.height || 26;
    const strokeWidth = options.strokeWidth || 1.5;
    const color = options.color || "var(--text-secondary)";

    if (!data || data.length < 2) {
        return `<svg width="${width}" height="${height}"></svg>`;
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    const points = data.map((val, i) => {
        const x = (i / (data.length - 1)) * (width - 2) + 1;
        const y = height - 1 - ((val - min) / range) * (height - 2);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");

    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline points="${points}" fill="none" stroke="${color}"
                  stroke-width="${strokeWidth}"
                  stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
}

function sparklineColor(data) {
    if (!data || data.length < 2) return "var(--text-tertiary)";
    const first = data[0];
    const last = data[data.length - 1];
    if (last > first) return "var(--green)";
    if (last < first) return "var(--red)";
    return "var(--text-tertiary)";
}

// ============================================================
// CANDLESTICK (SVG)
// ============================================================
function drawCandlestick(candles) {
    if (!candles || candles.length === 0) {
        return `<div class="loading">Sin datos de gráfico</div>`;
    }

    const width = 660;
    const height = 140;
    const paddingX = 30;
    const paddingY = 20;
    const usableW = width - paddingX * 2;
    const usableH = height - paddingY * 2;

    let minLow = Infinity, maxHigh = -Infinity;
    for (const c of candles) {
        if (c.l < minLow) minLow = c.l;
        if (c.h > maxHigh) maxHigh = c.h;
    }
    const range = maxHigh - minLow || 1;

    const candleW = (usableW / candles.length) * 0.6;
    const gap = (usableW / candles.length) * 0.4;

    const toY = (v) => paddingY + (1 - (v - minLow) / range) * usableH;
    const toX = (i) => paddingX + i * (candleW + gap) + gap / 2;

    let svg = `<svg class="candlestick-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">`;

    for (let i = 0; i <= 4; i++) {
        const y = paddingY + (usableH / 4) * i;
        svg += `<line x1="${paddingX}" y1="${y}" x2="${width - paddingX}" y2="${y}"
                     stroke="var(--border)" stroke-width="0.5" opacity="0.5"/>`;
    }

    for (let i = 0; i < candles.length; i++) {
        const c = candles[i];
        const x = toX(i);
        const isUp = c.c >= c.o;
        const color = isUp ? "var(--green)" : "var(--red)";

        svg += `<line x1="${x + candleW / 2}" y1="${toY(c.h)}"
                     x2="${x + candleW / 2}" y2="${toY(c.l)}"
                     stroke="${color}" stroke-width="1.5"/>`;

        const bodyTop = toY(Math.max(c.o, c.c));
        const bodyBot = toY(Math.min(c.o, c.c));
        const bodyH = Math.max(1, bodyBot - bodyTop);
        svg += `<rect x="${x}" y="${bodyTop}" width="${candleW}" height="${bodyH}"
                     fill="${color}" rx="1"/>`;
    }

    for (let i = 0; i < candles.length; i++) {
        const c = candles[i];
        const x = toX(i) + candleW / 2;
        const label = (c.date || "").slice(5);
        svg += `<text x="${x}" y="${height - 4}" text-anchor="middle"
                     font-size="10" fill="var(--text-tertiary)"
                     font-family="inherit">${label}</text>`;
    }

    svg += `</svg>`;
    return svg;
}

// ============================================================
// API
// ============================================================
async function fetchDestacados() {
    try {
        const res = await fetch(`${API_URL}/destacados`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        allLong = data.long || [];
        allShort = data.short || [];
        allIndices = data.indices || [];
        topBySector = data.top_by_sector || { long: {}, short: {} };

        updateUpdateInfo(data.timestamp);
        renderMiniIndices();
        renderLists();
        renderIndices();
        renderSectors();
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

// ============================================================
// MINI-WIDGET ÍNDICES
// ============================================================
function renderMiniIndices() {
    const container = document.getElementById("miniIndicesInner");
    if (!container) return;

    if (!allIndices || allIndices.length === 0) {
        container.innerHTML = "";
        return;
    }

    const main = allIndices.slice(0, 6);
    container.innerHTML = main.map(idx => {
        const changeClass = idx.change_pct >= 0 ? "up" : "down";
        const sign = idx.change_pct >= 0 ? "+" : "";
        return `<div class="mini-index-item">
            <span class="symbol">${escapeHTML(idx.symbol)}</span>
            <span class="price">${idx.price.toLocaleString("es-ES", {maximumFractionDigits: 2})}</span>
            <span class="change ${changeClass}">${sign}${idx.change_pct.toFixed(2)}%</span>
        </div>`;
    }).join("");
}

// ============================================================
// TABS
// ============================================================
function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    const contents = document.querySelectorAll(".tab-content");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.dataset.tab;

            tabs.forEach(t => t.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            tab.classList.add("active");
            document.getElementById(`tab-${target}`).classList.add("active");
        });
    });
}

// ============================================================
// RENDER LISTAS (Top 15)
// ============================================================
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
        const sClass = scoreClass(score);
        const name = item.name ? `(${escapeHTML(item.name)})` : "";
        const strength = item.strength || "";
        const strengthCls = strengthClass(strength);
        const badgeClass = side === "long" ? "badge-long" : "badge-short";
        const badgeText = side === "long" ? "LONG" : "SHORT";

        const sparkColor = sparklineColor(item.sparkline);
        const sparkSVG = drawSparkline(item.sparkline, {
            width: 70, height: 26, color: sparkColor,
        });

        return `
            <div class="ticker-card" data-ticker="${escapeHTML(item.ticker)}">
                <div class="ticker-left">
                    <div class="ticker-symbol">
                        ${escapeHTML(item.ticker)}
                        <span class="ticker-name">${name}</span>
                    </div>
                    <div class="ticker-badges">
                        <span class="ticker-badge ${badgeClass}">${badgeText}</span>
                    </div>
                </div>
                <div class="ticker-sparkline">${sparkSVG}</div>
                <div class="ticker-right">
                    <div class="ticker-score ${sClass}">${score}</div>
                    <div class="ticker-strength ${strengthCls}">${escapeHTML(strength)}</div>
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

// ============================================================
// RENDER ÍNDICES (pestaña completa · 2 filas de 5 · clickables)
// ============================================================
function renderIndices() {
    const container = document.getElementById("indicesRow");
    if (!container) return;

    if (!allIndices || allIndices.length === 0) {
        container.innerHTML = `<div class="loading">Sin datos de índices</div>`;
        return;
    }

    container.innerHTML = allIndices.map(idx => {
        const changeClass = idx.change_pct >= 0 ? "up" : "down";
        const sign = idx.change_pct >= 0 ? "+" : "";
        const sparkColor = sparklineColor(idx.sparkline);
        const sparkSVG = drawSparkline(idx.sparkline, {
            width: 188, height: 40, color: sparkColor, strokeWidth: 2,
        });

        return `
            <div class="index-card" data-ticker="${escapeHTML(idx.symbol)}">
                <div class="index-name">${escapeHTML(idx.name)}</div>
                <div class="index-price">${idx.price.toLocaleString("es-ES", {maximumFractionDigits: 2})}</div>
                <div class="index-change ${changeClass}">${sign}${idx.change_pct.toFixed(2)}%</div>
                <div class="index-sparkline">${sparkSVG}</div>
            </div>
        `;
    }).join("");

    // Click en cualquier índice → abre el modal de ese ticker
    container.querySelectorAll(".index-card").forEach(card => {
        card.addEventListener("click", () => {
            openTickerModal(card.dataset.ticker);
        });
    });
}

// ============================================================
// RENDER SECTORES
// ============================================================
const SECTOR_EMOJIS = {
    "Tecnología": "💻",
    "Financiero": "🏦",
    "Salud": "🏥",
    "Consumo Discrecional": "🛍️",
    "Consumo Básico": "🛒",
    "Industrial": "🏭",
    "Energía": "⚡",
    "Materiales": "⛏️",
    "Utilities": "💡",
    "Bienes Raíces": "🏠",
    "Comunicaciones": "📡",
    "Otros": "❓",
};

function renderSectors() {
    const container = document.getElementById("sectorsContainer");
    if (!container) return;

    const hasLong = topBySector.long && Object.keys(topBySector.long).length > 0;
    const hasShort = topBySector.short && Object.keys(topBySector.short).length > 0;

    if (!hasLong && !hasShort) {
        container.innerHTML = `<div class="loading">Sin datos de sectores</div>`;
        return;
    }

    let html = "";

    if (hasLong) {
        html += `<div class="indices-title">🟢 LONG por sector</div>`;
        html += `<div class="sector-grid">`;
        html += Object.entries(topBySector.long).map(([sector, tickers]) =>
            renderSectorCard(sector, tickers)
        ).join("");
        html += `</div>`;
    }

    if (hasShort) {
        html += `<div class="indices-title" style="margin-top:30px;">🔴 SHORT por sector</div>`;
        html += `<div class="sector-grid">`;
        html += Object.entries(topBySector.short).map(([sector, tickers]) =>
            renderSectorCard(sector, tickers)
        ).join("");
        html += `</div>`;
    }

    container.innerHTML = html;

    container.querySelectorAll(".sector-ticker-row").forEach(row => {
        row.addEventListener("click", () => {
            openTickerModal(row.dataset.ticker);
        });
    });
}

function renderSectorCard(sector, tickers) {
    const emoji = SECTOR_EMOJIS[sector] || "📁";
    const rows = tickers.map((t, i) => {
        const sClass = scoreClass(t.score);
        return `
            <div class="sector-ticker-row" data-ticker="${escapeHTML(t.ticker)}">
                <span class="rank">${i + 1}.</span>
                <span class="sym">${escapeHTML(t.ticker)}</span>
                <span class="scr ${sClass}">${t.score}</span>
            </div>
        `;
    }).join("");

    return `
        <div class="sector-card">
            <div class="sector-header">
                <span class="sector-emoji">${emoji}</span>
                <span>${escapeHTML(sector)}</span>
            </div>
            <div class="sector-tickers">${rows}</div>
        </div>
    `;
}

// ============================================================
// BÚSQUEDA
// ============================================================
async function handleSearch() {
    const query = document.getElementById("searchInput").value.trim().toUpperCase();
    if (!query) return;

    if (/^[A-Z]{1,5}$/.test(query)) {
        openTickerModal(query);
        return;
    }

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
        showToast("Error en la búsqueda", "error");
    }
}

function showSearchResults(results) {
    const modal = document.getElementById("modal");
    const body = document.getElementById("modalBody");

    modal.classList.remove("hidden");

    let html = `<div class="modal-header">
        <div class="modal-ticker">Resultados (${results.length})</div>
    </div>`;

    html += results.map(r => `
        <div class="ticker-card" style="margin-bottom:8px;"
             onclick="openTickerModal('${escapeHTML(r.symbol)}')">
            <div class="ticker-left">
                <div class="ticker-symbol">${escapeHTML(r.symbol)}</div>
                <div style="font-size:0.78rem; color:var(--text-secondary);">
                    ${escapeHTML(r.name || "")}
                </div>
            </div>
            <div class="ticker-right" style="min-width:auto;">
                <div style="font-size:0.7rem; color:var(--text-tertiary);">
                    ${escapeHTML(r.exchange || "")}
                </div>
            </div>
        </div>
    `).join("");

    body.innerHTML = html;
}

// ============================================================
// MODAL DE DETALLE
// ============================================================
async function openTickerModal(ticker) {
    const modal = document.getElementById("modal");
    const body = document.getElementById("modalBody");

    modal.classList.remove("hidden");
    body.innerHTML = `<div class="loading">Analizando ${escapeHTML(ticker)}...</div>`;

    try {
        const res = await fetch(`${API_URL}/ticker/${encodeURIComponent(ticker)}`);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            const detail = errData.detail || `Error ${res.status}`;
            body.innerHTML = `
                <div class="modal-header">
                    <div class="modal-ticker">${escapeHTML(ticker)}</div>
                </div>
                <p style="color:var(--red); margin-top:10px;">${escapeHTML(detail)}</p>
                <p style="color:var(--text-secondary); margin-top:20px; font-size:0.85rem;">
                    💡 Consejo: prueba con un ticker del Top 15 LONG o SHORT.
                </p>
            `;
            return;
        }

        const data = await res.json();
        body.innerHTML = renderTickerDetail(data);
    } catch (err) {
        body.innerHTML = `
            <div class="modal-header">
                <div class="modal-ticker">${escapeHTML(ticker)}</div>
            </div>
            <p style="color:var(--red); margin-top:10px;">No se pudo conectar con el servidor.</p>
        `;
    }
}

function renderTickerDetail(data) {
    if (data.error) {
        return `<div class="modal-header">
            <div class="modal-ticker">${escapeHTML(data.ticker)}</div>
        </div>
        <p>${escapeHTML(data.error)}</p>`;
    }

    const score = data.score || 0;
    const sClass = scoreClass(score);
    const strength = data.strength || "";
    const strengthCls = strengthClass(strength);
    const name = data.name ? escapeHTML(data.name) : "";
    const alignmentEs = data.alignment_es || "";
    const ticker = escapeHTML(data.ticker);

    const sideBadge = data.side === "long"
        ? '<span class="ticker-badge badge-long">LONG</span>'
        : data.side === "short"
            ? '<span class="ticker-badge badge-short">SHORT</span>'
            : '';

    let html = `
        <div class="modal-header">
            <div class="modal-ticker">${ticker} ${sideBadge}</div>
            ${name ? `<div class="modal-name">${name}</div>` : ""}
            <div class="modal-score-row">
                <div class="modal-score ${sClass}">${score}</div>
                <div class="modal-score-meta">
                    <div class="modal-strength ${strengthCls}">${escapeHTML(strength)}</div>
                    <div class="modal-alignment">${escapeHTML(alignmentEs)}</div>
                </div>
            </div>
        </div>
    `;

    if (data.chart_5d && data.chart_5d.length > 0) {
        html += `
            <div class="modal-chart">
                <div class="modal-chart-title">📈 Últimos 5 días</div>
                ${drawCandlestick(data.chart_5d)}
            </div>
        `;
    }

    if (data.reasons && data.reasons.length > 0) {
        html += `<div class="modal-reasons-title">🎯 ¿Por qué está en ${data.side_label}?</div>`;
        html += `<div class="modal-reasons-sub">Estos son los motivos que componen el score de ${score}/100</div>`;
        html += `<div class="reasons-list">`;

        for (const r of data.reasons) {
            const points = r.points || 0;
            const pointsClass = points >= 0 ? "positive" : "negative";
            const pointsStr = points >= 0 ? `+${points}` : `${points}`;
            html += `
                <div class="reason-item">
                    <div class="reason-icon">${r.icon || ""}</div>
                    <div class="reason-text">
                        <div class="reason-label">${escapeHTML(r.label || "")}</div>
                        <div class="reason-detail">${escapeHTML(r.detail || "")}</div>
                    </div>
                    <div class="reason-points ${pointsClass}">${pointsStr}</div>
                </div>
            `;
        }

        html += `</div>`;
        html += `
            <div class="reasons-total">
                <span class="label">Total</span>
                <span class="value ticker-score ${sClass}">${score}/100</span>
            </div>
        `;
    }

    const tfs = data.timeframes || {};
    const tfNames = {
        daily: { label: "📅 Diario", subtitle: "Tendencia principal" },
        h1: { label: "⏰ 1 hora", subtitle: "Dirección del día" },
        m5: { label: "⚡ 5 minutos", subtitle: "Punto de entrada" },
    };

    let hasTF = false;
    for (const key of ["daily", "h1", "m5"]) {
        if (tfs[key]) { hasTF = true; break; }
    }

    if (hasTF) {
        html += `<div class="modal-tf-title">📊 Detalle por temporalidad</div>`;

        for (const key of ["daily", "h1", "m5"]) {
            const tf = tfs[key];
            if (!tf) continue;

            const tfMeta = tfNames[key] || { label: key, subtitle: "" };
            const tfScore = tf.score || 0;
            const tfClass = scoreClass(tfScore);
            const tfBias = tf.structure_bias_es || tf.structure_bias || "";
            const tfRegime = tf.regime_es || tf.regime || "";

            html += `
                <div class="tf-block">
                    <div class="tf-header">
                        <div class="tf-name">${tfMeta.label} · ${escapeHTML(tfMeta.subtitle)}</div>
                        <div class="tf-score ${tfClass}">${tfScore}/100</div>
                    </div>
                    <div class="tf-meta">${escapeHTML(tfBias)} · ${escapeHTML(tfRegime)}</div>
                </div>
            `;
        }
    }

    if (data.side_label && score > 0) {
        const strongText = strength === "MUY FUERTE" || strength === "FUERTE";
        const summary = strongText
            ? `${ticker} muestra una estructura claramente ${data.side_label === "LONG" ? "alcista" : "bajista"}. Las temporalidades están alineadas y los indicadores confirman la dirección.`
            : `${ticker} presenta una señal ${data.side_label === "LONG" ? "alcista" : "bajista"} pero con menos fuerza. Considera esperar confirmación adicional.`;

        html += `
            <div class="modal-summary">
                <div class="modal-summary-title">📌 En resumen</div>
                <div>${summary}</div>
            </div>
        `;
    }

    html += `<div class="modal-disclaimer">
        ⚠️ Esta aplicación ofrece análisis de datos, no asesoramiento financiero.
    </div>`;

    return html;
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}

// ============================================================
// TOAST
// ============================================================
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
            padding: 11px 22px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            z-index: 2000;
            transition: opacity 0.3s;
            opacity: 0;
            pointer-events: none;
        `;
        document.body.appendChild(toast);
    }

    const colors = {
        info: "var(--accent)",
        success: "var(--green)",
        error: "var(--red)",
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

// ============================================================
// INICIALIZACIÓN
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    setupTabs();
    fetchDestacados();

    document.getElementById("themeToggle").addEventListener("click", toggleTheme);

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