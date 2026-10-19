"""
Assignment 3 tools: each tool on its own, the argument validator, the orchestrator's
timeout / error paths, and one full tool turn over the WebSocket with a fake LLM.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import orchestrator
from app.llm_engine import GenerationStats
from app.main import app
from app.tools import TOOLS, nutrition, workout_schedule
from app.tools.base import Tool, ToolContext, ToolError, validate_args
from app.tools.fitness_metrics import run as metrics
from app.tools.json_store import JsonStore

CTX = ToolContext(user_id="test-user")


# ---------------------------------------------------------------- calculate_fitness_metrics

async def test_bmi():
    assert await metrics({"metric": "bmi", "weight_kg": 80, "height_cm": 180}, CTX) == {
        "bmi": 24.7, "category": "normal weight"}


async def test_daily_calories_mifflin_st_jeor():
    result = await metrics({"metric": "daily_calories", "weight_kg": 80, "height_cm": 180,
                            "age": 25, "sex": "male", "activity_level": "sedentary"}, CTX)
    assert result["bmr_kcal"] == 1805  # 800 + 1125 - 125 + 5
    assert result["maintenance_kcal"] == 2166  # x 1.2


async def test_one_rep_max_epley():
    assert (await metrics({"metric": "one_rep_max", "lifted_kg": 100, "reps": 5}, CTX))["one_rep_max_kg"] == 116.7


async def test_missing_numbers_raise_a_friendly_tool_error():
    with pytest.raises(ToolError, match="height_cm"):
        await metrics({"metric": "bmi", "weight_kg": 80}, CTX)


# ---------------------------------------------------------------- lookup_nutrition

def test_food_tables_cover_desi_dishes_and_thousands_of_usda_foods():
    assert len({f["name"] for f in nutrition._curated().values()}) >= 55  # incl. karahi, nihari, lassi
    assert len(nutrition._usda()) > 13000  # USDA FoodData Central (built by data/build_food_db.py)


async def test_lookup_by_alias_and_servings():
    result = await nutrition.run({"food": "eggs", "servings": 2}, CTX)
    assert result["food"] == "egg" and result["protein_g"] == 13.0 and result["calories"] == 155


async def test_lookup_tolerates_a_typo_and_scales_grams():
    result = await nutrition.run({"food": "chiken breast", "grams": 200}, CTX)
    assert result["food"] == "chicken breast" and result["protein_g"] == 62.0


async def test_unknown_food():
    with pytest.raises(ToolError, match="not in my nutrition database"):
        await nutrition.run({"food": "zzqx blorp"}, CTX)


async def test_usda_dishes_with_portions():
    """Live-demo misses: pizza slice, chocolate cake, burger -- now found, with a real portion."""
    pizza = await nutrition.run({"food": "pizza", "portion": "slice"}, CTX)
    assert pizza["food"].startswith("Pizza") and "piece" in pizza["totals_for"]
    assert 150 < pizza["calories"] < 600 and {"protein_g", "carbs_g", "fat_g"} <= set(pizza)
    burger = await nutrition.run({"food": "beef burger"}, CTX)  # no name has both words
    assert "Hamburger" in burger["food"]
    cola = await nutrition.run({"food": "cola", "portion": "can"}, CTX)
    assert "diet" not in cola["food"].lower() and cola["calories"] > 50  # not the diet version


async def test_desi_dishes_and_aliases():
    karahi = await nutrition.run({"food": "chicken karahi"}, CTX)
    assert karahi["food"] == "chicken karahi" and karahi["source"] == "Zor food table"
    assert (await nutrition.run({"food": "doodh patti"}, CTX))["food"] == "chai"


# ---------------------------------------------------------------- workout_schedule

@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workout_schedule, "store", JsonStore(tmp_path / "workouts.json"))


async def test_add_list_delete_workouts(temp_store):
    run = workout_schedule.run
    await run({"action": "add", "day": "wed", "workout": "leg day", "duration_min": 60}, CTX)
    await run({"action": "add", "day": "Monday", "workout": "5 km run"}, CTX)
    listed = await run({"action": "list"}, CTX)
    assert [w["day"] for w in listed["workouts"]] == ["Monday", "Wednesday"]  # sorted by weekday
    deleted = await run({"action": "delete", "day": "Wednesday"}, CTX)
    assert deleted["deleted"][0]["workout"] == "leg day"
    assert (await run({"action": "list"}, CTX))["count"] == 1


async def test_schedules_are_per_user(temp_store):
    await workout_schedule.run({"action": "add", "day": "Fri", "workout": "yoga"}, CTX)
    other = await workout_schedule.run({"action": "list"}, ToolContext(user_id="someone-else"))
    assert other["count"] == 0


async def test_concurrent_adds_are_not_lost(temp_store):
    await asyncio.gather(*[
        workout_schedule.run({"action": "add", "day": "Tue", "workout": f"set {i}"}, CTX) for i in range(10)
    ])
    assert (await workout_schedule.run({"action": "list"}, CTX))["count"] == 10


async def test_bad_day(temp_store):
    with pytest.raises(ToolError, match="not a day"):
        await workout_schedule.run({"action": "add", "day": "someday", "workout": "x"}, CTX)


# ---------------------------------------------------------------- validator + orchestrator

def test_every_tool_has_name_description_and_object_schema():
    for name, tool in TOOLS.items():
        assert tool.name == name and tool.description
        assert tool.parameters["type"] == "object" and "required" in tool.parameters


def test_validator_coerces_numeric_strings_and_drops_unknown_keys():
    schema = TOOLS["calculate_fitness_metrics"].parameters
    assert validate_args(schema, {"metric": "BMI", "weight_kg": "80", "color": "red"}) == {
        "metric": "bmi", "weight_kg": 80.0}
    with pytest.raises(ToolError, match="one of"):
        validate_args(schema, {"metric": "vo2max"})


def test_parse_tool_call():
    assert orchestrator.parse_tool_call('```json\n{"tool": "lookup_nutrition", "arguments": {"food": "egg"}}\n```') == {
        "tool": "lookup_nutrition", "arguments": {"food": "egg"}}
    assert orchestrator.parse_tool_call('{"tool": "launch_rocket", "arguments": {}}') is None
    assert orchestrator.parse_tool_call("{not json") is None


@pytest.fixture
def slow_and_broken_tools(monkeypatch):
    async def slow(args, ctx):
        await asyncio.sleep(10)

    async def broken(args, ctx):
        raise RuntimeError("disk on fire")

    empty = {"type": "object", "properties": {}, "required": []}
    monkeypatch.setitem(TOOLS, "slow_tool", Tool("slow_tool", "sleeps", empty, slow))
    monkeypatch.setitem(TOOLS, "broken_tool", Tool("broken_tool", "crashes", empty, broken))


async def test_timeout_returns_friendly_message(slow_and_broken_tools):
    ok, result = await orchestrator.run_tool("slow_tool", {}, CTX, timeout=0.1)
    assert (ok, result) == (False, orchestrator.FRIENDLY_TIMEOUT)


async def test_crash_returns_friendly_message(slow_and_broken_tools):
    assert await orchestrator.run_tool("broken_tool", {}, CTX) == (False, orchestrator.FRIENDLY_ERROR)


async def test_invalid_arguments_return_the_reason():
    ok, result = await orchestrator.run_tool("lookup_nutrition", {}, CTX)
    assert not ok and "food" in result


# ---------------------------------------------------------------- full turn over the WebSocket

class ToolCallingEngine:
    """Router call -> a JSON tool call; classifier -> OFF_TOPIC (a tool call must override it);
    main reply -> a plain answer that can only be right if it saw the TOOL RESULT."""

    def __init__(self):
        self.prompts = []

    async def generate_with_stats(self, messages, **kwargs):
        stats = GenerationStats(0.0, 0.0, 1)
        if "TOOLS:" in messages[0]["content"]:  # the router prompt
            return ('{"tool": "calculate_fitness_metrics", "arguments": '
                    '{"metric": "bmi", "weight_kg": 80, "height_cm": 180}}'), stats
        return "OFF_TOPIC", stats  # the classifier ("BMI" looks like math to it)

    async def stream_chat(self, messages):
        self.prompts.append(messages)
        assert any("TOOL RESULT" in m["content"] and "24.7" in m["content"] for m in messages)
        for token in ("Your BMI ", "is 24.7."):
            yield token

    async def check_health(self):
        return True

    async def aclose(self):
        return None


def _events_until_done(ws):
    events = []
    while not events or events[-1]["type"] not in ("done", "error"):
        events.append(ws.receive_json())
    return events


def test_tool_turn_sends_cards_then_streams_the_answer():
    with TestClient(app) as client:
        app.state.llm_engine = engine = ToolCallingEngine()
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "BMI for 80 kg, 180 cm?"})
            events = _events_until_done(ws)
            latency = ws.receive_json()  # extended clients also get per-turn timings
    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result", "token", "token", "done"]
    assert events[1]["ok"] and events[1]["result"]["bmi"] == 24.7
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Your BMI is 24.7."
    assert "sources" not in events[-1]  # a tool answer is not a document citation
    assert len(engine.prompts) == 1  # ONE streamed generation: the router did the tool choice
    assert latency["type"] == "latency" and "tool_ms" in latency


def test_old_clients_get_only_the_assignment_2_events():
    with TestClient(app) as client:
        app.state.llm_engine = ToolCallingEngine()
        with client.websocket_connect("/ws/chat") as ws:  # no ?extended=1
            ws.receive_json()
            ws.send_json({"type": "message", "content": "BMI for 80 kg, 180 cm?"})
            assert [e["type"] for e in _events_until_done(ws)] == ["token", "token", "done"]
            ws.send_json({"type": "reset"})
            assert ws.receive_json()["type"] == "session"  # no stray latency event in between


async def test_router_failure_means_no_tool():
    class Broken:
        async def generate_with_stats(self, messages, **kwargs):
            raise RuntimeError("ollama down")
    assert await orchestrator.route(Broken(), [], "BMI for 80 kg 180 cm") is None


# ---------------------------------------------------------------- user_profile (CRM bonus)

from app.tools import user_profile  # noqa: E402


@pytest.fixture
def temp_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(user_profile, "store", JsonStore(tmp_path / "profiles.json"))


async def test_profile_update_then_get(temp_profiles):
    await user_profile.run({"action": "update", "name": "Sara", "fitness_goal": "lose 5 kg"}, CTX)
    await user_profile.run({"action": "update", "injuries": "left knee"}, CTX)  # merges, keeps the rest
    got = await user_profile.run({"action": "get"}, CTX)
    assert got["profile"] == {"name": "Sara", "fitness_goal": "lose 5 kg", "injuries": "left knee"}


async def test_profile_update_without_fields_is_a_friendly_error(temp_profiles):
    with pytest.raises(ToolError, match="remember"):
        await user_profile.run({"action": "update"}, CTX)


async def test_interactions_keep_only_the_last_five_and_feed_the_greeting(temp_profiles):
    await user_profile.run({"action": "update", "name": "Ali"}, CTX)
    for i in range(7):
        await user_profile.record_interaction("test-user", f"question {i}")
    profile = await user_profile.load("test-user")
    assert [x["request"] for x in profile["interactions"]] == [f"question {i}" for i in range(2, 7)]
    assert user_profile.greeting(profile).startswith('Welcome back, Ali! Last time you asked: "question 6"')
    assert "name: Ali" in user_profile.profile_note(profile)
    assert user_profile.greeting({}) is None and user_profile.profile_note({}) is None


def test_returning_member_is_greeted_and_profile_reaches_the_prompt(temp_profiles):
    class Engine(ToolCallingEngine):
        async def generate_with_stats(self, messages, **kwargs):
            return ("NONE" if "TOOLS:" in messages[0]["content"] else "ON_TOPIC"), GenerationStats(0, 0, 1)

        async def stream_chat(self, messages):
            self.prompts.append(messages)
            yield "Sure, Sara!"

    asyncio.run(user_profile.store.update(lambda d: d.update(
        {"member-1": {"name": "Sara", "interactions": [{"at": "x", "request": "How much is Plus?"}]}})))
    with TestClient(app) as client:
        app.state.llm_engine = engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1&user_id=member-1") as ws:
            ws.receive_json()  # session
            greeting = ws.receive_json()
            assert greeting["type"] == "token" and "Welcome back, Sara" in greeting["content"]
            assert "How much is Plus?" in greeting["content"] and ws.receive_json()["type"] == "done"
            ws.send_json({"type": "message", "content": "Yes, tell me more"})
            _events_until_done(ws)
    prompt = engine.prompts[0]
    assert any("MEMBER PROFILE" in m["content"] and "Sara" in m["content"] for m in prompt)
    assert prompt[1] == {"role": "assistant", "content": greeting["content"]}  # greeting is in history
    log = asyncio.run(user_profile.load("member-1"))["interactions"]
    assert log[-1]["request"] == "Yes, tell me more"  # this visit was recorded too


async def test_only_a_typed_name_becomes_a_speech_hint(temp_profiles):
    """Regression (live demo): a misheard spoken name fed back to Whisper locked the mistake in."""
    spoken = ToolContext(user_id="u1", spoken=True)
    await user_profile.run({"action": "update", "name": "Saros"}, spoken)
    assert user_profile.member_name_hint(await user_profile.load("u1")) is None
    await user_profile.run({"action": "update", "name": "Sarosh"}, ToolContext(user_id="u1"))  # typed
    assert user_profile.member_name_hint(await user_profile.load("u1")) == "Sarosh"


async def test_spoken_near_miss_keeps_the_typed_name_but_a_new_name_replaces_it(temp_profiles):
    await user_profile.run({"action": "update", "name": "Sarosh"}, ToolContext(user_id="u2"))  # typed
    spoken = ToolContext(user_id="u2", spoken=True)
    await user_profile.run({"action": "update", "name": "Saros"}, spoken)  # misheard
    assert (await user_profile.load("u2"))["name"] == "Sarosh"
    await user_profile.run({"action": "update", "name": "Abdullah"}, spoken)  # really a new name
    assert (await user_profile.load("u2"))["name"] == "Abdullah"



async def test_height_in_feet_is_converted_and_nonsense_is_rejected():
    """Live demo: "6 foot" became height_cm=720 and BMI 2.1 'underweight'."""
    assert (await metrics({"metric": "bmi", "weight_kg": 90, "height_ft": 6, "height_in": 1}, CTX))["bmi"] == 26.2
    with pytest.raises(ToolError, match="doesn't look right"):
        await metrics({"metric": "bmi", "weight_kg": 110, "height_cm": 720}, CTX)


def test_feet_and_pounds_are_read_from_the_members_words():
    call = {"tool": "calculate_fitness_metrics", "arguments": {"metric": "bmi", "weight_kg": 110, "height_cm": 720}}
    fixed = orchestrator.apply_unit_hints(call, "If my height is 6 foot and my weight is 110 kg what is my BMI?")
    assert fixed["arguments"] == {"metric": "bmi", "weight_kg": 110, "height_ft": 6.0, "height_in": 0.0}
    fixed = orchestrator.apply_unit_hints(call, "I'm 5 ft 9 and 180 pounds")
    assert fixed["arguments"]["height_in"] == 9.0 and fixed["arguments"]["weight_kg"] == 81.6
