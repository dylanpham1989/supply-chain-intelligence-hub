import type { components } from './api'

type S = components['schemas']

export type Shipment = S['ShipmentRead']
export type Supplier = S['SupplierRead']
export type SupplierPerformance = S['SupplierPerformance']
export type Alert = S['AlertRead']
export type Document = S['DocumentRead']
export type Chunk = S['ChunkRead']
export type Insight = S['InsightRead']
export type User = S['UserRead']
export type Summary = S['Summary']
export type StatusBreakdown = S['StatusBreakdown']
export type Timeseries = S['Timeseries']
export type TopSuppliers = S['TopSuppliers']
export type RiskBreakdown = S['RiskBreakdown']
export type AskResponse = S['AskResponse']
export type TokenResponse = S['TokenResponse']
export type UserRole = S['UserRole']
export type ShipmentStatus = S['ShipmentStatus']
export type DocStatus = S['DocStatus']
export type DocType = S['DocType']

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface ApiErrorBody {
  code: string
  message: string
  fields?: { field: string; problem: string }[]
}
