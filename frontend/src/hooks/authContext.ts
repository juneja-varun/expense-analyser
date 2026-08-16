import { createContext } from "react";

import type { User } from "../api/auth";

export interface AuthState {
  user: User | null;
  /** True until the initial session check resolves. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

// Kept in its own module so the provider file exports only a component —
// mixing components and non-components in one file disables Fast Refresh.
export const AuthContext = createContext<AuthState | null>(null);
