export interface SkeletonProps {
  height?: number | string;
  width?: number | string;
  className?: string;
}

/** Dimension-matched loading placeholder to prevent Cumulative Layout Shift. */
export function Skeleton({ height = 18, width = '100%', className = '' }: SkeletonProps) {
  return (
    <div
      className={`ui-skeleton ${className}`.trim()}
      style={{ height, width }}
      aria-hidden="true"
    />
  );
}
