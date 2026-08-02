/** Grobe, rein clientseitig erzeugte Kartengrafik.
 *
 * Keine echten Geodaten, keine Bildgenerierung -- siehe lib/proceduralMap.ts
 * fuer die Herleitung. Dieselbe Spiel-ID ergibt immer dieselbe Kuestenlinie,
 * derselbe Ortsname immer denselben Punkt darauf.
 */

import { useMemo } from "react";

import { generateMapShape, markerPoint } from "../lib/proceduralMap";

export function WorldMap({
  seed,
  markerSeed = null,
  detail = false,
  size = 220,
}: {
  /** Legt die Kuestenlinie fest -- ueblicherweise die Spiel-ID. */
  seed: string;
  /** Legt den "Hier seid ihr"-Punkt fest, z. B. der Ortsname. `null`:
   * kein Punkt (Standort noch unbekannt). */
  markerSeed?: string | null;
  /** Kleinere, eigenstaendige Kuestenlinie fuer eine Detailkarte -- der
   * Marker sitzt dabei immer in der Mitte, die Detailkarte *ist* der Ort. */
  detail?: boolean;
  size?: number;
}) {
  const shape = useMemo(() => {
    const shapeSeed = detail && markerSeed ? `${seed}:detail:${markerSeed}` : seed;
    return generateMapShape(shapeSeed, detail ? 7 : 11);
  }, [seed, detail, markerSeed]);

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
        <path d={shape.path} className="fill-ember-500/25 stroke-ink-800" strokeWidth={1.2} />
        {marker && (
          <>
            <circle cx={marker.x} cy={marker.y} r={3} className="fill-none stroke-ember-600/60">
              <animate attributeName="r" values="3;6;3" dur="2.4s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.6;0;0.6" dur="2.4s" repeatCount="indefinite" />
            </circle>
            <circle
              cx={marker.x}
              cy={marker.y}
              r={2.4}
              className="fill-ember-600 stroke-ink-900"
              strokeWidth={0.6}
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
