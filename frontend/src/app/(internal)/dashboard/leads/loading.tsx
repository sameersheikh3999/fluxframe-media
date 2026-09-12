/**
 * Skeleton shown while the dashboard fetches.
 *
 * These pages are `force-dynamic` and hit the API on every request, so without
 * a loading state the browser sits on the previous page for a beat with no
 * indication anything is happening. The UI/UX audit calls this out under
 * "Loading feedback": an interface that appears frozen is indistinguishable
 * from one that is broken.
 *
 * The skeleton mirrors the real layout's dimensions rather than showing a
 * spinner, so the content does not jump when it arrives — the same reasoning
 * as reserving space for images to avoid layout shift.
 */
function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-line ${className}`} />;
}

export default function LeadsLoading() {
  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10 sm:px-8" aria-busy="true">
      {/* One polite announcement for assistive tech; the blocks themselves are
          decorative and hidden from the accessibility tree. */}
      <span className="sr-only" role="status">
        Loading leads…
      </span>

      <div aria-hidden="true">
        <Block className="h-10 w-40" />
        <Block className="mt-3 h-4 w-96 max-w-full" />

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="border border-line bg-paper-raised p-5">
              <Block className="h-3 w-20" />
              <Block className="mt-3 h-8 w-12" />
            </div>
          ))}
        </div>

        <div className="mt-10 flex gap-3 border-y border-line py-5">
          <Block className="h-10 w-64" />
          <Block className="h-10 w-40" />
          <Block className="h-10 w-20" />
        </div>

        <div className="mt-8 space-y-px border border-line">
          {Array.from({ length: 6 }).map((_, index) => (
            <Block key={index} className="h-16 w-full rounded-none" />
          ))}
        </div>
      </div>
    </div>
  );
}
