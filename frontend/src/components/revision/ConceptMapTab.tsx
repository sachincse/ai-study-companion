import dagre from '@dagrejs/dagre'
import { useMutation } from '@tanstack/react-query'
import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react'
import { Copy, Network, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { api, errorMessage } from '../../lib/api'
import { useInvalidate } from '../../lib/hooks'
import type { Artifact, ConceptGraph } from '../../lib/types'
import { Card, Field, Modal } from '../ui'
import { ArtifactList, SourcesFooter, useArtifacts } from './ArtifactTabs'
import { GenerateForm } from './GenerateForm'

const NODE_STYLES: Record<string, React.CSSProperties> = {
  root: { background: '#4946b5', color: '#fff', border: '1px solid #3b3894', fontWeight: 700 },
  concept: { background: '#ffffff', color: '#0b1220', border: '1px solid #c3c8fb' },
  process: { background: '#e2f1fb', color: '#1d659a', border: '1px solid #bfdbfe' },
  example: { background: '#e0f5ea', color: '#19764d', border: '1px solid #bbf7d0' },
  definition: { background: '#fff0d9', color: '#9a5a08', border: '1px solid #fde68a' },
}

function layoutGraph(graph: ConceptGraph): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: graph.style === 'flowchart' ? 'TB' : 'LR', nodesep: 32, ranksep: 70 })
  graph.nodes.forEach((n) => g.setNode(n.id, { width: 190, height: 54 }))
  graph.edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  const nodes: Node[] = graph.nodes.map((n) => {
    const p = g.node(n.id)
    return {
      id: n.id,
      position: { x: p.x - 95, y: p.y - 27 },
      data: { label: n.label, description: n.description },
      style: { ...NODE_STYLES[n.type] ?? NODE_STYLES.concept, borderRadius: 12, padding: '8px 12px', fontSize: 13, width: 190, textAlign: 'center' },
    }
  })
  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    labelStyle: { fontSize: 11, fill: '#64748b' },
    style: { stroke: '#94a3b8', strokeWidth: 1.5 },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
  }))
  return { nodes, edges }
}

function toMermaid(graph: ConceptGraph) {
  const lines = [graph.style === 'flowchart' ? 'flowchart TD' : 'graph LR']
  for (const n of graph.nodes) lines.push(`  ${n.id}["${n.label.replace(/"/g, "'")}"]`)
  for (const e of graph.edges) lines.push(`  ${e.source} ${e.label ? `-- ${e.label.replace(/"/g, "'")} ` : ''}--> ${e.target}`)
  return lines.join('\n')
}

export function ConceptMapTab() {
  const invalidate = useInvalidate()
  const { data } = useArtifacts<ConceptGraph>('concept_map')
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState<'concept_map' | 'flowchart'>('concept_map')
  const [selected, setSelected] = useState<number | null>(null)
  const [focus, setFocus] = useState<{ label: string; description?: string } | null>(null)
  const generate = useMutation({
    mutationFn: (v: { topic: string; document_ids: number[]; subject_id: number | '' }) =>
      api<Artifact<ConceptGraph>>('/api/v1/tools/concept-map', { body: { topic: v.topic || null, document_ids: v.document_ids.length ? v.document_ids : null, subject_id: v.subject_id || null, style } }),
    onSuccess: (a) => {
      setOpen(false)
      setSelected(a.id)
      invalidate('artifacts', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const active = data?.find((a) => a.id === selected) ?? data?.[0]
  const flow = useMemo(() => (active ? layoutGraph(active.content) : null), [active])

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="space-y-3">
        <button className="btn-primary w-full" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New concept map
        </button>
        <ArtifactList kind="concept_map" items={data} selected={active?.id ?? null} onSelect={setSelected} emptyTitle="No concept maps yet" emptyDescription="Interactive knowledge graphs and flowcharts generated from your notes." onNew={() => setOpen(true)} renderMeta={(a) => `${a.content.style === 'flowchart' ? 'Flowchart' : 'Concept map'} · ${a.content.nodes.length} nodes`} />
        {focus && (
          <Card title={focus.label}>
            <p className="text-sm text-slate-600">{focus.description || 'No description for this node.'}</p>
          </Card>
        )}
      </div>
      <Card className="p-0 overflow-hidden">
        {active && flow ? (
          <>
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
              <div className="flex items-center gap-2 text-sm font-bold text-ink-900">
                <Network className="h-4 w-4 text-brand-600" /> {active.title}
              </div>
              <button className="btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(toMermaid(active.content)).then(() => toast.success('Mermaid source copied'))}>
                <Copy className="h-3.5 w-3.5" /> Copy as Mermaid
              </button>
            </div>
            <div className="h-[560px]">
              <ReactFlow key={active.id} nodes={flow.nodes} edges={flow.edges} fitView nodesDraggable nodesConnectable={false} onNodeClick={(_e, n) => setFocus({ label: String(n.data.label), description: n.data.description as string | undefined })} proOptions={{ hideAttribution: true }}>
                <Background gap={18} color="#e2e8f0" />
                <MiniMap pannable zoomable />
                <Controls />
              </ReactFlow>
            </div>
            <div className="px-4 pb-3">
              <SourcesFooter sources={active.sources} />
            </div>
          </>
        ) : (
          <p className="p-5 text-sm text-slate-500">Select or generate a concept map.</p>
        )}
      </Card>
      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Generate a concept map">
        <GenerateForm onSubmit={(v) => generate.mutate(v)} busy={generate.isPending} submitLabel="Build map">
          <Field label="Diagram type">
            <div className="flex gap-2">
              {(['concept_map', 'flowchart'] as const).map((s) => (
                <button key={s} type="button" onClick={() => setStyle(s)} className={style === s ? 'chip border border-brand-200 bg-brand-50 text-brand-700' : 'chip border border-slate-200 bg-white text-slate-500'}>
                  {s === 'concept_map' ? 'Concept map' : 'Flowchart (process / algorithm)'}
                </button>
              ))}
            </div>
          </Field>
        </GenerateForm>
      </Modal>
    </div>
  )
}
