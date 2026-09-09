export type QuestionnaireAnswer = string | number | boolean | string[]
export type QuestionnaireCondition = {
  question_id?: string
  operator: 'eq'|'neq'|'in'|'contains'|'starts_with'|'all'|'any'|'house_accepted'|'not_contains_any'
  value?: string|string[]
  conditions?: QuestionnaireCondition[]
}
export type QuestionnaireQuestion = {
  id:string
  text:string
  kind:'single'|'multi'|'number'|'text'|'consent'
  options:string[]
  required:boolean
  skip_default:string|string[]|null
  skip_condition:QuestionnaireCondition|null
  help:string|null
  field_hint:string|null
  max_selections:number|null
  min_value?:number|null
  max_value?:number|null
  phase:'pre_render'|'review'|'application'
  condition:QuestionnaireCondition|null
  option_rules:Record<string,QuestionnaireCondition>
  edit_targets:Record<string,string[]>
}
export type QuestionnaireDefinition = { key:string; title:string; source_file:string; order:number; questions:QuestionnaireQuestion[]; scene_policy:Record<string,string>|null }
export type QuestionnaireSection = { key:string; title:string; object_keys:string[] }
export type QuestionnaireCatalog = { version:string; sections:QuestionnaireSection[]; questionnaires:QuestionnaireDefinition[]; application_key:'zayavka'; source_rules:string[] }
export type DesignSession = {
  session_id:string
  catalog_version:string
  selected_objects:string[]
  current_object:string|null
  current_question_id:string|null
  source_step_completed:boolean
  source_asset_id:string|null
  scene_asset_id:string|null
  answers:Record<string,Record<string,QuestionnaireAnswer>>
  accepted_objects:string[]
  generation_ids:Record<string,string>
  edit_question_ids:string[]
  review_comments:Record<string,string>
  application_submitted:boolean
}
export type QuestionnaireProjectContext = { design_session?:DesignSession|null }
export type QuestionnaireApplication = {
  id:string
  session_id:string
  project_id:string
  user_id:string
  catalog_version:string
  selected_objects:string[]
  accepted_objects:string[]
  answers:Record<string,Record<string,QuestionnaireAnswer>>
  scene_asset_id:string|null
  status:string
  telegram_delivery_status:string
  telegram_notified_at:string|null
  created_at:string
}
export type QuestionnaireApplicationSubmitResponse = { session:DesignSession; application:QuestionnaireApplication }
