import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

/** Accessible action button supporting variant, compact size, and safe pending lock. */
export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  const sizeClass = size === 'sm' ? 'ui-btn--sm' : '';
  return (
    <button
      type={type}
      disabled={Boolean(disabled || loading)}
      aria-busy={loading || undefined}
      className={`btn btn-${variant} ui-btn ${sizeClass} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  );
}
