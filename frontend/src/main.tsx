import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { App } from "./ui/App.tsx";

const container = document.getElementById("root");
if (container === null) throw new Error("No #root element in index.html");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
