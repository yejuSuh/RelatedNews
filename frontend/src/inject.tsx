import { createRoot } from "react-dom/client";
import App from "./App";

const ROOT_ID = "__injected__root__"

function mountAssistant() {
  // avoid iframes + double-injecting
  if (window.top !== window.self || document.getElementById(ROOT_ID)) return;

  const container = document.createElement("div");
  container.id = ROOT_ID;
  container.style.position = "fixed";
  container.style.top = "20px";
  container.style.right = "20px";
  container.style.zIndex = "999999";
  container.style.fontFamily =
    'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

  document.body.appendChild(container);

  const root = createRoot(container);
  root.render(<App />);
}

if (document.readyState === "complete") {
  mountAssistant();
} else {
  window.addEventListener("load", () => {
    mountAssistant();
  });
}
