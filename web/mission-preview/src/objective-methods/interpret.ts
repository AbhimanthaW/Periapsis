import { goals, methodCatalog, modifiers, operationAliases } from './catalog.ts'
import type { GoalId, Method } from './catalog.ts'

type AliasTarget = { kind: 'method' | 'operation'; id: string }

export interface Intent {
  objective: string
  goalIds: readonly GoalId[]
  modifierIds: readonly string[]
  source: 'lexicon' | 'confirmed'
  requestedMethodIds: readonly string[]
  excludedMethodIds: readonly string[]
  excludedOperationIds: readonly string[]
  constraintIssues: readonly string[]
  goalIssue?: string
}

const cue = /\b(without|exclude|excluding|avoid|no|do not use|with|include|using|use)\b/gi
const negativeCues = new Set(['without', 'exclude', 'excluding', 'avoid', 'no', 'do not use'])
const normalize = (value: string) => value.normalize('NFKC').toLowerCase()
  .replace(/[‐‑–—-]/g, ' ').replace(/\s+/g, ' ').trim()
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const phrase = (value: string) => new RegExp('\\b' + escape(value) + '\\b', 'g')
const ignoredGoalWords = /\b(?:map|assess|review|survey|investigate|study|determine|compare|record|examine|analyze|the|a|an|of|and|or|at|around|in|on|for|over|mars|arcadia planitia|arcadia)\b/g

function aliasesFor(catalog: readonly Method[]) {
  const entries = new Map<string, AliasTarget[]>()
  function add(kind: AliasTarget['kind'], id: string, aliases: readonly string[]) {
    for (const alias of aliases) {
      const key = normalize(alias)
      entries.set(key, [...(entries.get(key) ?? []), { kind, id }])
    }
  }
  for (const method of catalog) add('method', method.id, method.aliases)
  for (const [id, aliases] of Object.entries(operationAliases)) add('operation', id, aliases)
  return entries
}

export function interpretObjective(objective: string, catalog: readonly Method[] = methodCatalog): Intent {
  const aliases = aliasesFor(catalog)
  const requestedMethodIds = new Set<string>()
  const excludedMethodIds = new Set<string>()
  const excludedOperationIds = new Set<string>()
  const constraintIssues: string[] = []
  const normalized = normalize(objective)
  const goalClauses: string[] = []

  for (const clause of normalized.split(/[;.!?]/)) {
    const cues = [...clause.matchAll(cue)]
    goalClauses.push(clause.slice(0, cues[0]?.index ?? clause.length))
    for (const [index, match] of cues.entries()) {
      const exclusion = negativeCues.has(match[0])
      const start = match.index + match[0].length
      const end = cues[index + 1]?.index ?? clause.length
      const instruction = clause.slice(start, end).trim().replace(/(?:[,\s]+|\b(?:and|or)\s*)+$/, '')
      const parts = instruction.split(/\s*,\s*|\b(?:and|or)\b/).filter(part => part.trim())
      if (parts.length === 0) constraintIssues.push('Name the method to ' + (exclusion ? 'exclude.' : 'request.'))
      for (const part of parts) {
        const alias = part.trim().replace(/^(?:a|an|the)\s+/, '')
        const targets = aliases.get(alias) ?? []
        const target = targets.length === 1 ? targets[0] : undefined
        if (target?.kind === 'method') {
          (exclusion ? excludedMethodIds : requestedMethodIds).add(target.id)
        } else if (target?.kind === 'operation' && exclusion) {
          excludedOperationIds.add(target.id)
        } else {
          constraintIssues.push('Clarify which method to ' + (exclusion ? 'exclude' : 'request') + ' for “' + alias + '”.')
        }
      }
    }
  }

  for (const method of catalog) {
    if (!requestedMethodIds.has(method.id)) continue
    if (excludedMethodIds.has(method.id) || method.operations.some(id => excludedOperationIds.has(id))) {
      constraintIssues.push('“' + method.label + '” is both requested and excluded.')
    }
  }

  let text = goalClauses.join(' ')
  const modifierIds: string[] = []
  for (const modifier of modifiers) {
    if (modifier.aliases.some(alias => phrase(alias).test(text))) {
      modifierIds.push(modifier.id)
      for (const alias of modifier.aliases) text = text.replace(phrase(alias), ' ')
    }
  }

  const goalIds: GoalId[] = []
  for (const goal of goals) {
    let matched = false
    for (const alias of goal.aliases) {
      text = text.replace(phrase(alias), () => {
        matched = true
        return ' '
      })
    }
    if (matched) goalIds.push(goal.id)
  }
  const unknown = text.replace(ignoredGoalWords, ' ').replace(/[^\p{L}\p{N}]+/gu, ' ').trim()
  const goalIssue = goalIds.length === 0
    ? 'Choose broad elevation context, local elevation at 20 m posting, or both.'
    : unknown ? 'Confirm the interpreted goals or revise the objective.' : undefined

  return {
    objective, goalIds, modifierIds, goalIssue, source: 'lexicon', constraintIssues,
    requestedMethodIds: [...requestedMethodIds],
    excludedMethodIds: [...excludedMethodIds],
    excludedOperationIds: [...excludedOperationIds],
  }
}

export function confirmGoals(intent: Intent, selected: readonly GoalId[]): Intent {
  const goalIds = goals.map(goal => goal.id).filter(id => selected.includes(id))
  return {
    ...intent,
    goalIds,
    source: 'confirmed',
    goalIssue: goalIds.length ? undefined : 'Select at least one elevation goal.',
  }
}
