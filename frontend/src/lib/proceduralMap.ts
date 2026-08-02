/** Deterministische, rein clientseitige Kartengrafik.
 *
 * Es gibt weder ein Kartenformat noch echte Geodaten im Spiel -- die Welt
 * ist eine von der KI erzaehlte Textwelt, `Location.coordinates` bleibt
 * unbenutzt. Diese Karte erhebt bewusst keinen Anspruch auf geografische
 * Genauigkeit, sondern liefert ein grobes, atmosphaerisches Kartenbild: aus
 * einem Seed-Text (z. B. der Spiel-ID) entstehen immer dieselbe Kuestenlinie
 * und dieselben Gelaendemerkmale, aus einem zweiten Seed (z. B. dem
 * Ortsnamen) immer derselbe Punkt darauf -- ganz ohne Server-Rundreise oder
 * Bildgenerierung.
 */

export interface Point {
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
const MAX_RADIUS = 38;
const RADIUS_MIN = 0.18;
const RADIUS_MAX = 0.95;

function buildRadiusTable(
  random: () => number,
  pointCount: number,
  base: number,
  amplitude: number,
): number[] {
  return Array.from({ length: pointCount }, () => base + random() * amplitude);
}

function interpolate(table: number[], angleFraction: number): number {
  const n = table.length;
  const normalized = ((angleFraction % 1) + 1) % 1;
  const scaled = normalized * n;
  const index = Math.floor(scaled) % n;
  const next = (index + 1) % n;
  const t = scaled - Math.floor(scaled);
  return table[index] * (1 - t) + table[next] * t;
}

export interface MapShape {
  /** SVG-Pfad ("d"-Attribut) der Kuestenlinie im 0..100-Koordinatenraum. */
  path: string;
  /** Radius (0..1, relativ zu MAX_RADIUS) an einem Winkel-Anteil [0,1). */
  radiusAt: (angleFraction: number) => number;
}

/** Baut eine glatte, geschlossene, unregelmaessige Kuestenlinie.
 *
 * Zwei uebereinandergelegte Rausch-Ebenen statt einer einzelnen: eine grobe
 * Grundform (`pointCount` Eckpunkte) traegt eine zweite, hochfrequentere
 * Welle mit kleinerer Amplitude, die Buchten und Landzungen einstreut --
 * eine reine Kreisform wirkt sonst wie ein Fleck, keine Kuestenlinie. Die
 * Summe wird an vielen Zwischenpunkten abgetastet und ueber quadratische
 * Kurven durch die Mittelpunkte benachbarter Punkte geglaettet (Eckpunkte
 * als Kontrollpunkte) -- ein gaengiger Kniff fuer prozedurale Umrisse, der
 * immer eine geschlossene, nicht selbstueberschneidende Form liefert, weil
 * der Radius als Funktion des Winkels nie negativ wird.
 */
export function generateMapShape(seed: string, pointCount = 12): MapShape {
  const random = mulberry32(hashSeed(seed));
  const primary = buildRadiusTable(random, pointCount, 0.55, 0.4);
  const secondaryCount = pointCount * 2 + 3;
  const secondary = buildRadiusTable(random, secondaryCount, -0.06, 0.24);

  const radiusAt = (angleFraction: number): number => {
    const combined = interpolate(primary, angleFraction) + interpolate(secondary, angleFraction);
    return Math.min(RADIUS_MAX, Math.max(RADIUS_MIN, combined));
  };

  const sampleCount = pointCount * 3;
  const points: Point[] = Array.from({ length: sampleCount }, (_, index) => {
    const angleFraction = index / sampleCount;
    const angle = angleFraction * Math.PI * 2;
    const radius = radiusAt(angleFraction) * MAX_RADIUS;
    return { x: CENTER + Math.cos(angle) * radius, y: CENTER + Math.sin(angle) * radius };
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

/** Deterministischer Punkt innerhalb der Kuestenlinie, gewuerfelt aus einem
 * eigenen Zufallsstrom -- liegt per Konstruktion immer innerhalb der Form,
 * ohne einen Punkt-in-Polygon-Test zu brauchen: Winkel und Radius werden
 * relativ zum Radius der Form an genau diesem Winkel bestimmt. */
function pointInside(
  random: () => number,
  shape: MapShape,
  minFraction: number,
  maxFraction: number,
): Point {
  const angleFraction = random();
  const angle = angleFraction * Math.PI * 2;
  const maxRadius = shape.radiusAt(angleFraction) * MAX_RADIUS;
  const radius = maxRadius * (minFraction + random() * (maxFraction - minFraction));
  return { x: CENTER + Math.cos(angle) * radius, y: CENTER + Math.sin(angle) * radius };
}

/** Standort-Marker: derselbe Ortsname ergibt immer denselben Punkt. */
export function markerPoint(seed: string, shape: MapShape): Point {
  const random = mulberry32(hashSeed(`${seed}:marker`));
  return pointInside(random, shape, 0.15, 0.7);
}

export interface TerrainFeatures {
  mountains: Point[];
  forests: Point[];
  /** Punktfolge eines Flusslaufs von einer Quelle im Landesinneren bis zur
   * Kueste. Leer, wenn diese Karte keinen Fluss zeigt (siehe `compact`). */
  river: Point[];
}

/** Wuerfelt Gelaendemerkmale innerhalb einer Kuestenlinie -- reine Zierde,
 * damit die Karte nach Landschaft statt nach einer eingefaerbten Flaeche
 * aussieht. `compact` liefert weniger und schlichtere Merkmale (fuer die
 * kleineren Detailkarten je Ort). */
export function generateTerrainFeatures(
  seed: string,
  shape: MapShape,
  options: { compact?: boolean } = {},
): TerrainFeatures {
  const random = mulberry32(hashSeed(`${seed}:terrain`));
  const compact = options.compact ?? false;

  const mountainCount = compact ? Math.floor(random() * 2) : 1 + Math.floor(random() * 3);
  const mountains = Array.from({ length: mountainCount }, () =>
    pointInside(random, shape, 0.15, 0.55),
  );

  const forestCount = compact ? 1 + Math.floor(random() * 2) : 2 + Math.floor(random() * 4);
  const forests = Array.from({ length: forestCount }, () => pointInside(random, shape, 0.1, 0.8));

  let river: Point[] = [];
  if (!compact) {
    const source = pointInside(random, shape, 0.2, 0.45);
    const mouthAngleFraction = random();
    const mouthAngle = mouthAngleFraction * Math.PI * 2;
    const mouthRadius = shape.radiusAt(mouthAngleFraction) * MAX_RADIUS;
    const mouth: Point = {
      x: CENTER + Math.cos(mouthAngle) * mouthRadius,
      y: CENTER + Math.sin(mouthAngle) * mouthRadius,
    };
    const steps = 3;
    river = [source];
    for (let step = 1; step < steps; step += 1) {
      const t = step / steps;
      const jitterX = (random() - 0.5) * 10;
      const jitterY = (random() - 0.5) * 10;
      river.push({
        x: source.x + (mouth.x - source.x) * t + jitterX,
        y: source.y + (mouth.y - source.y) * t + jitterY,
      });
    }
    river.push(mouth);
  }

  return { mountains, forests, river };
}
