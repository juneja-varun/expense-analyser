import { useState } from "react";

import type { MonthTotals } from "../api/insights";
import { formatAmount } from "../lib/format";

interface Props {
  months: MonthTotals[];
}

const WIDTH = 560;
const HEIGHT = 200;
const PAD_TOP = 12;
const PAD_BOTTOM = 26;
const BAR_GAP = 2;

function monthLabel(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString("en-IN", { month: "short" });
}

/**
 * Money in and money out per month, as grouped bars.
 *
 * Grouped rather than stacked: stacking would imply income and spend sum to
 * something meaningful, and the question here is which was larger.
 *
 * Both series share one axis — they are the same unit. A second y-scale would
 * let the two lines cross wherever the scales happened to put them, which is
 * the most common way a chart lies.
 */
export function MonthlyTrendChart({ months }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);

  const hasActivity = months.some(
    (month) => Number(month.spent) > 0 || Number(month.received) > 0,
  );
  if (!hasActivity) {
    return <p className="muted">Upload a few months of statements to see a trend.</p>;
  }

  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const largest = Math.max(
    ...months.flatMap((month) => [Number(month.spent), Number(month.received)]),
    1,
  );
  const slotWidth = WIDTH / months.length;
  const barWidth = Math.max((slotWidth - BAR_GAP * 3) / 2, 3);

  const scale = (value: number) => (value / largest) * plotHeight;

  return (
    <figure className="chart">
      <figcaption className="chart__legend">
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--received" aria-hidden="true" />
          Received
        </span>
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--spent" aria-hidden="true" />
          Spent
        </span>
      </figcaption>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart__svg"
        role="img"
        aria-label="Money received and spent per month"
      >
        {/* Baseline only — no gridlines. With direct values on hover they would
            add ink without adding information. */}
        <line
          x1="0"
          y1={PAD_TOP + plotHeight}
          x2={WIDTH}
          y2={PAD_TOP + plotHeight}
          className="chart__axis"
        />

        {months.map((month, index) => {
          const x = index * slotWidth;
          const received = scale(Number(month.received));
          const spent = scale(Number(month.spent));
          const baseline = PAD_TOP + plotHeight;
          const isHovered = hovered === index;

          return (
            <g
              key={month.month}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              <rect
                x={x}
                y="0"
                width={slotWidth}
                height={HEIGHT}
                fill="transparent"
                className="chart__hit"
              />
              <rect
                x={x + BAR_GAP}
                y={baseline - received}
                width={barWidth}
                height={Math.max(received, received > 0 ? 2 : 0)}
                rx="4"
                className="chart__bar chart__bar--received"
                opacity={hovered === null || isHovered ? 1 : 0.45}
              />
              <rect
                x={x + BAR_GAP * 2 + barWidth}
                y={baseline - spent}
                width={barWidth}
                height={Math.max(spent, spent > 0 ? 2 : 0)}
                rx="4"
                className="chart__bar chart__bar--spent"
                opacity={hovered === null || isHovered ? 1 : 0.45}
              />
              <text
                x={x + slotWidth / 2}
                y={HEIGHT - 8}
                textAnchor="middle"
                className="chart__label chart__label--axis"
              >
                {monthLabel(month.month)}
              </text>
            </g>
          );
        })}
      </svg>

      {/* A fixed-height readout rather than a floating tooltip: it never covers
          the bars, and the layout doesn't jump as the pointer moves. */}
      <p className="chart__readout" aria-live="polite">
        {hovered !== null ? (
          <>
            <strong>{monthLabel(months[hovered].month)}</strong> · received{" "}
            {formatAmount(months[hovered].received)} · spent{" "}
            {formatAmount(months[hovered].spent)} · net{" "}
            <span className={Number(months[hovered].net) < 0 ? "debit" : "credit"}>
              {formatAmount(months[hovered].net)}
            </span>
          </>
        ) : (
          <span className="muted">Hover a month for its totals.</span>
        )}
      </p>
    </figure>
  );
}
