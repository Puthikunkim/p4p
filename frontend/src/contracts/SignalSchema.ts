/* Auto-generated from contracts/signal_schema.schema.json — do not edit by hand. */

/**
 * Self-describing manifest that the sensor pipeline publishes alongside its LSL stream. Drives dashboard renderer selection and rule engine signal resolution.
 */
export interface SignalSchemaContract1 {
  /**
   * SemVer — see contracts/VERSIONING.md for compatibility policy.
   */
  schema_version: string;
  stream: {
    name: string;
    source_id: string;
    nominal_srate: number;
  };
  /**
   * @minItems 1
   */
  channels: [Channel, ...Channel[]];
}
export interface Channel {
  name: string;
  unit: string;
  type: "scalar" | "timeseries" | "categorical";
  range?: {
    min: number;
    max: number;
  };
  /**
   * @minItems 1
   */
  categories?: [string, ...string[]];
  display: DisplayHint;
}
export interface DisplayHint {
  hint: string;
  label: string;
  precision?: number;
  window_s?: number;
  [k: string]: unknown;
}
