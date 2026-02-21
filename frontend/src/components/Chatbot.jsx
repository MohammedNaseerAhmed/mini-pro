import { useState, useRef, useEffect } from "react";

export default function Chatbot({ api }) {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([
        { role: "bot", text: "👋 Hello! I'm your Legal Assistant. Ask me anything about the uploaded document — I'll explain it simply." }
    ]);
    const [input, setInput] = useState("");
    const [asking, setAsking] = useState(false);
    const bottomRef = useRef(null);

    useEffect(() => {
        if (open && bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, open]);

    const send = async () => {
        const q = input.trim();
        if (!q || asking) return;
        setInput("");
        setMessages((m) => [...m, { role: "user", text: q }]);
        setAsking(true);
        try {
            const data = await api(`/chatbot/ask?q=${encodeURIComponent(q)}`);
            setMessages((m) => [...m, { role: "bot", text: data.answer || "I could not find an answer in the document." }]);
        } catch (e) {
            setMessages((m) => [...m, { role: "bot", text: `Sorry, there was an error: ${e.message}` }]);
        } finally {
            setAsking(false);
        }
    };

    const onKeyDown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    };

    return (
        <>
            <button id="chat-fab" className="chat-fab" title="Ask Legal Assistant" onClick={() => setOpen((o) => !o)}>
                {open ? "✕" : "💬"}
            </button>

            {open && (
                <div className="chat-panel">
                    <div className="chat-header">
                        <span>💬 Legal Assistant (RAG)</span>
                        <button className="chat-close" onClick={() => setOpen(false)}>✕</button>
                    </div>
                    <div className="chat-messages">
                        {messages.map((m, i) => (
                            <div key={i} className={`chat-bubble ${m.role}`}>{m.text}</div>
                        ))}
                        {asking && (
                            <div className="chat-bubble bot typing">
                                <span><i /><i /><i /></span>
                            </div>
                        )}
                        <div ref={bottomRef} />
                    </div>
                    <div className="chat-input-row">
                        <textarea
                            id="chat-input"
                            className="chat-input"
                            placeholder="Ask about the document…"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={onKeyDown}
                            rows={1}
                        />
                        <button id="chat-send" className="chat-send" onClick={send} disabled={asking || !input.trim()}>
                            ➤
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
