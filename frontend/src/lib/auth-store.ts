// In memory, not localStorage: an xss can read storage, and it cannot read a
// module-scoped variable that is never exposed. The refresh token lives in an
// httpOnly cookie, so a reload recovers the session through /auth/refresh.
let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}
