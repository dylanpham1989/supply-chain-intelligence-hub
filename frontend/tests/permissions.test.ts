import { describe, expect, it } from 'vitest'
import { can } from '../src/lib/permissions'

describe('role grants', () => {
  it('gives an admin everything', () => {
    for (const permission of ['shipment:write', 'user:write', 'document:upload', 'tenant:write']) {
      expect(can('admin', permission)).toBe(true)
    }
  })

  it('lets an analyst work but not manage people', () => {
    expect(can('analyst', 'shipment:write')).toBe(true)
    expect(can('analyst', 'document:upload')).toBe(true)
    expect(can('analyst', 'insight:create')).toBe(true)
    expect(can('analyst', 'user:write')).toBe(false)
  })

  it('keeps a viewer read only', () => {
    expect(can('viewer', 'shipment:read')).toBe(true)
    expect(can('viewer', 'shipment:write')).toBe(false)
    expect(can('viewer', 'document:upload')).toBe(false)
    expect(can('viewer', 'insight:create')).toBe(false)
  })

  it('denies when the role is not known yet', () => {
    expect(can(undefined, 'shipment:read')).toBe(false)
  })
})
