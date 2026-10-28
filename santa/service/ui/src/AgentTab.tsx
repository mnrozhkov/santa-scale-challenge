import { useState } from 'react'
import { runAgentStream } from './api'
import {
  applyAgentEvent,
  initialAgentRun,
  simAgentScript,
  type RunState,
} from './agentGraph'

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
const MOODS = ['Warm', 'Playful', 'Dreamy', 'Adventurous', 'Cozy', 'Magical', 'Joyful', 'Calm']
const BGS = ['rgb(255,230,180)', 'rgb(200,235,200)', 'rgb(210,225,255)', 'rgb(255,210,210)', 'rgb(220,245,235)', 'rgb(255,240,200)']

type Form = {
  name: string
  age: number
  wish: string
  tags: string[]
  mood: string
  city: string
}

type CardResult = {
  kidId: string
  gift: string
  model: string
  bg: string
  pngUrl?: string
  videoUrl?: string
  status?: string
  wishText?: string
}

type Props = {
  realMode: boolean
  speed: number
  onRunChange: (run: RunState) => void
  running: boolean
  onRunning: (v: boolean) => void
}

function slugId(name: string): string {
  const base = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'kid'
  return `${base}-${Math.random().toString(36).slice(2, 8)}`
}

export function AgentTab({ realMode, speed, onRunChange, running, onRunning }: Props) {
  const [form, setForm] = useState<Form>({
    name: 'Emma',
    age: 7,
    wish: 'a telescope',
    tags: ['space'],
    mood: 'Magical',
    city: 'Oslo',
  })
  const [stage, setStage] = useState<'hidden' | 'running' | 'ready'>('hidden')
  const [stageLabel, setStageLabel] = useState('')
  const [card, setCard] = useState<CardResult | null>(null)
  const [videoPlaying, setVideoPlaying] = useState(false)
  const [summary, setSummary] = useState('')
  const [error, setError] = useState('')

  const inputStyle: React.CSSProperties = {
    width: '100%', height: 40, border: '1px solid rgba(0,0,0,.15)', borderRadius: 6, padding: '0 12px',
    fontSize: 15, fontFamily: 'inherit', color: 'rgba(0,0,0,.85)', background: 'white', outline: 'none',
    boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 500, color: 'rgba(0,0,0,.6)', marginBottom: 5, display: 'block' }
  const sectionCard: React.CSSProperties = {
    background: 'white', border: '1px solid rgba(0,0,0,.15)', borderRadius: 8,
    boxShadow: '0 4px 12px -2px rgba(0,0,0,.12)', padding: '16px 20px 20px', marginBottom: 20,
  }

  function validate(): string | null {
    if (!form.name.trim()) return 'Name is required'
    if (!form.age || form.age < 1 || form.age > 18) return 'Age must be 1–18'
    if (!form.wish.trim()) return 'Christmas wish is required'
    return null
  }

  async function runSim() {
    const err = validate()
    if (err) { setError(err); return }
    onRunning(true)
    setError('')
    setSummary('')
    setVideoPlaying(false)
    setStage('running')
    setStageLabel('evaluate → escalate…')
    setCard(null)
    let run = { ...initialAgentRun(), title: form.name.trim() }
    onRunChange(run)
    const t0 = performance.now()
    const script = simAgentScript(speed)
    for (const step of script) {
      await new Promise((r) => setTimeout(r, Math.max(0, step.delay - (performance.now() - t0))))
      const label = step.event.tool || step.event.event || step.event.type || ''
      if (label) setStageLabel(String(label))
      run = applyAgentEvent(run, step.event, performance.now() - t0)
      onRunChange({ ...run })
    }
    setCard({
      kidId: 'sim-emma',
      gift: "Beginner's tabletop telescope with easy-focus lenses",
      model: 'Sim · image RETRY → PASS → video PASS · H100 on rejected = 0',
      bg: BGS[5],
      pngUrl: '/demo/g6/card.png',
      videoUrl: '/demo/g6/video.mp4',
      status: 'accepted',
      wishText: form.wish,
    })
    setStage('ready')
    setSummary('Sim e2e: graph + card + animation (no endpoints)')
    onRunning(false)
  }

  async function runReal() {
    const err = validate()
    if (err) { setError(err); return }
    onRunning(true)
    setError('')
    setSummary('')
    setVideoPlaying(false)
    setStage('running')
    setStageLabel('POST /api/agent/stream…')
    setCard(null)
    const kidId = slugId(form.name)
    const wishlist = [form.wish.trim(), ...form.tags]
    let run = { ...initialAgentRun(), title: form.name.trim() }
    onRunChange(run)
    const t0 = performance.now()
    try {
      const report = await runAgentStream(
        {
          kids: [{ id: kidId, name: form.name.trim(), age: form.age, wishlist }],
          budget_usd: 1.5,
          publish: true,
        },
        (event) => {
          const label = String(event.tool || event.event || event.type || '')
          if (label) setStageLabel(label)
          run = applyAgentEvent(run, event as Parameters<typeof applyAgentEvent>[1], performance.now() - t0)
          onRunChange({ ...run })
        },
      )
      const kids = (report.kids as Array<Record<string, unknown>> | undefined) || []
      const first = kids[0] || {}
      const id = String(first.kid_id || kidId)
      const pngUrl = String(first.png_url || `/media/cards/${id}/card.png`)
      const videoUrl = first.video_url ? String(first.video_url) : `/media/cards/${id}/video.mp4`
      const status = String(first.status || 'accepted')
      const totals = (report.totals as Record<string, number> | undefined) || {}
      setCard({
        kidId: id,
        gift: form.wish.trim(),
        model: `agent · ${status} · $${Number(totals.cost ?? first.cost_usd ?? 0).toFixed(3)}`,
        bg: BGS[form.tags.length % BGS.length],
        pngUrl,
        videoUrl,
        status,
        wishText: form.wish,
      })
      setStage('ready')
      setSummary(
        `${status} · H100 on rejected ${totals.wasted_h100_s ?? 0}s · cost $${Number(totals.cost ?? 0).toFixed(3)}`,
      )
      run = { ...run, status: 'done' }
      onRunChange(run)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
      setStage('hidden')
      run = { ...run, status: 'done' }
      onRunChange(run)
    } finally {
      onRunning(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 650, marginBottom: 4 }}>Agent · evaluate before you escalate</div>
        <div style={{ fontSize: 13.5, color: 'rgba(0,0,0,.55)', maxWidth: 560, lineHeight: 1.45 }}>
          One kid, same profile as Create — then the full loop: judge the illustration before any H100 video second.
          Live graph on the right; card + animation appear when the run finishes.
        </div>
      </div>

      <div style={sectionCard}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
          <div style={{ width: 4, height: 16, background: 'rgb(45,139,93)', borderRadius: 2 }} />
          <span style={{ fontSize: 17, fontWeight: 600 }}>Kid Details</span>
        </div>
        <div className="create-form-grid">
          <div>
            <label style={labelStyle}>Name</label>
            <input style={inputStyle} placeholder="e.g. Emma" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div>
            <label style={labelStyle}>Age</label>
            <input style={inputStyle} type="number" min={1} max={18} value={form.age} onChange={e => setForm(f => ({ ...f, age: Number(e.target.value) }))} />
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
              {ITAGS.map(tag => {
                const selected = form.tags.includes(tag.id)
                return (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => setForm(f => ({
                      ...f,
                      tags: f.tags.includes(tag.id) ? f.tags.filter(t => t !== tag.id) : [...f.tags, tag.id],
                    }))}
                    style={{
                      border: selected ? `1.5px solid ${tag.color}` : '1px solid rgba(0,0,0,.15)',
                      background: selected ? tag.light : 'white',
                      color: selected ? tag.color : 'rgba(0,0,0,.65)',
                      borderRadius: 6, padding: '6px 10px', fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', fontFamily: 'inherit',
                    }}
                  >
                    {tag.label}
                  </button>
                )
              })}
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

        <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="tap-target"
            disabled={running}
            onClick={() => { void (realMode ? runReal() : runSim()) }}
            style={{
              height: 44, border: 'none',
              background: running ? 'rgba(255,190,92,.5)' : 'rgb(255,190,92)',
              color: 'rgba(0,0,0,.75)', borderRadius: 6, padding: '0 24px',
              fontSize: 15, fontWeight: 600, cursor: running ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', opacity: running ? 0.5 : 1,
            }}
          >
            {running ? 'Running…' : realMode ? '✨ Run agent (Real)' : '▶ Sim evaluate → escalate'}
          </button>
          <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.4)' }}>
            {realMode ? 'POST /api/agent/stream · 1 kid · operator' : 'Sim script · graph + demo card/video'}
          </span>
        </div>
      </div>

      {error && (
        <div style={{ color: 'rgb(180,40,40)', fontSize: 13, marginBottom: 12 }}>{error}</div>
      )}
      {summary && (
        <div style={{
          background: 'rgba(48,170,110,.1)', border: '1px solid rgba(48,170,110,.35)',
          borderRadius: 8, padding: '10px 12px', fontSize: 13.5, marginBottom: 12,
        }}>
          {summary}
        </div>
      )}

      {stage !== 'hidden' && (
        <div className="fadein" style={sectionCard}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <div style={{ width: 4, height: 16, background: 'rgb(45,139,93)', borderRadius: 2 }} />
            <span style={{ fontSize: 17, fontWeight: 600 }}>Gift Card + Animation</span>
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div style={{
              width: 280, height: 280, borderRadius: 6, flexShrink: 0, position: 'relative', overflow: 'hidden',
              background: card?.bg || 'rgba(0,0,0,.04)',
              borderTop: stage === 'ready' ? '4px solid rgb(45,139,93)' : undefined,
            }}>
              {stage === 'running' && (
                <>
                  <div className="shimmer-bg" style={{ position: 'absolute', inset: 0 }} />
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                    <div style={{ width: 24, height: 24, border: '2.5px solid rgba(0,0,0,.15)', borderTopColor: 'rgb(45,139,93)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                    <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.45)', textAlign: 'center', padding: '0 16px' }}>{stageLabel}</div>
                  </div>
                </>
              )}
              {stage === 'ready' && card?.pngUrl && (
                <img src={card.pngUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
              )}
            </div>
            {stage === 'ready' && card && (
              <div style={{ flex: 1, minWidth: 220, display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 4 }}>
                <div>
                  <div style={{ fontSize: 19, fontWeight: 700 }}>Merry Christmas, {form.name}! 🎄</div>
                  <div style={{ fontSize: 14, color: 'rgba(0,0,0,.55)', marginTop: 4, lineHeight: '20px' }}>
                    {card.wishText || form.wish}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{ background: 'rgba(45,139,93,.12)', color: 'rgb(45,139,93)', borderRadius: 4, padding: '3px 8px', fontSize: 12.5, fontWeight: 500 }}>
                    Gift: {card.gift}
                  </span>
                  <span style={{ background: 'rgba(0,0,0,.06)', borderRadius: 4, padding: '3px 8px', fontSize: 12.5 }}>
                    {card.status || 'accepted'}
                  </span>
                </div>
                <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 11.5, color: 'rgba(0,0,0,.35)' }}>{card.model}</div>
                <div style={{ marginTop: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {card.videoUrl && (
                    <button
                      type="button"
                      className="tap-target"
                      onClick={() => setVideoPlaying(v => !v)}
                      style={{
                        border: 'none', background: 'rgb(45,139,93)', color: 'white', borderRadius: 6,
                        padding: '8px 16px', fontSize: 14, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >
                      {videoPlaying ? '⏹ Stop' : '▶ Play video card'}
                    </button>
                  )}
                  <span style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 11.5, color: 'rgba(0,0,0,.35)' }}>
                    {form.mood.toLowerCase()} mood · agent mux
                  </span>
                </div>
                {videoPlaying && card.videoUrl && (
                  <video src={card.videoUrl} autoPlay controls playsInline style={{ width: '100%', borderRadius: 6, marginTop: 4 }} />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
