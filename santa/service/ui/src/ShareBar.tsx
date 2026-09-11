import { useEffect, useState, type CSSProperties } from 'react'

function sharePageUrl(id: string): string {
  return `${window.location.origin}/s/${encodeURIComponent(id)}`
}

function tweetUrl(share: string, name: string): string {
  const text = `A Christmas card for ${name}`
  return `https://twitter.com/intent/tweet?url=${encodeURIComponent(share)}&text=${encodeURIComponent(text)}`
}

function linkedInUrl(share: string): string {
  return `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(share)}`
}

const btn: CSSProperties = {
  border: '1.5px solid rgba(0,0,0,.2)',
  background: 'white',
  borderRadius: 6,
  padding: '8px 14px',
  minHeight: 44,
  fontSize: 14,
  fontWeight: 500,
  cursor: 'pointer',
  fontFamily: 'inherit',
  color: 'rgba(0,0,0,.75)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  textDecoration: 'none',
}

export function ShareBar({
  id,
  pngUrl,
  name,
}: {
  id: string
  pngUrl?: string
  name: string
}) {
  const [canWebShare, setCanWebShare] = useState(false)
  const share = sharePageUrl(id)

  useEffect(() => {
    setCanWebShare(typeof navigator !== 'undefined' && typeof navigator.share === 'function')
  }, [])

  const onDownload = async () => {
    if (!pngUrl) return
    const resp = await fetch(pngUrl)
    const blob = await resp.blob()
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = `gift-card-${name || id}.png`
    a.click()
    URL.revokeObjectURL(href)
  }

  const onWebShare = async () => {
    if (!navigator.share) return
    try {
      if (pngUrl) {
        const resp = await fetch(pngUrl)
        const blob = await resp.blob()
        const file = new File([blob], `gift-card-${name || id}.png`, { type: blob.type || 'image/png' })
        if (navigator.canShare?.({ files: [file] })) {
          await navigator.share({ title: `A Christmas card for ${name}`, files: [file] })
          return
        }
      }
      await navigator.share({ title: `A Christmas card for ${name}`, url: share, text: `A Christmas card for ${name}` })
    } catch {
      /* user cancelled */
    }
  }

  return (
    <div className="share-bar" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {pngUrl && (
        <button type="button" className="tap-target" onClick={() => { void onDownload() }} style={btn}>
          Download
        </button>
      )}
      <a className="tap-target" href={tweetUrl(share, name)} target="_blank" rel="noreferrer" style={btn}>
        X
      </a>
      <a className="tap-target" href={linkedInUrl(share)} target="_blank" rel="noreferrer" style={btn}>
        LinkedIn
      </a>
      {canWebShare && (
        <button type="button" className="tap-target" onClick={() => { void onWebShare() }} style={btn}>
          Share
        </button>
      )}
    </div>
  )
}
