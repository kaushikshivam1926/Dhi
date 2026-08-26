// Add DOM Elements for Market Data
const mdTableBody = document.getElementById('marketdata-table-body');
const mdModal = document.getElementById('marketdata-modal');
const btnAddMd = document.getElementById('btn-add-marketdata');
const btnCloseMdModal = document.getElementById('btn-close-marketdata-modal');
const btnSaveMd = document.getElementById('btn-save-marketdata');
const mdProvider = document.getElementById('md-provider');
const mdType = document.getElementById('md-type');
const mdSymbol = document.getElementById('md-symbol');
const mdFields = document.getElementById('md-fields');
const mdClosingTime = document.getElementById('md-closing-time');
const settingAlphavantageKey = document.getElementById('setting-alphavantage-key');
const settingPolygonKey = document.getElementById('setting-polygon-key');
const btnSaveMdProviders = document.getElementById('btn-save-marketdata-providers');
const btnSyncAllMd = document.getElementById('btn-sync-all-marketdata');
const btnScheduleMd = document.getElementById('btn-schedule-marketdata');

let mdEditingIndex = -1;

function renderMarketData() {
    if (!mdTableBody) return;
    mdTableBody.innerHTML = '';
    
    if (!globalConfig.market_data_points) {
        globalConfig.market_data_points = [];
    }

    if (globalConfig.market_data_points.length === 0) {
        mdTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding: 20px;">No market data points configured. Click "Add Data Point" to start.</td></tr>`;
        return;
    }

    globalConfig.market_data_points.forEach((point, index) => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        
        tr.innerHTML = `
            <td style="padding: 15px; font-weight: 500;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <i data-lucide="activity" style="color:var(--primary); width:16px; height:16px;"></i>
                    ${point.symbol}
                </div>
            </td>
            <td style="padding: 15px; color: var(--text-light);">
                <span class="badge" style="background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-size:0.8rem;">
                    ${point.provider}
                </span>
                <span style="font-size:0.85rem; margin-left:8px; opacity:0.8;">(${point.type})</span>
            </td>
            <td style="padding: 15px; color: var(--text-light); font-size:0.9rem;">
                ${point.fields}
            </td>
            <td style="padding: 15px; color: var(--text-light);">
                <span style="display:flex; align-items:center; gap:4px;">
                    <i data-lucide="clock" style="width:14px; height:14px; opacity:0.7;"></i>
                    ${point.closing_time} IST
                </span>
            </td>
            <td style="padding: 15px; text-align: right;">
                <div style="display:flex; gap:8px; justify-content:flex-end;">
                    <button class="btn-icon" onclick="syncMarketData(${index})" title="Sync Now" style="color:var(--primary);">
                        <i data-lucide="refresh-cw" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="btn-icon" onclick="scheduleMarketData(${index})" title="Schedule" style="color:#f59e0b;">
                        <i data-lucide="calendar" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="btn-icon" onclick="editMarketData(${index})" title="Edit" style="color:var(--text-light);">
                        <i data-lucide="edit-2" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="btn-icon" onclick="deleteMarketData(${index})" title="Delete" style="color:#ef4444;">
                        <i data-lucide="trash-2" style="width:16px; height:16px;"></i>
                    </button>
                </div>
            </td>
        `;
        mdTableBody.appendChild(tr);
    });
    
    lucide.createIcons();
}

function openMdModal(index = -1) {
    mdEditingIndex = index;
    if (index >= 0) {
        document.getElementById('marketdata-modal-title').innerText = "Edit Data Point";
        const p = globalConfig.market_data_points[index];
        mdProvider.value = p.provider;
        mdType.value = p.type;
        mdSymbol.value = p.symbol;
        mdFields.value = p.fields;
        mdClosingTime.value = p.closing_time;
    } else {
        document.getElementById('marketdata-modal-title').innerText = "Add Data Point";
        mdProvider.value = 'alphavantage';
        mdType.value = 'stock';
        mdSymbol.value = '';
        mdFields.value = 'Open, High, Low, Close, Volume';
        mdClosingTime.value = '16:00';
    }
    mdModal.classList.add('active');
}

function closeMdModal() {
    mdModal.classList.remove('active');
}

async function saveMarketData() {
    if (!mdSymbol.value || !mdClosingTime.value) {
        appendLog("Please fill required fields", "error");
        return;
    }

    const newPoint = {
        provider: mdProvider.value,
        type: mdType.value,
        symbol: mdSymbol.value,
        fields: mdFields.value,
        closing_time: mdClosingTime.value
    };

    if (!globalConfig.market_data_points) {
        globalConfig.market_data_points = [];
    }

    if (mdEditingIndex >= 0) {
        globalConfig.market_data_points[mdEditingIndex] = newPoint;
    } else {
        globalConfig.market_data_points.push(newPoint);
    }

    closeMdModal();
    renderMarketData();
    
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(globalConfig)
        });
        if (res.ok) {
            appendLog("Market Data saved successfully.", "success");
        }
    } catch (e) {
        appendLog("Error saving config: " + e.message, "error");
    }
}

async function deleteMarketData(index) {
    if (confirm("Delete this data point?")) {
        globalConfig.market_data_points.splice(index, 1);
        renderMarketData();
        
        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(globalConfig)
            });
            appendLog("Data point deleted.", "success");
        } catch(e) {}
    }
}

function editMarketData(index) {
    openMdModal(index);
}

async function syncMarketData(index) {
    const point = globalConfig.market_data_points[index];
    appendLog(\`Starting sync for \${point.symbol}...\`, "info");
    try {
        const res = await fetch('/api/harvest/market', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ index: index })
        });
        const data = await res.json();
        if (data.status === 'success') {
            appendLog(\`Successfully synced \${point.symbol}\`, "success");
        } else {
            appendLog(\`Error syncing \${point.symbol}: \${data.message}\`, "error");
        }
    } catch (e) {
        appendLog(\`Failed to sync \${point.symbol}: \${e.message}\`, "error");
    }
}

async function scheduleMarketData(index) {
    openScheduleModal('market_data', null, null, null, index);
}

if (btnAddMd) btnAddMd.addEventListener('click', () => openMdModal());
if (btnCloseMdModal) btnCloseMdModal.addEventListener('click', closeMdModal);
if (btnSaveMd) btnSaveMd.addEventListener('click', saveMarketData);

if (btnSaveMdProviders) {
    btnSaveMdProviders.addEventListener('click', async () => {
        if (!globalConfig.api_keys) globalConfig.api_keys = {};
        globalConfig.api_keys.alphavantage = settingAlphavantageKey.value;
        globalConfig.api_keys.polygon = settingPolygonKey.value;
        
        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(globalConfig)
            });
            if (res.ok) {
                appendLog("Market Data Providers saved.", "success");
            }
        } catch (e) {
            appendLog("Error saving providers: " + e.message, "error");
        }
    });
}
