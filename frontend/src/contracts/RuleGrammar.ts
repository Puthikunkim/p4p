/* Auto-generated from contracts/rule_grammar.schema.json — do not edit by hand. */

export type ConditionGroup =
  | {
      /**
       * @minItems 1
       */
      all: [ConditionItem, ...ConditionItem[]];
    }
  | {
      /**
       * @minItems 1
       */
      any: [ConditionItem, ...ConditionItem[]];
    };
export type Target =
  | {
      tag: string;
    }
  | {
      id: string;
    };

/**
 * Declarative IF→THEN rule files authored in the UI or dropped into backend/rules/. The engine hot-reloads these files via watchdog.
 */
export interface RuleGrammarContract2 {
  id: string;
  schema_version: string;
  description?: string;
  enabled?: boolean;
  when: ConditionGroup;
  then: ThenClause;
}
export interface ConditionItem {
  signal: string;
  op: ">" | ">=" | "<" | "<=" | "==" | "!=" | "between";
  threshold?: number;
  low?: number;
  high?: number;
  value?: string;
  sustain_s?: number;
}
export interface ThenClause {
  set: SetAction;
  cooldown_s?: number;
}
export interface SetAction {
  target: Target;
  status: string;
  value: number | string;
}
