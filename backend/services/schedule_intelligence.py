"""Moteur pur et explicable de planification.

Les fonctions de ce module acceptent des dictionnaires ou des objets simples.
Elles ne lisent aucune base de données et ne dépendent ni de FastAPI ni de
SQLAlchemy. Les dates doivent être des ``datetime`` comparables entre eux.

API publique principale :

* ``evaluate_candidate`` vérifie un candidat pour un créneau et calcule son score.
* ``rank_candidates`` classe tous les candidats pour un créneau.
* ``suggest_assignments`` propose des couples créneau/collaborateur.
* ``calculate_capacity`` agrège charge et capacité par métier et par station.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable, Mapping


DEFAULT_SCORE = 100.0
DEFAULT_SPEED_KMH = 35.0


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _identifier(item: Any) -> str:
    return str(_value(item, "id", _value(item, "reference", "")))


def _normal(value: Any) -> str:
    return str(value or "").strip().upper()


def _set(values: Iterable[Any] | None) -> set[str]:
    return {_normal(value) for value in (values or []) if _normal(value)}


def _interval(item: Any) -> tuple[datetime, datetime]:
    return _value(item, "start"), _value(item, "end")


def _overlaps(
    start: datetime,
    end: datetime,
    other_start: datetime,
    other_end: datetime,
) -> bool:
    return start < other_end and end > other_start


def _hours(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600)


def _reason(code: str, message: str, **details: Any) -> dict[str, Any]:
    result = {"code": code, "message": message}
    if details:
        result["details"] = details
    return result


def _task_end(task: Any, start: datetime) -> datetime:
    duration = int(_value(task, "duration_minutes", 0) or 0)
    if duration <= 0:
        raise ValueError("duration_minutes doit être strictement positif.")
    return start + timedelta(minutes=duration)


def _scoped(item: Any, *, user_id: Any = None, station_id: Any = None) -> bool:
    scoped_user = _value(item, "user_id")
    scoped_station = _value(item, "station_id")
    if scoped_user is not None and str(scoped_user) != str(user_id):
        return False
    if scoped_station is not None and str(scoped_station) != str(station_id):
        return False
    return True


def _within_working_interval(
    candidate: Any,
    start: datetime,
    end: datetime,
) -> bool:
    intervals = _value(candidate, "working_intervals", None)
    if intervals is None:
        return True
    return any(
        interval_start <= start and interval_end >= end
        for interval_start, interval_end in map(_interval, intervals)
    )


def _coordinates(location: Any) -> tuple[float, float] | None:
    if not location:
        return None
    latitude = _value(location, "lat", _value(location, "latitude"))
    longitude = _value(location, "lon", _value(location, "longitude"))
    if latitude is None or longitude is None:
        return None
    return float(latitude), float(longitude)


def _location_key(location: Any) -> str:
    if location is None:
        return ""
    if isinstance(location, str):
        return location
    return str(
        _value(
            location,
            "id",
            _value(location, "reference", _value(location, "name", "")),
        )
    )


def travel_minutes(
    origin: Any,
    destination: Any,
    travel_times: Mapping[Any, Any] | None = None,
    *,
    speed_kmh: float = DEFAULT_SPEED_KMH,
) -> int:
    """Retourne un temps de trajet déterministe, arrondi à la minute supérieure.

    ``travel_times`` peut utiliser une clé tuple ``(origine, destination)`` ou
    une clé texte ``"origine->destination"``. À défaut, les coordonnées
    latitude/longitude sont utilisées. Sans information géographique, le
    trajet vaut zéro.
    """

    origin_key = _location_key(origin)
    destination_key = _location_key(destination)
    if not origin_key or not destination_key or origin_key == destination_key:
        return 0

    travel_times = travel_times or {}
    direct_keys = (
        (origin_key, destination_key),
        f"{origin_key}->{destination_key}",
    )
    for key in direct_keys:
        if key in travel_times:
            return max(0, int(float(travel_times[key]) + 0.999999))

    first = _coordinates(origin)
    second = _coordinates(destination)
    if not first or not second:
        return 0
    if speed_kmh <= 0:
        raise ValueError("speed_kmh doit être strictement positif.")

    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    distance_km = 2 * 6371.0 * asin(sqrt(a))
    return int((distance_km / speed_kmh * 60) + 0.999999)


def _resource_conflicts(
    required_resource_ids: set[str],
    resources: Iterable[Any],
    bookings: Iterable[Any],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    conflicts = []
    resources_by_id = {_identifier(resource): resource for resource in resources}

    for resource_id in sorted(required_resource_ids):
        resource = resources_by_id.get(resource_id)
        if resource is None:
            conflicts.append(
                _reason(
                    "RESOURCE_UNKNOWN",
                    f"Ressource {resource_id} introuvable.",
                    resource_id=resource_id,
                )
            )
            continue
        if not bool(_value(resource, "active", True)):
            conflicts.append(
                _reason(
                    "RESOURCE_UNAVAILABLE",
                    f"Ressource {resource_id} inactive.",
                    resource_id=resource_id,
                )
            )
            continue
        for unavailability in _value(resource, "unavailable_intervals", []) or []:
            unavailable_start, unavailable_end = _interval(unavailability)
            if _overlaps(start, end, unavailable_start, unavailable_end):
                conflicts.append(
                    _reason(
                        "RESOURCE_UNAVAILABLE",
                        f"Ressource {resource_id} indisponible sur le créneau.",
                        resource_id=resource_id,
                    )
                )
                break

        for booking in bookings:
            booking_resources = _set(_value(booking, "resource_ids", []) or [])
            booking_start, booking_end = _interval(booking)
            if resource_id in booking_resources and _overlaps(
                start, end, booking_start, booking_end
            ):
                conflicts.append(
                    _reason(
                        "RESOURCE_BUSY",
                        f"Ressource {resource_id} déjà occupée.",
                        resource_id=resource_id,
                        booking_id=_identifier(booking),
                    )
                )
                break
    return conflicts


def _travel_constraints(
    task: Any,
    candidate: Any,
    bookings: Iterable[Any],
    start: datetime,
    end: datetime,
    travel_times: Mapping[Any, Any] | None,
) -> tuple[list[dict[str, Any]], int]:
    candidate_id = _identifier(candidate)
    task_location = _value(task, "location")
    margin = max(0, int(_value(task, "travel_margin_minutes", 0) or 0))
    candidate_bookings = sorted(
        (
            booking
            for booking in bookings
            if str(_value(booking, "user_id", "")) == candidate_id
        ),
        key=lambda booking: (_value(booking, "start"), _identifier(booking)),
    )
    previous = None
    following = None
    for booking in candidate_bookings:
        booking_start, booking_end = _interval(booking)
        if booking_end <= start and (
            previous is None or booking_end > _value(previous, "end")
        ):
            previous = booking
        if booking_start >= end and (
            following is None or booking_start < _value(following, "start")
        ):
            following = booking

    refusals = []
    total_travel = 0
    if previous is not None:
        minutes = travel_minutes(
            _value(previous, "location"),
            task_location,
            travel_times,
        )
        total_travel += minutes
        available = int((start - _value(previous, "end")).total_seconds() / 60)
        required = minutes + margin
        if available < required:
            refusals.append(
                _reason(
                    "TRAVEL_FROM_PREVIOUS",
                    "Temps insuffisant depuis l’intervention précédente.",
                    required_minutes=required,
                    available_minutes=available,
                    booking_id=_identifier(previous),
                )
            )

    if following is not None:
        minutes = travel_minutes(
            task_location,
            _value(following, "location"),
            travel_times,
        )
        total_travel += minutes
        available = int((_value(following, "start") - end).total_seconds() / 60)
        required = minutes + margin
        if available < required:
            refusals.append(
                _reason(
                    "TRAVEL_TO_NEXT",
                    "Temps insuffisant pour rejoindre l’intervention suivante.",
                    required_minutes=required,
                    available_minutes=available,
                    booking_id=_identifier(following),
                )
            )
    return refusals, total_travel


def evaluate_candidate(
    task: Any,
    candidate: Any,
    start: datetime,
    *,
    bookings: Iterable[Any] = (),
    resources: Iterable[Any] = (),
    closures: Iterable[Any] = (),
    absences: Iterable[Any] = (),
    travel_times: Mapping[Any, Any] | None = None,
) -> dict[str, Any]:
    """Évalue un collaborateur pour un créneau.

    Un résultat admissible contient ``accepted=True`` et un score de 0 à 100.
    Chaque bonus/malus est détaillé dans ``score_reasons``. Un résultat refusé
    contient toutes les raisons bloquantes dans ``refusals``.
    """

    bookings = tuple(bookings)
    resources = tuple(resources)
    closures = tuple(closures)
    absences = tuple(absences)
    end = _task_end(task, start)
    candidate_id = _identifier(candidate)
    station_id = _value(task, "station_id")
    required_skills = _set(_value(task, "required_skills", []) or [])
    candidate_skills = _set(_value(candidate, "skills", []) or [])
    required_resources = _set(_value(task, "required_resource_ids", []) or [])
    refusals: list[dict[str, Any]] = []

    missing_skills = sorted(required_skills - candidate_skills)
    if missing_skills:
        refusals.append(
            _reason(
                "MISSING_SKILLS",
                "Compétences requises manquantes.",
                missing_skills=missing_skills,
            )
        )

    candidate_stations = _set(_value(candidate, "station_ids", []) or [])
    if station_id is not None and candidate_stations and _normal(station_id) not in candidate_stations:
        refusals.append(
            _reason(
                "STATION_NOT_AUTHORIZED",
                f"Collaborateur non habilité pour la station {station_id}.",
                station_id=station_id,
            )
        )

    if not _within_working_interval(candidate, start, end):
        refusals.append(
            _reason(
                "OUTSIDE_WORK_SCHEDULE",
                "Créneau hors des horaires individuels.",
            )
        )

    all_absences = tuple(_value(candidate, "absences", []) or []) + absences
    for absence in all_absences:
        if not _scoped(absence, user_id=candidate_id, station_id=station_id):
            continue
        absence_start, absence_end = _interval(absence)
        if _overlaps(start, end, absence_start, absence_end):
            refusals.append(
                _reason(
                    "USER_ABSENT",
                    "Collaborateur absent sur le créneau.",
                    absence_id=_identifier(absence),
                    absence_type=_value(absence, "type", _value(absence, "absence_type")),
                )
            )
            break

    for closure in closures:
        if not _scoped(closure, user_id=candidate_id, station_id=station_id):
            continue
        closure_start, closure_end = _interval(closure)
        if _overlaps(start, end, closure_start, closure_end):
            refusals.append(
                _reason(
                    "CLOSED_PERIOD",
                    "Entreprise ou station fermée sur le créneau.",
                    closure_id=_identifier(closure),
                    label=_value(closure, "label"),
                )
            )
            break

    for booking in bookings:
        if str(_value(booking, "user_id", "")) != candidate_id:
            continue
        booking_start, booking_end = _interval(booking)
        if _overlaps(start, end, booking_start, booking_end):
            refusals.append(
                _reason(
                    "USER_BUSY",
                    "Collaborateur déjà affecté sur le créneau.",
                    booking_id=_identifier(booking),
                )
            )
            break

    refusals.extend(
        _resource_conflicts(required_resources, resources, bookings, start, end)
    )
    travel_refusals, total_travel = _travel_constraints(
        task,
        candidate,
        bookings,
        start,
        end,
        travel_times,
    )
    refusals.extend(travel_refusals)

    score_reasons: list[dict[str, Any]] = []
    score = DEFAULT_SCORE
    if refusals:
        score = 0.0
    else:
        excess_skills = len(candidate_skills - required_skills)
        if required_skills:
            score_reasons.append(
                _reason(
                    "SKILLS_MATCH",
                    "Toutes les compétences requises sont couvertes.",
                    delta=5.0,
                )
            )
            score += 5.0
        if excess_skills:
            versatility_bonus = min(3.0, excess_skills * 0.5)
            score += versatility_bonus
            score_reasons.append(
                _reason(
                    "VERSATILITY",
                    "Polyvalence utile disponible.",
                    delta=versatility_bonus,
                )
            )

        capacity_hours = float(_value(candidate, "capacity_hours", 35.0) or 0)
        planned_hours = sum(
            _hours(*_interval(booking))
            for booking in bookings
            if str(_value(booking, "user_id", "")) == candidate_id
        )
        task_hours = _hours(start, end)
        utilization = (
            (planned_hours + task_hours) / capacity_hours if capacity_hours > 0 else 1.0
        )
        load_penalty = min(40.0, max(0.0, utilization) * 20.0)
        score -= load_penalty
        score_reasons.append(
            _reason(
                "WORKLOAD",
                "Charge prévisionnelle après affectation.",
                delta=-round(load_penalty, 2),
                utilization_percent=round(utilization * 100, 1),
            )
        )

        travel_penalty = min(25.0, total_travel / 4)
        score -= travel_penalty
        score_reasons.append(
            _reason(
                "TRAVEL",
                "Impact des trajets adjacents.",
                delta=-round(travel_penalty, 2),
                travel_minutes=total_travel,
            )
        )

        preferred = _set(_value(task, "preferred_candidate_ids", []) or [])
        if candidate_id in preferred:
            score += 5.0
            score_reasons.append(
                _reason(
                    "PREFERRED_CANDIDATE",
                    "Collaborateur préféré pour cette intervention.",
                    delta=5.0,
                )
            )

    return {
        "candidate_id": candidate_id,
        "start": start,
        "end": end,
        "accepted": not refusals,
        "score": round(max(0.0, min(100.0, score)), 2),
        "refusals": refusals,
        "score_reasons": score_reasons,
        "travel_minutes": total_travel,
    }


def rank_candidates(
    task: Any,
    candidates: Iterable[Any],
    start: datetime,
    **context: Any,
) -> list[dict[str, Any]]:
    """Classe les candidats : admissibles d’abord, score puis identifiant."""

    results = [
        evaluate_candidate(task, candidate, start, **context)
        for candidate in candidates
    ]
    return sorted(
        results,
        key=lambda item: (
            not item["accepted"],
            -item["score"],
            item["candidate_id"],
        ),
    )


def suggest_assignments(
    task: Any,
    candidates: Iterable[Any],
    window_start: datetime,
    window_end: datetime,
    *,
    step_minutes: int = 30,
    limit: int = 10,
    **context: Any,
) -> list[dict[str, Any]]:
    """Propose les meilleurs couples créneau/collaborateur dans une fenêtre."""

    if step_minutes <= 0:
        raise ValueError("step_minutes doit être strictement positif.")
    if limit <= 0:
        return []

    candidates = tuple(candidates)
    suggestions = []
    cursor = window_start
    duration = timedelta(minutes=int(_value(task, "duration_minutes", 0) or 0))
    if duration <= timedelta(0):
        raise ValueError("duration_minutes doit être strictement positif.")

    while cursor + duration <= window_end:
        for result in rank_candidates(task, candidates, cursor, **context):
            if result["accepted"]:
                suggestions.append(result)
        cursor += timedelta(minutes=step_minutes)

    suggestions.sort(
        key=lambda item: (
            -item["score"],
            item["start"],
            item["candidate_id"],
        )
    )
    return suggestions[:limit]


def calculate_capacity(
    users: Iterable[Any],
    stations: Iterable[Any],
    assignments: Iterable[Any],
) -> dict[str, dict[str, dict[str, float]]]:
    """Agrège capacité et charge par métier et par station.

    Les utilisateurs et stations fournissent ``capacity_hours`` pour la
    période analysée. Chaque affectation fournit ``start``, ``end``,
    ``user_id`` et éventuellement ``station_id``.
    """

    users = tuple(users)
    stations = tuple(stations)
    assignments = tuple(assignments)
    user_by_id = {_identifier(user): user for user in users}
    station_by_id = {_identifier(station): station for station in stations}
    profession_capacity: dict[str, float] = defaultdict(float)
    profession_load: dict[str, float] = defaultdict(float)
    station_capacity: dict[str, float] = defaultdict(float)
    station_load: dict[str, float] = defaultdict(float)

    for user in users:
        profession = _normal(_value(user, "profession", "NON RENSEIGNÉ"))
        profession_capacity[profession] += float(
            _value(user, "capacity_hours", 0) or 0
        )

    for station in stations:
        station_capacity[_identifier(station)] += float(
            _value(station, "capacity_hours", 0) or 0
        )

    for assignment in assignments:
        duration = _hours(*_interval(assignment))
        user = user_by_id.get(str(_value(assignment, "user_id", "")))
        if user is not None:
            profession = _normal(_value(user, "profession", "NON RENSEIGNÉ"))
            profession_load[profession] += duration
        station_id = str(_value(assignment, "station_id", ""))
        if station_id in station_by_id:
            station_load[station_id] += duration

    def rows(
        capacities: Mapping[str, float],
        loads: Mapping[str, float],
    ) -> dict[str, dict[str, float]]:
        result = {}
        for key in sorted(set(capacities) | set(loads)):
            capacity = round(float(capacities.get(key, 0)), 2)
            load = round(float(loads.get(key, 0)), 2)
            result[key] = {
                "capacity_hours": capacity,
                "planned_hours": load,
                "remaining_hours": round(capacity - load, 2),
                "utilization_percent": round(load / capacity * 100, 1)
                if capacity
                else 0.0,
            }
        return result

    return {
        "by_profession": rows(profession_capacity, profession_load),
        "by_station": rows(station_capacity, station_load),
    }

