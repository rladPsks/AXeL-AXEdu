export function Brand() {
  return (
    <span className="brand-logo" role="img" aria-label="함께">
      <svg viewBox="0 0 56 48" aria-hidden="true" focusable="false">
        <circle cx="17" cy="12" r="6" fill="currentColor" />
        <circle cx="39" cy="12" r="6" fill="currentColor" />
        <path
          d="M6 39V30c0-9 14-12 22 0 8-12 22-9 22 0v9M17 29l11 9 11-9"
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span aria-hidden="true">함께</span>
    </span>
  );
}
