import { useState, useEffect, useRef, type CSSProperties } from 'react'
import { flushSync } from 'react-dom'
import {
  animateCard,
  createCardStream,
  fetchRun,
  fetchWall,
  submitRun,
  type CardProgressEvent,
  type WallItem,
} from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'create' | 'batch' | 'gallery'
type NodeStatus = 'idle' | 'active' | 'scheduling' | 'pending' | 'done' | 'failed' | 'preempted' | 'skipped'

interface RNode {
  id: string; label: string; kind: string; sub: string
  status: NodeStatus; meta?: string; metaColor?: string; progress?: number
}
interface LogLine { t: number; mark: string; text: string; tone: string }
interface RunState {
  title: string; status: 'idle' | 'running' | 'done'
  nodes: Record<string, RNode>; levels: string[][]
  log: LogLine[]; elapsed: number
}
interface Kid {
  id: string; name: string; age: number; wish: string
  tags: string[]; mood: string; city: string; bg: string
  hasVideo: boolean; gift?: string; batchStatus?: 'queued' | 'card' | 'video' | 'failed'
  pngUrl?: string; videoUrl?: string; model?: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const ITAGS = [
  { id: 'space', label: '🚀 Space', color: '#3B82F6', light: 'rgba(59,130,246,.15)' },
  { id: 'dinosaurs', label: '🦕 Dinosaurs', color: '#22C55E', light: 'rgba(34,197,94,.15)' },
  { id: 'art', label: '🎨 Art', color: '#EF4444', light: 'rgba(239,68,68,.15)' },
  { id: 'music', label: '🎵 Music', color: '#A855F7', light: 'rgba(168,85,247,.15)' },
  { id: 'football', label: '⚽ Football', color: '#F97316', light: 'rgba(249,115,22,.15)' },
  { id: 'robots', label: '🤖 Robots', color: '#6B7280', light: 'rgba(107,114,128,.15)' },
  { id: 'animals', label: '🐾 Animals', color: '#F59E0B', light: 'rgba(245,158,11,.15)' },
  { id: 'books', label: '📚 Books', color: '#7C3AED', light: 'rgba(124,58,237,.15)' },
  { id: 'lego', label: '🧱 Lego', color: '#DC2626', light: 'rgba(220,38,38,.15)' },
  { id: 'ocean', label: '🌊 Ocean', color: '#0EA5E9', light: 'rgba(14,165,233,.15)' },
]
const MOODS = ['Dreamy', 'Playful', 'Cozy', 'Epic']
const BGS = ['rgb(255,230,180)', 'rgb(200,235,200)', 'rgb(210,225,255)', 'rgb(255,210,210)', 'rgb(220,245,235)', 'rgb(255,240,200)']

const GALLERY_SEED: Kid[] = [
  { id:'g1', name:"Emma", age:8, wish:"Dear Alex, my dear three‑year‑old explorer, I’ve heard about the wonderful wooden car that loves to pull you along sn…", tags:["books"], mood:"Dreamy", city:"Oslo", bg:BGS[0], hasVideo:true, gift:"Wooden pull‑along car", pngUrl:'/demo/g1/card.png', videoUrl:'/demo/g1/video.mp4' },
  { id:'g2', name:"Lucas", age:8, wish:"Dear Kid, being 8 is such a marvelous age for discovering new wonders, and I’ve heard you’ll be building fantastic cr…", tags:["lego"], mood:"Dreamy", city:"Stockholm", bg:BGS[1], hasVideo:false, gift:"LEGO Creator 3‑in‑1 Building Set", pngUrl:'/demo/g2/card.png' },
  { id:'g3', name:"Sofia", age:8, wish:"Dear Kid, at the wonderful age of 8 your imagination is already as bright as the twinkling lights on my sleigh. I hea…", tags:["lego", "robots"], mood:"Dreamy", city:"Helsinki", bg:BGS[2], hasVideo:false, gift:"LEGO Boost Creative Toolbox (STEM building kit)", pngUrl:'/demo/g3/card.png' },
  { id:'g4', name:"Noah", age:8, wish:"Dear Kid, at 8 years old you’re already a brilliant explorer of imagination! I hear you’ve been crafting marvelous in…", tags:["robots", "lego"], mood:"Dreamy", city:"Copenhagen", bg:BGS[3], hasVideo:false, gift:"Interactive STEM building set (e.g., magnetic circuits or robot kit)", pngUrl:'/demo/g4/card.png' },
  { id:'g5', name:"Ingrid", age:8, wish:"Dear Kid, at your wonderful age of 8 you’re already a master of building marvelous structures that snap together, a b…", tags:["lego"], mood:"Dreamy", city:"Bergen", bg:BGS[4], hasVideo:false, gift:"Magnetic building tiles set", pngUrl:'/demo/g5/card.png' },
  { id:'g6', name:"Felix", age:8, wish:"Dear Kid, at eight years old you already shine with the curiosity of a thousand stars. I’ve placed a handful of wondr…", tags:["robots"], mood:"Dreamy", city:"Malmö", bg:BGS[5], hasVideo:false, gift:"Interactive STEM building set", pngUrl:'/demo/g6/card.png' },
  { id:'g7', name:"Astrid", age:8, wish:"Dear Kid, I hear that being 8 years old fills your days with curiosity and wonder! This year the North Pole elves hav…", tags:["robots", "lego"], mood:"Dreamy", city:"Gothenburg", bg:BGS[0], hasVideo:false, gift:"STEM Building Kit (magnetic tiles or simple robotics set)", pngUrl:'/demo/g7/card.png' },
  { id:'g8', name:"Oliver", age:8, wish:"Hello Kid! At eight years old, your curiosity shines brighter than the North Star, and I hear the soft clink of magne…", tags:["robots", "lego"], mood:"Dreamy", city:"Espoo", bg:BGS[1], hasVideo:false, gift:"Magnetic STEM Building Kit", pngUrl:'/demo/g8/card.png' },
  { id:'g9', name:"Nick", age:5, wish:"Lego and animals", tags:["dinosaurs", "lego"], mood:"Dreamy", city:"Turku", bg:BGS[2], hasVideo:false, gift:"LEGO Dino Adventure Building Set", pngUrl:'/demo/g9/card.png' },
  { id:'g10', name:"Elias", age:8, wish:"Dear Kid, being eight is such a wonderful time when every question feels like a new adventure, and I’ve seen how your…", tags:["lego", "robots"], mood:"Dreamy", city:"Aarhus", bg:BGS[3], hasVideo:false, gift:"STEM Building Kit (e.g., LEGO Boost or similar)", pngUrl:'/demo/g10/card.png' },
  { id:'g11', name:"Freya", age:8, wish:"Dear Kid, at the wonderful age of 8 you’re already a true master of imagination. I’ve heard the North Pole elves have…", tags:["lego"], mood:"Dreamy", city:"Odense", bg:BGS[4], hasVideo:false, gift:"LEGO Creator 3‑in‑1 Building Set", pngUrl:'/demo/g11/card.png' },
  { id:'g12', name:"Viktor", age:8, wish:"Hello Kid, being eight means your imagination shines brighter than the twinkling lights on my sleigh. I’ve tucked a c…", tags:["robots", "lego"], mood:"Dreamy", city:"Tampere", bg:BGS[5], hasVideo:false, gift:"Magnetic STEM Building Tiles", pngUrl:'/demo/g12/card.png' },
]

const BATCH_SEED: Kid[] = [
  { id:'k1', name:'Thea', age:8, wish:'Fairy tale collection', tags:['books'], mood:'Cozy', city:'Oslo', bg:BGS[0], hasVideo:false },
  { id:'k2', name:'Mikkel', age:10, wish:'RC racing car', tags:['robots'], mood:'Epic', city:'Copenhagen', bg:BGS[1], hasVideo:false },
  { id:'k3', name:'Lena', age:7, wish:'Art supply mega kit', tags:['art'], mood:'Dreamy', city:'Stockholm', bg:BGS[2], hasVideo:false },
  { id:'k4', name:'Oscar', age:12, wish:'Reflecting telescope', tags:['space'], mood:'Epic', city:'Helsinki', bg:BGS[3], hasVideo:false },
  { id:'k5', name:'Nora', age:6, wish:'Stuffed elephant family', tags:['animals'], mood:'Cozy', city:'Bergen', bg:BGS[4], hasVideo:false },
  { id:'k6', name:'Emil', age:9, wish:'Football boots and ball', tags:['football'], mood:'Playful', city:'Malmö', bg:BGS[5], hasVideo:false },
  { id:'k7', name:'Hanna', age:8, wish:'Mini piano keyboard', tags:['music'], mood:'Dreamy', city:'Gothenburg', bg:BGS[0], hasVideo:false },
  { id:'k8', name:'Lars', age:11, wish:'Lego Technic supercar', tags:['lego','robots'], mood:'Epic', city:'Aarhus', bg:BGS[1], hasVideo:false },
  { id:'k9', name:'Sigrid', age:5, wish:'Ocean animals puzzle', tags:['ocean'], mood:'Cozy', city:'Turku', bg:BGS[2], hasVideo:false },
  { id:'k10', name:'Bjorn', age:13, wish:'Dinosaur encyclopedia set', tags:['dinosaurs','books'], mood:'Cozy', city:'Espoo', bg:BGS[3], hasVideo:false },
  { id:'k11', name:'Ida', age:7, wish:'Watercolour brush set', tags:['art'], mood:'Playful', city:'Odense', bg:BGS[4], hasVideo:false },
  { id:'k12', name:'Kristian', age:10, wish:'Programmable robot kit', tags:['robots'], mood:'Epic', city:'Tampere', bg:BGS[5], hasVideo:false },
  { id:'k13', name:'Elin', age:8, wish:'Star projector nightlight', tags:['space'], mood:'Dreamy', city:'Oslo', bg:BGS[0], hasVideo:false },
  { id:'k14', name:'Tor', age:9, wish:'Football training goal', tags:['football'], mood:'Playful', city:'Stockholm', bg:BGS[1], hasVideo:false },
  { id:'k15', name:'Maria', age:6, wish:'Animal plushie collection', tags:['animals'], mood:'Cozy', city:'Helsinki', bg:BGS[2], hasVideo:false },
  { id:'k16', name:'Gunnar', age:11, wish:'Coding board game', tags:['robots','space'], mood:'Epic', city:'Copenhagen', bg:BGS[3], hasVideo:false },
  { id:'k17', name:'Ragna', age:7, wish:'Junior drum kit', tags:['music'], mood:'Playful', city:'Bergen', bg:BGS[4], hasVideo:false },
  { id:'k18', name:'Sven', age:12, wish:'Sailing ship model kit', tags:['ocean'], mood:'Cozy', city:'Malmö', bg:BGS[5], hasVideo:false },
  { id:'k19', name:'Klara', age:8, wish:'Lego Harry Potter castle', tags:['lego','books'], mood:'Dreamy', city:'Gothenburg', bg:BGS[0], hasVideo:false },
  { id:'k20', name:'Viggo', age:10, wish:'Paleontology excavation kit', tags:['dinosaurs'], mood:'Epic', city:'Aarhus', bg:BGS[1], hasVideo:false },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtElapsed(ms: number): string {
  const t = Math.max(0, ms)
  const tenths = Math.floor(t / 100) % 10
  const secs = Math.floor(t / 1000) % 60
  const mins = Math.floor(t / 60000)
  return `${mins}:${String(secs).padStart(2, '0')}.${tenths}`
}

function emptyRun(): RunState {
  return { title: '', status: 'idle', nodes: {}, levels: [], log: [], elapsed: 0 }
}

function nodeColors(s: NodeStatus) {
  const map: Record<NodeStatus, { border: string; bg: string }> = {
    idle: { border: 'rgba(0,0,0,.1)', bg: 'white' },
    active: { border: 'rgb(54,151,241)', bg: 'rgba(54,151,241,.08)' },
    scheduling: { border: 'rgb(143,82,204)', bg: 'rgba(143,82,204,.08)' },
    pending: { border: 'rgba(0,0,0,.2)', bg: 'rgba(0,0,0,.03)' },
    done: { border: 'rgb(48,170,110)', bg: 'rgba(48,170,110,.08)' },
    failed: { border: 'rgb(233,3,58)', bg: 'rgba(233,3,58,.06)' },
    preempted: { border: 'rgb(233,174,86)', bg: 'rgba(233,174,86,.15)' },
    skipped: { border: 'rgba(0,0,0,.15)', bg: 'white' },
  }
  return map[s]
}

function nodeBadge(s: NodeStatus) {
  const map: Record<NodeStatus, { bg: string; text: string; label: string }> = {
    idle: { bg: 'rgba(0,0,0,.06)', text: 'rgba(0,0,0,.4)', label: 'IDLE' },
    active: { bg: 'rgba(54,151,241,.15)', text: 'rgb(54,151,241)', label: 'RUNNING' },
    scheduling: { bg: 'rgba(143,82,204,.15)', text: 'rgb(143,82,204)', label: 'SCHEDULING' },
    pending: { bg: 'rgba(0,0,0,.08)', text: 'rgba(0,0,0,.5)', label: 'PENDING' },
    done: { bg: 'rgba(48,170,110,.15)', text: 'rgb(48,170,110)', label: 'DONE' },
    failed: { bg: 'rgba(233,3,58,.12)', text: 'rgb(233,3,58)', label: 'FAILED' },
    preempted: { bg: 'rgba(233,174,86,.2)', text: 'rgb(160,110,20)', label: 'PREEMPTED' },
    skipped: { bg: 'rgba(0,0,0,.08)', text: 'rgba(0,0,0,.4)', label: 'SKIPPED' },
  }
  return map[s]
}

function logMarkColor(tone: string): string {
  const map: Record<string, string> = {
    blue: 'rgb(54,151,241)', green: 'rgb(48,170,110)',
    amber: 'rgb(160,110,20)', red: 'rgb(233,3,58)', muted: 'rgba(0,0,0,.35)',
  }
  return map[tone] ?? 'rgba(0,0,0,.35)'
}

function tagById(id: string) {
  return ITAGS.find(t => t.id === id)
}

function bgForId(id: string): string {
  let n = 0
  for (let i = 0; i < id.length; i++) n = (n + id.charCodeAt(i) * (i + 1)) % 997
  return BGS[n % BGS.length]
}

function wallToKid(item: WallItem): Kid {
  return {
    id: item.id,
    name: item.name,
    age: item.age,
    wish: item.wish,
    tags: item.tags,
    mood: item.mood,
    city: item.city || '',
    bg: bgForId(item.id),
    hasVideo: item.has_video,
    gift: item.gift,
    pngUrl: item.png_url || undefined,
    videoUrl: item.video_url || undefined,
    model: item.model,
    batchStatus: item.has_video ? 'video' : 'card',
  }
}

function jobNodeStatus(state: string): NodeStatus {
  const s = (state || '').toUpperCase()
  if (s.includes('SCHEDUL')) return 'scheduling'
  if (s === 'PENDING' || s === 'QUEUED' || s === 'CREATED') return 'pending'
  if (s === 'RUNNING' || s === 'ACTIVE') return 'active'
  if (['COMPLETED', 'SUCCEEDED', 'SUCCESS', 'DONE'].includes(s)) return 'done'
  if (s.includes('PREEMPT')) return 'preempted'
  if (['FAILED', 'ERROR', 'CANCELLED', 'CANCELED'].includes(s) || s.startsWith('ERROR')) return 'failed'
  return 'pending'
}

function shortError(err: unknown): string {
  const text = String(err instanceof Error ? err.message : err).replace(/^Error:\s*/, '')
  if (/CERTIFICATE_VERIFY_FAILED|TLS failed|SSL validation/i.test(text)) {
    return 'TLS failed (laptop CA). Retry with AWS_CA_BUNDLE=/etc/ssl/cert.pem'
  }
  return text.length > 90 ? `${text.slice(0, 87)}…` : text
}

const ANIMATE_JOBS = 4

function animateBatchNodes(jobCount = ANIMATE_JOBS): Record<string, RNode> {
  const nodes: Record<string, RNode> = {
    santa: nodeWithStatus('santa', 'idle', { sub: 'POST /api/runs · animate_batch' }),
    storecards: nodeWithStatus('storecards', 'idle', { sub: 'list cards/{id}/card.png' }),
    storevideos: nodeWithStatus('storevideos', 'idle'),
  }
  for (let i = 0; i < jobCount; i++) {
    nodes[`job${i}`] = {
      id: `job${i}`, label: `Job ${i}`, kind: 'job',
      sub: 'santa-job · H100 preemptible',
      status: 'pending',
    }
  }
  return nodes
}

function animateBatchLevels(jobCount = ANIMATE_JOBS): string[][] {
  return [['santa'], ['storecards'], Array.from({ length: jobCount }, (_, i) => `job${i}`), ['storevideos']]
}

function initialAnimateBatchRun(status: RunState['status'] = 'idle'): RunState {
  return {
    title: 'Let it snow · GPU jobs',
    status,
    nodes: animateBatchNodes(),
    levels: animateBatchLevels(),
    log: [],
    elapsed: 0,
  }
}

const MAGIC_LEVELS: Record<string, string[][]> = {
  default: [['santa'], ['token'], ['sana'], ['bucket']],
  fallback: [['santa'], ['token'], ['sana', 'openai'], ['bucket']],
}

/** Graph node labels — role first; model name only in meta (never URLs). */
const GRAPH_NODE: Record<string, Omit<RNode, 'status'>> = {
  santa: { id: 'santa', label: 'santa-service', kind: 'service', sub: 'POST /api/cards' },
  token: { id: 'token', label: 'LLM (Token Factory)', kind: 'llm', sub: 'chat.completions' },
  sana: { id: 'sana', label: 'Image gen endpoint (Serverless AI)', kind: 'endpoint', sub: 'images.generate' },
  openai: { id: 'openai', label: 'Image gen (OpenAI fallback)', kind: 'fallback', sub: 'images.generate' },
  wan: { id: 'wan', label: 'Video gen endpoint (Serverless AI)', kind: 'endpoint', sub: 'POST /v1/videos' },
  ace: { id: 'ace', label: 'Audio gen endpoint (Serverless AI)', kind: 'endpoint', sub: 'text2music' },
  mux: { id: 'mux', label: 'mux.py', kind: 'file', sub: 'ffmpeg -i mp4 -i mp3 -shortest' },
  bucket: { id: 'bucket', label: 'Object Storage', kind: 'bucket', sub: 'PUT cards/{id}/card.png' },
  storecards: { id: 'storecards', label: 'Object Storage', kind: 'bucket', sub: 'cards/ · chunks/ · runs/' },
  storevideos: { id: 'storevideos', label: 'Object Storage', kind: 'bucket', sub: 'videos/ · summary.json' },
}

const MAGIC_NODE_DEFAULTS = GRAPH_NODE

function nodeWithStatus(id: string, status: NodeStatus, patch?: Partial<RNode>): RNode {
  const base = GRAPH_NODE[id] ?? { id, label: id, kind: 'service', sub: '' }
  return { ...base, status, ...patch }
}

function shortModelName(raw: string): string {
  const text = (raw || '').trim()
  if (!text) return text
  const at = text.indexOf('@')
  if (at > 0) return text.slice(0, at).trim()
  return text
}

function compactNodeMeta(meta?: string): string | undefined {
  if (!meta) return meta
  const parts = meta.split(' · ')
  if (parts.length < 2) return meta
  const last = parts[parts.length - 1]
  if (last.includes('@') || last.startsWith('http')) {
    parts[parts.length - 1] = shortModelName(last)
    return parts.join(' · ')
  }
  return meta
}

function initialMagicRun(): RunState {
  return {
    title: 'Magic · single card',
    status: 'running',
    nodes: {
      santa: { ...MAGIC_NODE_DEFAULTS.santa, status: 'active' },
      token: { ...MAGIC_NODE_DEFAULTS.token, status: 'idle' },
      sana: { ...MAGIC_NODE_DEFAULTS.sana, status: 'idle' },
      bucket: { ...MAGIC_NODE_DEFAULTS.bucket, status: 'idle' },
    },
    levels: MAGIC_LEVELS.default,
    log: [],
    elapsed: 0,
  }
}

function applyCardProgress(run: RunState, event: CardProgressEvent): RunState {
  if (event.type === 'step') return run
  const nodes = { ...run.nodes }
  let levels = run.levels

  if (event.type === 'active') {
    const base = MAGIC_NODE_DEFAULTS[event.node]
    if (!base) return run
    if (event.node === 'openai') levels = MAGIC_LEVELS.fallback
    nodes[event.node] = { ...base, status: 'active' }
    return { ...run, nodes, levels }
  }

  if (event.type === 'done') {
    const base = nodes[event.node] ?? MAGIC_NODE_DEFAULTS[event.node]
    if (!base) return run
    const status = (event.status ?? 'done') as NodeStatus
    nodes[event.node] = { ...base, status, meta: compactNodeMeta(event.meta) }
    return { ...run, nodes, levels }
  }

  return run
}

// ── Node Card ─────────────────────────────────────────────────────────────────

const NODE_LINE: CSSProperties = {
  fontFamily: 'JetBrains Mono,Menlo,monospace',
  fontSize: 12,
  lineHeight: '17px',
  minWidth: 0,
  maxWidth: '100%',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
}

function NodeLine({ text, color, marginTop }: { text: string; color: string; marginTop?: number }) {
  return (
    <div style={{ ...NODE_LINE, color, marginTop }} title={text}>
      {text}
    </div>
  )
}

function NodeCard({ node }: { node: RNode }) {
  const col = nodeColors(node.status)
  const badge = nodeBadge(node.status)
  const pulse = node.status === 'active'
  const pulsePurple = node.status === 'scheduling'

  return (
    <div style={{
      border: `1.5px solid ${col.border}`,
      background: col.bg,
      borderRadius: 6,
      padding: '10px 12px',
      flex: '1 1 140px',
      minWidth: 0,
      maxWidth: 310,
      width: '100%',
      boxSizing: 'border-box',
      overflow: 'hidden',
      position: 'relative',
      animation: pulse || pulsePurple ? `${pulse ? 'pulse-ring' : 'pulse-purple'} 1.8s ease-out infinite` : undefined,
      transition: 'border-color 0.3s, background 0.3s',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 3, minWidth: 0 }}>
        <div style={{
          fontSize: 14, fontWeight: 600, color: 'rgba(0,0,0,.85)', lineHeight: '20px',
          minWidth: 0, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }} title={node.label}>{node.label}</div>
        <div style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
          background: badge.bg, color: badge.text,
          borderRadius: 3, padding: '2px 6px', whiteSpace: 'nowrap', flexShrink: 0,
        }}>{badge.label}</div>
      </div>
      <NodeLine text={node.sub} color="rgba(0,0,0,.5)" />
      {node.meta && (
        <NodeLine text={node.meta} color={node.metaColor ?? 'rgba(0,0,0,.45)'} marginTop={2} />
      )}
      {node.progress !== undefined && (
        <div style={{ height: 3, borderRadius: 2, background: 'rgba(0,0,0,.08)', marginTop: 6 }}>
          <div style={{ height: '100%', borderRadius: 2, background: col.border, width: `${node.progress}%`, transition: 'width 0.5s ease' }} />
        </div>
      )}
    </div>
  )
}

// ── DAG Graph ─────────────────────────────────────────────────────────────────

function DAGGraph({ run }: { run: RunState }) {
  if (run.levels.length === 0) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ border: '1.5px dashed rgba(0,0,0,.15)', borderRadius: 8, padding: '28px 20px', textAlign: 'center', color: 'rgba(0,0,0,.3)', fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 13 }}>
          Nothing running. Press Magic, Animate or Let it snow…
        </div>
      </div>
    )
  }
  return (
    <div style={{ padding: '16px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
      {run.levels.map((levelIds, li) => {
        const nodes = levelIds.map(id => run.nodes[id]).filter(Boolean)
        const isActive = nodes.some(n => n.status === 'active' || n.status === 'scheduling' || n.status === 'pending')
        const allDone = nodes.length > 0 && nodes.every(n => ['done','failed','skipped','preempted'].includes(n.status))
        const connColor = isActive ? 'rgb(54,151,241)' : allDone ? 'rgb(48,170,110)' : 'rgba(0,0,0,.15)'
        return (
          <div key={li} style={{ width: '100%', maxWidth: 620, minWidth: 0, padding: '0 4px', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', minWidth: 0 }}>
              {nodes.map(node => <NodeCard key={node.id} node={node} />)}
            </div>
            {li < run.levels.length - 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', height: 18, position: 'relative' }}>
                <div style={{ width: 2, background: connColor, transition: 'background 0.4s', position: 'relative', overflow: 'hidden' }}>
                  {isActive && (
                    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '200%', background: 'linear-gradient(to bottom, transparent 0%, rgba(255,255,255,.8) 50%, transparent 100%)', animation: 'connector-flow 0.7s linear infinite' }} />
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Log Panel ─────────────────────────────────────────────────────────────────

function LogPanel({ run }: { run: RunState }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [run.log.length])

  if (run.log.length === 0) {
    return (
      <div ref={ref} style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12.5, color: 'rgba(0,0,0,.35)', lineHeight: '19px' }}>
        {'$ santa doctor · .env ok · TF ok · endpoints ok · bucket ok'}
      </div>
    )
  }
  return (
    <div ref={ref} style={{ padding: '10px 14px', overflowY: 'auto', fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12.5, lineHeight: '19px' }}>
      {run.log.map((line, i) => (
        <div key={i} className="fadein" style={{ display: 'flex', gap: 8, marginBottom: 1 }}>
          <span style={{ color: 'rgba(0,0,0,.28)', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>{fmtElapsed(line.t)}</span>
          <span style={{ color: logMarkColor(line.tone), flexShrink: 0, width: 14 }}>{line.mark}</span>
          <span style={{ color: line.tone === 'muted' ? 'rgba(0,0,0,.45)' : line.tone === 'amber' ? 'rgb(160,110,20)' : logMarkColor(line.tone), wordBreak: 'break-all' }}>{line.text}</span>
        </div>
      ))}
    </div>
  )
}

// ── Live Panel ────────────────────────────────────────────────────────────────

function LivePanel({ run, scope, realMode, onRealMode }: {
  run: RunState; scope: string; realMode: boolean; onRealMode: (v: boolean) => void
}) {
  const statusDot = run.status === 'running' ? 'rgb(54,151,241)' : run.status === 'done' ? 'rgb(48,170,110)' : 'rgba(0,0,0,.2)'
  const statusLabel = run.status === 'running' ? 'running' : run.status === 'done' ? 'done' : 'idle'

  // Draggable split: logPct is the percentage of the body height given to the LOG panel (0–90)
  const [logPct, setLogPct] = useState(40)
  const dragging = useRef(false)
  const panelBodyRef = useRef<HTMLDivElement>(null)

  const onDividerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current || !panelBodyRef.current) return
      const rect = panelBodyRef.current.getBoundingClientRect()
      const relY = ev.clientY - rect.top
      const pct = 100 - (relY / rect.height) * 100
      setLogPct(Math.min(90, Math.max(5, pct)))
    }
    const onUp = () => {
      dragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <aside style={{ width: 720, display: 'flex', flexDirection: 'column', borderLeft: '2px solid rgba(0,0,0,.15)', background: 'rgb(242,237,228)', flexShrink: 0 }}>
      {/* Panel header */}
      <div style={{ background: 'white', borderBottom: '1px solid rgba(0,0,0,.1)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusDot, boxShadow: run.status === 'running' ? `0 0 0 3px rgba(54,151,241,.2)` : undefined, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'rgba(0,0,0,.7)' }}>Serverless AI · live</span>
        <div style={{ display: 'flex', border: '1px solid rgba(0,0,0,.15)', borderRadius: 6, overflow: 'hidden' }}>
          {([['Sim', false], ['Real', true]] as const).map(([label, value]) => {
            const active = realMode === value
            return (
              <button key={label} onClick={() => onRealMode(value)} style={{
                border: 'none', padding: '3px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
                cursor: 'pointer', fontFamily: 'inherit',
                background: active ? (value ? 'rgb(45,139,93)' : 'rgb(233,174,86)') : 'white',
                color: active ? (value ? 'white' : 'rgba(0,0,0,.8)') : 'rgba(0,0,0,.45)',
              }}>{label}</button>
            )
          })}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, background: 'rgba(0,0,0,.07)', borderRadius: 4, padding: '2px 7px', color: 'rgba(0,0,0,.5)', fontWeight: 500 }}>{scope}</span>
          {run.title && <span style={{ fontSize: 12, color: 'rgba(0,0,0,.55)', fontWeight: 500 }}>{run.title}</span>}
          <span style={{
            fontSize: 10, fontWeight: 600, letterSpacing: '0.05em',
            background: run.status === 'running' ? 'rgba(54,151,241,.12)' : run.status === 'done' ? 'rgba(48,170,110,.12)' : 'rgba(0,0,0,.06)',
            color: run.status === 'running' ? 'rgb(54,151,241)' : run.status === 'done' ? 'rgb(48,170,110)' : 'rgba(0,0,0,.4)',
            borderRadius: 3, padding: '2px 6px',
          }}>{statusLabel.toUpperCase()}</span>
          <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)', fontVariantNumeric: 'tabular-nums', minWidth: 52 }}>{fmtElapsed(run.elapsed)}</span>
        </div>
      </div>

      {/* Resizable body: DAG + divider + log */}
      <div ref={panelBodyRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* DAG region — takes remaining space above log */}
        <div style={{ flex: 1, overflowY: 'auto', background: 'white', minHeight: 40 }}>
          <div style={{ padding: '10px 12px 4px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'rgba(0,0,0,.35)', letterSpacing: '0.06em' }}>RESOURCES</span>
          </div>
          <DAGGraph run={run} />
        </div>

        {!realMode && (
          <>
            {/* Drag divider */}
            <div
              onMouseDown={onDividerMouseDown}
              style={{
                height: 6, flexShrink: 0, cursor: 'row-resize', position: 'relative',
                background: 'rgba(0,0,0,.1)', borderTop: '1px solid rgba(0,0,0,.12)', borderBottom: '1px solid rgba(0,0,0,.12)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(233,174,86,.5)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'rgba(0,0,0,.1)')}
            >
              {/* Drag grip dots */}
              <div style={{ display: 'flex', gap: 3 }}>
                {[0,1,2].map(i => <div key={i} style={{ width: 3, height: 3, borderRadius: '50%', background: 'rgba(0,0,0,.3)' }} />)}
              </div>
            </div>

            {/* Log region — height controlled by logPct */}
            <div style={{ height: `${logPct}%`, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 24 }}>
              <div style={{ padding: '7px 14px 3px', flexShrink: 0 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: 'rgba(0,0,0,.35)', letterSpacing: '0.06em' }}>LOG</span>
              </div>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <LogPanel run={run} />
              </div>
            </div>
          </>
        )}
      </div>
    </aside>
  )
}

// ── Tag Chip ──────────────────────────────────────────────────────────────────

function TagChip({ tag, selected, onClick }: { tag: typeof ITAGS[0]; selected: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      border: 'none', cursor: 'pointer', borderRadius: 20, padding: '5px 12px', fontSize: 13, fontWeight: 500,
      background: selected ? tag.color : tag.light,
      color: selected ? 'white' : tag.color,
      transition: 'all 0.15s ease', fontFamily: 'inherit',
    }}>{tag.label}</button>
  )
}

// ── Gift Card Preview ─────────────────────────────────────────────────────────

function GiftCard({ stage, form, cardData, stage2, onAnimate, onPlay, hasVideo, videoPlaying }: {
  stage: 'hidden' | 'generating' | 'ready'
  form: { name: string; age: number; wish: string; tags: string[]; mood: string }
  cardData: { gift: string; model: string; bg: string; pngUrl?: string; videoUrl?: string } | null
  stage2: string
  onAnimate: () => void
  onPlay: () => void
  hasVideo: boolean
  videoPlaying: boolean
}) {
  if (stage === 'hidden') return null
  return (
    <div className="fadein" style={{ background: 'white', border: '1px solid rgba(0,0,0,.15)', borderRadius: 8, boxShadow: '0 4px 12px -2px rgba(0,0,0,.12)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 4, height: 16, background: 'rgb(45,139,93)', borderRadius: 2 }} />
        <span style={{ fontSize: 17, fontWeight: 600 }}>Gift Card</span>
      </div>
      <div style={{ padding: '0 20px 20px', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        {/* Square preview */}
        <div style={{
          width: 280, height: 280, borderRadius: 6, flexShrink: 0, position: 'relative', overflow: 'hidden',
          background: stage === 'ready' && cardData ? cardData.bg : 'rgba(0,0,0,.04)',
          borderTop: stage === 'ready' ? '4px solid rgb(45,139,93)' : undefined,
        }}>
          {stage === 'generating' && (
            <>
              <div className="shimmer-bg" style={{ position: 'absolute', inset: 0 }} />
              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                <div style={{ width: 24, height: 24, border: '2.5px solid rgba(0,0,0,.15)', borderTopColor: 'rgb(45,139,93)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.45)', textAlign: 'center', padding: '0 16px' }}>{stage2}</div>
              </div>
            </>
          )}
          {stage === 'ready' && (
            cardData?.pngUrl ? (
              <img src={cardData.pngUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, padding: 16 }}>
              <div style={{ fontSize: 40 }}>🎁</div>
              <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 10.5, color: 'rgba(0,0,0,.3)', textAlign: 'center', lineHeight: '15px' }}>
                image placeholder · 1024×1024<br />drop generated PNG here
              </div>
            </div>
            )
          )}
        </div>
        {/* Card details */}
        {stage === 'ready' && cardData && (
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 4 }}>
            <div>
              <div style={{ fontSize: 19, fontWeight: 700, color: 'rgba(0,0,0,.85)' }}>Merry Christmas, {form.name || 'Kid'}! 🎄</div>
              <div style={{ fontSize: 14, color: 'rgba(0,0,0,.55)', marginTop: 4, lineHeight: '20px', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                {form.wish || 'Wishing you a magical Christmas this year!'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ background: 'rgba(45,139,93,.12)', color: 'rgb(45,139,93)', borderRadius: 4, padding: '3px 8px', fontSize: 12.5, fontWeight: 500 }}>Gift: {cardData.gift}</span>
              {form.tags.slice(0,2).map(tid => {
                const t = tagById(tid)
                return t ? <span key={tid} style={{ background: t.light, color: t.color, borderRadius: 4, padding: '3px 8px', fontSize: 12.5, fontWeight: 500 }}>{t.label}</span> : null
              })}
            </div>
            <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 11.5, color: 'rgba(0,0,0,.35)' }}>{cardData.model}</div>
            {/* Actions */}
            <div style={{ marginTop: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {!hasVideo && (
                <button onClick={onAnimate} style={{
                  border: '1.5px solid rgba(0,0,0,.2)', background: 'white', borderRadius: 6, padding: '8px 16px',
                  fontSize: 14, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit', color: 'rgba(0,0,0,.75)',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}>🎬 Animate</button>
              )}
              {hasVideo && (
                <>
                  <button onClick={onPlay} style={{
                    border: 'none', background: 'rgb(45,139,93)', color: 'white', borderRadius: 6, padding: '8px 16px',
                    fontSize: 14, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>{videoPlaying ? '⏹ Stop' : '▶ Play video card'}</button>
                  <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 11.5, color: 'rgba(0,0,0,.35)', alignSelf: 'center' }}>
                    videos/v_8f2a.mp4 · 832×480 · 16 fps · 5 s · {form.mood.toLowerCase()} track
                  </span>
                </>
              )}
            </div>
            {videoPlaying && (
              cardData?.videoUrl ? (
                <video src={cardData.videoUrl} autoPlay controls playsInline style={{ width: '100%', borderRadius: 6, marginTop: 4 }} />
              ) : (
              <div style={{ height: 4, borderRadius: 2, background: 'rgba(0,0,0,.08)', marginTop: 4, overflow: 'hidden' }}>
                <div className="fadein" style={{ height: '100%', borderRadius: 2, background: 'rgb(45,139,93)', width: '100%', animation: 'shimmer 5s linear' }} />
              </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Create Tab ────────────────────────────────────────────────────────────────

function CreateTab({ form, setForm, onMagic, createRunning, cardStage, cardStageLabel, cardData, onAnimate, onPlay, hasVideo, videoPlaying, animating }: {
  form: { name: string; age: number; wish: string; tags: string[]; mood: string; city: string }
  setForm: React.Dispatch<React.SetStateAction<{ name: string; age: number; wish: string; tags: string[]; mood: string; city: string }>>
  onMagic: () => void
  createRunning: boolean
  cardStage: 'hidden' | 'generating' | 'ready'
  cardStageLabel: string
  cardData: { gift: string; model: string; bg: string; pngUrl?: string; videoUrl?: string } | null
  onAnimate: () => void
  onPlay: () => void
  hasVideo: boolean
  videoPlaying: boolean
  animating: boolean
}) {
  const inputStyle: React.CSSProperties = {
    width: '100%', height: 40, border: '1px solid rgba(0,0,0,.15)', borderRadius: 6, padding: '0 12px',
    fontSize: 15, fontFamily: 'inherit', color: 'rgba(0,0,0,.85)', background: 'white', outline: 'none',
    boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 500, color: 'rgba(0,0,0,.6)', marginBottom: 5, display: 'block' }
  const sectionCard: React.CSSProperties = { background: 'white', border: '1px solid rgba(0,0,0,.15)', borderRadius: 8, boxShadow: '0 4px 12px -2px rgba(0,0,0,.12)', padding: '16px 20px 20px', marginBottom: 20 }

  return (
    <div>
      {/* Kid details card */}
      <div style={sectionCard}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
          <div style={{ width: 4, height: 16, background: 'rgb(45,139,93)', borderRadius: 2 }} />
          <span style={{ fontSize: 17, fontWeight: 600 }}>Kid Details</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 20px' }}>
          <div>
            <label style={labelStyle}>Name</label>
            <input style={inputStyle} placeholder="e.g. Emma" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div>
            <label style={labelStyle}>Age</label>
            <input style={inputStyle} type="number" min={1} max={14} value={form.age} onChange={e => setForm(f => ({ ...f, age: Number(e.target.value) }))} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Christmas Wish</label>
            <textarea
              style={{ ...inputStyle, height: 72, padding: '10px 12px', resize: 'none', lineHeight: '21px' }}
              placeholder="What does this kid wish for most this Christmas?"
              value={form.wish}
              onChange={e => setForm(f => ({ ...f, wish: e.target.value }))}
            />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Interests</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ITAGS.map(tag => (
                <TagChip key={tag.id} tag={tag} selected={form.tags.includes(tag.id)} onClick={() => {
                  setForm(f => ({ ...f, tags: f.tags.includes(tag.id) ? f.tags.filter(t => t !== tag.id) : [...f.tags, tag.id] }))
                }} />
              ))}
            </div>
          </div>
          <div>
            <label style={labelStyle}>Mood for music</label>
            <select style={{ ...inputStyle, cursor: 'pointer' }} value={form.mood} onChange={e => setForm(f => ({ ...f, mood: e.target.value }))}>
              {MOODS.map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>City</label>
            <input style={inputStyle} placeholder="e.g. Oslo" value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} />
          </div>
        </div>
        {/* Magic button */}
        <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={onMagic} disabled={createRunning || animating} style={{
            height: 44, border: 'none', background: createRunning || animating ? 'rgba(255,190,92,.5)' : 'rgb(255,190,92)',
            color: 'rgba(0,0,0,.75)', borderRadius: 6, padding: '0 24px', fontSize: 15, fontWeight: 600,
            cursor: createRunning || animating ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 8,
            opacity: createRunning || animating ? 0.5 : 1,
          }}>✨ Magic</button>
          <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)' }}>
            POST /api/cards · llm → image → render
          </span>
        </div>
      </div>
      {/* Gift card output */}
      <GiftCard
        stage={cardStage}
        form={form}
        cardData={cardData}
        stage2={cardStageLabel}
        onAnimate={onAnimate}
        onPlay={onPlay}
        hasVideo={hasVideo}
        videoPlaying={videoPlaying}
      />
    </div>
  )
}

// ── Batch Tab ─────────────────────────────────────────────────────────────────

function BatchStatusPill({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string; label: string }> = {
    queued: { bg: 'rgba(0,0,0,.07)', text: 'rgba(0,0,0,.45)', label: 'queued' },
    card: { bg: 'rgba(54,151,241,.12)', text: 'rgb(54,151,241)', label: 'card' },
    video: { bg: 'rgba(48,170,110,.12)', text: 'rgb(48,170,110)', label: 'video' },
    failed: { bg: 'rgba(233,3,58,.1)', text: 'rgb(233,3,58)', label: 'failed' },
  }
  const c = cfg[status] ?? cfg.queued
  return <span style={{ background: c.bg, color: c.text, borderRadius: 4, padding: '2px 8px', fontSize: 12, fontWeight: 500 }}>{c.label}</span>
}

function BatchTab({ batchKids, batchLoaded, onLoad, onRun, batchRunning, batchDone, batchSummary, metrics, realMode }: {
  batchKids: Kid[]; batchLoaded: boolean; onLoad: () => void; onRun: () => void
  batchRunning: boolean; batchDone: boolean
  batchSummary: { done: number; failed: number; skipped: number; gpuTime: string; cost: string; onDemand: string; saved: string; savedPct: string } | null
  metrics?: { kids: string; jobs: string; perJob: string; kidsSub: string; jobsSub: string; perJobSub: string }
  realMode?: boolean
}) {
  const sectionCard: React.CSSProperties = { background: 'white', border: '1px solid rgba(0,0,0,.15)', borderRadius: 8, boxShadow: '0 4px 12px -2px rgba(0,0,0,.12)', padding: '16px 20px 20px', marginBottom: 20 }
  const visibleKids = batchKids.slice(0, 6)
  const extra = batchKids.length - 6

  return (
    <div>
      <div style={sectionCard}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <div style={{ width: 4, height: 16, background: 'rgb(45,139,93)', borderRadius: 2 }} />
          <span style={{ fontSize: 17, fontWeight: 600 }}>{realMode ? 'Published GiftCards' : 'Kids List'}</span>
        </div>
        {!batchLoaded ? (
          <div
            onClick={onLoad}
            style={{
              border: '1.5px dashed rgba(0,0,0,.2)', borderRadius: 8, padding: '36px 20px', textAlign: 'center',
              cursor: 'pointer', color: 'rgba(0,0,0,.45)', fontSize: 14, transition: 'all 0.15s',
            }}
          >
            <div style={{ fontSize: 28, marginBottom: 8 }}>{realMode ? '🎁' : '📂'}</div>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>{realMode ? 'Load published GiftCards' : 'Drop kids.csv here'}</div>
            <div style={{ fontSize: 12.5, fontFamily: 'JetBrains Mono,Menlo,monospace' }}>
              {realMode ? 'GET /api/wall · cards/{id}/card.png' : 'or click to load 20 sample kids'}
            </div>
          </div>
        ) : (
          <>
            {/* Table */}
            <div style={{ border: '1px solid rgba(0,0,0,.1)', borderRadius: 6, overflow: 'hidden', marginBottom: 16 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
                <thead>
                  <tr style={{ background: 'rgba(0,0,0,.03)', borderBottom: '1px solid rgba(0,0,0,.1)' }}>
                    {['Name','Age','Wish','Mood','Status'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'rgba(0,0,0,.55)', fontSize: 12 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleKids.map((k, i) => (
                    <tr key={k.id} style={{ borderBottom: i < visibleKids.length - 1 ? '1px solid rgba(0,0,0,.06)' : undefined }}>
                      <td style={{ padding: '9px 12px', fontWeight: 500 }}>{k.name}</td>
                      <td style={{ padding: '9px 12px', color: 'rgba(0,0,0,.55)' }}>{k.age}</td>
                      <td style={{ padding: '9px 12px', color: 'rgba(0,0,0,.6)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k.wish}</td>
                      <td style={{ padding: '9px 12px', color: 'rgba(0,0,0,.55)' }}>{k.mood}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <BatchStatusPill status={k.batchStatus ?? 'queued'} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {extra > 0 && (
                <div style={{ padding: '8px 12px', color: 'rgba(0,0,0,.4)', fontSize: 13, borderTop: '1px solid rgba(0,0,0,.06)', fontStyle: 'italic' }}>… {extra} more rows</div>
              )}
            </div>
            {/* Metric tiles */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
              {[
                { label: realMode ? 'Cards' : 'Kids', value: metrics?.kids ?? '20', sub: metrics?.kidsSub ?? 'sample CSV' },
                { label: 'GPU jobs', value: metrics?.jobs ?? '4', sub: metrics?.jobsSub ?? 'H100 · preemptible' },
                { label: 'Per job', value: metrics?.perJob ?? '5 kids', sub: metrics?.perJobSub ?? '~13 s · $0.09' },
              ].map(tile => (
                <div key={tile.label} style={{ flex: 1, border: '1px solid rgba(0,0,0,.1)', borderRadius: 6, padding: '12px 16px', background: 'rgba(0,0,0,.02)' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'rgba(0,0,0,.4)', letterSpacing: '0.05em', marginBottom: 4 }}>{tile.label.toUpperCase()}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: 'rgba(0,0,0,.85)' }}>{tile.value}</div>
                  <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)', marginTop: 2 }}>{tile.sub}</div>
                </div>
              ))}
            </div>
            {/* Run button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <button onClick={onRun} disabled={batchRunning} style={{
                height: 44, border: 'none', background: batchRunning ? 'rgba(255,190,92,.5)' : 'rgb(255,190,92)',
                color: 'rgba(0,0,0,.75)', borderRadius: 6, padding: '0 24px', fontSize: 15, fontWeight: 600,
                cursor: batchRunning ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: 8, opacity: batchRunning ? 0.6 : 1,
              }}>❄️ Let it snow</button>
              <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)' }}>santa animate_batch --jobs 4</span>
            </div>
          </>
        )}
      </div>
      {/* Summary */}
      {batchDone && batchSummary && (
        <div className="fadein" style={{ ...sectionCard, background: 'rgba(48,170,110,.07)', border: '1.5px solid rgba(48,170,110,.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <div style={{ width: 4, height: 16, background: 'rgb(48,170,110)', borderRadius: 2 }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'rgb(48,170,110)', fontFamily: 'JetBrains Mono,Menlo,monospace' }}>run_summary.json</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[
              { label: 'Videos done', value: `${batchSummary.done}`, color: 'rgb(48,170,110)' },
              { label: 'Failed', value: `${batchSummary.failed}`, color: 'rgb(233,3,58)' },
              { label: 'Skipped', value: `${batchSummary.skipped}`, color: 'rgba(0,0,0,.45)' },
              { label: 'GPU time', value: batchSummary.gpuTime, color: 'rgba(0,0,0,.75)' },
              { label: 'Cost (preemptible)', value: batchSummary.cost, color: 'rgb(45,139,93)' },
              { label: 'On-demand equiv.', value: batchSummary.onDemand, color: 'rgba(0,0,0,.55)' },
              { label: 'Saved', value: batchSummary.saved, color: 'rgb(45,139,93)' },
              { label: 'Savings', value: batchSummary.savedPct, color: 'rgb(45,139,93)' },
            ].map(m => (
              <div key={m.label}>
                <div style={{ fontSize: 11, color: 'rgba(0,0,0,.45)', fontWeight: 500, marginBottom: 2 }}>{m.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: m.color }}>{m.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Gallery Tab ───────────────────────────────────────────────────────────────

function GalleryTile({ kid, selected, onClick }: { kid: Kid; selected: boolean; onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        border: selected ? '2px solid rgb(45,139,93)' : '1px solid rgba(0,0,0,.12)', borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
        background: 'white', boxShadow: hovered || selected ? '0 6px 18px -4px rgba(0,0,0,.18)' : '0 2px 8px -2px rgba(0,0,0,.1)',
        transform: hovered ? 'translateY(-2px)' : undefined,
        transition: 'all 0.18s ease',
      }}
    >
      <div style={{ width: '100%', paddingTop: '100%', position: 'relative', background: kid.bg }}>
        {kid.pngUrl ? (
          <img src={kid.pngUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
          <div style={{ fontSize: 28 }}>🎁</div>
          <div style={{ fontSize: 10, fontFamily: 'JetBrains Mono,Menlo,monospace', color: 'rgba(0,0,0,.3)', textAlign: 'center', padding: '0 8px' }}>cards/{kid.id}.png</div>
        </div>
        )}
        {kid.hasVideo && (
          <div style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,.6)', color: 'white', fontSize: 10, fontWeight: 600, borderRadius: 3, padding: '2px 6px', letterSpacing: '0.04em' }}>VIDEO</div>
        )}
        {hovered && kid.hasVideo && (
          <div className="fadein" style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            {kid.videoUrl ? (
              <video src={kid.videoUrl} muted loop autoPlay playsInline style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <>
            <div style={{ width: 20, height: 20, border: '2px solid rgba(255,255,255,.6)', borderTopColor: 'white', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 10, color: 'rgba(255,255,255,.7)' }}>videos/{kid.id}.mp4</div>
              </>
            )}
          </div>
        )}
      </div>
      <div style={{ padding: '10px 12px' }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{kid.name}, {kid.age}</div>
        <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)', marginTop: 1 }}>{kid.city}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 6 }}>
          {kid.tags.slice(0, 2).map(tid => {
            const t = tagById(tid)
            return t ? <span key={tid} style={{ background: t.light, color: t.color, fontSize: 11, fontWeight: 500, borderRadius: 3, padding: '1px 5px' }}>{t.label}</span> : null
          })}
        </div>
      </div>
    </div>
  )
}

function GalleryPreview({ kid, realMode, onRealMode }: {
  kid: Kid | null
  realMode: boolean
  onRealMode: (v: boolean) => void
}) {
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    setPlaying(false)
  }, [kid?.id])

  return (
    <aside style={{ width: 720, display: 'flex', flexDirection: 'column', borderLeft: '2px solid rgba(0,0,0,.15)', background: 'rgb(242,237,228)', flexShrink: 0 }}>
      <div style={{ background: 'white', borderBottom: '1px solid rgba(0,0,0,.1)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: kid ? 'rgb(45,139,93)' : 'rgba(0,0,0,.2)', flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'rgba(0,0,0,.7)' }}>GiftCard · preview</span>
        <div style={{ display: 'flex', border: '1px solid rgba(0,0,0,.15)', borderRadius: 6, overflow: 'hidden' }}>
          {([['Sim', false], ['Real', true]] as const).map(([label, value]) => {
            const active = realMode === value
            return (
              <button key={label} onClick={() => onRealMode(value)} style={{
                border: 'none', padding: '3px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
                cursor: 'pointer', fontFamily: 'inherit',
                background: active ? (value ? 'rgb(45,139,93)' : 'rgb(233,174,86)') : 'white',
                color: active ? (value ? 'white' : 'rgba(0,0,0,.8)') : 'rgba(0,0,0,.45)',
              }}>{label}</button>
            )
          })}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, background: 'rgba(0,0,0,.07)', borderRadius: 4, padding: '2px 7px', color: 'rgba(0,0,0,.5)', fontWeight: 500 }}>Gallery</span>
          {kid && (
            <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)' }}>{kid.id}</span>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', background: 'white', padding: 20 }}>
        {!kid ? (
          <div style={{ border: '1.5px dashed rgba(0,0,0,.15)', borderRadius: 8, padding: '48px 24px', textAlign: 'center', color: 'rgba(0,0,0,.35)', fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 13 }}>
            Select a GiftCard from the Gallery
          </div>
        ) : (
          <div className="fadein" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{
              width: '100%', aspectRatio: '1', borderRadius: 8, overflow: 'hidden', position: 'relative',
              background: kid.bg, borderTop: '4px solid rgb(45,139,93)',
            }}>
              {playing && kid.videoUrl ? (
                <video src={kid.videoUrl} autoPlay controls playsInline style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : kid.pngUrl ? (
                <img src={kid.pngUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <div style={{ fontSize: 48 }}>🎁</div>
                  <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 11, color: 'rgba(0,0,0,.3)', textAlign: 'center', lineHeight: '16px' }}>
                    image placeholder<br />1024×1024
                  </div>
                </div>
              )}
            </div>

            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>Merry Christmas, {kid.name}! 🎄</div>
              <div style={{ fontSize: 13, color: 'rgba(0,0,0,.45)', marginTop: 4 }}>
                Age {kid.age}{kid.city ? ` · ${kid.city}` : ''}{kid.mood ? ` · ${kid.mood}` : ''}
              </div>
            </div>

            <div style={{ fontSize: 14, color: 'rgba(0,0,0,.65)', lineHeight: '21px' }}>"{kid.wish}"</div>

            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {kid.gift && (
                <span style={{ background: 'rgba(45,139,93,.12)', color: 'rgb(45,139,93)', borderRadius: 4, padding: '4px 10px', fontSize: 13, fontWeight: 500 }}>🎁 Gift: {kid.gift}</span>
              )}
              {kid.tags.map(tid => {
                const t = tagById(tid)
                return t ? <span key={tid} style={{ background: t.light, color: t.color, borderRadius: 4, padding: '4px 10px', fontSize: 13, fontWeight: 500 }}>{t.label}</span> : null
              })}
            </div>

            <div style={{ paddingTop: 12, borderTop: '1px solid rgba(0,0,0,.08)' }}>
              {kid.hasVideo ? (
                <button onClick={() => setPlaying(v => !v)} style={{
                  border: 'none', background: 'rgb(45,139,93)', color: 'white', borderRadius: 6, padding: '10px 20px',
                  fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                }}>{playing ? '⏹ Stop' : '▶ Play video gift card'}</button>
              ) : (
                <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12.5, color: 'rgba(0,0,0,.4)' }}>Image card only. Run Animate to add a video.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

function GalleryTab({ gallery, selectedId, onSelect }: {
  gallery: Kid[]
  selectedId: string | null
  onSelect: (id: string | null) => void
}) {
  const [ageFilter, setAgeFilter] = useState('all')
  const [tagFilter, setTagFilter] = useState('all')

  const filtered = gallery
    .filter(k => {
      if (ageFilter === '3-5' && !(k.age >= 3 && k.age <= 5)) return false
      if (ageFilter === '6-8' && !(k.age >= 6 && k.age <= 8)) return false
      if (ageFilter === '9-12' && !(k.age >= 9 && k.age <= 12)) return false
      if (tagFilter !== 'all' && !k.tags.includes(tagFilter)) return false
      return true
    })
    .slice()
    .sort((a, b) => Number(b.hasVideo) - Number(a.hasVideo))

  const filterBtn = (label: string, value: string, current: string, onClick: () => void) => (
    <button key={value} onClick={onClick} style={{
      border: 'none', background: current === value ? 'rgb(233,174,86)' : 'rgba(0,0,0,.07)',
      color: current === value ? 'rgba(0,0,0,.8)' : 'rgba(0,0,0,.55)',
      borderRadius: 20, padding: '5px 14px', fontSize: 13, fontWeight: 500,
      cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
    }}>{label}</button>
  )

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ width: 4, height: 20, background: 'rgb(45,139,93)', borderRadius: 2 }} />
        <span style={{ fontSize: 17, fontWeight: 600 }}>Gallery</span>
        <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)', marginLeft: 4 }}>GET /api/wall · {filtered.length} of {gallery.length}</span>
      </div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          {[['All','all'],['3–5','3-5'],['6–8','6-8'],['9–12','9-12']].map(([label,value]) =>
            filterBtn(label, value, ageFilter, () => setAgeFilter(value))
          )}
        </div>
        <div style={{ width: 1, background: 'rgba(0,0,0,.12)', margin: '0 4px' }} />
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {filterBtn('All', 'all', tagFilter, () => setTagFilter('all'))}
          {ITAGS.map(t => (
            <button key={t.id} onClick={() => setTagFilter(t.id === tagFilter ? 'all' : t.id)} style={{
              border: 'none', background: tagFilter === t.id ? t.color : t.light,
              color: tagFilter === t.id ? 'white' : t.color,
              borderRadius: 20, padding: '5px 12px', fontSize: 12.5, fontWeight: 500,
              cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
            }}>{t.label}</button>
          ))}
        </div>
      </div>
      {/* Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 14 }}>
        {filtered.map(kid => (
          <GalleryTile
            key={kid.id}
            kid={kid}
            selected={selectedId === kid.id}
            onClick={() => onSelect(selectedId === kid.id ? null : kid.id)}
          />
        ))}
      </div>
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState<Tab>('create')
  const [coldSana, setColdSana] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [gallery, setGallery] = useState<Kid[]>(GALLERY_SEED)
  const [gallerySelectedId, setGallerySelectedId] = useState<string | null>(null)
  const [realMode, setRealMode] = useState(false)

  // Create tab state
  const [form, setForm] = useState({ name: '', age: 8, wish: '', tags: [] as string[], mood: 'Playful', city: '' })
  const [createRun, setCreateRun] = useState<RunState>(emptyRun())
  const [cardStage, setCardStage] = useState<'hidden' | 'generating' | 'ready'>('hidden')
  const [cardStageLabel, setCardStageLabel] = useState('')
  const [cardData, setCardData] = useState<{ gift: string; model: string; bg: string; pngUrl?: string; videoUrl?: string } | null>(null)
  const [hasVideo, setHasVideo] = useState(false)
  const [animating, setAnimating] = useState(false)
  const [videoPlaying, setVideoPlaying] = useState(false)
  const lastKidId = useRef<string | null>(null)
  const simGallery = useRef<Kid[]>(GALLERY_SEED)
  const createRunRef = useRef<RunState>(emptyRun())

  // Batch tab state
  const [batchKids, setBatchKids] = useState<Kid[]>([])
  const [batchLoaded, setBatchLoaded] = useState(false)
  const [batchRun, setBatchRun] = useState<RunState>(emptyRun())
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchDone, setBatchDone] = useState(false)
  const [batchSummary, setBatchSummary] = useState<{ done: number; failed: number; skipped: number; gpuTime: string; cost: string; onDemand: string; saved: string; savedPct: string } | null>(null)
  const [batchMetrics, setBatchMetrics] = useState<{ kids: string; jobs: string; perJob: string; kidsSub: string; jobsSub: string; perJobSub: string } | undefined>(undefined)

  // Timer refs
  const createTimers = useRef<number[]>([])
  const batchTimers = useRef<number[]>([])
  const animTimers = useRef<number[]>([])
  const createT0 = useRef(0)
  const batchT0 = useRef(0)

  // Elapsed timers
  useEffect(() => {
    if (createRun.status !== 'running') return
    const id = window.setInterval(() => {
      setCreateRun(r => r.status === 'running' ? { ...r, elapsed: Date.now() - createT0.current } : r)
    }, 100)
    return () => window.clearInterval(id)
  }, [createRun.status])

  useEffect(() => {
    if (batchRun.status !== 'running') return
    const id = window.setInterval(() => {
      setBatchRun(r => r.status === 'running' ? { ...r, elapsed: Date.now() - batchT0.current } : r)
    }, 100)
    return () => window.clearInterval(id)
  }, [batchRun.status])

  // Card stage label cycling
  useEffect(() => {
    if (cardStage !== 'generating') return
    const labels = ['LLM: gift + wish', 'image gen: images.generate', 'pillow render → card.png']
    let i = 0
    setCardStageLabel(labels[0])
    const id = window.setInterval(() => { i = (i + 1) % labels.length; setCardStageLabel(labels[i]) }, 1600)
    return () => window.clearInterval(id)
  }, [cardStage])

  const refreshWall = async () => {
    const wall = await fetchWall()
    setGallery(wall.items.map(wallToKid))
    return wall
  }

  const applyWallToAnimate = (items: WallItem[]) => {
    setBatchKids(items.map(wallToKid))
    setBatchLoaded(true)
    const n = items.length
    const pending = items.filter(i => !i.has_video).length
    setBatchMetrics({
      kids: String(n), kidsSub: 'GET /api/wall',
      jobs: String(ANIMATE_JOBS), jobsSub: 'H100 · preemptible',
      perJob: n ? `${Math.ceil(n / ANIMATE_JOBS)} cards` : '—',
      perJobSub: pending ? `${pending} need video` : n ? 'all have video' : 'publish a GiftCard first',
    })
    setBatchRun(initialAnimateBatchRun('idle'))
  }

  const setMode = async (real: boolean) => {
    setRealMode(real)
    if (real) {
      simGallery.current = gallery
      try {
        const wall = await refreshWall()
        applyWallToAnimate(wall.items || [])
      } catch {
        setGallery(GALLERY_SEED)
        setBatchKids([])
        setBatchLoaded(false)
        setBatchRun(initialAnimateBatchRun('idle'))
      }
    } else {
      setGallery(simGallery.current.length ? simGallery.current : GALLERY_SEED)
    }
  }

  const runMagicReal = async () => {
    if (createRun.status === 'running') return
    createT0.current = Date.now()
    setCardStage('generating')
    setCardData(null)
    setHasVideo(false)
    setVideoPlaying(false)
    const extras = [
      form.wish,
      form.tags.length ? `Interests: ${form.tags.join(', ')}` : '',
      form.city ? `City: ${form.city}` : '',
    ].filter(Boolean).join('. ')
    const initial = initialMagicRun()
    createRunRef.current = initial
    setCreateRun(initial)
    try {
      const body = { name: form.name || 'Kid', age: form.age, wishlist: extras ? [extras] : [] }
      const data = await createCardStream(body, (event) => {
        createRunRef.current = applyCardProgress(createRunRef.current, event)
        flushSync(() => setCreateRun({ ...createRunRef.current, nodes: { ...createRunRef.current.nodes } }))
      })
      const elapsed = Date.now() - createT0.current
      setCreateRun(r => ({
        ...r,
        status: 'done',
        elapsed,
        nodes: {
          ...r.nodes,
          santa: { ...r.nodes.santa, status: 'done', meta: `200 · ${(elapsed / 1000).toFixed(1)} s` },
        },
      }))
      const gift = data.card.recommendation.gifts[0] || 'Gift'
      const pngUrl = data.png_url || undefined
      lastKidId.current = data.card.kid_id
      const tagBg = form.tags[0] ? (tagById(form.tags[0])?.light ?? BGS[0]) : bgForId(data.card.kid_id)
      const imageStep = data.steps.find(s => s.role === 'image')
      setCardData({
        gift,
        model: imageStep ? `${imageStep.model}${imageStep.fallback ? ' (fallback)' : ''}` : (data.card.image.model_version || ''),
        bg: tagBg,
        pngUrl,
      })
      setCardStage('ready')
      const kid: Kid = {
        id: data.card.kid_id, name: form.name || 'Kid', age: form.age, wish: form.wish,
        tags: form.tags, mood: form.mood, city: form.city, bg: tagBg, hasVideo: false, gift, pngUrl,
      }
      setGallery(prev => [kid, ...prev.filter(k => k.id !== kid.id)])
    } catch (err) {
      setCreateRun(r => ({
        ...r, status: 'done',
        nodes: { ...r.nodes, santa: { ...r.nodes.santa, status: 'failed', meta: String(err) } },
      }))
      setCardStage('hidden')
    }
  }

  const runAnimateReal = async () => {
    const kidId = lastKidId.current
    if (!kidId || animating) return
    setAnimating(true)
    createT0.current = Date.now()
    setCreateRun({
      title: 'Animate · video card', status: 'running',
      nodes: {
        santa: nodeWithStatus('santa', 'active', { sub: 'POST /api/cards/{id}/animate' }),
        wan: nodeWithStatus('wan', 'active', { sub: 'video · mood-bank' }),
        mux: nodeWithStatus('mux', 'pending'),
        bucket: nodeWithStatus('bucket', 'idle', { sub: 'PUT cards/{id}/video.mp4' }),
      },
      levels: [['santa'], ['wan'], ['mux'], ['bucket']],
      log: [], elapsed: 0,
    })
    try {
      const data = await animateCard(kidId)
      const elapsed = Date.now() - createT0.current
      setCreateRun({
        title: 'Animate · video card', status: 'done',
        nodes: {
          santa: nodeWithStatus('santa', 'done', { sub: 'POST /api/cards/{id}/animate', meta: `${(elapsed / 1000).toFixed(1)} s` }),
          wan: nodeWithStatus('wan', 'done', { sub: 'video · mood-bank' }),
          mux: nodeWithStatus('mux', 'done'),
          bucket: nodeWithStatus('bucket', 'done', { sub: 'PUT cards/{id}/video.mp4' }),
        },
        levels: [['santa'], ['wan'], ['mux'], ['bucket']],
        log: [], elapsed,
      })
      setHasVideo(true)
      setCardData(cd => cd ? { ...cd, videoUrl: data.video_url } : cd)
      setGallery(prev => prev.map(k => k.id === kidId ? { ...k, hasVideo: true, videoUrl: data.video_url } : k))
    } catch (err) {
      setCreateRun(r => ({
        ...r, status: 'done',
        nodes: { ...r.nodes, santa: { ...r.nodes.santa, status: 'failed', meta: String(err) }, wan: { ...r.nodes.wan, status: 'failed' } },
      }))
    } finally {
      setAnimating(false)
    }
  }

  const loadKidsReal = async () => {
    try {
      const wall = await fetchWall()
      applyWallToAnimate(wall.items || [])
    } catch (err) {
      const hint = shortError(err)
      const nodes = animateBatchNodes()
      nodes.santa = { ...nodes.santa, status: 'failed', meta: hint }
      nodes.storecards = { ...nodes.storecards, status: 'failed', meta: hint }
      setBatchRun({
        title: 'Published GiftCards', status: 'done',
        nodes, levels: animateBatchLevels(), log: [], elapsed: 0,
      })
    }
  }

  const runBatchReal = async () => {
    if (batchRun.status === 'running') return
    batchT0.current = Date.now()
    setBatchRunning(true); setBatchDone(false); setBatchSummary(null)
    const starting = initialAnimateBatchRun('running')
    starting.nodes.santa = { ...starting.nodes.santa, status: 'active' }
    starting.nodes.storecards = { ...starting.nodes.storecards, status: 'active' }
    setBatchRun(starting)
    try {
      const submitted = await submitRun(ANIMATE_JOBS)
      const nJobs = Math.max(submitted.jobs.length, 1)
      const nodes = animateBatchNodes(nJobs)
      nodes.santa = { ...nodes.santa, status: 'active', sub: `run ${submitted.run_id}`, meta: `${submitted.kids.length} cards` }
      nodes.storecards = { ...nodes.storecards, status: 'done', meta: `${submitted.kids.length} cards inventoried` }
      submitted.jobs.forEach((j, i) => {
        const id = `job${i}`
        nodes[id] = {
          id, label: `Job ${i}`, kind: 'job',
          sub: `${(j.ids || []).length} cards · ${(j.job_id || '').slice(0, 12)}`,
          status: jobNodeStatus(j.state || 'PENDING'),
          meta: j.state,
        }
      })
      if (submitted.jobs.length === 0) {
        nodes.job0 = { ...nodes.job0, status: 'skipped', meta: 'nothing to submit · videos exist' }
        nodes.storevideos = { ...nodes.storevideos, status: 'done', meta: 'all skipped' }
        nodes.santa = { ...nodes.santa, status: 'done' }
      }
      setBatchKids(kids => kids.map(k => ({
        ...k,
        batchStatus: (submitted.kids || []).includes(k.id) ? (k.hasVideo ? 'video' : 'card') : (k.batchStatus ?? 'queued'),
      })))
      setBatchRun({
        title: `Let it snow · ${submitted.kids.length} cards · ${submitted.jobs.length} jobs`,
        status: submitted.jobs.length === 0 ? 'done' : 'running',
        nodes, levels: animateBatchLevels(nJobs),
        log: [], elapsed: Date.now() - batchT0.current,
      })
      if (submitted.jobs.length === 0) {
        setBatchRunning(false)
        setBatchDone(true)
        return
      }
      const poll = async () => {
        const status = await fetchRun(submitted.run_id)
        const mapped = status.jobs.map(j => jobNodeStatus(j.state || ''))
        const allDone = status.jobs.length > 0 && mapped.every(s => ['done', 'failed', 'preempted', 'skipped'].includes(s))
        setBatchRun(r => {
          const next = { ...r.nodes }
          status.jobs.forEach((j, i) => {
            const id = `job${i}`
            if (next[id]) next[id] = { ...next[id], status: jobNodeStatus(j.state || ''), meta: j.state }
          })
          if (allDone) {
            next.storevideos = { ...next.storevideos, status: mapped.some(s => s === 'done') ? 'done' : 'failed', meta: 'cards/{id}/video.mp4' }
          }
          return {
            ...r,
            nodes: { ...next, santa: { ...next.santa, status: allDone ? 'done' : 'active' } },
            status: allDone ? 'done' : 'running',
            elapsed: Date.now() - batchT0.current,
          }
        })
        if (status.summary?.totals) {
          const t = status.summary.totals
          const onDemand = t.on_demand_cost_usd ?? 0
          const saved = status.summary.savings_usd ?? 0
          setBatchSummary({
            done: t.done ?? 0, failed: t.failed ?? 0, skipped: t.skipped ?? 0,
            gpuTime: `${Math.round(t.run_s ?? 0)} s`,
            cost: `$${(t.cost_usd ?? 0).toFixed(2)}`,
            onDemand: `$${onDemand.toFixed(2)}`,
            saved: `$${saved.toFixed(2)}`,
            savedPct: onDemand ? `${Math.round((saved / onDemand) * 100)}%` : '—',
          })
          setBatchDone(true)
          setBatchRunning(false)
          await refreshWall().catch(() => undefined)
          return
        }
        if (allDone) {
          setBatchRunning(false)
          setBatchDone(true)
          await refreshWall().catch(() => undefined)
          return
        }
        window.setTimeout(() => { void poll() }, 4000)
      }
      void poll()
    } catch (err) {
      const hint = shortError(err)
      const tls = /TLS failed|CERTIFICATE_VERIFY_FAILED|SSL/i.test(hint)
      const empty = /cards\//i.test(hint) && /publish/i.test(hint)
      setBatchRun(r => {
        const nodes = { ...r.nodes }
        nodes.santa = { ...nodes.santa, status: 'failed', meta: hint }
        nodes.storecards = {
          ...nodes.storecards,
          status: 'failed',
          meta: tls ? hint : empty ? 'No GiftCards in cards/' : hint,
        }
        return { ...r, status: 'done', nodes }
      })
      setBatchRunning(false)
    }
  }

  // ── Magic simulation ──────────────────────────────────────────────────────────
  const runMagic = () => {
    if (createRun.status === 'running') return
    createTimers.current.forEach(clearTimeout)
    createTimers.current = []
    createT0.current = Date.now()
    setCardStage('generating')
    setCardData(null)
    setHasVideo(false)
    setVideoPlaying(false)

    const S = (ms: number) => ms / speed
    const at = (ms: number, fn: () => void) => { const id = window.setTimeout(fn, S(ms)); createTimers.current.push(id) }

    const tagBg = form.tags[0] ? (tagById(form.tags[0])?.light ?? BGS[0]) : BGS[Math.floor(Math.random() * BGS.length)]
    const kidName = form.name || 'Kid'
    const isCold = coldSana

    const nodes: Record<string, RNode> = {
      santa: nodeWithStatus('santa', 'active'),
      token: nodeWithStatus('token', 'idle'),
      sana: nodeWithStatus('sana', 'idle'),
      ...(isCold ? { openai: nodeWithStatus('openai', 'idle') } : {}),
      bucket: nodeWithStatus('bucket', 'idle', { sub: 'PUT cards/{id}.png' }),
    }

    setCreateRun({
      title: 'Magic · single card', status: 'running',
      nodes, levels: isCold ? [['santa'],['token'],['sana','openai'],['bucket']] : [['santa'],['token'],['sana'],['bucket']],
      log: [{ t: 0, mark: '→', text: `POST /api/cards {name:"${kidName}", age:${form.age}, mood:${form.mood}}`, tone: 'blue' }],
      elapsed: 0,
    })

    at(500, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, token: { ...r.nodes.token, status: 'active' } }, log: [...r.log, { t: 500, mark: '→', text: 'chat.completions model=gpt-oss-120b (gift_rec, wish)', tone: 'blue' }] })))
    at(2400, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, token: { ...r.nodes.token, status: 'done', meta: '1.9 s · openai/gpt-oss-120b' }, sana: { ...r.nodes.sana, status: 'active' } }, log: [...r.log, { t: 2400, mark: '←', text: 'chat.completions → "Cosmic Explorer Kit" · 1.9 s', tone: 'green' }, { t: 2400, mark: '→', text: 'images.generate size=1024x1024 seed=42', tone: 'blue' }] })))

    if (isCold) {
      at(4200, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, sana: { ...r.nodes.sana, status: 'failed', meta: '503 · endpoint cold (scaling 0→1)' }, openai: { ...r.nodes.openai!, status: 'active' } }, log: [...r.log, { t: 4200, mark: '×', text: 'Sana 503 · endpoint cold (scaling 0→1)', tone: 'red' }, { t: 4200, mark: '!', text: 'Resilient: primary failed → fallback gpt-image-1 (SANTA_FALLBACK=auto)', tone: 'amber' }, { t: 4200, mark: '→', text: 'gpt-image-1 images.generate (fallback)', tone: 'blue' }] })))
      at(8200, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, openai: { ...r.nodes.openai!, status: 'done', meta: '4.0 s · gpt-image-1' }, bucket: { ...r.nodes.bucket, status: 'active' } }, log: [...r.log, { t: 8200, mark: '←', text: 'gpt-image-1 → b64_json 1.2 MB · 4.0 s', tone: 'green' }, { t: 8200, mark: '·', text: 'render.py: Pillow → card.png + card.html · 0.3 s', tone: 'muted' }, { t: 8200, mark: '→', text: 'PUT cards/c_8f2a.png', tone: 'blue' }] })))
      at(9600, () => {
        setCreateRun(r => ({ ...r, status: 'done', nodes: { ...r.nodes, bucket: { ...r.nodes.bucket, status: 'done', meta: '1.3 s · cards/c_8f2a.png' }, santa: { ...r.nodes.santa, status: 'done', meta: '200 {id, card_url} · 9.6 s total' } }, log: [...r.log, { t: 9600, mark: '✓', text: 'PUT cards/c_8f2a.png → 200 OK', tone: 'green' }, { t: 9600, mark: '✓', text: 'santa-service → 200 · attribution: gpt-image-1 (fallback) · 9.6 s', tone: 'green' }] }))
        const cd = { gift: 'Cosmic Explorer Kit', model: 'gpt-image-1 (fallback)', bg: tagBg }
        setCardData(cd); setCardStage('ready')
        setGallery(prev => [{ id: 'c_8f2a', name: kidName, age: form.age, wish: form.wish, tags: form.tags, mood: form.mood, city: form.city, bg: tagBg, hasVideo: false, gift: 'Cosmic Explorer Kit' }, ...prev.filter(k => k.id !== 'c_8f2a')])
      })
    } else {
      at(5100, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, sana: { ...r.nodes.sana, status: 'done', meta: '2.7 s · Sana_1600M_1024px_diffusers' }, bucket: { ...r.nodes.bucket, status: 'active' } }, log: [...r.log, { t: 5100, mark: '←', text: 'Sana → b64_json 1.2 MB · 2.7 s', tone: 'green' }, { t: 5100, mark: '·', text: 'render.py: Pillow → card.png + card.html · 0.3 s', tone: 'muted' }, { t: 5100, mark: '→', text: 'PUT cards/c_8f2a.png', tone: 'blue' }] })))
      at(6400, () => {
        setCreateRun(r => ({ ...r, status: 'done', nodes: { ...r.nodes, bucket: { ...r.nodes.bucket, status: 'done', meta: '1.3 s · cards/c_8f2a.png' }, santa: { ...r.nodes.santa, status: 'done', meta: '200 {id, card_url} · 6.4 s' } }, log: [...r.log, { t: 6400, mark: '✓', text: 'PUT cards/c_8f2a.png → 200 OK', tone: 'green' }, { t: 6400, mark: '✓', text: 'santa-service → 200 {id:"c_8f2a", card_url} · 6.4 s', tone: 'green' }] }))
        setCardData({ gift: 'Cosmic Explorer Kit', model: 'Sana_1600M_1024px_diffusers', bg: tagBg }); setCardStage('ready')
        setGallery(prev => [{ id: 'c_8f2a', name: kidName, age: form.age, wish: form.wish, tags: form.tags, mood: form.mood, city: form.city, bg: tagBg, hasVideo: false, gift: 'Cosmic Explorer Kit' }, ...prev.filter(k => k.id !== 'c_8f2a')])
      })
    }
  }

  // ── Animate simulation ────────────────────────────────────────────────────────
  const runAnimate = () => {
    if (animating) return
    setAnimating(true)
    animTimers.current.forEach(clearTimeout); animTimers.current = []
    createT0.current = Date.now()

    const S = (ms: number) => ms / speed
    const at = (ms: number, fn: () => void) => { const id = window.setTimeout(fn, S(ms)); animTimers.current.push(id) }

    const animNodes: Record<string, RNode> = {
      santa: nodeWithStatus('santa', 'active', { sub: 'santa animate' }),
      wan: nodeWithStatus('wan', 'idle', { sub: 'POST /v1/videos · async', progress: 0 }),
      ace: nodeWithStatus('ace', 'idle', { sub: `text2music · mood=${form.mood}` }),
      mux: nodeWithStatus('mux', 'idle'),
      bucket: nodeWithStatus('bucket', 'idle', { sub: 'PUT videos/{id}.mp4' }),
    }

    setCreateRun({ title: 'Animate · video card', status: 'running', nodes: animNodes, levels: [['santa'],['wan','ace'],['mux'],['bucket']], log: [{ t: 0, mark: '→', text: `santa animate (mood=${form.mood}) → Wan + ACE-Step`, tone: 'blue' }], elapsed: 0 })

    at(400, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, status: 'active', meta: 'POST /v1/videos async queued', progress: 0 }, ace: { ...r.nodes.ace, status: 'active' } }, log: [...r.log, { t: 400, mark: '→', text: 'POST /v1/videos 832×480 fps=16 num_frames=81', tone: 'blue' }, { t: 400, mark: '→', text: `text2music mood=${form.mood} duration=8`, tone: 'blue' }] })))
    at(1200, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, meta: '202 {id:"vid_8f2a", status:"queued"} · polling', progress: 5 } }, log: [...r.log, { t: 1200, mark: '←', text: 'Wan 202 {id:"vid_8f2a", status:"queued"} · polling', tone: 'blue' }] })))
    at(3000, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, meta: 'poll: status:"processing" progress:20%', progress: 20 } }, log: [...r.log, { t: 3000, mark: '←', text: 'Wan poll → processing · 20%', tone: 'blue' }] })))
    at(4600, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, ace: { ...r.nodes.ace, status: 'done', meta: '4.2 s · mp3 128 KB' }, wan: { ...r.nodes.wan, meta: 'poll: progress:45%', progress: 45 } }, log: [...r.log, { t: 4600, mark: '←', text: 'ACE-Step → mp3 128 KB · 4.2 s', tone: 'green' }, { t: 4600, mark: '←', text: 'Wan poll → 45%', tone: 'blue' }] })))
    at(7000, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, meta: 'poll: progress:70%', progress: 70 } }, log: [...r.log, { t: 7000, mark: '←', text: 'Wan poll → 70%', tone: 'blue' }] })))
    at(9000, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, meta: 'poll: progress:95%', progress: 95 } }, log: [...r.log, { t: 9000, mark: '←', text: 'Wan poll → 95%', tone: 'blue' }] })))
    at(10600, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, wan: { ...r.nodes.wan, status: 'done', meta: '10.2 s · mp4 2.1 MB', progress: 100 }, mux: { ...r.nodes.mux, status: 'active' } }, log: [...r.log, { t: 10600, mark: '←', text: 'Wan → mp4 2.1 MB · 10.2 s', tone: 'green' }, { t: 10600, mark: '→', text: 'ffmpeg -i mp4 -i mp3 -shortest', tone: 'blue' }] })))
    at(11800, () => setCreateRun(r => ({ ...r, nodes: { ...r.nodes, mux: { ...r.nodes.mux, status: 'done', meta: '1.2 s · muxed 2.3 MB' }, bucket: { ...r.nodes.bucket, status: 'active' } }, log: [...r.log, { t: 11800, mark: '←', text: 'mux done · 1.2 s', tone: 'green' }, { t: 11800, mark: '→', text: 'PUT videos/v_8f2a.mp4', tone: 'blue' }] })))
    at(12700, () => {
      setCreateRun(r => ({ ...r, status: 'done', nodes: { ...r.nodes, bucket: { ...r.nodes.bucket, status: 'done', meta: 'videos/v_8f2a.mp4 · 0.9 s' }, santa: { ...r.nodes.santa, status: 'done', meta: `video ready · 832×480 · 16fps · ${form.mood.toLowerCase()} · 12.7 s` } }, log: [...r.log, { t: 12700, mark: '✓', text: 'PUT videos/v_8f2a.mp4 → 200 OK', tone: 'green' }, { t: 12700, mark: '✓', text: `animate done · 832×480 · 16 fps · 5 s · ${form.mood.toLowerCase()} track`, tone: 'green' }] }))
      setHasVideo(true); setAnimating(false)
      setGallery(prev => prev.map(k => k.id === 'c_8f2a' ? { ...k, hasVideo: true } : k))
    })
  }

  // ── Batch simulation ──────────────────────────────────────────────────────────
  const runBatch = () => {
    if (batchRun.status === 'running') return
    batchTimers.current.forEach(clearTimeout); batchTimers.current = []
    batchT0.current = Date.now()
    setBatchRunning(true); setBatchDone(false); setBatchSummary(null)
    setBatchKids(BATCH_SEED.map(k => ({ ...k, batchStatus: 'queued' as const })))

    const S = (ms: number) => ms / speed
    const at = (ms: number, fn: () => void) => { const id = window.setTimeout(fn, S(ms)); batchTimers.current.push(id) }

    const bn: Record<string, RNode> = {
      santa: { id: 'santa', label: 'santa-service', kind: 'service', sub: 'POST /api/cards/batch · 20 kids', status: 'active' },
      sana: nodeWithStatus('sana', 'idle', { sub: 'images.generate · ×20', progress: 0 }),
      storecards: { id: 'storecards', label: 'Object Storage', kind: 'bucket', sub: 'cards/ · chunks/ · runs/', status: 'idle' },
      job0: { id: 'job0', label: 'Job 0', kind: 'job', sub: 'santa-job:v2 · 5 kids · H100 preemptible', status: 'pending' },
      job1: { id: 'job1', label: 'Job 1', kind: 'job', sub: 'santa-job:v2 · 5 kids · H100 preemptible', status: 'pending' },
      job2: { id: 'job2', label: 'Job 2', kind: 'job', sub: 'santa-job:v2 · 5 kids · H100 preemptible', status: 'pending' },
      job3: { id: 'job3', label: 'Job 3', kind: 'job', sub: 'santa-job:v2 · 5 kids · H100 preemptible', status: 'pending' },
      storevideos: { id: 'storevideos', label: 'Object Storage', kind: 'bucket', sub: 'videos/ · summary.json', status: 'idle' },
    }

    setBatchRun({ title: 'Let it snow · 20 kids · 4 jobs', status: 'running', nodes: bn, levels: [['santa'],['sana'],['storecards'],['job0','job1','job2','job3'],['storevideos']], log: [{ t: 0, mark: '→', text: 'POST /api/cards/batch {kids:20, jobs:4}', tone: 'blue' }], elapsed: 0 })

    at(100, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, sana: { ...r.nodes.sana, status: 'active', progress: 0 } } })))

    for (let i = 0; i < 20; i++) {
      const t = 300 + i * 300
      const pct = Math.round((i + 1) / 20 * 100)
      const idx = i
      at(t, () => {
        setBatchKids(kids => kids.map((k, ki) => ki <= idx ? { ...k, batchStatus: 'card' as const } : k))
        setBatchRun(r => ({ ...r, nodes: { ...r.nodes, sana: { ...r.nodes.sana, progress: pct } }, log: idx % 5 === 4 ? [...r.log, { t, mark: '←', text: `cards ${idx + 1}/20 done · ${pct}%`, tone: 'green' }] : r.log }))
      })
    }

    at(6600, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, sana: { ...r.nodes.sana, status: 'done', progress: 100, meta: '20 cards · 6.6 s' }, storecards: { ...r.nodes.storecards, status: 'active' } }, log: [...r.log, { t: 6600, mark: '←', text: '200 {ids:[20]} · all cards done', tone: 'green' }] })))
    at(7600, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, storecards: { ...r.nodes.storecards, status: 'done', meta: 'chunks/0..3.json written' }, job0: { ...r.nodes.job0, status: 'pending', meta: 'nebius_jobs.create queued' }, job1: { ...r.nodes.job1, status: 'pending', meta: 'nebius_jobs.create queued' }, job2: { ...r.nodes.job2, status: 'pending', meta: 'nebius_jobs.create queued' }, job3: { ...r.nodes.job3, status: 'pending', meta: 'nebius_jobs.create queued' } }, log: [...r.log, { t: 7600, mark: '·', text: 'chunk → runs/{run}/chunks/{0..3}.json', tone: 'muted' }, { t: 7600, mark: '→', text: 'nebius_jobs.create ×4 · image santa-job:v2 · mount bucket → /data', tone: 'blue' }] })))
    at(9000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job0: { ...r.nodes.job0, status: 'scheduling' }, job1: { ...r.nodes.job1, status: 'scheduling' } }, log: [...r.log, { t: 9000, mark: '·', text: 'Job 0, 1 → SCHEDULING', tone: 'muted' }] })))
    at(10000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'scheduling' }, job3: { ...r.nodes.job3, status: 'scheduling' } }, log: [...r.log, { t: 10000, mark: '·', text: 'Job 2, 3 → SCHEDULING', tone: 'muted' }] })))
    at(11800, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job0: { ...r.nodes.job0, status: 'active', meta: 'loading weights /data/models…', progress: 0 }, job1: { ...r.nodes.job1, status: 'active', meta: 'loading weights…', progress: 0 } }, log: [...r.log, { t: 11800, mark: '·', text: 'Job 0, 1 RUNNING · weights load (pre-baked)', tone: 'muted' }] })))
    at(13000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'active', meta: 'loading weights…', progress: 0 }, job3: { ...r.nodes.job3, status: 'failed', meta: 'image pull timeout · exit 1' } }, log: [...r.log, { t: 13000, mark: '·', text: 'Job 2 RUNNING · loading weights', tone: 'muted' }, { t: 13000, mark: '×', text: 'Job 3 FAILED · image pull timeout · exit 1', tone: 'red' }] })))
    at(14000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job3: { ...r.nodes.job3, status: 'scheduling', meta: 'resubmitted' } }, log: [...r.log, { t: 14000, mark: '!', text: 'Job 3 resubmitted → SCHEDULING', tone: 'amber' }] })))

    // Job 0 cards (kids 0-4)
    for (let c = 0; c < 5; c++) {
      const tc = 14000 + c * 2600
      const ci = c
      at(tc, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job0: { ...r.nodes.job0, meta: `card ${ci + 1}/5 rendering…`, progress: (ci + 1) * 20 } } })); setBatchKids(kids => kids.map((k, ki) => ki === ci ? { ...k, batchStatus: 'video' as const } : k)) })
    }

    // Job 1 cards (kids 5-9, card 4 OOM)
    for (let c = 0; c < 3; c++) {
      const tc = 14000 + c * 2600
      const ci = c
      at(tc, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job1: { ...r.nodes.job1, meta: `card ${ci + 1}/5 rendering…`, progress: (ci + 1) * 20 } } })); setBatchKids(kids => kids.map((k, ki) => ki === 5 + ci ? { ...k, batchStatus: 'video' as const } : k)) })
    }
    at(21800, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job1: { ...r.nodes.job1, meta: 'card 4/5 rendering…', progress: 60 } } })); setBatchKids(kids => kids.map((k, ki) => ki === 5 + 3 ? { ...k, batchStatus: 'video' as const } : k)) })

    // Job 2 cards (kids 10-14), preempted after 2
    at(14000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, meta: 'card 1/5 rendering…', progress: 20 } } })))
    at(16600, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, meta: 'card 2/5 rendering…', progress: 40 } } })); setBatchKids(kids => kids.map((k, ki) => ki === 10 || ki === 11 ? { ...k, batchStatus: 'video' as const } : k)) })
    at(18000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'preempted', meta: 'node reclaimed · 2/5 written', progress: 40 } }, log: [...r.log, { t: 18000, mark: '!', text: 'Job 2 PREEMPTED · node reclaimed · 2/5 written', tone: 'amber' }] })))

    at(23400, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job1: { ...r.nodes.job1, meta: 'card 4: CUDA OOM · skipped, exit stays 0', progress: 60 } }, log: [...r.log, { t: 23400, mark: '!', text: 'Job 1 card 4: CUDA OOM on decode · skipped', tone: 'amber' }] })); setBatchKids(kids => kids.map((k, ki) => ki === 8 ? { ...k, batchStatus: 'failed' as const } : k)) })

    // Job 3 retry
    at(20000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job3: { ...r.nodes.job3, status: 'active', meta: 'loading weights (retry)…', progress: 0 } }, log: [...r.log, { t: 20000, mark: '·', text: 'Job 3 RUNNING (retry)', tone: 'muted' }] })))
    for (let c = 0; c < 5; c++) {
      const tc = 20000 + c * 2600
      const ci = c
      at(tc, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job3: { ...r.nodes.job3, meta: `card ${ci + 1}/5 rendering…`, progress: (ci + 1) * 20 } } })); setBatchKids(kids => kids.map((k, ki) => ki === 15 + ci ? { ...k, batchStatus: 'video' as const } : k)) })
    }

    // Job 2 resumes
    at(22000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'scheduling', meta: 'PENDING → SCHEDULING' } }, log: [...r.log, { t: 22000, mark: '·', text: 'Job 2 re-queued → SCHEDULING', tone: 'muted' }] })))
    at(24000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'active', meta: '2 skipped (exist) · 3 to go', progress: 40 } }, log: [...r.log, { t: 24000, mark: '·', text: 'Job 2 RUNNING · 2 skipped (exist) · 3 to go', tone: 'muted' }] })))
    for (let c = 2; c < 5; c++) {
      const tc = 24000 + (c - 2) * 2600
      const ci = c
      at(tc, () => { setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, meta: `card ${ci + 1}/5 rendering (resumed)…`, progress: (ci + 1) * 20 } } })); setBatchKids(kids => kids.map((k, ki) => ki === 10 + ci ? { ...k, batchStatus: 'video' as const } : k)) })
    }

    // Jobs completing
    at(27000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job0: { ...r.nodes.job0, status: 'done', meta: '5 done · 13.4 s · $0.09', progress: 100 } }, log: [...r.log, { t: 27000, mark: '✓', text: 'Job 0 SUCCEEDED · 5 done · 13.4 s · $0.09', tone: 'green' }] })))
    at(27500, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job1: { ...r.nodes.job1, status: 'done', meta: '4 done · 1 failed (OOM)', progress: 100 } }, log: [...r.log, { t: 27500, mark: '✓', text: 'Job 1 SUCCEEDED · 4 done · 1 failed (CUDA OOM)', tone: 'green' }] })))
    at(33000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job3: { ...r.nodes.job3, status: 'done', meta: '5 done (retry) · $0.09', progress: 100 } }, log: [...r.log, { t: 33000, mark: '✓', text: 'Job 3 SUCCEEDED · 5 done (retry) · $0.09', tone: 'green' }] })))
    at(35000, () => setBatchRun(r => ({ ...r, nodes: { ...r.nodes, job2: { ...r.nodes.job2, status: 'done', meta: '3 done · 2 skipped', progress: 100 }, storevideos: { ...r.nodes.storevideos, status: 'active' } }, log: [...r.log, { t: 35000, mark: '✓', text: 'Job 2 SUCCEEDED · 3 done · 2 skipped (already written)', tone: 'green' }] })))

    at(45000, () => {
      setBatchRun(r => ({ ...r, status: 'done', nodes: { ...r.nodes, storevideos: { ...r.nodes.storevideos, status: 'done', meta: 'videos/ 19/20 · summary.json' }, santa: { ...r.nodes.santa, status: 'done', meta: '200 batch done · 45 s' } }, log: [...r.log, { t: 45000, mark: '✓', text: 'output bucket done · videos/ 19/20 · summary.json written', tone: 'green' }, { t: 45000, mark: '✓', text: 'batch complete · 19 done · 1 failed · 2 skipped', tone: 'green' }] }))
      setBatchRunning(false); setBatchDone(true)
      setBatchSummary({ done: 19, failed: 1, skipped: 2, gpuTime: '4 × ~14 s', cost: '$0.34', onDemand: '$1.02', saved: '$0.68', savedPct: '67%' })
      setGallery(prev => {
        const newKids = BATCH_SEED.slice(0, 19).map(k => ({ ...k, hasVideo: true }))
        return [...newKids, ...prev]
      })
    })
  }

  // Panel: show create run on create/gallery tab, batch on batch tab
  const panelRun = tab === 'batch' ? batchRun : createRun
  const panelScope = tab === 'batch' ? 'Animate' : 'Create gift card'

  // Snow effect active during batch
  const snowActive = batchRunning

  return (
    <div style={{ position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column', background: 'rgb(249,245,238)', fontFamily: 'Inter,system-ui,sans-serif', color: 'rgba(0,0,0,.85)' }}>
      {/* ── Header ── */}
      <header style={{
        height: 52, flexShrink: 0, position: 'relative', overflow: 'hidden',
        background: 'linear-gradient(90deg, rgba(255,190,92,.42) 0%, rgba(255,190,92,.12) 520px, rgba(255,190,92,.06) 100%)',
        borderBottom: '2px solid rgba(255,190,92,.6)',
        display: 'flex', alignItems: 'center', gap: 0,
      }}>
        {/* Snow layer */}
        {snowActive && (
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.55,
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,.9) 1px, transparent 1px), radial-gradient(circle, rgba(255,255,255,.8) 1.5px, transparent 1.5px), radial-gradient(circle, rgba(255,255,255,.7) 1px, transparent 1px)',
            backgroundSize: '80px 120px, 120px 90px, 60px 100px',
            backgroundPosition: '0 0, 40px 30px, 70px 10px',
            animation: 'snowfall 6s linear infinite',
          }} />
        )}
        {/* Logo + title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', flexShrink: 0 }}>
          <div style={{ fontSize: 22 }}>🎅</div>
          <div>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'rgba(0,0,0,.85)' }}>Santa Scale Challenge</span>
            <span style={{ fontSize: 12, marginLeft: 8, background: realMode ? 'rgba(45,139,93,.15)' : 'rgba(45,139,93,.15)', color: 'rgb(45,139,93)', borderRadius: 4, padding: '1px 6px', fontWeight: 600 }}>{realMode ? 'REAL' : 'DEMO'}</span>
            <span style={{ fontSize: 11.5, marginLeft: 6, color: 'rgba(0,0,0,.4)', fontFamily: 'JetBrains Mono,Menlo,monospace' }}>Nordic Tech Week 2025</span>
          </div>
        </div>
        {/* Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', height: '100%', marginLeft: 8 }}>
          {(['create', 'batch', 'gallery'] as Tab[]).map(t => {
            const labels: Record<Tab, string> = { create: 'Create gift card', batch: 'Animate', gallery: 'Gallery' }
            const active = tab === t
            return (
              <button key={t} onClick={() => setTab(t)} style={{
                height: '100%', border: 'none', background: 'transparent', cursor: 'pointer',
                padding: '0 18px', fontSize: 15, fontWeight: active ? 500 : 400,
                color: active ? 'rgba(0,0,0,.85)' : 'rgba(0,0,0,.5)',
                borderBottom: active ? '2.5px solid rgb(233,174,86)' : '2.5px solid transparent',
                fontFamily: 'inherit', transition: 'all 0.15s', position: 'relative',
              }}>
                {labels[t]}
                {t === 'gallery' && <span style={{ marginLeft: 5, background: 'rgba(0,0,0,.1)', borderRadius: 10, padding: '1px 6px', fontSize: 11, fontWeight: 600 }}>{gallery.length}</span>}
              </button>
            )
          })}
        </div>
        {/* Right controls */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16, padding: '0 20px' }}>
          {!realMode && (
            <>
          {/* Cold Sana toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'rgba(0,0,0,.6)' }}>
            <span>Simulate cold Sana endpoint</span>
            <button onClick={() => setColdSana(v => !v)} style={{
              width: 34, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer', position: 'relative',
              background: coldSana ? 'rgb(233,174,86)' : 'rgba(0,0,0,.15)', transition: 'background 0.2s',
            }}>
              <div style={{ position: 'absolute', top: 2, left: coldSana ? 16 : 2, width: 16, height: 16, borderRadius: '50%', background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,.2)', transition: 'left 0.2s' }} />
            </button>
          </div>
          {/* Speed selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'rgba(0,0,0,.6)' }}>
            <span>Speed:</span>
            {[0.5, 1, 2, 4].map(s => (
              <button key={s} onClick={() => setSpeed(s)} style={{
                border: 'none', borderRadius: 4, padding: '2px 7px', fontSize: 12.5, fontWeight: 500, cursor: 'pointer', fontFamily: 'JetBrains Mono,Menlo,monospace',
                background: speed === s ? 'rgb(233,174,86)' : 'rgba(0,0,0,.08)', color: speed === s ? 'rgba(0,0,0,.8)' : 'rgba(0,0,0,.55)',
              }}>{s}×</button>
            ))}
          </div>
          {/* Fallback label */}
          <div style={{ fontSize: 13, color: 'rgba(0,0,0,.5)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span>Fallback:</span>
            <span style={{ fontWeight: 500, color: 'rgba(0,0,0,.65)' }}>{coldSana ? 'auto (primary down)' : 'auto'}</span>
          </div>
            </>
          )}
          {realMode && (
            <div style={{ fontSize: 13, color: 'rgba(0,0,0,.5)', fontFamily: 'JetBrains Mono,Menlo,monospace' }}>
              {tab === 'batch' ? 'GET /api/wall · POST /api/runs' : 'GET /api/wall · POST /api/cards/stream'}
            </div>
          )}
        </div>
      </header>

      {/* ── Main area ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Content column */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
          <div style={{ maxWidth: 880 }}>
            {tab === 'create' && (
              <CreateTab
                form={form} setForm={setForm} onMagic={realMode ? () => { void runMagicReal() } : runMagic}
                createRunning={createRun.status === 'running'} animating={animating}
                cardStage={cardStage} cardStageLabel={cardStageLabel} cardData={cardData}
                onAnimate={realMode ? () => { void runAnimateReal() } : runAnimate} onPlay={() => {
                  setVideoPlaying(v => !v)
                  if (!cardData?.videoUrl) setTimeout(() => setVideoPlaying(false), 5200 / speed)
                }}
                hasVideo={hasVideo} videoPlaying={videoPlaying}
              />
            )}
            {tab === 'batch' && (
              <BatchTab
                batchKids={batchKids} batchLoaded={batchLoaded}
                onLoad={realMode ? () => { void loadKidsReal() } : () => { setBatchLoaded(true); setBatchKids(BATCH_SEED.map(k => ({ ...k, batchStatus: 'queued' as const }))) }}
                onRun={realMode ? () => { void runBatchReal() } : runBatch} batchRunning={batchRunning} batchDone={batchDone} batchSummary={batchSummary}
                metrics={realMode ? batchMetrics : undefined}
                realMode={realMode}
              />
            )}
            {tab === 'gallery' && (
              <GalleryTab
                gallery={gallery}
                selectedId={gallerySelectedId}
                onSelect={setGallerySelectedId}
              />
            )}
          </div>
        </main>

        {/* ── Right panel: GiftCard preview on Gallery; LivePanel elsewhere ── */}
        {tab === 'gallery' ? (
          <GalleryPreview
            kid={gallerySelectedId ? (gallery.find(k => k.id === gallerySelectedId) ?? null) : null}
            realMode={realMode}
            onRealMode={v => { void setMode(v) }}
          />
        ) : (
          <LivePanel run={panelRun} scope={panelScope} realMode={realMode} onRealMode={v => { void setMode(v) }} />
        )}
      </div>
    </div>
  )
}
