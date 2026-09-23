import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { documents } from '../api'
import { Button, Card, EmptyState } from '../components/ui'
import { SidePanel } from '../components/ui/SidePanel'
import { DataTable, type Column } from '../components/ui/DataTable'
import { DocStatusBadge } from '../components/ui/status'
import { useAuth } from '../hooks/auth-context'
import { useFilters } from '../hooks/use-filters'
import { can } from '../lib/permissions'
import { day } from '../lib/format'
import { qk } from '../lib/query-keys'
import type { Document } from '../types'

const DEFAULTS = { page: '1', doc_type: '', status: '' }
const TERMINAL = new Set(['indexed', 'failed'])
const POLL_MS = 2000

export default function DocumentsPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const { values, setFilter } = useFilters(DEFAULTS)
  const [selected, setSelected] = useState<Document | null>(null)

  const params = {
    page: Number(values.page),
    size: 20,
    ...(values.doc_type && { doc_type: values.doc_type }),
    ...(values.status && { status: values.status }),
  }

  const query = useQuery({
    queryKey: qk.documents(params),
    queryFn: () => documents.list(params),
    placeholderData: (previous) => previous,
    // Polling stops as soon as nothing is in flight. A fixed interval would
    // keep asking forever and for nothing.
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? []
      return items.some((d) => !TERMINAL.has(d.status)) ? POLL_MS : false
    },
  })

  const columns: Column<Document>[] = [
    {
      key: 'filename',
      header: 'File',
      render: (d) => <span className="font-medium">{d.filename}</span>,
    },
    { key: 'type', header: 'Type', hideBelow: 'sm', render: (d) => d.doc_type },
    {
      key: 'pages',
      header: 'Pages',
      align: 'right',
      hideBelow: 'md',
      render: (d) => d.page_count ?? '—',
    },
    { key: 'uploaded', header: 'Uploaded', hideBelow: 'md', render: (d) => day(d.created_at) },
    {
      key: 'status',
      header: 'Status',
      render: (d) => (
        <div className="flex items-center gap-2">
          <DocStatusBadge status={d.status} />
          {d.error && <span className="text-xs text-(--color-bad)">{d.error.slice(0, 60)}</span>}
        </div>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Documents</h1>
        <p className="text-sm text-(--color-ink-muted)">
          Contracts and invoices are indexed for questions. Manifests become shipments.
        </p>
      </header>

      {can(user?.role, 'document:upload') && (
        <UploadCard onUploaded={() => void client.invalidateQueries({ queryKey: ['documents'] })} />
      )}

      <Card>
        <DataTable
          columns={columns}
          rows={query.data?.items ?? []}
          rowKey={(d) => d.id}
          total={query.data?.total ?? 0}
          page={Number(values.page)}
          size={20}
          onPageChange={(page) => setFilter('page', String(page))}
          isPending={query.isPending}
          error={query.error}
          onRetry={() => void query.refetch()}
          onRowClick={(d) => setSelected(d)}
          emptyTitle="No documents yet"
          emptyHint="Upload a contract to ask questions about it, or a manifest to import shipments."
        />
      </Card>

      {selected && <ChunkPanel document={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function UploadCard({ onUploaded }: { onUploaded: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [docType, setDocType] = useState('contract')
  const [message, setMessage] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: ({ file, type }: { file: File; type: string }) => documents.upload(file, type),
    onSuccess: () => {
      setMessage('Uploaded. Processing starts in the background.')
      if (fileRef.current) fileRef.current.value = ''
      onUploaded()
    },
    onError: (error: Error) => setMessage(error.message),
  })

  return (
    <Card title="Upload">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-(--color-ink-muted)">Kind</span>
          <select
            value={docType}
            onChange={(event) => setDocType(event.target.value)}
            className="rounded-lg bg-(--color-surface) px-3 py-2 text-sm ring-1 ring-black/10"
          >
            <option value="contract">Contract (pdf)</option>
            <option value="invoice">Invoice (pdf)</option>
            <option value="manifest">Manifest (csv)</option>
          </select>
        </label>

        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span className="text-(--color-ink-muted)">File</span>
          <input
            ref={fileRef}
            type="file"
            accept={docType === 'manifest' ? '.csv' : '.pdf'}
            className="text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-(--color-accent) file:px-3 file:py-2 file:text-sm file:text-white"
          />
        </label>

        <Button
          disabled={upload.isPending}
          onClick={() => {
            const file = fileRef.current?.files?.[0]
            if (!file) {
              setMessage('Choose a file first')
              return
            }
            setMessage(null)
            upload.mutate({ file, type: docType })
          }}
        >
          {upload.isPending ? 'Uploading' : 'Upload'}
        </Button>
      </div>

      {message && (
        <p
          role={upload.isError ? 'alert' : 'status'}
          className={`mt-3 text-sm ${upload.isError ? 'text-(--color-bad)' : 'text-(--color-ink-muted)'}`}
        >
          {message}
        </p>
      )}
    </Card>
  )
}

function ChunkPanel({ document, onClose }: { document: Document; onClose: () => void }) {
  const query = useQuery({
    queryKey: qk.chunks(document.id),
    queryFn: () => documents.chunks(document.id),
    enabled: document.status === 'indexed',
  })

  return (
    <SidePanel
      title={document.filename}
      subtitle={`${document.doc_type} · ${document.page_count ?? 0} pages`}
      onClose={onClose}
      width="max-w-2xl"
    >
      {document.status !== 'indexed' ? (
        <EmptyState
          title={document.status === 'failed' ? 'Processing failed' : 'Still processing'}
          hint={document.error ?? 'Chunks appear once indexing finishes.'}
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {(query.data?.items ?? []).map((chunk) => (
            <li key={chunk.id} className="rounded-lg bg-(--color-surface-raised) p-3 text-sm">
              <p className="mb-1 text-xs text-(--color-ink-muted)">
                #{chunk.chunk_index}
                {chunk.page_no ? ` · page ${chunk.page_no}` : ''}
                {chunk.meta?.section ? ` · ${String(chunk.meta.section)}` : ''}
              </p>
              <p className="whitespace-pre-wrap">{chunk.content}</p>
            </li>
          ))}
        </ul>
      )}
    </SidePanel>
  )
}
