#!/usr/bin/env python3
"""Deterministic fitness runtime for today's plan, workout control, and logging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import model_route_decider


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "fitness_agent.yaml"
DEFAULT_MEMORY_CONFIG = ROOT / "config" / "memory.yaml"
DEFAULT_DB = ROOT / ".memory" / "fitness.db"
DEFAULT_STATUS = ROOT / "data" / "fitness-runtime-status.json"
FITNESS_CANONICAL_FILES = (
    "ATHLETE_PROFILE.md",
    "PROGRAM.md",
    "RULES.md",
    "EXERCISE_LIBRARY.md",
    "SESSION_QUEUE.md",
)

DAY_CODE_TO_INDEX = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
}
INDEX_TO_DAY_CODE = {value: key for key, value in DAY_CODE_TO_INDEX.items()}
MAIN_DAY_CODES = ("M1", "M2", "M3", "M4", "M5")
OPTIONAL_DAY_CODE: str | None = None
SESSION_CODE_TO_QUEUE_KEY = {
    "M1": "M1_mon_bench_1",
    "M2": "M2_tue_db",
    "M3": "M3_thu_db_bb",
    "M4": "M4_fri_bench_2",
    "M5": "M5_sat_db",
}
REST_DAY_TO_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MUSCLE_GROUP_BY_EXERCISE = {
    "incline_dumbbell_press": "chest",
    "close_grip_barbell_press": "triceps",
    "barbell_curl": "biceps",
    "hammer_curl": "biceps",
    "overhead_dumbbell_triceps_extension": "triceps",
    "dumbbell_lat_row": "back",
    "zottman_curl": "biceps",
    "lateral_raise": "delts",
    "barbell_standing_extension": "triceps",
    "wide_grip_barbell_curl": "biceps",
    "dumbbell_neutral_floor_press": "chest",
    "deadlift": "posterior_chain",
    "dumbbell_fly": "chest",
    "incline_dumbbell_curl": "biceps",
    "lunges": "legs",
}
EQUIPMENT_BY_EXERCISE = {
    "incline_dumbbell_press": "dumbbells",
    "close_grip_barbell_press": "barbell",
    "barbell_curl": "barbell",
    "hammer_curl": "dumbbells",
    "overhead_dumbbell_triceps_extension": "dumbbells",
    "dumbbell_lat_row": "dumbbells",
    "zottman_curl": "dumbbells",
    "lateral_raise": "dumbbells",
    "barbell_standing_extension": "barbell",
    "wide_grip_barbell_curl": "barbell",
    "dumbbell_neutral_floor_press": "dumbbells",
    "deadlift": "barbell",
    "dumbbell_fly": "dumbbells",
    "incline_dumbbell_curl": "dumbbells",
    "lunges": "dumbbells",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_from_code(code: str) -> str:
    return " ".join(part.capitalize() for part in code.split("_"))


def format_local(ts_text: str | None, timezone_name: str) -> str:
    if not ts_text:
        return "-"
    text = ts_text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")


def local_date_iso(timezone_name: str) -> str:
    return now_utc().astimezone(ZoneInfo(timezone_name)).date().isoformat()


def program_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def canonical_fitness_paths(root: Path) -> list[Path]:
    return [root / "fitness" / name for name in FITNESS_CANONICAL_FILES]


def build_canonical_fitness_context(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    hash_parts: list[str] = []
    for path in canonical_fitness_paths(root):
        text = path.read_text(encoding="utf-8")
        relative_path = str(path.relative_to(root))
        files.append(
            {
                "path": relative_path,
                "content_hash": program_hash(text),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            }
        )
        hash_parts.append(f"## {relative_path}\n{text}")
    return {
        "hash": program_hash("\n\n".join(hash_parts)),
        "files": files,
    }


@dataclass
class ExerciseDefinition:
    code: str
    aliases: list[str]


@dataclass
class DayExerciseSpec:
    slot_label: str
    exercise_code: str
    display_name: str
    target_sets: int
    target_rep_min: int | None
    target_rep_max: int | None
    set_style: str
    prescription_text: str


@dataclass
class DayPlan:
    code: str
    title: str
    equipment: list[str]
    exercises: list[DayExerciseSpec]


def parse_exercise_library(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    definitions: dict[str, ExerciseDefinition] = {}
    alias_map: dict[str, list[str]] = {}
    current_code: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        code_match = re.match(r"^\d+\.\s+`([^`]+)`$", line)
        if code_match:
            current_code = code_match.group(1).strip()
            definitions[current_code] = ExerciseDefinition(code=current_code, aliases=[])
            for alias in {current_code, current_code.replace("_", " "), title_from_code(current_code)}:
                alias_map.setdefault(normalize_text(alias), []).append(current_code)
            continue
        if current_code and line.startswith("- aliases:"):
            aliases = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            definitions[current_code].aliases.extend(aliases)
            for alias in aliases:
                alias_map.setdefault(normalize_text(alias), []).append(current_code)
            continue
        if line.startswith("## ") and "Main Program Pool" not in line and current_code:
            current_code = None
    return {
        "definitions": definitions,
        "alias_map": alias_map,
    }


def resolve_exercise_code(
    raw_name: str,
    *,
    alias_map: dict[str, list[str]],
    active_codes: list[str] | None = None,
) -> str:
    normalized = normalize_text(raw_name.replace("myorep", "").replace("myoreps", ""))
    if normalized in alias_map:
        candidates = list(dict.fromkeys(alias_map[normalized]))
        if len(candidates) == 1:
            return candidates[0]
        if active_codes:
            narrowed = [item for item in candidates if item in active_codes]
            if len(narrowed) == 1:
                return narrowed[0]
        raise ValueError(f"ambiguous exercise: {raw_name}")

    all_candidates: set[str] = set()
    for alias_text, codes in alias_map.items():
        if normalized and (normalized in alias_text or alias_text in normalized):
            all_candidates.update(codes)
    if active_codes:
        narrowed = [item for item in all_candidates if item in active_codes]
        if len(narrowed) == 1:
            return narrowed[0]
        if len(narrowed) > 1:
            raise ValueError(f"ambiguous exercise: {raw_name}")
    if len(all_candidates) == 1:
        return next(iter(all_candidates))
    if all_candidates:
        raise ValueError(f"ambiguous exercise: {raw_name}")
    raise ValueError(f"unknown exercise: {raw_name}")


def parse_straight_prescription(text: str) -> tuple[int, int | None, int | None, str]:
    clean = text.replace("`", "").strip()
    match = re.match(r"^(?P<sets>\d+)\s*x\s*(?P<min>\d+)(?:-(?P<max>\d+))?", clean)
    if match:
        rep_min = int(match.group("min"))
        rep_max = int(match.group("max") or match.group("min"))
        return int(match.group("sets")), rep_min, rep_max, "straight"

    myo = re.match(r"^(?P<min>\d+)-(?P<max>\d+)\s+\+\s+(?P<mini_sets>\d+)-(?P<mini_sets_max>\d+)\s+x\s+(?P<mini_min>\d+)-(?P<mini_max>\d+)", clean)
    if myo:
        rep_min = int(myo.group("min"))
        rep_max = int(myo.group("max"))
        return 1, rep_min, rep_max, "myorep"

    if clean:
        return 1, None, None, "straight"
    raise ValueError(f"invalid prescription: {text}")


def parse_program(path: Path, exercise_catalog: dict[str, Any]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Program"
    day_matches = list(re.finditer(r"^###\s+(M\d|O\d):\s+(.+)$", text, flags=re.MULTILINE))
    plans: dict[str, DayPlan] = {}
    alias_map = exercise_catalog["alias_map"]
    for index, match in enumerate(day_matches):
        code = match.group(1).strip()
        day_title = match.group(2).strip()
        start = match.end()
        end = day_matches[index + 1].start() if index + 1 < len(day_matches) else len(text)
        block = text[start:end]
        lines = [line.rstrip() for line in block.splitlines()]
        exercise_lines: list[str] = []
        equipment: list[str] = []
        in_equipment = False
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("Equipment:"):
                in_equipment = True
                continue
            if in_equipment:
                equipment.extend([item.strip() for item in line.replace("`", "").split(",") if item.strip()])
                continue
            if re.match(r"^\d+\.\s+", line):
                exercise_lines.append(line)

        day_exercises: list[DayExerciseSpec] = []
        for row in exercise_lines:
            clean = row.replace("`", "")
            numberless = re.sub(r"^\d+\.\s+", "", clean).strip()
            if ":" not in numberless:
                continue
            left, right = [part.strip() for part in numberless.split(":", 1)]
            slot_match = re.match(r"^(A1|A2|B1|B2|C1|C2)\s+(.+)$", left)
            slot_label = slot_match.group(1) if slot_match else f"X{len(day_exercises) + 1}"
            display_name = slot_match.group(2).strip() if slot_match else left
            resolved_name = display_name.replace(" myorep", "").replace(" myoreps", "").strip()
            exercise_code = resolve_exercise_code(resolved_name, alias_map=alias_map)
            target_sets, rep_min, rep_max, set_style = parse_straight_prescription(right)
            if "myorep" in display_name.lower():
                set_style = "myorep"
            day_exercises.append(
                DayExerciseSpec(
                    slot_label=slot_label,
                    exercise_code=exercise_code,
                    display_name=display_name,
                    target_sets=target_sets,
                    target_rep_min=rep_min,
                    target_rep_max=rep_max,
                    set_style=set_style,
                    prescription_text=right.replace("`", "").strip(),
                )
            )
        plans[code] = DayPlan(code=code, title=day_title, equipment=equipment, exercises=day_exercises)
    return {
        "name": title,
        "hash": program_hash(text),
        "days": plans,
    }


def load_yaml_dict(path: Path) -> dict[str, Any]:
    data = model_route_decider.load_yaml(path)
    return ensure_dict(data)


def open_conn(db_path: Path, schema_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    ensure_runtime_extensions(conn)
    return conn


def ensure_runtime_extensions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    add_column_if_missing(conn, "sessions", "training_day_code", "TEXT")
    add_column_if_missing(conn, "set_logs", "weight_mode", "TEXT")
    add_column_if_missing(conn, "set_logs", "raw_input_text", "TEXT")
    conn.commit()


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM runtime_settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO runtime_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, iso_now()),
    )
    conn.commit()


def sync_program(conn: sqlite3.Connection, *, config: dict[str, Any], plan: dict[str, Any]) -> int:
    program_name = str(plan.get("name") or "Program").strip()
    now = iso_now()
    row = conn.execute(
        "SELECT id FROM programs WHERE name = ? ORDER BY id DESC LIMIT 1",
        (program_name,),
    ).fetchone()
    if row:
        program_id = int(row["id"])
        conn.execute("UPDATE programs SET status = 'active', updated_at = ? WHERE id = ?", (now, program_id))
    else:
        cur = conn.execute(
            """
            INSERT INTO programs (name, status, start_date, notes, created_at, updated_at)
            VALUES (?, 'active', NULL, ?, ?, ?)
            """,
            (program_name, f"plan_hash={plan.get('hash')}", now, now),
        )
        program_id = int(cur.lastrowid)

    exercise_defs = ensure_dict(config.get("_exercise_definitions"))
    for code in exercise_defs:
        conn.execute(
            """
            INSERT INTO exercises (code, name, muscle_group, equipment, movement_pattern, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
              name = excluded.name,
              muscle_group = excluded.muscle_group,
              equipment = excluded.equipment,
              movement_pattern = excluded.movement_pattern,
              updated_at = excluded.updated_at
            """,
            (
                code,
                title_from_code(code),
                MUSCLE_GROUP_BY_EXERCISE.get(code),
                EQUIPMENT_BY_EXERCISE.get(code),
                None,
                now,
                now,
            ),
        )

    days = ensure_dict(plan.get("days"))
    for code, day in days.items():
        day_plan = day if isinstance(day, DayPlan) else None
        if day_plan is None:
            continue
        day_index = DAY_CODE_TO_INDEX[code]
        row = conn.execute(
            "SELECT id FROM training_days WHERE program_id = ? AND day_index = ?",
            (program_id, day_index),
        ).fetchone()
        if row:
            training_day_id = int(row["id"])
            conn.execute(
                """
                UPDATE training_days
                SET day_name = ?, focus = ?, updated_at = ?
                WHERE id = ?
                """,
                (code, day_plan.title, now, training_day_id),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO training_days (program_id, day_index, day_name, focus, is_rest_day, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (program_id, day_index, code, day_plan.title, now, now),
            )
            training_day_id = int(cur.lastrowid)

        conn.execute("DELETE FROM day_exercises WHERE training_day_id = ?", (training_day_id,))
        for slot_order, exercise in enumerate(day_plan.exercises, start=1):
            exercise_id = exercise_id_by_code(conn, exercise.exercise_code)
            conn.execute(
                """
                INSERT INTO day_exercises (
                  training_day_id, exercise_id, slot_order, target_rep_min, target_rep_max, target_sets,
                  progression_rule, set_style, superset_label, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    training_day_id,
                    exercise_id,
                    slot_order,
                    exercise.target_rep_min,
                    exercise.target_rep_max,
                    exercise.target_sets,
                    "myorep_density" if exercise.set_style == "myorep" else "double_progression",
                    exercise.set_style,
                    exercise.slot_label,
                    exercise.prescription_text,
                    now,
                    now,
                ),
            )

    conn.commit()
    return program_id


def load_fitness_config(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    resolved = config_path or (root / "config" / "fitness_agent.yaml")
    config = load_yaml_dict(resolved)
    canonical_context = build_canonical_fitness_context(root)
    catalog = parse_exercise_library(root / "fitness" / "EXERCISE_LIBRARY.md")
    config["_canonical_context"] = canonical_context
    config["_canonical_hash"] = canonical_context["hash"]
    config["_exercise_definitions"] = catalog["definitions"]
    config["_exercise_alias_map"] = catalog["alias_map"]
    config["_program"] = parse_program(root / "fitness" / "PROGRAM.md", catalog)
    return config


def load_day_plan(config: dict[str, Any], code: str) -> DayPlan:
    plans = ensure_dict(config.get("_program", {})).get("days", {})
    if isinstance(plans, dict) and code in plans:
        return plans[code]
    raise ValueError(f"day plan not found: {code}")


def get_program_id(conn: sqlite3.Connection, config: dict[str, Any]) -> int:
    return sync_program(conn, config=config, plan=ensure_dict(config["_program"]))


def get_active_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM sessions
        WHERE status = 'in_progress'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def get_last_completed_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM sessions
        WHERE status = 'completed'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def get_last_completed_main_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM sessions
        WHERE status = 'completed' AND training_day_index BETWEEN 1 AND 4
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def determine_next_main_code(conn: sqlite3.Connection) -> str:
    row = get_last_completed_main_session(conn)
    if not row:
        return "M1"
    current = int(row["training_day_index"])
    return INDEX_TO_DAY_CODE[(current % len(MAIN_DAY_CODES)) + 1]


def current_local_weekday(timezone_name: str) -> int:
    return now_utc().astimezone(ZoneInfo(timezone_name)).weekday()


def default_rest_weekdays(config: dict[str, Any]) -> set[int]:
    days = ensure_string_list(ensure_dict(config.get("schedule")).get("default_rest_days", []))
    return {REST_DAY_TO_WEEKDAY[item] for item in days if item in REST_DAY_TO_WEEKDAY}


def optional_session_available(config: dict[str, Any]) -> bool:
    optional_count = int(ensure_dict(config.get("schedule")).get("optional_workouts_per_week") or 0)
    if not OPTIONAL_DAY_CODE or optional_count <= 0:
        return False
    return current_local_weekday(str(ensure_dict(config.get("schedule")).get("timezone") or "UTC")) == 5


def build_plan_row(plan: DayPlan) -> dict[str, Any]:
    return {
        "code": plan.code,
        "title": plan.title,
        "equipment": list(plan.equipment),
        "exercises": [
            {
                "slot_label": item.slot_label,
                "exercise_code": item.exercise_code,
                "display_name": item.display_name,
                "target_sets": item.target_sets,
                "target_rep_min": item.target_rep_min,
                "target_rep_max": item.target_rep_max,
                "set_style": item.set_style,
                "prescription_text": item.prescription_text,
            }
            for item in plan.exercises
        ],
    }


def determine_today_plan(conn: sqlite3.Connection, config: dict[str, Any], *, include_optional: bool = False) -> dict[str, Any]:
    active = get_active_session(conn)
    timezone_name = str(ensure_dict(config.get("schedule")).get("timezone") or "UTC")
    rest_anchors = default_rest_weekdays(config)
    weekday = current_local_weekday(timezone_name)
    if active:
        code = str(active["training_day_code"] or INDEX_TO_DAY_CODE.get(int(active["training_day_index"]), "M1"))
        plan = load_day_plan(config, code)
        return {
            "mode": "active_session",
            "is_rest_anchor": weekday in rest_anchors,
            "plan": build_plan_row(plan),
            "optional_plan": None,
            "notes": ["An active workout session already exists."],
        }

    next_main_code = determine_next_main_code(conn)
    plan = load_day_plan(config, next_main_code)
    optional_plan = None
    if include_optional and OPTIONAL_DAY_CODE and optional_session_available(config):
        optional_plan = build_plan_row(load_day_plan(config, OPTIONAL_DAY_CODE))
    notes: list[str] = []
    if weekday in rest_anchors:
        notes.append("Today is a default rest anchor. Main-session queue still rolls forward.")
    if optional_plan:
        notes.append(f"Optional {OPTIONAL_DAY_CODE} is available today if recovery and schedule allow it.")
    return {
        "mode": "next_pending",
        "is_rest_anchor": weekday in rest_anchors,
        "plan": build_plan_row(plan),
        "optional_plan": optional_plan,
        "notes": notes,
    }


def next_set_order(conn: sqlite3.Connection, session_id: int, exercise_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(set_order), 0) AS value FROM set_logs WHERE session_id = ? AND exercise_id = ?",
        (session_id, exercise_id),
    ).fetchone()
    return int(row["value"]) + 1 if row else 1


def exercise_id_by_code(conn: sqlite3.Connection, code: str) -> int:
    row = conn.execute("SELECT id FROM exercises WHERE code = ?", (code,)).fetchone()
    if not row:
        raise ValueError(f"exercise not found: {code}")
    return int(row["id"])


def active_day_exercise_codes(conn: sqlite3.Connection, session_id: int) -> list[str]:
    row = conn.execute("SELECT training_day_index FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return []
    training_day = conn.execute(
        "SELECT id FROM training_days WHERE day_index = ? ORDER BY id DESC LIMIT 1",
        (int(row["training_day_index"]),),
    ).fetchone()
    if not training_day:
        return []
    rows = conn.execute(
        """
        SELECT exercises.code
        FROM day_exercises
        JOIN exercises ON exercises.id = day_exercises.exercise_id
        WHERE day_exercises.training_day_id = ?
        ORDER BY day_exercises.slot_order
        """,
        (int(training_day["id"]),),
    ).fetchall()
    return [str(item["code"]) for item in rows]


def infer_default_weight_mode(exercise_code: str) -> str:
    equipment = EQUIPMENT_BY_EXERCISE.get(exercise_code)
    if equipment == "barbell":
        return "bb_total"
    return "each"


def canonicalize_weight(
    *,
    entered_weight: float,
    weight_mode: str,
    conn: sqlite3.Connection,
) -> float:
    if weight_mode == "pair":
        return round(entered_weight / 2.0, 3)
    if weight_mode == "bb_side":
        empty = get_setting(conn, "barbell_empty_weight_kg")
        if empty is None:
            raise ValueError("Barbell empty weight is not set. Use `set barbell empty <kg>kg` first.")
        return round(float(empty) + (entered_weight * 2.0), 3)
    return entered_weight


def parse_single_set(
    text: str,
    *,
    alias_map: dict[str, list[str]],
    conn: sqlite3.Connection,
    active_codes: list[str],
    default_superset_label: str | None = None,
) -> list[dict[str, Any]]:
    clean = text.replace("`", "").strip()
    match = re.match(
        r"^(?:(?P<label>A1|A2|B1|B2|C1|C2)\s+)?(?P<exercise>.+?)\s+(?P<reps>\d+)\s+reps\s+(?P<weight>\d+(?:\.\d+)?)kg(?:\s+(?P<mode>each|pair|bb total|bb side))?(?:\s+rir\s+(?P<rir>\d+(?:\.\d+)?))?$",
        clean,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Could not parse set log: {text}")
    exercise_code = resolve_exercise_code(
        match.group("exercise"),
        alias_map=alias_map,
        active_codes=active_codes,
    )
    weight_mode = (match.group("mode") or infer_default_weight_mode(exercise_code)).strip().lower().replace(" ", "_")
    entered_weight = float(match.group("weight"))
    canonical_weight = canonicalize_weight(entered_weight=entered_weight, weight_mode=weight_mode, conn=conn)
    return [
        {
            "exercise_code": exercise_code,
            "reps": int(match.group("reps")),
            "weight_kg": canonical_weight,
            "weight_mode": weight_mode,
            "set_type": "straight",
            "rir": float(match.group("rir")) if match.group("rir") else None,
            "superset_label": match.group("label") or default_superset_label,
            "myorep_cluster": None,
            "raw_input_text": clean,
        }
    ]


def parse_myoreps(
    text: str,
    *,
    alias_map: dict[str, list[str]],
    conn: sqlite3.Connection,
    active_codes: list[str],
) -> list[dict[str, Any]]:
    clean = text.replace("`", "").strip()
    match = re.match(
        r"^myoreps?\s+(?P<exercise>.+?)\s+(?P<weight>\d+(?:\.\d+)?)kg(?:\s+(?P<mode>each|pair|bb total|bb side))?\s+activation\s+(?P<activation>\d+)\s+then\s+(?P<minis>\d+(?:\+\d+)*)$",
        clean,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Could not parse myorep log: {text}")
    exercise_code = resolve_exercise_code(
        match.group("exercise"),
        alias_map=alias_map,
        active_codes=active_codes,
    )
    weight_mode = (match.group("mode") or infer_default_weight_mode(exercise_code)).strip().lower().replace(" ", "_")
    canonical_weight = canonicalize_weight(
        entered_weight=float(match.group("weight")),
        weight_mode=weight_mode,
        conn=conn,
    )
    mini_reps = [int(item) for item in match.group("minis").split("+") if item.strip()]
    cluster = "|".join([match.group("activation"), *[str(item) for item in mini_reps]])
    payload = [
        {
            "exercise_code": exercise_code,
            "reps": int(match.group("activation")),
            "weight_kg": canonical_weight,
            "weight_mode": weight_mode,
            "set_type": "myorep_activation",
            "rir": None,
            "superset_label": None,
            "myorep_cluster": cluster,
            "raw_input_text": clean,
        }
    ]
    payload.extend(
        {
            "exercise_code": exercise_code,
            "reps": reps,
            "weight_kg": canonical_weight,
            "weight_mode": weight_mode,
            "set_type": "myorep_mini",
            "rir": None,
            "superset_label": None,
            "myorep_cluster": cluster,
            "raw_input_text": clean,
        }
        for reps in mini_reps
    )
    return payload


def parse_log_text(
    text: str,
    *,
    alias_map: dict[str, list[str]],
    conn: sqlite3.Connection,
    active_codes: list[str],
) -> list[dict[str, Any]]:
    clean = text.replace("`", "").strip()
    if clean.lower().startswith("log "):
        clean = clean[4:].strip()

    if clean.lower().startswith("superset "):
        match = re.match(
            r"^superset\s+(?P<label1>A1|A2|B1|B2|C1|C2)\s+(?P<body1>.+?)\s+and\s+(?P<label2>A1|A2|B1|B2|C1|C2)\s+(?P<body2>.+)$",
            clean,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError("Could not parse superset log")
        first = parse_single_set(
            match.group("body1"),
            alias_map=alias_map,
            conn=conn,
            active_codes=active_codes,
            default_superset_label=match.group("label1").upper(),
        )
        second = parse_single_set(
            match.group("body2"),
            alias_map=alias_map,
            conn=conn,
            active_codes=active_codes,
            default_superset_label=match.group("label2").upper(),
        )
        return first + second

    if clean.lower().startswith("myorep"):
        return parse_myoreps(clean, alias_map=alias_map, conn=conn, active_codes=active_codes)

    return parse_single_set(clean, alias_map=alias_map, conn=conn, active_codes=active_codes)


def create_session(conn: sqlite3.Connection, *, program_id: int, day_code: str, timezone_name: str) -> dict[str, Any]:
    active = get_active_session(conn)
    if active:
        return {"created": False, "session": dict(active)}
    day_index = DAY_CODE_TO_INDEX[day_code]
    now = iso_now()
    cur = conn.execute(
        """
        INSERT INTO sessions (
          program_id, session_date, training_day_index, training_day_code, status, bodyweight_kg,
          readiness_score, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'in_progress', NULL, NULL, NULL, ?, ?)
        """,
        (program_id, local_date_iso(timezone_name), day_index, day_code, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (int(cur.lastrowid),)).fetchone()
    return {"created": True, "session": dict(row) if row else None}


def log_sets(conn: sqlite3.Connection, *, text: str, config: dict[str, Any]) -> dict[str, Any]:
    session = get_active_session(conn)
    if not session:
        raise ValueError("No active workout session. Use `start workout` first.")
    alias_map = ensure_dict(config.get("_exercise_alias_map"))
    active_codes = active_day_exercise_codes(conn, int(session["id"]))
    entries = parse_log_text(text, alias_map=alias_map, conn=conn, active_codes=active_codes)
    created: list[dict[str, Any]] = []
    for row in entries:
        exercise_id = exercise_id_by_code(conn, str(row["exercise_code"]))
        set_order = next_set_order(conn, int(session["id"]), exercise_id)
        conn.execute(
            """
            INSERT INTO set_logs (
              session_id, exercise_id, set_order, set_type, reps, weight_kg, rir, rest_seconds,
              myorep_cluster, superset_label, effort_note, weight_mode, raw_input_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?)
            """,
            (
                int(session["id"]),
                exercise_id,
                set_order,
                row["set_type"],
                row["reps"],
                row["weight_kg"],
                row["rir"],
                row["myorep_cluster"],
                row["superset_label"],
                row["weight_mode"],
                row["raw_input_text"],
                iso_now(),
            ),
        )
        created.append(
            {
                "exercise_code": row["exercise_code"],
                "set_order": set_order,
                "reps": row["reps"],
                "weight_kg": row["weight_kg"],
                "weight_mode": row["weight_mode"],
                "set_type": row["set_type"],
                "superset_label": row["superset_label"],
                "myorep_cluster": row["myorep_cluster"],
            }
        )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (iso_now(), int(session["id"])))
    conn.commit()
    return {"session_id": int(session["id"]), "created_sets": created}


def set_barbell_empty_weight(conn: sqlite3.Connection, weight_kg: float) -> dict[str, Any]:
    if weight_kg <= 0:
        raise ValueError("barbell empty weight must be > 0")
    set_setting(conn, "barbell_empty_weight_kg", str(weight_kg))
    return {"barbell_empty_weight_kg": weight_kg}


def fetch_session_sets(conn: sqlite3.Connection, session_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          set_logs.set_order,
          set_logs.set_type,
          set_logs.reps,
          set_logs.weight_kg,
          set_logs.rir,
          set_logs.myorep_cluster,
          set_logs.superset_label,
          set_logs.weight_mode,
          set_logs.raw_input_text,
          exercises.code AS exercise_code,
          exercises.name AS exercise_name
        FROM set_logs
        JOIN exercises ON exercises.id = set_logs.exercise_id
        WHERE set_logs.session_id = ?
        ORDER BY set_logs.created_at ASC, set_logs.id ASC
        """,
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def summarize_session_logs(sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in sets:
        code = str(row["exercise_code"])
        bucket = grouped.setdefault(
            code,
            {
                "exercise_code": code,
                "exercise_name": str(row["exercise_name"]),
                "logged_sets": 0,
                "reps": [],
                "top_weight_kg": None,
                "set_types": set(),
            },
        )
        bucket["logged_sets"] += 1
        if row["reps"] is not None:
            bucket["reps"].append(int(row["reps"]))
        if row["weight_kg"] is not None:
            current = float(row["weight_kg"])
            if bucket["top_weight_kg"] is None or current > bucket["top_weight_kg"]:
                bucket["top_weight_kg"] = current
        bucket["set_types"].add(str(row["set_type"]))
    results = []
    for bucket in grouped.values():
        results.append(
            {
                "exercise_code": bucket["exercise_code"],
                "exercise_name": bucket["exercise_name"],
                "logged_sets": bucket["logged_sets"],
                "best_reps": max(bucket["reps"]) if bucket["reps"] else None,
                "top_weight_kg": bucket["top_weight_kg"],
                "set_types": sorted(bucket["set_types"]),
            }
        )
    return sorted(results, key=lambda row: row["exercise_name"])


def write_session_summary(
    *,
    root: Path,
    session: dict[str, Any],
    day_plan: DayPlan,
    session_sets: list[dict[str, Any]],
    timezone_name: str,
    next_main_code: str,
) -> Path:
    log_dir = root / "fitness" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_text = str(session.get("session_date") or local_date_iso(timezone_name))
    log_path = log_dir / f"{date_text}-{day_plan.code}.md"
    lines = [
        f"# {day_plan.code} Session Summary",
        "",
        f"- Date: {date_text}",
        f"- Session id: {session.get('id')}",
        f"- Plan: {day_plan.title}",
        f"- Finished at: {format_local(str(session.get('updated_at') or ''), timezone_name)}",
        f"- Next main session: {next_main_code}",
        "",
        "## Logged Sets",
    ]
    for row in summarize_session_logs(session_sets):
        top_weight = f"{row['top_weight_kg']}kg" if row.get("top_weight_kg") is not None else "-"
        best_reps = row.get("best_reps") if row.get("best_reps") is not None else "-"
        lines.append(
            f"- {row['exercise_name']}: sets={row['logged_sets']} | best_reps={best_reps} | top_weight={top_weight} | types={', '.join(row['set_types'])}"
        )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def finish_session(conn: sqlite3.Connection, *, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    session = get_active_session(conn)
    if not session:
        raise ValueError("No active workout session.")
    session_id = int(session["id"])
    conn.execute("UPDATE sessions SET status = 'completed', updated_at = ? WHERE id = ?", (iso_now(), session_id))
    conn.commit()
    completed = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    session_row = dict(completed) if completed else dict(session)
    code = str(session_row.get("training_day_code") or INDEX_TO_DAY_CODE.get(int(session_row["training_day_index"]), "M1"))
    plan = load_day_plan(config, code)
    sets = fetch_session_sets(conn, session_id)
    next_main = determine_next_main_code(conn)
    log_path = write_session_summary(
        root=root,
        session=session_row,
        day_plan=plan,
        session_sets=sets,
        timezone_name=str(ensure_dict(config.get("schedule")).get("timezone") or "UTC"),
        next_main_code=next_main,
    )
    return {
        "session": session_row,
        "summary_path": str(log_path),
        "next_main_code": next_main,
        "summary": summarize_session_logs(sets),
    }


def weekly_volume(conn: sqlite3.Connection, *, timezone_name: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT exercises.muscle_group, COUNT(*) AS set_count
        FROM set_logs
        JOIN sessions ON sessions.id = set_logs.session_id
        JOIN exercises ON exercises.id = set_logs.exercise_id
        WHERE sessions.status = 'completed'
          AND date(sessions.session_date) >= date('now', '-7 day')
          AND set_logs.set_type != 'warmup'
        GROUP BY exercises.muscle_group
        """
    ).fetchall()
    return {str(row["muscle_group"] or "unknown"): int(row["set_count"] or 0) for row in rows}


def progression_flags(conn: sqlite3.Connection, config: dict[str, Any]) -> list[dict[str, Any]]:
    latest = get_last_completed_session(conn)
    if not latest:
        return []
    code = str(latest["training_day_code"] or INDEX_TO_DAY_CODE.get(int(latest["training_day_index"]), "M1"))
    plan = load_day_plan(config, code)
    plan_by_exercise = {item.exercise_code: item for item in plan.exercises}
    summaries = summarize_session_logs(fetch_session_sets(conn, int(latest["id"])))
    flags: list[dict[str, Any]] = []
    for row in summaries:
        spec = plan_by_exercise.get(str(row["exercise_code"]))
        if spec is None or spec.target_rep_max is None:
            continue
        if spec.set_style == "straight" and row.get("best_reps") is not None and int(row["best_reps"]) >= int(spec.target_rep_max):
            flags.append(
                {
                    "exercise_code": row["exercise_code"],
                    "exercise_name": row["exercise_name"],
                    "flag": "consider_load_increase",
                    "reason": f"best reps reached upper target ({spec.target_rep_max})",
                }
            )
        if spec.set_style == "myorep" and row.get("best_reps") is not None and int(row["best_reps"]) >= int(spec.target_rep_max):
            flags.append(
                {
                    "exercise_code": row["exercise_code"],
                    "exercise_name": row["exercise_name"],
                    "flag": "consider_load_or_density_increase",
                    "reason": f"activation reps reached upper target ({spec.target_rep_max})",
                }
            )
    return flags[:8]


def build_status_payload(
    conn: sqlite3.Connection,
    *,
    root: Path,
    db_path: Path,
    config: dict[str, Any],
    action: str,
    recent_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timezone_name = str(ensure_dict(config.get("schedule")).get("timezone") or "UTC")
    today = determine_today_plan(conn, config, include_optional=True)
    active = get_active_session(conn)
    last = get_last_completed_session(conn)
    active_summary = None
    if active:
        active_summary = summarize_session_logs(fetch_session_sets(conn, int(active["id"])))
    last_summary = None
    if last:
        last_summary = summarize_session_logs(fetch_session_sets(conn, int(last["id"])))
    payload = {
        "generated_at": iso_now(),
        "available": True,
        "action": action,
        "timezone": timezone_name,
        "db_path": str(db_path),
        "canonical_context": ensure_dict(config.get("_canonical_context")),
        "settings": {
            "barbell_empty_weight_kg": (
                float(get_setting(conn, "barbell_empty_weight_kg"))
                if get_setting(conn, "barbell_empty_weight_kg") is not None
                else None
            ),
        },
        "today_plan": today,
        "active_session": dict(active) if active else None,
        "active_session_summary": active_summary,
        "last_session": dict(last) if last else None,
        "last_session_summary": last_summary,
        "weekly_volume": weekly_volume(conn, timezone_name=timezone_name),
        "progression_flags": progression_flags(conn, config),
        "recent_results": recent_results or [],
    }
    return payload


def format_day_plan(plan_row: dict[str, Any], notes: list[str] | None = None) -> str:
    lines = [f"{plan_row['code']} - {plan_row['title']}"]
    if plan_row.get("equipment"):
        lines.append(f"Equipment: {', '.join(plan_row['equipment'])}")
    for item in plan_row.get("exercises", []):
        row = ensure_dict(item)
        lines.append(f"- {row.get('slot_label')} {row.get('display_name')} | {row.get('prescription_text')}")
    for note in notes or []:
        lines.append(f"- Note: {note}")
    return "\n".join(lines)


def format_today_response(status: dict[str, Any]) -> str:
    today = ensure_dict(status.get("today_plan"))
    plan = ensure_dict(today.get("plan"))
    notes = ensure_string_list(today.get("notes", []))
    lines = ["Today's workout plan", format_day_plan(plan, notes)]
    optional_plan = ensure_dict(today.get("optional_plan"))
    if optional_plan:
        lines.extend(["", "Optional session", format_day_plan(optional_plan)])
    return "\n".join(lines)


def format_start_response(result: dict[str, Any], config: dict[str, Any]) -> str:
    session = ensure_dict(result.get("session"))
    code = str(session.get("training_day_code") or "")
    plan = load_day_plan(config, code)
    prefix = "Workout already active" if not result.get("created") else "Workout started"
    return f"{prefix}: {plan.code} - {plan.title}\n" + format_day_plan(build_plan_row(plan))


def format_log_response(result: dict[str, Any]) -> str:
    created = [ensure_dict(item) for item in result.get("created_sets", []) if isinstance(item, dict)]
    lines = [f"Logged {len(created)} set(s)."]
    for row in created[:4]:
        weight_mode = str(row.get("weight_mode") or "")
        lines.append(
            f"- {row.get('exercise_code')} set {row.get('set_order')}: {row.get('reps')} reps @ {row.get('weight_kg')}kg {weight_mode}"
        )
    return "\n".join(lines)


def format_finish_response(result: dict[str, Any], config: dict[str, Any]) -> str:
    session = ensure_dict(result.get("session"))
    code = str(session.get("training_day_code") or "")
    plan = load_day_plan(config, code)
    lines = [
        f"Finished workout: {plan.code} - {plan.title}",
        f"- Summary: {result.get('summary_path')}",
        f"- Next main session: {result.get('next_main_code')}",
    ]
    for row in result.get("summary", [])[:5]:
        bucket = ensure_dict(row)
        lines.append(
            f"- {bucket.get('exercise_name')}: sets={bucket.get('logged_sets')} | best_reps={bucket.get('best_reps')} | top_weight={bucket.get('top_weight_kg')}"
        )
    return "\n".join(lines)


def format_status_response(status: dict[str, Any]) -> str:
    lines = ["Fitness status"]
    active = ensure_dict(status.get("active_session"))
    if active:
        lines.append(f"- Active session: {active.get('training_day_code')} ({active.get('session_date')})")
    else:
        lines.append("- Active session: none")
    today = ensure_dict(status.get("today_plan"))
    plan = ensure_dict(today.get("plan"))
    lines.append(f"- Next plan: {plan.get('code')} {plan.get('title')}")
    settings = ensure_dict(status.get("settings"))
    lines.append(f"- Barbell empty weight: {settings.get('barbell_empty_weight_kg') or 'unset'}")
    weekly = ensure_dict(status.get("weekly_volume"))
    if weekly:
        top = ", ".join(f"{key}={value}" for key, value in sorted(weekly.items()))
        lines.append(f"- Weekly volume: {top}")
    flags = [ensure_dict(item) for item in status.get("progression_flags", []) if isinstance(item, dict)]
    if flags:
        lines.append(f"- Progression flags: {len(flags)}")
        for item in flags[:3]:
            lines.append(f"  - {item.get('exercise_name')}: {item.get('flag')}")
    return "\n".join(lines)


def parse_command_text(text: str, *, allow_shortcuts: bool = True) -> tuple[str, str]:
    clean = text.strip()
    lower = clean.lower()
    today_values = {"workout today", "what is my workout today", "today workout", "today's workout"}
    if allow_shortcuts:
        today_values.add("today")
    if lower in today_values:
        return "today", ""
    start_values = {"start workout"}
    if allow_shortcuts:
        start_values.add("start")
    if lower in start_values:
        return "start", ""
    finish_values = {"finish workout", "end workout"}
    if allow_shortcuts:
        finish_values.add("finish")
    if lower in finish_values:
        return "finish", ""
    status_values = {"fitness status", "workout status"}
    if allow_shortcuts:
        status_values.add("status")
    if lower in status_values:
        return "status", ""
    if lower.startswith("log "):
        return "log", clean[4:].strip()
    barbell_match = re.match(r"^(?:set\s+)?barbell\s+empty\s+(?P<weight>\d+(?:\.\d+)?)kg$", lower)
    if barbell_match:
        return "set_barbell_empty", barbell_match.group("weight")
    if lower in {"start optional", "start o5", "start optional workout"}:
        return "start_optional", ""
    return "unknown", clean


def supports_command_text(text: str, *, explicit_context: bool = False) -> bool:
    command, _ = parse_command_text(text, allow_shortcuts=explicit_context)
    return command != "unknown"


class FitnessRuntime:
    def __init__(
        self,
        *,
        root: Path = ROOT,
        config_path: Path | None = None,
        db_path: Path | None = None,
        status_path: Path | None = None,
    ) -> None:
        self.root = root
        self.config_path = config_path or (root / "config" / "fitness_agent.yaml")
        self.status_path = status_path or (root / "data" / "fitness-runtime-status.json")
        self.config = load_fitness_config(root, self.config_path)
        sqlite_cfg = ensure_dict(ensure_dict(self.config.get("memory_strategy")).get("sqlite"))
        self.db_path = db_path or (root / str(sqlite_cfg.get("db_path") or ".memory/fitness.db"))
        self.schema_path = root / str(sqlite_cfg.get("schema_file") or "contracts/fitness/sqlite_schema.sql")

    def refresh_config(self) -> dict[str, Any]:
        self.config = load_fitness_config(self.root, self.config_path)
        return self.config

    def current_canonical_hash(self) -> str:
        config = self.refresh_config()
        return str(config.get("_canonical_hash") or "").strip()

    def conn(self) -> sqlite3.Connection:
        self.refresh_config()
        conn = open_conn(self.db_path, self.schema_path)
        get_program_id(conn, self.config)
        return conn

    def snapshot(self, *, action: str = "snapshot", recent_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        conn = self.conn()
        try:
            payload = build_status_payload(
                conn,
                root=self.root,
                db_path=self.db_path,
                config=self.config,
                action=action,
                recent_results=recent_results,
            )
        finally:
            conn.close()
        write_json(self.status_path, payload)
        return payload

    def today(self) -> dict[str, Any]:
        payload = self.snapshot(action="today")
        return {"status": payload, "reply_text": format_today_response(payload)}

    def status(self) -> dict[str, Any]:
        payload = self.snapshot(action="status")
        return {"status": payload, "reply_text": format_status_response(payload)}

    def start(self, *, optional: bool = False) -> dict[str, Any]:
        conn = self.conn()
        try:
            if optional:
                if not OPTIONAL_DAY_CODE:
                    raise ValueError("No optional workout is configured in the current program.")
                code = OPTIONAL_DAY_CODE
            else:
                code = determine_next_main_code(conn)
            result = create_session(
                conn,
                program_id=get_program_id(conn, self.config),
                day_code=code,
                timezone_name=str(ensure_dict(self.config.get("schedule")).get("timezone") or "UTC"),
            )
            status = build_status_payload(
                conn,
                root=self.root,
                db_path=self.db_path,
                config=self.config,
                action="start",
                recent_results=[{"action": "start", "day_code": code, "created": bool(result.get("created"))}],
            )
        finally:
            conn.close()
        write_json(self.status_path, status)
        result["status"] = status
        result["reply_text"] = format_start_response(result, self.config)
        return result

    def log(self, text: str) -> dict[str, Any]:
        conn = self.conn()
        try:
            result = log_sets(conn, text=text, config=self.config)
            status = build_status_payload(
                conn,
                root=self.root,
                db_path=self.db_path,
                config=self.config,
                action="log",
                recent_results=[{"action": "log", "created_set_count": len(result["created_sets"])}],
            )
        finally:
            conn.close()
        write_json(self.status_path, status)
        result["status"] = status
        result["reply_text"] = format_log_response(result)
        return result

    def finish(self) -> dict[str, Any]:
        conn = self.conn()
        try:
            result = finish_session(conn, root=self.root, config=self.config)
            status = build_status_payload(
                conn,
                root=self.root,
                db_path=self.db_path,
                config=self.config,
                action="finish",
                recent_results=[{"action": "finish", "summary_path": result["summary_path"]}],
            )
        finally:
            conn.close()
        write_json(self.status_path, status)
        result["status"] = status
        result["reply_text"] = format_finish_response(result, self.config)
        return result

    def set_barbell_empty(self, weight_kg: float) -> dict[str, Any]:
        conn = self.conn()
        try:
            result = set_barbell_empty_weight(conn, weight_kg)
            status = build_status_payload(
                conn,
                root=self.root,
                db_path=self.db_path,
                config=self.config,
                action="set_barbell_empty",
                recent_results=[{"action": "set_barbell_empty", "weight_kg": weight_kg}],
            )
        finally:
            conn.close()
        write_json(self.status_path, status)
        result["status"] = status
        result["reply_text"] = f"Barbell empty weight set to {weight_kg}kg."
        return result

    def execute_text(self, text: str) -> dict[str, Any]:
        command, body = parse_command_text(text)
        if command == "today":
            return self.today()
        if command == "status":
            return self.status()
        if command == "start":
            return self.start(optional=False)
        if command == "start_optional":
            return self.start(optional=True)
        if command == "log":
            return self.log(body)
        if command == "finish":
            return self.finish()
        if command == "set_barbell_empty":
            return self.set_barbell_empty(float(body))
        raise ValueError(
            "Unsupported fitness command. Use `today`, `start workout`, `log ...`, `finish workout`, or `set barbell empty <kg>kg`."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fitness runtime")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS))
    parser.add_argument("--db-path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", nargs="*", help="fitness command text")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    runtime = FitnessRuntime(
        root=root,
        db_path=Path(args.db_path).expanduser().resolve() if args.db_path else None,
        status_path=Path(args.status_file).expanduser().resolve(),
    )
    command_text = " ".join(args.command).strip() or "status"
    result = runtime.execute_text(command_text)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(str(result.get("reply_text") or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
