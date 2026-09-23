import { Badge } from './index'
import type { DocStatus, ShipmentStatus } from '../../types'

const SHIPMENT_TONE: Record<ShipmentStatus, 'neutral' | 'ok' | 'warn' | 'bad'> = {
  planned: 'neutral',
  in_transit: 'warn',
  delivered: 'ok',
  delayed: 'bad',
  cancelled: 'neutral',
}

const DOC_TONE: Record<DocStatus, 'neutral' | 'ok' | 'warn' | 'bad'> = {
  pending: 'neutral',
  processing: 'warn',
  indexed: 'ok',
  failed: 'bad',
}

const label = (value: string) => value.replace(/_/g, ' ')

export function ShipmentStatusBadge({ status }: { status: ShipmentStatus }) {
  return <Badge tone={SHIPMENT_TONE[status]}>{label(status)}</Badge>
}

export function DocStatusBadge({ status }: { status: DocStatus }) {
  return <Badge tone={DOC_TONE[status]}>{label(status)}</Badge>
}
