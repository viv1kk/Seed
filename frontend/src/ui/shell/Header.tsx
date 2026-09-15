/**
 * The title bar and the run controls.
 *
 * The simulation badge is always present, never an icon, and carries the
 * tooltip the spec specifies. It stays after the run finishes: a deterministic
 * replay mode is a legitimate feature of the real product too, and saying
 * "simulated" before anyone else does is part of the demo.
 *
 * The seed field is editable only while idle, because a run reproduces only if
 * the seed it started with is the seed it keeps.
 */

import type { ReactNode } from "react";

export type Phase = "idle" | "planned" | "running" | "paused" | "done";

export interface HeaderProps {
  requirementName: string | null;
  seed: number;
  onSeedChange: (seed: number) => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  phase: Phase;
  primaryLabel: string;
  onPrimary: () => void;
  primaryDisabled: boolean;
  onTogglePause: () => void;
  onReset: () => void;
  extra?: ReactNode;
}

const SPEEDS = [1, 2, 5] as const;

export function Header({
  requirementName,
  seed,
  onSeedChange,
  speed,
  onSpeedChange,
  phase,
  primaryLabel,
  onPrimary,
  primaryDisabled,
  onTogglePause,
  onReset,
  extra,
}: HeaderProps) {
  const live = phase === "running" || phase === "paused";

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-ink-600 bg-ink-800 px-5 py-2.5">
      <h1 className="t-run-title text-chalk">Seed</h1>

      {requirementName !== null && (
        <span className="t-log text-chalk-dim">{requirementName}</span>
      )}

      <div className="flex flex-1 items-center justify-end gap-4">
        {extra}

        <label className="t-secondary flex items-center gap-1.5 text-chalk-dim">
          seed
          <input
            type="number"
            value={seed}
            disabled={phase !== "idle" && phase !== "planned"}
            onChange={(event) => onSeedChange(Number(event.target.value))}
            className="t-num w-[86px] rounded-sm border border-ink-600 bg-ink-900 px-1.5 py-0.5 text-right text-chalk disabled:opacity-50"
          />
        </label>

        <div
          className="t-secondary rounded-sm bg-ink-900 px-2 py-0.5 text-chalk-dim"
          title="Agent reasoning is scripted. The pipeline and all figures are computed from real data."
        >
          Simulation
        </div>
      </div>

      <div className="flex w-full items-center gap-2">
        <Segmented
          label="Speed"
          value={speed}
          options={SPEEDS.map((option) => [option, `${option}x`] as const)}
          onChange={onSpeedChange}
        />

        <div className="flex flex-1 justify-end gap-2">
          <button
            type="button"
            onClick={onPrimary}
            disabled={primaryDisabled}
            className="t-secondary rounded-sm border border-signal px-3 py-1 font-medium text-signal hover:bg-signal/10 disabled:border-ink-600 disabled:text-chalk-dim disabled:opacity-50 disabled:hover:bg-transparent"
          >
            {primaryLabel}
          </button>
          <button
            type="button"
            onClick={onTogglePause}
            disabled={!live}
            className="t-secondary rounded-sm border border-ink-600 px-3 py-1 text-chalk hover:border-chalk-dim disabled:text-chalk-dim disabled:opacity-50"
          >
            {phase === "paused" ? "Resume" : "Pause"}
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={phase === "idle" || phase === "planned"}
            className="t-secondary rounded-sm border border-ink-600 px-3 py-1 text-chalk hover:border-chalk-dim disabled:text-chalk-dim disabled:opacity-50"
          >
            Reset
          </button>
        </div>
      </div>
    </header>
  );
}

function Segmented<T extends number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (next: T) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex overflow-hidden rounded-sm border border-ink-600"
    >
      {options.map(([option, text]) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={value === option}
          onClick={() => onChange(option)}
          className={`t-secondary t-num px-2.5 py-0.5 ${
            value === option ? "bg-ink-600 text-chalk" : "text-chalk-dim hover:text-chalk"
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
