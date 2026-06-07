import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { validate, isValid } from './validate'

const EXAMPLES = resolve(__dirname, '../../../contracts/examples')

function loadExample(name: string): unknown {
  const raw = JSON.parse(readFileSync(resolve(EXAMPLES, name), 'utf8'))
  // Strip the documentation meta-key before validating
  delete raw._invalid_reason
  return raw
}

const contracts = [
  'signal_schema',
  'rule_grammar',
  'status_request',
  'object_status_manifest',
] as const

describe('Contract validators — valid goldens', () => {
  for (const contract of contracts) {
    it(`${contract} valid golden passes`, () => {
      const payload = loadExample(`${contract}.valid.json`)
      expect(isValid(contract, payload)).toBe(true)
    })
  }
})

describe('Contract validators — invalid goldens', () => {
  for (const contract of contracts) {
    it(`${contract} invalid golden fails`, () => {
      const payload = loadExample(`${contract}.invalid.json`)
      const result = validate(contract, payload)
      expect(result).not.toBe(true)
      expect(Array.isArray(result)).toBe(true)
      expect((result as string[]).length).toBeGreaterThan(0)
    })
  }
})
