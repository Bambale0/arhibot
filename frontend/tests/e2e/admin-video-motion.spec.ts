import { expect, test, type Route } from '@playwright/test'

const now = '2026-10-14T12:00:00Z'
const admin = {
  id:'11111111-1111-4111-8111-111111111111',
  display_name:'Admin Video E2E',
  status:'active',
  role:'superadmin',
  credits_balance:10,
  created_at:now,
  updated_at:now,
  capabilities:{can_generate:true},
}
const settings = {
  primary_model:'gpt-image-2',
  fallback_model:'nano-banana-pro',
  primary_timeout_seconds:90,
  primary_params:{},
  fallback_params:{},
  mode_params:{},
  quality_judge_model:'grok-4.5',
  video_enabled:true,
  video_model:'seedance-2.5',
  video_params:{duration:8,resolution:'480p',aspect_ratio:'16:9',motion_prompt:'Rise and truck left.'},
  masked_edit_provider_context_margin_fraction:0.05,
  masked_edit_feather_fraction:0.03,
  masked_edit_feather_min_px:4,
  masked_edit_feather_max_px:32,
  masked_edit_recomposite_feather_multiplier:1,
  masked_edit_boundary_band_px:8,
  masked_edit_max_luma_excess:40,
  masked_edit_max_color_excess:80,
  masked_edit_max_straight_edge_fraction:0.02,
  generation_quality_max_retries:0,
  updated_at:now,
}

async function json(route:Route,data:unknown,status=200) {
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
}

test('admin can tune and clear video camera motion without altering Seedance wire settings', async ({page})=>{
  const requests: Record<string,unknown>[]=[]
  await page.addInitScript(() => {
    sessionStorage.setItem('auroom.access_token','admin-video-e2e')
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
      catalog:{version:'video-e2e',sections:[],questionnaires:[],application_key:'zayavka',source_rules:[]},
      source_texts:{},updated_at:now,
    })
    if(path.endsWith('/admin/generation/sandbox/history')) return json(route,[])
    if(path.endsWith('/admin/generation')&&method==='PUT'){
      const payload=req.postDataJSON() as Record<string,unknown>
      requests.push(payload)
      return json(route,{...settings,...payload,updated_at:now})
    }
    if(path.endsWith('/admin/generation')) return json(route,settings)
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
      auth_rate_limit_per_minute:30,generation_rate_limit_per_minute:10,payment_rate_limit_per_minute:10,
      registration_rate_limit_per_day:20,yookassa_webhook_rate_limit_per_minute:120,asset_upload_rate_limit_per_minute:12,
      asset_max_retained_count_per_user:200,asset_max_retained_bytes_per_user:536870912,generation_max_inflight_per_user:2,
      initial_concept_offer_limit_per_day:3,starter_credits:0,initial_concept_credits:0,media_retention_days:30,
      backup_interval_hours:24,backup_retention_days:14,media_min_free_bytes:2147483648,updated_at:null,
    })
    if(path.endsWith('/admin/audit')) return json(route,[])
    if(path.endsWith('/projects')&&method==='GET') return json(route,{items:[],next_cursor:null,has_more:false})

    return json(route,{type:'mock_unhandled',detail:`${method} ${path}`},404)
  })

  await page.goto('/?admin=1')
  await page.getByRole('button',{name:'AI и стоимость'}).click()

  const motion=page.getByLabel('Траектория камеры Seedance (необязательно)')
  const wire=page.getByLabel('Video params')
  await expect(motion).toHaveValue('Rise and truck left.')
  await expect(wire).not.toContainText('motion_prompt')

  await motion.fill('Start at house level, rise steeply, then truck right.')
  await page.getByRole('button',{name:'Сохранить AI'}).click()
  await expect.poll(()=>requests.length).toBe(1)
  expect(requests[0].video_params).toMatchObject({
    duration:8,resolution:'480p',aspect_ratio:'16:9',
    motion_prompt:'Start at house level, rise steeply, then truck right.',
  })

  await motion.fill('')
  await page.getByRole('button',{name:'Сохранить AI'}).click()
  await expect.poll(()=>requests.length).toBe(2)
  const cleared=requests[1].video_params as Record<string,unknown>
  expect(cleared).toMatchObject({duration:8,resolution:'480p',aspect_ratio:'16:9'})
  expect('motion_prompt' in cleared).toBe(false)
})
