import { expect, test, type Route } from '@playwright/test'

const now='2026-09-14T13:00:00Z'
const admin={
  id:'11111111-1111-4111-8111-111111111111',
  display_name:'Admin E2E',
  status:'active',
  role:'superadmin',
  credits_balance:10,
  created_at:now,
  updated_at:now,
  capabilities:{can_generate:true},
}

const questionnaireCatalog={
  catalog:{
    version:'2026-09-14.1',
    sections:[{key:'house',title:'Дом',object_keys:['eskez-doma']}],
    questionnaires:[{
      key:'eskez-doma',
      title:'Дом, фасад',
      source_file:'house.txt',
      order:0,
      questions:[{
        id:'1',
        text:'Стиль дома?',
        kind:'single',
        options:['Современный минимализм'],
        required:true,
        skip_default:null,
        skip_condition:null,
        help:null,
        field_hint:null,
        placeholder:null,
        max_selections:null,
        min_value:null,
        max_value:null,
        phase:'pre_render',
        condition:null,
        option_rules:{},
        edit_targets:{},
      }],
      scene_policy:{camera:'hero'},
    }],
    application_key:'zayavka',
    source_rules:[],
  },
  source_texts:{'eskez-doma':{filename:'house.txt',text:'1. Стиль дома?'}},
  updated_at:now,
}

async function json(route:Route,data:unknown,status=200){
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
}

test('admin publishes a new questionnaire catalog revision from the control plane', async ({page})=>{
  let submitted:unknown=null

  await page.addInitScript(()=>{
    localStorage.setItem('auroom.access_token','e2e')
    localStorage.setItem('auroom.refresh_token','e2e-refresh')
  })

  await page.route('**/api/v1/**',async route=>{
    const req=route.request()
    const path=new URL(req.url()).pathname
    const method=req.method()

    if(path.endsWith('/me')&&method==='GET') return json(route,admin)
    if(path.endsWith('/admin/overview')) return json(route,{yookassa_configured:false,nexus_configured:true,telegram_configured:true})
    if(path.endsWith('/admin/tariffs')) return json(route,[])
    if(path.endsWith('/admin/billing-settings')) return json(route,{receipts_enabled:false,vat_code:null,payment_subject:null,payment_mode:null,updated_at:null})
    if(path.endsWith('/admin/ideas')) return json(route,[])
    if(path.endsWith('/admin/questionnaire-applications')) return json(route,[])
    if(path.endsWith('/admin/questionnaires')&&method==='GET') return json(route,questionnaireCatalog)
    if(path.endsWith('/admin/questionnaires')&&method==='PUT'){
      submitted=JSON.parse(req.postData()||'{}')
      const body=submitted as typeof questionnaireCatalog
      return json(route,{...body,updated_at:'2026-09-14T13:05:00Z'})
    }
    if(path.endsWith('/admin/generation/sandbox/history')) return json(route,[])
    if(path.endsWith('/admin/generation')) return json(route,{primary_model:'nano-banana-pro',fallback_model:'gpt-image-2',primary_timeout_seconds:90,primary_params:{},fallback_params:{},mode_params:{},updated_at:now})
    if(path.endsWith('/admin/generation-prices')) return json(route,[])
    if(path.endsWith('/admin/prompts')) return json(route,[])
    if(path.endsWith('/admin/users')) return json(route,[])
    if(path.endsWith('/admin/credit-transactions')) return json(route,[])
    if(path.endsWith('/admin/payments')) return json(route,[])
    if(path.endsWith('/admin/broadcasts')) return json(route,[])
    if(path.endsWith('/admin/telegram-content')) return json(route,{configured:false,bot_name:null,short_description:null,description:null,start_text:null,open_button_text:null,start_command_description:null,app_command_description:null,updated_at:null})
    if(path.endsWith('/admin/operations')) return json(route,{auth_rate_limit_per_minute:30,generation_rate_limit_per_minute:10,payment_rate_limit_per_minute:10,registration_rate_limit_per_day:20,yookassa_webhook_rate_limit_per_minute:120,asset_upload_rate_limit_per_minute:12,asset_max_retained_count_per_user:200,asset_max_retained_bytes_per_user:536870912,generation_max_inflight_per_user:2,initial_concept_offer_limit_per_day:3,starter_credits:0,initial_concept_credits:0,media_retention_days:30,backup_interval_hours:24,backup_retention_days:14,media_min_free_bytes:2147483648,updated_at:null})
    if(path.endsWith('/admin/audit')) return json(route,[])
    return json(route,{type:'mock_unhandled',detail:`${method} ${path}`},404)
  })

  await page.goto('/?admin=1')
  await page.getByRole('button',{name:'Опросники'}).click()

  await expect(page.getByRole('heading',{name:'Опросники'})).toBeVisible()
  await expect(page.getByText('1 опросников · 1 разделов')).toBeVisible()

  const version=page.getByLabel('Новая версия каталога')
  await version.fill('2026-09-14.2')
  await page.getByRole('button',{name:'Опубликовать новую версию'}).click()

  await expect(version).toHaveValue('2026-09-14.2')
  expect(submitted).toMatchObject({
    catalog:{version:'2026-09-14.2'},
    source_texts:{'eskez-doma':{filename:'house.txt'}},
  })
})
