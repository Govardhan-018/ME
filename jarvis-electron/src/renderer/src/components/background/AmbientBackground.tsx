import { ParticleField } from './ParticleField'

/** Layered spatial atmosphere: void → aurora → grid → particles → vignette. */
export function AmbientBackground(): JSX.Element {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden bg-void">
      <div
        className="absolute left-1/2 top-1/2 h-[120vh] w-[120vh] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-60"
        style={{
          background: 'radial-gradient(circle, rgba(56,232,255,0.10), transparent 60%)',
          animation: 'auroraShift 20s ease-in-out infinite'
        }}
      />
      <div
        className="absolute left-[12%] top-[8%] h-[62vh] w-[62vh] rounded-full opacity-50"
        style={{
          background: 'radial-gradient(circle, rgba(77,124,255,0.10), transparent 60%)',
          animation: 'auroraShift 28s ease-in-out infinite reverse'
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.045]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          animation: 'gridDrift 16s linear infinite',
          WebkitMaskImage: 'radial-gradient(circle at center, #000 28%, transparent 74%)',
          maskImage: 'radial-gradient(circle at center, #000 28%, transparent 74%)'
        }}
      />
      <ParticleField />
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.72))' }}
      />
    </div>
  )
}
