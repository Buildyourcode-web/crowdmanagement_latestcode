import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// CSS imports - order matters
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "./styles/variables.css";
import "./styles/global.css";
import "./styles/command-center.css";

import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
