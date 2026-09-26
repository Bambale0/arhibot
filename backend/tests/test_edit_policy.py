from app.services.edit_policy import EditDomain, EditIntent, build_edit_policy


def test_facade_finish_is_allowed_exterior_edit() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["8"],
        review_comment="Сделай фасад светлее.",
    )

    assert policy.allow_generation is True
    assert policy.domain == EditDomain.EXTERIOR
    assert policy.intent == EditIntent.FACADE_FINISH
    assert policy.preserve_visible_interior is True
    assert policy.allow_interior_reconstruction is False


def test_roof_material_change_keeps_structural_link_checks() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["7"],
        review_comment="Сделай кровлю темнее, материал — фальц.",
    )

    assert policy.intent == EditIntent.ROOF_FINISH
    assert "fireplace_chimney" in policy.structural_links
    assert "structural_link_consistency" in policy.quality_checks
    assert "structural_link_consistency" in policy.deferred_quality_checks
    assert "structural_link_consistency" not in policy.enforced_quality_checks
    assert policy.scene_analysis_enforced is False
    assert policy.allow_chimney_relocation is False


def test_roof_geometry_change_is_structural_sensitive() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["7"],
        review_comment="Сделай крышу двускатной.",
    )

    assert policy.intent == EditIntent.ROOF_GEOMETRY
    assert policy.scene_analysis_required is True
    assert policy.allow_fireplace_relocation is False


def test_interior_only_comment_is_blocked() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=[],
        review_comment="Переставь диван и сделай интерьер красивее.",
    )

    assert policy.allow_generation is False
    assert policy.domain == EditDomain.INTERIOR
    assert policy.intent == EditIntent.INTERIOR
    assert policy.interior_request_detected is True


def test_mixed_comment_keeps_only_exterior_request() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["8"],
        review_comment="Сделай фасад светлее. Переставь диван внутри.",
    )

    assert policy.allow_generation is True
    assert policy.domain == EditDomain.MIXED
    assert policy.interior_request_detected is True
    assert "фасад" in policy.sanitized_comment.lower()
    assert "диван" not in policy.sanitized_comment.lower()


def test_fireplace_relocation_is_blocked_in_exterior_mode() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["11б"],
        review_comment="Перенеси камин левее к окну.",
    )

    assert policy.allow_generation is False
    assert policy.intent == EditIntent.INTERIOR
    assert policy.allow_fireplace_relocation is False


def test_chimney_finish_is_allowed_but_anchor_stays_locked() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["11б"],
        review_comment="Сделай трубу кирпичной.",
    )

    assert policy.allow_generation is True
    assert policy.intent == EditIntent.CHIMNEY_FINISH
    assert policy.allow_chimney_relocation is False
    assert "fireplace_chimney" in policy.structural_links


def test_chimney_move_is_structural_geometry_edit() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["11б"],
        review_comment="Перенеси трубу на другой скат.",
    )

    assert policy.allow_generation is True
    assert policy.intent == EditIntent.CHIMNEY_GEOMETRY
    assert policy.scene_analysis_required is True
    assert "structural_link_consistency" in policy.quality_checks

def test_layout_only_comment_is_blocked() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=[],
        review_comment="Измени планировку.",
    )

    assert policy.allow_generation is False
    assert policy.domain == EditDomain.INTERIOR
    assert policy.sanitized_comment == ""


def test_mixed_comment_removes_kitchen_inside_clause() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["8"],
        review_comment="Сделай фасад светлее, кухню внутри оформи современнее.",
    )

    assert policy.allow_generation is True
    assert policy.domain == EditDomain.MIXED
    assert policy.sanitized_comment == "Сделай фасад светлее"
    assert "кухн" not in policy.sanitized_comment.casefold()



def test_fireplace_chimney_finish_phrase_is_not_misclassified_as_interior_fireplace() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["11б"],
        review_comment="Сделай каминную трубу кирпичной.",
    )

    assert policy.allow_generation is True
    assert policy.domain == EditDomain.EXTERIOR
    assert policy.intent == EditIntent.CHIMNEY_FINISH
    assert policy.sanitized_comment == "Сделай каминную трубу кирпичной."


def test_negative_fireplace_lock_instruction_is_not_blocked() -> None:
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["7"],
        review_comment="Сделай крышу темнее и не изменяй камин.",
    )

    assert policy.allow_generation is True
    assert policy.intent == EditIntent.ROOF_FINISH
    assert "не изменяй камин" in policy.sanitized_comment.casefold()
    assert policy.allow_fireplace_relocation is False
