/** Kleine, wiederverwendbare Bausteine der Oberflaeche. */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "danger" | "subtle";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-ember-500 text-ink-950 hover:bg-ember-400 active:bg-ember-400 disabled:bg-ink-600 disabled:text-ink-800",
  ghost:
    "bg-ink-700 text-parchment hover:bg-ink-600 active:bg-ink-600 disabled:text-parchment/40",
  danger: "bg-blood-500 text-parchment hover:opacity-90 disabled:opacity-40",
  subtle: "bg-transparent text-parchment/70 hover:text-parchment",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`min-h-11 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-ink-700 bg-ink-800/80 p-4 ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && (
            <h2 className="text-xs font-bold uppercase tracking-[0.18em] text-ember-400">
              {title}
            </h2>
          )}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "bad" | "warn";
}) {
  const tones = {
    neutral: "bg-ink-700 text-parchment/80",
    good: "bg-moss-500/25 text-moss-500",
    bad: "bg-blood-500/25 text-blood-500",
    warn: "bg-ember-500/20 text-ember-400",
  } as const;
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-parchment/60">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-parchment/45">{hint}</span>}
    </label>
  );
}

const CONTROL =
  "w-full min-h-11 rounded-xl border border-ink-600 bg-ink-900 px-3 py-2.5 text-base text-parchment outline-none transition focus:border-ember-500";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function Select({
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...rest} className={`${CONTROL} ${rest.className ?? ""}`}>
      {children}
    </select>
  );
}

/** Vollflaechiger Dialog. Ohne `onDismiss` laesst sich der Hintergrund nicht
 * wegtippen -- fuer Momente, die eine bewusste Entscheidung verlangen. */
export function Modal({
  children,
  onDismiss,
}: {
  children: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/85 p-4 backdrop-blur-sm"
      onClick={onDismiss}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-ink-600 bg-ink-800 p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-parchment/60">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-ember-500" />
      {label && <span>{label}</span>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-xl border border-blood-500/40 bg-blood-500/10 px-3 py-2 text-sm text-parchment"
    >
      {children}
    </p>
  );
}

export function StatBar({ stat }: { stat: { key: string; value: number; max_value: number | null } }) {
  const max = stat.max_value ?? stat.value;
  const ratio = max > 0 ? Math.max(0, Math.min(1, stat.value / max)) : 0;
  const colors: Record<string, string> = {
    hp: "bg-blood-500",
    mana: "bg-sky-500",
    stamina: "bg-moss-500",
  };
  const labels: Record<string, string> = {
    hp: "Leben",
    mana: "Mana",
    stamina: "Ausdauer",
  };
  return (
    <div>
      <div className="flex justify-between text-xs text-parchment/70">
        <span>{labels[stat.key] ?? stat.key}</span>
        <span className="tabular-nums">
          {stat.value}
          {stat.max_value !== null ? ` / ${stat.max_value}` : ""}
        </span>
      </div>
      {stat.max_value !== null && (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-700">
          <div
            className={`h-full rounded-full transition-all ${colors[stat.key] ?? "bg-ember-500"}`}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
