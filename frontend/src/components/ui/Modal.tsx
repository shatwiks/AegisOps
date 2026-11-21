import { useEffect, useRef, type ReactNode } from 'react';

export interface ModalProps {
  titleId: string;
  title: string;
  onClose: () => void;
  wide?: boolean;
  children: ReactNode;
}

/** Accessible modal dialog with Escape dismissal, focus management, and focus restoration. */
export function Modal({ titleId, title, onClose, wide = false, children }: ModalProps) {
  const cardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    cardRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus();
      }
    };
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={cardRef}
        tabIndex={-1}
        className={`modal-card ${wide ? 'modal-card--wide' : ''}`.trim()}
      >
        <div className="modal-header">
          <h3 id={titleId} style={{ margin: 0 }}>
            {title}
          </h3>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
