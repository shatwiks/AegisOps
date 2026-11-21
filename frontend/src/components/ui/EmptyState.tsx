import type { ReactNode } from 'react';

export interface EmptyStateProps {
  title?: string;
  description: ReactNode;
  action?: ReactNode;
}

/** Clear empty/unauthenticated state explaining context plus optional next CTA. */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state ui-empty-state">
      {title && <div className="ui-empty-state__title">{title}</div>}
      <div>{description}</div>
      {action && <div className="ui-empty-state__actions">{action}</div>}
    </div>
  );
}
