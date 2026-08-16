import { useAuth } from "./hooks/useAuth";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  const { user, loading } = useAuth();

  // Rendering the login form before the session check resolves would flash it
  // at users who are already signed in.
  if (loading) {
    return <div className="loading">Loading…</div>;
  }

  return user ? <DashboardPage /> : <LoginPage />;
}
