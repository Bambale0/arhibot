import json

import pytest

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def initial(*, photo=False, total=200, floors='2 этажа', objects=None):
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog['version'],
        selected_objects=objects or ['eskez-doma', 'basseyn', 'izgorod', 'gazon'],
        plot_area_sotkas=10,
        initial_concept_mode=True,
        answers={'eskez-doma': {'2': 'Г-образная', '3': total, '4': floors},
                 'izgorod': {'1': 'Цветущая', '3': 'Весь периметр внутри забора'}},
    )
    return build_initial_concept_prompt(catalog, session, input_asset_present=photo)


def parsed(prompt):
    return json.JSONDecoder().raw_decode(prompt.split('STRUCTURED_SPEC:\n', 1)[1])[0]


@pytest.mark.parametrize('total,floors,share,remaining', [(200, '2 этажа', .1, '90.0%'), (60, '1 этаж', .06, '94.0%')])
def test_boundary_priority_preserves_camera_and_computed_ground_scale(total, floors, share, remaining):
    canonical = initial(total=total, floors=floors)
    original = parsed(canonical)
    provider = build_visual_fidelity_prompt(canonical)
    spec = parsed(provider)
    priority = provider.split('AUROOM_INITIAL_CONCEPT_V1', 1)[0]
    assert spec['site_scale']['ground_footprint_contract']['target_share'] == pytest.approx(share)
    assert spec['camera'] == original['camera']
    assert 'OPEN GAP' in priority and 'no gate' in priority
    assert 'measuring grid' in priority
    assert parsed(canonical) == original
    assert 'elevation_degrees' not in original['camera']


def test_existing_photo_boundaries_and_single_object_camera_are_not_overridden():
    photo = initial(photo=True)
    assert parsed(build_visual_fidelity_prompt(photo))['camera'] == parsed(photo)['camera']
    assert not build_visual_fidelity_prompt(photo).startswith('MANDATORY COMPOSITION')
    hero = initial(objects=['eskez-doma'])
    assert parsed(build_visual_fidelity_prompt(hero))['camera'] == parsed(hero)['camera']


def test_selected_gate_is_not_forbidden_by_priority():
    provider = build_visual_fidelity_prompt(initial(objects=['eskez-doma', 'izgorod', 'vorota']))
    assert 'OPEN GAP' not in provider.split('AUROOM_INITIAL_CONCEPT_V1', 1)[0]
