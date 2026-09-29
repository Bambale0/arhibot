import { expect, test } from '@playwright/test'
import { createDesignSession, type QuestionnaireCatalog } from '../../src/questionnaireTypes'
import type { Asset, Generation, Project } from '../../src/types'

for (const pausedByProvider of [false, true]) {
test(`initial concept resumes ${pausedByProvider ? 'paused provider task' : 'polling timeout'} without another paid request`, async ({ page }) => {
  const now = '2026-09-27T10:00:00Z'
  const projectId = '33333333-3333-4333-8333-333333333333'
  const generationId = '44444444-4444-4444-8444-444444444441'
  const catalog:QuestionnaireCatalog = {
    version:'initial-recovery', application_key:'zayavka', source_rules:[],
    sections:[{key:'furniture', title:'Мебель', object_keys:['lavochka']}],
    questionnaires:[{key:'lavochka', title:'Лавочка', source_file:'fixture', order:0, scene_policy:{}, questions:[{
      id:'1', text:'Какая лавочка?', kind:'single', options:['Деревянная'], required:true,
      skip_default:null, skip_condition:null, help:null, field_hint:null, placeholder:null,
      max_selections:null, phase:'pre_render', condition:null, option_rules:{}, edit_targets:{},
    }]}],
  }
  let session = {
    ...createDesignSession(catalog.version, ['lavochka']),
    plot_area_sotkas:8, source_step_completed:true, current_object:null,
    survey_completed_objects:['lavochka'], initial_generation_id:generationId,
    answers:{lavochka:{'1':'Деревянная'}},
  }
  const project:Project = {
    id:projectId, name:'Общая концепция', description:null, status:'active',
    context:{questionnaire_draft:false, plot_area_m2:800, design_session:session},
    created_at:now, updated_at:now,
  }
  const output:Asset = {
    id:'55555555-5555-4555-8555-555555555551', project_id:projectId,
    type:'image', purpose:'generation_output', original_filename:'concept.svg',
    mime_type:'image/svg+xml', size_bytes:100, width:640, height:480, created_at:now,
    url:'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"></svg>'),
  }
  const generation:Generation = {
    id:generationId, project_id:projectId, input_asset_id:null, output_asset:null,
    type:'master_plan', status:'processing', credits_charged:1, model_name:'mock',
    fallback_used:false, composition_mode:'replace', edit_region:null, protected_regions:[],
    error:pausedByProvider ? 'Проверяем ранее созданную задачу. Повторная оплата не нужна.' : null, created_at:now, updated_at:now, started_at:now, completed_at:null,
  }
  const mutations:string[] = []
  const requestedGenerationIds:string[] = []
  await page.clock.setFixedTime(now)
  await page.addInitScript(() => sessionStorage.setItem('auroom.access_token', 'e2e'))
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    if (method !== 'GET') mutations.push(`${method} ${path}`)
    let body:unknown
    let status = 200
    if (path.endsWith('/me')) body = {
      id:'11111111-1111-4111-8111-111111111111', display_name:'Проверка', status:'active',
      role:'user', credits_balance:10, created_at:now, updated_at:now, capabilities:{can_generate:true},
    }
    else if (path.endsWith('/projects')) body = {items:[], next_cursor:null, has_more:false}
    else if (path.endsWith(`/projects/${projectId}`)) body = project
    else if (path.endsWith('/questionnaires')) body = catalog
    else if (path.endsWith('/questionnaire-generation-cost')) body = {
      generation_type:'master_plan', initial_credits:1, credits:1, initial_offer_available:true, is_available:true,
    }
    else if (path.endsWith('/questionnaire-session') && method === 'GET') body = {session}
    else if (path.includes('/questionnaire-generation/') && method === 'GET') {
      requestedGenerationIds.push(path.split('/').at(-1)!)
      body = generation
    }
    else if (path.endsWith('/questionnaire-initial-accept') && method === 'POST') {
      expect(generation.status).toBe('completed')
      session = {...session, initial_concept_accepted:true, accepted_objects:['lavochka'],
        generation_ids:{lavochka:generationId}, scene_asset_id:output.id, scene_generation_id:generationId}
      project.context.design_session = session
      body = {session}
    }
    else if (path.endsWith(`/assets/${output.id}`)) body = output
    else if (path.endsWith('/ideas')) body = []
    else if (path.includes('/ideas/mine/')) body = null
    else { status = 404; body = {type:'mock_unhandled', detail:`${method} ${path}`} }
    await route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)})
  })

  await page.goto(`/?project=${projectId}`)
  if (pausedByProvider) {
    await expect(page.getByText(generation.error!)).toBeVisible()
  } else {
    await expect(page.getByText('Создаём весь участок одной генерацией…')).toBeVisible()
    await page.clock.setFixedTime(new Date(Date.parse(now) + 7 * 60 * 1000))
    await expect(page.getByText('Генерация ещё выполняется. Задача сохранена — проверьте результат чуть позже.')).toBeVisible()
  }

  const check = page.getByRole('button', {name:'Проверить генерацию', exact:true})
  await expect(check).toBeEnabled()
  generation.error = null
  await check.click()
  await expect(check).toBeDisabled()
  generation.status = 'completed'
  generation.output_asset = output
  generation.completed_at = now
  await expect(page.getByRole('button', {name:'Принять концепцию', exact:true})).toBeVisible()
  await expect(page.getByAltText('Общая концепция участка')).toBeVisible()
  expect(requestedGenerationIds.length).toBeGreaterThanOrEqual(3)
  expect(new Set(requestedGenerationIds)).toEqual(new Set([generationId]))
  expect(session.initial_generation_id).toBe(generationId)
  expect(mutations).toEqual([])

  await page.getByRole('button', {name:'Принять концепцию', exact:true}).click()
  await expect(page.getByRole('heading', {name:'Что делаем дальше?'})).toBeVisible()
  expect(session.initial_concept_accepted).toBe(true)
  expect(session.initial_generation_id).toBe(generationId)
  expect(mutations).toEqual([`POST /api/v1/projects/${projectId}/questionnaire-initial-accept`])
})

}
