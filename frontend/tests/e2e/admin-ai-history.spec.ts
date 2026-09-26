import { expect, test, type Route } from '@playwright/test'

const now = '2026-09-14T10:30:00Z'
const admin = {
  id:'11111111-1111-4111-8111-111111111111',
  display_name:'Admin E2E',
  status:'active',
  role:'superadmin',
  credits_balance:10,
  created_at:now,
  updated_at:now,
  capabilities:{can_generate:true},
}
const projectId='22222222-2222-4222-8222-222222222222'

function asset(id:string) {
  return {
    id,
    project_id:projectId,
    type:'image',
    purpose:'generation_output',
    original_filename:'result.png',
    mime_type:'image/png',
    size_bytes:1234,
    width:1376,
    height:768,
    url:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"></svg>',
    created_at:now,
  }
}

function generation(id:string, model:string, assetId:string, started:string, completed:string) {
  return {
    id,
    project_id:projectId,
    input_asset_id:null,
    output_asset:asset(assetId),
    type:'master_plan',
    status:'completed',
    credits_charged:0,
    model_name:model,
    fallback_used:false,
    composition_mode:'replace',
    edit_region:null,
    protected_regions:[],
    error:null,
    created_at:started,
    updated_at:completed,
    started_at:started,
    completed_at:completed,
  }
}

const newestStill = generation(
  '33333333-3333-4333-8333-333333333331',
  'nano-banana-pro',
  '44444444-4444-4444-8444-444444444441',
  '2026-09-14T10:00:00Z',
  '2026-09-14T10:01:10Z',
)
const olderStill = generation(
  '33333333-3333-4333-8333-333333333332',
  'gpt-image-2',
  '44444444-4444-4444-8444-444444444442',
  '2026-09-14T09:00:00Z',
  '2026-09-14T09:01:00Z',
)
const orbit = generation(
  '33333333-3333-4333-8333-333333333333',
  'nano-banana-pro',
  '44444444-4444-4444-8444-444444444443',
  '2026-09-14T10:02:00Z',
  '2026-09-14T10:04:00Z',
)

const history = [
  {kind:'orbit',generation:orbit,prompt:'Warm orbit',params:{guidance:4},frame_count:6,frame_duration_ms:160},
  {kind:'sandbox',generation:newestStill,prompt:'Newest still prompt',params:{aspect_ratio:'16:9'},frame_count:null,frame_duration_ms:null},
  {kind:'sandbox',generation:olderStill,prompt:'Older still prompt',params:{aspect_ratio:'16:9',quality:'high'},frame_count:null,frame_duration_ms:null},
]

async function json(route:Route, data:unknown, status=200) {
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
}

// Regression: persisted history must survive a full Mini App reload.
test('admin AI history survives reload and an older still can launch a GIF flyover', async ({ page }) => {
  let submittedFlyover:Record<string,unknown>|null=null
  await page.addInitScript(() => {
    sessionStorage.setItem('auroom.access_token','e2e')
      })

  await page.route('**/api/v1/**', async route => {
    const req=route.request()
    const path=new URL(req.url()).pathname
    const method=req.method()

    if(path.endsWith('/me')&&method==='GET') return json(route,admin)
    if(path.endsWith('/admin/overview')) return json(route,{yookassa_configured:true,nexus_configured:true,telegram_configured:true})
    if(path.endsWith('/admin/tariffs')) return json(route,[])
    if(path.endsWith('/admin/billing-settings')) return json(route,{receipts_enabled:false,vat_code:null,payment_subject:null,payment_mode:null,updated_at:null})
    if(path.endsWith('/admin/ideas')) return json(route,[])
    if(path.endsWith('/admin/questionnaire-applications')) return json(route,[])
    if(path.endsWith('/admin/questionnaires')) return json(route,{
      catalog:{version:'e2e-v1',sections:[],questionnaires:[],application_key:'zayavka',source_rules:[]},
      source_texts:{},
      updated_at:now,
    })
    if(path.endsWith('/admin/generation/sandbox/history')) return json(route,history)
    if(path.endsWith('/admin/generation/flyover-gif')&&method==='POST') {
      submittedFlyover=req.postDataJSON() as Record<string,unknown>
      return json(route,{...olderStill,id:'55555555-5555-4555-8555-555555555555',status:'queued',output_asset:null,started_at:null,completed_at:null})
    }
    if(path.endsWith('/admin/generation')) return json(route,{
      primary_model:'nano-banana-pro',
      fallback_model:'gpt-image-2',
      primary_timeout_seconds:90,
      primary_params:{image_size:'2K'},
      fallback_params:{},
      mode_params:{facade:{aspect_ratio:'16:9'},master_plan:{aspect_ratio:'1:1'}},
      updated_at:now,
    })
    if(path.endsWith('/admin/generation-prices')) return json(route,[])
    if(path.endsWith('/admin/prompts')) return json(route,[])
    if(path.endsWith('/admin/users')) return json(route,[])
    if(path.endsWith('/admin/credit-transactions')) return json(route,[])
    if(path.endsWith('/admin/payments')) return json(route,[])
    if(path.endsWith('/admin/broadcasts')) return json(route,[])
    if(path.endsWith('/admin/telegram-content')) return json(route,{
      configured:false,bot_name:null,short_description:null,description:null,start_text:null,
      open_button_text:null,start_command_description:null,app_command_description:null,updated_at:null,
    })
    if(path.endsWith('/admin/operations')) return json(route,{
      auth_rate_limit_per_minute:30,generation_rate_limit_per_minute:10,payment_rate_limit_per_minute:10,registration_rate_limit_per_day:20,yookassa_webhook_rate_limit_per_minute:120,asset_upload_rate_limit_per_minute:12,asset_max_retained_count_per_user:200,asset_max_retained_bytes_per_user:536870912,generation_max_inflight_per_user:2,initial_concept_offer_limit_per_day:3,
      starter_credits:0,initial_concept_credits:0,media_retention_days:30,backup_interval_hours:24,backup_retention_days:14,media_min_free_bytes:2147483648,updated_at:null,
    })
    if(path.endsWith('/admin/audit')) return json(route,[])
    if(path.endsWith('/projects')&&method==='GET') return json(route,{items:[],next_cursor:null,has_more:false})

    return json(route,{type:'mock_unhandled',detail:`${method} ${path}`},404)
  })

  await page.goto('/?admin=1')
  await page.getByRole('button',{name:'AI и стоимость'}).click()

  await expect(page.getByRole('heading',{name:'История AI Sandbox'})).toBeVisible()
  await expect(page.getByText('Newest still prompt',{exact:true})).toBeVisible()
  await expect(page.getByText('Older still prompt',{exact:true})).toBeVisible()
  await expect(page.getByText('Warm orbit',{exact:true})).toBeVisible()
  await expect(page.getByText(/Legacy 360°/)).toBeVisible()
  await expect(page.getByLabel('Primary timeout, сек')).toHaveValue('90')

  await page.reload()
  await page.getByRole('button',{name:'AI и стоимость'}).click()
  await expect(page.getByText('Older still prompt',{exact:true})).toBeVisible()

  const olderCard=page.locator('article').filter({hasText:'Older still prompt'})
  await olderCard.getByRole('button',{name:'Использовать для пролёта'}).click()
  await expect(olderCard.getByRole('button',{name:'Выбран для пролёта'})).toBeVisible()
  await expect(page.getByLabel('Nexus model ID')).toHaveValue('gpt-image-2')
  await expect(page.getByLabel('Prompt')).toHaveValue('Older still prompt')
  await expect(page.getByRole('heading',{name:'Bird flyover GIF'})).toBeVisible()
  await expect(page.getByLabel('Ключевых кадров')).toHaveValue('6')
  await expect(page.getByLabel('Промежуточных кадров')).toHaveValue('3')
  await expect(page.getByLabel('мс / кадр')).toHaveValue('120')
  await expect(page.getByText('5 image-вызовов · 0 video-вызовов',{exact:false})).toBeVisible()
  await page.getByRole('button',{name:'Собрать GIF-пролёт'}).click()
  await expect.poll(()=>submittedFlyover).not.toBeNull()
  expect(submittedFlyover).toMatchObject({
    source_generation_id:olderStill.id,
    model_name:'gpt-image-2',
    keyframe_count:6,
    inbetween_frames:3,
    frame_duration_ms:120,
  })
})
