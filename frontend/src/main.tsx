import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Fonts are bundled into the build, not pulled from a CDN at runtime — ARIA has to look
// and work the same with no internet connection, which is the whole point of it.
import "@fontsource/space-grotesk/400.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/700.css";

import App from "./App";
import "./styles.css";

const container = document.getElementById("root");
if (!container) throw new Error("#root element is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
