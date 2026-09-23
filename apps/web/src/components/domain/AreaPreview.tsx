import { cn } from '@/lib/cn';

/**
 * پیش‌نمایش محدودهٔ مطالعه — مرحلهٔ ۱ گردش‌کار شهری (FR-CITY-01).
 *
 * فقط شکل چندضلعی، بدون کاشی نقشه: نقشهٔ کامل با کاشی داخلی مال
 * FR-CITY-02 است (§11 «هیچ وابستگی به CDN خارجی»). همین شکل برای اینکه
 * دانشجو ببیند فایلش همان محدودهٔ مورد نظر است، کافی است.
 *
 * طول جغرافیایی با کسینوس عرض فشرده می‌شود تا شکل در عرض ۳۰ درجه کشیده
 * به نظر نرسد.
 */

type Rings = number[][][];

export function AreaPreview({
  polygons,
  className,
  label = 'شکل محدودهٔ مطالعه',
}: {
  /** MultiPolygon: فهرست چندضلعی، هرکدام فهرست حلقه، هر حلقه فهرست [طول، عرض]. */
  polygons: Rings[];
  className?: string;
  label?: string;
}) {
  const outers = polygons.map((polygon) => polygon[0] ?? []).filter((ring) => ring.length > 2);
  if (outers.length === 0) return null;

  const points = outers.flat().map(([lon = 0, lat = 0]) => [lon, lat] as const);
  const lats = points.map(([, lat]) => lat);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const squeeze = Math.cos((midLat * Math.PI) / 180);
  const xs = points.map(([lon]) => lon * squeeze);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...lats);
  const maxY = Math.max(...lats);
  const span = Math.max(maxX - minX, maxY - minY) || 1;
  const pad = span * 0.08;
  const size = 100;
  const scale = size / (span + pad * 2);

  const toPath = (ring: number[][]) =>
    ring
      .map(([lon = 0, lat = 0], index) => {
        const x = (lon * squeeze - minX + pad) * scale;
        // محور y در SVG رو به پایین است؛ شمال باید بالا باشد.
        const y = (maxY - lat + pad) * scale;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ') + ' Z';

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={label}
      className={cn('aspect-square w-full rounded-[var(--radius-md)] bg-[var(--bg-sunken)]', className)}
    >
      {outers.map((ring, index) => (
        <path
          key={index}
          d={toPath(ring)}
          fill="color-mix(in oklch, var(--brand-500) 18%, transparent)"
          stroke="var(--brand-600)"
          strokeWidth={1.2}
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}

/** GeoJSON دلخواه ← MultiPolygon برای پیش‌نمایش؛ شکل ناشناخته یعنی بدون پیش‌نمایش. */
export function polygonsOf(geojson: unknown): Rings[] {
  if (!geojson || typeof geojson !== 'object') return [];
  const value = geojson as { type?: string; coordinates?: unknown; features?: unknown; geometry?: unknown };
  switch (value.type) {
    case 'FeatureCollection':
      return Array.isArray(value.features) ? value.features.flatMap((f) => polygonsOf(f)) : [];
    case 'Feature':
      return polygonsOf(value.geometry);
    case 'Polygon':
      return Array.isArray(value.coordinates) ? [value.coordinates as Rings] : [];
    case 'MultiPolygon':
      return Array.isArray(value.coordinates) ? (value.coordinates as Rings[]) : [];
    default:
      return [];
  }
}
