import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Self-hosted fonts (no Google Fonts request -- the app works fully offline).
import "@fontsource/anton";
import "@fontsource-variable/inter";
import "lenis/dist/lenis.css";
import "./styles/tailwind.css";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
