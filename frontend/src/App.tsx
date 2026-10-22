import { useEffect, useState } from "react";
import "./App.css";

type ResourceType = "papers" | "articles" | "blogs" | "videos";
type Feedback = "like" | "dislike" | null;

interface CrossReference {
  title: string;
  url: string;
  note?: string;
}

interface RecommendationItem {
  id: string;
  title: string;
  url: string;
  type: ResourceType;
  summary: string;
  source?: string;
  score?: number;
  feedback: Feedback;
  crossReferences?: CrossReference[];
}

interface StructuredResponse {
  query: string;
  resourceTypes: ResourceType[];
  createdAt: string;
  items: RecommendationItem[];
  additionalSources?: CrossReference[];
}

const API_URL = "/__proxy_inject__/backend";

async function fetchRecommendations(
  query: string,
): Promise<StructuredResponse> {
  const text = Array.from(
    document.querySelectorAll('article p, article h1, article h2, article h3, article li')
  )
    // @ts-ignore
    .map(el => el.innerText?.trim())
    .filter(Boolean)
    .join('\n\n');

  console.log(text);
  const payload = {
    query,
    url:
      typeof window !== "undefined"
        ? window.location.href
        : undefined,
    title:
      typeof document !== "undefined"
        ? document.title
        : undefined,
    contentSnippet: text,
  };

  const res = await fetch(`${API_URL}/related`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  return (await res.json()) as StructuredResponse;

}

async function sendFeedback(
  source: string,
  feedback: Exclude<Feedback, null>
) {
  console.debug("Sending feedback", { source, feedback });
  await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: source,
      feedback,
    }),
  });
}

type Status = "idle" | "loading" | "ready" | "error";

function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [query, setQuery] = useState<string | null>(null);
  const [response, setResponse] = useState<StructuredResponse | null>(null);
  const [showJson, setShowJson] = useState(false);

  const isVisible = status === "ready" && !!response;

  const derivePageQuery = () => {
    const title = typeof document !== "undefined" ? document.title : "";
    const host = typeof window !== "undefined" ? window.location.hostname : "";
    return title || host || "Current page";
  };

  const fetchData = async (q: string) => {
    try {
      setStatus("loading");
      const data = await fetchRecommendations(q);
      setResponse(data);
      setStatus("ready");
    } catch (e) {
      console.error(e);
      setStatus("error");
    }
  };

  useEffect(() => {
    let started = false;

    const start = () => {
      if (started) return;
      started = true;
      const q = derivePageQuery();
      setQuery(q);
      fetchData(q);
    };

    if (document.readyState === "complete") {
      start();
    } else {
      window.addEventListener("load", start);
    }

    return () => {
      window.removeEventListener("load", start);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const handleFeedback = async (
    source: string,
    feedback: Exclude<Feedback, null>
  ) => {
    setResponse((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.source === source ? { ...item, feedback } : item
        ),
      };
    });
    void sendFeedback(source, feedback);
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div
      className="assistant-root"
    >
      <header className="assistant-header">
        <div>
          <h1 className="assistant-title">Related coverage</h1>
          <p className="assistant-subtitle">
            Similar articles & sources for cross-checking.
          </p>
        </div>
      </header>

      <p className="assistant-based-on">
        Based on this page:{" "}
        <span className="assistant-based-on-text">{query}</span>
      </p>


      {response && status === "ready" && (
        <section className="assistant-results">
          <div className="assistant-results-header">
            <h2>Suggested articles</h2>
            <span className="assistant-meta">
              {response.items.length} results •{" "}
              {new Date(response.createdAt).toLocaleTimeString()}
            </span>
          </div>

          <div className="assistant-list">
            {response.items.map((item) => (
              <article key={item.id} className="assistant-card">
                <div className="assistant-card-header">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="assistant-card-title"
                  >
                    {item.title}
                  </a>
                </div>

                <p className="assistant-summary">{item.summary}</p>

                {item.crossReferences && item.crossReferences.length > 0 && (
                  <div className="assistant-crossrefs">
                    <span className="assistant-crossrefs-label">
                      Cross references:
                    </span>
                    <ul>
                      {item.crossReferences.map((cr, idx) => (
                        <li key={idx}>
                          <a
                            href={cr.url}
                            target="_blank"
                            rel="noreferrer"
                            className="assistant-crossref-link"
                          >
                            {cr.title}
                          </a>
                          {cr.note && (
                            <span className="assistant-crossref-note">
                              {" "}
                              — {cr.note}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="assistant-footer">
                  {item.source && (<div className="assistant-feedback">
                    <span>Useful?</span>
                    <button
                      type="button"
                      className={`assistant-feedback-btn ${item.feedback === "like"
                        ? "assistant-feedback-btn--active"
                        : ""
                        }`}
                      onClick={() => handleFeedback(item.source!, "like")}
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      className={`assistant-feedback-btn ${item.feedback === "dislike"
                        ? "assistant-feedback-btn--active"
                        : ""
                        }`}
                      onClick={() => handleFeedback(item.source!, "dislike")}
                    >
                      👎
                    </button>
                  </div>)}
                  {typeof item.score === "number" && (
                    <span className="assistant-score">
                      Relevance: {(item.score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </article>
            ))}
          </div>

          <button
            type="button"
            className="assistant-json-toggle"
            onClick={() => setShowJson((s) => !s)}
          >
            {showJson ? "Hide JSON" : "Show JSON"}
          </button>

          {showJson && (
            <pre className="assistant-json">
              {JSON.stringify(response, null, 2)}
            </pre>
          )}
        </section>
      )}
    </div>
  );
}

export default App;
