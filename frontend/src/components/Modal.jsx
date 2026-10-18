import React, { useEffect, useRef } from 'react'
import Icon from './Icon'

export default function Modal({ title, eyebrow, badge, onClose, children }) {
  const panel = useRef(null)

  useEffect(() => {
    const onKeyDown = event => {
      if (event.key === 'Escape') onClose()
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', onKeyDown)
    panel.current?.focus()
    return () => {
      document.body.style.overflow = previous
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  return (
    <div
      className="modal-overlay"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="modal panel" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={panel}>
        <header className="modal-header">
          <div>
            {eyebrow && <span className="eyebrow muted">{eyebrow}</span>}
            <h2>{title}</h2>
          </div>
          {badge && <span className="pill">{badge}</span>}
          <button className="icon-button" onClick={onClose} aria-label="Fechar">
            <Icon name="close" />
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}
