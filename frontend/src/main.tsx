import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ChecklistPage } from "./components/ChecklistPage";
import { StaffGamePage } from "./components/StaffGamePage";
import "./styles.css";

const queryClient = new QueryClient();
const checklistMatch = window.location.pathname.match(/^\/checklist\/([^/]+)$/);
const staffGameMatch = window.location.pathname.match(/^\/play\/([^/]+)$/);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {staffGameMatch
        ? <StaffGamePage joinToken={decodeURIComponent(staffGameMatch[1])} />
        : checklistMatch
          ? <ChecklistPage token={decodeURIComponent(checklistMatch[1])} />
          : <App />}
    </QueryClientProvider>
  </React.StrictMode>,
);
