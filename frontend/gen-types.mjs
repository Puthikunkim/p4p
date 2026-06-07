#!/usr/bin/env node
/**
 * Generate TypeScript types from the four JSON Schema contracts.
 * Output goes to frontend/src/contracts/
 *
 * Usage:  node tools/gen-types.mjs
 */
import { compile } from 'json-schema-to-typescript'
import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')
const CONTRACTS_DIR = resolve(ROOT, 'contracts')
const OUT_DIR = resolve(__dirname, 'src', 'contracts')

mkdirSync(OUT_DIR, { recursive: true })

const contracts = [
  { file: 'signal_schema.schema.json', out: 'SignalSchema.ts' },
  { file: 'rule_grammar.schema.json', out: 'RuleGrammar.ts' },
  { file: 'status_request.schema.json', out: 'StatusRequest.ts' },
  { file: 'object_status_manifest.schema.json', out: 'ObjectStatusManifest.ts' },
]

for (const { file, out } of contracts) {
  const schema = JSON.parse(readFileSync(resolve(CONTRACTS_DIR, file), 'utf8'))
  const ts = await compile(schema, schema.title ?? file, {
    bannerComment: `/* Auto-generated from contracts/${file} — do not edit by hand. */`,
    additionalProperties: false,
  })
  writeFileSync(resolve(OUT_DIR, out), ts)
  console.log(`✓  ${out}`)
}
