import { expect, test, type Page } from '@playwright/test'
import { createDesignSession, type DesignSession, type QuestionnaireCatalog } from '../../src/questionnaireTypes'

const projectId = '33333333-3333-4333-8333-333333333333'
const sceneId = '55555555-5555-4555-8555-555555555551'
const generationId = '44444444-4444-4444-8444-444444444441'
const now = '2026-09-29T10:00:00Z'
const catalog:QuestionnaireCatalog = {
  version:'navigation', application_key:'zayavka', source_rules:[],
  sections:[{key:'house',title:'Дом',object_keys:['eskez-doma']},{key:'fences',title:'Ограждения',object_keys:['izgorod']}],
  questionnaires:[['eskez-doma','Дом, фасад'],['izgorod','Живая изгородь']].map(([key,title], order) => ({
    key,title,order,source_file:'fixture',scene_policy:{},questions:[{
      id:'1',text:`Параметры: ${title}`,kind:'single',options:['Принятый ответ'],required:true,
      skip_default:null,skip_condition:null,help:null,field_hint:null,placeholder:null,max_selections:null,
      phase:'pre_render',condition:null,option_rules:{},edit_targets:{},
    }],
  })),
}
async function setup(page:Page, stuck = false) {
  let session:DesignSession = {...createDesignSession(catalog.version, ['eskez-doma','izgorod']),
    initial_concept_accepted:true, initial_generation_id:generationId, plot_area_sotkas:10,
    source_step_completed:true, accepted_objects:['eskez-doma','izgorod'],
    survey_completed_objects:['eskez-doma','izgorod'],
    scene_asset_id:sceneId,scene_generation_id:generationId,
    generation_ids:{'eskez-doma':generationId,izgorod:generationId},
    edit_regions:{'eskez-doma':{x:0.2,y:0.2,width:0.5,height:0.5}},
    answers:{'eskez-doma':{'1':'Принятый ответ'},izgorod:{'1':'Принятый ответ'}},
    current_object:stuck ? 'izgorod' : null,current_question_id:stuck ? '1' : null,
  }
  const original = structuredClone(session)
  let rejectSave = false
  const mutations:string[] = []
  const image = {id:sceneId,project_id:projectId,type:'image',purpose:'generation_output',original_filename:'scene.svg',
    mime_type:'image/svg+xml',size_bytes:100,width:640,height:480,created_at:now,
    url:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="green"/></svg>')}
  await page.addInitScript(() => sessionStorage.setItem('auroom.access_token','e2e'))
  await page.route('**/api/v1/**', async route => {
    const request=route.request(), path=new URL(request.url()).pathname, method=request.method()
    if (method !== 'GET') mutations.push(`${method} ${path}`)
    let body:unknown; let status=200
    if (path.endsWith('/me')) body={id:'11111111-1111-4111-8111-111111111111',display_name:'QA',status:'active',role:'user',credits_balance:10,created_at:now,updated_at:now,capabilities:{can_generate:true}}
    else if (path.endsWith('/projects')) body={items:[],next_cursor:null,has_more:false}
    else if (path.endsWith(`/projects/${projectId}`)) body={id:projectId,name:'Участок',description:null,status:'active',context:{design_session:session,plot_area_m2:1000},created_at:now,updated_at:now}
    else if (path.endsWith('/questionnaires')) body=catalog
    else if (path.endsWith('/questionnaire-generation-cost')) body={generation_type:'master_plan',initial_credits:1,credits:1,initial_offer_available:false,is_available:true}
    else if (path.endsWith('/questionnaire-session')) {
      if (method === 'PUT' && rejectSave) {status=503;body={type:'unavailable',detail:'Не удалось сохранить'}}
      else {if(method === 'PUT') session=request.postDataJSON();body={session}}
    }
    else if (path.includes('/questionnaire-generation/')) body={id:generationId,project_id:projectId,status:'completed',output_asset:image}
    else if (path.endsWith(`/assets/${sceneId}`)) body=image
    else if (path.includes('/ideas/mine/')) body=null
    else if (path.endsWith('/ideas')) body=[]
    else {status=404;body={type:'unhandled',detail:`${method} ${path}`}}
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})
  })
  await page.goto(`/?project=${projectId}`)
  return {read:()=>session,original,mutations,failSave:()=>{rejectSave=true}}
}

for (const exit of ['Назад','Отменить изменение']) test(`accepted hedge ${exit} returns to scene without generation and stays there after reload`,async({page})=>{
  const state=await setup(page)
  await page.getByRole('button',{name:'Изменить: Живая изгородь',exact:true}).click()
  await page.getByLabel('Что изменить?').fill('Сделай изгородь ниже')
  await page.getByRole('button',{name:exit,exact:true}).click()
  await expect(page.getByRole('heading',{name:'Что делаем дальше?'})).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading',{name:'Что делаем дальше?'})).toBeVisible()
  expect(state.read().answers).toEqual(state.original.answers)
  expect(state.read().scene_asset_id).toBe(sceneId)
  expect(state.read().generation_ids).toEqual(state.original.generation_ids)
  expect(state.read().region_mode).toBeNull()
  expect(state.mutations.every(item=>item.startsWith('PUT ')&&item.endsWith('/questionnaire-session'))).toBe(true)
})

test('hedge edit identifies its target and permits explicit switch to house without paying',async({page})=>{
  const state=await setup(page)
  await page.getByRole('button',{name:'Изменить: Живая изгородь',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Изменить: Живая изгородь'})).toBeVisible()
  await expect(page.getByLabel('Что изменить?')).not.toHaveAttribute('placeholder',/крыш/)
  await page.getByLabel('Что изменить?').fill('Замени цвет крыши на темный')
  await page.getByLabel('Редактируемый объект').selectOption('eskez-doma')
  await expect(page.getByRole('heading',{name:'Изменить: Дом, фасад'})).toBeVisible()
  await expect(page.getByLabel('Что изменить?')).toHaveValue('Замени цвет крыши на темный')
  await expect(page.getByRole('button',{name:/Подтвердить область/})).toBeDisabled()
  expect(state.read().region_object).toBe('eskez-doma')
  expect(state.read().answers).toEqual(state.original.answers)
  expect(state.mutations.every(item=>item.startsWith('PUT '))).toBe(true)
})

test('old stuck accepted questionnaire can return directly to accepted scene',async({page})=>{
  const state=await setup(page,true)
  await expect(page.getByRole('heading',{name:'Параметры: Живая изгородь'})).toBeVisible()
  await page.getByRole('button',{name:'Назад',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Что делаем дальше?'})).toBeVisible()
  expect(state.read().answers).toEqual(state.original.answers)
})

test('failed cancel remains editable and does not pretend the session was saved',async({page})=>{
  const state=await setup(page)
  await page.getByRole('button',{name:'Изменить: Живая изгородь',exact:true}).click()
  state.failSave()
  await page.getByRole('button',{name:'Назад',exact:true}).click()
  await expect(page.locator('.banner-error')).toBeVisible()
  await expect(page.getByRole('heading',{name:'Изменить: Живая изгородь'})).toBeVisible()
  expect(state.read().region_object).toBe('izgorod')
})


test('server target mismatch stays on edit form and can be corrected without losing the request',async({page})=>{
  const state=await setup(page)
  let rejectedRequests=0
  await page.route('**/questionnaire-generation',async route=>{
    rejectedRequests++
    await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({type:'questionnaire_edit_target_mismatch',detail:'Выбран другой объект'})})
  })
  await page.getByRole('button',{name:'Изменить: Живая изгородь',exact:true}).click()
  await page.getByLabel('Что изменить?').fill('Замени цвет крыши на темный')
  const box=await page.locator('.region-canvas').boundingBox()
  expect(box).not.toBeNull()
  await page.mouse.move(box!.x+box!.width*0.2,box!.y+box!.height*0.2)
  await page.mouse.down()
  await page.mouse.move(box!.x+box!.width*0.6,box!.y+box!.height*0.6)
  await page.mouse.up()
  await page.getByRole('button',{name:/Подтвердить область/}).click()
  await expect(page.getByText(/Сейчас выбрана живая изгородь, а запрос относится к крыше/)).toBeVisible()
  await expect(page.getByRole('heading',{name:'Изменить: Живая изгородь'})).toBeVisible()
  expect(state.read().generation_ids).toEqual(state.original.generation_ids)
  await page.getByLabel('Редактируемый объект').selectOption('eskez-doma')
  await expect(page.getByLabel('Что изменить?')).toHaveValue('Замени цвет крыши на темный')
  await expect(page.getByRole('button',{name:/Подтвердить область/})).toBeDisabled()
  await expect(page.locator('.region-selection')).toHaveCount(0)
  expect(rejectedRequests).toBe(1)
})
