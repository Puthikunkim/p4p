import { useMemo, useState } from 'react'
import { useVCoreStore } from '../ws/store'
import { IconWarn } from '../components/icons'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '../components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../components/ui/dialog'
import type { ConditionItem, InvokeAction, RuleGrammarContract2 } from '../contracts/RuleGrammar'
import type { AbstractAction, ObjectDeclaration } from '../contracts/ObjectStatusManifest'

function formatCondition(c: ConditionItem): string {
  const val = c.threshold !== undefined ? c.threshold : (c.value ?? '')
  return `${c.signal} ${c.op} ${val}`
}

// Union the live (loaded-scene) manifest with the project-wide catalog so the builder
// can author against everything the project can expose. Live entries win on conflict.
function mergeObjects(live: ObjectDeclaration[], catalog: ObjectDeclaration[]): ObjectDeclaration[] {
  const byId = new Map<string, ObjectDeclaration>()
  for (const o of [...catalog, ...live]) {
    const prev = byId.get(o.id)
    if (!prev) { byId.set(o.id, { ...o, tags: [...o.tags], statuses: [...o.statuses] }); continue }
    const tags = Array.from(new Set([...prev.tags, ...o.tags]))
    const byName = new Map(prev.statuses.map((s) => [s.name, s]))
    for (const s of o.statuses) byName.set(s.name, s)
    byId.set(o.id, { ...prev, tags, statuses: Array.from(byName.values()) as ObjectDeclaration['statuses'] })
  }
  return Array.from(byId.values())
}

function mergeActions(live: AbstractAction[], catalog: AbstractAction[]): AbstractAction[] {
  const byKey = new Map<string, AbstractAction>()
  for (const a of [...catalog, ...live]) byKey.set(`${a.name}|${a.scope}|${a.id ?? ''}`, a)
  return Array.from(byKey.values())
}

export function RuleManager() {
  const rules = useVCoreStore((s) => s.rules)
  const disabledRules = useVCoreStore((s) => s.disabledRules)
  const signalManifest = useVCoreStore((s) => s.signalManifest)
  const objectStatusManifest = useVCoreStore((s) => s.objectStatusManifest)
  const objectStatusCatalog = useVCoreStore((s) => s.objectStatusCatalog)
  const [showBuilder, setShowBuilder] = useState(false)
  const [editingRule, setEditingRule] = useState<RuleGrammarContract2 | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const channels = signalManifest?.channels ?? []
  const objects: ObjectDeclaration[] = useMemo(
    () => mergeObjects(objectStatusManifest?.objects ?? [], objectStatusCatalog?.objects ?? []),
    [objectStatusManifest, objectStatusCatalog],
  )
  const abstractActions: AbstractAction[] = useMemo(
    () => mergeActions(objectStatusManifest?.abstract_actions ?? [], objectStatusCatalog?.abstract_actions ?? []),
    [objectStatusManifest, objectStatusCatalog],
  )

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

  async function performDeleteRule(id: string) {
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
        <Button variant="outline" onClick={showBuilder && !editingRule ? closeBuilder : openNew}>
          {showBuilder && !editingRule ? 'Cancel' : '+ New Rule'}
        </Button>
      </div>

      {/* Rule builder / editor */}
      {showBuilder && (
        <div className="rule-builder">
          <div className="rule-builder__header">
            <h3>{editingRule ? `Edit Rule` : 'New Rule'}</h3>
            {editingRule && <Button variant="outline" size="sm" onClick={closeBuilder}>Cancel</Button>}
          </div>

          <div className="form-row">
            <label>ID</label>
            {editingRule
              ? <span className="form-value-readonly">{ruleId}</span>
              : <Input value={ruleId} onChange={(e) => setRuleId(e.target.value)} placeholder="my-rule-id" />
            }
          </div>
          <div className="form-row">
            <label>Description</label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
          </div>

          <fieldset className="form-section form-section--if">
            <legend>IF [TRIGGER]</legend>
            <div className="form-row">
              <label>Signal</label>
              <Select value={signal || undefined} onValueChange={(v) => setSignal(v)}>
                <SelectTrigger><SelectValue placeholder="— no manifest —" /></SelectTrigger>
                <SelectContent>
                  {channels.map((ch) => <SelectItem key={ch.name} value={ch.name}>{ch.display.label} ({ch.name})</SelectItem>)}
                  {channels.length === 0 && signal && <SelectItem value={signal}>{signal}</SelectItem>}
                </SelectContent>
              </Select>
            </div>
            <div className="form-row">
              <label>Operator</label>
              <Select value={op} onValueChange={(v) => setOp(v as ConditionItem['op'])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(['>', '>=', '<', '<=', '==', '!='] as const).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="form-row">
              <label>Threshold / value</label>
              <Input value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
            <div className="form-row">
              <label>Sustained (s)</label>
              <Input type="number" min="0" value={sustainS} onChange={(e) => setSustainS(e.target.value)} placeholder="0" />
            </div>
          </fieldset>

          <fieldset className="form-section form-section--then">
            <legend>THEN [ACTION]</legend>
            <div className="form-row">
              <label>THEN do</label>
              <Select value={thenMode} onValueChange={(v) => setThenMode(v as 'set' | 'action')}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="set">Set status</SelectItem>
                  <SelectItem value="action">Invoke action</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {thenMode === 'set' && (<>
            <div className="form-row">
              <label>Target type</label>
              <Select value={targetType} onValueChange={(v) => setTargetType(v as 'tag' | 'id')}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="tag">tag</SelectItem>
                  <SelectItem value="id">id</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="form-row">
              <label>Target value</label>
              <Select
                value={targetValue || undefined}
                onValueChange={(v) => { setTargetValue(v); setStatusName(''); setStatusValue('') }}
              >
                <SelectTrigger><SelectValue placeholder="— pick —" /></SelectTrigger>
                <SelectContent>
                  {targetType === 'tag'
                    ? [...new Set(objects.flatMap((o) => o.tags))].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)
                    : objects.map((o) => <SelectItem key={o.id} value={o.id}>{o.id}</SelectItem>)
                  }
                  {/* Show current value even if no manifest loaded */}
                  {targetValue && !objects.length && <SelectItem value={targetValue}>{targetValue}</SelectItem>}
                </SelectContent>
              </Select>
            </div>
            {targetValue && (() => {
              const matched = targetType === 'tag'
                ? objects.filter((o) => o.tags.includes(targetValue))
                : objects.filter((o) => o.id === targetValue)
              // Dedupe by status name: a tag can match several objects that declare the
              // same status (e.g. `brightness` on both campfire_01 and demo_cube), and a
              // tag request fans out by name — so the picker should list each name once.
              const statuses = Array.from(
                new Map(matched.flatMap((o) => o.statuses).map((s) => [s.name, s])).values(),
              )
              return (
                <>
                  <div className="form-row">
                    <label>Status</label>
                    {statuses.length > 0
                      ? <Select value={statusName || undefined} onValueChange={(v) => { setStatusName(v); setStatusValue('') }}>
                          <SelectTrigger><SelectValue placeholder="— pick —" /></SelectTrigger>
                          <SelectContent>
                            {statuses.map((s) => <SelectItem key={s.name} value={s.name}>{s.name} ({s.type})</SelectItem>)}
                          </SelectContent>
                        </Select>
                      : <Input value={statusName} onChange={(e) => setStatusName(e.target.value)} placeholder="status name" />
                    }
                  </div>
                  {statusName && (() => {
                    const st = statuses.find((s) => s.name === statusName)
                    return st?.type === 'discrete' ? (
                      <div className="form-row">
                        <label>Value</label>
                        <Select value={statusValue || undefined} onValueChange={(v) => setStatusValue(v)}>
                          <SelectTrigger><SelectValue placeholder="— pick —" /></SelectTrigger>
                          <SelectContent>
                            {(st.values ?? []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <div className="form-row">
                        <label>Value{st ? ` (${st.range?.min ?? 0}–${st.range?.max ?? 100})` : ''}</label>
                        <Input value={statusValue} onChange={(e) => setStatusValue(e.target.value)}
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
                  ? <Select value={actionKey || undefined} onValueChange={(v) => setActionKey(v)}>
                      <SelectTrigger><SelectValue placeholder="— pick —" /></SelectTrigger>
                      <SelectContent>
                        {abstractActions.map((a, i) => (
                          <SelectItem key={i} value={String(i)}>
                            {a.name} ({a.scope}{a.scope === 'object' && a.id ? `:${a.id}` : ''})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  : <Input value={actionName} onChange={(e) => setActionName(e.target.value)} placeholder="action name (scene-level)" />
                }
              </div>
            )}
            <div className="form-row">
              <label>Cooldown (s)</label>
              <Input type="number" min="0" value={cooldownS} onChange={(e) => setCooldownS(e.target.value)} />
            </div>
          </fieldset>

          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <Button onClick={saveRule} disabled={saving}>
              {saving ? 'Saving…' : editingRule ? 'Update Rule' : 'Save Rule'}
            </Button>
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
              onDelete={setPendingDeleteId}
            />
          ))
        )}
      </div>

      <Dialog open={pendingDeleteId !== null} onOpenChange={(o) => { if (!o) setPendingDeleteId(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete rule?</DialogTitle>
            <DialogDescription>
              Delete rule <code>{pendingDeleteId}</code>? This removes its YAML from the rules directory.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDeleteId(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => { const id = pendingDeleteId; setPendingDeleteId(null); if (id) performDeleteRule(id) }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
  const conditions = 'all' in r.when ? [...r.when.all] : [...r.when.any]
  const setAction = r.then?.set
  const invokeAction = r.then?.action
  const sustain = conditions[0]?.sustain_s

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
        <span className="rule-card__title">{r.description || r.id}</span>
        <span className="rule-card__id-label">Id: {r.id}</span>
        <span className={`rule-card__state rule-card__state--${disabled ? 'disabled' : 'active'}`}>
          {disabled ? 'disabled' : 'active'}
        </span>
      </div>

      <div className="rule-card__body">
        {conditions.length > 0 && (
          <div>
            <div className="rule-card__section-label rule-card__section-label--if">IF [TRIGGER]</div>
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
            <div className="rule-card__section-label rule-card__section-label--then">THEN [ACTION]</div>
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
            <div className="rule-card__section-label rule-card__section-label--then">THEN [ACTION]</div>
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
        <Button variant="outline" size="sm" onClick={() => onEdit(r)}>Edit</Button>
        <Button variant="destructive" size="sm" onClick={() => onDelete(r.id)}>Delete</Button>
      </div>
    </div>
  )
}
