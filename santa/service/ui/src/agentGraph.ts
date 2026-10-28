/** Map Experiment B tracer events → kiosk RunState (act → eval → reiterate). */

export type NodeStatus =
  | 'idle'
  | 'active'
  | 'scheduling'
  | 'pending'
  | 'done'
  | 'failed'
  | 'preempted'
  | 'skipped'

export interface RNode {
  id: string
  label: string
  kind: string
  sub: string
  status: NodeStatus
  meta?: string
  metaColor?: string
  progress?: number
}

export interface LogLine {
  t: number
  mark: string
  text: string
  tone: string
}

export interface RunState {
  title: string
  status: 'idle' | 'running' | 'done'
  nodes: Record<string, RNode>
  levels: string[][]
  log: LogLine[]
  elapsed: number
  footer?: string
}

export type AgentTraceEvent = {
  type?: string
  event?: string
  tool?: string
  kind?: string
  attempt?: number
  decision?: string
  score?: number
  reasons?: string[]
  passed?: string[]
  failed?: string[]
  cause?: string
  fix?: string
  check?: string
  result?: string
  detail?: string
  spent?: number
  remaining?: number
  kid_id?: string
  status?: string
  cost_usd?: number
  latency_s?: number
  role?: string
  ts?: string
}

const AGENT_LEVELS = [
  ['agent'],
  ['recommend', 'wish'],
  ['image', 'evalImg'],
  ['gate'],
  ['video', 'evalVid'],
  ['accept'],
]

function baseNodes(): Record<string, RNode> {
  return {
    agent: { id: 'agent', label: 'Agent (Pydantic AI)', kind: 'service', sub: 'evaluate → escalate', status: 'idle' },
    recommend: { id: 'recommend', label: 'recommend_gift', kind: 'llm', sub: 'llm role', status: 'idle' },
    wish: { id: 'wish', label: 'write_wish', kind: 'llm', sub: 'llm role', status: 'idle' },
    image: { id: 'image', label: 'generate_image', kind: 'endpoint', sub: 'L40S · Sana', status: 'idle' },
    evalImg: { id: 'evalImg', label: 'evaluate_image', kind: 'llm', sub: 'vlm judge', status: 'idle' },
    gate: { id: 'gate', label: 'gate_video_on_image_pass', kind: 'service', sub: 'policy in tools', status: 'idle' },
    video: { id: 'video', label: 'generate_video', kind: 'endpoint', sub: 'H100 · Wan', status: 'idle' },
    evalVid: { id: 'evalVid', label: 'evaluate_video', kind: 'llm', sub: 'vlm + motion', status: 'idle' },
    accept: { id: 'accept', label: 'accept / keep_best', kind: 'file', sub: 'card.png + card.mp4', status: 'idle' },
  }
}

export function initialAgentRun(): RunState {
  return {
    title: 'Agent · evaluate before escalate',
    status: 'running',
    nodes: baseNodes(),
    levels: AGENT_LEVELS,
    log: [],
    elapsed: 0,
    footer: '',
  }
}

function setNode(
  run: RunState,
  id: string,
  status: NodeStatus,
  meta?: string,
  extra?: Partial<RNode>,
): RunState {
  const base = run.nodes[id] ?? { id, label: id, kind: 'service', sub: '', status: 'idle' }
  return {
    ...run,
    nodes: {
      ...run.nodes,
      [id]: { ...base, ...extra, status, meta: meta ?? base.meta },
    },
  }
}

/** Mark every currently-active node done (tools don't emit explicit completion). */
function settleActive(run: RunState): RunState {
  const nodes = { ...run.nodes }
  for (const id of Object.keys(nodes)) {
    if (nodes[id].status === 'active') {
      nodes[id] = { ...nodes[id], status: 'done' }
    }
  }
  return { ...run, nodes }
}

/** After keep_best / failed: unused video path → skipped. */
function skipIdleTail(run: RunState): RunState {
  const nodes = { ...run.nodes }
  for (const id of ['gate', 'video', 'evalVid']) {
    if (nodes[id] && nodes[id].status === 'idle') {
      nodes[id] = { ...nodes[id], status: 'skipped', meta: 'not reached' }
    }
  }
  for (const id of Object.keys(nodes)) {
    if (id.startsWith('evalImg') && nodes[id].status === 'idle') {
      nodes[id] = { ...nodes[id], status: 'skipped', meta: 'not evaluated' }
    }
  }
  return { ...run, nodes }
}

/** Append a retry sibling level for image-2 / eval-2 when attempt > 1. */
function ensureRetryLevel(run: RunState, attempt: number): RunState {
  if (attempt <= 1) return run
  const imgId = `image${attempt}`
  const evalId = `evalImg${attempt}`
  if (run.nodes[imgId]) return run
  const nodes = {
    ...run.nodes,
    [imgId]: {
      id: imgId,
      label: `generate_image (${attempt})`,
      kind: 'endpoint',
      sub: 'retry',
      status: 'idle' as NodeStatus,
    },
    [evalId]: {
      id: evalId,
      label: `evaluate_image (${attempt})`,
      kind: 'llm',
      sub: 'vlm judge',
      status: 'idle' as NodeStatus,
    },
  }
  const levels = run.levels.map((level) =>
    level.includes('image') ? [...level, imgId, evalId] : level,
  )
  return { ...run, nodes, levels }
}

function eventAttempt(event: AgentTraceEvent): number {
  const args = (event as { args?: { n?: number; image_n?: number } }).args
  return Number(event.attempt || args?.n || args?.image_n || 1)
}

export function applyAgentEvent(run: RunState, event: AgentTraceEvent, elapsed: number): RunState {
  const name = event.event || event.type || ''
  let next = { ...run, elapsed }
  const appendLog = (lines: { text: string; tone?: string; mark?: string }[]): RunState => ({
    ...next,
    log: [
      ...next.log,
      ...lines.map((l) => ({
        t: elapsed,
        mark: l.mark || '·',
        text: l.text,
        tone: l.tone || 'gray',
      })),
    ],
  })
  const logLine = (text: string, tone = 'gray'): RunState => appendLog([{ text, tone }])

  if (name === 'run_started') {
    next = setNode(next, 'agent', 'active')
    return logLine(`run_started ${event.kid_id || ''}`, 'blue')
  }
  if (name === 'tool_call') {
    const tool = event.tool || ''
    next = settleActive(next)
    if (tool === 'recommend_gift') next = setNode(next, 'recommend', 'active')
    else if (tool === 'write_wish') {
      next = setNode(next, 'recommend', 'done')
      next = setNode(next, 'wish', 'active')
    } else if (tool === 'generate_image') {
      const n = eventAttempt(event)
      next = setNode(next, 'recommend', 'done')
      next = setNode(next, 'wish', 'done')
      next = ensureRetryLevel(next, n)
      next = setNode(next, n > 1 ? `image${n}` : 'image', 'active', `attempt ${n}`)
    } else if (tool === 'evaluate_image') {
      const n = eventAttempt(event)
      next = ensureRetryLevel(next, n)
      next = setNode(next, n > 1 ? `image${n}` : 'image', 'done')
      next = setNode(next, n > 1 ? `evalImg${n}` : 'evalImg', 'active')
    } else if (tool === 'generate_video') {
      next = setNode(next, 'gate', 'done', 'allowed')
      next = setNode(next, 'video', 'active')
    } else if (tool === 'evaluate_video') {
      next = setNode(next, 'video', 'done')
      next = setNode(next, 'evalVid', 'active')
    } else if (tool === 'accept' || tool === 'keep_best') {
      next = setNode(next, 'accept', 'active', tool)
      // keep_best may still animate — do not skip video nodes yet
    }
    return logLine(`tool_call ${tool}`, 'blue')
  }
  if (name === 'endpoint_call_completed') {
    const role = event.role || ''
    const meta = `${(event.latency_s ?? 0).toFixed(1)} s`
    if (role === 'image') {
      const n = eventAttempt(event)
      next = ensureRetryLevel(next, n)
      next = setNode(next, n > 1 ? `image${n}` : 'image', 'done', meta)
    }
    if (role === 'video') next = setNode(next, 'video', 'done', meta)
    return logLine(`${role} done · ${meta}`, 'green')
  }
  if (name === 'artifact_evaluated') {
    const kind = event.kind || 'image'
    const decision = event.decision || '?'
    const score = event.score ?? ''
    const meta = `${decision} · ${score}`
    const n = eventAttempt(event)
    const reasons = (event.reasons || []).filter(Boolean)
    const passed = (event.passed || []).filter(Boolean)
    const failed = (event.failed || []).filter(Boolean)
    const cause = event.cause && event.cause !== 'none' ? ` cause=${event.cause}` : ''
    const fix = event.fix && event.fix !== 'none' ? ` fix=${event.fix}` : ''
    if (kind === 'image') {
      next = ensureRetryLevel(next, n)
      next = setNode(next, n > 1 ? `evalImg${n}` : 'evalImg', decision === 'PASS' ? 'done' : 'failed', meta)
      next = setNode(next, n > 1 ? `image${n}` : 'image', 'done')
    } else {
      next = setNode(next, 'evalVid', decision === 'PASS' ? 'done' : 'failed', meta)
      next = setNode(next, 'video', 'done')
    }
    const tone = decision === 'PASS' ? 'green' : decision === 'WEAK' || decision === 'RETRY' ? 'amber' : 'orange'
    const lines: { text: string; tone?: string; mark?: string }[] = [
      { text: `eval ${kind}-${n}: ${decision} (${score})${cause}${fix}`, tone, mark: decision === 'PASS' ? '✓' : '×' },
    ]
    if (passed.length) {
      lines.push({ text: `  ✓ passed: ${passed.join(' · ')}`, tone: 'green', mark: ' ' })
    }
    if (failed.length) {
      lines.push({ text: `  × failed: ${failed.join(' · ')}`, tone: 'amber', mark: ' ' })
    }
    if (reasons.length) {
      lines.push({ text: `  · why: ${reasons.slice(0, 3).join('; ')}`, tone: 'muted', mark: ' ' })
    }
    if (!passed.length && !failed.length && !reasons.length) {
      lines.push({ text: '  · no per-rule breakdown from judge', tone: 'muted', mark: ' ' })
    }
    return appendLog(lines)
  }
  if (name === 'policy_check') {
    const allowed = event.result === 'allowed'
    const check = event.check || 'policy'
    if (check === 'gate_video_on_image_pass' || check === 'keep_best_animate') {
      next = setNode(
        next,
        'gate',
        allowed ? 'done' : 'failed',
        event.detail || event.result,
        check === 'keep_best_animate' ? { label: 'keep_best_animate', sub: 'best score → video' } : undefined,
      )
      if (allowed && check === 'keep_best_animate') {
        next = setNode(next, 'video', 'active', 'best candidate')
      }
    } else {
      next = setNode(
        next,
        'gate',
        allowed ? 'done' : 'failed',
        event.detail || `${check}: ${event.result}`,
        { label: check, sub: 'policy in tools' },
      )
    }
    return logLine(`${check} ${event.result}: ${event.detail || ''}`, allowed ? 'green' : 'orange')
  }
  if (name === 'budget_updated') {
    next = {
      ...next,
      footer: `spent $${(event.spent ?? 0).toFixed(3)} · remaining $${(event.remaining ?? 0).toFixed(3)}`,
    }
    return logLine(next.footer || '', 'gray')
  }
  if (name === 'run_completed') {
    next = settleActive(next)
    if (event.status === 'kept_best' || event.status === 'failed') {
      next = skipIdleTail(next)
    }
    next = setNode(next, 'agent', event.status === 'failed' ? 'failed' : 'done', event.status)
    next = setNode(next, 'accept', event.status === 'failed' ? 'failed' : 'done', event.status)
    next = { ...next, status: 'done' }
    return logLine(`run_completed ${event.kid_id} · ${event.status}`, 'green')
  }
  if (name === 'complete' || event.type === 'complete') {
    next = settleActive(next)
    return { ...next, status: 'done' }
  }
  return next
}

/** Scripted Sim: image RETRY (garbled) → image PASS → video PASS → accept. */
export function simAgentScript(speed: number): { delay: number; event: AgentTraceEvent }[] {
  const s = 1000 / speed
  return [
    { delay: 0, event: { event: 'run_started', kid_id: 'k01' } },
    { delay: 0.4 * s, event: { event: 'tool_call', tool: 'recommend_gift' } },
    { delay: 0.8 * s, event: { event: 'tool_call', tool: 'write_wish' } },
    { delay: 1.2 * s, event: { event: 'tool_call', tool: 'generate_image', attempt: 1 } },
    {
      delay: 2.0 * s,
      event: {
        event: 'endpoint_call_completed',
        role: 'image',
        attempt: 1,
        latency_s: 1.0,
      },
    },
    { delay: 2.2 * s, event: { event: 'tool_call', tool: 'evaluate_image', attempt: 1 } },
    {
      delay: 2.8 * s,
      event: {
        event: 'artifact_evaluated',
        kind: 'image',
        attempt: 1,
        decision: 'RETRY',
        score: 42,
        passed: ['gift recognizable', 'christmas/storybook atmosphere', 'object-centric composition'],
        failed: ['text OK (correct English or none)'],
        reasons: ['garbled lettering'],
        fix: 'seed',
      },
    },
    { delay: 3.0 * s, event: { event: 'tool_call', tool: 'generate_image', attempt: 2 } },
    {
      delay: 3.8 * s,
      event: {
        event: 'endpoint_call_completed',
        role: 'image',
        attempt: 2,
        latency_s: 1.0,
      },
    },
    { delay: 4.0 * s, event: { event: 'tool_call', tool: 'evaluate_image', attempt: 2 } },
    {
      delay: 4.5 * s,
      event: {
        event: 'artifact_evaluated',
        kind: 'image',
        attempt: 2,
        decision: 'PASS',
        score: 91,
        passed: [
          'gift recognizable',
          'christmas/storybook atmosphere',
          'object-centric composition',
          'no people/faces',
          'text OK (correct English or none)',
        ],
        failed: [],
        reasons: ['gift clear'],
      },
    },
    {
      delay: 4.7 * s,
      event: {
        event: 'policy_check',
        check: 'gate_video_on_image_pass',
        result: 'allowed',
        detail: 'image 2 PASS',
      },
    },
    { delay: 5.0 * s, event: { event: 'tool_call', tool: 'generate_video' } },
    {
      delay: 6.5 * s,
      event: {
        event: 'endpoint_call_completed',
        role: 'video',
        attempt: 1,
        latency_s: 2.0,
      },
    },
    { delay: 6.7 * s, event: { event: 'tool_call', tool: 'evaluate_video' } },
    {
      delay: 7.2 * s,
      event: {
        event: 'artifact_evaluated',
        kind: 'video',
        attempt: 1,
        decision: 'PASS',
        score: 88,
        passed: [
          'same scene/object as illustration',
          'no new people/faces/bad text',
          'subtle motion (still the illustration)',
        ],
        failed: [],
        cause: 'none',
      },
    },
    { delay: 7.4 * s, event: { event: 'tool_call', tool: 'accept' } },
    {
      delay: 7.8 * s,
      event: { event: 'budget_updated', spent: 0.29, remaining: 1.21 },
    },
    {
      delay: 8.0 * s,
      event: {
        event: 'run_completed',
        kid_id: 'k01',
        status: 'accepted',
        cost_usd: 0.29,
      },
    },
  ]
}
