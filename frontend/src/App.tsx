import { useQuery } from "@tanstack/react-query";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type HealthResponse = {
  status: string;
  service: string;
};

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`);
  if (!response.ok) {
    throw new Error("The simulation service is unavailable");
  }
  return response.json() as Promise<HealthResponse>;
}

export default function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 1,
    refetchInterval: 30_000,
  });

  const scrollToFoundation = () => {
    document.querySelector("#foundation")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Situational Awareness home">
          <span className="brand-mark">SA</span>
          <span>
            <strong>Situational Awareness</strong>
            <small>Retail decision intelligence</small>
          </span>
        </a>
        <span className={`status-pill ${health.isSuccess ? "status-ok" : ""}`}>
          <i aria-hidden="true" />
          {health.isSuccess ? "Simulation engine online" : "Connecting to engine"}
        </span>
      </header>

      <section className="hero" id="top">
        <span className="eyebrow">Decisions before disruption</span>
        <h1>See how a sustainability change plays out before your store commits.</h1>
        <p>
          Simulate staff, shoppers, operations, energy, and margin as one auditable
          system. Green Close is the first behavior we test—not the name of the
          product and not the limit of the platform.
        </p>
        <div className="hero-actions">
          <button type="button" onClick={scrollToFoundation}>
            Explore the foundation
          </button>
          <button className="button-secondary" type="button" onClick={scrollToFoundation}>
            How the Game Master works
          </button>
        </div>
      </section>

      <section className="foundation-grid" id="foundation" aria-label="Platform foundation">
        <article>
          <span>01 / Governed</span>
          <h2>An authoritative Game Master</h2>
          <p>
            Every agent proposes actions; one deterministic controller enforces
            safety, operating rules, and a replayable event sequence.
          </p>
        </article>
        <article>
          <span>02 / Situated</span>
          <h2>A store, not a spreadsheet</h2>
          <p>
            Layout, equipment, customers, staff workload, and closing tasks share
            the same timeline so second-order effects remain visible.
          </p>
        </article>
        <article>
          <span>03 / Auditable</span>
          <h2>Evidence over theatre</h2>
          <p>
            The interface separates measured inputs, assumptions, and simulated
            outcomes, then explains each intervention with its confidence range.
          </p>
        </article>
      </section>
    </main>
  );
}
