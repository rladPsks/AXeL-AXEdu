import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./app/App";
import "./styles.css";
import "./mobile.css";
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
