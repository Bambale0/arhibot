export type User = {
  id: string
  display_name: string
  avatar_url?: string | null
  status: 'active' | 'disabled'
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

export type GenerationMode = 'facade' | 'interior' | 'redesign'

export type DemoGeneration = {
  id: string
  mode: GenerationMode
  prompt: string
  sourceUrl: string
  createdAt: string
}
