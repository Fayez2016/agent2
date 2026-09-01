// LangGraph Deep Agent Dashboard Client
// Strict Chronological Execution (Tools First, Final Response Last), Permanent HITL Cards & Incident Export
const API_HOST = window.location.hostname || "localhost";
const BASE_URL = `${window.location.protocol}//${API_HOST}:8642`;
const API_KEY = "hermes-api-secret";

let currentThreadId = null;
let currentMode = "enforced";
let activePendingRequestId = null;

document.addEventListener("DOMContentLoaded", () => {
  // DOM References
  const chatStream = document.getElementById("chat-messages");
  const inputForm = document.getElementById("prompt-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const loadingIndicator = document.getElementById("loading-indicator");
  const threadsList = document.getElementById("threads-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const exportReportBtn = document.getElementById("export-report-btn");
  const purgeDbBtn = document.getElementById("purge-db-btn");
  const hitlModeToggle = document.getElementById("hitl-mode-toggle");
  const modeStatusText = document.getElementById("mode-status-text");
  
  // Views
  const chatView = document.getElementById("chat-view");
  const eventsView = document.getElementById("events-view");
  const auditView = document.getElementById("audit-view");
  const studioView = document.getElementById("studio-view");
  const settingsView = document.getElementById("settings-view");
  const tabChat = document.getElementById("tab-chat");
  const tabEvents = document.getElementById("tab-events");
  const tabAudit = document.getElementById("tab-audit");
  const tabStudio = document.getElementById("tab-studio");
  const tabSettings = document.getElementById("tab-settings");
  const webhookCountBadge = document.getElementById("webhook-count-badge");
  const eventsPendingStat = document.getElementById("events-pending-stat");
  const eventsTotalStat = document.getElementById("events-total-stat");
  const eventsTableBody = document.getElementById("events-table-body");
  const refreshEventsBtn = document.getElementById("refresh-events-btn");
  const simulateAlertStormBtn = document.getElementById("simulate-alert-storm-btn");
  const triggerBatchProcessBtn = document.getElementById("trigger-batch-process-btn");
  const auditTableBody = document.getElementById("audit-table-body");
  const refreshAuditBtn = document.getElementById("refresh-audit-btn");
  const refreshStudioBtn = document.getElementById("refresh-studio-btn");

  // Export Modal
  const exportModal = document.getElementById("export-modal");
  const exportPreview = document.getElementById("export-preview");
  const closeExportModalBtn = document.getElementById("close-export-modal");
  const downloadMdBtn = document.getElementById("download-md-btn");
  const printReportBtn = document.getElementById("print-report-btn");

  // Settings Elements
  const settingsEmailInput = document.getElementById("settings-email-input");
  const settingsSaveEmailBtn = document.getElementById("settings-save-email-btn");
  const settingsPurgeDbBtn = document.getElementById("settings-purge-db-btn");
  const settingsHitlToggle = document.getElementById("settings-hitl-toggle");
  const settingsModeLabel = document.getElementById("settings-mode-label");
  const hitlBadgeIcon = document.getElementById("hitl-badge-icon");
  const hitlBadgeText = document.getElementById("hitl-badge-text");
  const supervisorHealthBadge = document.getElementById("supervisor-health-badge");
  const supervisorDot = document.getElementById("supervisor-dot");
  const supervisorText = document.getElementById("supervisor-text");

  let currentExportMarkdown = "";

  initApp();

  async function initApp() {
    await fetchHitlMode();
    await fetchNotificationEmail();
    await populateDomainSwitcher();
    await loadThreads();
    await pollWebhookBufferCount();
    await pollSupervisorHealth();
    startPendingHitlPolling();
    startWebhookPolling();
    startSupervisorPolling();
  }

  // --- Multi-MCP Supervisor Daemon Polling ---
  async function pollSupervisorHealth() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/system/supervisor`);
      const data = await resp.json();
      const isHealthy = data.status === "healthy";
      
      if (supervisorHealthBadge && supervisorDot && supervisorText) {
        if (isHealthy) {
          supervisorHealthBadge.style.background = "rgba(16, 185, 129, 0.15)";
          supervisorHealthBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
          supervisorHealthBadge.style.color = "#34d399";
          supervisorDot.style.background = "#10b981";
          supervisorText.textContent = "Supervisor: Healthy";
        } else {
          supervisorHealthBadge.style.background = "rgba(239, 68, 68, 0.15)";
          supervisorHealthBadge.style.borderColor = "rgba(239, 68, 68, 0.3)";
          supervisorHealthBadge.style.color = "#f87171";
          supervisorDot.style.background = "#ef4444";
          supervisorText.textContent = "Supervisor: Degraded";
        }
        supervisorHealthBadge.title = data.summary || "Multi-MCP Supervisor Daemon";
      }

      // Update Settings View Component Health Grid
      const statDb = document.getElementById("health-stat-db");
      const statLlm = document.getElementById("health-stat-llm");
      const statAnsible = document.getElementById("health-stat-ansible");
      const statSop = document.getElementById("health-stat-sop");

      if (statDb) {
        const isDbUp = data.database?.status === "healthy";
        statDb.innerHTML = isDbUp ? "🟢 Healthy" : "🔴 Unreachable";
        statDb.style.color = isDbUp ? "#10b981" : "#ef4444";
      }
      if (statLlm) {
        const isLlmUp = data.llm_gateway?.status === "healthy";
        statLlm.innerHTML = isLlmUp ? `🟢 Online (${data.llm_gateway?.provider || 'LLM'})` : "🔴 Degraded";
        statLlm.style.color = isLlmUp ? "#10b981" : "#ef4444";
      }
      if (statAnsible && data.mcp_servers?.ansible) {
        const isAnsUp = data.mcp_servers.ansible.status === "healthy";
        statAnsible.innerHTML = isAnsUp ? `🟢 Online (${data.mcp_servers.ansible.latency_ms || 0}ms)` : "🔴 Offline";
        statAnsible.style.color = isAnsUp ? "#10b981" : "#ef4444";
      }
      if (statSop && data.mcp_servers?.sop) {
        const isSopUp = data.mcp_servers.sop.status === "healthy";
        statSop.innerHTML = isSopUp ? `🟢 Online (${data.mcp_servers.sop.latency_ms || 0}ms)` : "🔴 Offline";
        statSop.style.color = isSopUp ? "#10b981" : "#ef4444";
      }
    } catch (e) {
      if (supervisorText) supervisorText.textContent = "Supervisor: Offline";
    }
  }

  const refreshHealthBtn = document.getElementById("refresh-health-btn");
  if (refreshHealthBtn) {
    refreshHealthBtn.addEventListener("click", async () => {
      refreshHealthBtn.textContent = "⏳ Probing...";
      await pollSupervisorHealth();
      setTimeout(() => { refreshHealthBtn.textContent = "🔄 Probe All Components"; }, 1000);
    });
  }

  function startSupervisorPolling() {
    setInterval(pollSupervisorHealth, 10000);
  }

  if (supervisorHealthBadge) {
    supervisorHealthBadge.addEventListener("click", async () => {
      try {
        const resp = await fetch(`${BASE_URL}/v1/system/supervisor`);
        const data = await resp.json();
        let details = `🛡️ Multi-MCP Supervisor Daemon Health Status\n`;
        details += `Status: ${data.status.toUpperCase()}\n`;
        details += `Database Pool: ${data.database?.status || 'unknown'}\n`;
        details += `LLM Provider: ${data.llm_gateway?.provider || 'unknown'} (${data.llm_gateway?.status || 'unknown'})\n\n`;
        details += `Connected MCP Servers:\n`;
        if (data.mcp_servers) {
          Object.entries(data.mcp_servers).forEach(([k, v]) => {
            details += `- ${k} (${v.url}): ${v.status.toUpperCase()} [${v.latency_ms}ms]\n`;
          });
        }
        alert(details);
      } catch (e) {
        alert("Failed to query supervisor: " + e.message);
      }
    });
  }

  // --- SRE Report Recipient Email Settings ---
  async function fetchNotificationEmail() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/settings/notification_email`);
      const data = await resp.json();
      if (data.email && settingsEmailInput) {
        settingsEmailInput.value = data.email;
      }
    } catch (e) {
      console.warn("Failed to fetch notification email", e);
    }
  }

  if (settingsSaveEmailBtn) {
    settingsSaveEmailBtn.addEventListener("click", async () => {
      const email = (settingsEmailInput.value || "").trim();
      if (!email || !email.includes("@")) {
        alert("Please enter a valid email address.");
        return;
      }
      try {
        const resp = await fetch(`${BASE_URL}/v1/settings/notification_email`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: email })
        });
        const data = await resp.json();
        if (data.status === "success") {
          settingsSaveEmailBtn.textContent = "✓ Saved";
          settingsSaveEmailBtn.style.background = "#10b981";
          setTimeout(() => {
            settingsSaveEmailBtn.textContent = "Save Email";
            settingsSaveEmailBtn.style.background = "var(--accent-color, #3b82f6)";
          }, 2000);
        } else {
          alert("Failed to save email: " + JSON.stringify(data));
        }
      } catch (err) {
        alert("Error saving notification email: " + err.message);
      }
    });
  }

  if (settingsPurgeDbBtn) {
    settingsPurgeDbBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to purge stale thread histories and historical test HITL records from PostgreSQL?")) {
        return;
      }
      try {
        const resp = await fetch(`${BASE_URL}/v1/hitl/cleanup`, { method: "POST" });
        const data = await resp.json();
        alert(`✓ Cleanup Completed:\n- Purged Threads: ${data.purged_threads || 0}\n- Purged Messages: ${data.purged_messages || 0}\n- Purged HITL Audits: ${data.purged_hitl || 0}`);
        await loadThreads();
      } catch (e) {
        alert("Failed to clean database: " + e.message);
      }
    });
  }

  // --- View Switcher ---
  function hideAllViews() {
    tabChat.classList.remove("active");
    if (tabEvents) tabEvents.classList.remove("active");
    tabAudit.classList.remove("active");
    if (tabStudio) tabStudio.classList.remove("active");
    if (tabSettings) tabSettings.classList.remove("active");
    chatView.style.display = "none";
    if (eventsView) eventsView.style.display = "none";
    auditView.style.display = "none";
    if (studioView) studioView.style.display = "none";
    if (settingsView) settingsView.style.display = "none";
  }

  tabChat.addEventListener("click", () => {
    hideAllViews();
    tabChat.classList.add("active");
    chatView.style.display = "flex";
  });

  if (tabEvents) {
    tabEvents.addEventListener("click", async () => {
      hideAllViews();
      tabEvents.classList.add("active");
      eventsView.style.display = "block";
      await loadEventsFeed();
    });
  }

  tabAudit.addEventListener("click", async () => {
    hideAllViews();
    tabAudit.classList.add("active");
    auditView.style.display = "block";
    await loadAuditHistory();
  });

  if (tabStudio) {
    tabStudio.addEventListener("click", async () => {
      hideAllViews();
      tabStudio.classList.add("active");
      studioView.style.display = "block";
      await loadStudioData();
    });
  }

  if (tabSettings) {
    tabSettings.addEventListener("click", async () => {
      hideAllViews();
      tabSettings.classList.add("active");
      settingsView.style.display = "block";
      await fetchNotificationEmail();
      await fetchHitlMode();
      await fetchSMTPSettings();
    });
  }

  // --- Inbound Webhook Alarms & Event Storm Feed ---
  async function pollWebhookBufferCount() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/events/pending?domain=${activeDomainKey || 'linux'}`);
      const data = await resp.json();
      const count = data.pending_count || 0;
      if (webhookCountBadge) {
        if (count > 0) {
          webhookCountBadge.textContent = count;
          webhookCountBadge.style.display = "inline-block";
        } else {
          webhookCountBadge.style.display = "none";
        }
      }
      if (eventsPendingStat) eventsPendingStat.textContent = `${count} Alarms`;
    } catch (e) {
      // quiet poll
    }
  }

  function startWebhookPolling() {
    setInterval(pollWebhookBufferCount, 3000);
  }

  async function loadEventsFeed() {
    if (!eventsTableBody) return;
    try {
      const [pendResp, histResp] = await Promise.all([
        fetch(`${BASE_URL}/v1/events/pending?domain=${activeDomainKey || 'linux'}`),
        fetch(`${BASE_URL}/v1/events/history?limit=50`)
      ]);
      const pendData = await pendResp.json();
      const histData = await histResp.json();
      
      const pendingCount = pendData.pending_count || 0;
      const historyList = histData.events || [];

      if (eventsPendingStat) eventsPendingStat.textContent = `${pendingCount} Alarms`;
      if (eventsTotalStat) eventsTotalStat.textContent = `${historyList.length} Events`;

      eventsTableBody.innerHTML = "";
      if (historyList.length === 0) {
        eventsTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: #64748b; padding: 20px;">No webhook events recorded yet. Click 'Simulate 20-Alarm Storm' to test alert ingestion.</td></tr>`;
        return;
      }

      historyList.forEach((ev) => {
        const tr = document.createElement("tr");
        const isPending = ev.status === "PENDING";
        const isCritical = ev.severity === "critical";
        
        tr.innerHTML = `
          <td>#${ev.id}</td>
          <td><strong style="color: #f8fafc; font-family: var(--font-mono);">${escapeHtml(ev.host_target)}</strong></td>
          <td><code>${escapeHtml(ev.alert_type)}</code></td>
          <td><span class="status-badge ${isCritical ? 'status-denied' : 'status-pending'}">${escapeHtml(ev.severity.toUpperCase())}</span></td>
          <td><span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-size: 10px; padding: 2px 6px;">${escapeHtml(ev.domain)}</span></td>
          <td style="font-size: 11px; color: #94a3b8;">${ev.received_at ? new Date(ev.received_at).toLocaleTimeString() : '-'}</td>
          <td><span class="status-badge ${isPending ? 'status-pending' : 'status-granted'}">${escapeHtml(ev.status)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px; color: #94a3b8;">${escapeHtml(ev.batch_id || 'Buffering...')}</td>
        `;
        eventsTableBody.appendChild(tr);
      });
    } catch (e) {
      eventsTableBody.innerHTML = `<tr><td colspan="8" style="color: #ef4444; padding: 12px;">Failed to load events: ${e.message}</td></tr>`;
    }
  }

  if (refreshEventsBtn) refreshEventsBtn.addEventListener("click", loadEventsFeed);

  if (simulateAlertStormBtn) {
    simulateAlertStormBtn.addEventListener("click", async () => {
      simulateAlertStormBtn.disabled = true;
      simulateAlertStormBtn.textContent = "⏳ Simulating Storm...";
      try {
        const nodes = ["ha_cluster1_node1", "ha_cluster1_node2", "ha_cluster2_node1", "rhel-prod-01", "rhel-prod-02"];
        const alertTypes = ["CorosyncLinkFlapping", "DiskPressure95Percent", "MemoryExhaustion", "PCSResourceFailCount"];
        const fakeEvents = [];
        for (let i = 0; i < 20; i++) {
          fakeEvents.push({
            host_target: nodes[i % nodes.length],
            alert_type: alertTypes[i % alertTypes.length],
            severity: i % 3 === 0 ? "critical" : "warning",
            domain: activeDomainKey || "linux",
            payload: { iteration: i + 1, source: "Dynatrace_Webhook_Simulator" }
          });
        }

        const resp = await fetch(`${BASE_URL}/v1/events/bulk`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ events: fakeEvents, domain: activeDomainKey || "linux" })
        });
        const data = await resp.json();
        alert(`✓ Webhook Ingestion Complete:\n- Ingested ${data.count} raw alarms into 5-minute rolling buffer.\n- Deduplicator subagent is buffering alarms.`);
        await loadEventsFeed();
        await pollWebhookBufferCount();
      } catch (e) {
        alert("Simulation error: " + e.message);
      } finally {
        simulateAlertStormBtn.disabled = false;
        simulateAlertStormBtn.textContent = "⚡ Simulate 20-Alarm Storm";
      }
    });
  }

  if (triggerBatchProcessBtn) {
    triggerBatchProcessBtn.addEventListener("click", async () => {
      triggerBatchProcessBtn.disabled = true;
      triggerBatchProcessBtn.textContent = "⏳ Deduplicating...";
      try {
        const resp = await fetch(`${BASE_URL}/v1/events/process_batch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain: activeDomainKey || "linux", trigger_remediation: true })
        });
        const data = await resp.json();
        const m = data.manifest;
        alert(`✓ 5-Minute Event Batch Deduplicated:\n- Total Raw Alarms Absorbed: ${m.total_raw_events}\n- Actionable Nodes: ${m.deduplicated_count}\n- Auto-Created Incident Session: ${data.thread_id || 'None'}`);
        await loadEventsFeed();
        await pollWebhookBufferCount();
        await loadThreads();
      } catch (e) {
        alert("Batch processing error: " + e.message);
      } finally {
        triggerBatchProcessBtn.disabled = false;
        triggerBatchProcessBtn.textContent = "🚀 Process & Deduplicate Batch Now";
      }
    });
  }

  // --- Live SMTP Relay Handlers ---
  const smtpHostInput = document.getElementById("smtp-host-input");
  const smtpPortInput = document.getElementById("smtp-port-input");
  const smtpUserInput = document.getElementById("smtp-user-input");
  const smtpPassInput = document.getElementById("smtp-pass-input");
  const saveSmtpBtn = document.getElementById("save-smtp-btn");
  const testSmtpBtn = document.getElementById("test-smtp-btn");
  const smtpStatusMsg = document.getElementById("smtp-status-msg");

  async function fetchSMTPSettings() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/settings/smtp`);
      const data = await resp.json();
      if (smtpHostInput && data.smtp_host) smtpHostInput.value = data.smtp_host;
      if (smtpPortInput && data.smtp_port) smtpPortInput.value = data.smtp_port;
      if (smtpUserInput && data.smtp_user) smtpUserInput.value = data.smtp_user;
    } catch (e) {
      console.warn("Failed to fetch SMTP settings:", e);
    }
  }

  if (saveSmtpBtn) {
    saveSmtpBtn.addEventListener("click", async () => {
      try {
        const resp = await fetch(`${BASE_URL}/v1/settings/smtp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            smtp_host: (smtpHostInput.value || "smtp.gmail.com").trim(),
            smtp_port: parseInt(smtpPortInput.value || "587"),
            smtp_user: (smtpUserInput.value || "").trim(),
            smtp_pass: (smtpPassInput.value || "").trim(),
            sender_email: (smtpUserInput.value || "").trim()
          })
        });
        const data = await resp.json();
        if (data.status === "success") {
          saveSmtpBtn.textContent = "✓ Saved";
          saveSmtpBtn.style.background = "#10b981";
          setTimeout(() => {
            saveSmtpBtn.textContent = "Save SMTP Config";
            saveSmtpBtn.style.background = "var(--accent-color, #3b82f6)";
          }, 2000);
        } else {
          alert("Failed to save SMTP: " + data.detail);
        }
      } catch (err) {
        alert("Error saving SMTP settings: " + err.message);
      }
    });
  }

  if (testSmtpBtn) {
    testSmtpBtn.addEventListener("click", async () => {
      if (smtpStatusMsg) {
        smtpStatusMsg.textContent = "⏳ Sending test email...";
        smtpStatusMsg.style.color = "#fbbf24";
      }
      try {
        const resp = await fetch(`${BASE_URL}/v1/settings/smtp/test`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            smtp_host: (smtpHostInput.value || "smtp.gmail.com").trim(),
            smtp_port: parseInt(smtpPortInput.value || "587"),
            smtp_user: (smtpUserInput.value || "").trim(),
            smtp_pass: (smtpPassInput.value || "").trim(),
            sender_email: (smtpUserInput.value || "").trim()
          })
        });
        const data = await resp.json();
        if (data.status === "success") {
          if (smtpStatusMsg) {
            smtpStatusMsg.textContent = "✓ " + data.message;
            smtpStatusMsg.style.color = "#10b981";
          }
        } else {
          if (smtpStatusMsg) {
            smtpStatusMsg.textContent = "✗ " + data.message;
            smtpStatusMsg.style.color = "#ef4444";
          }
        }
      } catch (err) {
        if (smtpStatusMsg) {
          smtpStatusMsg.textContent = "✗ " + err.message;
          smtpStatusMsg.style.color = "#ef4444";
        }
      }
    });
  }

  if (refreshStudioBtn) {
    refreshStudioBtn.addEventListener("click", loadStudioData);
  }

  // --- Linux SRE Studio Data Loaders & Renderers ---
  async function loadStudioData() {
    await Promise.all([loadStudioMCPServers(), loadStudioAgents(), loadStudioSkills()]);
  }

  // --- Add MCP Server UI Handlers ---
  const showAddMcpBtn = document.getElementById("show-add-mcp-btn");
  const addMcpFormCard = document.getElementById("add-mcp-form-card");
  const cancelAddMcpBtn = document.getElementById("cancel-add-mcp-btn");
  const saveNewMcpBtn = document.getElementById("save-new-mcp-btn");
  const newMcpNameInput = document.getElementById("new-mcp-name");
  const newMcpDomainSelect = document.getElementById("new-mcp-domain");
  const newMcpUrlInput = document.getElementById("new-mcp-url");
  const addMcpStatus = document.getElementById("add-mcp-status");

  if (showAddMcpBtn && addMcpFormCard) {
    showAddMcpBtn.addEventListener("click", () => {
      addMcpFormCard.style.display = addMcpFormCard.style.display === "none" ? "block" : "none";
    });
  }

  if (cancelAddMcpBtn && addMcpFormCard) {
    cancelAddMcpBtn.addEventListener("click", () => {
      addMcpFormCard.style.display = "none";
    });
  }

  if (saveNewMcpBtn) {
    saveNewMcpBtn.addEventListener("click", async () => {
      const name = (newMcpNameInput.value || "").trim().toLowerCase();
      const url = (newMcpUrlInput.value || "").trim();
      const domain = newMcpDomainSelect.value || "linux";

      if (!name || !url) {
        alert("Please provide both a server name and endpoint URL.");
        return;
      }

      if (addMcpStatus) {
        addMcpStatus.textContent = "⏳ Saving...";
        addMcpStatus.style.color = "#fbbf24";
      }

      try {
        const resp = await fetch(`${BASE_URL}/v1/studio/mcp_servers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name,
            display_name: name.toUpperCase() + " FastMCP",
            domain_scope: domain,
            url: url,
            transport: "streamable_http"
          })
        });
        const data = await resp.json();
        if (data.status === "success") {
          if (addMcpStatus) {
            addMcpStatus.textContent = "✓ Connected & Saved";
            addMcpStatus.style.color = "#10b981";
          }
          newMcpNameInput.value = "";
          newMcpUrlInput.value = "";
          setTimeout(() => {
            addMcpFormCard.style.display = "none";
            if (addMcpStatus) addMcpStatus.textContent = "";
          }, 1500);
          await loadStudioMCPServers();
        } else {
          alert("Failed to save MCP server: " + data.detail);
        }
      } catch (e) {
        alert("Error saving MCP server: " + e.message);
      }
    });
  }

  async function loadStudioMCPServers() {
    const listEl = document.getElementById("mcp-servers-list");
    if (!listEl) return;
    try {
      const [mcpResp, supResp] = await Promise.all([
        fetch(`${BASE_URL}/v1/studio/mcp_servers`),
        fetch(`${BASE_URL}/v1/system/supervisor`)
      ]);
      const mcpData = await mcpResp.json();
      const supData = await supResp.json();
      const servers = mcpData.servers || [];
      const mcpStatuses = supData.mcp_servers || {};

      listEl.innerHTML = servers.map(s => {
        const liveInfo = mcpStatuses[s.name] || {};
        const isUp = liveInfo.status === "healthy";
        const statusBadge = isUp 
          ? `<span style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(16, 185, 129, 0.3);">🟢 Online (${liveInfo.latency_ms || 0}ms)</span>`
          : `<span style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.3);">🔴 Unreachable</span>`;

        return `
          <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 6px; padding: 10px; font-size: 13px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <strong style="color: #60a5fa;">${escapeHtml(s.display_name || s.name)}</strong>
                ${statusBadge}
              </div>
              <div style="display: flex; gap: 6px; align-items: center;">
                <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-size: 10px; padding: 2px 6px;">${escapeHtml(s.domain_scope || 'linux')}</span>
                <button onclick="deleteMCPServer('${s.name}')" style="background: none; border: none; color: #ef4444; font-size: 13px; cursor: pointer; padding: 0 4px;" title="Remove MCP Server">🗑️</button>
              </div>
            </div>
            <div style="color: #94a3b8; font-size: 11px; margin-top: 4px; word-break: break-all;"><code>${escapeHtml(s.url)}</code></div>
            <div style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 11px; color: #64748b;">Transport: ${escapeHtml(s.transport)}</span>
              <button onclick="pingMCPServer('${s.name}')" style="background: #334155; border: 1px solid #475569; color: #f8fafc; font-size: 11px; padding: 3px 8px; border-radius: 4px; cursor: pointer;">⚡ Ping / Live Tools</button>
            </div>
            <div id="mcp-ping-${s.name}" style="margin-top: 6px; font-size: 11px; display: none;"></div>
          </div>
        `;
      }).join("");
    } catch (e) {
      listEl.innerHTML = `<div style="color: #ef4444; font-size: 12px;">Failed to load MCP servers: ${e.message}</div>`;
    }
  }

  window.deleteMCPServer = async function(serverName) {
    if (!confirm(`Are you sure you want to remove MCP server '${serverName}'?`)) return;
    try {
      await fetch(`${BASE_URL}/v1/studio/mcp_servers/${serverName}`, { method: "DELETE" });
      await loadStudioMCPServers();
    } catch (e) {
      alert("Failed to delete MCP server: " + e.message);
    }
  };

  window.pingMCPServer = async function(serverName) {
    const target = document.getElementById(`mcp-ping-${serverName}`);
    if (!target) return;
    target.style.display = "block";
    target.innerHTML = `<span style="color: #94a3b8;">Testing connection to ${serverName}...</span>`;
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/mcp_servers/${serverName}/ping`, { method: "POST" });
      const data = await resp.json();
      if (data.status === "connected") {
        target.innerHTML = `<div style="color: #10b981; margin-bottom: 4px;">✓ Connected (${data.live_tools_count} live tools):</div><div style="color: #94a3b8; font-size: 10px; max-height: 80px; overflow-y: auto;">${data.tools.map(t => `<code style="display:inline-block; margin:2px; padding:2px 4px; background:#0f172a; border-radius:3px;">${escapeHtml(t)}</code>`).join(" ")}</div>`;
      } else {
        target.innerHTML = `<span style="color: #ef4444;">✗ Unreachable: ${data.error || 'Connection timed out'}</span>`;
      }
    } catch (e) {
      target.innerHTML = `<span style="color: #ef4444;">✗ Error: ${e.message}</span>`;
    }
  };

  // --- Create Domain Agent UI Handlers ---
  const showAddAgentBtn = document.getElementById("show-add-agent-btn");
  const addAgentFormCard = document.getElementById("add-agent-form-card");
  const cancelAddAgentBtn = document.getElementById("cancel-add-agent-btn");
  const saveNewAgentBtn = document.getElementById("save-new-agent-btn");
  const newAgentKeyInput = document.getElementById("new-agent-key");
  const newAgentNameInput = document.getElementById("new-agent-name");
  const newAgentDomainSelect = document.getElementById("new-agent-domain");
  const newAgentPromptInput = document.getElementById("new-agent-prompt");
  const addAgentStatus = document.getElementById("add-agent-status");
  const domainAgentSwitcher = document.getElementById("domain-agent-switcher");

  let activeDomainKey = "linux_sre";

  if (showAddAgentBtn && addAgentFormCard) {
    showAddAgentBtn.addEventListener("click", () => {
      addAgentFormCard.style.display = addAgentFormCard.style.display === "none" ? "block" : "none";
    });
  }

  if (cancelAddAgentBtn && addAgentFormCard) {
    cancelAddAgentBtn.addEventListener("click", () => {
      addAgentFormCard.style.display = "none";
    });
  }

  if (saveNewAgentBtn) {
    saveNewAgentBtn.addEventListener("click", async () => {
      const key = (newAgentKeyInput.value || "").trim().toLowerCase();
      const name = (newAgentNameInput.value || "").trim();
      const domain = newAgentDomainSelect.value || "linux";
      const prompt = (newAgentPromptInput.value || "").trim();

      if (!key || !name || !prompt) {
        alert("Please provide an Agent Key, Display Name, and System Prompt.");
        return;
      }

      if (addAgentStatus) {
        addAgentStatus.textContent = "⏳ Saving...";
        addAgentStatus.style.color = "#fbbf24";
      }

      try {
        const resp = await fetch(`${BASE_URL}/v1/studio/agents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            key_name: key,
            display_name: name,
            domain_category: domain,
            description: `Lead Orchestrator for ${name}`,
            system_prompt: prompt
          })
        });
        const data = await resp.json();
        if (data.status === "success") {
          if (addAgentStatus) {
            addAgentStatus.textContent = "✓ Agent Created";
            addAgentStatus.style.color = "#10b981";
          }
          newAgentKeyInput.value = "";
          newAgentNameInput.value = "";
          newAgentPromptInput.value = "";
          setTimeout(() => {
            addAgentFormCard.style.display = "none";
            if (addAgentStatus) addAgentStatus.textContent = "";
          }, 1500);
          await loadStudioAgents();
          await populateDomainSwitcher();
        } else {
          alert("Failed to create agent: " + data.detail);
        }
      } catch (e) {
        alert("Error creating agent: " + e.message);
      }
    });
  }

  // --- Create Subagent UI Handlers ---
  const showAddSubagentBtn = document.getElementById("show-add-subagent-btn");
  const addSubagentFormCard = document.getElementById("add-subagent-form-card");
  const cancelAddSubagentBtn = document.getElementById("cancel-add-subagent-btn");
  const saveNewSubagentBtn = document.getElementById("save-new-subagent-btn");
  const newSubagentNameInput = document.getElementById("new-subagent-name");
  const newSubagentToolsInput = document.getElementById("new-subagent-tools");
  const newSubagentDescInput = document.getElementById("new-subagent-desc");
  const newSubagentPromptInput = document.getElementById("new-subagent-prompt");
  const addSubagentStatus = document.getElementById("add-subagent-status");

  if (showAddSubagentBtn && addSubagentFormCard) {
    showAddSubagentBtn.addEventListener("click", () => {
      addSubagentFormCard.style.display = addSubagentFormCard.style.display === "none" ? "block" : "none";
    });
  }

  if (cancelAddSubagentBtn && addSubagentFormCard) {
    cancelAddSubagentBtn.addEventListener("click", () => {
      addSubagentFormCard.style.display = "none";
    });
  }

  if (saveNewSubagentBtn) {
    saveNewSubagentBtn.addEventListener("click", async () => {
      const name = (newSubagentNameInput.value || "").trim().toLowerCase();
      const desc = (newSubagentDescInput.value || "").trim();
      const prompt = (newSubagentPromptInput.value || "").trim();
      const toolsStr = (newSubagentToolsInput.value || "").trim();
      const toolBindings = toolsStr ? toolsStr.split(",").map(t => t.trim()).filter(Boolean) : [];

      if (!name || !prompt) {
        alert("Please provide a Subagent Name and System Prompt.");
        return;
      }

      if (addSubagentStatus) {
        addSubagentStatus.textContent = "⏳ Saving...";
        addSubagentStatus.style.color = "#fbbf24";
      }

      try {
        // Fetch current active agent's id
        const respAg = await fetch(`${BASE_URL}/v1/studio/agents`);
        const dataAg = await respAg.json();
        const cur = (dataAg.agents || []).find(a => a.key_name === activeDomainKey);
        if (!cur) {
          alert("Active agent not found in database.");
          return;
        }

        const resp = await fetch(`${BASE_URL}/v1/studio/subagents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            parent_agent_id: cur.id,
            name: name,
            display_name: name,
            description: desc || name,
            system_prompt: prompt,
            tool_bindings: toolBindings
          })
        });
        const data = await resp.json();
        if (data.status === "success") {
          if (addSubagentStatus) {
            addSubagentStatus.textContent = "✓ Subagent Saved";
            addSubagentStatus.style.color = "#10b981";
          }
          newSubagentNameInput.value = "";
          newSubagentToolsInput.value = "";
          newSubagentDescInput.value = "";
          newSubagentPromptInput.value = "";
          setTimeout(() => {
            addSubagentFormCard.style.display = "none";
            if (addSubagentStatus) addSubagentStatus.textContent = "";
          }, 1500);
          await loadStudioAgents();
        } else {
          alert("Failed to save subagent: " + data.detail);
        }
      } catch (e) {
        alert("Error saving subagent: " + e.message);
      }
    });
  }

  if (domainAgentSwitcher) {
    domainAgentSwitcher.addEventListener("change", (e) => {
      activeDomainKey = e.target.value;
      console.log("Switched active domain agent to:", activeDomainKey);
      loadStudioAgents();
    });
  }

  async function populateDomainSwitcher() {
    if (!domainAgentSwitcher) return;
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/agents`);
      const data = await resp.json();
      const agents = data.agents || [];
      
      domainAgentSwitcher.innerHTML = agents.map(a => `
        <option value="${escapeHtml(a.key_name)}" ${a.key_name === activeDomainKey ? 'selected' : ''}>
          ⚡ ${escapeHtml(a.display_name)} (${escapeHtml(a.domain_category)})
        </option>
      `).join("");
    } catch (e) {
      console.warn("Failed to populate domain switcher:", e);
    }
  }

  async function loadStudioAgents() {
    const mainCardEl = document.getElementById("linux-main-agent-card");
    const subListEl = document.getElementById("domain-subagents-list");
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/agents`);
      const data = await resp.json();
      const agents = data.agents || [];
      const currentAgent = agents.find(a => a.key_name === activeDomainKey) || agents[0] || {
        display_name: "Linux SRE Lead Agent",
        domain_category: "linux",
        model_name: "qwen/qwen-2.5-72b-instruct",
        description: "Primary SRE Orchestrator",
        system_prompt: "Active SRE harness",
        subagents: []
      };

      if (currentAgent && mainCardEl) {
        mainCardEl.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <h3 style="font-size: 16px; color: #f8fafc; display: flex; align-items: center; gap: 8px;"><span>🛡️</span> ${escapeHtml(currentAgent.display_name)}</h3>
              <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Domain Category: <code>${escapeHtml(currentAgent.domain_category)}</code> | Model: <code>${escapeHtml(currentAgent.model_name)}</code></div>
            </div>
            <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 11px; padding: 3px 8px;">Active Lead Agent</span>
          </div>
          <div style="font-size: 12px; color: #cbd5e1; margin-bottom: 10px;">${escapeHtml(currentAgent.description || '')}</div>
          
          <details style="margin-top: 8px; background: #0f172a; border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 12px;">
            <summary style="font-size: 12px; font-weight: 600; color: #60a5fa; cursor: pointer; display: flex; justify-content: space-between; align-items: center;">
              <span>📜 Lead Orchestrator System Prompt</span>
              <span style="font-size: 11px; color: #94a3b8;">Click to Edit</span>
            </summary>
            <div style="margin-top: 8px;">
              <textarea id="edit-agent-prompt-${currentAgent.key_name}" rows="6" style="width: 100%; background: #1e293b; border: 1px solid #334155; color: #f8fafc; font-size: 11px; padding: 8px; border-radius: 4px; outline: none; font-family: var(--font-mono);">${escapeHtml(currentAgent.system_prompt)}</textarea>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <div id="save-prompt-status-${currentAgent.key_name}" style="font-size: 11px;"></div>
                <button onclick="saveAgentPrompt('${currentAgent.key_name}')" style="background: #10b981; border: none; color: #fff; font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 4px; cursor: pointer;">Save Prompt Changes</button>
              </div>
            </div>
          </details>
        `;

        if (subListEl) {
          const subagents = currentAgent.subagents || [];
          if (subagents.length === 0) {
            subListEl.innerHTML = `<div style="color: #64748b; font-size: 12px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 6px;">No specialized subagents attached to this agent. All tasks executed by the Lead Orchestrator.</div>`;
          } else {
            subListEl.innerHTML = subagents.map(sub => `
              <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; font-size: 13px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <strong style="color: #c084fc; font-family: var(--font-mono); font-size: 12px;">🤖 ${escapeHtml(sub.name)}</strong>
                  <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; font-size: 10px; padding: 2px 6px;">${(sub.tool_bindings || []).length} Tools</span>
                </div>
                <div style="color: #94a3b8; font-size: 11px; margin-top: 4px;">${escapeHtml(sub.description || '')}</div>
                
                <div style="margin-top: 8px; font-size: 11px;">
                  <span style="color: #64748b;">Bound FastMCP Tools:</span>
                  <div style="margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px;">
                    ${(sub.tool_bindings || []).map(tb => `<code style="font-size: 10px; background: #0f172a; padding: 2px 5px; border-radius: 3px; color: #38bdf8;">${escapeHtml(tb)}</code>`).join("")}
                  </div>
                </div>

                <details style="margin-top: 8px; background: #0f172a; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 4px; padding: 8px 10px;">
                  <summary style="font-size: 11px; font-weight: 600; color: #a855f7; cursor: pointer; display: flex; justify-content: space-between; align-items: center;">
                    <span>📜 Subagent System Prompt</span>
                    <span style="font-size: 10px; color: #94a3b8;">Click to Edit</span>
                  </summary>
                  <div style="margin-top: 6px;">
                    <textarea id="edit-sub-prompt-${sub.id}" rows="4" style="width: 100%; background: #1e293b; border: 1px solid #334155; color: #cbd5e1; font-size: 10px; padding: 6px; border-radius: 4px; outline: none; font-family: var(--font-mono);">${escapeHtml(sub.system_prompt)}</textarea>
                    <div style="display: flex; justify-content: flex-end; margin-top: 4px;">
                      <button onclick="saveSubagentPrompt(${sub.id}, ${currentAgent.id}, '${sub.name}')" style="background: #a855f7; border: none; color: #fff; font-size: 10px; padding: 3px 8px; border-radius: 3px; cursor: pointer;">Save Subagent Prompt</button>
                    </div>
                  </div>
                </details>
              </div>
            `).join("");
          }
        }
      }
    } catch (e) {
      if (mainCardEl) mainCardEl.innerHTML = `<div style="color: #ef4444; font-size: 12px;">Failed to load agent: ${e.message}</div>`;
    }
  }

  window.saveAgentPrompt = async function(agentKey) {
    const txt = document.getElementById(`edit-agent-prompt-${agentKey}`);
    const statusEl = document.getElementById(`save-prompt-status-${agentKey}`);
    if (!txt) return;
    try {
      const respAg = await fetch(`${BASE_URL}/v1/studio/agents`);
      const dataAg = await respAg.json();
      const cur = (dataAg.agents || []).find(a => a.key_name === agentKey);
      if (!cur) return;

      const resp = await fetch(`${BASE_URL}/v1/studio/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key_name: cur.key_name,
          display_name: cur.display_name,
          domain_category: cur.domain_category,
          description: cur.description,
          model_provider: cur.model_provider || "openrouter",
          model_name: cur.model_name || "qwen/qwen-2.5-72b-instruct",
          system_prompt: txt.value.trim()
        })
      });
      const data = await resp.json();
      if (data.status === "success" && statusEl) {
        statusEl.innerHTML = `<span style="color: #10b981;">✓ System prompt updated successfully!</span>`;
        setTimeout(() => { statusEl.innerHTML = ""; }, 3000);
      }
    } catch (e) {
      alert("Failed to save agent prompt: " + e.message);
    }
  };

  window.saveSubagentPrompt = async function(subId, parentAgentId, subName) {
    const txt = document.getElementById(`edit-sub-prompt-${subId}`);
    if (!txt) return;
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/subagents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent_agent_id: parentAgentId,
          name: subName,
          display_name: subName,
          description: subName,
          system_prompt: txt.value.trim()
        })
      });
      const data = await resp.json();
      if (data.status === "success") {
        alert("✓ Subagent prompt updated successfully!");
      }
    } catch (e) {
      alert("Failed to update subagent prompt: " + e.message);
    }
  };

  async function loadStudioSkills() {
    const listEl = document.getElementById("domain-skills-list");
    if (!listEl) return;
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/skills`);
      const data = await resp.json();
      const skills = data.skills || [];

      listEl.innerHTML = skills.map(sk => `
        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; font-size: 13px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="color: #38bdf8;">${escapeHtml(sk.display_name || sk.name)}</strong>
            <div style="display: flex; gap: 6px; align-items: center;">
              <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 10px; padding: 2px 6px;">${escapeHtml(sk.domain_category)}</span>
              <button onclick="deleteSkillRecord('${sk.name}')" style="background: none; border: none; color: #ef4444; font-size: 12px; cursor: pointer;" title="Delete SOP">🗑️</button>
            </div>
          </div>
          <div style="color: #94a3b8; font-size: 11px; margin-top: 4px;">${escapeHtml(sk.description || '')}</div>
          
          <details style="margin-top: 8px; background: #0f172a; border-radius: 4px; padding: 6px 10px;">
            <summary style="font-size: 11px; font-weight: 600; color: #0284c7; cursor: pointer; display: flex; justify-content: space-between;">
              <span>View & Edit Markdown SOP</span>
              <span style="font-size: 10px; color: #94a3b8;">Click to Edit</span>
            </summary>
            <div style="margin-top: 6px;">
              <textarea id="edit-skill-md-${sk.name}" rows="6" style="width: 100%; background: #1e293b; border: 1px solid #334155; color: #cbd5e1; font-size: 10px; padding: 6px; border-radius: 4px; outline: none; font-family: var(--font-mono);">${escapeHtml(sk.content_markdown)}</textarea>
              <div style="display: flex; justify-content: flex-end; margin-top: 4px;">
                <button onclick="saveSkillMarkdown('${sk.name}', '${escapeHtml(sk.domain_category)}')" style="background: #0284c7; border: none; color: #fff; font-size: 10px; padding: 3px 8px; border-radius: 3px; cursor: pointer;">Save SOP Markdown</button>
              </div>
            </div>
          </details>
        </div>
      `).join("");
    } catch (e) {
      listEl.innerHTML = `<div style="color: #ef4444; font-size: 12px;">Failed to load skills: ${e.message}</div>`;
    }
  }

  window.saveSkillMarkdown = async function(skillName, domainCategory) {
    const txt = document.getElementById(`edit-skill-md-${skillName}`);
    if (!txt) return;
    try {
      const resp = await fetch(`${BASE_URL}/v1/studio/skills`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: skillName,
          display_name: skillName,
          domain_category: domainCategory,
          description: skillName,
          content_markdown: txt.value.trim()
        })
      });
      const data = await resp.json();
      if (data.status === "success") {
        alert("✓ SOP Markdown updated successfully!");
      }
    } catch (e) {
      alert("Failed to save SOP: " + e.message);
    }
  };

  window.deleteSkillRecord = async function(skillName) {
    if (!confirm(`Are you sure you want to delete SOP Skill '${skillName}'?`)) return;
    try {
      await fetch(`${BASE_URL}/v1/studio/skills/${skillName}`, { method: "DELETE" });
      await loadStudioSkills();
    } catch (e) {
      alert("Failed to delete SOP skill: " + e.message);
    }
  };

  refreshAuditBtn.addEventListener("click", loadAuditHistory);

  // --- HITL Mode Management & Top Header Sync ---
  function updateModeUI() {
    const isEnforced = currentMode === "enforced";
    if (settingsHitlToggle) settingsHitlToggle.checked = isEnforced;
    if (settingsModeLabel) {
      settingsModeLabel.textContent = isEnforced ? "🛡️ Guardrail Mode (HITL Enforced)" : "⚡ 24/7 Autonomous Mode (HITL OFF)";
      settingsModeLabel.style.color = isEnforced ? "#60a5fa" : "#10b981";
    }
    if (hitlBadgeIcon) hitlBadgeIcon.textContent = isEnforced ? "🛡️" : "⚡";
    if (hitlBadgeText) hitlBadgeText.textContent = isEnforced ? "HITL Enforced" : "Autonomous";
  }

  async function fetchHitlMode() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/settings/hitl_mode`);
      const data = await resp.json();
      currentMode = data.mode || "enforced";
      updateModeUI();
    } catch (e) {
      console.warn("Failed to fetch hitl_mode:", e);
    }
  }

  if (settingsHitlToggle) {
    settingsHitlToggle.addEventListener("change", async () => {
      const newMode = settingsHitlToggle.checked ? "enforced" : "autonomous";
      try {
        const resp = await fetch(`${BASE_URL}/v1/settings/hitl_mode`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: newMode })
        });
        const data = await resp.json();
        currentMode = data.mode;
        updateModeUI();
      } catch (e) {
        alert("Failed to update HITL mode: " + e.message);
      }
    });
  }

  // --- Thread & Conversation Persistence ---
  if (purgeDbBtn) {
    purgeDbBtn.addEventListener("click", async () => {
      const confirmPurge = confirm("⚠️ Are you sure you want to clean up the database?\n\nThis will purge all previous conversational threads, message traces, and historical HITL test records while keeping user accounts and settings.");
      if (!confirmPurge) return;
      try {
        const resp = await fetch(`${BASE_URL}/v1/settings/db/cleanup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ purge_threads: true, purge_hitl: true, keep_days: 0 })
        });
        const data = await resp.json();
        if (data.status === "success") {
          alert(`✅ Database Cleaned Successfully!\n\nDeleted Threads: ${data.stats.deleted_threads}\nDeleted Messages: ${data.stats.deleted_messages}\nDeleted HITL Records: ${data.stats.deleted_hitl_requests}`);
          chatStream.innerHTML = "";
          currentThreadId = null;
          await loadThreads();
          await loadAuditHistory();
        } else {
          alert("❌ Cleanup failed: " + JSON.stringify(data));
        }
      } catch (err) {
        alert("❌ Error cleaning database: " + err.message);
      }
    });
  }

  newChatBtn.addEventListener("click", createNewSession);

  async function createNewSession() {
    const nowStr = new Date().toISOString().replace("T", " ").substring(0, 19);
    const defaultTitle = `Session ${nowStr}`;
    try {
      const resp = await fetch(`${BASE_URL}/v1/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: defaultTitle })
      });
      const data = await resp.json();
      currentThreadId = data.thread_id;
      chatStream.innerHTML = "";
      renderAssistantGreeting();
      await loadThreads();
    } catch (e) {
      console.error("Failed to create new session:", e);
    }
  }

  function renderAssistantGreeting() {
    appendAssistantMessage("Hello! I am your **LangGraph Deep Agent**. Ready to execute infrastructure tasks.", []);
  }

  async function loadThreads(reloadChat = true) {
    try {
      const resp = await fetch(`${BASE_URL}/v1/threads`);
      const data = await resp.json();
      const threads = data.threads || [];
      
      threadsList.innerHTML = "";
      if (threads.length === 0) {
        await createNewSession();
        return;
      }

      if (!currentThreadId && threads.length > 0) {
        currentThreadId = threads[0].thread_id;
      }

      threads.forEach((th) => {
        const item = document.createElement("div");
        item.className = `thread-item ${th.thread_id === currentThreadId ? "active" : ""}`;
        item.innerHTML = `
          <span class="thread-title">💬 ${escapeHtml(th.title)}</span>
          <button class="thread-del-btn" title="Delete Session">🗑️</button>
        `;

        item.querySelector(".thread-title").addEventListener("click", () => switchThread(th.thread_id));
        item.querySelector(".thread-del-btn").addEventListener("click", (e) => {
          e.stopPropagation();
          deleteThread(th.thread_id);
        });

        threadsList.appendChild(item);
      });

      if (reloadChat && currentThreadId) {
        await loadThreadMessages(currentThreadId);
      }
    } catch (e) {
      console.warn("Failed to load threads:", e);
    }
  }

  async function switchThread(threadId) {
    currentThreadId = threadId;
    document.querySelectorAll(".thread-item").forEach((el) => el.classList.remove("active"));
    await loadThreads(true);
  }

  async function deleteThread(threadId) {
    if (!confirm("Delete this conversation session?")) return;
    try {
      await fetch(`${BASE_URL}/v1/threads/${threadId}`, { method: "DELETE" });
      if (currentThreadId === threadId) currentThreadId = null;
      await loadThreads();
    } catch (e) {
      alert("Failed to delete thread: " + e.message);
    }
  }

  async function loadThreadMessages(threadId) {
    try {
      const resp = await fetch(`${BASE_URL}/v1/threads/${threadId}/messages`);
      const data = await resp.json();
      const messages = data.messages || [];
      
      chatStream.innerHTML = "";
      if (messages.length === 0) {
        renderAssistantGreeting();
      } else {
        messages.forEach((msg) => {
          if (msg.role === "user") {
            appendUserMessage(msg.content);
          } else {
            appendAssistantMessage(msg.content, msg.intermediate_steps || []);
          }
        });
      }
    } catch (e) {
      console.warn("Failed to load messages:", e);
    }
  }

  // Quick Action Chips
  document.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        userInput.value = prompt;
        userInput.focus();
      }
    });
  });

  // --- Prompt Submission & Strict Chronological Streaming ---
  inputForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const promptText = userInput.value.trim();
    if (!promptText || sendBtn.disabled) return;

    appendUserMessage(promptText);
    userInput.value = "";
    isCurrentlyStreaming = true;
    setLoadingState(true);

    // Ensure active session thread exists before first submission
    if (!currentThreadId) {
      const nowStr = new Date().toISOString().replace("T", " ").substring(0, 19);
      const defaultTitle = promptText.substring(0, 30) + (promptText.length > 30 ? "..." : "");
      try {
        const resp = await fetch(`${BASE_URL}/v1/threads`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: defaultTitle })
        });
        const data = await resp.json();
        currentThreadId = data.thread_id;
      } catch (e) {
        console.warn("Auto-thread initialization failed:", e);
      }
    }

    // Create live assistant message row with STRICT Chronological Hierarchy (Tools FIRST, Final Response LAST)
    const assistantRow = document.createElement("div");
    assistantRow.className = "message-row assistant";
    assistantRow.innerHTML = `
      <div class="message-author">Deep Agent</div>
      <div class="message-bubble">
        <!-- 1. Chronological Tool & Subagent Traces Appear FIRST -->
        <div class="trace-container"></div>
        <!-- 2. Final Synthesis Text Summary Streams LAST -->
        <div class="final-response-text">
          <span class="stream-text"></span><span class="typing-cursor"></span>
        </div>
      </div>
    `;
    chatStream.appendChild(assistantRow);
    scrollToBottom();

    const traceContainer = assistantRow.querySelector(".trace-container");
    const streamTextEl = assistantRow.querySelector(".stream-text");
    const cursorEl = assistantRow.querySelector(".typing-cursor");

    let fullText = "";
    let capturedSteps = [];

    try {
      const response = await fetch(`${BASE_URL}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${API_KEY}`
        },
        body: JSON.stringify({
          model: "deepagent",
          thread_id: currentThreadId,
          domain: activeDomainKey || "linux_sre",
          stream: true,
          messages: [{ role: "user", content: promptText }]
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          
          const rawData = trimmed.replace(/^data:\s*/, "");
          if (rawData === "[DONE]") break;

          try {
            const parsed = JSON.parse(rawData);
            
            // Event: Status / Reasoning
            if (parsed.event === "status") {
              cursorEl.style.display = "inline-block";
            }
            
            // Event: Intermediate Tool Step / Subagent Delegation (Appended Chronologically)
            else if (parsed.event === "step") {
              capturedSteps.push(parsed.step);
              renderSingleTraceCard(traceContainer, parsed.step);
              scrollToBottom();
            }

            // Event: Live Tool Output Update (Populate trace code dynamically)
            else if (parsed.event === "tool_result") {
              if (capturedSteps.length > 0) {
                capturedSteps[capturedSteps.length - 1].tool_output = parsed.tool_output;
              }
              const stepId = parsed.step_id;
              let targetCodeEl = stepId ? traceContainer.querySelector(`#trace-step-${stepId} .trace-code`) : null;
              if (!targetCodeEl) {
                const allCodes = traceContainer.querySelectorAll(".trace-card .trace-code, .fs-card .trace-code");
                targetCodeEl = allCodes.length > 0 ? allCodes[allCodes.length - 1] : null;
              }
              if (targetCodeEl && parsed.tool_output) {
                const currentTxt = targetCodeEl.textContent;
                if (currentTxt.includes("No output recorded")) {
                  targetCodeEl.textContent = currentTxt.replace("No output recorded", parsed.tool_output);
                } else {
                  targetCodeEl.textContent += `\nOutput:\n${parsed.tool_output}`;
                }
              }
            }

            // Event: Final Response Token Stream (Rendered Below Tools)
            else if (parsed.event === "token") {
              const tokenText = parsed.token !== undefined ? parsed.token : (parsed.chunk !== undefined ? parsed.chunk : "");
              if (tokenText) {
                fullText += tokenText;
                streamTextEl.innerHTML = formatMarkdown(fullText);
                scrollToBottom();
              }
            }

            // Event: Stream Completion
            else if (parsed.event === "done") {
              if (parsed.thread_id) currentThreadId = parsed.thread_id;
              const finalResp = parsed.response_text || parsed.content || "";
              if (finalResp && !fullText) {
                fullText = finalResp;
                streamTextEl.innerHTML = formatMarkdown(fullText);
              }
            }
          } catch (err) {
            console.warn("Error parsing SSE chunk:", err);
          }
        }
      }

      cursorEl.style.display = "none";
      await loadThreads(false);
    } catch (err) {
      cursorEl.style.display = "none";
      streamTextEl.innerHTML = `<span style="color: #ef4444;">⚠️ Error communicating with Deep Agent API: ${escapeHtml(err.message)}</span>`;
    } finally {
      isCurrentlyStreaming = false;
      setLoadingState(false);
    }
  });

  function appendUserMessage(text) {
    const msgRow = document.createElement("div");
    msgRow.className = "message-row user";
    msgRow.innerHTML = `
      <div class="message-author">You</div>
      <div class="message-bubble">${escapeHtml(text)}</div>
    `;
    chatStream.appendChild(msgRow);
    scrollToBottom();
  }

  // Strict Chronological History Rendering (Tools FIRST, Synthesis LAST)
  function appendAssistantMessage(text, steps) {
    const msgRow = document.createElement("div");
    msgRow.className = "message-row assistant";

    let stepsHtml = "";
    if (steps && steps.length > 0) {
      stepsHtml = `<div class="trace-container">`;
      steps.forEach((step) => {
        stepsHtml += generateTraceCardHtml(step);
      });
      stepsHtml += `</div>`;
    }

    msgRow.innerHTML = `
      <div class="message-author">Deep Agent</div>
      <div class="message-bubble">
        <!-- 1. Chronological Tool Execution Timeline FIRST -->
        ${stepsHtml}
        <!-- 2. Final Synthesis Text Summary LAST -->
        <div class="final-response-text">${formatMarkdown(text)}</div>
      </div>
    `;
    chatStream.appendChild(msgRow);
    scrollToBottom();
  }

  function renderSingleTraceCard(container, step) {
    if (step.hitl_approval && step.hitl_approval.id) {
      const tempCard = document.getElementById(`inline-hitl-${step.hitl_approval.id}`);
      if (tempCard) {
        tempCard.remove();
      }
    }

    // 1. Handle Planning Card In-Place Update (write_todos)
    if (step.step_type === "planning" || step.tool_name === "write_todos") {
      let planCard = container.querySelector(".planning-card");
      if (planCard) {
        planCard.querySelector(".todo-list").innerHTML = renderTodoListHtml(step.todos || step.tool_args?.todos || []);
        return;
      }
    }

    const temp = document.createElement("div");
    temp.innerHTML = generateTraceCardHtml(step);
    container.appendChild(temp.firstElementChild);
  }

  function renderTodoListHtml(todos) {
    if (!todos || todos.length === 0) {
      return `<div style="color: #94a3b8; font-size: 12px;"><em>Initializing operational checklist...</em></div>`;
    }
    return todos.map((t, idx) => {
      const status = t.status || "pending";
      let icon = "⏳";
      if (status === "in_progress") icon = `<span class="pulse-icon">🔄</span>`;
      else if (status === "completed") icon = "✅";
      else if (status === "failed") icon = "❌";

      const text = t.task || t.title || t.content || `Task #${t.id || idx + 1}`;
      return `
        <div class="todo-item ${status}">
          <span class="todo-status-icon">${icon}</span>
          <span class="todo-text">${escapeHtml(text)}</span>
        </div>
      `;
    }).join("");
  }

  function generateTraceCardHtml(step) {
    // 1. Intercept Planning Tool: write_todos
    if (step.step_type === "planning" || step.tool_name === "write_todos") {
      const todos = step.todos || step.tool_args?.todos || [];
      return `
        <div>
          <div class="planning-card">
            <div class="planning-header">
              <span>📋</span>
              <strong>Live Execution Plan (TODOs)</strong>
              <span class="trace-type-badge type-planning" style="margin-left: auto;">PLANNING</span>
            </div>
            <div class="todo-list">
              ${renderTodoListHtml(todos)}
            </div>
          </div>
        </div>
      `;
    }

    // 2. Intercept Filesystem Tools: read_file, ls, write_file, edit_file
    if (step.step_type === "filesystem" || ["read_file", "write_file", "edit_file", "ls", "list_dir"].includes(step.tool_name)) {
      const filePath = step.file_path || step.tool_args?.path || step.tool_args?.file_path || step.tool_args?.target_file || "skills/";
      return `
        <div>
          <div class="fs-card">
            <div class="fs-header">
              <span class="trace-type-badge type-filesystem">FILESYSTEM</span>
              <strong>${escapeHtml(step.tool_name || 'read_file')}</strong>: <code>${escapeHtml(filePath)}</code>
            </div>
            <div class="trace-body">
              <pre class="trace-code">${escapeHtml(step.tool_output || 'SOP Skill Loaded Successfully.')}</pre>
            </div>
          </div>
        </div>
      `;
    }

    const isSubagent = step.step_type === "subagent_delegation";
    const badgeClass = isSubagent ? "type-subagent" : "type-mcp";
    const badgeLabel = isSubagent ? `🤖 SUBAGENT: ${step.target_subagent || 'AGENT'}` : `🛠️ TOOL: ${step.tool_name}`;
    
    let headerTitle = step.tool_name;
    if (isSubagent) {
      headerTitle = `Delegation to '${step.target_subagent}'`;
    }

    let hitlCardHtml = "";
    if (step.hitl_approval) {
      const hitl = step.hitl_approval;
      const isGranted = hitl.status === "GRANTED" || hitl.status === "AUTONOMOUS_GRANTED";
      hitlCardHtml = `
        <div class="inline-hitl-card ${isGranted ? 'resolved-granted' : 'resolved-denied'}">
          <div class="inline-hitl-header">
            <h4><span>🛡️</span> Human Authorization Record (Request #${hitl.id})</h4>
            <span class="status-badge ${isGranted ? 'status-granted' : 'status-denied'}">${hitl.status}</span>
          </div>
          <div class="inline-hitl-body">
            <div><strong>Authorized Action:</strong> <code>${escapeHtml(hitl.action_name)}</code></div>
            <div><strong>Parameters:</strong> <code>${escapeHtml(hitl.action_summary)}</code></div>
            <div style="font-size: 11px; color: #94a3b8;">Timestamp: ${hitl.resolved_at || hitl.requested_at || 'Recorded'}</div>
          </div>
        </div>
      `;
    }

    let bodyContent = "";
    if (step.subagent_task_prompt) {
      bodyContent += `Task: ${escapeHtml(step.subagent_task_prompt)}\n\n`;
    }
    if (step.tool_args && Object.keys(step.tool_args).length > 0) {
      bodyContent += `Arguments: ${JSON.stringify(step.tool_args, null, 2)}\n\n`;
    }
    bodyContent += `Output:\n${escapeHtml(step.tool_output || 'No output recorded')}`;

    const stepId = step.step_id || `step_${Date.now()}`;

    return `
      <div id="trace-step-container-${stepId}">
        ${hitlCardHtml}
        <div class="trace-card" id="trace-step-${stepId}">
          <div class="trace-header" onclick="this.parentElement.querySelector('.trace-body').classList.toggle('hidden')">
            <div class="trace-title">
              <span class="trace-type-badge ${badgeClass}">${badgeLabel}</span>
              <span>${headerTitle}</span>
            </div>
            <span style="font-size: 11px; color: #94a3b8;">Click to toggle details ▼</span>
          </div>
          <div class="trace-body">
            <pre class="trace-code">${bodyContent}</pre>
          </div>
        </div>
      </div>
    `;
  }

  // --- In-Pane Inline HITL Approval Polling & Resolution ---
  let isCurrentlyStreaming = false;

  function startPendingHitlPolling() {
    setInterval(async () => {
      // In enforced mode, we MUST poll to detect and render pending HITL approval requests
      if (currentMode !== "enforced") return;
      try {
        const resp = await fetch(`${BASE_URL}/v1/hitl/pending`);
        const data = await resp.json();
        const pending = data.pending || [];

        if (pending.length > 0) {
          pending.forEach((req) => {
            renderPendingInlineHitlCard(req);
          });
        }
      } catch (e) {
        // quiet poll
      }
    }, 1500);
  }

  function renderPendingInlineHitlCard(req) {
    const existing = document.getElementById(`inline-hitl-${req.id}`);
    if (existing) return;

    let targetContainer = chatStream.querySelector(".message-row.assistant:last-child .message-bubble .trace-container");
    if (!targetContainer) {
      targetContainer = chatStream;
    }

    const hitlCard = document.createElement("div");
    hitlCard.id = `inline-hitl-${req.id}`;
    hitlCard.className = "inline-hitl-card";
    hitlCard.innerHTML = `
      <div class="inline-hitl-header">
        <h4><span>🛡️</span> Human Authorization Required (Request #${req.id})</h4>
        <span class="status-badge status-pending">PENDING</span>
      </div>
      <div class="inline-hitl-body">
        <div><strong>High-Risk Action:</strong> <code>${escapeHtml(req.action_name)}</code></div>
        <div><strong>Parameters:</strong> <code>${escapeHtml(req.action_summary)}</code></div>
      </div>
      <div class="inline-hitl-actions">
        <button class="btn-inline-approve" onclick="resolveInlineHitl(${req.id}, 'GRANTED')">Approve & Execute (GRANT)</button>
        <button class="btn-inline-deny" onclick="resolveInlineHitl(${req.id}, 'DENIED')">Deny & Abort (DENY)</button>
      </div>
    `;

    // Place the HITL card directly into the container
    targetContainer.appendChild(hitlCard);
    scrollToBottom();
  }

  window.resolveInlineHitl = async function(requestId, decision) {
    try {
      await fetch(`${BASE_URL}/v1/hitl/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: requestId,
          decision: decision
        })
      });

      const card = document.getElementById(`inline-hitl-${requestId}`);
      if (card) {
        const isGranted = decision === "GRANTED";
        card.className = `inline-hitl-card ${isGranted ? 'resolved-granted' : 'resolved-denied'}`;
        card.querySelector(".inline-hitl-actions").innerHTML = `
          <span class="inline-resolved-badge ${isGranted ? 'status-granted' : 'status-denied'}">
            ${isGranted ? '✓ Action Authorized by Operator' : '✗ Action Denied by Operator'}
          </span>
        `;
        card.querySelector(".inline-hitl-header .status-badge").className = `status-badge ${isGranted ? 'status-granted' : 'status-denied'}`;
        card.querySelector(".inline-hitl-header .status-badge").textContent = decision;
      }
    } catch (e) {
      alert("Error resolving HITL request: " + e.message);
    }
  };

  // --- Session Export & Reporting ---
  exportReportBtn.addEventListener("click", async () => {
    if (!currentThreadId) {
      alert("Please select or start a session first.");
      return;
    }
    try {
      const resp = await fetch(`${BASE_URL}/v1/threads/${currentThreadId}/export`);
      const data = await resp.json();
      currentExportMarkdown = data.markdown || "No report content generated.";
      exportPreview.textContent = currentExportMarkdown;
      exportModal.style.display = "flex";
    } catch (e) {
      alert("Failed to export session: " + e.message);
    }
  });

  closeExportModalBtn.addEventListener("click", () => {
    exportModal.style.display = "none";
  });

  downloadMdBtn.addEventListener("click", () => {
    const blob = new Blob([currentExportMarkdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `incident_report_${currentThreadId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  });

  printReportBtn.addEventListener("click", () => {
    const printWindow = window.open("", "_blank");
    printWindow.document.write(`
      <html>
        <head>
          <title>Deep Agent SRE Report</title>
          <style>
            body { font-family: -apple-system, sans-serif; padding: 40px; color: #1e293b; line-height: 1.6; }
            pre { background: #f1f5f9; padding: 12px; border-radius: 6px; overflow-x: auto; }
            code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }
            h1, h2, h3 { color: #0f172a; }
            hr { border: none; border-top: 1px solid #cbd5e1; margin: 20px 0; }
          </style>
        </head>
        <body>
          <pre style="white-space: pre-wrap; font-family: inherit;">${escapeHtml(currentExportMarkdown)}</pre>
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  });

  // --- Audit History View ---
  async function loadAuditHistory() {
    try {
      const resp = await fetch(`${BASE_URL}/v1/hitl/history`);
      const data = await resp.json();
      const history = data.history || [];

      auditTableBody.innerHTML = "";
      if (history.length === 0) {
        auditTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94a3b8;">No actions recorded yet.</td></tr>`;
        return;
      }

      history.forEach((row) => {
        const tr = document.createElement("tr");
        let badgeClass = "status-pending";
        if (row.status === "GRANTED") badgeClass = "status-granted";
        else if (row.status === "AUTONOMOUS_GRANTED") badgeClass = "status-autonomous";
        else if (row.status === "DENIED") badgeClass = "status-denied";

        tr.innerHTML = `
          <td>#${row.id}</td>
          <td><strong>${escapeHtml(row.action_name)}</strong></td>
          <td style="font-family: var(--font-mono); font-size: 11px; max-width: 300px; word-break: break-all;">${escapeHtml(row.action_summary)}</td>
          <td><span class="status-badge ${badgeClass}">${row.status}</span></td>
          <td style="font-size: 11px; color: #94a3b8;">${row.requested_at || '-'}</td>
          <td style="font-size: 11px; color: #94a3b8;">${row.resolved_at || '-'}</td>
        `;
        auditTableBody.appendChild(tr);
      });
    } catch (e) {
      console.warn("Failed to load audit history:", e);
    }
  }

  // --- SRE Incident Post-Mortem Export & Report Generation ---
  if (exportReportBtn) {
    exportReportBtn.addEventListener("click", async () => {
      if (!currentThreadId) {
        alert("No active session selected to export.");
        return;
      }

      try {
        const [msgResp, hitlResp] = await Promise.all([
          fetch(`${BASE_URL}/v1/threads/${currentThreadId}/messages`),
          fetch(`${BASE_URL}/v1/hitl/history`)
        ]);
        const msgData = await msgResp.json();
        const hitlData = await hitlResp.json();
        const messages = msgData.messages || [];
        const hitls = (hitlData.history || []).filter(h => h.thread_id === currentThreadId || !h.thread_id);

        let reportMd = `# 🛡️ SRE Incident & Execution Post-Mortem Report\n\n`;
        reportMd += `**Session ID:** \`${currentThreadId}\`  \n`;
        reportMd += `**Generated At:** \`${new Date().toISOString()}\`  \n`;
        reportMd += `**Active Domain:** \`${activeDomainKey || 'linux_sre'}\`  \n`;
        reportMd += `**Governance Mode:** \`${currentMode.toUpperCase()}\`  \n\n`;
        reportMd += `---\n\n`;

        reportMd += `## 1. Executive Summary & Timeline\n\n`;
        messages.forEach((m, idx) => {
          const role = m.role === "user" ? "👤 Operator Command" : "🤖 Deep Agent Execution";
          reportMd += `### ${idx + 1}. ${role}\n\n${m.content}\n\n`;
          if (m.intermediate_steps && m.intermediate_steps.length > 0) {
            reportMd += `#### Intermediate Tool Steps (${m.intermediate_steps.length} Steps):\n`;
            m.intermediate_steps.forEach((step, sIdx) => {
              reportMd += `- **Step ${sIdx + 1}**: \`${step.tool_name || step.step_type}\`\n`;
              if (step.tool_args) reportMd += `  - Arguments: \`${JSON.stringify(step.tool_args)}\`\n`;
              if (step.tool_output) reportMd += `  - Output: \`${String(step.tool_output).substring(0, 150)}...\`\n`;
            });
            reportMd += `\n`;
          }
        });

        reportMd += `## 2. Human-In-The-Loop (HITL) Authorization Log\n\n`;
        if (hitls.length === 0) {
          reportMd += `*No high-risk destructive actions required manual operator intervention during this session.*\n\n`;
        } else {
          reportMd += `| Request ID | Action Name | Parameters | Decision | Requested At | Resolved At |\n`;
          reportMd += `| :--- | :--- | :--- | :--- | :--- | :--- |\n`;
          hitls.forEach((h) => {
            reportMd += `| #${h.id} | **${h.action_name}** | \`${h.action_summary}\` | **${h.status}** | ${h.requested_at || '-'} | ${h.resolved_at || '-'} |\n`;
          });
          reportMd += `\n`;
        }

        reportMd += `---\n*Report digitally signed and exported from Deep Agent Autonomous SRE Platform.*\n`;

        currentExportMarkdown = reportMd;
        if (exportPreview) exportPreview.innerHTML = formatMarkdown(reportMd);
        if (exportModal) exportModal.style.display = "flex";
      } catch (err) {
        alert("Failed to compile incident report: " + err.message);
      }
    });
  }

  if (closeExportModalBtn && exportModal) {
    closeExportModalBtn.addEventListener("click", () => {
      exportModal.style.display = "none";
    });
  }

  if (downloadMdBtn) {
    downloadMdBtn.addEventListener("click", () => {
      if (!currentExportMarkdown) return;
      const blob = new Blob([currentExportMarkdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `SRE_Incident_Report_${currentThreadId || 'export'}_${Date.now()}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  if (printReportBtn) {
    printReportBtn.addEventListener("click", () => {
      window.print();
    });
  }

  function setLoadingState(isLoading) {
    sendBtn.disabled = isLoading;
    if (isLoading) {
      loadingIndicator.style.display = "flex";
      sendBtn.innerHTML = "Streaming...";
    } else {
      loadingIndicator.style.display = "none";
      sendBtn.innerHTML = "Send Prompt ↵";
    }
  }

  function scrollToBottom() {
    chatStream.scrollTop = chatStream.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatMarkdown(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/```([\s\S]*?)```/g, "<pre class='trace-code'>$1</pre>");
    safe = safe.replace(/`([^`]+)`/g, "<code style='background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8;'>$1</code>");
    safe = safe.replace(/\n/g, "<br/>");
    return safe;
  }
});
