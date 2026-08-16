import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import type { User } from "../api/auth";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Prime the CSRF cookie, then see whether an existing session cookie
    // already identifies someone. A 403 here just means "logged out".
    void (async () => {
      try {
        await authApi.fetchCsrfToken();
        setUser(await authApi.getCurrentUser());
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setUser(await authApi.login(email, password));
  }, []);

  const register = useCallback(async (email: string, password: string, displayName: string) => {
    setUser(await authApi.register(email, password, displayName));
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
