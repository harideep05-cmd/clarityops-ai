import { useState } from "react";
import "./App.css";

function App() {
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);

  const askAI = async () => {
    if (!prompt.trim()) return;

    setLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt: prompt,
        }),
      });

      const data = await res.json();
      setResponse(data.response);
    } catch (err) {
      setResponse("Error connecting to backend.");
    }

    setLoading(false);
  };

  return (
    <div className="container">
      <h1>🚀 ClarityOps AI</h1>

      <textarea
        placeholder="Ask Gemini anything..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />

      <button onClick={askAI}>
        {loading ? "Thinking..." : "Ask AI"}
      </button>

      <div className="response">
        <h2>Response</h2>
        <p>{response}</p>
      </div>
    </div>
  );
}

export default App;