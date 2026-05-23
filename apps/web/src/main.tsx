import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="shell">
      <section className="status-panel">
        <p className="eyebrow">NeuroWeave</p>
        <h1>EEG workflow workspace</h1>
        <p>
          Phase 0 UI shell is ready. API wiring and sample EEG metadata will be
          added next.
        </p>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
