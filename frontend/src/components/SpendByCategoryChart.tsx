import { useState } from "react";

import type { CategorySpend } from "../api/insights";
import { formatAmount } from "../lib/format";

interface Props {
  categories: CategorySpend[];
  total: string;
}

const ROW_HEIGHT = 30;
const BAR_HEIGHT = 14;
const LABEL_WIDTH = 132;
const VALUE_WIDTH = 96;
const MAX_ROWS = 8;

/**
 * Horizontal bars, largest first.
 *
 * One hue rather than one colour per category: this chart answers "how much",
 * and identity is already carried by the axis labels. Colouring ten bars ten
 * ways would be decoration competing with the data — and a pie would be worse
 * still, since comparing angles is harder than comparing lengths.
 *
 * Horizontal because Indian category names ("Food & Dining", "Entertainment")
 * are long; vertical bars would need rotated labels.
 */
export function SpendByCategoryChart({ categories, total }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (categories.length === 0) {
    return <p className="muted">No spending recorded for this month yet.</p>;
  }

  // Anything past the top few is a long tail that crowds the chart; it stays in
  // the total, and the "+N more" line keeps that honest.
  const rows = categories.slice(0, MAX_ROWS);
  const hidden = categories.length - rows.length;
  const largest = Math.max(...rows.map((row) => Number(row.amount)));
  const width = 560;
  const plotWidth = width - LABEL_WIDTH - VALUE_WIDTH;
  const height = rows.length * ROW_HEIGHT;

  return (
    <figure className="chart">
      <figcaption className="chart__caption">
        <span className="chart__total">{formatAmount(total)}</span>
        <span className="muted small">total spend</span>
      </figcaption>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart__svg"
        role="img"
        aria-label={`Spending by category. Total ${formatAmount(total)}.`}
      >
        {rows.map((row, index) => {
          const value = Number(row.amount);
          const barWidth = largest > 0 ? (value / largest) * plotWidth : 0;
          const y = index * ROW_HEIGHT;
          const isHovered = hovered === index;

          return (
            <g
              key={row.category ?? "uncategorised"}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Full-row hit target: bigger than the mark, per the interaction rule. */}
              <rect
                x="0"
                y={y}
                width={width}
                height={ROW_HEIGHT}
                fill="transparent"
                className="chart__hit"
              />
              <text
                x={LABEL_WIDTH - 10}
                y={y + ROW_HEIGHT / 2}
                textAnchor="end"
                dominantBaseline="middle"
                className="chart__label"
              >
                {row.name}
              </text>
              <rect
                x={LABEL_WIDTH}
                y={y + (ROW_HEIGHT - BAR_HEIGHT) / 2}
                width={Math.max(barWidth, 2)}
                height={BAR_HEIGHT}
                rx="4"
                className={`chart__bar${isHovered ? " chart__bar--hover" : ""}`}
              />
              {/* Direct value labels rather than an axis: eight numbers are
                  easier to read than gridlines plus mental arithmetic. */}
              <text
                x={LABEL_WIDTH + Math.max(barWidth, 2) + 8}
                y={y + ROW_HEIGHT / 2}
                dominantBaseline="middle"
                className="chart__value"
              >
                {formatAmount(row.amount)}
              </text>
            </g>
          );
        })}
      </svg>

      {hidden > 0 && (
        <p className="muted small">
          {hidden} smaller {hidden === 1 ? "category is" : "categories are"} included in the
          total but not shown.
        </p>
      )}
    </figure>
  );
}
