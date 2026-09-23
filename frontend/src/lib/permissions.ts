import type { UserRole } from '../types'

// Mirrors the server. This hides controls a role cannot use; it is not a
// security boundary. Every one of these is enforced again in the api, and a
// test proves curl gets a 403 regardless of what the ui shows.
const GRANTS: Record<UserRole, ReadonlySet<string>> = {
  admin: new Set(['*']),
  analyst: new Set([
    'shipment:read',
    'shipment:write',
    'supplier:read',
    'supplier:write',
    'contract:read',
    'document:read',
    'document:upload',
    'insight:read',
    'insight:create',
    'alert:read',
    'alert:write',
    'user:read',
  ]),
  viewer: new Set([
    'shipment:read',
    'supplier:read',
    'contract:read',
    'document:read',
    'insight:read',
    'alert:read',
  ]),
}

export function can(role: UserRole | undefined, permission: string): boolean {
  if (!role) return false
  const granted = GRANTS[role]
  return granted.has('*') || granted.has(permission)
}
