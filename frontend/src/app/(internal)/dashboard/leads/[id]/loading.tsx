/** Skeleton for the lead detail page. Mirrors the two-column layout. */
function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-line ${className}`} />;
}

export default function LeadDetailLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10 sm:px-8" aria-busy="true">
      <span className="sr-only" role="status">
        Loading lead…
      </span>

      <div aria-hidden="true">
        <Block className="h-4 w-24" />
        <div className="mt-6 border-b border-line pb-8">
          <Block className="h-10 w-72 max-w-full" />
          <Block className="mt-3 h-5 w-48" />
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="border border-line bg-paper-raised">
                <Block className="h-12 w-full rounded-none" />
                <div className="space-y-3 px-6 py-5">
                  <Block className="h-4 w-full" />
                  <Block className="h-4 w-5/6" />
                  <Block className="h-4 w-2/3" />
                </div>
              </div>
            ))}
          </div>
          <div className="space-y-6">
            {Array.from({ length: 2 }).map((_, index) => (
              <div key={index} className="border border-line bg-paper-raised">
                <Block className="h-12 w-full rounded-none" />
                <div className="space-y-3 px-6 py-5">
                  <Block className="h-4 w-full" />
                  <Block className="h-4 w-3/4" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
