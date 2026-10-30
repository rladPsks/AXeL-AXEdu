import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./app/App";
import "./styles.css";
import "./mobile.css";
import "./coordination.css";
import "./demo.css";
import "./comparison.css";
import "./reference-theme.css";
import "./sunshine-theme.css";
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
