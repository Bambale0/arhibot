export type User = {
  id: string
  email: string | null
  display_name: string
  role: 'user' | 'admin' | 'superadmin'
  credits: number
  created_at: string
  updated_at: string
}

export type TokenPair = {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

export type ProjectContext = {
  house_area_m2?: number | null
  floors?: number | null
  plot_area_m2?: number | null
  bedrooms?: number | null
  bathrooms?: number | null
  architecture_style?: string | null
  garage_cars?: number | null
  pool?: boolean | null
  attic?: boolean | null
  glazed_veranda?: boolean | null
  architecture?: ArchitecturePackage | null
  design_session?: import('./questionnaireTypes').DesignSession | null
  questionnaire_draft?: boolean | null
}

export type Project = {
  id: string
  name: string
  description: string | null
  status: 'active' | 'archived'
  context: ProjectContext
  created_at: string
  updated_at: string
}

export type ProjectList = {
  items: Project[]
  next_cursor?: string | null
  has_more?: boolean
}

export type Asset = {
  id: string
  project_id: string | null
  type: 'image'
  purpose: 'generation_input' | 'project_reference' | 'generation_output'
  original_filename: string | null
  mime_type: string
  size_bytes: number
  width: number
  height: number
  url: string
  created_at: string
}

export type GenerationMode = 'floor_plan' | 'facade' | 'master_plan' | 'interior'
export type NormalizedRect = { x:number; y:number; width:number; height:number }

export type Generation = {
  id: string
  project_id: string
  user_id: string
  input_asset_id: string | null
  type: GenerationMode
  prompt: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  composition_mode: 'replace' | 'masked_edit'
  edit_region: NormalizedRect | null
  protected_regions: NormalizedRect[]
  provider: string | null
  external_task_id: string | null
  output_asset_id: string | null
  output_asset: Asset | null
  error: string | null
  created_at: string
  updated_at: string
}

export type GenerationList = {
  items: Generation[]
  next_cursor?: string | null
  has_more?: boolean
}

export type IdeaMediaKind = 'photo' | 'floor_plan' | 'section' | 'facade'
export type IdeaMedia = { asset: Asset; kind: IdeaMediaKind; label: string }
export type Idea = { id:string; title:string; category:string; text:string; generation_type:GenerationMode; prompt:string; image_asset:Asset|null; media:IdeaMedia[]; model_url:string|null }

export type BillingSummary = {
  credits: number
  tariffs: Array<{ code:string; name:string; description:string|null; credits:number; amount:string; currency:string }>
  payments: Array<{ id:string; package_code:string; status:string; amount:string; currency:string; credits:number; confirmation_url:string|null; created_at:string; paid_at:string|null }>
}
export type BillingPayment = BillingSummary['payments'][number]

export type ArchitecturePoint = { x:number; y:number }
export type ArchitectureOpening = { id:string; kind:'door'|'window'|'opening'; wall_id:string; offset_mm:number; width_mm:number; height_mm:number; sill_mm?:number|null }
export type ArchitectureWall = { id:string; level_id:string; start:ArchitecturePoint; end:ArchitecturePoint; thickness_mm:number; height_mm:number; exterior:boolean }
export type ArchitectureRoom = { id:string; level_id:string; name:string; polygon:ArchitecturePoint[]; target_area_m2?:number|null }
export type ArchitectureLevel = { id:string; name:string; elevation_mm:number; height_mm:number; boundary:ArchitecturePoint[]; slab_thickness_mm:number }
export type ArchitectureRoof = { kind:'flat'|'gable'|'hip'; base_level_id:string; ridge_height_mm:number; overhang_mm:number; ridge_axis?:'x'|'y'|null }
export type ArchitectureProgram = { house_area_m2:number; floors:number; bedrooms:number; bathrooms:number; architecture_style:string|null }
export type ArchitectureGeometry = { levels:ArchitectureLevel[]; walls:ArchitectureWall[]; openings:ArchitectureOpening[]; rooms:ArchitectureRoom[]; roof:ArchitectureRoof|null }
export type ArchitecturePackage = { version:string; units:'mm'; program:ArchitectureProgram; geometry:ArchitectureGeometry; metadata:Record<string,unknown> }

export type AdminOverview = { users:number; active_projects:number; generations:number; completed_generations:number; payments:number; paid_revenue:string; currency:string }
export type AdminTariff = { id:string; code:string; name:string; description:string|null; credits:number; amount:string; currency:string; is_active:boolean; sort_order:number; created_at:string; updated_at:string }
export type AdminBillingSettings = { receipt_enabled:boolean; vat_code:number|null; payment_mode:string|null; payment_subject:string|null; updated_at:string }
export type AdminIdea = { id:string; title:string; category:string; text:string; generation_type:GenerationMode; prompt:string; image_asset_id:string|null; architecture_project_id:string|null; media:Array<{asset_id:string;kind:IdeaMediaKind;label:string}>; model_url:string|null; is_active:boolean; sort_order:number; created_at:string; updated_at:string }
export type AdminGenerationSettings = { primary_model:string; fallback_model:string|null; primary_params:Record<string,unknown>; fallback_params:Record<string,unknown>; mode_params:Record<string,Record<string,unknown>>; updated_at:string }
export type AdminGenerationPrice = { mode:GenerationMode; credits:number; is_active:boolean; updated_at:string }
export type AdminPrompt = { mode:GenerationMode; template:string; updated_at:string }
export type AdminUser = { id:string; email:string|null; display_name:string; role:'user'|'admin'|'superadmin'; credits:number; created_at:string }
export type AdminBroadcast = { id:string; title:string; message:string; audience:string; status:string; total_recipients:number; sent_count:number; failed_count:number; created_at:string; started_at:string|null; completed_at:string|null }
export type AdminAudit = { id:string; actor_user_id:string; action:string; entity_type:string; entity_id:string|null; details:Record<string,unknown>; created_at:string }
export type AdminOperationalSettings = { generation_rate_limit_per_minute:number; payment_rate_limit_per_minute:number; media_retention_days:number|null; backup_interval_hours:number; backup_retention_days:number; updated_at:string }
export type AdminTelegramContent = { bot_name:string; short_description:string; description:string; start_message:string; mini_app_button_text:string; commands:Array<{command:string;description:string}>; updated_at:string }
