import { useState } from 'react'
import { useVCoreStore } from '../ws/store'
import type { ConditionItem, RuleGrammarContract2 } from '../contracts/RuleGrammar'
import type { ObjectDeclaration } from '../contracts/ObjectStatusManifest'

export function RuleManager() {
  const rules = useVCoreStore((s) => s.rules)
  const disabledRules = useVCoreStore((s) => s.disabledRules)
  const signalManifest = useVCoreStore((s) => s.signalManifest)
  const objectStatusManifest = useVCoreStore((s) => s.objectStatusManifest)
  const [showBuilder, setShowBuilder] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const channels = signalManifest?.channels ?? []
  const objects: ObjectDeclaration[] = objectStatusManifest?.objects ?? []

  // Rule builder state
  const [ruleId, setRuleId] = useState('')
  const [description, setDescription] = useState('')
  const [signal, setSignal] = useState(channels[0]?.name ?? '')
  const [op, setOp] = useState<ConditionItem['op']>('>=')
  const [threshold, setThreshold] = useState('0.8')
  const [sustainS, setSustainS] = useState('')
  const [cooldownS, setCooldownS] = useState('30')
  const [targetType, setTargetType] = useState<'tag' | 'id'>('tag')
  const [targetValue, setTargetValue] = useState('')
  const [statusName, setStatusName] = useState('')
  const [statusValue, setStatusValue] = useState('')

  async function saveRule() {
    setError(null)
    if (!ruleId.trim()) { setError('Rule ID is required'); return }
    if (!signal) { setError('Pick a signal'); return }
    if (!targetValue.trim()) { setError('Pick a target'); return }
    if (!statusName.trim()) { setError('Pick a status'); return }
    if (!statusValue.trim()) { setError('Enter a value'); return }

    const cond: ConditionItem = {
      signal,
      op,
      threshold: ['>', '>=', '<', '<=', 'between'].includes(op) ? parseFloat(threshold) : undefined,
      value: op === '==' || op === '!=' ? threshold : undefined,
      sustain_s: sustainS ? parseFloat(sustainS) : undefined,
    }

    const rule: RuleGrammarContract2 = {
      id: ruleId.trim(),
      schema_version: '1.0.0',
      description: description || undefined,
      enabled: true,
      when: { all: [cond] },
      then: {
        set: {
          target: targetType === 'tag' ? { tag: targetValue } : { id: targetValue },
          status: statusName,
          value: isNaN(Number(statusValue)) ? statusValue : Number(statusValue),
        },
        cooldown_s: cooldownS ? parseFloat(cooldownS) : undefined,
      },
    }

    setSaving(true)
    try {
      const resp = await fetch('/api/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rule),
      })
      if (!resp.ok) {
        const body = await resp.json() as { detail?: string }
        setError(body.detail ?? `HTTP ${resp.status}`)
      } else {
        setShowBuilder(false)
        setRuleId('')
        setDescription('')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function deleteRule(id: string) {
    if (!confirm(`Delete rule "${id}"?`)) return
    await fetch(`/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Rule Manager</h2>
        <button className="btn" onClick={() => setShowBuilder(!showBuilder)}>
          {showBuilder ? 'Cancel' : '+ New Rule'}
        </button>
      </div>

      {/* Rule builder */}
      {showBuilder && (
        <div className="rule-builder">
          <h3>New Rule</h3>

          <div className="form-row">
            <label>ID</label>
            <input value={ruleId} onChange={(e) => setRuleId(e.target.value)} placeholder="my-rule-id" />
          </div>
          <div className="form-row">
            <label>Description</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
          </div>

          <fieldset className="form-section">
            <legend>IF</legend>
            <div className="form-row">
              <label>Signal</label>
              <select value={signal} onChange={(e) => setSignal(e.target.value)}>
                {channels.map((ch) => <option key={ch.name} value={ch.name}>{ch.display.label} ({ch.name})</option>)}
                {channels.length === 0 && <option value="">— no manifest —</option>}
              </select>
            </div>
            <div className="form-row">
              <label>Op</label>
              <select value={op} onChange={(e) => setOp(e.target.value as ConditionItem['op'])}>
                {(['>', '>=', '<', '<=', '==', '!='] as const).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div className="form-row">
              <label>Threshold / value</label>
              <input value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Sustain (s)</label>
              <input type="number" min="0" value={sustainS} onChange={(e) => setSustainS(e.target.value)} placeholder="0" />
            </div>
          </fieldset>

          <fieldset className="form-section">
            <legend>THEN set</legend>
            <div className="form-row">
              <label>Target type</label>
              <select value={targetType} onChange={(e) => setTargetType(e.target.value as 'tag' | 'id')}>
                <option value="tag">tag</option>
                <option value="id">id</option>
              </select>
            </div>
            <div className="form-row">
              <label>Target value</label>
              <select value={targetValue} onChange={(e) => {
                setTargetValue(e.target.value)
                setStatusName('')
                setStatusValue('')
              }}>
                <option value="">— pick —</option>
                {targetType === 'tag'
                  ? [...new Set(objects.flatMap((o) => o.tags))].map((t) => <option key={t} value={t}>{t}</option>)
                  : objects.map((o) => <option key={o.id} value={o.id}>{o.id}</option>)
                }
              </select>
            </div>
            {targetValue && (() => {
              const matched = targetType === 'tag'
                ? objects.filter((o) => o.tags.includes(targetValue))
                : objects.filter((o) => o.id === targetValue)
              const statuses = matched.flatMap((o) => o.statuses)
              return (
                <>
                  <div className="form-row">
                    <label>Status</label>
                    <select value={statusName} onChange={(e) => { setStatusName(e.target.value); setStatusValue('') }}>
                      <option value="">— pick —</option>
                      {statuses.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.type})</option>)}
                    </select>
                  </div>
                  {statusName && (() => {
                    const st = statuses.find((s) => s.name === statusName)
                    return st?.type === 'discrete' ? (
                      <div className="form-row">
                        <label>Value</label>
                        <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)}>
                          <option value="">— pick —</option>
                          {(st.values ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
                        </select>
                      </div>
                    ) : (
                      <div className="form-row">
                        <label>Value ({st?.range?.min ?? 0}–{st?.range?.max ?? 100})</label>
                        <input type="number" value={statusValue} onChange={(e) => setStatusValue(e.target.value)}
                          min={st?.range?.min} max={st?.range?.max} />
                      </div>
                    )
                  })()}
                </>
              )
            })()}
            <div className="form-row">
              <label>Cooldown (s)</label>
              <input type="number" min="0" value={cooldownS} onChange={(e) => setCooldownS(e.target.value)} />
            </div>
          </fieldset>

          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button className="btn btn--primary" onClick={saveRule} disabled={saving}>
              {saving ? 'Saving…' : 'Save Rule'}
            </button>
          </div>
        </div>
      )}

      {/* Rule list */}
      <div className="rule-list">
        {rules.length === 0 ? (
          <p className="empty-state">No rules yet. Drop YAML files in <code>backend/rules/</code> or use the builder above.</p>
        ) : (
          rules.map((r) => {
            const reason = disabledRules[r.id]
            return (
              <div key={r.id} className={`rule-card ${reason ? 'rule-card--disabled' : ''}`}>
                <div className="rule-card__header">
                  <span className="rule-card__id">{r.id}</span>
                  <span className={`rule-card__badge ${reason ? 'rule-card__badge--warn' : 'rule-card__badge--ok'}`}>
                    {reason ? 'disabled' : 'active'}
                  </span>
                  <button className="btn btn--small btn--danger" onClick={() => deleteRule(r.id)}>Delete</button>
                </div>
                {r.description && <p className="rule-card__desc">{r.description}</p>}
                {reason && <p className="rule-card__reason">⚠ {reason}</p>}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
