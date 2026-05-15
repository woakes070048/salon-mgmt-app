/**
 * Persistent banner shown at the top of every page when the frontend is
 * built with VITE_ENV=dev. Loud yellow so staff don't mistake the dev
 * environment for production and accidentally book real clients here.
 */
export default function DevBanner() {
  const env = import.meta.env.VITE_ENV
  if (env !== 'dev') return null

  return (
    <div className="bg-yellow-400 text-yellow-950 text-center text-xs font-semibold tracking-wide py-1 px-3 print:hidden">
      DEV ENVIRONMENT — DO NOT USE FOR REAL APPOINTMENTS
    </div>
  )
}
