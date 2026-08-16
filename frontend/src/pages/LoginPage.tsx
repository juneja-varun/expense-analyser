import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, displayName);
      }
    } catch (err) {
      // Surface the server's field errors rather than a generic failure —
      // password rules in particular are useless if the user can't see them.
      if (err instanceof ApiError) {
        const messages = Object.values(err.fieldErrors).flat();
        setError(messages.length ? messages.join(" ") : "Something went wrong. Please try again.");
      } else {
        setError("Could not reach the server.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth__card">
        <h1>Expense Analyser</h1>
        <p className="auth__subtitle">
          {mode === "login" ? "Sign in to your instance" : "Create your account"}
        </p>

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <label>
              Name
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                required
              />
            </label>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </label>

          {error && <p className="auth__error">{error}</p>}

          <button type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          type="button"
          className="auth__switch"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "Need an account? Register" : "Already registered? Sign in"}
        </button>
      </div>
    </main>
  );
}
