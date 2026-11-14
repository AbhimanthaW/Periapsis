export const methods = ['Sample rock', 'Investigate ice', 'Remote survey'] as const
export const exclusions = ['Polar', 'Volcanic'] as const
export const profiles = ['Rover', 'Astronaut'] as const
export const sorts = ['Match', 'Science', 'Records', 'Traversal'] as const

export type Method = (typeof methods)[number]
export type Exclusion = (typeof exclusions)[number]
export type Profile = (typeof profiles)[number]
export type Sort = (typeof sorts)[number]

export interface Region {
  id: string
  name: string
  type: string
  coords: string
  position: [number, number]
  phrase: string
  targets: string[]
  science: number
  records: number | string
  traversal: Record<Profile, number | string>
  scienceSummary: string
  traversalSummary: string
  preferred: Method
  exclusion?: Exclusion
}

const varied = 'Low to very high · no level'
const traversal = (rover: string | number = varied, astronaut: string | number = rover) => ({
  Rover: rover,
  Astronaut: astronaut,
})

export const regions: Region[] = [
  {
    id: '43', name: 'Jezero Crater', type: 'Crater', coords: '18.41°N 77.69°E',
    position: [488.4, 353.1], phrase: 'ancient river delta',
    targets: ['fluvial', 'delta', 'sedimentary', 'biosignature', 'clay', 'water'],
    science: 5, records: 'Exceptionally high on studied corridors',
    traversal: traversal(varied, 'Moderate to very high · no level'),
    scienceSummary: 'Very high · ancient habitability, sedimentology',
    traversalSummary: 'Low–moderate on floor · high at major obstacles', preferred: 'Sample rock',
  },
  {
    id: '46', name: 'Nili Fossae', type: 'Fossa', coords: '22.02°N 76.69°E',
    position: [477.8, 329.2], phrase: 'water-rock alteration',
    targets: ['aqueous', 'alteration', 'clay', 'carbonates', 'water'],
    science: 5, records: 5, traversal: traversal(varied, 'High · no level'),
    scienceSummary: 'Very high · aqueous alteration, mineralogy',
    traversalSummary: 'Variable · trough walls and fractured terrain', preferred: 'Sample rock',
  },
  {
    id: '14', name: 'Isidis Planitia', type: 'Planitia', coords: '13.94°N 88.38°E',
    position: [553.8, 377.3], phrase: 'ancient water processes',
    targets: ['aqueous', 'water', 'basin', 'sedimentary'],
    science: 5, records: 4, traversal: traversal(),
    scienceSummary: 'Very high · basin history and ancient water',
    traversalSummary: 'Variable · basin plains and rough margins', preferred: 'Remote survey',
  },
  {
    id: '55', name: 'Nilosyrtis Mensae', type: 'Mensa', coords: '34.77°N 68.47°E',
    position: [422.8, 248.8], phrase: 'ancient glaciation',
    targets: ['ice', 'glaciation', 'glacial', 'climate'],
    science: 5, records: 5, traversal: traversal('Low to extreme · no level', 'High to extreme · no level'),
    scienceSummary: 'Very high · glacial history and ice-related landforms',
    traversalSummary: 'Low to extreme · gentle floors and steep scarps', preferred: 'Investigate ice',
  },
  {
    id: '01', name: 'Planum Boreum', type: 'Planum', coords: '87.32°N 54.96°E',
    position: [384.5, 15.3], phrase: 'north polar ice deposits',
    targets: ['ice', 'polar', 'climate', 'volatiles'],
    science: 4, records: 4, traversal: traversal(4, 5),
    scienceSummary: 'High · polar ice and climate history',
    traversalSummary: 'High difficulty · frost, dunes and seasonal constraints', preferred: 'Investigate ice',
    exclusion: 'Polar',
  },
]

const context = (
  id: string, name: string, type: string, coords: string, position: Region['position'],
  phrase: string, exclusion?: Exclusion,
): Region => ({
  id, name, type, coords, position, phrase, exclusion,
  targets: [], science: 0, records: 'No level', traversal: traversal('No level'),
  scienceSummary: 'Survey level unavailable in this sample',
  traversalSummary: 'Local terrain model unavailable', preferred: 'Remote survey',
})

export const contextRegions = [
  context('08', 'Utopia Planitia', 'Planitia', '46.74°N 117.52°E', [605.4, 149], 'northern lowland basin'),
  context('11', 'Arabia Terra', 'Terra', '21.25°N 5.72°E', [86.7, 298.2], 'layered highland deposits'),
  context('13', 'Syrtis Major Planum', 'Planum', '9.20°N 67.10°E', [420.5, 417.9], 'volcanic plains', 'Volcanic'),
  context('17', 'Terra Sabaea', 'Terra', '2.72°N 51.30°E', [315, 460], 'ancient cratered highlands'),
  context('09', 'Acidalia Planitia', 'Planitia', '49.76°N 20.74°W', [139.4, 107.2], 'northern lowland plains'),
  context('56', 'Deuteronilus Mensae', 'Mensa', '45.11°N 23.92°E', [218.4, 172.1], 'glacial deposits'),
]

export const allRegions = [...regions, ...contextRegions]
export const defaultObjective = 'ancient water and delta deposits'
export const initialTerms = ['Fluvial and deltaic deposits', 'Aqueous alteration']

const stopWords = new Set(['and', 'the', 'for', 'with', 'from', 'find', 'look', 'near', 'ancient', 'deposits'])
const words = (text: string) => (text.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(word => !stopWords.has(word))

export function interpretObjective(objective: string): string[] {
  const tokens = words(objective)
  const terms = [
    tokens.some(word => /^(delta|fluvial|river|sediment)/.test(word)) && initialTerms[0],
    tokens.some(word => /^(water|aqueous|clay|alterat)/.test(word)) && initialTerms[1],
    tokens.some(word => /^(ice|glaci|polar|climat)/.test(word)) && 'Water ice and glaciation',
    tokens.some(word => /^(volcan|lava|basalt)/.test(word)) && 'Volcanic deposits',
  ].filter((term): term is string => typeof term === 'string')
  return terms.length ? terms : [...new Set(tokens)].slice(0, 4)
}

export const isExcluded = (region: Region, excludes: Exclusion[]) =>
  region.exclusion !== undefined && excludes.includes(region.exclusion)

export function matchStrength(region: Region, terms: string[]) {
  const targets = [...region.targets, ...words(region.phrase)]
  return words(terms.join(' ')).reduce((total, word) =>
    total + Number(targets.some(target => word.startsWith(target) || target.startsWith(word))), 0)
}

export function rankRegions(terms: string[], method: Method, excludes: Exclusion[], sort: Sort, profile: Profile) {
  const value = (region: Region) => {
    switch (sort) {
      case 'Science': return region.science
      case 'Records': return typeof region.records === 'number' ? region.records : 0
      case 'Traversal': {
        const difficulty = region.traversal[profile]
        return typeof difficulty === 'number' ? 10 - difficulty : 0
      }
      case 'Match': return matchStrength(region, terms) * 2 + Number(region.preferred === method)
    }
  }
  const extraMatches = contextRegions.filter(region => matchStrength(region, terms) > 0 || isExcluded(region, excludes))
  return [...regions, ...extraMatches].sort((left, right) =>
    Number(isExcluded(left, excludes)) - Number(isExcluded(right, excludes)) || value(right) - value(left))
}
