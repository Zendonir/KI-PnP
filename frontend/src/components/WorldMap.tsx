/** Grobe, rein clientseitig erzeugte Kartengrafik.
 *
 * Keine echten Geodaten, keine Bildgenerierung -- siehe lib/proceduralMap.ts
 * fuer die Herleitung. Dieselbe Spiel-ID ergibt immer dieselbe Kuestenlinie
 * samt Gelaendemerkmalen, derselbe Ortsname immer denselben Punkt darauf.
 */

import { useMemo } from "react";

import {
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
  const shape = useMemo(() => {
    const shapeSeed = detail && markerSeed ? `${seed}:detail:${markerSeed}` : seed;
    return generateMapShape(shapeSeed, detail ? 8 : 12);
  }, [seed, detail, markerSeed]);

  const terrain = useMemo(
    () => generateTerrainFeatures(detail && markerSeed ? `${seed}:detail:${markerSeed}` : seed, shape, { compact: detail }),
    [seed, detail, markerSeed, shape],
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

        {terrain.river.length > 1 && (
          <polyline
            points={terrain.river.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
            className="fill-none stroke-[#5b7f96]/70"
            strokeWidth={0.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {terrain.mountains.map((point, index) => (
          <MountainIcon key={`m${index}`} x={point.x} y={point.y} />
        ))}
        {terrain.forests.map((point, index) => (
          <ForestIcon key={`f${index}`} x={point.x} y={point.y} />
        ))}

        {marker && <LocationPin x={marker.x} y={marker.y} />}

        {!detail && <CompassRose />}
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
