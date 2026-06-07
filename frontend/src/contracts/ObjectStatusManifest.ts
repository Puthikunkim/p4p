/* Auto-generated from contracts/object_status_manifest.schema.json — do not edit by hand. */

/**
 * Sent by the Unity runtime over /ws/runtime at connect time and on scene change. Declares every controllable object and its settable statuses so V-CORE can populate the rule builder THEN side and validate incoming status requests.
 */
export interface ObjectStatusManifestContract3B {
  schema_version: string;
  scene: string;
  runtime: string;
  objects: ObjectDeclaration[];
  abstract_actions?: AbstractAction[];
}
export interface ObjectDeclaration {
  id: string;
  tags: string[];
  /**
   * @minItems 1
   */
  statuses: [StatusDeclaration, ...StatusDeclaration[]];
}
export interface StatusDeclaration {
  name: string;
  type: "discrete" | "continuous";
  /**
   * Required when type=discrete.
   *
   * @minItems 1
   */
  values?: [string, ...string[]];
  /**
   * Required when type=continuous.
   */
  range?: {
    min: number;
    max: number;
  };
}
export interface AbstractAction {
  action: string;
  params_schema?: {};
  [k: string]: unknown;
}
