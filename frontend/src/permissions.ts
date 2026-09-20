import type { AccessRole } from "./types";

export function canEditDiagram(role: AccessRole | null | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "EDITOR";
}

export function canShareProject(role: AccessRole | null | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "SHARER";
}

export function canGrantRole(role: AccessRole | null | undefined, grantedRole: Exclude<AccessRole, "OWNER">): boolean {
  return canShareProject(role) && (role !== "SHARER" || grantedRole === "VIEWER" || grantedRole === "SHARER");
}
