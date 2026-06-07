# V-CORE Contract Versioning Policy

All four contracts use [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).
The `schema_version` field is present in every contract payload and checked by V-CORE at
ingest time.

## Compatibility matrix

| Change type | MAJOR | MINOR | PATCH |
|---|---|---|---|
| Remove or rename a required field | ✓ | | |
| Change a field's type or allowed values | ✓ | | |
| Add a new **required** field | ✓ | | |
| Add a new **optional** field | | ✓ | |
| Tighten an existing constraint (e.g. stricter enum) | ✓ | | |
| Relax an existing constraint | | ✓ | |
| Documentation / description only | | | ✓ |

## Runtime behaviour on version skew

V-CORE compares the `schema_version` in the incoming payload against the version of the
schema it has loaded (`contracts/*.schema.json`).

| Skew | V-CORE behaviour |
|---|---|
| **Patch** (`1.0.0` vs `1.0.1`) | Accept silently. |
| **Minor** (`1.0.x` vs `1.1.x`) | Accept with a `warning` event on the event bus; surfaced in the dashboard System Config screen. |
| **Major** (`1.x.x` vs `2.x.x`) | **Refuse** — the stream/rule/manifest is rejected; a blocking warning is surfaced in the dashboard. The system continues to operate with the last accepted payload. |

## Per-contract current versions

| Contract | File | Current version |
|---|---|---|
| Signal Schema | `signal_schema.schema.json` | `1.0.0` |
| Rule Grammar | `rule_grammar.schema.json` | `1.0.0` |
| Status Request | `status_request.schema.json` | `1.0.0` |
| Object-Status Manifest | `object_status_manifest.schema.json` | `1.0.0` |

## Upgrade path

When a breaking change is required:

1. Bump `MAJOR` in the relevant schema and update this table.
2. Update the golden examples in `contracts/examples/` and ensure all valid/invalid
   goldens reflect the new version.
3. Both the Python validator (`backend/vcore/core/schema.py`) and the TypeScript validator
   (`frontend/src/contracts/`) must pass against the updated goldens before merging.
4. Update `ARCHITECTURE.md §6` if the compatibility policy itself changes.
