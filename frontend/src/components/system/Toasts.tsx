import { useEffect } from 'react'
import { useUiStore } from '../../store/uiStore'

export function Toasts() {
  const toasts = useUiStore((s) => s.toasts)
  const dismiss = useUiStore((s) => s.dismissToast)

  useEffect(() => {
    const id = toasts[0]?.id
    if (id === undefined) return
    const t = setTimeout(() => dismiss(id), 4000)
    return () => clearTimeout(t)
  }, [toasts, dismiss])

  if (toasts.length === 0) return null
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.tone}`} role="alert">
          {t.text}
          <button type="button" aria-label="닫기" onClick={() => dismiss(t.id)}>×</button>
        </div>
      ))}
    </div>
  )
}
