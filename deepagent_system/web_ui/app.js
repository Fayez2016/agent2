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
  const hitlModeToggle = document.getElementById("hitl-mode-toggle");
  const modeStatusText = document.getElementById("mode-status-text");
  
  // Views
  const chatView = document.getElementById("chat-view");
  const auditView = document.getElementById("audit-view");
  const tabChat = document.getElementById("tab-chat");
  const tabAudit = document.getElementById("tab-audit");
  const auditTableBody = document.getElementById("audit-table-body");
  const refreshAuditBtn = document.getElementById("refresh-audit-btn");

  // Export Modal
  const exportModal = document.getElementById("export-modal");
  const exportPreview = document.getElementById("export-preview");
  const closeExportModalBtn = document.getElementById("close-export-modal");
  const downloadMdBtn = document.getElementById("download-md-btn");
  const printReportBtn = document.getElementById("print-report-btn");

  let currentExportMarkdown = "";

  initApp();

  async function initApp() {
    await fetchHitlMode();
    await loadThreads();
    startPendingHitlPolling();
  }

  // --- View Switcher ---
  tabChat.addEventListener("click", () => {
    tabChat.classList.add("active");
    tabAudit.classList.remove("active");
    chatView.style.display = "flex";
    auditView.style.display = "none";
  });

  tabAudit.addEventListener("click", async () => {
    tabAudit.classList.add("active");
    tabChat.classList.remove("active");
    chatView.style.display = "none";
    auditView.style.display = "block";
    await loadAuditHistory();
  });

  refreshAuditBtn.addEventListener("click", loadAuditHistory);

  // --- HITL Mode Toggle ---
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

  hitlModeToggle.addEventListener("change", async () => {
    const newMode = hitlModeToggle.checked ? "enforced" : "autonomous";
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
      hitlModeToggle.checked = currentMode === "enforced";
    }
  });

  function updateModeUI() {
    hitlModeToggle.checked = currentMode === "enforced";
    if (currentMode === "enforced") {
      modeStatusText.textContent = "🛡️ Guardrail Mode (HITL ON)";
      modeStatusText.style.color = "#10b981";
    } else {
      modeStatusText.textContent = "⚡ 24/7 Autonomous (HITL OFF)";
      modeStatusText.style.color = "#a855f7";
    }
  }

  // --- Thread & Conversation Persistence ---
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
    setLoadingState(true);

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

            // Event: Final Response Token Stream (Rendered Below Tools)
            else if (parsed.event === "token") {
              fullText += parsed.chunk;
              streamTextEl.innerHTML = formatMarkdown(fullText);
              scrollToBottom();
            }

            // Event: Stream Completion
            else if (parsed.event === "done") {
              if (parsed.thread_id) currentThreadId = parsed.thread_id;
              if (parsed.content && !fullText) {
                fullText = parsed.content;
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
    const temp = document.createElement("div");
    temp.innerHTML = generateTraceCardHtml(step);
    container.appendChild(temp.firstElementChild);
  }

  function generateTraceCardHtml(step) {
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

    return `
      <div>
        ${hitlCardHtml}
        <div class="trace-card">
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
  function startPendingHitlPolling() {
    setInterval(async () => {
      if (currentMode !== "enforced") return;
      try {
        const resp = await fetch(`${BASE_URL}/v1/hitl/pending`);
        const data = await resp.json();
        const pending = data.pending || [];

        if (pending.length > 0) {
          const req = pending[0];
          activePendingRequestId = req.id;
          renderPendingInlineHitlCard(req);
        }
      } catch (e) {
        // quiet poll
      }
    }, 2000);
  }

  function renderPendingInlineHitlCard(req) {
    const existing = document.getElementById(`inline-hitl-${req.id}`);
    if (existing) return;

    const lastAssistantRow = chatStream.querySelector(".message-row.assistant:last-child .message-bubble .trace-container");
    if (!lastAssistantRow) return;

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

    lastAssistantRow.appendChild(hitlCard);
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
