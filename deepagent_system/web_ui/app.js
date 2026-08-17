// LangGraph Deep Agent Dashboard Client
const API_HOST = window.location.hostname || "localhost";
const API_URL = `${window.location.protocol}//${API_HOST}:8642/v1/chat/completions`;
const HITL_PORTAL_URL = `${window.location.protocol}//${API_HOST}:5001`;
const API_KEY = "hermes-api-secret";

document.addEventListener("DOMContentLoaded", () => {
  const chatStream = document.getElementById("chat-messages");
  const inputForm = document.getElementById("prompt-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const loadingIndicator = document.getElementById("loading-indicator");
  const hitlBanner = document.getElementById("hitl-alert-banner");
  const hitlBannerText = document.getElementById("hitl-banner-text");

  // Quick Action Chips Click Handlers
  document.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        userInput.value = prompt;
        userInput.focus();
      }
    });
  });

  // Handle Prompt Submission
  inputForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const promptText = userInput.value.trim();
    if (!promptText || sendBtn.disabled) return;

    // Append User Message to Chat Stream
    appendUserMessage(promptText);
    userInput.value = "";
    setLoadingState(true);
    hideHitlBanner();

    try {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${API_KEY}`
        },
        body: JSON.stringify({
          model: "deepagent",
          messages: [{ role: "user", content: promptText }]
        })
      });

      if (!resp.ok) {
        throw new Error(`API returned HTTP ${resp.status}: ${resp.statusText}`);
      }

      const data = await resp.json();
      const choice = data?.choices?.[0];
      const assistantText = choice?.message?.content || "Operation completed successfully.";
      const intermediateSteps = data?.intermediate_steps || [];

      // Check if HITL security block was encountered
      if (assistantText.includes("CRITICAL SECURITY VIOLATION") || assistantText.includes("HITL")) {
        showHitlBanner("High-risk infrastructure action intercepted. Human authorization required.");
      }

      // Append Assistant Message with Tool & Subagent traces
      appendAssistantMessage(assistantText, intermediateSteps);

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
      steps.forEach((step, idx) => {
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

  function showHitlBanner(text) {
    hitlBannerText.textContent = text;
    hitlBanner.style.display = "flex";
  }

  function hideHitlBanner() {
    hitlBanner.style.display = "none";
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
    // Bold
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Code blocks
    safe = safe.replace(/```([\s\S]*?)```/g, "<pre class='trace-code'>$1</pre>");
    // Inline code
    safe = safe.replace(/`([^`]+)`/g, "<code style='background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8;'>$1</code>");
    // Line breaks
    safe = safe.replace(/\n/g, "<br/>");
    return safe;
  }
});
