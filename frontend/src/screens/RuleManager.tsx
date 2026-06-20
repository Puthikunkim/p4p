import { useState } from 'react'
import { useVCoreStore } from '../ws/store'
import { IconWarn } from '../components/icons'
import type { ConditionItem, InvokeAction, RuleGrammarContract2 } from '../contracts/RuleGrammar'
import type { AbstractAction, ObjectDeclaration } from '../contracts/ObjectStatusManifest'

const TYPE_COLORS = 5  // cycles through .rule-card__type--0..4

function ruleTypeIndex(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0
  return Math.abs(hash) % TYPE_COLORS
}

function formatCondition(c: ConditionItem): string {
  const val = c.threshold !== undefined ? c.threshold : (c.value ?? '')
  return `${c.signal} ${c.op} ${val}`
}

export function RuleManager() {
  const rules = useVCoreStore((s) => s.rules)
  const disabledRules = useVCoreStore((s) => s.disabledRules)
  const signalManifest = useVCoreStore((s) => s.signalManifest)
  const objectStatusManifest = useVCoreStore((s) => s.objectStatusManifest)
  const [showBuilder, setShowBuilder] = useState(false)
  const [editingRule, setEditingRule] = useState<RuleGrammarContract2 | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const channels = signalManifest?.channels ?? []
  const objects: ObjectDeclaration[] = objectStatusManifest?.objects ?? []
  const abstractActions: AbstractAction[] = objectStatusManifest?.abstract_actions ?? []

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
  // THEN output: 'set' a status, or 'action' (invoke an abstract action)
  const [thenMode, setThenMode] = useState<'set' | 'action'>('set')
  const [actionKey, setActionKey] = useState('')  // index into abstractActions, or ''
  const [actionName, setActionName] = useState('')  // free-text fallback (scene-level)

  function openNew() {
    setEditingRule(null)
    setRuleId('')
    setDescription('')
    setSignal(channels[0]?.name ?? '')
    setOp('>=')
    setThreshold('0.8')
    setSustainS('')
    setCooldownS('30')
    setTargetType('tag')
    setTargetValue('')
    setStatusName('')
    setStatusValue('')
    setThenMode('set')
    setActionKey('')
    setActionName('')
    setError(null)
    setShowBuilder(true)
  }

  function openEdit(rule: RuleGrammarContract2) {
    const cond = 'all' in rule.when ? rule.when.all[0] : rule.when.any[0]
    setEditingRule(rule)
    setRuleId(rule.id)
    setDescription(rule.description ?? '')
    setSignal(cond?.signal ?? channels[0]?.name ?? '')
    setOp(cond?.op ?? '>=')
    setThreshold(String(cond?.threshold ?? cond?.value ?? ''))
    setSustainS(cond?.sustain_s !== undefined ? String(cond.sustain_s) : '')
    setCooldownS(rule.then.cooldown_s !== undefined ? String(rule.then.cooldown_s) : '')

    if (rule.then.action) {
      const a = rule.then.action
      setThenMode('action')
      setActionName(a.action)
      const isScene = a.target == null
      const idx = abstractActions.findIndex(
        (d) => d.name === a.action && (d.scope === 'scene') === isScene,
      )
      setActionKey(idx >= 0 ? String(idx) : '')
      // leave status/target fields at defaults
      setTargetType('tag'); setTargetValue(''); setStatusName(''); setStatusValue('')
    } else if (rule.then.set) {
      const target = rule.then.set.target
      setThenMode('set')
      setTargetType('tag' in target ? 'tag' : 'id')
      setTargetValue('tag' in target ? (target as { tag: string }).tag : (target as { id: string }).id)
      setStatusName(rule.then.set.status)
      setStatusValue(String(rule.then.set.value))
      setActionKey(''); setActionName('')
    }
    setError(null)
    setShowBuilder(true)
  }

  function closeBuilder() {
    setShowBuilder(false)
    setEditingRule(null)
    setError(null)
  }

  async function saveRule() {
    setError(null)
    if (!ruleId.trim()) { setError('Rule ID is required'); return }
    if (!signal) { setError('Pick a signal'); return }

    const cooldown_s = cooldownS ? parseFloat(cooldownS) : undefined
    let then: RuleGrammarContract2['then']
    if (thenMode === 'action') {
      let action: InvokeAction
      if (abstractActions.length > 0) {
        if (!actionKey) { setError('Pick an action'); return }
        const a = abstractActions[Number(actionKey)]
        action = { action: a.name, target: a.scope === 'scene' ? undefined : { id: a.id! } }
      } else {
        if (!actionName.trim()) { setError('Enter an action name'); return }
        action = { action: actionName.trim() }  // free-text → scene-level
      }
      then = { action, cooldown_s }
    } else {
      if (!targetValue.trim()) { setError('Pick a target'); return }
      if (!statusName.trim()) { setError('Pick a status'); return }
      if (!statusValue.trim()) { setError('Enter a value'); return }
      then = {
        set: {
          target: targetType === 'tag' ? { tag: targetValue } : { id: targetValue },
          status: statusName,
          value: isNaN(Number(statusValue)) ? statusValue : Number(statusValue),
        },
        cooldown_s,
      }
    }

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
      then,
    }

    const isEditing = editingRule !== null
    const url = isEditing ? `/api/rules/${encodeURIComponent(rule.id)}` : '/api/rules'
    const method = isEditing ? 'PUT' : 'POST'

    setSaving(true)
    try {
      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rule),
      })
      if (!resp.ok) {
        const body = await resp.json() as { detail?: string }
        setError(body.detail ?? `HTTP ${resp.status}`)
      } else {
        closeBuilder()
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function deleteRule(id: string) {
    if (!confirm(`Delete rule "${id}"?`)) return
    if (editingRule?.id === id) closeBuilder()
    await fetch(`/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  return (
    <div className="screen">
      <div className="screen-header">
        <div style={{ flex: 1 }}>
          <div className="screen-title">Adaptation Rules</div>
          {rules.length > 0 && (
            <div className="screen-subtitle">{rules.length} rule{rules.length !== 1 ? 's' : ''} loaded</div>
          )}
        </div>
        <button className="btn" onClick={showBuilder && !editingRule ? closeBuilder : openNew}>
          {showBuilder && !editingRule ? 'Cancel' : '+ New Rule'}
        </button>
      </div>

      {/* Rule builder / editor */}
      {showBuilder && (
        <div className="rule-builder">
          <div className="rule-builder__header">
            <h3>{editingRule ? `Edit Rule` : 'New Rule'}</h3>
            {editingRule && <button className="btn btn--small" onClick={closeBuilder}>Cancel</button>}
          </div>

          <div className="form-row">
            <label>ID</label>
            {editingRule
              ? <span className="form-value-readonly">{ruleId}</span>
              : <input value={ruleId} onChange={(e) => setRuleId(e.target.value)} placeholder="my-rule-id" />
            }
          </div>
          <div className="form-row">
            <label>Description</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
          </div>

          <fieldset className="form-section">
            <legend>IF [TRIGGER]</legend>
            <div className="form-row">
              <label>Signal</label>
              <select value={signal} onChange={(e) => setSignal(e.target.value)}>
                {channels.map((ch) => <option key={ch.name} value={ch.name}>{ch.display.label} ({ch.name})</option>)}
                {channels.length === 0 && <option value={signal}>{signal || '— no manifest —'}</option>}
              </select>
            </div>
            <div className="form-row">
              <label>Operator</label>
              <select value={op} onChange={(e) => setOp(e.target.value as ConditionItem['op'])}>
                {(['>', '>=', '<', '<=', '==', '!='] as const).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div className="form-row">
              <label>Threshold / value</label>
              <input value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Sustained (s)</label>
              <input type="number" min="0" value={sustainS} onChange={(e) => setSustainS(e.target.value)} placeholder="0" />
            </div>
          </fieldset>

          <fieldset className="form-section">
            <legend>THEN [ACTION]</legend>
            <div className="form-row">
              <label>THEN do</label>
              <select value={thenMode} onChange={(e) => setThenMode(e.target.value as 'set' | 'action')}>
                <option value="set">Set status</option>
                <option value="action">Invoke action</option>
              </select>
            </div>
            {thenMode === 'set' && (<>
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
                {/* Show current value even if no manifest loaded */}
                {targetValue && !objects.length && <option value={targetValue}>{targetValue}</option>}
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
                    {statuses.length > 0
                      ? <select value={statusName} onChange={(e) => { setStatusName(e.target.value); setStatusValue('') }}>
                          <option value="">— pick —</option>
                          {statuses.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.type})</option>)}
                        </select>
                      : <input value={statusName} onChange={(e) => setStatusName(e.target.value)} placeholder="status name" />
                    }
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
                        <label>Value{st ? ` (${st.range?.min ?? 0}–${st.range?.max ?? 100})` : ''}</label>
                        <input value={statusValue} onChange={(e) => setStatusValue(e.target.value)}
                          type={st ? 'number' : 'text'}
                          min={st?.range?.min} max={st?.range?.max} />
                      </div>
                    )
                  })()}
                </>
              )
            })()}
            </>)}
            {thenMode === 'action' && (
              <div className="form-row">
                <label>Action</label>
                {abstractActions.length > 0
                  ? <select value={actionKey} onChange={(e) => setActionKey(e.target.value)}>
                      <option value="">— pick —</option>
                      {abstractActions.map((a, i) => (
                        <option key={i} value={String(i)}>
                          {a.name} ({a.scope}{a.scope === 'object' && a.id ? `:${a.id}` : ''})
                        </option>
                      ))}
                    </select>
                  : <input value={actionName} onChange={(e) => setActionName(e.target.value)} placeholder="action name (scene-level)" />
                }
              </div>
            )}
            <div className="form-row">
              <label>Cooldown (s)</label>
              <input type="number" min="0" value={cooldownS} onChange={(e) => setCooldownS(e.target.value)} />
            </div>
          </fieldset>

          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button className="btn btn--primary" onClick={saveRule} disabled={saving}>
              {saving ? 'Saving…' : editingRule ? 'Update Rule' : 'Save Rule'}
            </button>
          </div>
        </div>
      )}

      {/* Rule list */}
      <div className="rule-list">
        {rules.length === 0 ? (
          <p className="empty-state">
            No rules yet. Drop YAML files in <code>backend/rules/</code> or use the builder above.
          </p>
        ) : (
          rules.map((r) => (
            <RuleCard
              key={r.id}
              rule={r}
              disabled={disabledRules[r.id]}
              isEditing={editingRule?.id === r.id}
              onEdit={openEdit}
              onDelete={deleteRule}
            />
          ))
        )}
      </div>
    </div>
  )
}

function RuleCard({
  rule: r,
  disabled,
  isEditing,
  onEdit,
  onDelete,
}: {
  rule: RuleGrammarContract2
  disabled?: string
  isEditing: boolean
  onEdit: (rule: RuleGrammarContract2) => void
  onDelete: (id: string) => void
}) {
  const typeIdx = ruleTypeIndex(r.id)
  const conditions = 'all' in r.when ? [...r.when.all] : [...r.when.any]
  const setAction = r.then?.set
  const invokeAction = r.then?.action
  const sustain = conditions[0]?.sustain_s

  const typeTag = r.id.replace(/[^a-zA-Z]/g, '').slice(0, 3).toUpperCase() || '???'

  return (
    <div
      className={`rule-card ${disabled ? 'rule-card--disabled' : ''} ${isEditing ? 'rule-card--editing' : ''}`}
      onClick={() => onEdit(r)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onEdit(r)}
      style={{ cursor: 'pointer' }}
    >
      <div className="rule-card__header">
        <span className={`rule-card__type rule-card__type--${typeIdx}`}>{typeTag}</span>
        <span className="rule-card__title">{r.description || r.id}</span>
        <span className="rule-card__id-label">Id: {r.id}</span>
        <span className={`rule-card__state rule-card__state--${disabled ? 'disabled' : 'active'}`}>
          {disabled ? 'disabled' : 'active'}
        </span>
      </div>

      <div className="rule-card__body">
        {conditions.length > 0 && (
          <div>
            <div className="rule-card__section-label">IF [TRIGGER]</div>
            {conditions.map((c, i) => (
              <div key={i} className="rule-card__condition">
                {formatCondition(c)}
              </div>
            ))}
            {sustain !== undefined && (
              <div className="rule-card__sustain">Sustained for {sustain}s</div>
            )}
          </div>
        )}

        {setAction && (
          <div>
            <div className="rule-card__section-label">THEN [ACTION]</div>
            <div className="rule-card__action">
              <span>
                {setAction.status} = <strong>{String(setAction.value)}</strong>
                {' '}on{' '}
                {'tag' in setAction.target ? `tag:${setAction.target.tag}` : `id:${setAction.target.id}`}
              </span>
              {r.then.cooldown_s !== undefined && (
                <span className="rule-card__action-tag">cooldown {r.then.cooldown_s}s</span>
              )}
            </div>
          </div>
        )}

        {invokeAction && (
          <div>
            <div className="rule-card__section-label">THEN [ACTION]</div>
            <div className="rule-card__action">
              <span>
                invoke <strong>{invokeAction.action}()</strong>
                {' '}on{' '}
                {invokeAction.target
                  ? ('tag' in invokeAction.target ? `tag:${invokeAction.target.tag}` : `id:${invokeAction.target.id}`)
                  : 'scene'}
              </span>
              {r.then.cooldown_s !== undefined && (
                <span className="rule-card__action-tag">cooldown {r.then.cooldown_s}s</span>
              )}
            </div>
          </div>
        )}

        {disabled && (
          <div className="rule-card__disabled-note">
            <IconWarn /> {disabled}
          </div>
        )}
      </div>

      <div className="rule-card__footer" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn--small" onClick={() => onEdit(r)}>Edit</button>
        <button className="btn btn--small btn--danger" onClick={() => onDelete(r.id)}>Delete</button>
      </div>
    </div>
  )
}
