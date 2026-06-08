import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

// Shared control primitives for the paleo-coastline panel.
//
// The panel previously repeated near-identical Tailwind blobs for every button
// group, toggle, and legend. Centralizing them here keeps spacing, borders, and
// the cyan accent consistent, and lets the panel read as a calm instrument
// rather than a stack of competing bordered cards.

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70";

export const sectionTitleClass =
  "text-[11px] font-medium uppercase tracking-[0.14em] text-gray-400";

export const valueClass = "font-mono text-[11px] text-cyan-200";

// ---------------------------------------------------------------------------
// Section: a titled group, optionally collapsible. Top-level sections are
// separated by a hairline divider + vertical rhythm instead of boxing each one.
// ---------------------------------------------------------------------------

interface SectionProps {
  title: string;
  icon?: ReactNode;
  trailing?: ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
  divider?: boolean;
  children: ReactNode;
}

export function Section({
  title,
  icon,
  trailing,
  collapsible = false,
  defaultOpen = true,
  divider = true,
  children,
}: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const expanded = collapsible ? open : true;

  const header = (
    <>
      <span className={`flex items-center gap-1.5 ${sectionTitleClass}`}>
        {icon}
        {title}
      </span>
      <span className="flex items-center gap-2">
        {trailing}
        {collapsible ? (
          <ChevronDown
            size={14}
            className={`text-gray-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          />
        ) : null}
      </span>
    </>
  );

  return (
    <section className={divider ? "border-t border-white/[0.06] pt-4" : ""}>
      {collapsible ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className={`flex w-full items-center justify-between gap-3 rounded-md py-0.5 transition-colors hover:text-white ${focusRing}`}
          aria-expanded={open}
        >
          {header}
        </button>
      ) : (
        <div className="flex items-center justify-between gap-3 py-0.5">{header}</div>
      )}
      {expanded ? <div className="mt-3 space-y-3">{children}</div> : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// SegmentedControl: the grid-of-pills pattern used by period chips, scene
// profile, terrain mesh, terrain source mode, and surface style.
// ---------------------------------------------------------------------------

export interface SegmentedOption<T extends string> {
  id: T;
  label: string;
  title?: string;
}

interface SegmentedControlProps<T extends string> {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (id: T) => void;
  columns?: number;
  ariaLabel?: string;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  columns,
  ariaLabel,
}: SegmentedControlProps<T>) {
  const cols = columns ?? options.length;
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="grid gap-1 rounded-lg bg-white/[0.04] p-1"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {options.map((option) => {
        const active = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            className={`min-h-8 rounded-md px-2 text-xs font-semibold transition-colors ${focusRing} ${
              active
                ? "bg-cyan-300 text-gray-950 shadow-sm"
                : "text-gray-300 hover:bg-white/[0.06] hover:text-white"
            }`}
            aria-pressed={active}
            title={option.title}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TogglePill: an icon + label switch with a color accent when active.
// ---------------------------------------------------------------------------

type Accent = "cyan" | "emerald" | "sky" | "amber";

const ACTIVE_ACCENT: Record<Accent, string> = {
  cyan: "border-cyan-300/40 bg-cyan-300 text-gray-950",
  emerald: "border-emerald-300/40 bg-emerald-300 text-gray-950",
  sky: "border-sky-300/40 bg-sky-300 text-gray-950",
  amber: "border-amber-300/40 bg-amber-300 text-gray-950",
};

interface TogglePillProps {
  active: boolean;
  onClick: () => void;
  label: string;
  icon?: ReactNode;
  title?: string;
  accent?: Accent;
}

export function TogglePill({
  active,
  onClick,
  label,
  icon,
  title,
  accent = "cyan",
}: TogglePillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold transition-colors ${focusRing} ${
        active
          ? ACTIVE_ACCENT[accent]
          : "border-white/10 bg-white/[0.03] text-gray-300 hover:bg-white/[0.08] hover:text-white"
      }`}
      aria-pressed={active}
      title={title}
    >
      {icon}
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Legend: swatch + label rows. The title on each row is the hover explanation
// that tells the viewer what a color means (in place of a permanent legend).
// ---------------------------------------------------------------------------

export interface LegendItem {
  label: string;
  swatch: string;
  title?: string;
}

interface LegendProps {
  items: readonly LegendItem[];
  columns?: number;
}

export function Legend({ items, columns = 2 }: LegendProps) {
  return (
    <div
      className="grid gap-x-3 gap-y-1.5"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {items.map((item) => (
        <span
          key={item.label}
          className="flex cursor-help items-center gap-2 text-[11px] text-gray-400"
          title={item.title}
        >
          <span className={`h-1.5 w-4 shrink-0 rounded-full ${item.swatch}`} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
