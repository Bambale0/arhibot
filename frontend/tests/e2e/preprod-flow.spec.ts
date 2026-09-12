import { expect, test, type Route } from '@playwright/test'

const now = '2026-09-10T18:30:00Z'
const user = { id:'11111111-1111-4111-8111-111111111111', display_name:'Предпрод', status:'active', role:'user', credits_balance:10, created_at:now, updated_at:now, capabilities:{can_generate:true} }
const projectId='33333333-3333-4333-8333-333333333333'
const generationIds=['44444444-4444-4444-8444-444444444441','44444444-4444-4444-8444-444444444442']
const assetIds=['55555555-5555-4555-8555-555555555551','55555555-5555-4555-8555-555555555552']
const ideaId='66666666-6666-4666-8666-666666666666'
const catalog = {
  version:'e2e-v1',
  sections:[
    {key:'house',title:'Дом',object_keys:['eskez-doma']},
    {key:'furniture',title:'Мебель и площадки',object_keys:['lavochka']},
    {key:'landscape',title:'Участок',object_keys:['gazon','prud']},
  ],
  questionnaires:[
    {key:'lavochka',title:'Лавочка',source_file:'fixture',order:0,scene_policy:{},questions:[
      {id:'1',text:'Какая лавка?',kind:'single',options:['Деревянная со спинкой','Металл + дерево'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'2',text:'Где на участке относительно дома?',kind:'single',options:['Слева от дома','Справа от дома'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'3',text:'Эскиз лавочки вам подходит?',kind:'single',options:['Да, идём дальше','Нет, хочу уточнить и сделать заново'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'review',condition:null,option_rules:{},edit_targets:{}},
    ]},
    {key:'gazon',title:'Газон и посадки',source_file:'fixture',order:1,scene_policy:{},questions:[
      {id:'1',text:'Какой характер двора?',kind:'single',options:['Минимализм, газон и гравий','Лесной, хвойные'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'2',text:'Эскиз посадок вам подходит?',kind:'single',options:['Да, идём дальше','Нет, хочу уточнить и сделать заново'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'review',condition:null,option_rules:{},edit_targets:{}},
    ]},
    {key:'prud',title:'Пруд или ручей',source_file:'fixture',order:2,scene_policy:{},questions:[
      {id:'1',text:'Что делаем?',kind:'single',options:['Пруд','Ручей'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'2',text:'Эскиз воды вам подходит?',kind:'single',options:['Да, идём дальше','Нет, хочу уточнить и сделать заново'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'review',condition:null,option_rules:{},edit_targets:{}},
    ]},
    {key:'eskez-doma',title:'Дом, фасад',source_file:'fixture',order:3,scene_policy:{},questions:[
      {id:'4',text:'Сколько этажей?',kind:'single',options:['1 этаж','2 этажа','2 этажа + мансарда','3 этажа'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'12',text:'Нужна терраса?',kind:'single',options:['Терраса','Нет'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'pre_render',condition:null,option_rules:{},edit_targets:{}},
      {id:'12б',text:'На каких этажах терраса?',kind:'multi',options:['Первый этаж','Второй этаж','Третий этаж','Мансарда'],required:true,skip_default:null,help:null,field_hint:null,max_selections:4,phase:'pre_render',condition:{question_id:'12',operator:'neq',value:'Нет'},option_rules:{
        'Первый этаж':{question_id:'4',operator:'floor_option',value:'Первый этаж'},
        'Второй этаж':{question_id:'4',operator:'floor_option',value:'Второй этаж'},
        'Третий этаж':{question_id:'4',operator:'floor_option',value:'Третий этаж'},
        'Мансарда':{question_id:'4',operator:'floor_option',value:'Мансарда'},
      },edit_targets:{}},
      {id:'15',text:'Эскиз дома вам подходит?',kind:'single',options:['Да, идём дальше','Нет, хочу уточнить и сделать заново'],required:true,skip_default:null,help:null,field_hint:null,max_selections:null,phase:'review',condition:null,option_rules:{},edit_targets:{}},
    ]},
  ],
}
let session:any
let project:any
let generationCount=0
let publication:any=null
let savedIdea=false
let hideIdeaFromFeed=false
function resetState(){
  generationCount=0; publication=null; savedIdea=false; hideIdeaFromFeed=false
  session={session_id:'77777777-7777-4777-8777-777777777777',catalog_version:catalog.version,selected_objects:['lavochka'],initial_concept_mode:false,survey_completed_objects:[],initial_generation_id:null,initial_concept_accepted:false,current_object:null,current_question_id:null,source_step_completed:false,source_asset_id:null,scene_asset_id:null,answers:{},accepted_objects:[],removed_objects:[],pending_removal_object:null,generation_ids:{},edit_question_ids:[],review_comments:{},edit_regions:{},lock_regions:{},region_mode:null,region_object:null,application_submitted:false}
  project={id:projectId,name:'Лавочка',description:null,status:'active',context:{questionnaire_draft:false,design_session:session},created_at:now,updated_at:now}
}
function asset(i:number){return {id:assetIds[i],project_id:projectId,type:'image',purpose:'generation_output',original_filename:'result.png',mime_type:'image/png',size_bytes:1234,width:640,height:480,url:`data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"></svg>`,created_at:now}}
function generation(i:number,status='completed'){return {id:generationIds[i],project_id:projectId,input_asset_id:null,output_asset:status==='completed'?asset(i):null,type:'master_plan',status,credits_charged:1,model_name:'mock',fallback_used:false,composition_mode:'replace',edit_region:null,protected_regions:[],error:null,created_at:now,updated_at:now,started_at:now,completed_at:status==='completed'?now:null}}
async function json(route:Route,data:unknown,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})}

test.beforeEach(async ({page})=>{
  resetState()
  await page.addInitScript(()=>{localStorage.setItem('auroom.access_token','e2e');localStorage.setItem('auroom.refresh_token','e2e-refresh')})
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(), path=new URL(req.url()).pathname, method=req.method()
    if(path.endsWith('/me')&&method==='GET') return json(route,user)
    if(path.endsWith('/projects')&&method==='GET') return json(route,{items:[],next_cursor:null,has_more:false})
    if(path.endsWith(`/projects/${projectId}`)&&method==='GET') return json(route,project)
    for(let i=0;i<generationIds.length;i++) if(path.endsWith(`/generations/${generationIds[i]}`)&&method==='GET') return json(route,generation(i))
    if(path.endsWith('/questionnaires')&&method==='GET') return json(route,catalog)
    if(path.endsWith('/questionnaire-generation-cost')&&method==='GET') return json(route,{generation_type:'master_plan',credits:1,is_available:true})
    if(path.endsWith('/questionnaire-projects')&&method==='POST') return json(route,project,201)
    if(path.endsWith(`/projects/${projectId}/questionnaire-session`)&&method==='GET') return json(route,{session})
    if(path.endsWith(`/projects/${projectId}/questionnaire-session`)&&method==='PUT') {session=JSON.parse(req.postData()||'{}');project={...project,context:{...project.context,design_session:session}};return json(route,{session})}
    if(path.endsWith(`/projects/${projectId}/questionnaire-generation`)&&method==='POST'){const i=generationCount++;return json(route,generation(i,'queued'),202)}
    if(path.endsWith(`/projects/${projectId}/questionnaire-initial-accept`)&&method==='POST'){
      const completed=generation(0)
      session={...session,initial_concept_accepted:true,accepted_objects:[...session.selected_objects],generation_ids:Object.fromEntries(session.selected_objects.map((key:string)=>[key,generationIds[0]])),scene_asset_id:completed.output_asset.id,current_object:null,current_question_id:null}
      project={...project,context:{...project.context,design_session:session}}
      return json(route,{session})
    }
    for(let i=0;i<generationIds.length;i++) if(path.endsWith(`/projects/${projectId}/questionnaire-generation/${generationIds[i]}`)&&method==='GET') return json(route,generation(i))
    if(path.endsWith('/ideas')&&method==='GET') return json(route,hideIdeaFromFeed?[]:[{id:ideaId,title:'Лавочка',category:'Мебель и площадки',generation_type:'master_plan',image_url:asset(1).url,objects:[],selected_objects:['lavochka'],published_at:now,is_saved:savedIdea}])
    if(path.endsWith(`/ideas/${ideaId}`)&&method==='GET') return json(route,{id:ideaId,title:'Лавочка',category:'Мебель и площадки',generation_type:'master_plan',image_url:asset(1).url,objects:[],selected_objects:['lavochka'],published_at:now,is_saved:savedIdea})
    if(path.endsWith(`/ideas/${ideaId}/save`)&&method==='PUT'){savedIdea=true;return json(route,{idea_id:ideaId,is_saved:true})}
    if(path.endsWith(`/ideas/${ideaId}/save`)&&method==='DELETE'){savedIdea=false;return json(route,{idea_id:ideaId,is_saved:false})}
    if(path.endsWith(`/ideas/mine/${generationIds[1]}`)&&method==='GET') return json(route,publication)
    if(path.endsWith(`/ideas/mine/${generationIds[1]}`)&&method==='DELETE'){publication={...publication,owner_published:false};return json(route,publication)}
    if(path.endsWith('/ideas')&&method==='POST'){
      publication=publication
        ? {...publication,owner_published:true}
        : {id:ideaId,generation_id:generationIds[1],title:'Лавочка',category:'Мебель и площадки',generation_type:'master_plan',image_url:asset(1).url,objects:[],selected_objects:['lavochka'],published_at:now,is_saved:false,owner_published:true,is_active:true,sort_order:0,updated_at:now}
      return json(route,publication,201)
    }
    return json(route,{type:'mock_unhandled',detail:`${method} ${path}`},404)
  })
})

test('canonical create flow supports refinement and own unpublish without technical region UI',async({page})=>{
  const errors:string[]=[]; page.on('console',m=>{if(m.type()==='error')errors.push(m.text())})
  await page.goto('/')
  await page.getByRole('button',{name:'Создать проект'}).click()
  await expect(page.getByText('Что проектируем?')).toBeVisible()
  await expect(page.getByText('4 функции AuRoom')).toHaveCount(0)
  await page.getByText('Мебель и площадки',{exact:true}).click(); await page.getByText('Лавочка',{exact:true}).click(); await page.getByRole('button',{name:'Начать проект'}).click()
  await page.getByRole('button',{name:'Продолжить без фото'}).click(); await page.getByRole('button',{name:'Лавочка',exact:true}).click()
  await page.getByText('Деревянная со спинкой',{exact:true}).click(); await page.getByText('Слева от дома',{exact:true}).click()
  await expect(page.getByText('Эскиз лавочки вам подходит?')).toBeVisible(); expect(generationCount).toBe(1)
  await page.getByRole('button',{name:'Уточнить'}).click(); await page.getByText('Металл + дерево',{exact:true}).click(); await page.getByText('Справа от дома',{exact:true}).click()
  await expect(page.getByText('Эскиз лавочки вам подходит?')).toBeVisible(); expect(generationCount).toBe(2); await expect(page.getByText('Недостаточно кредитов')).toHaveCount(0)
  await page.getByRole('button',{name:'Подходит'}).click(); await expect(page.getByText('Что проектируем дальше?')).toBeVisible()
  await expect(page.getByText(/ПИКСЕЛЬНАЯ|Зафиксируйте:|выделите прямоугольник/)).toHaveCount(0)
  await page.getByRole('button',{name:'Добавить в Идеи'}).click(); await expect(page.getByRole('button',{name:'Убрать из Идей'})).toBeVisible()
  await page.getByRole('button',{name:'Убрать из Идей'}).click(); await expect(page.getByRole('button',{name:'Вернуть в Идеи'})).toBeVisible()
  await page.getByRole('button',{name:'Вернуть в Идеи'}).click(); await expect(page.getByRole('button',{name:'Убрать из Идей'})).toBeVisible()
  await expect(page.getByText('AUROOM_RENDER_SPEC_V1')).toHaveCount(0); expect(errors).toEqual([])
})


test('initial concept collects all answers before one generation and supports previous question',async({page})=>{
  session={...session,initial_concept_mode:true,current_object:null}
  project={...project,context:{...project.context,design_session:session}}
  await page.goto('/')
  await page.getByRole('button',{name:'Создать проект'}).click()
  await page.getByText('Мебель и площадки',{exact:true}).click()
  await page.getByText('Лавочка',{exact:true}).click()
  await page.getByRole('button',{name:'Начать проект'}).click()
  await page.getByRole('button',{name:'Продолжить без фото'}).click()
  await page.getByRole('button',{name:'Лавочка',exact:true}).click()

  await page.getByText('Деревянная со спинкой',{exact:true}).click()
  await expect(page.getByText('Где на участке относительно дома?')).toBeVisible()
  expect(generationCount).toBe(0)

  await page.getByRole('button',{name:'Назад'}).click()
  await expect(page.getByText('Какая лавка?')).toBeVisible()
  await page.getByText('Металл + дерево',{exact:true}).click()
  await page.getByText('Справа от дома',{exact:true}).click()

  await expect(page.getByText('Всё готово к одной генерации')).toBeVisible()
  expect(generationCount).toBe(0)
  await expect(page.getByText('Одна общая генерация · 1 кр.')).toBeVisible()
  await page.getByRole('button',{name:'Создать общую концепцию'}).click()
  await expect(page.getByAltText('Общая концепция участка')).toBeVisible()
  expect(generationCount).toBe(1)

  await page.getByRole('button',{name:'Принять концепцию'}).click()
  await expect(page.getByText('Что делаем дальше?')).toBeVisible()
  await expect(page.getByText('Следующая генерация · 1 кр.')).toBeVisible()
})



test('multi-object initial concept waits for every questionnaire, allows answer editing, then generates once',async({page})=>{
  session={...session,selected_objects:['lavochka','gazon','prud'],initial_concept_mode:true,current_object:null}
  project={...project,name:'Участок целиком',context:{...project.context,design_session:session}}

  await page.goto('/')
  await page.getByRole('button',{name:'Создать проект'}).click()
  await page.getByText('Мебель и площадки',{exact:true}).click()
  await page.getByText('Лавочка',{exact:true}).click()
  await page.getByRole('button',{name:'Добавить из другого раздела'}).click()
  await page.getByText('Участок',{exact:true}).click()
  await page.getByText('Газон и посадки',{exact:true}).click()
  await page.getByText('Пруд или ручей',{exact:true}).click()
  await page.getByRole('button',{name:'Начать проект'}).click()
  await page.getByRole('button',{name:'Продолжить без фото'}).click()

  await page.getByRole('button',{name:'Лавочка',exact:true}).click()
  await page.getByText('Деревянная со спинкой',{exact:true}).click()
  await page.getByText('Справа от дома',{exact:true}).click()
  expect(generationCount).toBe(0)

  await page.getByRole('button',{name:'Газон и посадки',exact:true}).click()
  await page.getByText('Минимализм, газон и гравий',{exact:true}).click()
  expect(generationCount).toBe(0)

  await page.getByRole('button',{name:'Пруд или ручей',exact:true}).click()
  await page.getByText('Пруд',{exact:true}).click()
  await expect(page.getByText('Всё готово к одной генерации')).toBeVisible()
  expect(generationCount).toBe(0)

  await page.locator('details').filter({hasText:'Лавочка'}).locator('summary').click()
  await page.getByRole('button',{name:/Какая лавка\?/}).click()
  await page.getByText('Металл + дерево',{exact:true}).click()
  await page.getByText('Справа от дома',{exact:true}).click()
  await expect(page.getByText('Всё готово к одной генерации')).toBeVisible()
  expect(generationCount).toBe(0)

  await page.locator('details').filter({hasText:'Лавочка'}).locator('summary').click()
  await expect(page.getByRole('button',{name:/Какая лавка\?/})).toContainText('Металл + дерево')
  await page.getByRole('button',{name:'Создать общую концепцию'}).click()
  await expect(page.getByAltText('Общая концепция участка')).toBeVisible()
  expect(generationCount).toBe(1)
})


test('house terrace floor options follow selected storeys in the UI',async({page})=>{
  session={...session,selected_objects:['eskez-doma'],initial_concept_mode:true,current_object:null}
  project={...project,name:'Дом',context:{...project.context,design_session:session}}

  await page.goto('/')
  await page.getByRole('button',{name:'Создать проект'}).click()
  await page.getByText('Дом',{exact:true}).click()
  await page.getByText('Дом, фасад',{exact:true}).click()
  await page.getByRole('button',{name:'Начать проект'}).click()
  await page.getByRole('button',{name:'Продолжить без фото'}).click()
  await page.getByRole('button',{name:'Дом, фасад',exact:true}).click()

  await page.getByText('1 этаж',{exact:true}).click()
  await page.getByText('Терраса',{exact:true}).click()
  await expect(page.getByText('На каких этажах терраса?')).toBeVisible()
  await expect(page.getByText('Первый этаж',{exact:true})).toBeVisible()
  await expect(page.getByText('Второй этаж',{exact:true})).toHaveCount(0)
  await expect(page.getByText('Третий этаж',{exact:true})).toHaveCount(0)
  await expect(page.getByText('Мансарда',{exact:true})).toHaveCount(0)

  await page.getByRole('button',{name:'Назад'}).click()
  await page.getByRole('button',{name:'Назад'}).click()
  await page.getByText('2 этажа + мансарда',{exact:true}).click()
  await page.getByText('Терраса',{exact:true}).click()
  await expect(page.getByText('Второй этаж',{exact:true})).toBeVisible()
  await expect(page.getByText('Мансарда',{exact:true})).toBeVisible()
  await expect(page.getByText('Третий этаж',{exact:true})).toHaveCount(0)
})


test('fullscreen control calls Telegram expand and requestFullscreen',async({page})=>{
  await page.goto('/')
  await page.evaluate(()=>{
    const target=window as typeof window & { __expandCalls?:number; __fullscreenCalls?:number }
    if (!window.Telegram?.WebApp) throw new Error('Telegram WebApp SDK is unavailable')
    window.Telegram.WebApp.expand=()=>{target.__expandCalls=(target.__expandCalls||0)+1}
    window.Telegram.WebApp.requestFullscreen=()=>{target.__fullscreenCalls=(target.__fullscreenCalls||0)+1}
  })
  await page.getByRole('button',{name:'Открыть на весь экран'}).click()
  await expect.poll(()=>page.evaluate(()=>({
    expand:(window as typeof window & {__expandCalls?:number}).__expandCalls||0,
    fullscreen:(window as typeof window & {__fullscreenCalls?:number}).__fullscreenCalls||0,
  }))).toEqual({expand:1,fullscreen:1})
})


test('shared idea deep-link opens exact work and saves on the server',async({page})=>{
  hideIdeaFromFeed=true
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'share', {
      configurable:true,
      value: async (data:unknown) => { (window as typeof window & { __shareData?:unknown }).__shareData = data },
    })
    const originalScrollIntoView = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function(arg?: boolean | ScrollIntoViewOptions) {
      const target = window as typeof window & { __ideaScrollCalls?:number }
      target.__ideaScrollCalls = (target.__ideaScrollCalls || 0) + 1
      return originalScrollIntoView?.call(this, arg)
    }
  })
  await page.goto(`/?idea=${ideaId}`)
  const card = page.locator(`[data-idea-id="${ideaId}"]`)
  await expect(card).toBeVisible()
  await expect(card.getByText('Идеи AuRoom')).toBeVisible()
  await expect(card.getByRole('button',{name:'Создать по этой работе'})).toBeVisible()
  const brandStyle = await page.locator('.ideas-concept-topbar .wordmark').evaluate((element) => {
    const style = getComputedStyle(element)
    return { color:style.color, fontFamily:style.fontFamily }
  })
  expect(brandStyle.color).toBe('rgb(228, 198, 126)')
  expect(brandStyle.fontFamily).not.toMatch(/Georgia|Times New Roman/)
  const brandSymbol = await page.locator('.ideas-concept-topbar .wordmark-dot').evaluate((element) => getComputedStyle(element).backgroundImage)
  expect(brandSymbol).toContain('/brand/auroom-symbol.webp')
  await card.getByRole('button',{name:'Сохранить'}).click()
  await expect(card.getByRole('button',{name:'Убрать из сохранённых'})).toBeVisible()
  expect(savedIdea).toBe(true)
  const scrollCalls = await page.evaluate(() => (window as typeof window & { __ideaScrollCalls?:number }).__ideaScrollCalls || 0)
  expect(scrollCalls).toBe(1)
  await card.getByRole('button',{name:'Поделиться'}).click()
  const shared = await page.evaluate(() => (window as typeof window & { __shareData?:{url?:string} }).__shareData)
  expect(shared?.url).toContain(`idea=${ideaId}`)
})


test('legacy browser bookmarks migrate to server saves once',async({page})=>{
  await page.addInitScript((id) => {
    localStorage.setItem('auroom.saved_ideas', JSON.stringify([id]))
  }, ideaId)
  await page.goto('/?idea=' + ideaId)
  const card = page.locator(`[data-idea-id="${ideaId}"]`)
  await expect(card.getByRole('button',{name:'Убрать из сохранённых'})).toBeVisible()
  expect(savedIdea).toBe(true)
  const legacy = await page.evaluate(() => localStorage.getItem('auroom.saved_ideas'))
  expect(legacy).toBeNull()
})


test('Telegram project deep-link resumes the exact questionnaire project',async({page})=>{
  session={...session,source_step_completed:true,current_object:'lavochka',current_question_id:'1'}
  project={...project,context:{...project.context,design_session:session}}
  await page.goto('/?project=' + projectId)
  await expect(page.getByText('Какая лавка?')).toBeVisible()
  await expect(page.locator('.questionnaire-topbar strong').getByText('Лавочка',{exact:true})).toBeVisible()
})

test('Telegram generation deep-link opens the exact completed result',async({page})=>{
  await page.goto('/?generation=' + generationIds[0])
  await expect(page.getByText('Готовая работа')).toBeVisible()
  await expect(page.getByAltText('Сгенерированная работа AuRoom')).toBeVisible()
})
