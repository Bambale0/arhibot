"""Regression briefs from rejected visual acceptance, with no customer identifiers."""
import json

import pytest

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def initial(answers, *, photo=False):
    catalog = build_catalog()
    state = DesignSession(
        catalog_version=catalog['version'], selected_objects=list(answers),
        initial_concept_mode=True, plot_area_sotkas=10, answers=answers,
    )
    canonical = build_initial_concept_prompt(catalog, state, input_asset_present=photo)
    result = build_visual_fidelity_prompt(canonical)
    parsed = json.JSONDecoder().raw_decode(result.split('STRUCTURED_SPEC:\n', 1)[1])[0]
    assert canonical == build_initial_concept_prompt(catalog, state, input_asset_present=photo)
    return result, parsed


@pytest.mark.parametrize('photo', [False, True])
@pytest.mark.parametrize('floors,full,attic', [
    ('1 этаж', 1, False), ('1 этаж с мансардой', 1, True),
    ('2 этажа', 2, False), ('2 этажа с мансардой', 2, True), ('3 этажа', 3, False),
])
def test_full_storeys_are_separate_from_attic_basement_and_double_height(photo, floors, full, attic):
    text, spec = initial({'eskez-doma': {
        '2': 'Несколько сдвинутых объёмов', '3': 200, '4': floors,
        '5': 'Да, полноценный подвал', '11': ['Второй свет в гостиной'],
    }}, photo=photo)
    contract = spec['task']['objects'][0]['selected_visual_constraints']
    assert contract['full_storeys'] == full
    assert contract['attic_above_full_storeys'] is attic
    assert f'exactly {full} full above-ground storeys' in text
    assert 'double-height room is a void within' in text
    assert 'basement does not replace' in text
    if attic:
        assert 'ADDITIONAL roof-space level' in text


@pytest.mark.parametrize('roof', ['Двускатная', 'Односкатная', 'Ломаная мансардная'])
def test_roof_geometry_is_explicit_even_when_style_suggests_another_roof(roof):
    text, spec = initial({'eskez-doma': {'1': 'Классика', '7': roof}})
    assert spec['task']['objects'][0]['selected_visual_constraints']['roof'] == roof
    assert 'Selected roof:' in text
    if roof == 'Двускатная':
        assert 'No hipped ends' in text


def test_house_no_fireplace_does_not_suppress_selected_bath_stove():
    text, spec = initial({'eskez-doma': {'11б': 'Нет'}, 'banya': {'5': 'Дровяная, с трубой'}})
    objects = {o['object_key']: o for o in spec['task']['objects']}
    assert objects['eskez-doma']['selected_visual_constraints']['chimney'] == 'not_requested'
    assert objects['banya']['selected_visual_constraints']['chimney'] == 'required'
    assert 'Object eskez-doma:' in text
    assert 'Do not invent a fireplace chimney on this object' in text


@pytest.mark.parametrize('cover,relation', [('Навес', 'above_water'), ('Павильон', 'encloses_water'), ('Открытый', 'none')])
def test_pool_cover_belongs_to_water_not_adjacent_seating(cover, relation):
    text, spec = initial({'basseyn': {'1': 'Выкопанный', '2': 'Овал', '4': cover}})
    contract = spec['task']['objects'][0]['selected_visual_constraints']
    assert contract['pool_cover_relation'] == relation
    assert contract['pool_ground_relation'] == 'in_ground'
    assert 'rim at the surrounding ground/deck level' in text
    if cover != 'Открытый':
        assert 'not an adjacent seating gazebo' in text
    assert 'continuous curved oval' in text


def test_visible_finish_wins_over_underlying_log_structural_system():
    text, spec = initial({'eskez-doma': {'8': ['Дерево, планкен', 'Камень'], '10': 'Бревно'}})
    assert spec['task']['objects'][0]['selected_visual_constraints']['facade_finishes'] == ['Дерево, планкен', 'Камень']
    assert 'flat planken boards, not exposed round logs' in text
    assert 'underlying wall construction' in text


@pytest.mark.parametrize('schema,operation', [('auroom.render_spec.v1', 'remove_object'), ('auroom.render_spec.v1', 'refine')])
def test_non_initial_prompt_does_not_reapply_initial_selections(schema, operation):
    payload = {'schema': schema, 'task': {'operation': operation, 'object_key': 'eskez-doma'},
               'questionnaire_constraints': [{'question': 'Сколько этажей?', 'answer': '2 этажа с мансардой'}]}
    canonical = 'AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n' + json.dumps(payload)
    assert 'selected_visual_constraints' not in build_visual_fidelity_prompt(canonical)


@pytest.mark.parametrize('operation', ['add', 'refine', 'remove'])
def test_local_pool_attachment_is_scoped_to_new_pool(operation):
    from app.localized_edit import local_edit_prompt
    payload = {'task': {'object_key': 'basseyn'}, 'questionnaire_constraints': [
        {'question': 'Какой бассейн?', 'answer': 'Выкопанный'},
        {'question': 'Чем накрыть?', 'answer': 'Навес'},
    ]}
    prompt = 'AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n' + json.dumps(payload)
    geometry = {'version': 'local-tile.v1', 'base_size': [100, 100], 'box': [20, 20, 80, 80],
                'aspect_ratio': '1:1', 'operation': operation}
    output = local_edit_prompt(prompt, geometry, {'x': .25, 'y': .25, 'width': .5, 'height': .5}, [])
    assert ('not an adjacent seating gazebo' in output) is (operation == 'add')


@pytest.mark.parametrize('photo', [False, True])
def test_new_boundary_prohibition_does_not_erase_photo_context(photo):
    text, spec = initial({'eskez-doma': {'4': '2 этажа'}, 'basseyn': {}, 'lavochka': {}}, photo=photo)
    assert ('No newly invented fence, gate, wicket or entrance posts' in text) is (not photo)
    if photo:
        assert 'Keep unrelated site context' in text


def test_explicit_gate_selection_keeps_gate_allowed():
    text, _ = initial({'eskez-doma': {}, 'vorota': {}, 'izgorod': {}})
    assert 'No newly invented fence, gate, wicket or entrance posts' not in text


def test_missing_selections_do_not_acquire_invented_geometry():
    _, spec = initial({'eskez-doma': {}})
    contract = spec['task']['objects'][0]['selected_visual_constraints']
    assert 'full_storeys' not in contract
    assert 'roof' not in contract
    assert 'facade_finishes' not in contract


def test_explicit_bath_log_accents_are_not_negated_by_primary_planken():
    text, _ = initial({'banya': {'9': ['Дерево, планкен', 'Бревно / брус']}})
    assert 'not exposed round logs' not in text
    assert 'Бревно / брус' in text
