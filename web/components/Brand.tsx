/** Scout mark: a lens with a check inside — "found, and proven". */
export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="scout-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--accent-2)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#scout-g)" />
      <circle cx="14.5" cy="14.5" r="7" fill="none" stroke="var(--accent-fg)" strokeWidth="2.4" />
      <path d="M19.8 19.8 24.5 24.5" stroke="var(--accent-fg)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="m11.4 14.6 2.3 2.3 4.2-4.6" fill="none" stroke="var(--accent-fg)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
