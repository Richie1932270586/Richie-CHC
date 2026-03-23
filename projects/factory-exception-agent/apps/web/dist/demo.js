const STORAGE_KEY = "factory-exception-agent-threads-v3";
const API_BASE = (new URLSearchParams(window.location.search).get("api") || window.FACTORY_AGENT_API_BASE || "")
  .trim()
  .replace(/\/$/, "");

const defaultAssistantMeta = {
  message: "",
  conclusion: "",
  issue_type: "",
  risk_level: "low",
  evidence: [],
  actions: [],
  confirmations: [],
  tool_results: [],
  trace: {},
};

const state = {
  threads: [],
  activeThreadId: "",
  activeTab: "chat",
  documents: [],
  imports: [],
  loading: false,
  importing: false,
  abortController: null,
  runtimeConfig: null,
  toastTimer: null,
};

function buildApiUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

function getApiTargetLabel() {
  return API_BASE || "same-origin";
}

function formatRequestError(error, fallback) {
  if (error?.name === "AbortError") {
    return error.message || fallback;
  }
  const message = String(error?.message || "").trim();
  if (!message || message === "Failed to fetch") {
    return `${fallback}，请确认 Agent 后端已启动：${getApiTargetLabel()}`;
  }
  return message;
}

const elements = {
  newThreadButton: document.querySelector("#newThreadButton"),
  threadList: document.querySelector("#threadList"),
  sourceDirInput: document.querySelector("#sourceDirInput"),
  replaceExisting: document.querySelector("#replaceExisting"),
  importButton: document.querySelector("#importButton"),
  refreshDocsButton: document.querySelector("#refreshDocsButton"),
  docCountTag: document.querySelector("#docCountTag"),
  latestImportBox: document.querySelector("#latestImportBox"),
  documentList: document.querySelector("#documentList"),
  agentMode: document.querySelector("#agentMode"),
  ragProfile: document.querySelector("#ragProfile"),
  ragEnabled: document.querySelector("#ragEnabled"),
  modeTag: document.querySelector("#modeTag"),
  activeThreadTitle: document.querySelector("#activeThreadTitle"),
  activeThreadMeta: document.querySelector("#activeThreadMeta"),
  activeDocTag: document.querySelector("#activeDocTag"),
  threadStatsTag: document.querySelector("#threadStatsTag"),
  runtimeBanner: document.querySelector("#runtimeBanner"),
  runtimeTitle: document.querySelector("#runtimeTitle"),
  runtimeDescription: document.querySelector("#runtimeDescription"),
  selectedModeTag: document.querySelector("#selectedModeTag"),
  selectedIssueTag: document.querySelector("#selectedIssueTag"),
  selectedRiskTag: document.querySelector("#selectedRiskTag"),
  selectedStepTag: document.querySelector("#selectedStepTag"),
  viewTabs: document.querySelector("#viewTabs"),
  panelChat: document.querySelector("#panel-chat"),
  panelEvidence: document.querySelector("#panel-evidence"),
  panelActions: document.querySelector("#panel-actions"),
  panelTools: document.querySelector("#panel-tools"),
  messageList: document.querySelector("#messageList"),
  summaryBox: document.querySelector("#summaryBox"),
  evidenceCount: document.querySelector("#evidenceCount"),
  evidenceList: document.querySelector("#evidenceList"),
  actionCount: document.querySelector("#actionCount"),
  actionList: document.querySelector("#actionList"),
  confirmationBox: document.querySelector("#confirmationBox"),
  toolList: document.querySelector("#toolList"),
  messageInput: document.querySelector("#messageInput"),
  composerHint: document.querySelector("#composerHint"),
  stopButton: document.querySelector("#stopButton"),
  submitButton: document.querySelector("#submitButton"),
  toastBox: document.querySelector("#toastBox"),
};

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function createThread(title = "新会话") {
  const now = new Date().toISOString();
  return {
    id: uid("thread"),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
    selectedAssistantId: "",
  };
}

function loadThreadState() {
  try {
    const payload = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    state.threads = Array.isArray(payload.threads) ? payload.threads : [];
    state.activeThreadId = payload.activeThreadId || "";
    state.activeTab = payload.activeTab || "chat";
  } catch {
    state.threads = [];
    state.activeThreadId = "";
    state.activeTab = "chat";
  }
  if (!state.threads.length) {
    const initial = createThread();
    state.threads = [initial];
    state.activeThreadId = initial.id;
  }
  if (!state.threads.some((thread) => thread.id === state.activeThreadId)) {
    state.activeThreadId = state.threads[0].id;
  }
}

function persistThreadState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      threads: state.threads,
      activeThreadId: state.activeThreadId,
      activeTab: state.activeTab,
    }),
  );
}

function getActiveThread() {
  return state.threads.find((thread) => thread.id === state.activeThreadId) || state.threads[0];
}

function getLastMessage(thread, role) {
  if (!thread) return null;
  for (let index = thread.messages.length - 1; index >= 0; index -= 1) {
    const current = thread.messages[index];
    if (!role || current.role === role) {
      return current;
    }
  }
  return null;
}

function getSelectedAssistant(thread) {
  if (!thread) return null;
  if (thread.selectedAssistantId) {
    const selected = thread.messages.find((item) => item.id === thread.selectedAssistantId);
    if (selected) return selected;
  }
  return getLastMessage(thread, "assistant");
}

function deriveThreadTitle(thread, fallback = "") {
  const firstUser = thread.messages.find((item) => item.role === "user")?.content || fallback;
  return firstUser ? firstUser.slice(0, 22) : thread.title;
}

function replaceActiveThread(nextThread) {
  state.threads = state.threads.map((thread) => (thread.id === nextThread.id ? nextThread : thread));
  persistThreadState();
}

function appendMessages(messages) {
  const thread = getActiveThread();
  const nextThread = {
    ...thread,
    messages: [...thread.messages, ...messages],
    updatedAt: new Date().toISOString(),
  };
  if (thread.title === "新会话" && messages.some((item) => item.role === "user")) {
    nextThread.title = deriveThreadTitle(nextThread, messages.find((item) => item.role === "user")?.content || "");
  }
  replaceActiveThread(nextThread);
  return nextThread;
}

function buildApiHistory(messages) {
  return messages.slice(-14).map((item) => ({
    role: item.role,
    content: item.content,
    meta: item.meta || undefined,
  }));
}

function renderToast(message = "") {
  elements.toastBox.innerHTML = message ? `<div class="toast">${escapeHtml(message)}</div>` : "";
}

function showToast(message) {
  renderToast(message);
  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }
  state.toastTimer = window.setTimeout(() => renderToast(""), 3200);
}

function setLoadingState(nextLoading) {
  state.loading = nextLoading;
  elements.submitButton.disabled = nextLoading;
  elements.submitButton.textContent = nextLoading ? "发送中..." : "发送";
  elements.stopButton.hidden = !nextLoading;
  elements.stopButton.disabled = !nextLoading;
  renderApp();
}

function renderThreadList() {
  elements.threadList.innerHTML = state.threads
    .map((thread) => {
      const preview =
        getLastMessage(thread, "assistant")?.meta?.conclusion ||
        getLastMessage(thread)?.content ||
        "还没有消息";
      return `
        <article class="thread-item ${thread.id === state.activeThreadId ? "active" : ""}">
          <div class="thread-row">
            <button class="thread-open" data-thread-id="${thread.id}">
              <span class="thread-title">${escapeHtml(thread.title)}</span>
              <span class="thread-preview">${escapeHtml(preview.slice(0, 50))}</span>
            </button>
            <button class="icon-button" data-delete-thread="${thread.id}" title="删除会话">×</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderChatHeader(thread, selectedAssistant) {
  const trace = selectedAssistant?.meta?.trace || {};
  const title = thread?.title || "新会话";
  elements.activeThreadTitle.textContent = title;
  elements.activeThreadMeta.textContent =
    selectedAssistant?.meta?.conclusion || "直接描述现场问题，或输入一个 SOP 名称开始查询。";
  elements.activeDocTag.textContent = trace.primary_doc_title || "未锁定文档";
  elements.threadStatsTag.textContent = `${thread?.messages.length || 0} 条消息`;
  elements.composerHint.textContent = trace.primary_doc_title
    ? `当前会话已锁定《${trace.primary_doc_title}》，可以继续追问“下一步呢”“注意什么”“为什么要这样做”。`
    : "支持普通问答和多轮追问，例如：你可以做什么 / 下一步呢";
}

function bubbleTags(message) {
  if (message.role !== "assistant" || !message.meta) return "";
  const trace = message.meta.trace || {};
  const tags = [message.meta.issue_type, trace.response_kind].filter(Boolean);
  return tags.map((tag) => `<span class="bubble-tag">${escapeHtml(tag)}</span>`).join("");
}

function renderMessages(thread) {
  if (!thread?.messages.length) {
    elements.messageList.innerHTML = `
      <div class="empty-chat">
        <div class="empty-chat-card">
          <h3>开始一条现场会话</h3>
          <p>可以直接输入异常场景、SOP 名称，或继续追问同一份作业指导书。</p>
        </div>
      </div>
    `;
    return;
  }

  const selectedAssistant = getSelectedAssistant(thread);
  const messageMarkup = thread.messages
    .map((message) => {
      const selectedClass = message.id === selectedAssistant?.id ? "selected" : "";
      const selectable = message.role === "assistant" ? `data-select-assistant="${message.id}"` : "";
      return `
        <div class="message-row ${message.role}">
          <article class="message-bubble ${selectedClass}" ${selectable}>
            <div class="bubble-topline">
              <span class="bubble-role">${message.role === "assistant" ? "助手" : "你"}</span>
              <div class="bubble-tags">${bubbleTags(message)}</div>
            </div>
            <pre class="message-text">${escapeHtml(message.content)}</pre>
          </article>
        </div>
      `;
    })
    .join("");
  const pendingMarkup = state.loading
    ? `
      <div class="message-row assistant pending">
        <article class="message-bubble pending-bubble">
          <div class="bubble-topline">
            <span class="bubble-role">助手</span>
            <div class="bubble-tags"><span class="bubble-tag pending-tag">生成中</span></div>
          </div>
          <pre class="message-text">正在生成回复，你可以点击“停止”。</pre>
        </article>
      </div>
    `
    : "";
  elements.messageList.innerHTML = messageMarkup + pendingMarkup;
  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

function renderSummary(selectedAssistant) {
  if (!selectedAssistant?.meta) {
    elements.selectedModeTag.textContent = "等待响应";
    elements.selectedIssueTag.textContent = "未分类";
    elements.selectedRiskTag.textContent = "low";
    elements.selectedStepTag.textContent = "0/0";
    elements.summaryBox.textContent = "选中一条助手回复后，这里会显示结论、风险等级和当前锁定文档。";
    return;
  }
  const meta = selectedAssistant.meta;
  const trace = meta.trace || {};
  elements.selectedModeTag.textContent = trace.conversation_mode || "chat";
  elements.selectedIssueTag.textContent = meta.issue_type || "未分类";
  elements.selectedRiskTag.textContent = meta.risk_level || "low";
  elements.selectedStepTag.textContent = `${trace.step_cursor || 0}/${trace.total_steps || trace.step_cursor || 0}`;
  elements.summaryBox.innerHTML = `
    <div class="summary-stack">
      <div class="summary-row">
        <strong>结论</strong>
        <span class="status-tag">${escapeHtml(trace.primary_doc_title || "未锁定文档")}</span>
      </div>
      <p>${escapeHtml(meta.conclusion || "无")}</p>
      <p class="empty">问题类型：${escapeHtml(meta.issue_type || "未分类")} · 风险等级：${escapeHtml(meta.risk_level || "low")}</p>
    </div>
  `;
}

function renderEvidence(selectedAssistant) {
  const evidence = selectedAssistant?.meta?.evidence || [];
  elements.evidenceCount.textContent = `${evidence.length} 条`;
  elements.evidenceList.innerHTML = evidence.length
    ? evidence
        .map(
          (item) => `
            <article class="evidence-card">
              <strong>${escapeHtml(item.title)}</strong>
              <p>${escapeHtml(item.snippet)}</p>
              <small>${escapeHtml(item.doc_type)} · score ${item.score} · p ${item.probability ?? "-"} · ${escapeHtml(item.confidence || "n/a")}</small>
            </article>
          `,
        )
        .join("")
    : '<div class="panel-card empty">当前回复没有返回证据片段。</div>';
}

function renderActions(selectedAssistant) {
  const actions = selectedAssistant?.meta?.actions || [];
  const confirmations = selectedAssistant?.meta?.confirmations || [];
  elements.actionCount.textContent = `${actions.length} 个`;
  elements.actionList.innerHTML = actions.length
    ? actions
        .map(
          (action) => `
            <article class="action-card">
              <div class="action-topline">
                <strong>${escapeHtml(action.title)}</strong>
                <span class="status-tag">${action.requires_confirmation ? "需确认" : "草稿"}</span>
              </div>
              <p>${escapeHtml(action.description)}</p>
              <pre>${escapeHtml(action.draft)}</pre>
              ${
                action.requires_confirmation
                  ? `<button class="ghost-button" data-confirm-action="${action.action_id}">人工确认</button>`
                  : ""
              }
            </article>
          `,
        )
        .join("")
    : '<div class="panel-card empty">当前没有动作草稿。</div>';
  elements.confirmationBox.innerHTML = confirmations.length
    ? `<ul class="flat-list">${confirmations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "当前回复未命中强制人工确认规则。";
}

function renderTools(selectedAssistant) {
  const toolResults = selectedAssistant?.meta?.tool_results || [];
  elements.toolList.innerHTML = toolResults.length
    ? toolResults
        .map(
          (tool) => `
            <article class="tool-card">
              <strong>${escapeHtml(tool.summary)}</strong>
              <pre>${escapeHtml(JSON.stringify(tool.rows, null, 2))}</pre>
            </article>
          `,
        )
        .join("")
    : '<div class="panel-card empty">本次没有结构化查询结果。</div>';
}

function renderDocuments() {
  elements.docCountTag.textContent = `${state.documents.length} 份文档`;
  elements.documentList.innerHTML = state.documents.length
    ? state.documents
        .slice(0, 10)
        .map(
          (item) => `
            <div class="mini-row">
              <strong>${escapeHtml(item.title)}</strong>
              <small>${escapeHtml(item.source)}</small>
            </div>
          `,
        )
        .join("")
    : '<div class="mini-panel empty">当前没有已索引文档。</div>';
}

function renderLatestImport() {
  const latest = state.imports[0];
  if (!latest) {
    elements.latestImportBox.textContent = "还没有导入记录。";
    return;
  }
  const importedFiles = latest.imported_files || [];
  const skippedFiles = latest.skipped_files || [];
  const failedFiles = latest.failed_files || [];
  elements.latestImportBox.innerHTML = `
    <p class="empty">扫描 ${latest.scanned_files || 0} 个，成功 ${importedFiles.length} 个，跳过 ${skippedFiles.length} 个，失败 ${failedFiles.length} 个。</p>
    <pre>${escapeHtml(latest.source_dir)}</pre>
  `;
}

function renderTabs() {
  Array.from(elements.viewTabs.querySelectorAll("[data-tab]")).forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-tab") === state.activeTab);
  });
  elements.panelChat.classList.toggle("active", state.activeTab === "chat");
  elements.panelEvidence.classList.toggle("active", state.activeTab === "evidence");
  elements.panelActions.classList.toggle("active", state.activeTab === "actions");
  elements.panelTools.classList.toggle("active", state.activeTab === "tools");
}

function renderApp() {
  const activeThread = getActiveThread();
  const selectedAssistant = getSelectedAssistant(activeThread);
  renderThreadList();
  renderChatHeader(activeThread, selectedAssistant);
  renderMessages(activeThread);
  renderSummary(selectedAssistant);
  renderEvidence(selectedAssistant);
  renderActions(selectedAssistant);
  renderTools(selectedAssistant);
  renderDocuments();
  renderLatestImport();
  renderTabs();
}

async function loadConfig() {
  try {
    const response = await fetch(buildApiUrl("/api/config"));
    if (!response.ok) {
      throw new Error("配置加载失败");
    }
    const config = await response.json();
    state.runtimeConfig = config;
    const runtimeTitle = config.llm_connected
      ? `模型已连接 · ${config.llm_model}`
      : "本地语义模式 · 未连接真实模型";
    const runtimeDetails = [
      `API: ${getApiTargetLabel()}`,
      `Provider: ${config.llm_provider}`,
      `Agent: ${config.agent_mode}`,
      `RAG: ${config.rag_enabled ? `${config.rag_profile} / top_k ${config.rag_top_k}` : "off"}`,
      `Reasoning: ${config.llm_reasoning_effort || "default"}`,
      `Max tokens: ${config.llm_max_tokens || "-"}`,
    ].join(" · ");
    elements.modeTag.textContent = config.llm_connected ? "LLM 已连接" : "本地语义";
    elements.runtimeTitle.textContent = runtimeTitle;
    elements.runtimeDescription.textContent = `${runtimeDetails}。${config.runtime_description || ""}`;
    elements.runtimeBanner.classList.toggle("warning", !config.llm_connected);
    elements.runtimeBanner.classList.toggle("success", Boolean(config.llm_connected));
    elements.agentMode.value = config.agent_mode;
    elements.ragProfile.value = config.rag_profile;
    elements.ragEnabled.checked = config.rag_enabled;
  } catch (error) {
    state.runtimeConfig = null;
    elements.modeTag.textContent = "后端未连接";
    elements.runtimeTitle.textContent = "未连接到 Agent 后端";
    elements.runtimeDescription.textContent = `当前页面正在尝试连接 ${getApiTargetLabel()}。请先启动 factory-exception-agent 后端，或通过 ?api=... / config.js 指向可访问的服务地址。`;
    elements.runtimeBanner.classList.add("warning");
    elements.runtimeBanner.classList.remove("success");
  }
}

async function refreshRagLibrary() {
  try {
    const [docsResponse, importsResponse] = await Promise.all([
      fetch(buildApiUrl("/api/rag/documents")),
      fetch(buildApiUrl("/api/rag/imports")),
    ]);
    if (!docsResponse.ok || !importsResponse.ok) {
      throw new Error("知识库加载失败");
    }
    const docsData = await docsResponse.json();
    const importsData = await importsResponse.json();
    state.documents = docsData.documents || [];
    state.imports = importsData.imports || [];
    if (!elements.sourceDirInput.value.trim() && state.imports[0]?.source_dir) {
      elements.sourceDirInput.value = state.imports[0].source_dir;
    }
  } catch {
    state.documents = [];
    state.imports = [];
  }
  renderDocuments();
  renderLatestImport();
}

async function confirmAction(actionId) {
  const selectedAssistant = getSelectedAssistant(getActiveThread());
  const action = (selectedAssistant?.meta?.actions || []).find((item) => item.action_id === actionId);
  if (!action) return;
  try {
    const response = await fetch(buildApiUrl("/api/actions/confirm"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action_id: action.action_id,
        action_type: action.action_type,
        action_title: action.title,
        draft: action.draft,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "确认失败");
    }
    showToast(data.message || "已确认");
  } catch (error) {
    showToast(formatRequestError(error, "确认失败"));
  }
}

async function submit(overrideMessage = "") {
  const activeThread = getActiveThread();
  const rawMessage = overrideMessage || elements.messageInput.value;
  const message = rawMessage.trim();
  if (!message || state.loading) {
    return;
  }

  const apiHistory = buildApiHistory(activeThread.messages);
  const userEntry = {
    id: uid("msg"),
    role: "user",
    content: message,
  };
  appendMessages([userEntry]);
  state.activeTab = "chat";
  elements.messageInput.value = "";
  state.abortController = new AbortController();
  setLoadingState(true);

  try {
    const response = await fetch(buildApiUrl("/api/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: state.abortController.signal,
      body: JSON.stringify({
        message,
        history: apiHistory,
        overrides: {
          agent_mode: elements.agentMode.value,
          rag_profile: elements.ragProfile.value,
          rag_enabled: elements.ragEnabled.checked,
        },
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "请求失败");
    }
    const assistantEntry = {
      id: uid("msg"),
      role: "assistant",
      content: data.message,
      meta: data,
    };
    const nextThread = appendMessages([assistantEntry]);
    replaceActiveThread({
      ...nextThread,
      selectedAssistantId: assistantEntry.id,
      title: deriveThreadTitle(nextThread, message),
    });
    renderApp();
  } catch (error) {
    if (error.name === "AbortError") {
      showToast("已停止本次生成。");
      return;
    }
    const errorMessage = formatRequestError(error, "请求失败");
    const assistantEntry = {
      id: uid("msg"),
      role: "assistant",
      content: `请求失败：${errorMessage}`,
      meta: {
        ...defaultAssistantMeta,
        message: `请求失败：${errorMessage}`,
        conclusion: "本次请求失败。",
        issue_type: "系统异常",
        risk_level: "medium",
        trace: { conversation_mode: "error" },
      },
    };
    const nextThread = appendMessages([assistantEntry]);
    replaceActiveThread({
      ...nextThread,
      selectedAssistantId: assistantEntry.id,
    });
    renderApp();
  } finally {
    state.abortController = null;
    setLoadingState(false);
  }
}

function stopCurrentRequest() {
  if (!state.abortController || !state.loading) {
    return;
  }
  elements.stopButton.disabled = true;
  state.abortController.abort();
}

async function importOfficeFolder() {
  const sourceDir = elements.sourceDirInput.value.trim();
  if (!sourceDir || state.importing) {
    if (!sourceDir) {
      showToast("请先输入本地文件夹路径。");
    }
    return;
  }

  state.importing = true;
  elements.importButton.textContent = "导入中...";
  elements.importButton.disabled = true;
  try {
    const response = await fetch(buildApiUrl("/api/rag/import-folder"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_dir: sourceDir,
        replace_existing: elements.replaceExisting.checked,
        recursive: true,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "导入失败");
    }
    showToast(data.message || "导入完成");
    await refreshRagLibrary();
  } catch (error) {
    showToast(formatRequestError(error, "导入失败"));
  } finally {
    state.importing = false;
    elements.importButton.textContent = "导入文件夹到 RAG";
    elements.importButton.disabled = false;
  }
}

function createNewThread() {
  const thread = createThread();
  state.threads = [thread, ...state.threads];
  state.activeThreadId = thread.id;
  state.activeTab = "chat";
  persistThreadState();
  renderApp();
  elements.messageInput.focus();
}

function deleteThread(threadId) {
  if (state.threads.length === 1) {
    const replacement = createThread();
    state.threads = [replacement];
    state.activeThreadId = replacement.id;
  } else {
    state.threads = state.threads.filter((thread) => thread.id !== threadId);
    if (state.activeThreadId === threadId) {
      state.activeThreadId = state.threads[0].id;
    }
  }
  persistThreadState();
  renderApp();
}

elements.newThreadButton.addEventListener("click", () => createNewThread());

elements.threadList.addEventListener("click", (event) => {
  const deleteId = event.target.getAttribute("data-delete-thread");
  if (deleteId) {
    deleteThread(deleteId);
    return;
  }
  const threadId = event.target.closest("[data-thread-id]")?.getAttribute("data-thread-id");
  if (!threadId) return;
  state.activeThreadId = threadId;
  state.activeTab = "chat";
  persistThreadState();
  renderApp();
});

elements.viewTabs.addEventListener("click", (event) => {
  const tab = event.target.getAttribute("data-tab");
  if (!tab) return;
  state.activeTab = tab;
  persistThreadState();
  renderTabs();
});

elements.messageList.addEventListener("click", (event) => {
  const assistantId = event.target.closest("[data-select-assistant]")?.getAttribute("data-select-assistant");
  if (!assistantId) return;
  const thread = getActiveThread();
  replaceActiveThread({
    ...thread,
    selectedAssistantId: assistantId,
    updatedAt: new Date().toISOString(),
  });
  renderApp();
});

elements.actionList.addEventListener("click", (event) => {
  const actionId = event.target.getAttribute("data-confirm-action");
  if (!actionId) return;
  confirmAction(actionId);
});

elements.submitButton.addEventListener("click", () => submit());
elements.stopButton.addEventListener("click", () => stopCurrentRequest());
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
});
elements.importButton.addEventListener("click", () => importOfficeFolder());
elements.refreshDocsButton.addEventListener("click", () => refreshRagLibrary());

loadThreadState();
renderApp();
await loadConfig();
await refreshRagLibrary();
