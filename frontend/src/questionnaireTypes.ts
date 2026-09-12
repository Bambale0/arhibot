export type NormalizedRect = { x:number; y:number; width:number; height:number }
export type QuestionnaireAnswer = string | number | boolean | string[]
export type QuestionnaireCondition = {
  question_id?: string
  operator: 'eq'|'neq'|'in'|'contains'|'starts_with'|'all'|'any'|'house_accepted'|'not_contains_any'|'floor_option'
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
  placeholder:string|null
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
  plot_area_sotkas:number|null
  initial_concept_mode:boolean
  survey_completed_objects:string[]
  initial_generation_id:string|null
  initial_concept_accepted:boolean
  current_object:string|null
  current_question_id:string|null
  source_step_completed:boolean
  source_asset_id:string|null
  scene_asset_id:string|null
  scene_generation_id:string|null
  answers:Record<string,Record<string,QuestionnaireAnswer>>
  accepted_objects:string[]
  removed_objects:string[]
  pending_removal_object:string|null
  generation_ids:Record<string,string>
  edit_question_ids:string[]
  review_comments:Record<string,string>
  edit_regions:Record<string,NormalizedRect>
  lock_regions:Record<string,NormalizedRect>
  region_mode:'edit'|'lock'|null
  region_object:string|null
  application_submitted:boolean
}

export function createDesignSession(catalogVersion:string, selectedObjects:string[]):DesignSession {
  return {
    session_id:crypto.randomUUID(),
    catalog_version:catalogVersion,
    selected_objects:[...selectedObjects],
    plot_area_sotkas:null,
    initial_concept_mode:true,
    survey_completed_objects:[],
    initial_generation_id:null,
    initial_concept_accepted:false,
    current_object:selectedObjects.length === 1 ? selectedObjects[0] : null,
    current_question_id:null,
    source_step_completed:false,
    source_asset_id:null,
    scene_asset_id:null,
    scene_generation_id:null,
    answers:{},
    accepted_objects:[],
    removed_objects:[],
    pending_removal_object:null,
    generation_ids:{},
    edit_question_ids:[],
    review_comments:{},
    edit_regions:{},
    lock_regions:{},
    region_mode:null,
    region_object:null,
    application_submitted:false,
  }
}

export type QuestionnaireProjectContext = { design_session?:DesignSession|null }
export type QuestionnaireBriefAnswer = {
  question_id:string
  question:string
  answer:QuestionnaireAnswer
}
export type QuestionnaireBriefObject = {
  key:string
  title:string
  accepted:boolean
  answers:QuestionnaireBriefAnswer[]
}

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
  project_name:string|null
  user_name:string|null
  scene_asset_url:string|null
  final_generation_id:string|null
  application_contact:string|null
  user_email:string|null
  telegram_user_id:string|null
  brief:QuestionnaireBriefObject[]
}
export type QuestionnaireApplicationSubmitResponse = { session:DesignSession; application:QuestionnaireApplication }

export type QuestionnaireGenerationCost = {
  generation_type:'master_plan'
  credits:number|null
  is_available:boolean
}
