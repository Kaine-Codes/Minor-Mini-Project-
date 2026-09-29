export default function GasDangerBanner({ active }) {
  if (!active) return null

  return (
    <div className="gas-danger-banner" role="alert">
      <span className="gas-danger-icon" aria-hidden="true">⚠️</span>
      GAS LEVEL HIGH — local safety override active, fan forced on
    </div>
  )
}
