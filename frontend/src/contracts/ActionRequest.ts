/* Auto-generated from contracts/action_request.schema.json — do not edit by hand. */

export type Target =
  | {
      tag: string;
    }
  | {
      id: string;
    };

/**
 * Emitted by the rule engine (source=engine) or by a researcher manually triggering a rule (source=manual). Sent to Unity over /ws/runtime to invoke a parameterless abstract action. Omit target for a scene-level action; include a tag/id target for an object-level one.
 */
export interface ActionRequestContract3C {
  schema_version: string;
  /**
   * UUID for deduplication and event logging.
   */
  intent_id: string;
  timestamp: string;
  action: string;
  target?: Target;
  /**
   * ID of the rule that generated this request. Omitted for manual triggers with no associated rule.
   */
  source_rule?: string;
  /**
   * engine = fired by the rule evaluator; manual = fired by the researcher via the dashboard trigger button.
   */
  source: "engine" | "manual";
}
