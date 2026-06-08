import { useVCoreStore } from '../ws/store'

export function SystemConfig() {
  const wsState = useVCoreStore((s) => s.wsState)
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>System Config</h2>
      </div>

      <section className="config-section">
        <h3>Connection Status</h3>
        <table className="config-table">
          <tbody>
            <tr>
              <td>Dashboard WS</td>
              <td><span className={`badge badge--${wsState}`}>{wsState}</span></td>
            </tr>
            {Object.entries(linkStatuses).map(([link, ls]) => (
              <tr key={link}>
                <td>{link}</td>
                <td>
                  <span className={`badge badge--${ls.state}`}>{ls.state}</span>
                  {ls.detail && <span className="config-meta"> {ls.detail}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="config-section">
        <h3>Configuration</h3>
        <p className="empty-state">
          Edit <code>backend/config.yaml</code> to set LSL stream names,
          WS bind address, and ZMQ endpoints.
        </p>
      </section>
    </div>
  )
}
