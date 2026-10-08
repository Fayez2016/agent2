import React, { useState } from "react";

export default function App() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([
    { role: "assistant", content: "Hello! I am your LangGraph Deep Agent system. How can I assist with your RHEL HA Cluster operations today?" }
  ]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const userText = query;
    setQuery("");
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    setLoading(true);

    try:
      const resp = await fetch("http://localhost:8642/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer hermes-api-secret"
        },
        body: JSON.stringify({
          model: "deepagent",
          messages: [{ role: "user", content: userText }]
        })
      });

      const data = await resp.json();
      const assistantText = data?.choices?.[0]?.message?.content || "No response received.";
      setMessages((prev) => [...prev, { role: "assistant", content: assistantText }]);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${err.message || "Failed to reach agent API"}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", padding: "20px", boxSizing: "border-box" }}>
      <header style={{ borderBottom: "1px solid #334155", paddingBottom: "15px", marginBottom: "20px" }}>
        <h2 style={{ margin: 0, color: "#38bdf8" }}>LangGraph Deep Agent Control Panel</h2>
        <small style={{ color: "#94a3b8" }}>Enterprise RHEL HA Infrastructure Automation</small>
      </header>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "12px" }}>
        {messages.map((msg, index) => (
          <div
            key={index}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              backgroundColor: msg.role === "user" ? "#0284c7" : "#1e293b",
              color: "#f8fafc",
              padding: "12px 18px",
              borderRadius: "12px",
              maxWidth: "80%",
              whiteSpace: "pre-wrap"
            }}
          >
            <strong>{msg.role === "user" ? "User" : "Deep Agent"}:</strong>
            <p style={{ margin: "6px 0 0 0" }}>{msg.content}</p>
          </div>
        ))}
        {loading && (
          <div style={{ color: "#38bdf8", fontStyle: "italic", alignSelf: "flex-start" }}>
            Deep Agent reasoning & executing tools...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type operational instruction (e.g. Check PCS cluster health for rhel-prod-01)..."
          style={{
            flex: 1,
            padding: "12px 16px",
            borderRadius: "8px",
            border: "1px solid #334155",
            backgroundColor: "#1e293b",
            color: "#fff",
            fontSize: "14px"
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "12px 24px",
            borderRadius: "8px",
            border: "none",
            backgroundColor: "#0284c7",
            color: "#fff",
            fontWeight: "bold",
            cursor: "pointer"
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
