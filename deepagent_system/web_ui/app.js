// LangGraph Deep Agent Dashboard Client with In-App HITL, 24/7 Mode, & Persistent Threads
const API_HOST = window.location.hostname || "localhost";
const BASE_URL = `${window.location.protocol}//${API_HOST}:8642`;
const API_KEY = "hermes-api-secret";

let currentThreadId = null;
let currentMode = "enforced";

document.addEventListener("DOMContentLoaded", () => {
  // DOM References
  const chatStream = document.getElementById("chat-messages");
  const inputForm = document.getElementById("prompt-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const loadingIndicator = document.getElementById("loading-indicator");
  const threadsList = document.getElementById("threads-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const hitlModeToggle = document.getElementById("hitl-mode-toggle");
  const modeStatusText = document.getElementById("mode-status-text");
  
  // Views
  const chatView = document.getElementById("chat-view");
  const auditView = document.getElementById("audit-view");
  const tabChat = document.getElementById("tab-chat");
  const tabAudit = document.getElementById("tab-audit");
  const auditTableBody = document.getElementById("audit-table-body");
  const refreshAuditBtn = document.getElementById("refresh-audit-btn");

  // In-App Approval Modal
  const approvalModal = document.getElementById("approval-modal");
  const modalActionName = document.getElementById("modal-action-name");
  const modalActionSummary = document.getElementById("modal-action-summary");
  const modalRequestId = document.getElementById("modal-request-id");
  const btnModalApprove = document.getElementById("btn-modal-approve");
  const btnModalDeny = document.getElementById("btn-modal-deny");

  let activePendingRequestId = null;

  // Initialize
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
    try {
      const resp = await fetch(`${BASE_URL}/v1/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Conversation" })
      });
      const data = await resp.json();
      currentThreadId = data.thread_id;
      chatStream.innerHTML = "";
      appendAssistantMessage("Hello! I am your **LangGraph Deep Agent**. Ready to execute infrastructure tasks.", []);
      await loadThreads();
    } catch (e) {
      console.error("Failed to create new session:", e);
    }
  }

  async function loadThreads() {
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

      if (currentThreadId) {
        await loadThreadMessages(currentThreadId);
      }
    } catch (e) {
      console.warn("Failed to load threads:", e);
    }
  }

  async function switchThread(threadId) {
    currentThreadId = threadId;
    document.querySelectorAll(".thread-item").forEach((el) => el.classList.remove("active"));
    await loadThreads();
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
        appendAssistantMessage("Hello! I am your **LangGraph Deep Agent**. Ready to execute infrastructure tasks.", []);
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

  // Prompt Submission
  inputForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const promptText = userInput.value.trim();
    if (!promptText || sendBtn.disabled) return;

    appendUserMessage(promptText);
    userInput.value = "";
    setLoadingState(true);

    try {
      const resp = await fetch(`${BASE_URL}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${API_KEY}`
        },
        body: JSON.stringify({
          model: "deepagent",
          thread_id: currentThreadId,
          messages: [{ role: "user", content: promptText }]
        })
      });

      const data = await resp.json();
      const choice = data?.choices?.[0];
      const assistantText = choice?.message?.content || "Operation completed.";
      const intermediateSteps = data?.intermediate_steps || [];

      appendAssistantMessage(assistantText, intermediateSteps);
      await loadThreads(); // Refresh thread titles in sidebar
    } catch (err) {
      appendAssistantMessage(`⚠️ Error communicating with Deep Agent API: ${err.message}`, []);
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

  function appendAssistantMessage(text, steps) {
    const msgRow = document.createElement("div");
    msgRow.className = "message-row assistant";

    let stepsHtml = "";
    if (steps && steps.length > 0) {
      stepsHtml = `<div class="trace-container">`;
      steps.forEach((step) => {
        const isSubagent = step.step_type === "subagent_delegation";
        const badgeClass = isSubagent ? "type-subagent" : "type-mcp";
        const badgeLabel = isSubagent ? `🤖 SUBAGENT: ${step.target_subagent || 'AGENT'}` : `🛠️ TOOL: ${step.tool_name}`;
        
        let headerTitle = step.tool_name;
        if (isSubagent) {
          headerTitle = `Delegation to '${step.target_subagent}'`;
        }

        let bodyContent = "";
        if (step.subagent_task_prompt) {
          bodyContent += `Task: ${escapeHtml(step.subagent_task_prompt)}\n\n`;
        }
        if (step.tool_args && Object.keys(step.tool_args).length > 0) {
          bodyContent += `Arguments: ${JSON.stringify(step.tool_args, null, 2)}\n\n`;
        }
        bodyContent += `Output:\n${escapeHtml(step.tool_output || 'No output recorded')}`;

        stepsHtml += `
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
        `;
      });
      stepsHtml += `</div>`;
    }

    msgRow.innerHTML = `
      <div class="message-author">Deep Agent</div>
      <div class="message-bubble">
        <div>${formatMarkdown(text)}</div>
        ${stepsHtml}
      </div>
    `;
    chatStream.appendChild(msgRow);
    scrollToBottom();
  }

  // --- In-App HITL Approval Polling & Resolution ---
  function startPendingHitlPolling() {
    setInterval(async () => {
      if (currentMode !== "enforced") {
        approvalModal.style.display = "none";
        return;
      }
      try {
        const resp = await fetch(`${BASE_URL}/v1/hitl/pending`);
        const data = await resp.json();
        const pending = data.pending || [];

        if (pending.length > 0) {
          const req = pending[0];
          activePendingRequestId = req.id;
          modalRequestId.textContent = `#${req.id}`;
          modalActionName.textContent = req.action_name;
          modalActionSummary.textContent = req.action_summary;
          approvalModal.style.display = "flex";
        } else {
          approvalModal.style.display = "none";
          activePendingRequestId = null;
        }
      } catch (e) {
        // quiet poll
      }
    }, 2000);
  }

  btnModalApprove.addEventListener("click", () => resolvePendingRequest("GRANTED"));
  btnModalDeny.addEventListener("click", () => resolvePendingRequest("DENIED"));

  async function resolvePendingRequest(decision) {
    if (!activePendingRequestId) return;
    try {
      await fetch(`${BASE_URL}/v1/hitl/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: activePendingRequestId,
          decision: decision
        })
      });
      approvalModal.style.display = "none";
      activePendingRequestId = null;
    } catch (e) {
      alert("Error resolving HITL request: " + e.message);
    }
  }

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
      sendBtn.innerHTML = "Processing...";
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
