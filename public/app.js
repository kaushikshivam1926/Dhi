// Initialize Icons
lucide.createIcons();

// State
let globalConfig = {
    sync_limit: 1,
    obsidian_vault_path: "./Vault",
    raw_material_path: "./RawMaterials",
    transcription_engine: "none",
    document_engine: "gemini",
    whisper_model: "base",
    folder_organisation: "per_channel",
    api_keys: { assemblyai: "", gemini: "" },
    shows: []
};

// Sync Queue State
let isSyncRunning = false;
let isPaused = false;
let currentSyncController = null;
const syncQueue = [];
const activeSyncKeys = new Set(); // Stores "showIndex-episodeIndex" strands
let pendingDocs = [];
let isDocSyncRunning = false;
let activeDocName = "";
let docProcessState = {}; // filename -> "Ready" | "Queued" | "Harvesting"

let editingIndex = -1;

// DOM Elements
const tabs = document.querySelectorAll('.menu-item');
const contents = document.querySelectorAll('.tab-content');

// Dashboard Elements
const btnSync = document.getElementById('btn-sync');
const syncLogs = document.getElementById('sync-logs');
const dashShowsCount = document.getElementById('dash-shows-count');
const dashInsightsCount = document.getElementById('dash-insights-count');
const dashLatestTitle = document.getElementById('dash-latest-title');
const recentInsightsContainer = document.getElementById('recent-insights-container');
const libPendingList = document.getElementById('lib-pending-list');
const progressContainer = document.getElementById('progress-container');
const progressLabel = document.getElementById('progress-label');
const progressPercent = document.getElementById('progress-percent');
const progressBar = document.getElementById('progress-bar');
const btnSyncDocs = document.getElementById('btn-sync-docs');
const libPendingCount = document.getElementById('lib-pending-count');
const libRawPath = document.getElementById('lib-raw-path');
const btnPauseSync = document.getElementById('btn-pause-sync');
const btnStopSync = document.getElementById('btn-stop-sync');
const geminiStatsContainer = document.getElementById('gemini-stats-container');
const geminiRpm = document.getElementById('gemini-rpm');
const geminiTotal = document.getElementById('gemini-total');
const stopConfirmModal = document.getElementById('stop-confirmation-modal');
const btnTerminateQueue = document.getElementById('btn-terminate-queue');
const btnContinueQueue = document.getElementById('btn-continue-queue');
const btnCancelStop = document.getElementById('btn-cancel-stop');
const queueCountInfo = document.getElementById('queue-count-info');

// Shows Elements
const showsContainer = document.getElementById('shows-container');
const btnOpenModal = document.getElementById('btn-open-modal');
const modal = document.getElementById('add-show-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnSubmitShow = document.getElementById('btn-submit-show');

// Episode Browser Elements
const episodeModal = document.getElementById('episode-browser-modal');
const episodeList = document.getElementById('episode-list');
const btnCloseEpisodeModal = document.getElementById('btn-close-episode-modal');
const episodeLoading = document.getElementById('episode-loading');
const episodeBrowserTitle = document.getElementById('episode-browser-title');
const episodeSearch = document.getElementById('episode-search');

// Settings Elements
const settingSyncLimit = document.getElementById('setting-sync-limit');
const settingVault = document.getElementById('setting-vault');
const btnBrowseVault = document.getElementById('btn-browse-vault');
const settingEngine = document.getElementById('setting-engine');
const settingWhisperModel = document.getElementById('setting-whisper-model');
const settingKey = document.getElementById('setting-key');
const settingGeminiKey = document.getElementById('setting-gemini-key');
const settingGeminiModel = document.getElementById('setting-gemini-model');
const settingOllamaModel = document.getElementById('setting-ollama-model');
const ollamaModelGroup = document.getElementById('ollama-model-group');
const settingNuextractModel = document.getElementById('setting-nuextract-model');
const nuextractModelGroup = document.getElementById('nuextract-model-group');
const geminiProviderSection = document.getElementById('gemini-provider-section');
const assemblyProviderSection = document.getElementById('assembly-provider-section');
const whisperProviderSection = document.getElementById('whisper-provider-section');
const settingRawPath = document.getElementById('setting-raw-path');
const settingArchiveDocs = document.getElementById('setting-archive-docs');
const btnSaveSettings = document.getElementById('btn-save-settings');
const btnClearHistory = document.getElementById('btn-clear-history');
const settingHistoryRange = document.getElementById('setting-history-range');
const orgOptions = document.querySelectorAll('.org-option');
const orgPerChannel = document.getElementById('org-per-channel');
const orgFlat = document.getElementById('org-flat');
const btnDangerToggle = document.getElementById('btn-danger-toggle');
const dangerZoneBody = document.getElementById('danger-zone-body');

// Job History Modal Elements
const historyModal = document.getElementById('job-history-modal');
const btnCloseHistoryModal = document.getElementById('btn-close-history-modal');
const iconDangerChevron = document.getElementById('icon-danger-chevron');
const btnAdvancedDocsToggle = document.getElementById('btn-advanced-docs-toggle');
const advancedDocsBody = document.getElementById('advanced-docs-body');
const iconAdvancedDocsChevron = document.getElementById('icon-advanced-docs-chevron');
const settingRestructurePrompt = document.getElementById('setting-restructure-prompt');
const settingChunkSize = document.getElementById('setting-chunk-size');
const settingChunkOverlap = document.getElementById('setting-chunk-overlap');
const settingAutoRestructureOllama = document.getElementById('setting-auto-restructure-ollama');
const autoOllamaGroup = document.getElementById('auto-ollama-group');
const settingFidelityMinRatio = document.getElementById('setting-fidelity-min-ratio');
const syncQueueList = document.getElementById('sync-queue-list');

// Web Harvest Elements
const webSessionLabel = document.getElementById('web-session-label');
const webSessionIcon = document.getElementById('web-session-icon');
const btnWebSetup = document.getElementById('btn-web-setup');
const btnWebReset = document.getElementById('btn-web-reset');
const btnRunWebHarvest = document.getElementById('btn-run-web-harvest');
const webHarvestUrl = document.getElementById('web-harvest-url');
const webCookieString = document.getElementById('web-cookie-string');
const btnWebImportCookies = document.getElementById('btn-web-import-cookies');

// Research Harvest Elements
const btnArxivSearch = document.getElementById('btn-arxiv-search');
const arxivSearchQuery = document.getElementById('arxiv-search-query');
const arxivResultsContainer = document.getElementById('arxiv-results-container');
const settingDocumentEngine = document.getElementById('setting-document-engine');

// YouTube Harvesting Elements
const youtubeChannelsContainer = document.getElementById('youtube-channels-container');
const btnOpenYoutubeModal = document.getElementById('btn-open-youtube-modal');
const youtubeModal = document.getElementById('youtube-modal');
const btnCloseYoutubeModal = document.getElementById('btn-close-youtube-modal');
const btnSaveYoutube = document.getElementById('btn-save-youtube');
const youtubeChannelName = document.getElementById('youtube-channel-name');
const youtubeRssUrl = document.getElementById('youtube-rss-url');
const btnSyncAllYoutube = document.getElementById('btn-sync-all-youtube');
const btnScheduleYoutube = document.getElementById('btn-schedule-youtube');

// Telegram Harvesting Elements
const telegramChannelsContainer = document.getElementById('telegram-channels-container');
const btnOpenTelegramModal = document.getElementById('btn-open-telegram-modal');
const telegramModal = document.getElementById('telegram-modal');
const btnCloseTelegramModal = document.getElementById('btn-close-telegram-modal');
const btnSaveTelegram = document.getElementById('btn-save-telegram');
const telegramChannelName = document.getElementById('telegram-channel-name');
const telegramChannelId = document.getElementById('telegram-channel-id');
const telegramKeywords = document.getElementById('telegram-keywords');
const btnSyncAllTelegram = document.getElementById('btn-sync-all-telegram');
const btnScheduleTelegram = document.getElementById('btn-schedule-telegram');

// Initialize
async function init() {
    await loadConfig();
    await loadDashboardStats();
    await loadLibraryStats();
    await loadWebHarvestStatus();
    await loadScheduledJobs();
    
    // Load persisted sync state
    loadSyncState();
    
    setupEventListeners();
    
    // Auto-resume queue if not empty and not paused
    if (syncQueue.length > 0 && !isPaused && !isSyncRunning) {
        const next = syncQueue.shift();
        triggerSync(next.showIndex, next.episodeIndex, next.silent);
    }
}

// Tab Switching
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        contents.forEach(c => c.classList.remove('active'));
        
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        lucide.createIcons();
        
        if (tab.dataset.tab === 'library') {
            loadLibraryStats();
        }
        if (tab.dataset.tab === 'webharvest') {
            loadWebHarvestStatus();
            loadHarvestEditions();
        }
        if (tab.dataset.tab === 'audio-overview') {
            loadAudioOverviewTab();
        }
    });
});

// API Functions
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        globalConfig = await res.json();
        renderShows();
        renderYoutubeChannels();
        renderTelegramChannels();
        renderMarketData();
        renderCentralBankConfig();
        await renderSettings();
        if (dashShowsCount) dashShowsCount.innerText = globalConfig.shows.length;
    } catch (e) {
        appendLog("Error loading configuration: " + e.message, "error");
    }
}

async function loadDashboardStats() {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        
        if (stats.status === 'success') {
            if (dashInsightsCount) dashInsightsCount.innerText = stats.total_insights;
            if (dashShowsCount) dashShowsCount.innerText = stats.total_shows;
            if (dashLatestTitle && stats.recent_insights.length > 0) {
                dashLatestTitle.innerText = stats.recent_insights[0].title;
                dashLatestTitle.style.fontSize = "0.85rem";
                dashLatestTitle.style.opacity = "0.9";
            }
            
            renderRecentInsights(stats.recent_insights);
        }
    } catch (e) {
        console.error("Failed to load dashboard stats:", e);
    }
}

async function loadLibraryStats() {
    try {
        const res = await fetch('/api/doc_stats');
        const data = await res.json();
        if (data.status === 'success') {
            if (libPendingCount) libPendingCount.innerText = data.count;
            if (libRawPath) libRawPath.innerText = globalConfig.raw_material_path || "./RawMaterials";
            pendingDocs = data.pending_files || [];
            
            // Clean up deleted docs from state
            Object.keys(docProcessState).forEach(doc => {
                if (!pendingDocs.includes(doc)) {
                    delete docProcessState[doc];
                }
            });
            // Initialize new docs
            pendingDocs.forEach(doc => {
                if (!docProcessState[doc]) {
                    docProcessState[doc] = 'Ready';
                }
            });

            renderQueueList();
            if (typeof renderLibraryPendingDocs === 'function') {
                renderLibraryPendingDocs();
            }
        }
    } catch (e) {
        console.error("Failed to load library stats:", e);
    }
}

async function loadWebHarvestStatus() {
    try {
        const res = await fetch('/api/harvest/status');
        const data = await res.json();
        if (webSessionLabel) {
            if (data.has_session) {
                webSessionLabel.innerText = "Session Active";
                webSessionLabel.style.color = "var(--success)";
                webSessionIcon.style.color = "var(--success)";
            } else {
                webSessionLabel.innerText = "No Session Found";
                webSessionLabel.style.color = "#71717a";
                webSessionIcon.style.color = "#71717a";
            }
        }
    } catch (e) {
        console.error("Failed to load web harvest status:", e);
    }
}

// ── Toast System ──
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'info';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'alert-circle';
    if (type === 'warning') icon = 'alert-triangle';

    toast.innerHTML = `
        <i data-lucide="${icon}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    lucide.createIcons({ root: toast });

    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Sync Helper ──
function getSyncKey(showIndex, episodeIndex) {
    if (showIndex === null) return "all";
    if (episodeIndex === null) return `show-${showIndex}`;
    return `${showIndex}-${episodeIndex}`;
}

function updateEpisodeButton(showIndex, episodeIndex, status) {
    const btn = document.getElementById(`btn-sync-${showIndex}-${episodeIndex}`);
    if (!btn) return;

    if (status === 'syncing') {
        btn.disabled = true;
        btn.className = 'btn-primary btn-syncing';
        btn.innerHTML = `<i data-lucide="loader-2"></i> Syncing...`;
    } else if (status === 'queued') {
        btn.disabled = true;
        btn.className = 'btn-primary btn-queued';
        btn.innerHTML = `<i data-lucide="clock"></i> Queued`;
    } else if (status === 'ready' || status === 'synced') {
        btn.disabled = false;
        btn.className = 'btn-primary';
        btn.style.background = status === 'synced' ? '#475569' : '';
        btn.style.border = status === 'synced' ? '1px solid var(--border)' : '';
        
        const icon = status === 'synced' ? 'rotate-cw' : 'download';
        const text = status === 'synced' ? 'Resync' : 'Sync';
        btn.innerHTML = `<i data-lucide="${icon}"></i> ${text}`;
    }
    lucide.createIcons({ root: btn });
}

function renderRecentInsights(insights) {
    if (!recentInsightsContainer) return;
    
    if (insights.length === 0) {
        recentInsightsContainer.innerHTML = `<div style="padding: 20px; text-align: center; color: #71717a;">No insights harvested yet.</div>`;
        return;
    }
    
    recentInsightsContainer.innerHTML = '';
    insights.forEach(insight => {
        const row = document.createElement('div');
        row.className = 'insight-row';
        
        // Format date from YYYYMMDD
        let displayDate = insight.date;
        if (insight.date && insight.date.length === 8) {
            displayDate = `${insight.date.substring(0,4)}-${insight.date.substring(4,6)}-${insight.date.substring(6,8)}`;
        }
        
        row.innerHTML = `
            <div class="insight-info">
                <div class="insight-title">${insight.title}</div>
                <div class="insight-meta">${insight.channel} • ${insight.show} • ${displayDate}</div>
            </div>
            <div class="insight-badge">
                Synced
            </div>
        `;
        recentInsightsContainer.appendChild(row);
    });
    
    lucide.createIcons();
}

async function saveConfig() {
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(globalConfig)
        });
        await loadConfig(); // Refresh
        return true;
    } catch (e) {
        alert("Failed to save configuration.");
        return false;
    }
}

// UI Renderers
function renderShows() {
    showsContainer.innerHTML = '';
    
    // Populate Datalist
    const datalist = document.getElementById('channel-list');
    datalist.innerHTML = '';
    const uniqueChannels = [...new Set(globalConfig.shows.map(s => s.channel_name))];
    uniqueChannels.forEach(c => {
        const option = document.createElement('option');
        option.value = c;
        datalist.appendChild(option);
    });

    // Grouping
    const grouped = {};
    globalConfig.shows.forEach((show, index) => {
        if (!grouped[show.channel_name]) grouped[show.channel_name] = [];
        grouped[show.channel_name].push({ ...show, originalIndex: index });
    });

    for (const channel in grouped) {
        // Create Channel Header
        const header = document.createElement('h3');
        header.className = 'channel-group-header';
        header.innerHTML = `<i data-lucide="folder-open"></i> ${channel}`;
        showsContainer.appendChild(header);

        // Group Container
        const groupCards = document.createElement('div');
        groupCards.className = 'shows-grid';
        groupCards.style.marginBottom = '2rem';
        groupCards.style.gridColumn = '1 / -1'; // Span full width

        grouped[channel].forEach(show => {
            const card = document.createElement('div');
            card.className = 'show-card';
            const isYoutubeFeed = show.rss_url && show.rss_url.includes('youtube.com');
            const iconName = isYoutubeFeed ? 'youtube' : 'radio';
            card.innerHTML = `
                <div class="show-card-actions-top">
                    <button class="icon-btn" onclick="editShow(${show.originalIndex})" title="Edit Show" aria-label="Edit Show">
                        <i data-lucide="edit-3"></i>
                    </button>
                    <button class="icon-btn danger" onclick="deleteShow(${show.originalIndex})" title="Remove Show" aria-label="Remove Show">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
                <div>
                    <div class="show-channel"><i data-lucide="${iconName}" class="w-3 h-3 inline"></i> ${show.channel_name}</div>
                    <div class="show-title" style="padding-right: 80px;">${show.show_name}</div>
                    <div class="show-url" title="${show.rss_url}">${show.rss_url}</div>
                </div>
                <div class="show-actions" style="justify-content: flex-start; gap: 8px;">
                     <button class="btn-primary" onclick="browseEpisodes(${show.originalIndex})" style="padding: 8px 12px; font-size: 0.8rem; background: #374151;">
                        <i data-lucide="list-video"></i> Browse
                    </button>
                    <button class="btn-primary" onclick="syncSpecificShow(${show.originalIndex})" style="padding: 8px 12px; font-size: 0.8rem; background: var(--success);">
                        <i data-lucide="refresh-cw"></i> Sync
                    </button>
                </div>
            `;
            groupCards.appendChild(card);
        });
        showsContainer.appendChild(groupCards);
    }
    
    lucide.createIcons();
}

async function updateGeminiModelsDropdown(apiKey) {
    if (!settingGeminiModel) return;
    
    // Keep reference of current selected model to restore if possible
    const currentVal = globalConfig.gemini_model || settingGeminiModel.value || "gemini-1.5-flash";
    
    settingGeminiModel.innerHTML = '<option value="">Loading models...</option>';
    
    try {
        const res = await fetch('/api/gemini/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        const data = await res.json();
        if (data.status === 'success' && data.models) {
            settingGeminiModel.innerHTML = '';
            data.models.forEach(model => {
                const opt = document.createElement('option');
                opt.value = model.value;
                opt.innerText = model.label;
                settingGeminiModel.appendChild(opt);
            });
            
            // Restore selection
            settingGeminiModel.value = currentVal;
            // If the restored value is not valid (i.e. not in the options), select the first option or fallback
            if (settingGeminiModel.selectedIndex === -1 && settingGeminiModel.options.length > 0) {
                settingGeminiModel.selectedIndex = 0;
            }
        }
    } catch (e) {
        console.error("Failed to load Gemini models:", e);
        settingGeminiModel.innerHTML = '<option value="gemini-1.5-flash">Gemini 1.5 Flash (Fallback)</option>';
    }
}

async function updateOllamaModelsDropdown() {
    const settingSelect = document.getElementById('setting-ollama-model');
    const cbSelect = document.getElementById('cb-ollama-model');
    
    if (!settingSelect && !cbSelect) return;

    const currentVal = globalConfig.ollama_model || "gemma2:9b";
    
    [settingSelect, cbSelect].forEach(select => {
        if (select) select.innerHTML = '<option value="">Loading models...</option>';
    });

    try {
        const res = await fetch('/api/ollama/models');
        const data = await res.json();
        if (data.status === 'success' && data.models) {
            [settingSelect, cbSelect].forEach(select => {
                if (!select) return;
                select.innerHTML = '';
                if (data.models.length === 0) {
                    select.innerHTML = '<option value="">No models found (Check Ollama list)</option>';
                } else {
                    data.models.forEach(model => {
                        const opt = document.createElement('option');
                        opt.value = model.value;
                        opt.innerText = model.label;
                        select.appendChild(opt);
                    });
                }
                
                // Restore selection
                select.value = currentVal;
                if (select.selectedIndex === -1 && select.options.length > 0) {
                    select.selectedIndex = 0;
                }
            });
        } else {
            [settingSelect, cbSelect].forEach(select => {
                if (select) select.innerHTML = `<option value="">${data.message || 'Ollama unavailable'}</option>`;
            });
        }
    } catch (e) {
        console.error("Failed to load Ollama models:", e);
        [settingSelect, cbSelect].forEach(select => {
            if (select) select.innerHTML = '<option value="">Ollama offline or not installed</option>';
        });
    }
}

function toggleDynamicSettings() {
    const docEngine = settingDocumentEngine ? settingDocumentEngine.value : "gemini";
    const sttEngine = settingEngine ? settingEngine.value : "none";
    
    // Toggle Auto-mode local restructuring checkbox (only meaningful in Auto mode)
    if (autoOllamaGroup) {
        autoOllamaGroup.style.display = (docEngine === 'auto') ? 'block' : 'none';
    }

    // Toggle Ollama model selector — for the Ollama engine, or Auto mode when local
    // restructuring is enabled (that path also needs a model chosen).
    const autoRestructureOn = settingAutoRestructureOllama ? settingAutoRestructureOllama.checked : false;
    if (ollamaModelGroup) {
        if (docEngine === 'ollama' || (docEngine === 'auto' && autoRestructureOn)) {
            ollamaModelGroup.style.display = 'block';
        } else {
            ollamaModelGroup.style.display = 'none';
        }
    }
    
    // Toggle NuExtract model selector — shown for 'nuextract' and for 'auto'
    // (auto routes image-format PDFs through the NuExtract VLM).
    if (nuextractModelGroup) {
        if (docEngine === 'nuextract' || docEngine === 'auto') {
            nuextractModelGroup.style.display = 'block';
        } else {
            nuextractModelGroup.style.display = 'none';
        }
    }
    
    // Toggle Whisper group
    if (whisperProviderSection) {
        whisperProviderSection.style.display = (sttEngine === 'whisper') ? 'block' : 'none';
    }
    
    // Toggle AssemblyAI group
    if (assemblyProviderSection) {
        assemblyProviderSection.style.display = (sttEngine === 'assemblyai') ? 'block' : 'none';
    }
    
    // Toggle Gemini configuration group (show if docEngine OR sttEngine is gemini)
    if (geminiProviderSection) {
        if (docEngine === 'gemini' || sttEngine === 'gemini') {
            geminiProviderSection.style.display = 'block';
        } else {
            geminiProviderSection.style.display = 'none';
        }
    }
}

async function renderSettings() {
    settingSyncLimit.value = globalConfig.sync_limit || 1;
    if (!globalConfig) return;
    
    if (settingSyncLimit) settingSyncLimit.value = globalConfig.sync_limit || "1";
    if (settingVault) settingVault.value = globalConfig.obsidian_vault_path || "";
    if (settingRawPath) settingRawPath.value = globalConfig.raw_material_path || "./RawMaterials";
    if (settingArchiveDocs) settingArchiveDocs.checked = !!globalConfig.archive_processed_docs;
    
    if (settingEngine) settingEngine.value = globalConfig.transcription_engine || "none";
    if (settingWhisperModel) settingWhisperModel.value = globalConfig.whisper_model || "base";
    if (settingDocumentEngine) settingDocumentEngine.value = globalConfig.document_engine || "gemini";
    if (settingOllamaModel) settingOllamaModel.value = globalConfig.ollama_model || "gemma2:9b";
    if (settingNuextractModel) settingNuextractModel.value = globalConfig.nuextract_model || "numind/NuExtract3-mlx-4bits";
    if (settingRestructurePrompt) settingRestructurePrompt.value = globalConfig.restructure_prompt || "";
    if (settingChunkSize) settingChunkSize.value = globalConfig.chunk_size || 16000;
    if (settingChunkOverlap) settingChunkOverlap.value = globalConfig.chunk_overlap || 1000;
    if (settingAutoRestructureOllama) settingAutoRestructureOllama.checked = !!globalConfig.auto_restructure_ollama;
    if (settingFidelityMinRatio) settingFidelityMinRatio.value = (globalConfig.fidelity_min_ratio != null ? globalConfig.fidelity_min_ratio : 0.5);

    // NotebookLM Audio Overview Settings
    const audioCfg = globalConfig.audio_overview || {};
    const settingAudioInputFolder = document.getElementById('setting-audio-input-folder');
    const settingAudioOutputFolder = document.getElementById('setting-audio-output-folder');
    const settingAudioTargetDuration = document.getElementById('setting-audio-target-duration');
    const settingAudioHost1Voice = document.getElementById('setting-audio-host1-voice');
    const settingAudioHost2Voice = document.getElementById('setting-audio-host2-voice');
    const settingAudioDefaultStyle = document.getElementById('setting-audio-default-style');
    const settingAudioAutoGenerate = document.getElementById('setting-audio-auto-generate');

    if (settingAudioInputFolder) settingAudioInputFolder.value = audioCfg.input_folder || "/Users/shivamkaushik/Library/Mobile Documents/iCloud~md~obsidian/Documents/SAMVIT/05_Digests";
    if (settingAudioOutputFolder) settingAudioOutputFolder.value = audioCfg.output_folder || "./Vault/Podcasts";
    if (settingAudioTargetDuration) settingAudioTargetDuration.value = audioCfg.target_duration || "18-20";
    if (settingAudioDefaultStyle) settingAudioDefaultStyle.value = audioCfg.default_style || "deep_dive";
    if (settingAudioAutoGenerate) settingAudioAutoGenerate.checked = !!audioCfg.auto_generate;

    if (audioOverviewVoices.length === 0) {
        await loadAudioVoices();
    }

    if (settingAudioHost1Voice && settingAudioHost2Voice && audioOverviewVoices.length > 0) {
        settingAudioHost1Voice.innerHTML = '';
        settingAudioHost2Voice.innerHTML = '';
        audioOverviewVoices.forEach(v => {
            const opt1 = document.createElement('option');
            opt1.value = v.id;
            opt1.textContent = v.name;
            if (v.id === (audioCfg.host1_voice || 'en-US-AndrewNeural')) opt1.selected = true;
            settingAudioHost1Voice.appendChild(opt1);

            const opt2 = document.createElement('option');
            opt2.value = v.id;
            opt2.textContent = v.name;
            if (v.id === (audioCfg.host2_voice || 'en-US-AvaNeural')) opt2.selected = true;
            settingAudioHost2Voice.appendChild(opt2);
        });
    }

    
    if (globalConfig.api_keys) {
        if (settingKey) settingKey.value = globalConfig.api_keys.assemblyai || "";
        if (settingGeminiKey) settingGeminiKey.value = globalConfig.api_keys.gemini || "";
        if (settingAlphavantageKey) settingAlphavantageKey.value = globalConfig.api_keys.alphavantage || "";
        if (typeof settingEodhdKey !== 'undefined' && settingEodhdKey) settingEodhdKey.value = globalConfig.api_keys.eodhd || "";
        if (settingPolygonKey) settingPolygonKey.value = globalConfig.api_keys.polygon || "";
        if (settingRefinitivKey) settingRefinitivKey.value = globalConfig.api_keys.refinitiv_app_key || "";
        if (settingRefinitivUsername) settingRefinitivUsername.value = globalConfig.api_keys.refinitiv_username || "";
        if (settingRefinitivPassword) settingRefinitivPassword.value = globalConfig.api_keys.refinitiv_password || "";
    }
    
    const geminiKeyVal = globalConfig.api_keys ? (globalConfig.api_keys.gemini || "") : "";
    await updateGeminiModelsDropdown(geminiKeyVal);
    await updateOllamaModelsDropdown();
    
    if (globalConfig.folder_organisation === 'flat') {
        orgFlat.checked = true;
    } else {
        orgPerChannel.checked = true;
    }
    updateOrgOptionStyles();
    toggleDynamicSettings();
}

function updateOrgOptionStyles() {
    orgOptions.forEach(opt => {
        const radio = opt.querySelector('input[type="radio"]');
        opt.classList.toggle('selected', radio.checked);
    });
}

// ── Sync State Persistence ──
let activeItem = null; // Stores { showIndex, episodeIndex, label } of what's currently running

function saveSyncState() {
    const state = {
        syncQueue,
        isPaused,
        activeItem,
        activeSyncKeys: Array.from(activeSyncKeys)
    };
    localStorage.setItem('dhi_sync_state', JSON.stringify(state));
}

function loadSyncState() {
    const saved = localStorage.getItem('dhi_sync_state');
    if (saved) {
        try {
            const state = JSON.parse(saved);
            syncQueue.length = 0;
            syncQueue.push(...(state.syncQueue || []));
            isPaused = state.isPaused || false;
            activeItem = state.activeItem || null;
            
            // If there was an active item that got interrupted by refresh, 
            // put it back at the front of the queue.
            if (activeItem) {
                syncQueue.unshift(activeItem);
                activeItem = null; 
            }
            
            activeSyncKeys.clear();
            (state.activeSyncKeys || []).forEach(k => activeSyncKeys.add(k));
            
            // Sync UI Pause State
            if (isPaused) {
                btnPauseSync.innerHTML = `<i data-lucide="play" style="width: 14px; height: 14px;"></i> Resume`;
                btnPauseSync.classList.add('btn-active');
            } else {
                btnPauseSync.innerHTML = `<i data-lucide="pause" style="width: 14px; height: 14px;"></i> Pause`;
                btnPauseSync.classList.remove('btn-active');
            }
            
            renderQueueList();
            lucide.createIcons();
        } catch (e) {
            console.error("Failed to load sync state:", e);
        }
    }
}

function createQueueItemElement(item, status, customStatusText = null) {
    let title = "Podcast Sync";
    let meta = "All Shows";
    
    if (item.showIndex !== null && globalConfig.shows[item.showIndex]) {
        const show = globalConfig.shows[item.showIndex];
        const titleMatch = (item.label || "").match(/'([^']+)'/);
        const displayTitle = titleMatch ? titleMatch[1] : (item.label || show.show_name);
        
        title = item.episodeIndex !== null ? `Ep ${item.episodeIndex}: ${displayTitle}` : show.show_name;
        meta = show.channel_name || show.show_name;
    }

    const itemEl = document.createElement('div');
    itemEl.className = 'queue-item' + (status === 'active' ? ' active-processing' : '');
    
    let badgeText = customStatusText || (status === 'active' ? 'Syncing...' : 'Pending');

    itemEl.innerHTML = `
        <div class="queue-item-info">
            <div class="queue-item-title" style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="headphones" style="width:14px; height:14px; color:var(--primary);"></i>
                <span>${title}</span>
            </div>
            <div class="queue-item-meta">${meta}</div>
        </div>
        <div class="queue-status-badge ${status === 'active' ? 'active' : ''}">
            ${badgeText}
        </div>
    `;
    lucide.createIcons({ root: itemEl });
    return itemEl;
}

function createDocQueueItemElement(filename, status, customStatusText = null, customMeta = null) {
    const itemEl = document.createElement('div');
    itemEl.className = 'queue-item' + (status === 'active' ? ' active-processing' : '');
    
    const displayTitle = filename;
    let meta = customMeta || ("Document Engine: " + (globalConfig.document_engine || "gemini"));

    let badgeText = customStatusText || (status === 'active' ? 'Harvesting...' : 'Queued');

    itemEl.innerHTML = `
        <div class="queue-item-info">
            <div class="queue-item-title" style="display:flex; align-items:center; gap:6px;">
                <i data-lucide="file-text" style="width:14px; height:14px; color:var(--primary);"></i>
                <span>${displayTitle}</span>
            </div>
            <div class="queue-item-meta">${meta}</div>
        </div>
        <div class="queue-status-badge ${status === 'active' ? 'active' : ''}">
            ${badgeText}
        </div>
    `;
    lucide.createIcons({ root: itemEl });
    return itemEl;
}

function renderQueueList() {
    if (!syncQueueList) return;
    
    const hasPodcasts = syncQueue.length > 0 || (isSyncRunning && activeItem);
    const hasDocs = pendingDocs.length > 0 || isDocSyncRunning;
    
    if (!hasPodcasts && !hasDocs) {
        syncQueueList.innerHTML = `<div style="padding: 20px; text-align: center; color: #71717a;">Queue is currently empty.</div>`;
        return;
    }
    
    syncQueueList.innerHTML = '';
    
    // 1. Render Active Podcast Item
    if (isSyncRunning && activeItem) {
        syncQueueList.appendChild(createQueueItemElement(activeItem, 'active'));
    }
    
    // 2. Render Active Document Item
    if (isDocSyncRunning) {
        const displayDocName = activeDocName || (pendingDocs.length > 0 ? pendingDocs[0] : "Initializing...");
        syncQueueList.appendChild(createDocQueueItemElement(displayDocName, 'active'));
    }
    
    // 3. Render Pending Podcast Items
    syncQueue.forEach(item => {
        let podcastStatus = isPaused ? 'Paused' : (isSyncRunning ? 'Waiting...' : 'Pending');
        syncQueueList.appendChild(createQueueItemElement(item, 'pending', podcastStatus));
    });
    
    // 4. Render Pending Document Items
    pendingDocs.forEach(doc => {
        if (isDocSyncRunning && (doc === activeDocName || (!activeDocName && doc === pendingDocs[0]))) {
            return;
        }
        
        let state = docProcessState[doc] || 'Ready';
        let docStatus = 'Queued';
        let docMeta = null;
        
        if (isDocSyncRunning && activeDocName === doc) {
            docStatus = 'Harvesting...';
        } else if (state === 'Queued') {
            docStatus = isDocSyncRunning ? 'Waiting...' : 'Queued';
        } else {
            docStatus = 'Ready (Manual Start)';
            docMeta = '<span style="color: #fbbf24;">Action Required: Click Start in Library</span>';
        }
        
        syncQueueList.appendChild(createDocQueueItemElement(doc, 'pending', docStatus, docMeta));
    });
}

function renderLibraryPendingDocs() {
    if (!libPendingList) return;
    if (pendingDocs.length === 0) {
        libPendingList.innerHTML = `<div style="padding: 20px; text-align: center; color: #71717a;">No pending documents found.</div>`;
        return;
    }
    
    libPendingList.innerHTML = '';
    pendingDocs.forEach((doc, idx) => {
        const state = docProcessState[doc] || 'Ready';
        const isQueued = state === 'Queued';
        let isHarvesting = (isDocSyncRunning && activeDocName === doc) || state === 'Harvesting';
        
        let btnHtml = '';
        if (state === 'Ready') {
            btnHtml = `<button class="btn-primary btn-queue-doc" data-doc="${doc.replace(/"/g, '&quot;')}" style="padding: 4px 10px; font-size: 0.8rem;"><i data-lucide="play" style="width:14px; height:14px;"></i> Start</button>`;
        } else if (state === 'Queued') {
            btnHtml = `<button class="btn-secondary btn-unqueue-doc" data-doc="${doc.replace(/"/g, '&quot;')}" style="padding: 4px 10px; font-size: 0.8rem; color: #ef4444;"><i data-lucide="x" style="width:14px; height:14px;"></i> Cancel</button>`;
        }
        
        let displayState = isHarvesting ? 'Harvesting...' : state;
        const badgeHtml = `<div class="queue-status-badge ${isHarvesting ? 'active' : ''}" style="margin-left: auto;">${displayState}</div>`;
        
        const itemEl = document.createElement('div');
        itemEl.className = 'queue-item' + (isHarvesting ? ' active-processing' : '');
        itemEl.style.display = 'flex';
        itemEl.style.alignItems = 'center';
        itemEl.innerHTML = `
            <div class="queue-item-info" style="flex: 1;">
                <div class="queue-item-title" style="display:flex; align-items:center; gap:6px;">
                    <i data-lucide="file-text" style="width:14px; height:14px; color:var(--primary);"></i>
                    <span style="word-break:break-all;">${doc}</span>
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
                ${badgeHtml}
                ${btnHtml}
            </div>
        `;
        libPendingList.appendChild(itemEl);
    });
    lucide.createIcons({ root: libPendingList });

    // Re-attach event listeners for dynamic buttons
    libPendingList.querySelectorAll('.btn-queue-doc').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const doc = e.currentTarget.getAttribute('data-doc');
            window.queueDocument(doc);
        });
    });
    libPendingList.querySelectorAll('.btn-unqueue-doc').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const doc = e.currentTarget.getAttribute('data-doc');
            window.unqueueDocument(doc);
        });
    });
}

window.queueDocument = function(doc) {
    docProcessState[doc] = 'Queued';
    renderLibraryPendingDocs();
    renderQueueList();
    processNextDoc(true);
};

window.unqueueDocument = function(doc) {
    if (docProcessState[doc] === 'Queued') {
        docProcessState[doc] = 'Ready';
        renderLibraryPendingDocs();
        renderQueueList();
    }
};

async function processNextDoc(switchTab = false) {
    if (isDocSyncRunning) return;
    const nextDoc = pendingDocs.find(d => docProcessState[d] === "Queued");
    if (!nextDoc) return;

    docProcessState[nextDoc] = "Harvesting";
    renderLibraryPendingDocs();
    renderQueueList();
    
    await triggerDocSync([nextDoc], switchTab);
    
    // Once finished, cleanup state
    delete docProcessState[nextDoc];
    await loadLibraryStats();
    processNextDoc(false);
}

// Event Listeners
function setupEventListeners() {
    // Update Gemini models dropdown when the key is typed / modified
    if (settingGeminiKey) {
        const handleKeyChange = async () => {
            const newKey = settingGeminiKey.value.trim();
            await updateGeminiModelsDropdown(newKey);
        };
        settingGeminiKey.addEventListener('change', handleKeyChange);
        settingGeminiKey.addEventListener('blur', handleKeyChange);
    }

    // Save Settings
    btnSaveSettings.addEventListener('click', async () => {
        globalConfig.sync_limit = settingSyncLimit.value;
        globalConfig.obsidian_vault_path = settingVault.value;
        globalConfig.raw_material_path = settingRawPath.value;
        globalConfig.archive_processed_docs = settingArchiveDocs ? settingArchiveDocs.checked : false;
        globalConfig.transcription_engine = settingEngine.value;
        globalConfig.document_engine = settingDocumentEngine.value;
        globalConfig.ollama_model = settingOllamaModel ? settingOllamaModel.value : "";
        globalConfig.nuextract_model = settingNuextractModel ? settingNuextractModel.value : "numind/NuExtract3-mlx-4bits";
        globalConfig.whisper_model = settingWhisperModel.value;
        globalConfig.gemini_model = settingGeminiModel.value;
        globalConfig.folder_organisation = orgPerChannel.checked ? 'per_channel' : 'flat';
        
        globalConfig.restructure_prompt = settingRestructurePrompt.value;
        globalConfig.chunk_size = parseInt(settingChunkSize.value) || 16000;
        globalConfig.chunk_overlap = parseInt(settingChunkOverlap.value) || 1000;
        globalConfig.auto_restructure_ollama = settingAutoRestructureOllama ? settingAutoRestructureOllama.checked : false;
        if (settingFidelityMinRatio) {
            let fmr = parseFloat(settingFidelityMinRatio.value);
            if (isNaN(fmr) || fmr <= 0 || fmr > 1) fmr = 0.5;
            globalConfig.fidelity_min_ratio = fmr;
        }
        
        if (!globalConfig.api_keys) globalConfig.api_keys = {};
        globalConfig.api_keys.assemblyai = settingKey.value;
        globalConfig.api_keys.gemini = settingGeminiKey.value;
        
        btnSaveSettings.innerText = "Saving...";
        await saveConfig();
        setTimeout(() => {
            btnSaveSettings.innerText = "Save Configuration";
            showToast("Configuration saved successfully", "success");
        }, 1000);
    });

    async function saveSettings(btn, successMsg) {
        globalConfig.sync_limit = settingSyncLimit.value;
        globalConfig.obsidian_vault_path = settingVault.value;
        globalConfig.raw_material_path = settingRawPath.value;
        globalConfig.archive_processed_docs = settingArchiveDocs ? settingArchiveDocs.checked : false;
        globalConfig.transcription_engine = settingEngine.value;
        globalConfig.document_engine = settingDocumentEngine.value;
        globalConfig.ollama_model = settingOllamaModel ? settingOllamaModel.value : "";
        globalConfig.nuextract_model = settingNuextractModel ? settingNuextractModel.value : "numind/NuExtract3-mlx-4bits";
        globalConfig.whisper_model = settingWhisperModel.value;
        globalConfig.gemini_model = settingGeminiModel.value;
        globalConfig.folder_organisation = orgPerChannel.checked ? 'per_channel' : 'flat';
        
        globalConfig.restructure_prompt = settingRestructurePrompt.value;
        globalConfig.chunk_size = parseInt(settingChunkSize.value) || 16000;
        globalConfig.chunk_overlap = parseInt(settingChunkOverlap.value) || 1000;
        globalConfig.auto_restructure_ollama = settingAutoRestructureOllama ? settingAutoRestructureOllama.checked : false;
        if (settingFidelityMinRatio) {
            let fmr = parseFloat(settingFidelityMinRatio.value);
            if (isNaN(fmr) || fmr <= 0 || fmr > 1) fmr = 0.5;
            globalConfig.fidelity_min_ratio = fmr;
        }

        // Save NotebookLM Audio Overview Settings
        const settingAudioInputFolder = document.getElementById('setting-audio-input-folder');
        const settingAudioOutputFolder = document.getElementById('setting-audio-output-folder');
        const settingAudioTargetDuration = document.getElementById('setting-audio-target-duration');
        const settingAudioHost1Voice = document.getElementById('setting-audio-host1-voice');
        const settingAudioHost2Voice = document.getElementById('setting-audio-host2-voice');
        const settingAudioDefaultStyle = document.getElementById('setting-audio-default-style');
        const settingAudioAutoGenerate = document.getElementById('setting-audio-auto-generate');

        globalConfig.audio_overview = {
            input_folder: settingAudioInputFolder ? settingAudioInputFolder.value.trim() : "/Users/shivamkaushik/Library/Mobile Documents/iCloud~md~obsidian/Documents/SAMVIT/05_Digests",
            output_folder: settingAudioOutputFolder ? settingAudioOutputFolder.value.trim() : "./Vault/Podcasts",
            target_duration: settingAudioTargetDuration ? settingAudioTargetDuration.value : "18-20",
            host1_voice: settingAudioHost1Voice ? settingAudioHost1Voice.value : "en-US-AndrewNeural",
            host2_voice: settingAudioHost2Voice ? settingAudioHost2Voice.value : "en-US-AvaNeural",
            default_style: settingAudioDefaultStyle ? settingAudioDefaultStyle.value : "deep_dive",
            auto_generate: settingAudioAutoGenerate ? settingAudioAutoGenerate.checked : false
        };

        if (!globalConfig.api_keys) globalConfig.api_keys = {};
        globalConfig.api_keys.assemblyai = settingKey.value;
        globalConfig.api_keys.gemini = settingGeminiKey.value;
        
        const originalText = btn.innerText;
        btn.innerText = "Saving...";
        await saveConfig();
        setTimeout(() => {
            btn.innerText = originalText;
            showToast(successMsg, "success");
        }, 800);
    }

    // Engine selectors toggle listeners
    if (settingEngine) {
        settingEngine.addEventListener('change', () => {
            toggleDynamicSettings();
        });
    }
    if (settingDocumentEngine) {
        settingDocumentEngine.addEventListener('change', () => {
            toggleDynamicSettings();
        });
    }
    if (settingAutoRestructureOllama) {
        settingAutoRestructureOllama.addEventListener('change', () => {
            toggleDynamicSettings();
        });
    }

    // Vault path Browse button
    if (btnBrowseVault) {
        btnBrowseVault.addEventListener('click', async () => {
            try {
                if (!window.showDirectoryPicker) {
                    alert('Folder picker is not supported in this browser. Please type the path manually.');
                    return;
                }
                const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
                // Build a best-effort path string from the handle name
                settingVault.value = dirHandle.name;
                settingVault.title = `Selected folder: ${dirHandle.name}`;
                appendLog(`Vault folder selected: ${dirHandle.name}`, 'success');
            } catch (err) {
                if (err.name !== 'AbortError') {
                    appendLog(`Folder picker error: ${err.message}`, 'error');
                }
            }
        });
    }

    // Organisation mode visual toggle
    orgOptions.forEach(opt => {
        opt.addEventListener('click', () => {
            // Give the browser a tick to update checked state first
            setTimeout(updateOrgOptionStyles, 0);
        });
    });

    // Danger-zone collapsible
    if (btnDangerToggle && dangerZoneBody) {
        btnDangerToggle.addEventListener('click', () => {
            const isOpen = btnDangerToggle.getAttribute('aria-expanded') === 'true';
            btnDangerToggle.setAttribute('aria-expanded', String(!isOpen));
            dangerZoneBody.style.display = isOpen ? 'none' : 'block';
            lucide.createIcons();
        });
    }

    // Advanced document processing collapsible
    if (btnAdvancedDocsToggle && advancedDocsBody) {
        btnAdvancedDocsToggle.addEventListener('click', () => {
            const isOpen = btnAdvancedDocsToggle.getAttribute('aria-expanded') === 'true';
            btnAdvancedDocsToggle.setAttribute('aria-expanded', String(!isOpen));
            advancedDocsBody.style.display = isOpen ? 'none' : 'block';
            lucide.createIcons();
        });
    }

    // STT collapsible removed since UI has been streamlined and unified

    // Clear History
    if (btnClearHistory) {
        btnClearHistory.addEventListener('click', async () => {
            const range = settingHistoryRange.value;
            let displayRange = range === 'all' ? 'ALL history' : `history from the last ${range} days`;
            
            if(!confirm(`WARNING: Are you absolutely sure you want to permanently delete and clear ${displayRange}? This action cannot be undone.`)) {
                return;
            }

            document.querySelector('[data-tab="dashboard"]').click();
            appendLog(`Initiating purge sequence for ${displayRange}...`, "info");
            
            try {
                const res = await fetch('/api/clear_history', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ days: range })
                });
                const data = await res.json();
                
                if (data.status === 'success') {
                    data.logs.forEach(l => appendLog("> " + l));
                    appendLog(`Purge complete.`, "success");
                } else {
                    appendLog("Purge Error: " + data.message, "error");
                }
            } catch (e) {
                appendLog("Connection Error: " + e.message, "error");
            }
        });
    }

    // Modal
    btnOpenModal.addEventListener('click', () => {
        editingIndex = -1;
        document.getElementById('modal-title').innerText = "Add Podcast Feed";
        document.getElementById('new-channel').value = '';
        document.getElementById('new-show').value = '';
        document.getElementById('new-url').value = '';
        modal.classList.add('active');
    });
    
    btnCloseModal.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    btnCloseEpisodeModal.addEventListener('click', () => {
        episodeModal.classList.remove('active');
        episodeList.innerHTML = ''; // Instant cleanup for performance
    });

    if (btnCloseHistoryModal) {
        btnCloseHistoryModal.addEventListener('click', () => {
            historyModal.classList.remove('active');
        });
    }

    episodeSearch.addEventListener('input', () => {
        const query = episodeSearch.value.toLowerCase();
        const rows = episodeList.querySelectorAll('.episode-row');
        rows.forEach(row => {
            const title = row.dataset.title.toLowerCase();
            row.style.display = title.includes(query) ? 'flex' : 'none';
        });
    });

    window.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
        if (e.target === episodeModal) {
            episodeModal.classList.remove('active');
            episodeList.innerHTML = ''; // Instant cleanup
        }
        if (e.target === historyModal) {
            historyModal.classList.remove('active');
        }
    });

    // Submit New Show
    btnSubmitShow.addEventListener('click', async () => {
        const channel = document.getElementById('new-channel').value;
        const show = document.getElementById('new-show').value;
        let url = document.getElementById('new-url').value;

        if (!channel || !show || !url) return alert("Please fill all fields");

        btnSubmitShow.disabled = true;
        const originalText = btnSubmitShow.textContent;
        btnSubmitShow.textContent = "Resolving Feed...";

        try {
            if (url.includes('youtube.com') || url.includes('youtu.be') || url.includes('@')) {
                const res = await fetch('/api/resolve_youtube', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (data.status === 'success' && data.resolved_url) {
                    url = data.resolved_url;
                }
            }

            if (editingIndex >= 0) {
                globalConfig.shows[editingIndex] = { channel_name: channel, show_name: show, rss_url: url };
            } else {
                globalConfig.shows.push({ channel_name: channel, show_name: show, rss_url: url });
            }

            modal.classList.remove('active');
            await saveConfig();
        } catch (e) {
            alert("Error: " + e.message);
        } finally {
            btnSubmitShow.disabled = false;
            btnSubmitShow.textContent = originalText;
        }
    });

    // YouTube Event Listeners
    if (btnOpenYoutubeModal) {
        btnOpenYoutubeModal.addEventListener('click', () => {
            window.ytEditingIndex = -1;
            const titleEl = document.getElementById('youtube-modal-title');
            if (titleEl) titleEl.innerText = "Add YouTube Channel";
            youtubeChannelName.value = '';
            youtubeRssUrl.value = '';
            youtubeModal.classList.add('active');
        });
    }
    if (btnCloseYoutubeModal) {
        btnCloseYoutubeModal.addEventListener('click', () => {
            youtubeModal.classList.remove('active');
        });
    }
    if (btnSaveYoutube) {
        btnSaveYoutube.addEventListener('click', saveYoutubeChannel);
    }
    if (btnSyncAllYoutube) {
        btnSyncAllYoutube.addEventListener('click', async () => {
            await syncYoutubeChannel(null); // Sync All
        });
    }
    if (btnScheduleYoutube) {
        btnScheduleYoutube.addEventListener('click', () => {
            openScheduleModal('youtube', { channel_index: null }, 'YouTube · All Channels');
        });
    }

    // Telegram Event Listeners
    if (btnOpenTelegramModal) {
        btnOpenTelegramModal.addEventListener('click', () => {
            window.tgEditingIndex = -1;
            const titleEl = document.getElementById('telegram-modal-title');
            if (titleEl) titleEl.innerText = "Add Telegram Channel";
            telegramChannelName.value = '';
            telegramChannelId.value = '';
            telegramKeywords.value = '';
            telegramModal.classList.add('active');
        });
    }
    if (btnCloseTelegramModal) {
        btnCloseTelegramModal.addEventListener('click', () => {
            telegramModal.classList.remove('active');
        });
    }
    if (btnSaveTelegram) {
        btnSaveTelegram.addEventListener('click', saveTelegramChannel);
    }
    if (btnSyncAllTelegram) {
        btnSyncAllTelegram.addEventListener('click', async () => {
            await syncTelegramChannel(null); // Sync All
        });
    }
    if (btnScheduleTelegram) {
        btnScheduleTelegram.addEventListener('click', () => {
            openScheduleModal('telegram', {}, 'Telegram Harvester');
        });
    }

    if (btnSyncAllMd) {
        btnSyncAllMd.addEventListener('click', async () => {
            await syncMarketData(null); // Sync All
        });
    }
    if (btnScheduleMd) {
        btnScheduleMd.addEventListener('click', () => {
            openScheduleModal('market_data', {}, 'Market Data Harvester');
        });
    }

    // Close overlays on click outside
    window.addEventListener('click', (e) => {
        if (e.target === youtubeModal) youtubeModal.classList.remove('active');
        if (e.target === telegramModal) telegramModal.classList.remove('active');
    });

    // Sync Action
    btnSync.addEventListener('click', async () => {
        await triggerSync(null); // Sync All
    });

    if (btnSyncDocs) {
        btnSyncDocs.addEventListener('click', async () => {
            let queuedAny = false;
            pendingDocs.forEach(doc => {
                if (docProcessState[doc] === 'Ready') {
                    docProcessState[doc] = 'Queued';
                    queuedAny = true;
                }
            });
            if (queuedAny) {
                renderLibraryPendingDocs();
                renderQueueList();
                processNextDoc(true);
            }
        });
    }

    // Pause/Stop Controls
    btnPauseSync.addEventListener('click', () => {
        isPaused = !isPaused;
        saveSyncState(); // Persist pause toggle
        if (isPaused) {
            btnPauseSync.innerHTML = `<i data-lucide="play" style="width: 14px; height: 14px;"></i> Resume`;
            btnPauseSync.classList.add('btn-active');
            appendLog("Sync queue paused. Current process will finish, then queue will wait.", "warning");
            showToast("Sync queue paused.", "info");
        } else {
            btnPauseSync.innerHTML = `<i data-lucide="pause" style="width: 14px; height: 14px;"></i> Pause`;
            btnPauseSync.classList.remove('btn-active');
            appendLog("Sync queue resumed.", "info");
            showToast("Sync queue resumed.", "success");
            
            // If nothing is running but there's a queue, kick it off
            if (!isSyncRunning && syncQueue.length > 0) {
                const next = syncQueue.shift();
                triggerSync(next.showIndex, next.episodeIndex, next.silent);
            }
        }
        lucide.createIcons();
    });

    btnStopSync.addEventListener('click', async () => {
        if (!isSyncRunning) return;
        
        if (confirm("Stop the current sync process immediately?")) {
            appendLog("Stopping sync process...", "warning");
            try {
                await fetch('/api/cancel_sync', { method: 'POST' });
                if (currentSyncController) {
                    currentSyncController.abort();
                }
                showToast("Stop signal sent.", "warning");
            } catch (e) {
                console.error("Stop error:", e);
            }
        }
    });

    btnTerminateQueue.addEventListener('click', () => {
        syncQueue.length = 0;
        activeSyncKeys.clear();
        saveSyncState(); // Persist cleared queue
        renderQueueList();
        stopConfirmModal.classList.remove('active');
        showToast("Remaining queue terminated.", "warning");
        appendLog("Sync queue cleared by user.", "warning");
        isPaused = false; // Reset pause if terminated
        btnPauseSync.innerHTML = `<i data-lucide="pause" style="width: 14px; height: 14px;"></i> Pause`;
        btnPauseSync.classList.remove('btn-active');
        lucide.createIcons();
    });

    btnContinueQueue.addEventListener('click', () => {
        stopConfirmModal.classList.remove('active');
        isPaused = false;
        saveSyncState();
        btnPauseSync.innerHTML = `<i data-lucide="pause" style="width: 14px; height: 14px;"></i> Pause`;
        btnPauseSync.classList.remove('btn-active');
        lucide.createIcons();
        
        if (syncQueue.length > 0) {
            const next = syncQueue.shift();
            triggerSync(next.showIndex, next.episodeIndex, next.silent);
        }
    });

    if (btnCancelStop) {
        btnCancelStop.addEventListener('click', () => {
            stopConfirmModal.classList.remove('active');
            isPaused = true;
            btnPauseSync.innerHTML = `<i data-lucide="play" style="width: 14px; height: 14px;"></i> Resume`;
            btnPauseSync.classList.add('btn-active');
            lucide.createIcons();
        });
    }

    // Web Harvest Actions
    if (btnWebSetup) {
        btnWebSetup.addEventListener('click', async () => {
            showToast("Opening browser for login. Please log in and close the window when done.", "info");
            btnWebSetup.disabled = true;
            btnWebSetup.innerText = "Browser Open...";
            
            try {
                const res = await fetch('/api/harvest/setup', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast("Login session captured successfully!", "success");
                }
            } catch (e) {
                showToast("Setup failed: " + e.message, "error");
            } finally {
                btnWebSetup.disabled = false;
                btnWebSetup.innerHTML = `<i data-lucide="log-in"></i> Setup Login`;
                await loadWebHarvestStatus();
                lucide.createIcons();
            }
        });
    }

    if (btnWebReset) {
        btnWebReset.addEventListener('click', async () => {
            if (!confirm("Reset the logged-in session? This clears saved cookies and the browser profile. You'll need to run 'Setup Login' again.")) {
                return;
            }
            btnWebReset.disabled = true;
            btnWebReset.innerHTML = `<i data-lucide="loader-2" class="spinning"></i> Resetting...`;
            lucide.createIcons();
            try {
                const res = await fetch('/api/harvest/reset', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    const n = (data.removed && data.removed.length) ? data.removed.join(', ') : 'nothing to clear';
                    showToast("Session reset (" + n + "). Run 'Setup Login' to log in again.", "success");
                } else {
                    showToast("Reset failed: " + (data.message || "unknown error"), "error");
                }
            } catch (e) {
                showToast("Reset failed: " + e.message, "error");
            } finally {
                btnWebReset.disabled = false;
                btnWebReset.innerHTML = `<i data-lucide="log-out"></i> Reset Session`;
                await loadWebHarvestStatus();
                lucide.createIcons();
            }
        });
    }

    if (btnRunWebHarvest) {
        btnRunWebHarvest.addEventListener('click', async () => {
            await triggerWebHarvest();
        });
    }

    if (btnWebImportCookies) {
        btnWebImportCookies.addEventListener('click', async () => {
            const cookies = webCookieString.value.trim();
            if (!cookies) {
                showToast("Please paste your cookie string first", "error");
                return;
            }
            
            btnWebImportCookies.disabled = true;
            btnWebImportCookies.innerText = "Importing...";
            
            try {
                const res = await fetch('/api/harvest/cookies', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cookies })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast("Cookies imported successfully!", "success");
                    webCookieString.value = '';
                    await loadWebHarvestStatus();
                } else {
                    showToast("Import failed: " + data.message, "error");
                }
            } catch (e) {
                showToast("Import error: " + e.message, "error");
            } finally {
                btnWebImportCookies.disabled = false;
                btnWebImportCookies.innerHTML = `<i data-lucide="upload"></i> Import Cookies`;
                lucide.createIcons();
            }
        });
    }

    // Reload available editions when the harvest date changes
    const webHarvestDate = document.getElementById('web-harvest-date');
    if (webHarvestDate) {
        webHarvestDate.addEventListener('change', loadHarvestEditions);
    }

    // Arxiv Research Harvest Actions
    if (btnArxivSearch) {
        btnArxivSearch.addEventListener('click', async () => {
            const query = arxivSearchQuery.value.trim();
            const sortBy = document.getElementById('arxiv-sort-order')?.value || 'relevance';
            const sources = Array.from(document.querySelectorAll('.arxiv-source:checked')).map(el => el.value);
            const yearFrom = document.getElementById('arxiv-year-from')?.value.trim();
            const yearTo = document.getElementById('arxiv-year-to')?.value.trim();

            if (!query) {
                showToast("Please enter a search query", "warning");
                return;
            }
            if (sources.length === 0) {
                showToast("Select at least one source", "warning");
                return;
            }

            btnArxivSearch.disabled = true;
            btnArxivSearch.innerHTML = `<i data-lucide="loader-2" class="spinning"></i> Searching...`;
            lucide.createIcons();

            try {
                const params = new URLSearchParams({ query, sort_by: sortBy, sources: sources.join(',') });
                if (yearFrom) params.set('year_from', yearFrom);
                if (yearTo) params.set('year_to', yearTo);

                const res = await fetch(`/api/arxiv/search?${params.toString()}`);
                const data = await res.json();

                if (data.status === 'success') {
                    renderArxivResults(data.results);
                    if (data.errors && data.errors.length) {
                        data.errors.forEach(err =>
                            showToast(`${err.source} unavailable: ${err.message}`, "warning"));
                    }
                } else {
                    showToast("Search failed: " + data.message, "error");
                    arxivResultsContainer.innerHTML = `<div style="padding: 20px; color: var(--danger);">${data.message}</div>`;
                }
            } catch (e) {
                showToast("Search error: " + e.message, "error");
                arxivResultsContainer.innerHTML = `<div style="padding: 20px; color: var(--danger);">Connection Error: ${e.message}</div>`;
            } finally {
                btnArxivSearch.disabled = false;
                btnArxivSearch.innerHTML = `<i data-lucide="sparkles"></i> Search`;
                lucide.createIcons();
            }
        });
        
        if (arxivSearchQuery) {
            arxivSearchQuery.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    btnArxivSearch.click();
                }
            });
        }
    }

    // File Drop Zone
    const dropZone = document.getElementById('file-drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');

    if (dropZone && fileInput) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.style.borderColor = 'var(--primary)';
                dropZone.style.background = 'rgba(255, 255, 255, 0.05)';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
                dropZone.style.background = 'transparent';
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        }, false);

        fileInput.addEventListener('change', function() {
            handleFiles(this.files);
        });

        async function handleFiles(files) {
            if (files.length === 0) return;
            
            uploadStatus.style.display = 'block';
            uploadStatus.style.color = '#a1a1aa';
            uploadStatus.innerText = `Uploading ${files.length} file(s)...`;

            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }

            try {
                const res = await fetch('/api/upload_docs', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await res.json();
                if (data.status === 'success') {
                    uploadStatus.style.color = 'var(--primary)';
                    uploadStatus.innerText = `Uploaded. Now processing ${files.length} document(s) independently...`;
                    showToast(`Uploaded ${files.length} document(s). Starting independent processing...`, 'info');
                    
                    // Trigger sync ONLY for these specific files
                    await triggerDocSync(data.files);
                    
                    uploadStatus.style.color = 'var(--success)';
                    uploadStatus.innerText = `Successfully processed ${files.length} file(s).`;
                } else {
                    uploadStatus.style.color = 'var(--danger)';
                    uploadStatus.innerText = `Upload failed: ${data.message}`;
                    showToast(`Upload failed`, 'error');
                }
            } catch (e) {
                uploadStatus.style.color = 'var(--danger)';
                uploadStatus.innerText = `Connection error: ${e.message}`;
            }
            
            setTimeout(() => {
                uploadStatus.style.display = 'none';
            }, 5000);
            
            fileInput.value = '';
        }
    }
}

async function triggerSync(showIndex = null, episodeIndex = null, silent = false) {
    const syncKey = getSyncKey(showIndex, episodeIndex);
    
    // Generate label early so it's available for queueing
    let label = showIndex !== null ? `'${globalConfig.shows[showIndex].show_name}'` : "All Shows";
    if (episodeIndex !== null) label += ` (Episode ID: ${episodeIndex})`;

    // 1. Handle Queueing
    if (isSyncRunning) {
        if (activeSyncKeys.has(syncKey)) {
            showToast("This item is already being processed.", "warning");
            return;
        }
        
        syncQueue.push({ showIndex, episodeIndex, silent, label });
        activeSyncKeys.add(syncKey);
        
        saveSyncState();
        renderQueueList();
        
        if (episodeIndex !== null) {
            updateEpisodeButton(showIndex, episodeIndex, 'queued');
            showToast("Episode added to sync queue.", "info");
        } else {
            showToast("Sync task added to queue.", "info");
        }
        return;
    }

    // 2. Start Sync
    isSyncRunning = true;
    activeSyncKeys.add(syncKey);

    if (!silent) {
        document.querySelector('[data-tab="dashboard"]').click();
    } else if (episodeIndex !== null) {
        updateEpisodeButton(showIndex, episodeIndex, 'syncing');
        showToast("Starting synchronization...", "info");
    }
    
    btnSync.disabled = true;
    btnSync.classList.add('spinning');
    btnSync.innerHTML = `<i data-lucide="loader-2"></i> Syncing...`;
    lucide.createIcons();

    activeItem = { showIndex, episodeIndex, silent, label };
    saveSyncState();
    renderQueueList();
    
    appendLog(`Initiating manual synchronization sequence for: ${label}...`);

    try {
        currentSyncController = new AbortController();
        progressContainer.style.display = 'block';
        progressLabel.innerText = 'Initializing...';
        progressPercent.innerText = '0%';
        progressBar.style.width = '0%';
        progressBar.style.background = 'var(--primary)';
        progressBar.style.animation = 'none';

        const bodyData = {};
        if (showIndex !== null) bodyData.show_index = showIndex;
        if (episodeIndex !== null) bodyData.episode_index = episodeIndex;
        
        const res = await fetch('/api/sync', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyData),
            signal: currentSyncController.signal
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    
                    if (data.message) {
                        appendLog("> " + data.message, data.type || "info");
                    }
                    
                    if (data.progress !== undefined && data.progress !== null) {
                        if (data.progress === "indeterminate") {
                             progressBar.style.background = 'linear-gradient(90deg, var(--primary) 0%, #a855f7 100%)';
                             progressBar.style.width = '100%';
                             progressPercent.innerText = '';
                             progressLabel.innerText = 'Transcribing Media...';
                        } else {
                             const pct = typeof data.progress === 'number' ? Math.round(data.progress) : 0;
                             progressBar.style.background = 'var(--primary)';
                             progressBar.style.animation = 'none';
                             progressBar.style.width = pct + '%';
                             progressPercent.innerText = pct + '%';
                             
                             if (pct === 100) {
                                 progressBar.style.background = 'var(--success)';
                                 progressLabel.innerText = 'Sync Complete!';
                             } else {
                                 progressLabel.innerText = 'Synchronizing Podcasts...';
                             }
                        }
                    }

                    if (data.gemini_stats) {
                        if (geminiStatsContainer) {
                            geminiStatsContainer.style.display = 'flex';
                            geminiRpm.innerText = data.gemini_stats.rpm;
                            geminiTotal.innerText = data.gemini_stats.total_today;
                        }
                    }
                } catch (e) {
                    console.error("Stream parse error:", line, e);
                }
            }
        }
        
        appendLog(`Sync process finished for ${label}.`, "success");
        if (silent) showToast(`Sync complete: ${label}`, "success");
        if (episodeIndex !== null) updateEpisodeButton(showIndex, episodeIndex, 'synced');

    } catch (e) {
        if (e.name === 'AbortError') {
            appendLog("Current sync process terminated by user.", "warning");
            if (syncQueue.length > 0) {
                queueCountInfo.innerText = `${syncQueue.length} items remaining in queue.`;
                stopConfirmModal.classList.add('active');
            }
        } else {
            appendLog("Connection Error: " + e.message, "error");
            if (silent) showToast(`Sync Error: ${e.message}`, "error");
            if (episodeIndex !== null) updateEpisodeButton(showIndex, episodeIndex, 'ready');
        }
    } finally {
        isSyncRunning = false;
        currentSyncController = null;
        activeSyncKeys.delete(syncKey);
        activeItem = null;
        
        saveSyncState();
        renderQueueList();
        
        btnSync.disabled = false;
        btnSync.classList.remove('spinning');
        btnSync.innerHTML = `<i data-lucide="refresh-cw"></i> Sync Now`;
        lucide.createIcons();
        await loadDashboardStats();

        // 3. Process Next in Queue
        if (syncQueue.length > 0) {
            if (isPaused) {
                appendLog(`Queue processing strictly paused. ${syncQueue.length} items waiting.`, "warning");
                return;
            }
            
            const next = syncQueue.shift();
            activeSyncKeys.delete(getSyncKey(next.showIndex, next.episodeIndex)); // Temporarily remove so triggerSync can re-add it correctly
            saveSyncState();
            renderQueueList();
            triggerSync(next.showIndex, next.episodeIndex, next.silent);
        } else {
            // If we were stopping, this might have been called via a stop signal
            // But we handled that in catch/finally.
        }
    }
}

async function triggerDocSync(target_files = null, switchTab = true) {
    // Switch to dashboard tab to show logs
    if (switchTab) {
        document.querySelector('[data-tab="dashboard"]').click();
    }
    
    if (btnSyncDocs) {
        btnSyncDocs.disabled = true;
        btnSyncDocs.innerHTML = `<i data-lucide="loader-2"></i> Harvesting...`;
    }
    lucide.createIcons();

    isDocSyncRunning = true;
    activeDocName = "";
    renderQueueList();

    const modeText = target_files ? `specific documents (${target_files.join(', ')})` : `all documents in: ${globalConfig.raw_material_path}`;
    appendLog(`Initiating document harvest for ${modeText}...`);

    try {
        progressContainer.style.display = 'block';
        progressLabel.innerText = 'Initializing...';
        progressPercent.innerText = '0%';
        progressBar.style.width = '0%';
        progressBar.style.background = 'var(--primary)';
        progressBar.style.animation = 'none';

        const bodyData = target_files ? JSON.stringify({ target_files }) : "{}";

        const res = await fetch('/api/sync_docs', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: bodyData
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    
                    if (data.message) {
                        appendLog("> " + data.message, data.type || "info");
                    }

                    if (data.current_file) {
                        activeDocName = data.current_file;
                        renderQueueList();
                    }
                    
                    if (data.progress !== undefined && data.progress !== null) {
                        const pct = typeof data.progress === 'number' ? Math.round(data.progress) : 0;
                        progressBar.style.background = 'var(--primary)';
                        progressBar.style.width = pct + '%';
                        progressPercent.innerText = pct + '%';
                        
                        if (pct === 100) {
                            progressBar.style.background = 'var(--success)';
                            progressLabel.innerText = 'Harvest Complete!';
                        } else {
                            progressLabel.innerText = 'Converting Documents...';
                        }
                    }

                    if (data.gemini_stats) {
                        if (geminiStatsContainer) {
                            geminiStatsContainer.style.display = 'flex';
                            geminiRpm.innerText = data.gemini_stats.rpm;
                            geminiTotal.innerText = data.gemini_stats.total_today;
                        }
                    }
                } catch (e) {
                    console.error("Stream parse error:", line, e);
                }
            }
        }
        
        appendLog(`Document harvest finished.`, "success");
    } catch (e) {
        appendLog("Connection Error: " + e.message, "error");
    } finally {
        isDocSyncRunning = false;
        activeDocName = "";
        if (btnSyncDocs) {
            btnSyncDocs.disabled = false;
            btnSyncDocs.innerHTML = `<i data-lucide="wand-2"></i> Harvest Documents`;
        }
        lucide.createIcons();
        await loadDashboardStats();
        await loadLibraryStats();
    }
}

async function loadHarvestEditions() {
    const sel = document.getElementById('web-harvest-edition');
    const dateInput = document.getElementById('web-harvest-date');
    const hint = document.getElementById('web-edition-hint');
    if (!sel) return;
    // Default the date picker to today
    if (dateInput && !dateInput.value) {
        dateInput.value = new Date().toISOString().slice(0, 10);
    }
    const date = dateInput ? dateInput.value : '';
    if (hint) hint.innerText = 'Loading editions...';
    try {
        const res = await fetch('/api/harvest/editions' + (date ? `?date=${date}` : ''));
        const data = await res.json();
        if (data.status === 'success' && data.editions && data.editions.length) {
            const prev = sel.value;
            sel.innerHTML = '';
            data.editions.forEach(ed => {
                const opt = document.createElement('option');
                opt.value = ed.id;
                opt.textContent = ed.title.replace('EPaper-', '');
                sel.appendChild(opt);
            });
            // preserve prior selection if still available
            if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
            if (hint) hint.innerText = `${data.editions.length} editions available for ${date || 'today'}.`;
        } else {
            if (hint) hint.innerText = 'No editions found (session may be inactive). Using Mumbai.';
        }
    } catch (e) {
        if (hint) hint.innerText = 'Could not load editions. Using default.';
        console.error('loadHarvestEditions failed:', e);
    }
}

async function triggerWebHarvest() {
    const url = webHarvestUrl ? webHarvestUrl.value : 'https://epaper.thehindu.com/reader';
    const publication = document.getElementById('web-harvest-edition')?.value || 'th_mumbai';
    const date = document.getElementById('web-harvest-date')?.value || '';

    // Switch to dashboard tab to show logs
    document.querySelector('[data-tab="dashboard"]').click();
    
    if (btnRunWebHarvest) {
        btnRunWebHarvest.disabled = true;
        btnRunWebHarvest.innerHTML = `<i data-lucide="loader-2" class="spinning"></i> Harvesting...`;
    }
    lucide.createIcons();

    appendLog(`Initiating web harvest for: ${publication}${date ? ' @ ' + date : ''}...`);

    try {
        progressContainer.style.display = 'block';
        progressLabel.innerText = 'Initializing...';
        progressPercent.innerText = '0%';
        progressBar.style.width = '0%';
        progressBar.style.background = 'var(--primary)';

        const res = await fetch('/api/harvest/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, publication, date })
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    
                    if (data.message) {
                        appendLog("> " + data.message, data.type || "info");
                    }
                    
                    if (data.progress !== undefined && data.progress !== null) {
                        const pct = typeof data.progress === 'number' ? Math.round(data.progress) : 0;
                        progressBar.style.width = pct + '%';
                        progressPercent.innerText = pct + '%';
                        
                        if (pct === 100) {
                            progressBar.style.background = 'var(--success)';
                            progressLabel.innerText = 'Harvest Complete!';
                        } else {
                            progressLabel.innerText = 'Harvesting Web Content...';
                        }
                    }

                    if (data.gemini_stats) {
                        if (geminiStatsContainer) {
                            geminiStatsContainer.style.display = 'flex';
                            geminiRpm.innerText = data.gemini_stats.rpm;
                            geminiTotal.innerText = data.gemini_stats.total_today;
                        }
                    }
                } catch (e) {
                    console.error("Stream parse error:", line, e);
                }
            }
        }
        
        appendLog(`Web harvest finished.`, "success");
    } catch (e) {
        appendLog("Harvest Error: " + e.message, "error");
    } finally {
        if (btnRunWebHarvest) {
            btnRunWebHarvest.disabled = false;
            btnRunWebHarvest.innerHTML = `<i data-lucide="zap"></i> Start Ingestion`;
        }
        lucide.createIcons();
        await loadDashboardStats();
        await loadWebHarvestStatus();
    }
}

const SOURCE_LABELS = {
    arxiv: 'arXiv',
    openalex: 'OpenAlex',
    crossref: 'CrossRef',
    semantic_scholar: 'Semantic Scholar'
};

function escapeHtml(str) {
    return String(str == null ? '' : str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Store the latest results so the Harvest button can pass along a paper's
// pdf_url / doi / title (needed to fetch non-arXiv open-access PDFs).
let researchResults = [];

function renderArxivResults(results) {
    if (!arxivResultsContainer) return;

    researchResults = results || [];

    if (!results || results.length === 0) {
        arxivResultsContainer.innerHTML = `<div style="padding: 20px; color: #a1a1aa;">No results found.</div>`;
        return;
    }

    arxivResultsContainer.innerHTML = '';

    results.forEach((paper, i) => {
        const row = document.createElement('div');
        row.className = 'glass-card mb-2';
        row.style.padding = '20px';

        const authors = (paper.authors && paper.authors.length)
            ? escapeHtml(paper.authors.slice(0, 8).join(', ')) : 'Unknown Authors';
        const summary = paper.summary
            ? escapeHtml(paper.summary.substring(0, 300)) + '…' : 'No summary available.';
        const dateStr = paper.published || (paper.year ? String(paper.year) : 'n/a');
        const badge = `<span class="src-badge ${paper.source}">${SOURCE_LABELS[paper.source] || paper.source}</span>`;
        const venue = paper.venue ? ` • ${escapeHtml(paper.venue)}` : '';
        const cites = (paper.citation_count != null)
            ? ` • <i data-lucide="quote" style="width:13px;height:13px;vertical-align:middle;"></i> ${paper.citation_count} cited` : '';
        const tags = (paper.categories && paper.categories.length)
            ? `<div style="font-size: 0.8rem; color: var(--primary);">
                    <i data-lucide="tag" style="width: 12px; height: 12px; vertical-align: middle;"></i> ${escapeHtml(paper.categories.join(', '))}
               </div>` : '';
        const pdfBtn = paper.pdf_url
            ? `<a href="${escapeHtml(paper.pdf_url)}" target="_blank" class="btn-secondary" style="justify-content: center; text-align: center; text-decoration: none;">
                    <i data-lucide="external-link"></i> View PDF
               </a>`
            : `<span style="font-size:0.75rem; color:#71717a; text-align:center;">No open-access PDF</span>`;

        row.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 15px;">
                <div style="flex: 1;">
                    <div style="margin-bottom: 6px;">${badge}</div>
                    <h3 style="margin-bottom: 5px; font-size: 1.1rem;">${escapeHtml(paper.title)}</h3>
                    <div style="font-size: 0.85rem; color: #a1a1aa; margin-bottom: 10px;">
                        <i data-lucide="users" style="width: 14px; height: 14px; vertical-align: middle;"></i> ${authors} •
                        <i data-lucide="calendar" style="width: 14px; height: 14px; vertical-align: middle;"></i> ${escapeHtml(dateStr)}${venue}${cites}
                    </div>
                    <p style="font-size: 0.9rem; color: #d4d4d8; line-height: 1.5; margin-bottom: 15px;">${summary}</p>
                    ${tags}
                </div>
                <div style="display: flex; flex-direction: column; gap: 10px; min-width: 120px;">
                    <button class="btn-primary" onclick="triggerArxivHarvest(${i})" style="justify-content: center; width: 100%;">
                        <i data-lucide="download-cloud"></i> Harvest
                    </button>
                    ${pdfBtn}
                </div>
            </div>
        `;
        arxivResultsContainer.appendChild(row);
    });

    lucide.createIcons();
}

async function triggerArxivHarvest(index) {
    const paper = researchResults[index];
    if (!paper) return;
    const paperId = paper.id;
    document.querySelector('[data-tab="dashboard"]').click();
    appendLog(`Initiating research harvest for: ${paper.title} [${SOURCE_LABELS[paper.source] || paper.source}]...`);

    try {
        progressContainer.style.display = 'block';
        progressLabel.innerText = 'Initializing...';
        progressPercent.innerText = '0%';
        progressBar.style.width = '0%';
        progressBar.style.background = 'var(--primary)';

        const res = await fetch('/api/arxiv/harvest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                paper_id: paperId,
                pdf_url: paper.pdf_url,
                doi: paper.doi,
                title: paper.title
            })
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    
                    if (data.message) {
                        appendLog("> " + data.message, data.type || "info");
                    }
                    
                    if (data.progress !== undefined && data.progress !== null) {
                        const pct = typeof data.progress === 'number' ? Math.round(data.progress) : 0;
                        progressBar.style.width = pct + '%';
                        progressPercent.innerText = pct + '%';
                        
                        if (pct === 100) {
                            progressBar.style.background = 'var(--success)';
                            progressLabel.innerText = 'Harvest Complete!';
                        } else {
                            progressLabel.innerText = 'Harvesting Research Content...';
                        }
                    }

                    if (data.gemini_stats) {
                        if (geminiStatsContainer) {
                            geminiStatsContainer.style.display = 'flex';
                            geminiRpm.innerText = data.gemini_stats.rpm;
                            geminiTotal.innerText = data.gemini_stats.total_today;
                        }
                    }
                } catch (e) {
                    console.error("Stream parse error:", line, e);
                }
            }
        }
        
        appendLog(`arXiv harvest finished.`, "success");
    } catch (e) {
        appendLog("Harvest Error: " + e.message, "error");
    } finally {
        await loadDashboardStats();
        await loadLibraryStats();
    }
}

async function browseEpisodes(showIndex) {
    const show = globalConfig.shows[showIndex];
    episodeBrowserTitle.innerText = `Browse: ${show.show_name}`;
    episodeModal.classList.add('active');
    episodeLoading.style.display = 'block';
    episodeList.innerHTML = '';
    episodeSearch.value = ''; // Reset search

    try {
        const res = await fetch(`/api/episodes?show_index=${showIndex}`);
        const data = await res.json();
        
        episodeLoading.style.display = 'none';
        
        if (data.status === 'success') {
            displayEpisodeList(showIndex, data.episodes);
        } else {
            episodeList.innerHTML = `<div style="padding: 20px; color: var(--danger);">Error: ${data.message}</div>`;
        }
    } catch (e) {
        episodeLoading.style.display = 'none';
        episodeList.innerHTML = `<div style="padding: 20px; color: var(--danger);">Connection Error: ${e.message}</div>`;
    }
}

function displayEpisodeList(showIndex, episodes) {
    if (episodes.length === 0) {
        episodeList.innerHTML = `<div style="padding: 20px; color: #a1a1aa;">No episodes found in this feed.</div>`;
        return;
    }

    // Performance optimization: only render first 50 episodes initially for DOM speed
    // Older episodes can be found via Search
    episodes.forEach((ep, idx) => {
        const row = document.createElement('div');
        row.className = 'glass-card mb-1 episode-row';
        row.dataset.title = ep.title; // For filtering
        row.style.display = idx < 50 ? 'flex' : 'none'; // Initial limit
        row.style.justifyContent = 'space-between';
        row.style.alignItems = 'center';
        row.style.padding = '12px 15px';
        row.style.border = '1px solid rgba(255,255,255,0.05)';
        row.style.background = 'rgba(255,255,255,0.02)';

        const info = document.createElement('div');
        info.style.flex = '1';
        info.innerHTML = `
            <div style="font-weight: 500; font-size: 0.95rem; margin-bottom: 2px;">${ep.title}</div>
            <div style="font-size: 0.8rem; color: #71717a;">${ep.date}</div>
        `;

        const action = document.createElement('div');
        
        // Conditional Button logic for Sync vs Resync
        const syncBtnId = `btn-sync-${showIndex}-${ep.index}`;
        const isCurrentlyActive = activeSyncKeys.has(getSyncKey(showIndex, ep.index));
        const isInQueue = syncQueue.find(q => q.showIndex === showIndex && q.episodeIndex === ep.index);

        if (isCurrentlyActive) {
            action.innerHTML = `
                <button id="${syncBtnId}" class="btn-primary btn-syncing" disabled style="padding: 6px 12px; font-size: 0.8rem;">
                    <i data-lucide="loader-2"></i> Syncing...
                </button>
            `;
        } else if (isInQueue) {
            action.innerHTML = `
                <button id="${syncBtnId}" class="btn-primary btn-queued" disabled style="padding: 6px 12px; font-size: 0.8rem;">
                    <i data-lucide="clock"></i> Queued
                </button>
            `;
        } else if (ep.is_synced) {
            action.innerHTML = `
                <button id="${syncBtnId}" class="btn-primary" onclick="syncSpecificEpisode(${showIndex}, ${ep.index})" style="padding: 6px 12px; font-size: 0.8rem; background: #475569; border: 1px solid var(--border);">
                    <i data-lucide="rotate-cw"></i> Resync
                </button>
            `;
        } else {
            action.innerHTML = `
                <button id="${syncBtnId}" class="btn-primary" onclick="syncSpecificEpisode(${showIndex}, ${ep.index})" style="padding: 6px 12px; font-size: 0.8rem;">
                    <i data-lucide="download"></i> Sync
                </button>
            `;
        }

        row.appendChild(info);
        row.appendChild(action);
        episodeList.appendChild(row);
    });
    
    lucide.createIcons({
        root: episodeList // Only scan the modal list for icons, much faster!
    });
}

function syncSpecificEpisode(showIndex, episodeIndex) {
    // No longer closing the modal!
    triggerSync(showIndex, episodeIndex, true);
}

function appendLog(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `log-entry ${type}`;
    
    // Aesthetic timestamp styling
    if (message.startsWith('[') && message.includes(']')) {
        const splitIdx = message.indexOf(']');
        const ts = message.substring(0, splitIdx + 1);
        const rest = message.substring(splitIdx + 1);
        
        const tsSpan = document.createElement('span');
        tsSpan.style.opacity = '0.5';
        tsSpan.style.marginRight = '8px';
        tsSpan.style.fontWeight = '400';
        tsSpan.innerText = ts;
        
        el.appendChild(tsSpan);
        el.appendChild(document.createTextNode(rest));
    } else {
        el.innerText = message;
    }

    syncLogs.appendChild(el);
    syncLogs.scrollTop = syncLogs.scrollHeight;
}

// Expose edit and delete globally
window.editShow = function(index) {
    editingIndex = index;
    const show = globalConfig.shows[index];
    document.getElementById('modal-title').innerText = "Edit Podcast Feed";
    document.getElementById('new-channel').value = show.channel_name;
    document.getElementById('new-show').value = show.show_name;
    document.getElementById('new-url').value = show.rss_url;
    modal.classList.add('active');
}

window.deleteShow = async function(index) {
    if(confirm("Are you sure you want to remove this show?")) {
        globalConfig.shows.splice(index, 1);
        await saveConfig();
    }
}

window.syncSpecificShow = async function(index) {
    await triggerSync(index);
}

// ─────────────────────────────────────────────────────────────────────────────
// SCHEDULED HARVESTING SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

// Schedule modal state
let _scheduleContext = null; // { engine, payload, label }
let selectedScheduleType = 'once';

const scheduleModal = document.getElementById('schedule-modal');
const scheduleDateInput = document.getElementById('schedule-date');
const scheduleTimeInput = document.getElementById('schedule-time');
const scheduleModalLabel = document.getElementById('schedule-modal-label');
const scheduleUtcPreview = document.getElementById('schedule-utc-preview');
const btnConfirmSchedule = document.getElementById('btn-confirm-schedule');
const btnCloseScheduleModal = document.getElementById('btn-close-schedule-modal');

// New scheduling references
const scheduleOnceGroup = document.getElementById('schedule-once-group');
const scheduleTimeGroup = document.getElementById('schedule-time-group');
const scheduleIntervalGroup = document.getElementById('schedule-interval-group');
const scheduleIntervalValue = document.getElementById('schedule-interval-value');
const scheduleIntervalUnit = document.getElementById('schedule-interval-unit');

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Returns local date string YYYY-MM-DD offset by `dayOffset` days.
 */
function localDateString(dayOffset = 0) {
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    return d.toISOString().split('T')[0];
}

/**
 * Given date "YYYY-MM-DD" and time "HH:MM" in local timezone,
 * returns UTC ISO-8601 string.
 */
function localToUtcIso(dateStr, timeStr) {
    if (!dateStr || !timeStr) throw new Error("Please select both a date and a time.");
    const dateParts = dateStr.split(/[-/]/).map(Number);
    const timeParts = timeStr.split(':').map(Number);
    if (dateParts.length < 3 || timeParts.length < 2 || dateParts.some(isNaN) || timeParts.some(isNaN)) {
        throw new Error("Invalid date or time format.");
    }
    // Handles both YYYY-MM-DD and MM/DD/YYYY formats robustly
    let year = dateParts[0], month = dateParts[1], day = dateParts[2];
    if (year < 1000 && dateParts[2] > 1000) {
        year = dateParts[2]; month = dateParts[0]; day = dateParts[1];
    }
    const local = new Date(year, month - 1, day, timeParts[0], timeParts[1], 0);
    if (isNaN(local.getTime())) throw new Error("Invalid date or time value.");
    return local.toISOString();
}

function updateUtcPreview() {
    if (selectedScheduleType === 'interval') {
        const val = scheduleIntervalValue.value || 1;
        const unit = scheduleIntervalUnit.value;
        scheduleUtcPreview.textContent = `Recurring: Every ${val} ${unit}`;
        return;
    }

    const t = scheduleTimeInput.value;
    if (!t) {
        scheduleUtcPreview.textContent = 'UTC: —';
        return;
    }

    if (selectedScheduleType === 'daily') {
        const today = localDateString(0);
        try {
            const utc = localToUtcIso(today, t);
            const dateObj = new Date(utc);
            const utcHour = String(dateObj.getUTCHours()).padStart(2, '0');
            const utcMin = String(dateObj.getUTCMinutes()).padStart(2, '0');
            scheduleUtcPreview.textContent = `Recurring: Daily at ${utcHour}:${utcMin} UTC`;
        } catch (e) {
            scheduleUtcPreview.textContent = 'UTC: (invalid)';
        }
        return;
    }

    const d = scheduleDateInput.value;
    if (!d) {
        scheduleUtcPreview.textContent = 'UTC: —';
        return;
    }
    try {
        const utc = localToUtcIso(d, t);
        const fmt = new Date(utc).toLocaleString('en-US', {
            timeZone: 'UTC',
            dateStyle: 'medium',
            timeStyle: 'short'
        });
        scheduleUtcPreview.textContent = `UTC: ${fmt}`;
    } catch (e) {
        scheduleUtcPreview.textContent = 'UTC: (invalid)';
    }
}

// ── Open Schedule Modal ───────────────────────────────────────────────────

/**
 * Opens the shared schedule modal.
 * @param {string} engine    'podcast' | 'docs' | 'web'
 * @param {object} payload   Engine-specific payload
 * @param {string} label     Human-readable description
 */
function openScheduleModal(engine, payload, label) {
    _scheduleContext = { engine, payload, label };
    scheduleModalLabel.textContent = label;

    // Reset schedule frequency controls
    selectedScheduleType = 'once';
    toggleScheduleTypeFields();

    // Default to midnight tonight
    const today = localDateString(0);
    const tomorrow = localDateString(1);
    scheduleDateInput.value = tomorrow;
    scheduleTimeInput.value = '00:00';
    updateUtcPreview();

    scheduleModal.classList.add('active');
    lucide.createIcons({ root: scheduleModal });
}

function toggleScheduleTypeFields() {
    document.querySelectorAll('.schedule-type-btn').forEach(btn => {
        btn.classList.toggle('btn-active', btn.dataset.type === selectedScheduleType);
    });

    if (selectedScheduleType === 'once') {
        if (scheduleOnceGroup) scheduleOnceGroup.style.display = 'block';
        if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'block';
        if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'none';
        const labelEl = document.getElementById('schedule-time-label');
        if (labelEl) labelEl.innerHTML = `Time <span style="color:#71717a; font-weight:400;">(local time — auto-converted to UTC)</span>`;
    } else if (selectedScheduleType === 'daily') {
        if (scheduleOnceGroup) scheduleOnceGroup.style.display = 'none';
        if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'block';
        if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'none';
        const labelEl = document.getElementById('schedule-time-label');
        if (labelEl) labelEl.innerHTML = `Time <span style="color:#71717a; font-weight:400;">(local time everyday — auto-converted to UTC)</span>`;
    } else if (selectedScheduleType === 'interval') {
        if (scheduleOnceGroup) scheduleOnceGroup.style.display = 'none';
        if (scheduleTimeGroup) scheduleTimeGroup.style.display = 'none';
        if (scheduleIntervalGroup) scheduleIntervalGroup.style.display = 'block';
    }
    updateUtcPreview();
}

// Bind frequency selection buttons
document.querySelectorAll('.schedule-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        selectedScheduleType = btn.dataset.type;
        toggleScheduleTypeFields();
    });
});

// ── Preset Buttons ────────────────────────────────────────────────────────

document.querySelectorAll('.schedule-preset').forEach(btn => {
    btn.addEventListener('click', () => {
        const preset = btn.dataset.preset;
        const now = new Date();

        if (preset === 'midnight') {
            scheduleDateInput.value = localDateString(0);
            scheduleTimeInput.value = '23:59';
        } else if (preset === 'tomorrow') {
            scheduleDateInput.value = localDateString(1);
            scheduleTimeInput.value = '00:00';
        } else if (preset === '1h') {
            const t = new Date(now.getTime() + 60 * 60 * 1000);
            scheduleDateInput.value = t.toLocaleDateString('en-CA'); // YYYY-MM-DD
            scheduleTimeInput.value = t.toTimeString().slice(0, 5);
        } else if (preset === '6h') {
            const t = new Date(now.getTime() + 6 * 60 * 60 * 1000);
            scheduleDateInput.value = t.toLocaleDateString('en-CA');
            scheduleTimeInput.value = t.toTimeString().slice(0, 5);
        }
        updateUtcPreview();
    });
});

scheduleDateInput.addEventListener('input', updateUtcPreview);
scheduleTimeInput.addEventListener('input', updateUtcPreview);
if (scheduleIntervalValue) scheduleIntervalValue.addEventListener('input', updateUtcPreview);
if (scheduleIntervalUnit) scheduleIntervalUnit.addEventListener('change', updateUtcPreview);

// ── Close Modal ───────────────────────────────────────────────────────────

if (btnCloseScheduleModal) {
    btnCloseScheduleModal.addEventListener('click', () => {
        scheduleModal.classList.remove('active');
        _scheduleContext = null;
    });
}
window.addEventListener('click', e => {
    if (e.target === scheduleModal) {
        scheduleModal.classList.remove('active');
        _scheduleContext = null;
    }
});

// ── Confirm Schedule ──────────────────────────────────────────────────────

if (btnConfirmSchedule) {
    btnConfirmSchedule.addEventListener('click', async () => {
        if (!_scheduleContext) return;

        let body = { trigger_type: selectedScheduleType === 'daily' ? 'cron' : selectedScheduleType };
        let displayStr = '';

        if (selectedScheduleType === 'once') {
            const d = scheduleDateInput.value;
            const t = scheduleTimeInput.value;
            if (!d || !t) {
                showToast('Please select a date and time.', 'error');
                return;
            }
            const runAtIso = localToUtcIso(d, t);
            const nowIso = new Date().toISOString();
            if (runAtIso <= nowIso) {
                showToast('Scheduled time must be in the future.', 'error');
                return;
            }
            body.run_at = runAtIso;
            displayStr = `at ${new Date(runAtIso).toLocaleString()}`;
        } else if (selectedScheduleType === 'daily') {
            const t = scheduleTimeInput.value;
            if (!t) {
                showToast('Please select a time.', 'error');
                return;
            }
            const today = localDateString(0);
            const runAtIso = localToUtcIso(today, t);
            const dateObj = new Date(runAtIso);
            body.cron_hour = dateObj.getUTCHours();
            body.cron_minute = dateObj.getUTCMinutes();
            body.run_at = runAtIso;
            displayStr = `Daily at ${t}`;
        } else if (selectedScheduleType === 'interval') {
            const val = parseInt(scheduleIntervalValue.value);
            if (!val || val <= 0) {
                showToast('Please enter a valid interval duration.', 'error');
                return;
            }
            body.interval_value = val;
            body.interval_unit = scheduleIntervalUnit.value;
            body.run_at = new Date().toISOString();
            displayStr = `every ${val} ${body.interval_unit}`;
        }

        const { engine, payload, label, edit_job_id } = _scheduleContext;
        body = { ...payload, ...body };
        if (edit_job_id) {
            body.job_id = edit_job_id;
        }

        const endpointMap = {
            podcast: '/api/schedule/podcast',
            docs: '/api/schedule/docs',
            web: '/api/schedule/web',
            youtube: '/api/schedule/youtube',
            telegram: '/api/schedule/telegram',
            market_data: '/api/schedule/market_data',
            central_bank: '/api/schedule/central_bank'
        };

        const targetUrl = endpointMap[engine] || `/api/schedule/${engine}`;

        btnConfirmSchedule.disabled = true;
        btnConfirmSchedule.innerHTML = `<i data-lucide="loader-2"></i> Scheduling...`;
        lucide.createIcons({ root: btnConfirmSchedule });

        try {
            const res = await fetch(targetUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await res.json();

            if (data.status === 'success') {
                scheduleModal.classList.remove('active');
                _scheduleContext = null;

                showToast(`Scheduled: "${label}" ${displayStr}`, 'success');
                appendLog(`📅 Scheduled job: "${label}" — runs ${displayStr}`, 'success');

                // Refresh jobs list
                await loadScheduledJobs();

                // Navigate to dashboard to show it
                document.querySelector('[data-tab="dashboard"]').click();
            } else {
                showToast('Scheduling failed: ' + data.message, 'error');
            }
        } catch (e) {
            showToast('Scheduling error: ' + (e.message || 'Unknown error'), 'error');
        } finally {
            btnConfirmSchedule.disabled = false;
            btnConfirmSchedule.innerHTML = `<i data-lucide="calendar-check"></i> Confirm Schedule`;
            lucide.createIcons({ root: btnConfirmSchedule });
        }
    });
}

// ── Jobs List ─────────────────────────────────────────────────────────────

function createJobRow(job) {
    const row = document.createElement('div');
    row.className = 'scheduled-job-row';

    let scheduleRuleStr = '';
    if (job.trigger_type === 'cron') {
        const hour = String(job.cron_hour).padStart(2, '0');
        const min = String(job.cron_minute).padStart(2, '0');
        scheduleRuleStr = `Daily at ${hour}:${min} UTC`;
    } else if (job.trigger_type === 'interval') {
        scheduleRuleStr = `Every ${job.interval_value} ${job.interval_unit}`;
    } else {
        scheduleRuleStr = `Once`;
    }

    const nextRunTimeStr = job.run_at ? ` (Next: ${new Date(job.run_at).toLocaleString()})` : '';
    const displayTime = `${scheduleRuleStr}${nextRunTimeStr}`;
    const isUpcoming = job.status === 'pending';
    const isRunning = job.status === 'running';
    const isPast = ['completed', 'failed', 'cancelled', 'missed'].includes(job.status);

    // Status badge config
    const badgeConfig = {
        pending:   { cls: 'badge-pending',   text: '⏰ Pending' },
        running:   { cls: 'badge-running',   text: '⚡ Running' },
        completed: { cls: 'badge-completed', text: '✓ Done' },
        failed:    { cls: 'badge-failed',    text: '✗ Failed' },
        cancelled: { cls: 'badge-cancelled', text: '✕ Cancelled' },
        missed:    { cls: 'badge-failed',    text: '⚠ Missed' }
    };
    const badge = badgeConfig[job.status] || { cls: 'badge-pending', text: job.status };

    // Engine icon
    const engineIcon = { podcast: 'headphones', docs: 'file-text', web: 'globe', market_data: 'bar-chart-2', central_bank: 'landmark' }[job.engine] || 'calendar';

    row.innerHTML = `
        <div class="sj-icon">
            <i data-lucide="${engineIcon}"></i>
        </div>
        <div class="sj-info">
            <div class="sj-label">${job.label}</div>
            <div class="sj-time">
                <i data-lucide="clock" style="width:11px;height:11px;vertical-align:middle;margin-right:3px;"></i>
                ${displayTime}
                ${job.error ? `<span style="color:var(--danger); margin-left:8px;" title="${job.error}">⚠ Error</span>` : ''}
            </div>
        </div>
        <div class="sj-actions">
            <span class="sj-badge ${badge.cls}">${badge.text}</span>
            <button class="icon-btn sj-history-btn" onclick="viewJobHistory('${job.id}')" title="View execution history" aria-label="View execution history">
                <i data-lucide="file-clock"></i>
            </button>
            ${isRunning ? `
                <button class="icon-btn danger sj-cancel-btn" onclick="cancelScheduledJob('${job.id}')" title="Cancel this job" aria-label="Cancel this job">
                    <i data-lucide="x"></i>
                </button>
            ` : ''}
            ${isUpcoming ? `
                <button class="icon-btn sj-edit-btn" onclick="editScheduledJob('${job.id}')" title="Edit this job" aria-label="Edit this job">
                    <i data-lucide="edit-2"></i>
                </button>
            ` : ''}
            ${isPast || isUpcoming ? `
                <button class="icon-btn danger sj-delete-btn" onclick="deleteScheduledJob('${job.id}')" title="Delete this job" aria-label="Delete this job">
                    <i data-lucide="trash-2"></i>
                </button>
            ` : ''}
        </div>
    `;
    return row;
}

async function loadScheduledJobs() {
    const dashboardContainer = document.getElementById('scheduled-jobs-list');
    const pendingList = document.getElementById('pending-jobs-list');
    const completedList = document.getElementById('completed-jobs-list');
    const cancelledList = document.getElementById('cancelled-jobs-list');

    try {
        const res = await fetch('/api/schedules');
        const data = await res.json();

        if (data.status !== 'success' || !data.jobs) {
            return;
        }

        const jobs = data.jobs;
        window.__allJobs = jobs;

        // 1. Populate Dashboard container
        if (dashboardContainer) {
            dashboardContainer.innerHTML = '';
            if (jobs.length === 0) {
                dashboardContainer.innerHTML = `<div style="padding:20px; text-align:center; color:#71717a; font-size:0.9rem;">No scheduled jobs found.</div>`;
            } else {
                jobs.forEach(job => {
                    dashboardContainer.appendChild(createJobRow(job));
                });
                lucide.createIcons({ root: dashboardContainer });
            }
        }

        // 2. Populate Dedicated Tab Containers
        if (pendingList && completedList && cancelledList) {
            pendingList.innerHTML = '';
            completedList.innerHTML = '';
            cancelledList.innerHTML = '';

            const pendingJobs = jobs.filter(j => j.status === 'pending' || j.status === 'running');
            const completedJobs = jobs.filter(j => j.status === 'completed' || j.status === 'failed');
            const cancelledJobs = jobs.filter(j => j.status === 'cancelled' || j.status === 'missed');

            // Set counts
            const pCount = document.getElementById('pending-jobs-count');
            const cCount = document.getElementById('completed-jobs-count');
            const cnCount = document.getElementById('cancelled-jobs-count');
            if (pCount) pCount.innerText = pendingJobs.length;
            if (cCount) cCount.innerText = completedJobs.length;
            if (cnCount) cnCount.innerText = cancelledJobs.length;

            if (pendingJobs.length === 0) {
                pendingList.innerHTML = `<div style="text-align: center; color: #71717a; padding: 20px;">No pending or running jobs.</div>`;
            } else {
                pendingJobs.forEach(job => pendingList.appendChild(createJobRow(job)));
                lucide.createIcons({ root: pendingList });
            }

            if (completedJobs.length === 0) {
                completedList.innerHTML = `<div style="text-align: center; color: #71717a; padding: 20px;">No completed or failed jobs.</div>`;
            } else {
                completedJobs.forEach(job => completedList.appendChild(createJobRow(job)));
                lucide.createIcons({ root: completedList });
            }

            if (cancelledJobs.length === 0) {
                cancelledList.innerHTML = `<div style="text-align: center; color: #71717a; padding: 20px;">No cancelled or missed jobs.</div>`;
            } else {
                cancelledJobs.forEach(job => cancelledList.appendChild(createJobRow(job)));
                lucide.createIcons({ root: cancelledList });
            }
        }

    } catch (e) {
        console.error('Failed to load scheduled jobs:', e);
    }
}

window.cancelScheduledJob = async function(jobId) {
    if (!confirm('Cancel this running job?')) return;
    try {
        const res = await fetch(`/api/schedule/${jobId}/cancel`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Job cancelled.', 'info');
            await loadScheduledJobs();
        } else {
            showToast('Failed to cancel: ' + data.message, 'error');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
};

window.deleteScheduledJob = async function(jobId) {
    if (!confirm('Delete this job from history?')) return;
    try {
        const res = await fetch(`/api/schedule/${jobId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Job deleted.', 'info');
            await loadScheduledJobs();
        } else {
            showToast('Failed to delete: ' + data.message, 'error');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
};

window.editScheduledJob = function(jobId) {
    if (!window.__allJobs) return;
    const job = window.__allJobs.find(j => j.id === jobId);
    if (!job) return;

    _scheduleContext = { 
        engine: job.engine, 
        payload: job.payload, 
        label: job.label,
        edit_job_id: job.id
    };
    scheduleModalLabel.textContent = "Edit Schedule: " + job.label;

    selectedScheduleType = job.trigger_type === 'cron' ? 'daily' : job.trigger_type;
    toggleScheduleTypeFields();

    if (selectedScheduleType === 'once' && job.run_at) {
        try {
            const localDate = new Date(job.run_at);
            scheduleDateInput.value = localDate.toLocaleDateString('en-CA');
            scheduleTimeInput.value = localDate.toTimeString().slice(0, 5);
        } catch (e) {}
    } else if (selectedScheduleType === 'daily') {
        const d = new Date();
        d.setUTCHours(job.cron_hour, job.cron_minute, 0, 0);
        scheduleTimeInput.value = d.toTimeString().slice(0, 5);
    } else if (selectedScheduleType === 'interval') {
        scheduleIntervalValue.value = job.interval_value;
        scheduleIntervalUnit.value = job.interval_unit;
    }
    updateUtcPreview();

    scheduleModal.classList.add('active');
    lucide.createIcons({ root: scheduleModal });
};

// Refresh button
const btnRefreshSchedules = document.getElementById('btn-refresh-schedules');
if (btnRefreshSchedules) {
    btnRefreshSchedules.addEventListener('click', async () => {
        btnRefreshSchedules.classList.add('spinning');
        await loadScheduledJobs();
        setTimeout(() => btnRefreshSchedules.classList.remove('spinning'), 600);
        lucide.createIcons({ root: btnRefreshSchedules });
    });
}

// Refresh Ollama models button
const btnRefreshOllamaModels = document.getElementById('btn-refresh-ollama-models');
if (btnRefreshOllamaModels) {
    btnRefreshOllamaModels.addEventListener('click', async () => {
        btnRefreshOllamaModels.classList.add('spinning');
        await updateOllamaModelsDropdown();
        setTimeout(() => btnRefreshOllamaModels.classList.remove('spinning'), 600);
        showToast("Ollama models list refreshed", "success");
    });
}

// ── Wire Up Schedule Buttons ──────────────────────────────────────────────

// Podcast — All Shows (sidebar button)
const btnSchedulePodcast = document.getElementById('btn-schedule-podcast');
if (btnSchedulePodcast) {
    btnSchedulePodcast.addEventListener('click', () => {
        openScheduleModal('podcast', { show_index: null, episode_index: null }, 'Podcast · All Shows');
    });
}

// Docs
const btnScheduleDocs = document.getElementById('btn-schedule-docs');
if (btnScheduleDocs) {
    btnScheduleDocs.addEventListener('click', () => {
        openScheduleModal('docs', { target_files: null }, 'Documents · All Pending');
    });
}

// Web
const btnScheduleWeb = document.getElementById('btn-schedule-web');
if (btnScheduleWeb) {
    btnScheduleWeb.addEventListener('click', () => {
        const url = document.getElementById('web-harvest-url')?.value || 'https://epaper.thehindu.com/reader';
        openScheduleModal('web', { url }, `Web · ${url.length > 40 ? url.slice(0, 40) + '...' : url}`);
    });
}

// Also expose a global for per-show schedule (used from show cards)
window.scheduleSpecificShow = function(showIndex) {
    const show = globalConfig.shows[showIndex];
    if (!show) return;
    const label = `Podcast · ${show.show_name} (Latest ${globalConfig.sync_limit || 1})`;
    openScheduleModal('podcast', { show_index: showIndex, episode_index: null }, label);
};

// ── Tab switch: refresh jobs when going to Dashboard or Schedules ────────
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        if (tab.dataset.tab === 'dashboard' || tab.dataset.tab === 'schedules') {
            loadScheduledJobs();
        }
    });
});

// Expose a global for job history logs
window.viewJobHistory = function(jobId) {
    if (!window.__allJobs) return;
    const job = window.__allJobs.find(j => j.id === jobId);
    if (!job) return;

    const titleEl = document.getElementById('job-history-modal-title');
    if (titleEl) {
        titleEl.textContent = `History: ${job.label}`;
    }

    const listEl = document.getElementById('job-history-list');
    if (listEl) {
        listEl.innerHTML = '';
        const history = job.history || [];
        if (history.length === 0) {
            listEl.innerHTML = `<div style="text-align: center; color: #71717a; padding: 20px;">No execution logs recorded yet.</div>`;
        } else {
            // Sort history to show most recent first
            const sortedHistory = [...history].reverse();
            sortedHistory.forEach(run => {
                const item = document.createElement('div');
                item.className = 'history-item';
                item.style.background = 'rgba(255, 255, 255, 0.02)';
                item.style.border = '1px solid rgba(255, 255, 255, 0.05)';
                item.style.borderRadius = '12px';
                item.style.padding = '15px';
                item.style.display = 'flex';
                item.style.flexDirection = 'column';
                item.style.gap = '8px';

                const runTime = new Date(run.run_at).toLocaleString();
                
                // Status badge config
                const badgeConfig = {
                    completed: { cls: 'badge-completed', text: '✓ Done' },
                    failed:    { cls: 'badge-failed',    text: '✗ Failed' }
                };
                const badge = badgeConfig[run.status] || { cls: 'badge-pending', text: run.status };

                let logsHtml = '';
                if (run.status === 'failed' && run.error) {
                    logsHtml = `
                        <div style="color: var(--danger); font-size: 0.82rem; background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.15); border-radius: 8px; padding: 10px; font-family: monospace; word-break: break-all;">
                            Error: ${run.error}
                        </div>
                    `;
                }

                if (run.logs && run.logs.length > 0) {
                    logsHtml += `
                        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; font-family: monospace; font-size: 0.78rem; color: #e4e4e7; max-height: 150px; overflow-y: auto; line-height: 1.4;">
                            ${run.logs.map(log => `
                                <div style="margin-bottom: 4px; ${log.includes('complete') || log.includes('✓') ? 'color: #6ee7b7;' : log.includes('fail') || log.includes('⚠') ? 'color: #fca5a5;' : ''}">
                                    ${escapeHtml(log)}
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else if (!run.error) {
                    logsHtml = `
                        <div style="color: #71717a; font-size: 0.8rem; font-style: italic; padding: 5px 10px;">
                            No logs captured for this run.
                        </div>
                    `;
                }

                item.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.85rem; color: #a1a1aa; font-family: monospace;">${runTime}</span>
                        <span class="sj-badge ${badge.cls}">${badge.text}</span>
                    </div>
                    ${logsHtml}
                `;
                listEl.appendChild(item);
            });
        }
    }

    if (historyModal) {
        historyModal.classList.add('active');
        lucide.createIcons({ root: historyModal });
    }
};

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Boot
init();

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
const settingEodhdKey = document.getElementById('setting-eodhd-key');
const settingPolygonKey = document.getElementById('setting-polygon-key');
const settingRefinitivKey = document.getElementById('setting-refinitiv-key');
const settingRefinitivUsername = document.getElementById('setting-refinitiv-username');
const settingRefinitivPassword = document.getElementById('setting-refinitiv-password');
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
                    <button class="icon-btn" onclick="syncMarketData(${index})" title="Sync Now" aria-label="Sync Now" style="color:var(--primary);">
                        <i data-lucide="refresh-cw" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="icon-btn" onclick="scheduleMarketData(${index})" title="Schedule" aria-label="Schedule" style="color:#f59e0b;">
                        <i data-lucide="calendar" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="icon-btn" onclick="editMarketData(${index})" title="Edit" aria-label="Edit" style="color:var(--text-light);">
                        <i data-lucide="edit-2" style="width:16px; height:16px;"></i>
                    </button>
                    <button class="icon-btn" onclick="deleteMarketData(${index})" title="Delete" aria-label="Delete" style="color:#ef4444;">
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
    let pointName = "all market data points";
    let bodyData = {};
    
    if (index !== null && index !== undefined) {
        const point = globalConfig.market_data_points[index];
        pointName = point.symbol;
        bodyData = { index: index };
    }
    
    appendLog(`Starting sync for ${pointName}...`, "info");
    try {
        const res = await fetch('/api/harvest/market', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(bodyData)
        });
        const data = await res.json();
        if (data.status === 'success') {
            appendLog(`Successfully synced ${pointName}`, "success");
            showToast(`Market data synced successfully.`, "success");
        } else {
            appendLog(`Error syncing ${pointName}: ${data.message}`, "error");
            showToast(`Error syncing ${pointName}`, "error");
        }
    } catch (e) {
        appendLog(`Failed to sync ${pointName}: ${e.message}`, "error");
        showToast(`Failed to sync ${pointName}`, "error");
    }
}

async function scheduleMarketData(index) {
    const point = globalConfig.market_data_points[index];
    openScheduleModal('market_data', { index: index }, `Market Data · ${point.symbol}`);
}

if (btnAddMd) btnAddMd.addEventListener('click', () => openMdModal());
if (btnCloseMdModal) btnCloseMdModal.addEventListener('click', closeMdModal);
if (btnSaveMd) btnSaveMd.addEventListener('click', saveMarketData);

if (btnSaveMdProviders) {
    btnSaveMdProviders.addEventListener('click', async () => {
        if (!globalConfig.api_keys) globalConfig.api_keys = {};
        globalConfig.api_keys.alphavantage = settingAlphavantageKey.value;
        globalConfig.api_keys.eodhd = settingEodhdKey.value;
        globalConfig.api_keys.polygon = settingPolygonKey.value;
        globalConfig.api_keys.refinitiv_app_key = settingRefinitivKey.value;
        globalConfig.api_keys.refinitiv_username = settingRefinitivUsername.value;
        globalConfig.api_keys.refinitiv_password = settingRefinitivPassword.value;
        
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

// ─────────────────────────────────────────────────────────────────────────────
// YOUTUBE HARVESTER FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

window.ytEditingIndex = -1;

window.renderYoutubeChannels = function() {
    if (!youtubeChannelsContainer) return;
    youtubeChannelsContainer.innerHTML = '';

    const channels = globalConfig.youtube_channels || [];
    if (channels.length === 0) {
        youtubeChannelsContainer.innerHTML = `
            <div class="no-data-card" style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-youtube" style="margin-bottom: 12px; opacity: 0.5;"><path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"></path><path d="m10 15 5-3-5-3z"></path></svg>
                <p>No YouTube channels configured yet.</p>
            </div>
        `;
        lucide.createIcons({ root: youtubeChannelsContainer });
        return;
    }

    channels.forEach((chan, index) => {
        const card = document.createElement('div');
        card.className = 'show-card';
        card.innerHTML = `
            <div class="show-card-actions-top">
                <button class="icon-btn" onclick="editYoutubeChannel(${index})" title="Edit Channel" aria-label="Edit Channel">
                    <i data-lucide="edit-3"></i>
                </button>
                <button class="icon-btn danger" onclick="deleteYoutubeChannel(${index})" title="Remove Channel" aria-label="Remove Channel">
                    <i data-lucide="trash-2"></i>
                </button>
            </div>
            <div>
                <div class="show-channel"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-youtube w-3 h-3 inline"><path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"></path><path d="m10 15 5-3-5-3z"></path></svg> YouTube</div>
                <div class="show-title" style="padding-right: 80px;">${chan.channel_name}</div>
                <div class="show-url" title="${chan.rss_url}">${chan.rss_url}</div>
            </div>
            <div class="show-actions" style="justify-content: flex-start; gap: 8px;">
                 <button class="btn-primary" onclick="browseYoutubeVideos(${index})" style="padding: 8px 12px; font-size: 0.8rem; background: #374151;">
                    <i data-lucide="list-video"></i> Browse
                </button>
                <button class="btn-primary" onclick="syncSpecificYoutubeChannel(${index})" style="padding: 8px 12px; font-size: 0.8rem; background: var(--success);">
                    <i data-lucide="refresh-cw"></i> Sync
                </button>
                <button class="btn-secondary" onclick="scheduleSpecificYoutube(${index})" style="padding: 8px 12px; font-size: 0.8rem; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);">
                    <i data-lucide="calendar-clock"></i> Schedule
                </button>
            </div>
        `;
        youtubeChannelsContainer.appendChild(card);
    });

    lucide.createIcons({ root: youtubeChannelsContainer });
};

window.editYoutubeChannel = function(index) {
    window.ytEditingIndex = index;
    const chan = globalConfig.youtube_channels[index];
    const titleEl = document.getElementById('youtube-modal-title');
    if (titleEl) titleEl.innerText = "Edit YouTube Channel";
    youtubeChannelName.value = chan.channel_name;
    youtubeRssUrl.value = chan.rss_url;
    youtubeModal.classList.add('active');
};

window.deleteYoutubeChannel = async function(index) {
    if (confirm("Are you sure you want to delete this YouTube channel?")) {
        globalConfig.youtube_channels.splice(index, 1);
        renderYoutubeChannels();
        await saveConfig();
    }
};

window.saveYoutubeChannel = async function() {
    const name = youtubeChannelName.value.trim();
    let url = youtubeRssUrl.value.trim();

    if (!name || !url) {
        alert("Please fill all fields");
        return;
    }

    btnSaveYoutube.disabled = true;
    const originalText = btnSaveYoutube.textContent;
    btnSaveYoutube.textContent = "Saving...";

    try {
        if (url.includes('youtube.com') || url.includes('youtu.be') || url.includes('@')) {
            const res = await fetch('/api/resolve_youtube', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            if (data.status === 'success' && data.resolved_url) {
                url = data.resolved_url;
            }
        }

        const newChannel = { channel_name: name, rss_url: url };
        if (!globalConfig.youtube_channels) {
            globalConfig.youtube_channels = [];
        }

        if (window.ytEditingIndex >= 0) {
            globalConfig.youtube_channels[window.ytEditingIndex] = newChannel;
        } else {
            globalConfig.youtube_channels.push(newChannel);
        }

        youtubeModal.classList.remove('active');
        renderYoutubeChannels();
        await saveConfig();
    } catch (e) {
        alert("Error saving channel: " + e.message);
    } finally {
        btnSaveYoutube.disabled = false;
        btnSaveYoutube.textContent = originalText;
    }
};

window.syncSpecificYoutubeChannel = async function(index) {
    const channel = globalConfig.youtube_channels[index];
    appendLog(`Starting YouTube sync for ${channel.channel_name}...`, "info");
    
    // Redirect to dashboard logs
    document.querySelector('[data-tab="dashboard"]').click();
    
    try {
        const res = await fetch('/api/youtube/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_index: index, video_index: null })
        });
        
        // This is a streaming endpoint (ndjson)
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep last unfinished line

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.type === 'log') {
                        appendLog(data.message, 'info');
                    } else if (data.type === 'error') {
                        appendLog(`Error: ${data.message}`, 'error');
                    } else if (data.type === 'success') {
                        appendLog(data.message, 'success');
                    }
                } catch(e) {}
            }
        }
    } catch (e) {
        appendLog(`Failed to run YouTube sync: ${e.message}`, "error");
    }
};

window.syncYoutubeChannel = async function(index) {
    await syncSpecificYoutubeChannel(index);
};

window.scheduleSpecificYoutube = function(index) {
    const channel = globalConfig.youtube_channels[index];
    openScheduleModal('youtube', { channel_index: index }, `YouTube · ${channel.channel_name}`);
};

window.browseYoutubeVideos = async function(index) {
    const channel = globalConfig.youtube_channels[index];
    episodeBrowserTitle.textContent = `Browse Videos: ${channel.channel_name}`;
    episodeList.innerHTML = '';
    episodeLoading.style.display = 'block';
    episodeModal.classList.add('active');

    try {
        const res = await fetch(`/api/youtube/episodes?channel_index=${index}`);
        const data = await res.json();
        episodeLoading.style.display = 'none';

        if (data.status === 'success' && data.episodes) {
            data.episodes.forEach(ep => {
                const row = document.createElement('div');
                row.className = 'episode-row';
                row.dataset.title = ep.title;

                const info = document.createElement('div');
                info.className = 'episode-info';
                info.innerHTML = `
                    <div class="episode-title">${ep.title}</div>
                    <div class="episode-meta">Published: ${ep.published}</div>
                `;

                const action = document.createElement('div');
                action.className = 'episode-action';

                if (ep.is_synced) {
                    action.innerHTML = `<span class="synced-badge"><i data-lucide="check-circle-2"></i> Synced</span>`;
                } else {
                    action.innerHTML = `
                        <button class="btn-primary" onclick="syncSpecificYoutubeVideo(${index}, ${ep.index}, this)" style="padding: 6px 12px; font-size: 0.75rem; background: var(--success);">
                            <i data-lucide="refresh-cw"></i> Sync
                        </button>
                    `;
                }

                row.appendChild(info);
                row.appendChild(action);
                episodeList.appendChild(row);
            });
            lucide.createIcons({ root: episodeList });
        } else {
            episodeList.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">Failed to load videos: ${data.message}</div>`;
        }
    } catch (e) {
        episodeLoading.style.display = 'none';
        episodeList.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">Error loading videos: ${e.message}</div>`;
    }
};

window.syncSpecificYoutubeVideo = async function(channelIndex, videoIndex, button) {
    if (button) {
        button.disabled = true;
        button.innerHTML = `<i data-lucide="loader-2" class="animate-spin"></i> Syncing...`;
        lucide.createIcons({ root: button });
    }
    
    try {
        const res = await fetch('/api/youtube/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_index: channelIndex, video_index: videoIndex })
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.type === 'log') {
                        appendLog(data.message, 'info');
                    } else if (data.type === 'error') {
                        appendLog(`Error: ${data.message}`, 'error');
                    } else if (data.type === 'success') {
                        appendLog(data.message, 'success');
                        if (button) {
                            button.parentElement.innerHTML = `<span class="synced-badge"><i data-lucide="check-circle-2"></i> Synced</span>`;
                        }
                    }
                } catch(e) {}
            }
        }
    } catch (e) {
        appendLog(`Failed to sync video: ${e.message}`, "error");
        if (button) {
            button.disabled = false;
            button.innerHTML = `<i data-lucide="refresh-cw"></i> Sync`;
            lucide.createIcons({ root: button });
        }
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// TELEGRAM HARVESTER FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

window.tgEditingIndex = -1;

window.renderTelegramChannels = function() {
    if (!telegramChannelsContainer) return;
    telegramChannelsContainer.innerHTML = '';

    const channels = (globalConfig.telegram && globalConfig.telegram.channels) || [];
    if (channels.length === 0) {
        telegramChannelsContainer.innerHTML = `
            <div class="no-data-card" style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
                <i data-lucide="send" style="width: 48px; height: 48px; margin-bottom: 12px; stroke-width: 1.5; opacity: 0.5;"></i>
                <p>No Telegram channels configured yet.</p>
            </div>
        `;
        lucide.createIcons({ root: telegramChannelsContainer });
        return;
    }

    channels.forEach((chan, index) => {
        const card = document.createElement('div');
        card.className = 'show-card';
        const keywordsInfo = chan.keywords ? `<div style="font-size:0.75rem; color:var(--text-muted); margin-top:4px;">Filter: <span style="color:var(--primary);">${chan.keywords}</span></div>` : '';
        card.innerHTML = `
            <div class="show-card-actions-top">
                <button class="icon-btn" onclick="editTelegramChannel(${index})" title="Edit Channel" aria-label="Edit Channel">
                    <i data-lucide="edit-3"></i>
                </button>
                <button class="icon-btn danger" onclick="deleteTelegramChannel(${index})" title="Remove Channel" aria-label="Remove Channel">
                    <i data-lucide="trash-2"></i>
                </button>
            </div>
            <div>
                <div class="show-channel"><i data-lucide="send" class="w-3 h-3 inline"></i> Telegram</div>
                <div class="show-title" style="padding-right: 80px;">${chan.channel_name}</div>
                <div class="show-url" title="${chan.channel_id}">${chan.channel_id}</div>
                ${keywordsInfo}
            </div>
            <div class="show-actions" style="justify-content: flex-start; gap: 8px;">
                <button class="btn-primary" onclick="syncSpecificTelegramChannel(${index})" style="padding: 8px 12px; font-size: 0.8rem; background: var(--success);">
                    <i data-lucide="refresh-cw"></i> Sync
                </button>
                <button class="btn-secondary" onclick="scheduleSpecificTelegram(${index})" style="padding: 8px 12px; font-size: 0.8rem; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);">
                    <i data-lucide="calendar-clock"></i> Schedule
                </button>
            </div>
        `;
        telegramChannelsContainer.appendChild(card);
    });

    lucide.createIcons({ root: telegramChannelsContainer });
};

window.editTelegramChannel = function(index) {
    window.tgEditingIndex = index;
    const chan = globalConfig.telegram.channels[index];
    const titleEl = document.getElementById('telegram-modal-title');
    if (titleEl) titleEl.innerText = "Edit Telegram Channel";
    telegramChannelName.value = chan.channel_name;
    telegramChannelId.value = chan.channel_id;
    telegramKeywords.value = chan.keywords || '';
    telegramModal.classList.add('active');
};

window.deleteTelegramChannel = async function(index) {
    if (confirm("Are you sure you want to delete this Telegram channel?")) {
        globalConfig.telegram.channels.splice(index, 1);
        renderTelegramChannels();
        await saveConfig();
    }
};

window.saveTelegramChannel = async function() {
    const name = telegramChannelName.value.trim();
    const id = telegramChannelId.value.trim();
    const keywords = telegramKeywords.value.trim();

    if (!name || !id) {
        alert("Please fill all required fields");
        return;
    }

    btnSaveTelegram.disabled = true;
    const originalText = btnSaveTelegram.textContent;
    btnSaveTelegram.textContent = "Saving...";

    try {
        const newChannel = { channel_name: name, channel_id: id };
        if (keywords) {
            newChannel.keywords = keywords;
        }

        if (!globalConfig.telegram) {
            globalConfig.telegram = { channels: [] };
        }
        if (!globalConfig.telegram.channels) {
            globalConfig.telegram.channels = [];
        }

        if (window.tgEditingIndex >= 0) {
            globalConfig.telegram.channels[window.tgEditingIndex] = newChannel;
        } else {
            globalConfig.telegram.channels.push(newChannel);
        }

        telegramModal.classList.remove('active');
        renderTelegramChannels();
        await saveConfig();
    } catch (e) {
        alert("Error saving Telegram channel: " + e.message);
    } finally {
        btnSaveTelegram.disabled = false;
        btnSaveTelegram.textContent = originalText;
    }
};

window.syncSpecificTelegramChannel = async function(index) {
    const channel = globalConfig.telegram.channels[index];
    appendLog(`Starting Telegram sync for ${channel.channel_name}...`, "info");
    
    // Redirect to dashboard logs
    document.querySelector('[data-tab="dashboard"]').click();
    
    try {
        const res = await fetch('/api/telegram/harvest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_index: index })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            appendLog(`Telegram sync job scheduled for ${channel.channel_name}. Check Schedules tab.`, "success");
            loadScheduledJobs();
        } else {
            appendLog(`Error triggering sync: ${data.message}`, "error");
        }
    } catch (e) {
        appendLog(`Failed to run Telegram sync: ${e.message}`, "error");
    }
};

window.syncTelegramChannel = async function(index) {
    appendLog(index === null ? "Starting sync for all Telegram channels..." : `Starting sync for Telegram channel index ${index}...`, "info");
    document.querySelector('[data-tab="dashboard"]').click();
    
    try {
        const res = await fetch('/api/telegram/harvest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_index: index })
        });
        const data = await res.json();
        if (data.status === 'success') {
            appendLog(index === null ? "Sync all Telegram channels started." : "Telegram channel sync started.", "success");
            loadScheduledJobs();
        } else {
            appendLog(`Error: ${data.message}`, "error");
        }
    } catch (e) {
        appendLog(`Error starting Telegram sync: ${e.message}`, "error");
    }
};

window.scheduleSpecificTelegram = function(index) {
    const channel = globalConfig.telegram.channels[index];
    openScheduleModal('telegram', { channel_index: index }, `Telegram · ${channel.channel_name}`);
};

// ── CENTRAL BANK & MACRO HARVESTER UI ──────────────────────────────────────
function renderCentralBankConfig() {
    const cbMode = document.getElementById('cb-engine-mode');
    const cbUrl = document.getElementById('cb-ollama-url');

    if (cbMode) cbMode.value = globalConfig.digest_engine_mode || 'raw_data';
    if (cbUrl) cbUrl.value = globalConfig.ollama_url || 'http://localhost:11434';
    
    updateOllamaModelsDropdown();
}

const btnSaveCbConfig = document.getElementById('btn-save-cb-config');
const btnSyncCb = document.getElementById('btn-sync-centralbank');
const btnScheduleCb = document.getElementById('btn-schedule-centralbank');
const btnRefreshCbOllamaModels = document.getElementById('btn-refresh-cb-ollama-models');

if (btnRefreshCbOllamaModels) {
    btnRefreshCbOllamaModels.addEventListener('click', async () => {
        btnRefreshCbOllamaModels.classList.add('spinning');
        await updateOllamaModelsDropdown();
        setTimeout(() => btnRefreshCbOllamaModels.classList.remove('spinning'), 600);
        lucide.createIcons({ root: btnRefreshCbOllamaModels });
        showToast("Ollama models list refreshed.", "info");
    });
}

if (btnSaveCbConfig) {
    btnSaveCbConfig.addEventListener('click', async () => {
        const cbMode = document.getElementById('cb-engine-mode');
        const cbModel = document.getElementById('cb-ollama-model');
        const cbUrl = document.getElementById('cb-ollama-url');

        if (cbMode) globalConfig.digest_engine_mode = cbMode.value;
        if (cbModel) globalConfig.ollama_model = cbModel.value;
        if (cbUrl) globalConfig.ollama_url = cbUrl.value;

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(globalConfig)
            });
            if (res.ok) {
                showToast("Central Bank Engine Controls saved.", "success");
                appendLog("Central Bank Engine Controls saved successfully.", "success");
            } else {
                showToast("Error saving Central Bank config.", "error");
                appendLog("Error saving Central Bank config.", "error");
            }
        } catch (e) {
            showToast("Error saving config: " + e.message, "error");
            appendLog("Error saving Central Bank config: " + e.message, "error");
        }
    });
}

if (btnSyncCb) {
    btnSyncCb.addEventListener('click', async () => {
        showToast("Starting Central Bank & Macro Digest harvest...", "info");
        appendLog("Starting Central Bank & Macro Digest Ingestion...", "info");
        
        // Navigate to dashboard to show live logs
        const dashBtn = document.querySelector('[data-tab="dashboard"]');
        if (dashBtn) dashBtn.click();

        const badge = document.getElementById('cb-status-badge');
        if (badge) {
            badge.innerText = "Ingesting...";
            badge.style.background = "rgba(251, 191, 36, 0.2)";
            badge.style.color = "#fbbf24";
        }
        try {
            const res = await fetch('/api/harvest/central_bank', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                showToast("Central Bank Harvest Success: " + data.message, "success");
                appendLog("Central Bank Harvest Success: " + data.message, "success");
                if (badge) {
                    badge.innerText = "Ready";
                    badge.style.background = "rgba(74, 222, 128, 0.2)";
                    badge.style.color = "#4ade80";
                }
                const todayStr = new Date().toISOString().split('T')[0];
                const fileEl = document.getElementById('cb-latest-file');
                if (fileEl) fileEl.innerText = `CentralBank_Macro_Digest_${todayStr}.md`;
            } else {
                showToast("Central Bank Harvest Error: " + data.message, "error");
                appendLog("Central Bank Harvest Error: " + data.message, "error");
                if (badge) {
                    badge.innerText = "Error";
                    badge.style.background = "rgba(239, 68, 68, 0.2)";
                    badge.style.color = "#ef4444";
                }
            }
        } catch (e) {
            showToast("Central Bank Harvest Failed: " + e.message, "error");
            appendLog("Central Bank Harvest Failed: " + e.message, "error");
            if (badge) {
                badge.innerText = "Failed";
                badge.style.background = "rgba(239, 68, 68, 0.2)";
                badge.style.color = "#ef4444";
            }
        }
    });
}

if (btnScheduleCb) {
    btnScheduleCb.addEventListener('click', () => {
        openScheduleModal('central_bank', {}, 'Central Bank & Macro Digest');
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// --- AUDIO OVERVIEW PODCAST MODULE ---
// ─────────────────────────────────────────────────────────────────────────────

let audioOverviewVoices = [];
let audioInputFiles = [];
let selectedAudioFilePaths = new Set();
let currentAudioPlayerTurns = [];
let activeTranscriptIndex = -1;

async function loadAudioOverviewTab() {
    await loadAudioVoices();
    await scanAudioInputFolder();
    await loadAudioHistory();
}

async function loadAudioVoices() {
    try {
        const res = await fetch('/api/audio-overview/voices');
        const data = await res.json();
        if (data.status === 'success') {
            audioOverviewVoices = data.voices || [];
            populateVoiceDropdowns();
        }
    } catch (e) {
        console.error('Error loading voices:', e);
    }
}

function populateVoiceDropdowns() {
    const h1Select = document.getElementById('audio-host1-voice');
    const h2Select = document.getElementById('audio-host2-voice');
    if (!h1Select || !h2Select) return;

    h1Select.innerHTML = '';
    h2Select.innerHTML = '';

    audioOverviewVoices.forEach(v => {
        const opt1 = document.createElement('option');
        opt1.value = v.id;
        opt1.textContent = v.name;
        if (v.id === 'en-US-AndrewNeural') opt1.selected = true;
        h1Select.appendChild(opt1);

        const opt2 = document.createElement('option');
        opt2.value = v.id;
        opt2.textContent = v.name;
        if (v.id === 'en-US-AvaNeural') opt2.selected = true;
        h2Select.appendChild(opt2);
    });
}

// Helper to escape HTML strings safely
function escapeAudioHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function scanAudioInputFolder() {
    const folderInput = document.getElementById('audio-input-folder');
    const filesList = document.getElementById('audio-input-files-list');
    const folder = folderInput ? folderInput.value.trim() : './RawMaterials';

    if (filesList) {
        filesList.innerHTML = '<div style="text-align: center; color: #71717a; padding: 20px;"><div class="spinning inline-block mb-1"><i data-lucide="loader-2"></i></div><p>Scanning folder for articles...</p></div>';
        lucide.createIcons();
    }

    try {
        const res = await fetch(`/api/audio-overview/input-files?folder=${encodeURIComponent(folder)}`);
        const data = await res.json();

        if (data.status === 'success') {
            audioInputFiles = data.files || [];
            renderAudioInputFiles();
        } else {
            if (filesList) filesList.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 15px;">${escapeAudioHtml(data.message) || 'Failed to scan folder'}</div>`;
        }
    } catch (e) {
        console.error("Audio Folder Scan Error:", e);
        if (filesList) filesList.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 15px;">Error scanning folder: ${escapeAudioHtml(e.message)}</div>`;
    }
}

function renderAudioInputFiles() {
    const filesList = document.getElementById('audio-input-files-list');
    const countSpan = document.getElementById('audio-selected-count');
    if (!filesList) return;

    if (audioInputFiles.length === 0) {
        filesList.innerHTML = '<div style="text-align: center; color: #71717a; padding: 20px;">No articles found in this folder. Place daily news syntheses (.md, .txt) in the folder.</div>';
        if (countSpan) countSpan.textContent = '0';
        return;
    }

    filesList.innerHTML = '';
    audioInputFiles.forEach((file, idx) => {
        const item = document.createElement('div');
        const isSelected = selectedAudioFilePaths.has(file.full_path);
        item.className = 'audio-file-item' + (isSelected ? ' selected' : '');

        const safeTitle = escapeAudioHtml(file.title);
        const safeDate = escapeAudioHtml(file.date_str);
        const safeFilename = escapeAudioHtml(file.filename);
        const safePreview = escapeAudioHtml(file.preview);

        item.innerHTML = `
            <input type="checkbox" id="chk-audio-${idx}" ${isSelected ? 'checked' : ''}>
            <div style="flex: 1; overflow: hidden;">
                <div style="font-weight: 500; font-size: 0.88rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${safeTitle}</div>
                <div style="font-size: 0.75rem; color: #a1a1aa;">${safeDate} · ${file.word_count || 0} words · ${safeFilename}</div>
                ${safePreview ? `<div style="font-size: 0.75rem; color: #71717a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${safePreview}</div>` : ''}
            </div>
        `;

        const chk = item.querySelector('input[type="checkbox"]');
        item.addEventListener('click', (e) => {
            if (e.target !== chk) {
                chk.checked = !chk.checked;
            }
            if (chk.checked) {
                selectedAudioFilePaths.add(file.full_path);
                item.classList.add('selected');
            } else {
                selectedAudioFilePaths.delete(file.full_path);
                item.classList.remove('selected');
            }
            if (countSpan) countSpan.textContent = selectedAudioFilePaths.size;
        });

        filesList.appendChild(item);
    });

    if (countSpan) countSpan.textContent = selectedAudioFilePaths.size;
}


function toggleSelectAllAudioFiles() {
    const btn = document.getElementById('btn-select-all-audio-files');
    if (selectedAudioFilePaths.size === audioInputFiles.length) {
        selectedAudioFilePaths.clear();
        if (btn) btn.textContent = 'Select All';
    } else {
        selectedAudioFilePaths.clear();
        audioInputFiles.forEach(f => selectedAudioFilePaths.add(f.full_path));
        if (btn) btn.textContent = 'Deselect All';
    }
    renderAudioInputFiles();
}

async function generateAudioOverview() {
    const filePaths = Array.from(selectedAudioFilePaths);
    const rawText = document.getElementById('audio-raw-text') ? document.getElementById('audio-raw-text').value.trim() : '';
    const title = document.getElementById('audio-podcast-title') ? document.getElementById('audio-podcast-title').value.trim() : 'Daily News Audio Overview';
    const style = document.getElementById('audio-overview-style') ? document.getElementById('audio-overview-style').value : 'deep_dive';
    const targetDuration = document.getElementById('audio-target-duration') ? document.getElementById('audio-target-duration').value : '18-20';
    const host1Voice = document.getElementById('audio-host1-voice') ? document.getElementById('audio-host1-voice').value : 'en-US-AndrewNeural';
    const host2Voice = document.getElementById('audio-host2-voice') ? document.getElementById('audio-host2-voice').value : 'en-US-AvaNeural';
    const topicFocus = document.getElementById('audio-topic-focus') ? document.getElementById('audio-topic-focus').value.trim() : '';

    if (filePaths.length === 0 && !rawText) {
        alert('Please select at least one article or paste custom synthesis text.');
        return;
    }

    const progressContainer = document.getElementById('audio-progress-container');
    const progressStatus = document.getElementById('audio-progress-status');
    const progressPercent = document.getElementById('audio-progress-percent');
    const progressBar = document.getElementById('audio-progress-bar');
    const playerCard = document.getElementById('audio-player-card');

    if (progressContainer) progressContainer.style.display = 'block';
    if (playerCard) playerCard.style.display = 'none';

    try {
        const response = await fetch('/api/audio-overview/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_paths: filePaths,
                raw_text: rawText,
                title: title,
                style: style,
                target_duration: targetDuration,
                host1_voice: host1Voice,
                host2_voice: host2Voice,
                topic_focus: topicFocus
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payloadStr = line.replace('data: ', '').trim();
                    if (!payloadStr) continue;
                    try {
                        const event = JSON.parse(payloadStr);
                        if (event.type === 'status') {
                            if (progressStatus) progressStatus.textContent = event.data.message;
                            if (progressPercent) progressPercent.textContent = `${event.data.progress}%`;
                            if (progressBar) progressBar.style.width = `${event.data.progress}%`;
                        } else if (event.type === 'complete') {
                            if (progressContainer) progressContainer.style.display = 'none';
                            initAudioPlayer(event.data);
                            await loadAudioHistory();
                        } else if (event.type === 'error') {
                            if (progressContainer) progressContainer.style.display = 'none';
                            alert(`Audio Overview Error: ${event.data.message}`);
                        }
                    } catch (err) {
                        console.error('SSE JSON parse error:', err);
                    }
                }
            }
        }
    } catch (e) {
        if (progressContainer) progressContainer.style.display = 'none';
        alert(`Failed to start audio generation: ${e.message}`);
    }
}

function initAudioPlayer(data) {
    const playerCard = document.getElementById('audio-player-card');
    const titleEl = document.getElementById('player-podcast-title');
    const metaEl = document.getElementById('player-podcast-meta');
    const obsidianLink = document.getElementById('player-obsidian-link');
    const audioElement = document.getElementById('main-audio-element');
    const downloadBtn = document.getElementById('btn-download-mp3');

    if (!playerCard || !audioElement) return;

    if (titleEl) titleEl.textContent = data.title;
    if (metaEl) metaEl.innerHTML = `NotebookLM Deep Dive · Duration: <span id="player-duration-text">${data.duration}</span>`;
    if (downloadBtn) downloadBtn.href = data.audio_url;

    if (obsidianLink && data.obsidian_note) {
        obsidianLink.href = `obsidian://open?file=Podcasts/${encodeURIComponent(data.obsidian_note)}`;
    }

    audioElement.src = data.audio_url;
    audioElement.load();
    playerCard.style.display = 'block';

    currentAudioPlayerTurns = data.timestamped_turns || [];
    renderInteractiveTranscript(currentAudioPlayerTurns);
    setupAudioPlayerControls(audioElement);

    // Auto-play audio
    audioElement.play().catch(e => console.log('Autoplay prevented:', e));
}

function setupAudioPlayerControls(audioElement) {
    const playPauseBtn = document.getElementById('btn-player-play-pause');
    const playIcon = document.getElementById('icon-player-play');
    const seekbar = document.getElementById('player-seekbar');
    const currTimeEl = document.getElementById('player-current-time');
    const totTimeEl = document.getElementById('player-total-time');
    const speedSelect = document.getElementById('player-speed-select');
    const skipBackBtn = document.getElementById('btn-player-skip-back');
    const skipFwdBtn = document.getElementById('btn-player-skip-forward');

    function updatePlayState() {
        if (audioElement.paused) {
            if (playIcon) playIcon.setAttribute('data-lucide', 'play');
        } else {
            if (playIcon) playIcon.setAttribute('data-lucide', 'pause');
        }
        lucide.createIcons();
    }

    if (playPauseBtn) {
        playPauseBtn.onclick = () => {
            if (audioElement.paused) audioElement.play();
            else audioElement.pause();
            updatePlayState();
        };
    }

    audioElement.onplay = updatePlayState;
    audioElement.onpause = updatePlayState;

    audioElement.ontimeupdate = () => {
        const cur = audioElement.currentTime;
        const dur = audioElement.duration || 1;
        if (seekbar) seekbar.value = (cur / dur) * 100;

        if (currTimeEl) currTimeEl.textContent = formatTimeSeconds(cur);
        if (totTimeEl) totTimeEl.textContent = formatTimeSeconds(dur);

        // Highlight transcript turn matching current time
        const curMs = cur * 1000;
        let foundIdx = -1;
        for (let i = 0; i < currentAudioPlayerTurns.length; i++) {
            const turn = currentAudioPlayerTurns[i];
            if (curMs >= turn.start_ms && curMs <= turn.end_ms) {
                foundIdx = i;
                break;
            }
        }
        if (foundIdx !== -1 && foundIdx !== activeTranscriptIndex) {
            highlightTranscriptTurn(foundIdx);
        }
    };

    if (seekbar) {
        seekbar.oninput = () => {
            const dur = audioElement.duration || 1;
            audioElement.currentTime = (seekbar.value / 100) * dur;
        };
    }

    if (speedSelect) {
        speedSelect.onchange = () => {
            audioElement.playbackRate = parseFloat(speedSelect.value);
        };
    }

    if (skipBackBtn) {
        skipBackBtn.onclick = () => { audioElement.currentTime = Math.max(0, audioElement.currentTime - 15); };
    }
    if (skipFwdBtn) {
        skipFwdBtn.onclick = () => { audioElement.currentTime = Math.min(audioElement.duration || 0, audioElement.currentTime + 15); };
    }
}

function renderInteractiveTranscript(turns) {
    const container = document.getElementById('player-transcript-container');
    if (!container) return;

    if (!turns || turns.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #71717a;">No transcript available.</div>';
        return;
    }

    container.innerHTML = '';
    turns.forEach((turn, idx) => {
        const item = document.createElement('div');
        const isH1 = turn.speaker === 'Host 1';
        item.className = `transcript-turn-bubble ${isH1 ? 'host-1' : 'host-2'}`;
        item.id = `transcript-turn-${idx}`;

        const safeTimestamp = escapeAudioHtml(turn.timestamp);
        const safeTurnText = escapeAudioHtml(turn.text);

        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="${isH1 ? 'host-badge-1' : 'host-badge-2'}">${isH1 ? 'Host 1 (Alex)' : 'Host 2 (Jamie)'}</span>
                <span style="font-size: 0.75rem; color: #a1a1aa; font-family: monospace;">${safeTimestamp}</span>
            </div>
            <div style="font-size: 0.88rem; color: #e4e4e7; line-height: 1.5; margin-top: 4px;">${safeTurnText}</div>
        `;

        item.onclick = () => {
            const audioElement = document.getElementById('main-audio-element');
            if (audioElement) {
                audioElement.currentTime = turn.start_ms / 1000;
                audioElement.play();
            }
            highlightTranscriptTurn(idx);
        };

        container.appendChild(item);
    });
}

function highlightTranscriptTurn(idx) {
    activeTranscriptIndex = idx;
    const bubbles = document.querySelectorAll('.transcript-turn-bubble');
    bubbles.forEach((b, i) => {
        if (i === idx) {
            b.classList.add('active-turn');
            b.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            b.classList.remove('active-turn');
        }
    });
}

function formatTimeSeconds(seconds) {
    if (isNaN(seconds)) return '00:00';
    const sec = Math.floor(seconds);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

async function loadAudioHistory() {
    const listEl = document.getElementById('audio-history-list');
    if (!listEl) return;

    try {
        const res = await fetch('/api/audio-overview/history');
        const data = await res.json();

        if (data.status === 'success') {
            const podcasts = data.podcasts || [];
            if (podcasts.length === 0) {
                listEl.innerHTML = '<div style="text-align: center; color: #71717a; padding: 20px;">No past podcast overviews found.</div>';
                return;
            }

            listEl.innerHTML = '';
            podcasts.forEach(p => {
                const card = document.createElement('div');
                card.className = 'glass-card';
                card.style.cssText = 'padding: 15px 18px; display: flex; align-items: center; justify-content: space-between; gap: 15px; border: 1px solid rgba(255,255,255,0.06);';

                const safeTitle = escapeAudioHtml(p.title);
                const safeDate = escapeAudioHtml(p.date_str);
                const safeDuration = escapeAudioHtml(p.duration);
                const safeNote = escapeAudioHtml(p.md_filename);
                const safeMp3 = escapeAudioHtml(p.mp3_filename);

                card.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 14px; overflow: hidden;">
                        <div style="width: 42px; height: 42px; border-radius: 10px; background: linear-gradient(135deg, var(--primary), #8b5cf6); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            <i data-lucide="mic" style="color: #fff; width: 20px; height: 20px;"></i>
                        </div>
                        <div style="overflow: hidden;">
                            <div style="font-weight: 600; font-size: 0.95rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${safeTitle}</div>
                            <div style="font-size: 0.78rem; color: #a1a1aa; margin-top: 2px;">
                                ${safeDate} · Duration: ${safeDuration} · ${safeNote}
                            </div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                        ${p.has_audio ? `<button class="btn-primary btn-play-podcast" data-mp3="${safeMp3}" data-title="${safeTitle}" data-duration="${safeDuration}" style="padding: 6px 14px; font-size: 0.8rem;"><i data-lucide="play"></i> Listen</button>` : '<span style="font-size:0.75rem; color:#ef4444;">Audio Missing</span>'}
                        <a href="obsidian://open?file=Podcasts/${encodeURIComponent(p.md_filename)}" target="_blank" class="btn-secondary" style="padding: 6px 12px; font-size: 0.8rem;"><i data-lucide="external-link"></i> Note</a>
                    </div>
                `;

                const playBtn = card.querySelector('.btn-play-podcast');
                if (playBtn) {
                    playBtn.onclick = () => {
                        const audioUrl = `/api/audio-overview/audio/${encodeURIComponent(p.mp3_filename)}`;
                        initAudioPlayer({
                            title: p.title,
                            duration: p.duration,
                            audio_url: audioUrl,
                            obsidian_note: p.md_filename,
                            timestamped_turns: []
                        });
                    };
                }

                listEl.appendChild(card);
            });
            lucide.createIcons();
        }
    } catch (e) {
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 15px;">Failed to load history: ${escapeAudioHtml(e.message)}</div>`;
    }
}


// Bind Audio Overview Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    const btnScan = document.getElementById('btn-scan-audio-folder');
    const btnSelectAll = document.getElementById('btn-select-all-audio-files');
    const btnGenerate = document.getElementById('btn-generate-audio-overview');
    const folderInput = document.getElementById('audio-input-folder');

    if (btnScan) btnScan.onclick = scanAudioInputFolder;
    if (btnSelectAll) btnSelectAll.onclick = toggleSelectAllAudioFiles;
    if (btnGenerate) btnGenerate.onclick = generateAudioOverview;

    if (folderInput) {
        folderInput.onchange = scanAudioInputFolder;
    }
});

