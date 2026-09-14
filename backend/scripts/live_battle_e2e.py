from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import dataclass
from uuid import UUID

from app.core.config import get_settings
from app.db.models.generations import Generation
from app.db.models.users import AuthIdentity, User
from app.db.session import get_session_factory
from app.domain.users.enums import AuthProvider, UserRole, UserStatus
from app.schemas.admin import IdeaPublicationCreate
from app.schemas.questionnaires import DesignSession, QuestionnaireProjectStartRequest
from app.services.generation_service import build_generation_service
from app.services.idea_service import IdeaService
from app.services.questionnaire_project_service import QuestionnaireProjectService
from app.services.questionnaire_service import QuestionnaireService


@dataclass(frozen=True)
class Scenario:
    objects: tuple[str, ...]
    plot_area_sotkas: int


SCENARIOS = (
    Scenario(("eskez-doma",), 4),
    Scenario(("eskez-doma", "banya"), 8),
    Scenario(("eskez-doma", "garazh", "besedka"), 12),
    Scenario(("banya", "letnyaya-kuhnya"), 6),
    Scenario(("garazh", "naves", "teplica", "besedka"), 15),
)


def _condition_ok(condition: dict | None, answers: dict, house_reference: bool) -> bool:
    if not condition:
        return True
    operator = condition.get("operator")
    if operator == "house_accepted":
        return house_reference
    if operator == "all":
        return all(
            _condition_ok(item, answers, house_reference)
            for item in condition.get("conditions", [])
        )
    if operator == "any":
        return any(
            _condition_ok(item, answers, house_reference)
            for item in condition.get("conditions", [])
        )

    answer = answers.get(condition.get("question_id"))
    value = condition.get("value")
    if operator == "eq":
        return answer == value
    if operator == "neq":
        return answer != value
    if operator == "in":
        return isinstance(answer, str) and isinstance(value, list) and answer in value
    if operator == "contains":
        return isinstance(answer, list) and isinstance(value, str) and value in answer
    if operator == "starts_with":
        return isinstance(answer, str) and isinstance(value, str) and answer.startswith(value)
    if operator == "not_contains_any":
        return not isinstance(answer, list) or not isinstance(value, list) or not any(
            item in answer for item in value
        )
    if operator == "floor_option":
        if not isinstance(answer, str) or not isinstance(value, str):
            return False
        floor_answer = answer.lower()
        if value == "Первый этаж":
            return True
        if value == "Второй этаж":
            return not floor_answer.startswith("1 ")
        if value == "Третий этаж":
            return "3" in floor_answer
        if value == "Мансарда":
            return "мансард" in floor_answer
        return False
    return True


def _answers_for(definition: dict, *, house_reference: bool, rng: random.Random) -> dict:
    answers: dict = {}
    for question in definition["questions"]:
        if question["phase"] != "pre_render":
            continue
        if not _condition_ok(question.get("condition"), answers, house_reference):
            continue

        skip_default = question.get("skip_default")
        if skip_default is not None and _condition_ok(
            question.get("skip_condition"), answers, house_reference
        ):
            answers[question["id"]] = skip_default
            continue

        kind = question["kind"]
        if kind == "number":
            answers[question["id"]] = int(question.get("min_value") or 1)
            continue
        if kind == "text":
            answers[question["id"]] = f"Battle E2E {question['id']}"
            continue

        options = [
            option
            for option in question.get("options", [])
            if _condition_ok(
                question.get("option_rules", {}).get(option),
                answers,
                house_reference,
            )
        ]
        if kind == "multi":
            answers[question["id"]] = rng.sample(options, 1) if options else []
            continue
        if not options:
            raise RuntimeError(
                f"No valid option for {definition['key']}.{question['id']}"
            )
        answers[question["id"]] = rng.choice(options)
    return answers


async def _create_battle_user(index: int) -> User:
    async with get_session_factory()() as session:
        user = User(
            display_name=f"Battle E2E {index}",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
            credits_balance=0,
        )
        session.add(user)
        await session.flush()
        session.add_all(
            [
                AuthIdentity(
                    user_id=user.id,
                    provider=AuthProvider.EMAIL,
                    provider_user_id=f"battle-e2e-{index}-{str(user.id)[:8]}@example.com",
                ),
                AuthIdentity(
                    user_id=user.id,
                    provider=AuthProvider.TELEGRAM,
                    provider_user_id=str(880_000_000 + index),
                ),
            ]
        )
        await session.commit()
        await session.refresh(user)
        return user


async def _wait_for_generation(generation_id: UUID, timeout_seconds: int) -> Generation:
    elapsed = 0
    while elapsed < timeout_seconds:
        await asyncio.sleep(4)
        elapsed += 4
        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            if generation is None:
                raise RuntimeError(f"Generation disappeared: {generation_id}")
            if generation.status.value in {"completed", "failed", "cancelled"}:
                return generation
    raise TimeoutError(f"Generation did not finish in {timeout_seconds}s: {generation_id}")


async def _run_scenario(index: int, scenario: Scenario, rng: random.Random) -> dict:
    settings = get_settings()
    user = await _create_battle_user(index)

    async with get_session_factory()() as session:
        user = await session.get(User, user.id)
        assert user is not None
        questionnaire = QuestionnaireService(session)
        catalog = await questionnaire.catalog()
        definitions = {item["key"]: item for item in catalog["questionnaires"]}

        project = await QuestionnaireProjectService(session).start(
            user,
            QuestionnaireProjectStartRequest(
                selected_objects=list(scenario.objects),
                plot_area_sotkas=scenario.plot_area_sotkas,
            ),
        )
        project_id = project.id
        design_session = DesignSession.model_validate(project.context.design_session)
        design_session.source_step_completed = True
        saved_source = await QuestionnaireProjectService(session).save_source_if_draft(
            user, project_id, design_session
        )
        if saved_source is None:
            raise RuntimeError("Questionnaire draft source step was not saved")
        design_session = saved_source

        house_reference = "eskez-doma" in scenario.objects
        design_session.answers = {
            object_key: _answers_for(
                definitions[object_key],
                house_reference=house_reference,
                rng=rng,
            )
            for object_key in scenario.objects
        }
        design_session.survey_completed_objects = list(scenario.objects)
        design_session.current_object = None
        design_session.current_question_id = None
        design_session = await questionnaire.save_session(
            user, project_id, design_session
        )

        generation_payload, expected_session, object_key = (
            await questionnaire.build_generation_request(user, project_id)
        )

        def bind_generation(generation: Generation, project_model) -> None:
            questionnaire.bind_generation_before_commit(
                project_model,
                expected_session=expected_session,
                object_key=object_key,
                generation_id=generation.id,
            )

        generation = await build_generation_service(session, settings).create(
            user,
            generation_payload,
            before_commit=bind_generation,
        )
        generation_id = generation.id

    generation = await _wait_for_generation(generation_id, timeout_seconds=420)
    if generation.status.value != "completed":
        return {
            "scenario": index,
            "status": generation.status.value,
            "project_id": str(project_id),
            "generation_id": str(generation_id),
            "model_name": generation.model_name,
            "fallback_used": generation.fallback_used,
            "objects": list(scenario.objects),
            "plot_area_sotkas": scenario.plot_area_sotkas,
            "error": generation.error_message,
        }

    async with get_session_factory()() as session:
        user = await session.get(User, user.id)
        assert user is not None
        questionnaire = QuestionnaireService(session)
        design_session = await questionnaire.accept_initial_concept(user, project_id)
        design_session.answers["zayavka"] = {
            "20": rng.choice(["Да, есть", "Пока выбираю", "Пока нет"]),
            "21": rng.choice(
                ["до 5 млн", "5–10 млн", "10–20 млн", "20–40 млн", "40 млн и больше"]
            ),
            "22": rng.choice(
                [
                    "В ближайшие 3 месяца",
                    "В течение полугода",
                    "В течение года",
                    "Просто интересуюсь",
                ]
            ),
            "23": f"Battle E2E {index}",
            "24": f"@battle_e2e_{index}",
            "25": True,
        }
        _, application = await questionnaire.submit_application(
            user, project_id, design_session
        )
        idea = await IdeaService(session, settings).publish(
            user, IdeaPublicationCreate(generation_id=generation_id)
        )

    return {
        "scenario": index,
        "status": "completed",
        "project_id": str(project_id),
        "generation_id": str(generation_id),
        "application_id": str(application.id),
        "idea_id": str(idea.id),
        "model_name": generation.model_name,
        "fallback_used": generation.fallback_used,
        "objects": list(scenario.objects),
        "plot_area_sotkas": scenario.plot_area_sotkas,
    }


async def _main(args: argparse.Namespace) -> int:
    settings = get_settings()
    plan = [
        {
            "scenario": index,
            "objects": list(item.objects),
            "plot_area_sotkas": item.plot_area_sotkas,
        }
        for index, item in enumerate(SCENARIOS[: args.scenarios], 1)
    ]
    if not args.apply:
        print(json.dumps({"environment": settings.app_env, "plan": plan}, ensure_ascii=False))
        return 0
    if not args.confirm_live_provider_cost:
        raise SystemExit("Refusing live Nexus calls without --confirm-live-provider-cost")

    rng = random.Random(args.seed)
    results = []
    for index, scenario in enumerate(SCENARIOS[: args.scenarios], 1):
        result = await _run_scenario(index, scenario, rng)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    print("FINAL " + json.dumps(results, ensure_ascii=False), flush=True)
    return 0 if all(item["status"] == "completed" for item in results) else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full live questionnaire -> Nexus -> application -> Ideas battle scenarios."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-live-provider-cost", action="store_true")
    parser.add_argument("--scenarios", type=int, choices=range(1, 6), default=5)
    parser.add_argument("--seed", type=int, default=20260914)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(parse_args())))
