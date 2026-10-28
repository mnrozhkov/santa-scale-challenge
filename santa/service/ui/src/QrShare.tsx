import { useState, type CSSProperties } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { kioskOrigin } from './access'

const tap: CSSProperties = {
  minHeight: 44,
  border: '1.5px solid rgba(0,0,0,.2)',
  background: 'white',
  borderRadius: 8,
  padding: '0 16px',
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'inherit',
  color: 'rgba(0,0,0,.75)',
}

export function QrModal({ origin, onClose }: { origin: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(origin)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div
      role="dialog"
      aria-label="QR code"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 80,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div
        className="fadein"
        onClick={e => e.stopPropagation()}
        style={{
          background: 'white', borderRadius: 12, padding: 24, maxWidth: 420, width: '100%',
          boxShadow: '0 16px 40px rgba(0,0,0,.25)', display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 14,
        }}
      >
        <div style={{ fontSize: 17, fontWeight: 700 }}>Scan to join</div>
        <QRCodeSVG value={origin} size={280} includeMargin />
        <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 12, color: 'rgba(0,0,0,.55)', wordBreak: 'break-all', textAlign: 'center' }}>
          {origin}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <button type="button" className="tap-target" style={tap} onClick={() => { void copy() }}>
            {copied ? 'Copied' : 'Copy URL'}
          </button>
          <a className="tap-target" href="/qr" target="_blank" rel="noreferrer" style={{ ...tap, display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}>
            Open in new tab
          </a>
          <button type="button" className="tap-target" style={tap} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

export function QrProjector() {
  const origin = kioskOrigin()
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgb(249,245,238)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 20, padding: 24, fontFamily: 'Inter,system-ui,sans-serif',
    }}>
      <div style={{ fontSize: 28, fontWeight: 700 }}>Santa Scale Challenge</div>
      <div style={{ fontSize: 16, color: 'rgba(0,0,0,.55)' }}>Scan to open the kiosk</div>
      <div style={{ background: 'white', padding: 24, borderRadius: 16, boxShadow: '0 8px 24px rgba(0,0,0,.12)' }}>
        <QRCodeSVG value={origin} size={Math.min(420, typeof window !== 'undefined' ? window.innerWidth - 80 : 420)} includeMargin />
      </div>
      <div style={{ fontFamily: 'JetBrains Mono,Menlo,monospace', fontSize: 14, color: 'rgba(0,0,0,.5)' }}>{origin}</div>
    </div>
  )
}
