import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { authApi } from "@/api/client";

const TOKEN_KEY = "ms_token";

interface AuthContextValue {
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, access_token);
    setToken(access_token);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const { access_token } = await authApi.register(name, email, password);
    localStorage.setItem(TOKEN_KEY, access_token);
    setToken(access_token);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
