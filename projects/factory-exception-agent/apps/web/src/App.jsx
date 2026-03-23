import { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_KEY = "factory-exception-agent-threads-v3";

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

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function createThread(title = "新聊天") {
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

function loadStoredState() {
  try {
    const payload = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    const threads = Array.isArray(payload.threads) ? payload.threads : [];
    const activeThreadId = payload.activeThreadId || threads[0]?.id || "";
    const activeTab = payload.activeTab || "chat";
    if (threads.length) {
      return { threads, activeThreadId, activeTab };
    }
  } catch {
    return { threads: [], activeThreadId: "", activeTab: "chat" };
  }
  const initial = createThread();
  return {
    threads: [initial],
    activeThreadId: initial.id,
    activeTab: "chat",
  };
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

function buildApiHistory(messages) {
  return messages.slice(-14).map((item) => ({
    role: item.role,
    content: item.content,
    meta: item.meta || undefined,
  }));
}

export default function App() {
  const storedState = useMemo(() => loadStoredState(), []);
  const [threads, setThreads] = useState(storedState.threads);
  const [activeThreadId, setActiveThreadId] = useState(storedState.activeThreadId);
  const [activeTab, setActiveTab] = useState(storedState.activeTab);
  const [message, setMessage] = useState("");
  const [config, setConfig] = useState(null);
  const [overrides, setOverrides] = useState({
    agent_mode: "hybrid",
    rag_profile: "light",
    rag_enabled: true,
  });
  const [documents, setDocuments] = useState([]);
  const [imports, setImports] = useState([]);
  const [importSourceDir, setImportSourceDir] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [toast, setToast] = useState("");
  const messageListRef = useRef(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) || threads[0],
    [threads, activeThreadId],
  );
  const selectedAssistant = useMemo(() => getSelectedAssistant(activeThread), [activeThread]);
  const trace = selectedAssistant?.meta?.trace || {};

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ threads, activeThreadId, activeTab }));
  }, [threads, activeThreadId, activeTab]);

  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
    }
  }, [activeThread?.messages]);

  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        setConfig(data);
        setOverrides({
          agent_mode: data.agent_mode,
          rag_profile: data.rag_profile,
          rag_enabled: data.rag_enabled,
        });
      });
    refreshRagLibrary();
  }, []);

  async function refreshRagLibrary() {
    const [docsResponse, importsResponse] = await Promise.all([fetch("/api/rag/documents"), fetch("/api/rag/imports")]);
    const docsData = await docsResponse.json();
    const importsData = await importsResponse.json();
    setDocuments(docsData.documents || []);
    const importItems = importsData.imports || [];
    setImports(importItems);
    if (!importSourceDir && importItems[0]?.source_dir) {
      setImportSourceDir(importItems[0].source_dir);
    }
  }

  function replaceActiveThread(nextThread) {
    setThreads((prev) => prev.map((thread) => (thread.id === nextThread.id ? nextThread : thread)));
  }

  function appendMessages(messages) {
    const nextThread = {
      ...activeThread,
      messages: [...(activeThread?.messages || []), ...messages],
      updatedAt: new Date().toISOString(),
    };
    if (activeThread.title === "新聊天" && messages.some((item) => item.role === "user")) {
      nextThread.title = deriveThreadTitle(nextThread, messages.find((item) => item.role === "user")?.content || "");
    }
    replaceActiveThread(nextThread);
    return nextThread;
  }

  async function submit() {
    const content = message.trim();
    if (!content || loading || !activeThread) return;
    const apiHistory = buildApiHistory(activeThread.messages);
    const userEntry = { id: uid("msg"), role: "user", content };
    appendMessages([userEntry]);
    setMessage("");
    setActiveTab("chat");
    setLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: content,
          history: apiHistory,
          overrides,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "请求失败");
      }
      const assistantEntry = { id: uid("msg"), role: "assistant", content: data.message, meta: data };
      const nextThread = appendMessages([assistantEntry]);
      replaceActiveThread({
        ...nextThread,
        selectedAssistantId: assistantEntry.id,
        title: deriveThreadTitle(nextThread, content),
      });
    } catch (error) {
      const assistantEntry = {
        id: uid("msg"),
        role: "assistant",
        content: `请求失败：${error.message || "未知错误"}`,
        meta: {
          ...defaultAssistantMeta,
          message: `请求失败：${error.message || "未知错误"}`,
          conclusion: "本次请求失败。",
          issue_type: "系统异常",
          risk_level: "medium",
          trace: { conversation_mode: "error" },
        },
      };
      const nextThread = appendMessages([assistantEntry]);
      replaceActiveThread({ ...nextThread, selectedAssistantId: assistantEntry.id });
    } finally {
      setLoading(false);
    }
  }

  async function importOfficeFolder() {
    const sourceDir = importSourceDir.trim();
    if (!sourceDir || importing) {
      if (!sourceDir) setToast("请先输入本地文件夹路径。");
      return;
    }
    setImporting(true);
    try {
      const response = await fetch("/api/rag/import-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_dir: sourceDir,
          replace_existing: replaceExisting,
          recursive: true,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "导入失败");
      }
      setToast(data.message || "导入完成");
      await refreshRagLibrary();
    } catch (error) {
      setToast(error.message || "导入失败");
    } finally {
      setImporting(false);
    }
  }

  async function confirmAction(action) {
    const response = await fetch("/api/actions/confirm", {
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
    setToast(data.message || "已确认");
  }

  function createNewThread() {
    const thread = createThread();
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    setActiveTab("chat");
    setMessage("");
  }

  function deleteThread(threadId) {
    setThreads((prev) => {
      if (prev.length === 1) {
        const replacement = createThread();
        setActiveThreadId(replacement.id);
        return [replacement];
      }
      const filtered = prev.filter((thread) => thread.id !== threadId);
      if (activeThreadId === threadId) {
        setActiveThreadId(filtered[0].id);
      }
      return filtered;
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <div className="brand-mark">FE</div>
            <div>
              <strong>Factory Exception Agent</strong>
              <p>厂内物流 SOP 与异常处理助手</p>
            </div>
          </div>

          <button type="button" className="sidebar-primary" onClick={createNewThread}>
            + 新聊天
          </button>

          <section className="sidebar-section">
            <div className="sidebar-section-title">最近会话</div>
            <div className="thread-list">
              {threads.map((thread) => {
                const preview =
                  getLastMessage(thread, "assistant")?.meta?.conclusion || getLastMessage(thread)?.content || "还没有消息";
                return (
                  <article key={thread.id} className={`thread-item ${thread.id === activeThreadId ? "active" : ""}`}>
                    <div className="thread-row">
                      <button type="button" className="thread-open" onClick={() => { setActiveThreadId(thread.id); setActiveTab("chat"); }}>
                        <span className="thread-title">{thread.title}</span>
                        <span className="thread-preview">{preview.slice(0, 50)}</span>
                      </button>
                      <button type="button" className="icon-button" onClick={() => deleteThread(thread.id)}>
                        ×
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>

        <div className="sidebar-bottom">
          <details className="sidebar-fold">
            <summary>知识库与导入</summary>
            <div className="fold-body">
              <div className="fold-row">
                <span className="fold-label">已索引</span>
                <span className="status-tag">{documents.length} 份文档</span>
              </div>
              <input
                className="path-input"
                value={importSourceDir}
                onChange={(event) => setImportSourceDir(event.target.value)}
                placeholder="例如：E:\实习工作\中都物流-小米工作文件\小米汽车作业标准流程"
              />
              <div className="stack-actions">
                <button type="button" className="primary-button" onClick={importOfficeFolder} disabled={importing}>
                  {importing ? "导入中..." : "导入文件夹到 RAG"}
                </button>
                <button type="button" className="ghost-button" onClick={refreshRagLibrary}>
                  刷新文档列表
                </button>
              </div>
              <label className="toggle inline-toggle">
                <input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />
                <span>覆盖同一路径上次导入结果</span>
              </label>
              <div className="mini-panel">
                {imports[0] ? (
                  <>
                    <p className="empty">
                      扫描 {imports[0].scanned_files || 0} 个，成功 {(imports[0].imported_files || []).length} 个，跳过{" "}
                      {(imports[0].skipped_files || []).length} 个，失败 {(imports[0].failed_files || []).length} 个。
                    </p>
                    <pre>{imports[0].source_dir}</pre>
                  </>
                ) : (
                  "还没有导入记录。"
                )}
              </div>
              <div className="compact-list">
                {documents.slice(0, 10).map((item) => (
                  <div key={`${item.source}-${item.path}`} className="mini-row">
                    <strong>{item.title}</strong>
                    <small>{item.source}</small>
                  </div>
                ))}
              </div>
            </div>
          </details>

          <details className="sidebar-fold">
            <summary>运行设置</summary>
            <div className="fold-body">
              <label>
                <span>Agent 模式</span>
                <select value={overrides.agent_mode} onChange={(event) => setOverrides((prev) => ({ ...prev, agent_mode: event.target.value }))}>
                  <option value="hybrid">hybrid</option>
                  <option value="only-tool">only-tool</option>
                </select>
              </label>
              <label>
                <span>RAG 档位</span>
                <select value={overrides.rag_profile} onChange={(event) => setOverrides((prev) => ({ ...prev, rag_profile: event.target.value }))}>
                  <option value="light">light</option>
                  <option value="full">full</option>
                </select>
              </label>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={overrides.rag_enabled}
                  onChange={(event) => setOverrides((prev) => ({ ...prev, rag_enabled: event.target.checked }))}
                />
                <span>启用 RAG</span>
              </label>
              <div className="fold-row">
                <span className="fold-label">当前模式</span>
                <span className="status-tag">{config?.mock_mode ? "Mock Mode" : "LLM Mode"}</span>
              </div>
            </div>
          </details>
        </div>
      </aside>

      <main className="main-panel">
        <header className="chat-header">
          <div>
            <h1>{activeThread?.title || "新聊天"}</h1>
            <p className="chat-subtitle">
              {selectedAssistant?.meta?.conclusion || "直接输入一个 SOP 或异常问题，系统会在当前会话里保留上下文。"}
            </p>
          </div>
          <div className="header-badges">
            <span className="status-tag">{trace.primary_doc_title || "未锁定 SOP"}</span>
            <span className="status-tag">{activeThread?.messages.length || 0} 条消息</span>
          </div>
        </header>

        <section className="summary-strip">
          <span className="summary-pill">{trace.conversation_mode || "等待选择"}</span>
          <span className="summary-pill">{selectedAssistant?.meta?.issue_type || "未分类"}</span>
          <span className="summary-pill">{selectedAssistant?.meta?.risk_level || "low"}</span>
          <span className="summary-pill">
            {trace.step_cursor || 0}/{trace.total_steps || trace.step_cursor || 0}
          </span>
        </section>

        <section className={`runtime-banner ${config?.llm_connected ? "success" : "warning"}`}>
          <div>
            <strong>
              {config?.llm_connected
                ? `真实模型已连接 · ${config?.llm_provider} / ${config?.llm_model}`
                : "推荐模型：Ollama + qwen3.5:9b"}
            </strong>
            <p>{config?.runtime_description || "正在获取当前运行模式；如果你本机有自定义 qwen3.5:14b，也可以直接在 .env 里替换 LLM_MODEL。"}</p>
          </div>
        </section>

        <nav className="view-tabs">
          {[
            ["chat", "聊天"],
            ["evidence", "来源"],
            ["actions", "动作"],
            ["tools", "工具"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`view-tab ${activeTab === key ? "active" : ""}`}
              onClick={() => setActiveTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>

        <section className="panel-stack">
          <section className={`view-panel ${activeTab === "chat" ? "active" : ""}`}>
            <div ref={messageListRef} className="message-list">
              {!activeThread?.messages.length ? (
                <div className="empty-chat">
                  <div className="empty-chat-card">
                    <h3>今天想处理什么问题？</h3>
                    <p>你可以直接输入某个 SOP 名称、异常场景，或者像聊天一样继续追问“下一步呢”“注意什么”“为什么要这样做”。</p>
                  </div>
                </div>
              ) : (
                activeThread.messages.map((entry) => (
                  <div key={entry.id} className={`message-row ${entry.role}`}>
                    <article
                      className={`message-bubble ${entry.id === selectedAssistant?.id ? "selected" : ""}`}
                      onClick={() => {
                        if (entry.role === "assistant") {
                          replaceActiveThread({ ...activeThread, selectedAssistantId: entry.id, updatedAt: new Date().toISOString() });
                        }
                      }}
                    >
                      <div className="bubble-topline">
                        <span className="bubble-role">{entry.role === "assistant" ? "Agent" : "你"}</span>
                        <div className="bubble-tags">
                          {entry.role === "assistant" &&
                            [entry.meta?.issue_type, entry.meta?.trace?.response_kind]
                              .filter(Boolean)
                              .map((tag) => (
                                <span key={`${entry.id}-${tag}`} className="bubble-tag">
                                  {tag}
                                </span>
                              ))}
                        </div>
                      </div>
                      <pre className="message-text">{entry.content}</pre>
                    </article>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className={`view-panel ${activeTab === "evidence" ? "active" : ""}`}>
            <div className="panel-card summary-box">
              {!selectedAssistant?.meta ? (
                "选中一条 Agent 回复后，这里会显示结论、风险等级和当前锁定的 SOP。"
              ) : (
                <div className="summary-stack">
                  <div className="summary-row">
                    <strong>结论</strong>
                    <span className="status-tag">{trace.primary_doc_title || "未锁定 SOP"}</span>
                  </div>
                  <p>{selectedAssistant.meta.conclusion}</p>
                  <p className="empty">
                    问题类型：{selectedAssistant.meta.issue_type || "未分类"} · 风险等级：{selectedAssistant.meta.risk_level || "low"}
                  </p>
                </div>
              )}
            </div>
            <div className="panel-head">
              <h2>证据 / 引用</h2>
              <span>{selectedAssistant?.meta?.evidence?.length || 0} 条</span>
            </div>
            <div className="list-stack">
              {(selectedAssistant?.meta?.evidence || []).length ? (
                selectedAssistant.meta.evidence.map((item) => (
                  <article key={`${item.source}-${item.snippet}`} className="evidence-card">
                    <strong>{item.title}</strong>
                    <p>{item.snippet}</p>
                    <small>
                      {item.source} · {item.doc_type} · score {item.score} · p {item.probability ?? "-"} · {item.confidence || "n/a"}
                    </small>
                  </article>
                ))
              ) : (
                <div className="panel-card empty">当前回复没有返回证据片段。</div>
              )}
            </div>
          </section>

          <section className={`view-panel ${activeTab === "actions" ? "active" : ""}`}>
            <div className="panel-head">
              <h2>建议动作</h2>
              <span>{selectedAssistant?.meta?.actions?.length || 0} 个</span>
            </div>
            <div className="list-stack">
              {(selectedAssistant?.meta?.actions || []).length ? (
                selectedAssistant.meta.actions.map((action) => (
                  <article key={action.action_id} className="action-card">
                    <div className="action-topline">
                      <strong>{action.title}</strong>
                      <span className="status-tag">{action.requires_confirmation ? "需确认" : "草稿"}</span>
                    </div>
                    <p>{action.description}</p>
                    <pre>{action.draft}</pre>
                    {action.requires_confirmation && (
                      <button type="button" className="ghost-button" onClick={() => confirmAction(action)}>
                        人工确认
                      </button>
                    )}
                  </article>
                ))
              ) : (
                <div className="panel-card empty">当前没有动作草稿。</div>
              )}
            </div>
            <div className="panel-head second-head">
              <h2>人工确认</h2>
            </div>
            <div className="panel-card">
              {(selectedAssistant?.meta?.confirmations || []).length ? (
                <ul className="flat-list">
                  {selectedAssistant.meta.confirmations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                "当前回复未命中强制人工确认规则。"
              )}
            </div>
          </section>

          <section className={`view-panel ${activeTab === "tools" ? "active" : ""}`}>
            <div className="panel-head">
              <h2>结构化查询</h2>
            </div>
            <div className="list-stack">
              {(selectedAssistant?.meta?.tool_results || []).length ? (
                selectedAssistant.meta.tool_results.map((tool) => (
                  <article key={tool.tool_name} className="tool-card">
                    <strong>{tool.summary}</strong>
                    <pre>{JSON.stringify(tool.rows, null, 2)}</pre>
                  </article>
                ))
              ) : (
                <div className="panel-card empty">本次没有结构化查询结果。</div>
              )}
            </div>
          </section>
        </section>

        <footer className="composer-shell">
          <div className="composer">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="给 Factory Exception Agent 发消息"
            />
            <div className="composer-bottom">
              <span className="composer-hint">
                {trace.primary_doc_title
                  ? `当前会话已锁定《${trace.primary_doc_title}》，可以继续追问“下一步呢”“注意什么”“为什么要这样做”。`
                  : "支持多轮追问，也支持普通聊天，例如：你好 / 你能做什么"}
              </span>
              <button type="button" className="submit-button" onClick={submit} disabled={loading}>
                {loading ? "思考中..." : "发送"}
              </button>
            </div>
          </div>
        </footer>
      </main>

      {toast && (
        <div className="toast-layer">
          <div className="toast">{toast}</div>
        </div>
      )}
    </div>
  );
}
