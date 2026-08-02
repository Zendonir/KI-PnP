/** Grobe, rein clientseitig erzeugte Kartengrafik.
 *
 * Keine echten Geodaten, keine Bildgenerierung -- siehe lib/proceduralMap.ts
 * fuer die Herleitung. Dieselbe Spiel-ID ergibt immer dieselbe Kuestenlinie
 * samt Gelaendemerkmalen, derselbe Ortsname immer denselben Punkt darauf.
 */

import { useMemo } from "react";

import {
  CONTOUR_SCALES,
  coastlineTicks,
  generateMapShape,
  generateTerrainFeatures,
  markerPoint,
  type Point,
} from "../lib/proceduralMap";

function MountainIcon({ x, y }: Point) {
  // Zwei ueberlappende Dreiecke -- das gaengige Kartensymbol fuer Gebirge.
  return (
    <g className="fill-ink-700/80 stroke-ink-800" strokeWidth={0.35} strokeLinejoin="round">
      <polygon points={`${x - 4},${y + 2.3} ${x - 1},${y - 3.2} ${x + 2},${y + 2.3}`} />
      <polygon points={`${x},${y + 2.3} ${x + 3},${y - 2.2} ${x + 6},${y + 2.3}`} />
      <line x1={x - 1.6} y1={y - 1.3} x2={x - 0.7} y2={y - 2.1} className="stroke-parchment/70" strokeWidth={0.3} />
    </g>
  );
}

function HillIcon({ x, y }: Point) {
  // Zwei kleine, halboffene Buckel -- deutlich flacher als ein Gebirgssymbol.
  return (
    <g className="fill-none stroke-ink-700/70" strokeWidth={0.5} strokeLinecap="round">
      <path d={`M ${x - 3} ${y + 1} Q ${x - 1.5} ${y - 2} ${x} ${y + 1}`} />
      <path d={`M ${x} ${y + 1.4} Q ${x + 1.8} ${y - 1.6} ${x + 3.6} ${y + 1.4}`} />
    </g>
  );
}

function ForestIcon({ x, y }: Point) {
  return (
    <g className="fill-moss-500/80">
      <circle cx={x - 1.6} cy={y} r={1.3} />
      <circle cx={x + 1.6} cy={y} r={1.3} />
      <circle cx={x} cy={y - 1.4} r={1.3} />
    </g>
  );
}

function LakeIcon({ x, y }: Point) {
  return (
    <ellipse
      cx={x}
      cy={y}
      rx={2.6}
      ry={1.9}
      className="fill-[#5b7f96]/60 stroke-[#3f5c6e]/70"
      strokeWidth={0.4}
    />
  );
}

function LocationPin({ x, y }: Point) {
  return (
    <g>
      <circle cx={x} cy={y} r={3} className="fill-none stroke-blood-500/50">
        <animate attributeName="r" values="3;6;3" dur="2.4s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.6;0;0.6" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <path
        d={`M ${x} ${y} C ${x - 4} ${y - 6} ${x - 4} ${y - 10} ${x} ${y - 10} C ${x + 4} ${y - 10} ${x + 4} ${y - 6} ${x} ${y} Z`}
        className="fill-blood-500 stroke-ink-900"
        strokeWidth={0.5}
      />
      <circle cx={x} cy={y - 6.5} r={1.6} className="fill-parchment" />
    </g>
  );
}

function CompassRose() {
  return (
    <g transform="translate(85, 16)" className="opacity-70">
      <circle r={7} className="fill-none stroke-ink-800" strokeWidth={0.6} />
      <path d="M0,-7 1.6,-1.6 0,0 -1.6,-1.6 Z" className="fill-blood-500 stroke-ink-900" strokeWidth={0.3} />
      <path d="M0,7 1.6,1.6 0,0 -1.6,1.6 Z" className="fill-ink-700 stroke-ink-900" strokeWidth={0.3} />
      <path d="M-7,0 -1.6,1.6 0,0 -1.6,-1.6 Z" className="fill-ink-600 stroke-ink-900" strokeWidth={0.3} />
      <path d="M7,0 1.6,1.6 0,0 1.6,-1.6 Z" className="fill-ink-600 stroke-ink-900" strokeWidth={0.3} />
      <text y={-9.5} textAnchor="middle" className="fill-ink-800 text-[5px] font-bold">
        N
      </text>
    </g>
  );
}

/** Kleiner, unbeschrifteter Massstabsbalken -- reine Kartenzierde, keine
 * echte Einheit, damit nichts eine falsche Praezision vorgaukelt. */
function ScaleBar() {
  return (
    <g transform="translate(10, 92)" className="opacity-60">
      <line x1={0} y1={0} x2={14} y2={0} className="stroke-ink-800" strokeWidth={0.6} />
      <line x1={0} y1={-1.2} x2={0} y2={1.2} className="stroke-ink-800" strokeWidth={0.6} />
      <line x1={7} y1={-0.8} x2={7} y2={0.8} className="stroke-ink-800" strokeWidth={0.4} />
      <line x1={14} y1={-1.2} x2={14} y2={1.2} className="stroke-ink-800" strokeWidth={0.6} />
    </g>
  );
}

const GRID_LINES = [20, 40, 60, 80];

export function WorldMap({
  seed,
  markerSeed = null,
  detail = false,
  size = 220,
}: {
  /** Legt die Kuestenlinie und Gelaendemerkmale fest -- ueblicherweise die
   * Spiel-ID. */
  seed: string;
  /** Legt den "Hier seid ihr"-Punkt fest, z. B. der Ortsname. `null`:
   * kein Punkt (Standort noch unbekannt). */
  markerSeed?: string | null;
  /** Kleinere, eigenstaendige Kuestenlinie fuer eine Detailkarte -- ohne
   * Rahmen/Kompassrose, der Marker sitzt dabei immer in der Mitte, die
   * Detailkarte *ist* der Ort. */
  detail?: boolean;
  size?: number;
}) {
  const shapeSeed = useMemo(
    () => (detail && markerSeed ? `${seed}:detail:${markerSeed}` : seed),
    [seed, detail, markerSeed],
  );

  const shape = useMemo(() => generateMapShape(shapeSeed, detail ? 8 : 12), [shapeSeed, detail]);

  const terrain = useMemo(
    () => generateTerrainFeatures(shapeSeed, shape, { compact: detail }),
    [shapeSeed, shape, detail],
  );

  const ticks = useMemo(
    () => coastlineTicks(shape, detail ? 32 : 56),
    [shape, detail],
  );

  const marker = useMemo(() => {
    if (!markerSeed) return null;
    return detail ? { x: 50, y: 50 } : markerPoint(markerSeed, shape);
  }, [markerSeed, shape, detail]);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        viewBox="0 0 100 100"
        width={size}
        height={size}
        role="img"
        aria-label={
          markerSeed
            ? `Karte mit markiertem Standort: ${markerSeed}`
            : "Karte, Standort noch unbekannt"
        }
        className="rounded-xl bg-parchment"
      >
        {!detail && (
          <g className="stroke-ink-800/10" strokeWidth={0.3} strokeDasharray="1.5 1.5">
            {GRID_LINES.map((v) => (
              <line key={`h${v}`} x1={4} y1={v} x2={96} y2={v} />
            ))}
            {GRID_LINES.map((v) => (
              <line key={`v${v}`} x1={v} y1={4} x2={v} y2={96} />
            ))}
          </g>
        )}

        {!detail && (
          <g className="fill-none stroke-ink-800/15" strokeWidth={0.5}>
            <circle cx={50} cy={50} r={46} />
            <circle cx={50} cy={50} r={40} />
          </g>
        )}

        <path
          d={shape.path}
          className="fill-ember-500/35 stroke-ink-800"
          strokeWidth={detail ? 1 : 1.1}
        />

        <g className="stroke-ink-800/45" strokeWidth={0.4} strokeLinecap="round">
          {ticks.map((tick, index) => (
            <line key={index} x1={tick.x1} y1={tick.y1} x2={tick.x2} y2={tick.y2} />
          ))}
        </g>

        {CONTOUR_SCALES.map((scale) => (
          <path
            key={scale}
            d={shape.path}
            transform={`translate(50 50) scale(${scale}) translate(-50 -50)`}
            className="fill-none stroke-ink-800/20"
            strokeWidth={0.4}
            strokeDasharray="1 1.4"
          />
        ))}

        {terrain.river.length > 1 && (
          <polyline
            points={terrain.river.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
            className="fill-none stroke-[#5b7f96]/70"
            strokeWidth={0.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {terrain.lake && <LakeIcon x={terrain.lake.x} y={terrain.lake.y} />}
        {terrain.hills.map((point, index) => (
          <HillIcon key={`h${index}`} x={point.x} y={point.y} />
        ))}
        {terrain.mountains.map((point, index) => (
          <MountainIcon key={`m${index}`} x={point.x} y={point.y} />
        ))}
        {terrain.forests.map((point, index) => (
          <ForestIcon key={`f${index}`} x={point.x} y={point.y} />
        ))}

        {marker && <LocationPin x={marker.x} y={marker.y} />}

        {!detail && <CompassRose />}
        {!detail && <ScaleBar />}
        {!detail && (
          <>
            <rect
              x={2.5}
              y={2.5}
              width={95}
              height={95}
              rx={4}
              className="fill-none stroke-ink-800"
              strokeWidth={1.2}
            />
            <rect
              x={4.5}
              y={4.5}
              width={91}
              height={91}
              rx={3}
              className="fill-none stroke-ink-800/50"
              strokeWidth={0.5}
            />
          </>
        )}
      </svg>
      <p className="text-xs text-parchment/50">
        {markerSeed ? `📍 ${markerSeed}` : "Standort noch unbekannt"}
      </p>
    </div>
  );
}
