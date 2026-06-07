import Ajv from 'ajv/dist/2020'
import type { ValidateFunction } from 'ajv/dist/2020'
import addFormats from 'ajv-formats'

import signalSchema from '../../../contracts/signal_schema.schema.json'
import ruleGrammar from '../../../contracts/rule_grammar.schema.json'
import statusRequest from '../../../contracts/status_request.schema.json'
import objectStatusManifest from '../../../contracts/object_status_manifest.schema.json'

const ajv = new Ajv({ strict: false, allErrors: true })
addFormats(ajv)

const validators: Record<string, ValidateFunction> = {
  signal_schema: ajv.compile(signalSchema),
  rule_grammar: ajv.compile(ruleGrammar),
  status_request: ajv.compile(statusRequest),
  object_status_manifest: ajv.compile(objectStatusManifest),
}

export function validate(contract: string, payload: unknown): true | string[] {
  const fn = validators[contract]
  if (!fn) throw new Error(`Unknown contract: ${contract}`)
  const ok = fn(payload)
  if (ok) return true
  return (fn.errors ?? []).map((e) => `${e.instancePath} ${e.message}`)
}

export function isValid(contract: string, payload: unknown): boolean {
  return validate(contract, payload) === true
}
