/** Deterministische, rein clientseitige Kartengrafik.
 *
 * Es gibt weder ein Kartenformat noch echte Geodaten im Spiel -- die Welt
 * ist eine von der KI erzaehlte Textwelt, `Location.coordinates` bleibt
 * unbenutzt. Diese Karte erhebt bewusst keinen Anspruch auf geografische
 * Genauigkeit, sondern liefert ein grobes, atmosphaerisches Kartenbild: aus
 * einem Seed-Text (z. B. der Spiel-ID) entsteht immer dieselbe Kuestenlinie,
 * aus einem zweiten Seed (z. B. dem Ortsnamen) immer derselbe Punkt darauf
 * -- ganz ohne Server-Rundreise oder Bildgenerierung.
 */

interface Point {
  x: number;
  y: number;
}

function hashSeed(text: string): number {
  // FNV-1a, 32-bit -- klein, schnell, reicht fuer eine Bild-Saat.
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const CENTER = 50;
const MAX_RADIUS = 42;

export interface MapShape {
  /** SVG-Pfad ("d"-Attribut) der Kuestenlinie im 0..100-Koordinatenraum. */
  path: string;
  /** Radius (0..1, relativ zu MAX_RADIUS) an einem Winkel-Anteil [0,1). */
  radiusAt: (angleFraction: number) => number;
}

/** Baut eine glatte, geschlossene, unregelmaessige Kuestenlinie.
 *
 * `pointCount` Eckpunkte werden gleichmaessig um einen Kreis verteilt und
 * per Seed zufaellig verschoben; quadratische Kurven durch die Mittelpunkte
 * benachbarter Eckpunkte (Eckpunkte selbst als Kontrollpunkte) ergeben eine
 * organische Blob-Form ohne Ecken -- ein gaengiger Kniff fuer prozedurale
 * Insel-/Kontinent-Umrisse.
 */
export function generateMapShape(seed: string, pointCount = 10): MapShape {
  const random = mulberry32(hashSeed(seed));
  const radii = Array.from({ length: pointCount }, () => 0.55 + random() * 0.42);

  const radiusAt = (angleFraction: number): number => {
    const normalized = ((angleFraction % 1) + 1) % 1;
    const scaled = normalized * pointCount;
    const index = Math.floor(scaled) % pointCount;
    const next = (index + 1) % pointCount;
    const t = scaled - Math.floor(scaled);
    return radii[index] * (1 - t) + radii[next] * t;
  };

  const points: Point[] = radii.map((radius, index) => {
    const angle = (index / pointCount) * Math.PI * 2;
    return {
      x: CENTER + Math.cos(angle) * radius * MAX_RADIUS,
      y: CENTER + Math.sin(angle) * radius * MAX_RADIUS,
    };
  });

  const midpoint = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

  let path = "";
  points.forEach((point, index) => {
    const next = points[(index + 1) % points.length];
    const mid = midpoint(point, next);
    path +=
      index === 0
        ? `M ${mid.x.toFixed(2)} ${mid.y.toFixed(2)} `
        : `Q ${point.x.toFixed(2)} ${point.y.toFixed(2)} ${mid.x.toFixed(2)} ${mid.y.toFixed(2)} `;
  });
  path += "Z";

  return { path, radiusAt };
}

/** Deterministischer Punkt innerhalb der Kuestenlinie fuer einen Seed
 * (z. B. den Ortsnamen) -- liegt per Konstruktion immer innerhalb der Form,
 * ohne einen Punkt-in-Polygon-Test zu brauchen: Winkel und Radius werden
 * relativ zum Radius der Form an genau diesem Winkel gewuerfelt. */
export function markerPoint(seed: string, shape: MapShape): Point {
  const random = mulberry32(hashSeed(`${seed}:marker`));
  const angleFraction = random();
  const angle = angleFraction * Math.PI * 2;
  const radius = shape.radiusAt(angleFraction) * MAX_RADIUS * (0.15 + random() * 0.55);
  return {
    x: CENTER + Math.cos(angle) * radius,
    y: CENTER + Math.sin(angle) * radius,
  };
}
