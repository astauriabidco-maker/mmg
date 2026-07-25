from datetime import datetime, timedelta

from backend.services.schedule_intelligence import (
    calculate_capacity,
    evaluate_candidate,
    rank_candidates,
    suggest_assignments,
)


DAY = datetime(2026, 8, 3, 8, 0)


def _candidate(
    identifier,
    *,
    skills=(),
    capacity_hours=35,
    profession="METREUR",
    station_ids=(),
):
    return {
        "id": identifier,
        "skills": list(skills),
        "capacity_hours": capacity_hours,
        "profession": profession,
        "station_ids": list(station_ids),
        "working_intervals": [
            {"start": DAY, "end": DAY + timedelta(hours=10)}
        ],
    }


def _task(**overrides):
    task = {
        "duration_minutes": 60,
        "required_skills": ["METRE"],
        "required_resource_ids": [],
        "location": "CHANTIER-A",
        "travel_margin_minutes": 15,
    }
    task.update(overrides)
    return task


def _codes(result):
    return {reason["code"] for reason in result["refusals"]}


def test_refuses_candidate_with_missing_skills():
    result = evaluate_candidate(
        _task(required_skills=["METRE", "PERMIS_B"]),
        _candidate("u1", skills=["METRE"]),
        DAY + timedelta(hours=1),
    )

    assert result["accepted"] is False
    assert result["score"] == 0
    assert "MISSING_SKILLS" in _codes(result)
    assert result["refusals"][0]["details"]["missing_skills"] == ["PERMIS_B"]


def test_refuses_leave_and_closed_period_with_explicit_reasons():
    slot = DAY + timedelta(hours=1)
    candidate = _candidate("u1", skills=["METRE"])
    absence = {
        "id": "leave-1",
        "user_id": "u1",
        "type": "LEAVE",
        "start": slot,
        "end": slot + timedelta(hours=2),
    }
    closure = {
        "id": "closed-1",
        "label": "Jour férié",
        "start": slot,
        "end": slot + timedelta(days=1),
    }

    result = evaluate_candidate(
        _task(),
        candidate,
        slot,
        absences=[absence],
        closures=[closure],
    )

    assert result["accepted"] is False
    assert _codes(result) == {"USER_ABSENT", "CLOSED_PERIOD"}


def test_refuses_busy_required_resource():
    slot = DAY + timedelta(hours=1)
    result = evaluate_candidate(
        _task(required_resource_ids=["VEHICLE-1"]),
        _candidate("u1", skills=["METRE"]),
        slot,
        resources=[{"id": "VEHICLE-1", "active": True}],
        bookings=[
            {
                "id": "booking-vehicle",
                "user_id": "u2",
                "resource_ids": ["VEHICLE-1"],
                "start": slot,
                "end": slot + timedelta(hours=2),
            }
        ],
    )

    assert result["accepted"] is False
    assert "RESOURCE_BUSY" in _codes(result)
    assert result["refusals"][0]["details"]["resource_id"] == "VEHICLE-1"


def test_travel_time_and_margin_can_refuse_candidate():
    slot = DAY + timedelta(hours=2)
    result = evaluate_candidate(
        _task(location="CHANTIER-B", travel_margin_minutes=15),
        _candidate("u1", skills=["METRE"]),
        slot,
        bookings=[
            {
                "id": "previous",
                "user_id": "u1",
                "start": DAY,
                "end": slot - timedelta(minutes=35),
                "location": "CHANTIER-A",
            }
        ],
        travel_times={("CHANTIER-A", "CHANTIER-B"): 30},
    )

    assert result["accepted"] is False
    assert result["travel_minutes"] == 30
    assert "TRAVEL_FROM_PREVIOUS" in _codes(result)
    details = result["refusals"][0]["details"]
    assert details["required_minutes"] == 45
    assert details["available_minutes"] == 35


def test_ranking_selects_best_candidate_and_explains_score():
    slot = DAY + timedelta(hours=4)
    candidates = [
        _candidate("busy", skills=["METRE"], capacity_hours=10),
        _candidate("best", skills=["METRE", "PERMIS_B"], capacity_hours=35),
    ]
    bookings = [
        {
            "id": "old-work",
            "user_id": "busy",
            "start": DAY - timedelta(days=1),
            "end": DAY - timedelta(days=1) + timedelta(hours=8),
            "location": "ATELIER",
        }
    ]

    ranked = rank_candidates(_task(), candidates, slot, bookings=bookings)

    assert [item["candidate_id"] for item in ranked] == ["best", "busy"]
    assert ranked[0]["accepted"] is True
    assert ranked[0]["score"] > ranked[1]["score"]
    assert {reason["code"] for reason in ranked[0]["score_reasons"]} >= {
        "SKILLS_MATCH",
        "WORKLOAD",
        "TRAVEL",
    }

    suggestions = suggest_assignments(
        _task(),
        candidates,
        slot,
        slot + timedelta(hours=2),
        step_minutes=60,
        limit=2,
        bookings=bookings,
    )
    assert suggestions[0]["candidate_id"] == "best"
    assert suggestions[0]["start"] == slot


def test_capacity_is_aggregated_by_profession_and_station():
    users = [
        _candidate("alu-1", profession="DEBIT_ALU", capacity_hours=28),
        _candidate("alu-2", profession="DEBIT_ALU", capacity_hours=35),
        _candidate("pvc-1", profession="DEBIT_PVC", capacity_hours=17.5),
    ]
    stations = [
        {"id": "ALU", "capacity_hours": 56},
        {"id": "PVC", "capacity_hours": 35},
    ]
    assignments = [
        {
            "user_id": "alu-1",
            "station_id": "ALU",
            "start": DAY,
            "end": DAY + timedelta(hours=7),
        },
        {
            "user_id": "alu-2",
            "station_id": "ALU",
            "start": DAY,
            "end": DAY + timedelta(hours=7),
        },
        {
            "user_id": "pvc-1",
            "station_id": "PVC",
            "start": DAY,
            "end": DAY + timedelta(hours=3.5),
        },
    ]

    capacity = calculate_capacity(users, stations, assignments)

    assert capacity["by_profession"]["DEBIT_ALU"] == {
        "capacity_hours": 63.0,
        "planned_hours": 14.0,
        "remaining_hours": 49.0,
        "utilization_percent": 22.2,
    }
    assert capacity["by_station"]["ALU"] == {
        "capacity_hours": 56.0,
        "planned_hours": 14.0,
        "remaining_hours": 42.0,
        "utilization_percent": 25.0,
    }
    assert capacity["by_station"]["PVC"]["planned_hours"] == 3.5

