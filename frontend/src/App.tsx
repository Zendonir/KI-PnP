/** Routing der Anwendung. */

import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { CreateGamePage } from "./pages/CreateGamePage";
import { GamePage } from "./pages/GamePage";
import { HomePage } from "./pages/HomePage";
import { JoinPage } from "./pages/JoinPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/create" element={<CreateGamePage />} />
        <Route path="/join/:code" element={<JoinPage />} />
        <Route path="/game/:gameId" element={<GamePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
