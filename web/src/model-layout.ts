import type { ModelLens } from './schema'
import type { Lens, PipelineRoute, SummaryLink } from './pipeline-layout'

export const modelFamilyNumbers: Record<string,string> = Object.fromEntries([
  'mission-models','geometry','surface','human-mobility','rover-mobility','environment','resources',
  'science-models','routing','decision','replan','uncertainty','validate','explanation',
].map((id,i)=>[id,String(i+1).padStart(2,'0')]))

export const modelViews: Record<ModelLens,Lens> = {
  complete:{label:'Complete scientific system',description:'From verified Mars terrain and platform assumptions to feasible, explainable mission choices.',
    rows:[['mission-models','geometry','surface','environment','validate'],['replan','human-mobility','rover-mobility','routing','uncertainty'],[null,'science-models','resources','decision','explanation']],open:[]},
  terrain:{label:'Terrain & traversability',description:'Read canonical pack geometry and determine supported edges and exclusions.',rows:[['pack','geometry','surface','routing']],open:['surface']},
  human:{label:'Human Marswalk',description:'Scope crew operating limits and calculate directional time with a required return reserve.',rows:[['mission-models','human-mobility','routing','resources'],[null,null,'surface','decision']],open:['human-mobility','resources']},
  rover:{label:'Rover mobility',description:'Apply vehicle-specific limits and trace estimated demand through routing and reserves.',rows:[['mission-models','rover-mobility','routing','resources'],['surface',null,'environment','decision']],open:['rover-mobility']},
  environment:{label:'Environment & resources',description:'Distinguish historical context, authorized scenarios and enabled budget inputs.',rows:[['mission-models','environment','resources','decision'],['geometry',null,'rover-mobility']],open:['environment','resources']},
  science:{label:'Science value',description:'Connect regional screening, mission objectives, candidate approaches and evidence-backed tasks.',rows:[['mission-models','science-models','routing','decision'],[null,null,null,'explanation']],open:['science-models']},
  pathfinding:{label:'Pathfinding',description:'Directed adjacency, outbound and return paths, and distinct bounded route candidates.',rows:[['geometry','surface','routing','decision'],['human-mobility','rover-mobility',null,'replan']],open:['routing']},
  optimization:{label:'Mission optimization',description:'Feasible candidates enter Pareto comparison. Mission priorities select among the resulting alternatives.',rows:[['routing','decision','explanation'],['science-models',null,'resources'],['uncertainty']],open:['decision']},
  replanning:{label:'Dynamic replanning',description:'Apply a versioned state change, recompute affected plans and explain what changed.',rows:[['ui','replan','routing','decision'],['mission-models',null,'resources','explanation']],open:['replan']},
  validation:{label:'Validation & uncertainty',description:'Fixtures, historical cases, sensitivity and explicit abstention when required evidence is missing.',rows:[['validate','uncertainty','decision','explanation'],['surface',null,'resources']],open:['validate','uncertainty']},
}
const summary = (entries:[string,string,PipelineRoute?][]):Record<string,SummaryLink> =>
  Object.fromEntries(entries.map(([pair,label,route])=>[pair,{label,route}]))

export const modelGuides: Record<ModelLens,Record<string,SummaryLink>> = {
  complete:summary([
    ['replan>mission-models','new revision'],['mission-models>human-mobility','crew profile'],
    ['mission-models>rover-mobility','vehicle profile','above'],
    ['geometry>surface','terrain support'],['geometry>human-mobility','directed grade'],
    ['surface>rover-mobility','admissible edges'],['human-mobility>routing','time costs','above'],
    ['rover-mobility>routing','rover costs'],['rover-mobility>resources','energy demand'],
    ['environment>uncertainty','data domain'],['validate>uncertainty','test findings'],
    ['routing>decision','route candidates'],['science-models>decision','science intent','above'],
    ['resources>decision','resource margins'],['uncertainty>explanation','limitations'],
    ['decision>explanation','trade-offs'],
  ]),
  terrain:summary([['pack>surface','pack support'],['geometry>surface','slope + support'],['surface>routing','valid edges']]),
  human:summary([['mission-models>human-mobility','crew profile'],['surface>human-mobility','allowed terrain'],['human-mobility>routing','directional time'],['routing>resources','direct return'],['resources>decision','return margin']]),
  rover:summary([['mission-models>rover-mobility','vehicle profile'],['surface>rover-mobility','valid terrain'],['rover-mobility>routing','time + energy'],['rover-mobility>resources','drive demand','above'],['environment>resources','supply scenario'],['resources>decision','reserve checks']]),
  environment:summary([['mission-models>environment','scenario scope'],['geometry>environment','Mars frame'],['environment>resources','authorized inputs'],['rover-mobility>resources','energy demand'],['resources>decision','separate budgets']]),
  science:summary([['mission-models>science-models','mission objective'],['science-models>routing','eligible targets'],['routing>decision','route options'],['science-models>decision','science intent','above'],['decision>explanation','retained science']]),
  pathfinding:summary([['geometry>surface','terrain support'],['surface>routing','validity masks'],['human-mobility>routing','time costs'],['rover-mobility>routing','vehicle costs'],['replan>routing','current closure'],['routing>decision','bounded routes']]),
  optimization:summary([['routing>decision','candidate legs'],['science-models>decision','science intent'],['decision>resources','plan ledgers'],['resources>decision','constraint margins'],['uncertainty>decision','required evidence'],['decision>explanation','feasible alternatives']]),
  replanning:summary([['ui>replan','field update'],['replan>mission-models','fresh snapshot'],['replan>routing','recompute routes'],['routing>decision','revised paths'],['resources>decision','updated margins'],['decision>explanation','new decision'],['replan>explanation','what changed']]),
  validation:summary([['surface>uncertainty','support limits'],['validate>uncertainty','test findings'],['uncertainty>decision','evidence policy'],['resources>decision','ledger checks'],['decision>explanation','feasible set'],['uncertainty>explanation','abstention reasons']]),
}

export const modelChildOrder: Record<string,string[]> = {
  geometry:['planetary-normalize','projection','planet-distance','terrain-crop','elevation','gradient','grade'],
  surface:['resolved-scale','coverage','roughness','surface-evidence','screen','barrier-mask','routing-inputs'],
  routing:['mobility-interface','graph','solve','legs','candidate-routes'],
  decision:['mission-candidates','feasibility','hard-filter','pareto-front','rank','multi-stop','excluded'],
  replan:['mission-update','freshness','recompute-scope','closure','contingency'],
  uncertainty:['evidence-limits','abstain','sensitivity','scenario-sensitivity'],
  explanation:['decision-record','explain','serialize','cards'],
}
