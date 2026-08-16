import { api } from "./client";

export interface Household {
  id: number;
  name: string;
  currency: string;
}

export interface User {
  id: number;
  email: string;
  display_name: string;
  household: Household;
  date_joined: string;
}

/**
 * Primes the CSRF cookie. Must run before any unsafe request in a fresh
 * session — Django only sets the cookie when something asks for the token.
 */
export const fetchCsrfToken = () => api.get<{ csrfToken: string }>("/auth/csrf/");

export const getCurrentUser = () => api.get<User>("/auth/me/");

export const login = (email: string, password: string) =>
  api.post<User>("/auth/login/", { email, password });

export const register = (email: string, password: string, displayName: string) =>
  api.post<User>("/auth/register/", {
    email,
    password,
    display_name: displayName,
  });

export const logout = () => api.post<void>("/auth/logout/");
