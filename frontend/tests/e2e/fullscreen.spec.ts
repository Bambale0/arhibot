import { expect, test, type Page, type Route } from '@playwright/test'

const now = '2026-09-12T08:30:00Z'
const projectId = '33333333-3333-4333-8333-333333333399'
const user = {
  id:'11111111-1111-4111-8111-111111111199',
  display_name:'Telegram E2E',
  status:'active',
  role:'user',
  credits_balance:3,
  created_at:now,
  updated_at:now,
  capabilities:{can_generate:true},
}
const session = {
  session_id:'77777777-7777-4777-8777-777777777799',
  catalog_version:'fullscreen-v1',
  selected_objects:['lavochka'],
  initial_concept_mode:true,
  survey_completed_objects:[],
  initial_generation_id:null,
  initial_concept_accepted:false,
  current_object:null,
  current_question_id:null,
  source_step_completed:true,
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
const project = {
  id:projectId,
  name:'Fullscreen project',
  description:null,
  status:'active',
  context:{questionnaire_draft:false,design_session:session},
  created_at:now,
  updated_at:now,
}
const catalog = {
  version:'fullscreen-v1',
  sections:[{key:'furniture',title:'Мебель',object_keys:['lavochka']}],
  questionnaires:[{
    key:'lavochka',title:'Лавочка',source_file:'fixture',order:0,scene_policy:{},questions:[
      {id:'1',text:'Какая лавка?',kind:'single',options:['Деревянная'],required:true,skip_default:null,skip_condition:null,help:null,field_hint:null,placeholder:null,max_selections:null,min_value:null,max_value:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'2',text:'Эскиз подходит?',kind:'single',options:['Да','Нет'],required:true,skip_default:null,skip_condition:null,help:null,field_hint:null,placeholder:null,max_selections:null,min_value:null,max_value:null,phase:'review',condition:null,option_rules:{},edit_targets:{}},
    ],
  }],
}

async function json(route:Route,data:unknown,status=200){
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
}

async function prepare(
  page:Page,
  ideas:unknown[] = [],
  onIdeasPage?: (limit:number, offset:number) => void,
) {
  await page.addInitScript(() => {
    sessionStorage.setItem('auroom.access_token','fullscreen-e2e')
    window.Telegram = { WebApp: { initData:'', requestFullscreen:() => {} } }
  })
  await page.route('**/api/v1/**',async route => {
    const request=route.request(), path=new URL(request.url()).pathname, method=request.method()
    if(path.endsWith('/me')&&method==='GET') return json(route,user)
    if(path.endsWith('/projects')&&method==='GET') return json(route,{items:[],next_cursor:null,has_more:false})
    if(path.endsWith(`/projects/${projectId}`)&&method==='GET') return json(route,project)
    if(path.endsWith('/ideas')&&method==='GET') {
      const url=new URL(request.url())
      const limit=Number(url.searchParams.get('limit')||50)
      const offset=Number(url.searchParams.get('offset')||0)
      onIdeasPage?.(limit,offset)
      return json(route,ideas.slice(offset,offset+limit))
    }
    if(path.endsWith('/questionnaires')&&method==='GET') return json(route,catalog)
    if(path.endsWith('/questionnaire-generation-cost')&&method==='GET') return json(route,{generation_type:'master_plan',initial_credits:0,credits:1,initial_offer_available:true,is_available:true})
    if(path.endsWith(`/projects/${projectId}/questionnaire-session`)&&method==='GET') return json(route,{session})
    return json(route,{type:'mock_unhandled',detail:`${method} ${path}`},404)
  })
}

async function installFullscreenCounters(page:Page) {
  await page.evaluate(() => {
    const telegram=window.Telegram?.WebApp
    if (!telegram) throw new Error('Telegram WebApp is unavailable')
    ;(window as unknown as { __fullscreenCalls:number }).__fullscreenCalls = 0
    ;(window as unknown as { __expandCalls:number }).__expandCalls = 0
    telegram.expand=() => { (window as unknown as { __expandCalls:number }).__expandCalls += 1 }
    telegram.requestFullscreen=() => { (window as unknown as { __fullscreenCalls:number }).__fullscreenCalls += 1 }
  })
}

test('fullscreen control stays visible on Ideas where AppFrame topbar is hidden',async({page})=>{
  await page.setViewportSize({width:1024,height:720})
  await prepare(page)
  await page.goto('/?section=ideas')
  const button=page.getByRole('button',{name:'Открыть на весь экран'})
  await expect(button).toBeVisible()
  await expect(button.locator('svg')).toHaveCount(1)
  const box=await button.boundingBox()
  expect(box?.width).toBe(40)
  expect(box?.height).toBe(40)
  await installFullscreenCounters(page)
  await button.click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { __expandCalls:number }).__expandCalls)).toBe(1)
  await expect.poll(() => page.evaluate(() => (window as unknown as { __fullscreenCalls:number }).__fullscreenCalls)).toBe(1)
})

test('fullscreen control is hidden on mobile Telegram viewports',async({page})=>{
  await page.setViewportSize({width:390,height:844})
  await prepare(page)
  await page.goto('/?section=ideas')
  await expect(page.locator('.telegram-fullscreen-button')).toBeHidden()
})

test('Ideas slideshow requests only active and neighboring previews',async({page})=>{
  const tinyPng=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')
  const requested:string[]=[]
  await page.route('**/perf/**',async route=>{
    requested.push(new URL(route.request().url()).pathname)
    await route.fulfill({status:200,contentType:'image/png',body:tinyPng})
  })
  const ideas=Array.from({length:4},(_,index)=>({
    id:`idea-${index}`,
    title:`Idea ${index}`,
    category:'Performance',
    generation_type:'master_plan',
    image_url:`/perf/original-${index}.png`,
    preview_url:`/perf/preview-${index}.webp`,
    objects:[],
    selected_objects:[],
    published_at:now,
    is_saved:false,
  }))
  await prepare(page,ideas)
  await page.goto('/?section=ideas')

  await expect(page.locator('[data-feed-index="0"]')).toBeVisible()
  await expect.poll(()=>requested.includes('/perf/preview-0.webp')).toBe(true)
  await expect.poll(()=>requested.includes('/perf/preview-1.webp')).toBe(true)
  expect(requested).not.toContain('/perf/preview-2.webp')
  expect(requested).not.toContain('/perf/preview-3.webp')
  expect(requested.some(path=>path.includes('/perf/original-'))).toBe(false)

  await page.locator('[data-feed-index="2"]').scrollIntoViewIfNeeded()
  await expect.poll(()=>requested.includes('/perf/preview-2.webp')).toBe(true)
  await expect.poll(()=>requested.includes('/perf/preview-3.webp')).toBe(true)
  expect(requested.some(path=>path.includes('/perf/original-'))).toBe(false)
})

test('Ideas feed loads metadata in pages instead of mounting the full catalog up front',async({page})=>{
  const requests:{limit:number;offset:number}[]=[]
  const ideas=Array.from({length:18},(_,index)=>({
    id:`paged-idea-${index}`,
    title:`Paged idea ${index}`,
    category:'Performance',
    generation_type:'master_plan',
    image_url:null,
    preview_url:null,
    objects:[],
    selected_objects:[],
    published_at:now,
    is_saved:false,
  }))
  await prepare(page,ideas,(limit,offset)=>requests.push({limit,offset}))
  await page.goto('/?section=ideas')

  await expect(page.locator('[data-feed-index]')).toHaveCount(12)
  expect(requests[0]).toEqual({limit:12,offset:0})

  await page.locator('[data-feed-index="9"]').scrollIntoViewIfNeeded()
  await expect.poll(()=>requests.some((item)=>item.limit===12&&item.offset===12)).toBe(true)
  await expect(page.locator('[data-feed-index]')).toHaveCount(18)
})

test('fullscreen control stays visible inside standalone questionnaire flow',async({page})=>{
  await page.setViewportSize({width:1024,height:720})
  await prepare(page)
  await page.goto(`/?project=${projectId}`)
  await expect(page.getByText('Заполните параметры всех объектов')).toBeVisible()
  const button=page.getByRole('button',{name:'Открыть на весь экран'})
  await expect(button).toBeVisible()
  await installFullscreenCounters(page)
  await button.click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { __fullscreenCalls:number }).__fullscreenCalls)).toBe(1)
})
