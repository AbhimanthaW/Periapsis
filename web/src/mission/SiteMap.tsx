import type { Geometry } from './api'
import type { ContextAsset } from './site'

type Position = [number, number]
const isPosition = (value: unknown): value is Position =>
  Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number'

// Lines (in lon/lat) that a geometry contributes to the map; unsupported shapes draw nothing.
function lines(geometry: Geometry | undefined): { points: Position[]; closed: boolean }[] {
  if (!geometry) return []
  const coordinates = geometry.coordinates
  if (geometry.type === 'Point' && isPosition(coordinates)) return [{ points: [coordinates], closed: false }]
  if (geometry.type === 'LineString' && Array.isArray(coordinates) && coordinates.every(isPosition)) return [{ points: coordinates, closed: false }]
  if (geometry.type === 'Polygon' && Array.isArray(coordinates)) {
    return coordinates.filter((ring): ring is Position[] => Array.isArray(ring) && ring.every(isPosition)).map(points => ({ points, closed: true }))
  }
  return []
}

type Props = {
  asset: ContextAsset
  support: Geometry[]
  query: Geometry | undefined
}

/** Local optical context with the evidence support and query geometry, in Mars lon/lat. */
export function SiteMap({ asset, support, query }: Props) {
  const [west, south, east, north] = asset.extent
  const project = ([lon, lat]: Position) => [
    (lon - west) / (east - west) * asset.width,
    (north - lat) / (north - south) * asset.height,
  ]
  const path = (points: Position[], closed: boolean) =>
    points.map((point, index) => `${index ? 'L' : 'M'}${project(point).map(value => value.toFixed(1)).join(' ')}`).join(' ') + (closed ? ' Z' : '')
  const queryLines = lines(query)
  const queryPoint = query?.type === 'Point' && isPosition(query.coordinates) ? project(query.coordinates) : null
  return (
    <figure className="mission-map">
      <svg style={{ maxWidth: asset.width }} viewBox={`0 0 ${asset.width} ${asset.height}`} role="img" aria-label={`${asset.title} with evidence support and query geometry`}>
        <image href={asset.url} width={asset.width} height={asset.height} preserveAspectRatio="none"/>
        {support.flatMap(lines).map((line, index) => (
          <path key={`support-${index}`} className="mission-map-support" d={path(line.points, line.closed)}/>
        ))}
        {queryLines.filter(line => line.points.length > 1).map((line, index) => (
          <path key={`query-${index}`} className="mission-map-query" d={path(line.points, line.closed)}/>
        ))}
        {queryLines.flatMap(line => line.points).map((point, index) => {
          const [x, y] = project(point)
          return <circle key={`vertex-${index}`} className="mission-map-vertex" cx={x} cy={y} r={9}/>
        })}
        {queryPoint && <circle className="mission-map-vertex" cx={queryPoint[0]} cy={queryPoint[1]} r={12}/>}
      </svg>
      <figcaption>
        <span className="mission-badge" title="Observed source imagery">OBS</span>
        {asset.title} · {asset.nativeMeters} m native · {asset.credit}
        {(support.length > 0 || query) && (
          <span className="mission-legend"><i className="mission-swatch-support"/>Evidence usable support <i className="mission-swatch-query"/>Evidence query</span>
        )}
      </figcaption>
    </figure>
  )
}
