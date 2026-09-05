export type UserRole = 'user' | 'admin' | 'superadmin'

export type User = {
  id: string
  display_name: string
  avatar_url?: string | null
  status: 'active' | 'disabled'
  role: UserRole
  credits_balance: number
  created_at: string
  updated_at: string
  capabilities?: { can_generate?: boolean }
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
export type GenerationStatus = 'queued' | 'processing' | 'completed' | 'failed'

export type Generation = {
  id: string
  project_id: string
  input_asset_id: string | null
  output_asset: Asset | null
  type: GenerationMode
  status: GenerationStatus
  prompt: string
  credits_charged: number
  model_name: string | null
  fallback_used: boolean
  error: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
}

export type GenerationList = {
  items: Generation[]
  next_cursor: string | null
  has_more: boolean
}

export type BillingPackage = {
  code: string
  label: string
  credits: number
  amount: string
  currency: string
}

export type BillingPayment = {
  id: string
  package_code: string
  credits: number
  amount: string
  currency: string
  status: string
  confirmation_url: string | null
  receipt_email: string | null
  refund_status: string | null
  created_at: string
  paid_at: string | null
  refunded_at: string | null
}

export type BillingSummary = {
  enabled: boolean
  receipt_required: boolean
  credits_balance: number
  packages: BillingPackage[]
  payments: BillingPayment[]
}

export type Idea = {
  id: string
  title: string
  category: string
  text: string
  generation_type: GenerationMode
  prompt: string
  image_url: string | null
}

export type AdminOverview = {
  yookassa_configured: boolean
  nexus_configured: boolean
  telegram_configured: boolean
}

export type AdminTariff = {
  id: string
  code: string
  name: string
  description: string | null
  credits: number
  amount: string
  currency: string
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type AdminBillingSettings = {
  receipts_enabled: boolean
  vat_code: number | null
  payment_subject: string | null
  payment_mode: string | null
  updated_at: string | null
}

export type AdminIdea = Idea & {
  image_asset_id: string | null
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type AdminGenerationSettings = {
  primary_model: string | null
  fallback_model: string | null
  primary_params: Record<string, unknown>
  fallback_params: Record<string, unknown>
  mode_params: Record<string, Record<string, unknown>>
  updated_at: string | null
}

export type AdminGenerationPrice = {
  generation_type: GenerationMode
  credits: number
  is_active: boolean
  updated_at: string
}

export type AdminPrompt = {
  generation_type: GenerationMode
  template: string
  updated_at: string
}

export type AdminUser = {
  id: string
  display_name: string
  status: 'active' | 'disabled'
  role: UserRole
  credits_balance: number
  created_at: string
  updated_at: string
}

export type AdminCreditTransaction = {
  id: string
  user_id: string
  amount: number
  balance_after: number
  kind: string
  reference_type: string | null
  reference_id: string | null
  reason: string | null
  actor_user_id: string | null
  created_at: string
}

export type AdminPayment = {
  id: string
  user_id: string
  package_code: string
  credits: number
  amount: string
  currency: string
  status: string
  yookassa_payment_id: string | null
  receipt_email: string | null
  refund_id: string | null
  refund_status: string | null
  provider_error: string | null
  created_at: string
  updated_at: string
  paid_at: string | null
  refunded_at: string | null
}

export type BroadcastSegment = 'all' | 'with_credits' | 'without_credits'

export type AdminBroadcast = {
  id: string
  text: string
  status: string
  segment: BroadcastSegment
  recipient_count: number
  sent_count: number
  failed_count: number
  scheduled_at: string | null
  canceled_at: string | null
  created_at: string
  updated_at: string
  sent_at: string | null
}

export type AdminOperationalSettings = {
  auth_rate_limit_per_minute: number | null
  generation_rate_limit_per_minute: number | null
  payment_rate_limit_per_minute: number | null
  media_retention_days: number | null
  backup_interval_hours: number | null
  backup_retention_days: number | null
  updated_at: string | null
}

export type AdminAudit = {
  id: string
  actor_user_id: string | null
  action: string
  entity_type: string
  entity_id: string | null
  details: Record<string, unknown>
  created_at: string
}
