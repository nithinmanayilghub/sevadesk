"use client";
// Shares the logged-in User's permissions with every /app page (story 2.5). The /app layout
// asks GET /api/v1/me once and provides the list; a page reads it with usePermissions(),
// so it can hide links and buttons the User may not use (UX-DR27). This only decides what
// to SHOW: the backend still checks every Role on every request (AD-5).
import { createContext, useContext, type ReactNode } from "react";
import type { Permission } from "@/lib/access";

// The default (no provider) is "may do nothing", so a mistake hides things instead of showing them.
const PermissionsContext = createContext<Permission[]>([]);

export function PermissionsProvider({ permissions, children }: { permissions: Permission[]; children: ReactNode }) {
  return <PermissionsContext.Provider value={permissions}>{children}</PermissionsContext.Provider>;
}

export function usePermissions(): Permission[] {
  return useContext(PermissionsContext);
}
