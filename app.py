from __future__ import annotations

import asyncio
import csv
import io
import hashlib
import json
import math
import mimetypes
import re
import shutil
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai.service import (
    get_provider,
    get_role_provider,
    provider_public_status,
    public_ai_status,
    role_provider_id,
)
from agents.chief_of_staff import ChiefPlanError, plan_project
from agents.chief_review import ChiefReviewError, run_chief_review
from agents.chief_revision import ChiefRevisionError, run_chief_revision_plan
from agents.research import ResearchError, run_research
from agents.programs import ProgramsError, run_programs
from agents.librarian import search_trusted_library
from library_indexer import extract_library_text
from weather_provider import refresh_weather as refresh_weather_provider, weather_underground_key_available
from grant_provider import GrantDiscoveryError, search_grants_gov

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "mavis.db"

STATIC = ROOT / "static"
REPOSITORY = ROOT / "repository"

# List-price estimates only. These are not billing records.
# OpenAI public model pricing checked 2026-08-30.
OPENAI_LIST_PRICES_PER_MILLION = {
    "gpt-5.6-sol": {"input": 4.00, "output": 20.00},
    "gpt-5.6": {"input": 4.00, "output": 20.00},
    "gpt-5.6-terra": {"input": 2.00, "output": 12.00},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
}
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4.0
DEFAULT_DAILY_ESTIMATED_COST_LIMIT_USD = 1.00
SCHEMA_VERSION = "0.9.3"
MAX_LIBRARY_UPLOAD_BYTES = 100 * 1024 * 1024
LIBRARY_MATERIAL_TYPES = ("Lesson Plan", "Instructor Notes", "Worksheet", "Slideshow", "Handout", "Supply List", "Photo", "Video", "Audio", "Document", "Spreadsheet", "Archive", "Reference", "Other")
PROGRAMS_LIBRARY_DECISIONS = ("reuse", "revise", "create_new")
GRANT_STATUSES = ("Discovered", "Reviewing", "Pursue", "Preparing", "Submitted", "Awarded", "Declined", "Passed")
GRANT_RECOMMENDATIONS = ("Pursue", "Review", "Pass")
EVENT_TYPES = ("Personal", "Institute", "Class / Program", "Farm", "Deadline", "Meeting", "Other")
EVENT_COMMITMENT_LEVELS = ("Light", "Normal", "Major")
EVENT_STATUSES = ("Scheduled", "Cancelled")
PHENOLOGY_STATUSES = ("suggested", "observed", "confirmed", "rejected")
PHENOLOGY_SOURCES = ("human observation", "system suggestion", "imported record")
PHENOLOGY_WATCHLIST_SEEDS = [
    ("Sunchokes","Food & garden plants","Fruit Forest",["emergence","first flower","full bloom","foliage dieback","harvest-ready"]),("Corn","Food & garden plants","Fruit Forest",["emergence","tasseling","silking","ear development","harvest","dry-down"]),("Grapes","Food & garden plants","Fruit Forest",["bud break","leaf-out","bloom","fruit set","veraison","ripe","harvest","leaf fall"]),("Apple","Food & garden plants","Fruit Forest",["bud break","first bloom","full bloom","fruit set","harvest","leaf fall"]),("Garlic","Food & garden plants","Fruit Forest",["emergence","scapes","harvest"]),("Tomatoes","Food & garden plants","Fruit Forest",["first bloom","fruit set","ripening","harvest"]),("Berries","Food & garden plants","Fruit Forest",["first bloom","fruit set","ripe","harvest"]),
    ("Multiflora rose","Wild Appalachian / property","Fruit Forest",["leaf-out","first bloom","full bloom","hips forming","hips ripe","leaf fall"]),("Ironweed","Wild Appalachian / property","Fruit Forest",["emergence","first bloom","full bloom","seed heads","dieback"]),("Goldenrod","Wild Appalachian / property","Fruit Forest",["emergence","first bloom","full bloom","seed heads"]),("Jewelweed","Wild Appalachian / property","Fruit Forest",["emergence","first bloom","seed heads"]),("Milkweed","Wild Appalachian / property","Fruit Forest",["emergence","first bloom","seed pods"]),("Dandelion","Wild Appalachian / property","Fruit Forest",["first bloom","seed heads"]),("Mayapple","Wild Appalachian / property","Fruit Forest",["emergence","first bloom","fruiting"]),("Tulip poplar","Wild Appalachian / property","Fruit Forest",["bud break","first bloom","leaf color","leaf fall"]),("Redbud","Wild Appalachian / property","Fruit Forest",["first bloom","full bloom","leaf-out","leaf fall"]),("Dogwood","Wild Appalachian / property","Fruit Forest",["first bloom","full bloom","leaf color","leaf fall"]),("Maple","Wild Appalachian / property","Fruit Forest",["bud break","leaf color","leaf fall"]),("Black walnut","Wild Appalachian / property","Fruit Forest",["leaf-out","fruit set","leaf color","leaf fall"]),
    ("Toads","Animals / insects / amphibians","Pond",["first adult seen","first calling heard","breeding observed","egg strings observed","first tadpoles","tadpoles developing legs","first tiny toads / metamorphs"]),("Tadpoles","Animals / insects / amphibians","Pond",["first observed","peak abundance","legs developing","metamorphosis","leaving water"]),("Spring peepers","Animals / insects / amphibians","Pond",["first heard","calling peak"]),("Fireflies","Animals / insects / amphibians","Fruit Forest",["first seen","peak abundance"]),("Honey bees","Animals / insects / amphibians","Fruit Forest",["first strong foraging flight","major pollen flow","strong nectar flow","swarm activity","reduced fall activity"]),("Bumblebees","Animals / insects / amphibians","Fruit Forest",["first seen","peak abundance"]),("Hummingbirds","Animals / insects / amphibians","Fruit Forest",["arrival","nesting","departure"]),("Monarchs","Animals / insects / amphibians","Fruit Forest",["first seen","migration / arrival"]),("Cicadas","Animals / insects / amphibians","Fruit Forest",["first heard","emergence"]),
    *((name,"Seasonal / physical indicators","Campus-wide",[name.lower()]) for name in ["First frost","First hard freeze","Last spring frost","First snow","Pond thaw / ice-out","Pond first freeze","Soil workable","First major spring warm-up","First major thunderstorm","Peak fall color","50% leaf color","75% leaf fall"]),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def repository_root() -> Path:
    # Keep repository data beside the active database. In normal use this is
    # the application folder; tests with temporary databases stay isolated.
    return DB_PATH.parent / "repository"


def library_root() -> Path:
    # Durable institutional Library storage is separate from project repository files.
    # Basing it on DB_PATH keeps test and copied Campus instances isolated.
    return DB_PATH.parent / "library"


def library_inbox_root() -> Path:
    return library_root() / "inbox"


def library_catalog_root() -> Path:
    return library_root() / "catalog"


def init_db() -> None:
    REPOSITORY.mkdir(parents=True, exist_ok=True)
    library_inbox_root().mkdir(parents=True, exist_ok=True)
    library_catalog_root().mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS buildings (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'building',
                x INTEGER NOT NULL,
                y INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                home_building_id TEXT REFERENCES buildings(id),
                building_id TEXT NOT NULL REFERENCES buildings(id),
                status TEXT NOT NULL,
                task_id INTEGER,
                updated_at TEXT NOT NULL
            );

            -- v0.8.7: Poe conversational operations foundation.
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                person_type TEXT NOT NULL DEFAULT 'Volunteer',
                status TEXT NOT NULL DEFAULT 'Active',
                contact_info TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                is_primary_user INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_people_name ON people(display_name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_people_status ON people(status,person_type,display_name);

            CREATE TABLE IF NOT EXISTS activity_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 100,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS work_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                activity_category_id INTEGER REFERENCES activity_categories(id) ON DELETE SET NULL,
                participation_type TEXT NOT NULL DEFAULT 'Volunteer',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_minutes INTEGER,
                entry_mode TEXT NOT NULL DEFAULT 'clock',
                work_date TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'Poe',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_work_sessions_one_open_person
                ON work_sessions(person_id) WHERE ended_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_work_sessions_person_date
                ON work_sessions(person_id,started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_work_sessions_project
                ON work_sessions(project_id,started_at DESC);

            CREATE TABLE IF NOT EXISTS work_session_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_session_id INTEGER NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_work_session_audit_session
                ON work_session_audit(work_session_id,created_at DESC,id DESC);

            -- v0.8.7: Vernadette conversational Grant Desk foundation.
            CREATE TABLE IF NOT EXISTS grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funder TEXT NOT NULL,
                title TEXT NOT NULL,
                deadline TEXT,
                amount_min REAL,
                amount_max REAL,
                amount_notes TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                source_key TEXT NOT NULL DEFAULT '',
                opportunity_number TEXT NOT NULL DEFAULT '',
                source_status TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Discovered',
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                notes TEXT NOT NULL DEFAULT '',
                mission_fit INTEGER NOT NULL DEFAULT 3,
                workload INTEGER NOT NULL DEFAULT 3,
                restrictions INTEGER NOT NULL DEFAULT 3,
                strategic_value INTEGER NOT NULL DEFAULT 3,
                recommendation TEXT NOT NULL DEFAULT 'Review',
                assessment_notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'Vernadette',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_grants_deadline ON grants(deadline,status);
            CREATE INDEX IF NOT EXISTS idx_grants_status ON grants(status,updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_grants_project ON grants(project_id,updated_at DESC);

            -- v0.8.7.1: internal Calendar foundation. Events are durable institutional
            -- records and do not imply Google Calendar or external scheduling authority.
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                all_day INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT 'Institute',
                commitment_level TEXT NOT NULL DEFAULT 'Normal',
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Scheduled',
                created_by TEXT NOT NULL DEFAULT 'Human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date,start_time,id);
            CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id,event_date,id);
            CREATE INDEX IF NOT EXISTS idx_events_status ON events(status,event_date,id);

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                owner_agent_id TEXT REFERENCES agents(id),
                status TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                brief TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                decision_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                input_chars INTEGER NOT NULL DEFAULT 0,
                output_chars INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_control (
                id INTEGER PRIMARY KEY CHECK(id=1),
                enabled INTEGER NOT NULL DEFAULT 1,
                daily_estimated_cost_limit_usd REAL NOT NULL DEFAULT 1.0,
                stopped_reason TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                state TEXT NOT NULL,
                current_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chief_request_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_key TEXT NOT NULL UNIQUE,
                normalized_request TEXT NOT NULL,
                original_request TEXT NOT NULL,
                status TEXT NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chief_request_submissions_normalized
                ON chief_request_submissions(normalized_request, updated_at DESC);

            CREATE TABLE IF NOT EXISTS schema_meta (
                id INTEGER PRIMARY KEY CHECK(id=1),
                schema_version TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chief_plans (
                project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                summary TEXT NOT NULL,
                success_criteria_json TEXT NOT NULL,
                questions_json TEXT NOT NULL,
                risk_notes_json TEXT NOT NULL,
                expected_deliverables_json TEXT NOT NULL DEFAULT '[]',
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_artifacts (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                content_json TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS programs_artifacts (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                content_json TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chief_review_artifacts (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                content_json TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliverables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                deliverable_key TEXT NOT NULL,
                deliverable_type TEXT NOT NULL,
                title TEXT NOT NULL,
                purpose TEXT,
                status TEXT NOT NULL,
                content_md TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                verification_json TEXT NOT NULL DEFAULT '[]',
                chief_review_status TEXT,
                chief_review_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id,deliverable_key,version)
            );
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_deliverable_id INTEGER REFERENCES deliverables(id) ON DELETE SET NULL,
                display_name TEXT NOT NULL,
                filename TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                file_kind TEXT NOT NULL,
                mime_type TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'Current',
                created_by TEXT NOT NULL DEFAULT 'Campus',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS briefing_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                brief_json TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT 'Human'
            );
            CREATE INDEX IF NOT EXISTS idx_briefing_snapshots_time ON briefing_snapshots(captured_at DESC);

            -- v0.8.6.1: durable Library foundation only. These tables intentionally
            -- store catalog structure/metadata without uploads, Librarian AI, or web access.
            CREATE TABLE IF NOT EXISTS library_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                collection_type TEXT NOT NULL DEFAULT 'Program',
                subject TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Active',
                created_by TEXT NOT NULL DEFAULT 'Human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_library_collections_status
                ON library_collections(status,collection_type,subject,title);

            CREATE TABLE IF NOT EXISTS library_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER REFERENCES library_collections(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                material_type TEXT NOT NULL DEFAULT 'Other',
                edition_label TEXT NOT NULL DEFAULT '',
                edition_date TEXT,
                status TEXT NOT NULL DEFAULT 'Cataloged',
                source_kind TEXT NOT NULL DEFAULT 'manual',
                source_project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                source_deliverable_id INTEGER REFERENCES deliverables(id) ON DELETE SET NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'Human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_library_materials_collection
                ON library_materials(collection_id,status,material_type,edition_date);
            CREATE INDEX IF NOT EXISTS idx_library_materials_source
                ON library_materials(source_kind,source_project_id,source_deliverable_id);

            -- v0.8.6.9.4: local trusted-document content index. Extracted text is
            -- stored locally and is never populated from Incoming Materials or the web.
            CREATE TABLE IF NOT EXISTS library_material_index (
                material_id INTEGER PRIMARY KEY REFERENCES library_materials(id) ON DELETE CASCADE,
                extraction_status TEXT NOT NULL DEFAULT 'pending',
                extraction_method TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                char_count INTEGER NOT NULL DEFAULT 0,
                source_sha256 TEXT NOT NULL DEFAULT '',
                indexed_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_library_material_index_status
                ON library_material_index(extraction_status,indexed_at DESC);

            -- v0.8.6.4: incoming Library Drop Box. Items here are quarantined
            -- from trusted Catalog search until a later human cataloging release.
            CREATE TABLE IF NOT EXISTS library_inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'Incoming',
                source_kind TEXT NOT NULL DEFAULT 'upload',
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'Human',
                received_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_library_inbox_status
                ON library_inbox(status,received_at DESC);

            -- v0.8.6.9.4: Programs Library First. Every Programs task checks the
            -- trusted Library before a new AI Programs generation is allowed.
            CREATE TABLE IF NOT EXISTS programs_library_preflights (
                task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'Pending',
                decision TEXT NOT NULL DEFAULT '',
                selected_collection_id INTEGER REFERENCES library_collections(id) ON DELETE SET NULL,
                human_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_programs_library_preflights_project
                ON programs_library_preflights(project_id,status,updated_at DESC);

            -- v0.8.6.9.4: durable audit trail for Programs outputs archived only after
            -- the Chief final review receives explicit human approval. This table
            -- intentionally keeps plain source IDs/titles so Library history survives
            -- a later Campus demo reset that clears project workspace tables.
            CREATE TABLE IF NOT EXISTS program_archive_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_project_id INTEGER NOT NULL,
                source_project_title TEXT NOT NULL,
                source_approval_id INTEGER NOT NULL,
                collection_id INTEGER REFERENCES library_collections(id) ON DELETE SET NULL,
                edition_label TEXT NOT NULL DEFAULT '',
                edition_date TEXT NOT NULL,
                status TEXT NOT NULL,
                material_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(source_approval_id)
            );
            CREATE INDEX IF NOT EXISTS idx_program_archive_events_project
                ON program_archive_events(source_project_id,created_at DESC);

            -- v0.8.6.9.4: Weather & Seasons + Personal Weather Station foundation.
            -- Weather networking is isolated from the Librarian and never performs AI calls.
            CREATE TABLE IF NOT EXISTS environment_settings (
                id INTEGER PRIMARY KEY CHECK(id=1),
                location_label TEXT NOT NULL DEFAULT 'Flat Top, West Virginia',
                timezone_name TEXT NOT NULL DEFAULT 'America/New_York',
                latitude REAL,
                longitude REAL,
                seasonal_region TEXT NOT NULL DEFAULT 'Southern Appalachia',
                pws_station_id TEXT NOT NULL DEFAULT 'KWFLATT11',
                pws_provider TEXT NOT NULL DEFAULT 'Weather Underground',
                forecast_source TEXT NOT NULL DEFAULT 'Open-Meteo',
                fallback_provider TEXT NOT NULL DEFAULT 'Open-Meteo',
                live_weather_enabled INTEGER NOT NULL DEFAULT 1,
                last_refresh_at TEXT,
                last_refresh_status TEXT NOT NULL DEFAULT 'Never',
                last_refresh_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_current (
                id INTEGER PRIMARY KEY CHECK(id=1),
                source TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT '',
                station_id TEXT NOT NULL DEFAULT '',
                observed_at TEXT,
                temperature_f REAL,
                feels_like_f REAL,
                humidity_pct REAL,
                dewpoint_f REAL,
                pressure_in REAL,
                wind_mph REAL,
                wind_gust_mph REAL,
                wind_direction_deg REAL,
                precip_rate_in REAL,
                precip_total_in REAL,
                solar_radiation REAL,
                uv_index REAL,
                summary TEXT NOT NULL DEFAULT '',
                latitude REAL,
                longitude REAL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_daily (
                forecast_date TEXT PRIMARY KEY,
                high_f REAL,
                low_f REAL,
                precip_chance INTEGER,
                precip_total_in REAL,
                rain_total_in REAL,
                snow_total_in REAL,
                wind_max_mph REAL,
                wind_gust_max_mph REAL,
                sunrise TEXT,
                sunset TEXT,
                daylight_seconds REAL,
                summary TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                observed_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_weather_daily_date ON weather_daily(forecast_date);

            CREATE TABLE IF NOT EXISTS seasonal_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Seasonal Window',
                start_md TEXT NOT NULL,
                end_md TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Normal',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_seasonal_windows_status ON seasonal_windows(status,start_md,end_md);

            CREATE TABLE IF NOT EXISTS phenology_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                stage TEXT NOT NULL,
                observation_date TEXT NOT NULL,
                location_area TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'observed',
                source TEXT NOT NULL DEFAULT 'human observation',
                notes TEXT NOT NULL DEFAULT '',
                review_agent_id TEXT NOT NULL DEFAULT 'research' REFERENCES agents(id) ON DELETE SET DEFAULT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_phenology_observations_date ON phenology_observations(observation_date DESC,id DESC);
            CREATE INDEX IF NOT EXISTS idx_phenology_observations_status ON phenology_observations(status,observation_date DESC);

            CREATE TABLE IF NOT EXISTS phenology_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, category TEXT NOT NULL, location_area TEXT NOT NULL,
                stages_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'Active', priority TEXT NOT NULL DEFAULT 'Normal',
                notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_phenology_watchlist_status ON phenology_watchlist(status,category,subject);

            CREATE TABLE IF NOT EXISTS playbooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                purpose TEXT NOT NULL,
                owner_agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
                trigger_text TEXT NOT NULL DEFAULT '',
                steps_json TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Draft',
                created_by TEXT NOT NULL DEFAULT 'Human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_playbooks_status ON playbooks(status,updated_at);
            CREATE INDEX IF NOT EXISTS idx_playbooks_project ON playbooks(project_id,status,updated_at);

            CREATE TABLE IF NOT EXISTS institutional_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                memory_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                importance TEXT NOT NULL DEFAULT 'Normal',
                source_kind TEXT NOT NULL DEFAULT 'manual',
                source_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Active',
                created_by TEXT NOT NULL DEFAULT 'Human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_at TEXT,
                review_interval_days INTEGER NOT NULL DEFAULT 180,
                review_due_at TEXT,
                supersedes_id INTEGER REFERENCES institutional_memory(id) ON DELETE SET NULL,
                superseded_by_id INTEGER REFERENCES institutional_memory(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_institutional_memory_status
                ON institutional_memory(status,importance,updated_at);
            CREATE INDEX IF NOT EXISTS idx_institutional_memory_project
                ON institutional_memory(project_id,status,updated_at);
            CREATE INDEX IF NOT EXISTS idx_institutional_memory_review
                ON institutional_memory(status,review_due_at);

            CREATE TABLE IF NOT EXISTS revision_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_approval_id INTEGER REFERENCES approvals(id) ON DELETE SET NULL,
                request_text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS revision_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                request_id INTEGER NOT NULL REFERENCES revision_requests(id) ON DELETE CASCADE,
                revision_number INTEGER NOT NULL,
                summary TEXT NOT NULL,
                task_revisions_json TEXT NOT NULL,
                deliverable_revisions_json TEXT NOT NULL,
                preserve_keys_json TEXT NOT NULL,
                questions_json TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id,revision_number)
            );
            """
        )
        building_columns = {row[1] for row in conn.execute("PRAGMA table_info(buildings)").fetchall()}
        if "kind" not in building_columns:
            conn.execute("ALTER TABLE buildings ADD COLUMN kind TEXT NOT NULL DEFAULT 'building'")
        agent_columns = {row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        if "home_building_id" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN home_building_id TEXT")
        task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "brief" not in task_columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN brief TEXT")

        # v0.8.7: conversational Poe needs an explicit primary-person alias
        # for “me / I / my” and a truthful date-only mode for remembered hours.
        people_columns = {row[1] for row in conn.execute("PRAGMA table_info(people)").fetchall()}
        if "is_primary_user" not in people_columns:
            conn.execute("ALTER TABLE people ADD COLUMN is_primary_user INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_people_one_primary_user ON people(is_primary_user) WHERE is_primary_user=1")
        work_columns = {row[1] for row in conn.execute("PRAGMA table_info(work_sessions)").fetchall()}
        if "entry_mode" not in work_columns:
            conn.execute("ALTER TABLE work_sessions ADD COLUMN entry_mode TEXT NOT NULL DEFAULT 'clock'")
        if "work_date" not in work_columns:
            conn.execute("ALTER TABLE work_sessions ADD COLUMN work_date TEXT")

        # v0.8.7: federal grant discovery source identity. Existing manual
        # Grant Desk rows remain untouched; imported opportunities can be deduplicated.
        grant_columns = {row[1] for row in conn.execute("PRAGMA table_info(grants)").fetchall()}
        for column, ddl in {
            "source_name": "TEXT NOT NULL DEFAULT ''",
            "source_key": "TEXT NOT NULL DEFAULT ''",
            "opportunity_number": "TEXT NOT NULL DEFAULT ''",
            "source_status": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in grant_columns:
                conn.execute(f"ALTER TABLE grants ADD COLUMN {column} {ddl}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_grants_source_identity ON grants(source_name,source_key) WHERE source_key<>''")

        chief_plan_columns = {row[1] for row in conn.execute("PRAGMA table_info(chief_plans)").fetchall()}
        if "expected_deliverables_json" not in chief_plan_columns:
            conn.execute(
                "ALTER TABLE chief_plans ADD COLUMN expected_deliverables_json TEXT NOT NULL DEFAULT '[]'"
            )

        memory_columns = {row[1] for row in conn.execute("PRAGMA table_info(institutional_memory)").fetchall()}
        if "reviewed_at" not in memory_columns:
            conn.execute("ALTER TABLE institutional_memory ADD COLUMN reviewed_at TEXT")
        if "review_interval_days" not in memory_columns:
            conn.execute("ALTER TABLE institutional_memory ADD COLUMN review_interval_days INTEGER NOT NULL DEFAULT 180")
        if "review_due_at" not in memory_columns:
            conn.execute("ALTER TABLE institutional_memory ADD COLUMN review_due_at TEXT")
        if "supersedes_id" not in memory_columns:
            conn.execute("ALTER TABLE institutional_memory ADD COLUMN supersedes_id INTEGER REFERENCES institutional_memory(id) ON DELETE SET NULL")
        if "superseded_by_id" not in memory_columns:
            conn.execute("ALTER TABLE institutional_memory ADD COLUMN superseded_by_id INTEGER REFERENCES institutional_memory(id) ON DELETE SET NULL")
        # Existing memories get a deterministic first review window without changing their content/status.
        existing_memories = conn.execute(
            "SELECT id,created_at,updated_at,reviewed_at,review_interval_days,review_due_at FROM institutional_memory"
        ).fetchall()
        for memory in existing_memories:
            interval = normalize_review_interval(memory["review_interval_days"])
            reviewed = memory["reviewed_at"] or memory["updated_at"] or memory["created_at"] or utc_now()
            due = memory["review_due_at"] or memory_review_due(reviewed, interval)
            conn.execute(
                "UPDATE institutional_memory SET reviewed_at=?,review_interval_days=?,review_due_at=? WHERE id=?",
                (reviewed, interval, due, memory["id"]),
            )

        # v0.8.6.4: Cataloging Desk file linkage. Existing v0.8.6.3 databases
        # are upgraded additively; incoming files remain quarantined until human approval.
        material_columns = {row[1] for row in conn.execute("PRAGMA table_info(library_materials)").fetchall()}
        for column, ddl in {
            "inbox_id": "INTEGER",
            "original_filename": "TEXT NOT NULL DEFAULT ''",
            "stored_filename": "TEXT NOT NULL DEFAULT ''",
            "relative_path": "TEXT NOT NULL DEFAULT ''",
            "mime_type": "TEXT NOT NULL DEFAULT 'application/octet-stream'",
            "size_bytes": "INTEGER NOT NULL DEFAULT 0",
            "sha256": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in material_columns:
                conn.execute(f"ALTER TABLE library_materials ADD COLUMN {column} {ddl}")
        inbox_columns = {row[1] for row in conn.execute("PRAGMA table_info(library_inbox)").fetchall()}
        if "cataloged_material_id" not in inbox_columns:
            conn.execute("ALTER TABLE library_inbox ADD COLUMN cataloged_material_id INTEGER")
        if "cataloged_at" not in inbox_columns:
            conn.execute("ALTER TABLE library_inbox ADD COLUMN cataloged_at TEXT")

        environment_columns = {row[1] for row in conn.execute("PRAGMA table_info(environment_settings)").fetchall()}
        for column, ddl in {
            "pws_station_id": "TEXT NOT NULL DEFAULT 'KWFLATT11'",
            "pws_provider": "TEXT NOT NULL DEFAULT 'Weather Underground'",
            "fallback_provider": "TEXT NOT NULL DEFAULT 'Open-Meteo'",
            "last_refresh_at": "TEXT",
            "last_refresh_status": "TEXT NOT NULL DEFAULT 'Never'",
            "last_refresh_error": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in environment_columns:
                conn.execute(f"ALTER TABLE environment_settings ADD COLUMN {column} {ddl}")
        daily_columns = {row[1] for row in conn.execute("PRAGMA table_info(weather_daily)").fetchall()}
        for column, ddl in {
            "precip_total_in": "REAL", "rain_total_in": "REAL", "snow_total_in": "REAL",
            "wind_max_mph": "REAL", "wind_gust_max_mph": "REAL", "sunrise": "TEXT",
            "sunset": "TEXT", "daylight_seconds": "REAL",
        }.items():
            if column not in daily_columns:
                conn.execute(f"ALTER TABLE weather_daily ADD COLUMN {column} {ddl}")

        ai_call_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_calls)").fetchall()}
        if "project_id" not in ai_call_columns:
            conn.execute("ALTER TABLE ai_calls ADD COLUMN project_id INTEGER")
        if "task_id" not in ai_call_columns:
            conn.execute("ALTER TABLE ai_calls ADD COLUMN task_id INTEGER")

        conn.execute(
            """
            INSERT OR IGNORE INTO ai_control(
                id,enabled,daily_estimated_cost_limit_usd,stopped_reason,updated_at
            ) VALUES(1,1,?,?,?)
            """,
            (DEFAULT_DAILY_ESTIMATED_COST_LIMIT_USD, None, utc_now()),
        )
        now_env = utc_now()
        conn.execute(
            """
            INSERT OR IGNORE INTO environment_settings(
                id,location_label,timezone_name,latitude,longitude,seasonal_region,pws_station_id,pws_provider,forecast_source,fallback_provider,live_weather_enabled,created_at,updated_at
            ) VALUES(1,'Flat Top, West Virginia','America/New_York',37.59,-81.11,'Southern Appalachia','KWFLATT11','Weather Underground','Open-Meteo','Open-Meteo',1,?,?)
            """,
            (now_env, now_env),
        )
        conn.execute(
            "UPDATE environment_settings SET "
            "pws_station_id=CASE WHEN TRIM(COALESCE(pws_station_id,''))='' THEN 'KWFLATT11' ELSE pws_station_id END, "
            "pws_provider=CASE WHEN TRIM(COALESCE(pws_provider,''))='' THEN 'Weather Underground' ELSE pws_provider END, "
            "fallback_provider=CASE WHEN TRIM(COALESCE(fallback_provider,''))='' THEN 'Open-Meteo' ELSE fallback_provider END, "
            "forecast_source=CASE WHEN forecast_source='manual' OR TRIM(COALESCE(forecast_source,''))='' THEN 'Open-Meteo' ELSE forecast_source END, "
            "live_weather_enabled=1, latitude=COALESCE(latitude,37.59), longitude=COALESCE(longitude,-81.11), updated_at=? WHERE id=1",
            (now_env,),
        )
        if int(conn.execute("SELECT COUNT(*) FROM seasonal_windows").fetchone()[0]) == 0:
            conn.executemany(
                """INSERT INTO seasonal_windows(name,category,start_md,end_md,priority,notes,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    ('Meteorological Winter','Season','12-01','02-28','Normal','Baseline seasonal context; customize farm-specific windows separately.','Active',now_env,now_env),
                    ('Meteorological Spring','Season','03-01','05-31','Normal','Baseline seasonal context; customize farm-specific windows separately.','Active',now_env,now_env),
                    ('Meteorological Summer','Season','06-01','08-31','Normal','Baseline seasonal context; customize farm-specific windows separately.','Active',now_env,now_env),
                    ('Meteorological Autumn','Season','09-01','11-30','Normal','Baseline seasonal context; customize farm-specific windows separately.','Active',now_env,now_env),
                ],
            )
        if int(conn.execute("SELECT COUNT(*) FROM phenology_watchlist").fetchone()[0]) == 0:
            conn.executemany("INSERT INTO phenology_watchlist(subject,category,location_area,stages_json,status,priority,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", [(s,c,l,json.dumps(stages),"Active","Normal","",now_env,now_env) for s,c,l,stages in PHENOLOGY_WATCHLIST_SEEDS])

        conn.execute(
            """
            INSERT INTO schema_meta(id,schema_version,updated_at)
            VALUES(1,?,?)
            ON CONFLICT(id) DO UPDATE SET
                schema_version=excluded.schema_version,
                updated_at=excluded.updated_at
            """,
            (SCHEMA_VERSION, utc_now()),
        )
        seed_base(conn)


def seed_base(conn: sqlite3.Connection) -> None:
    buildings = [
        ("manor", "Mavis Manor", "Executive Office", "building", 18, 73),
        ("library", "Library of Mavis", "Research & Institutional Knowledge", "building", 79, 73),
        ("barn", "Coopenheimer Barn", "Programs & Education", "building", 79, 22),
        ("fruit_forest", "Fruit Forest", "Perennial Food, Ecology & Agroforestry", "zone", 35, 50),
    ]
    conn.executemany(
        """
        INSERT INTO buildings(id,name,purpose,kind,x,y) VALUES(?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, purpose=excluded.purpose, kind=excluded.kind,
            x=excluded.x, y=excluded.y
        """,
        buildings,
    )
    now = utc_now()
    # Stable internal IDs are intentionally preserved for workflow compatibility.
    # Display names/titles are the canonical Mavis staff identities.
    agents = [
        ("chief", "Stella", "Chief of Staff", "manor", "manor", "Available", None, now),
        ("programs", "Percy", "Director of Programs & Education", "barn", "barn", "Available", None, now),
        ("research", "Rose", "Director of Research & Archives", "library", "library", "Available", None, now),
        ("caretaker", "Stewart", "Land Steward · Grounds, Infrastructure & Living Systems", "fruit_forest", "fruit_forest", "Available", None, now),
        ("operations", "Poe", "Operations & Volunteer Coordinator", "barn", "barn", "Available", None, now),
        ("grants", "Vernadette", "Grants & Development Officer", "manor", "manor", "Available", None, now),
    ]
    conn.executemany(
        """
        INSERT INTO agents(id,name,role,home_building_id,building_id,status,task_id,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, role=excluded.role, home_building_id=excluded.home_building_id
        """,
        agents,
    )
    # Poe's canonical home is the Coopenheimer Barn. On upgrade, move him there
    # immediately only when he is not in the middle of assigned work; active work
    # keeps its current location and normal completion logic returns him home later.
    conn.execute(
        """
        UPDATE agents
        SET home_building_id='barn',
            building_id=CASE WHEN task_id IS NULL THEN 'barn' ELSE building_id END,
            updated_at=?
        WHERE id='operations'
        """,
        (now,),
    )
    categories = [
        ("admin", "Administration", "Office, records, correspondence, scheduling, and routine administration.", 10),
        ("education", "Education & Program Delivery", "Teaching, class preparation, workshops, demonstrations, and program delivery.", 20),
        ("research", "Research & Archives", "Research, documentation, archives, fact-checking, and institutional knowledge.", 30),
        ("farm_land", "Farm & Land Stewardship", "Gardens, orchard, soil, water, habitat, and general land stewardship.", 40),
        ("animal_care", "Animal Care", "Routine and special care for chickens, ducks, bees, and other animals.", 50),
        ("maintenance", "Maintenance & Infrastructure", "Repairs, buildings, tools, water systems, paths, and infrastructure.", 60),
        ("grants", "Grants & Development", "Grant research, applications, development, donor, and funding work.", 70),
        ("outreach", "Community Outreach", "Community service, partnerships, visitor support, and outreach.", 80),
        ("media", "Media & Communications", "Streaming, photography, video, websites, social media, and communications.", 90),
        ("planning", "Planning & Governance", "Organizational planning, meetings, board/governance, and strategy.", 100),
        ("learning", "Training & Learning", "Formal or informal training, education, skill-building, and learning activities.", 110),
        ("volunteer_coordination", "Volunteer Coordination", "Volunteer onboarding, scheduling, support, and coordination.", 120),
        ("other", "Other", "Work that does not yet fit a standard Mavis activity category.", 999),
    ]
    conn.executemany(
        """
        INSERT INTO activity_categories(code,name,description,sort_order,active)
        VALUES(?,?,?,?,1)
        ON CONFLICT(code) DO UPDATE SET
            name=excluded.name,description=excluded.description,sort_order=excluded.sort_order
        """,
        categories,
    )


def log(conn: sqlite3.Connection, event_type: str, actor: str, message: str) -> None:
    conn.execute(
        "INSERT INTO activity_log(event_type,actor,message,created_at) VALUES(?,?,?,?)",
        (event_type, actor, message, utc_now()),
    )


def rows(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def estimate_tokens_from_chars(char_count: int | None) -> int:
    value = max(0, int(char_count or 0))
    if value == 0:
        return 0
    return max(1, int((value + TOKEN_ESTIMATE_CHARS_PER_TOKEN - 1) // TOKEN_ESTIMATE_CHARS_PER_TOKEN))


def estimate_openai_list_cost(
    provider: str,
    model: str,
    input_chars: int | None,
    output_chars: int | None,
) -> float | None:
    if str(provider).strip().lower() != "openai":
        return None

    price = OPENAI_LIST_PRICES_PER_MILLION.get(str(model).strip().lower())
    if not price:
        return None

    input_tokens = estimate_tokens_from_chars(input_chars)
    output_tokens = estimate_tokens_from_chars(output_chars)
    cost = (
        input_tokens * price["input"] / 1_000_000
        + output_tokens * price["output"] / 1_000_000
    )
    return round(cost, 8)


def enrich_ai_call(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["estimated_input_tokens"] = estimate_tokens_from_chars(item.get("input_chars"))
    item["estimated_output_tokens"] = estimate_tokens_from_chars(item.get("output_chars"))
    item["estimated_list_cost_usd"] = estimate_openai_list_cost(
        str(item.get("provider") or ""),
        str(item.get("model") or ""),
        item.get("input_chars"),
        item.get("output_chars"),
    )
    item["cost_is_estimate"] = True
    return item


def ai_usage_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    # Use the complete local AI-call history for guardrail/project totals.
    # Only the returned recent-call list is truncated for UI payload size.
    raw_calls = rows(conn, "SELECT * FROM ai_calls ORDER BY id DESC")
    enriched = [enrich_ai_call(row) for row in raw_calls]

    today_prefix = utc_now()[:10]
    today_calls = [
        item for item in enriched
        if str(item.get("created_at") or "").startswith(today_prefix)
    ]

    estimated_cost = sum(
        float(item["estimated_list_cost_usd"])
        for item in today_calls
        if item.get("estimated_list_cost_usd") is not None
        and item.get("status") in {"Success", "Responded"}
    )

    project_titles = {
        int(row["id"]): row["title"]
        for row in rows(conn, "SELECT id,title FROM projects")
    }
    project_groups: dict[int, dict[str, Any]] = {}

    for item in enriched:
        project_id = item.get("project_id")
        if project_id is None:
            continue
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            continue

        group = project_groups.setdefault(
            project_id,
            {
                "project_id": project_id,
                "project_title": project_titles.get(project_id, f"Project {project_id}"),
                "calls": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_list_cost_usd": 0.0,
                "priced_calls": 0,
            },
        )
        group["calls"] += 1
        group["estimated_input_tokens"] += int(item["estimated_input_tokens"])
        group["estimated_output_tokens"] += int(item["estimated_output_tokens"])
        if item.get("estimated_list_cost_usd") is not None and item.get("status") in {"Success", "Responded"}:
            group["estimated_list_cost_usd"] += float(item["estimated_list_cost_usd"])
            group["priced_calls"] += 1

    for group in project_groups.values():
        group["estimated_list_cost_usd"] = round(group["estimated_list_cost_usd"], 8)

    return {
        "calls": enriched[:40],
        "today": {
            "date_utc": today_prefix,
            "calls": len(today_calls),
            "estimated_input_tokens": sum(int(item["estimated_input_tokens"]) for item in today_calls),
            "estimated_output_tokens": sum(int(item["estimated_output_tokens"]) for item in today_calls),
            "estimated_openai_list_cost_usd": round(estimated_cost, 8),
        },
        "projects": sorted(
            project_groups.values(),
            key=lambda item: item["project_id"],
            reverse=True,
        )[:20],
        "method": {
            "token_estimate": "characters divided by 4",
            "pricing_basis": "OpenAI list prices checked 2026-08-30",
            "billing_warning": (
                "Estimated list price only. This is not an invoice and does not know whether complimentary tokens, "
                "credits, caching, discounts, or provider-specific billing changed the actual charge."
            ),
        },
    }


def ai_control_state(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT enabled,daily_estimated_cost_limit_usd,stopped_reason,updated_at
        FROM ai_control
        WHERE id=1
        """
    ).fetchone()

    if not row:
        now = utc_now()
        conn.execute(
            """
            INSERT INTO ai_control(
                id,enabled,daily_estimated_cost_limit_usd,stopped_reason,updated_at
            ) VALUES(1,1,?,?,?)
            """,
            (DEFAULT_DAILY_ESTIMATED_COST_LIMIT_USD, None, now),
        )
        row = conn.execute(
            """
            SELECT enabled,daily_estimated_cost_limit_usd,stopped_reason,updated_at
            FROM ai_control WHERE id=1
            """
        ).fetchone()

    usage = ai_usage_summary(conn)["today"]
    limit = max(0.0, float(row["daily_estimated_cost_limit_usd"] or 0.0))
    estimated = float(usage["estimated_openai_list_cost_usd"])
    budget_blocked = limit > 0 and estimated >= limit
    manually_enabled = bool(row["enabled"])

    return {
        "enabled": manually_enabled,
        "effective_enabled": manually_enabled,
        "budget_blocked": budget_blocked,
        "daily_estimated_cost_limit_usd": round(limit, 4),
        "today_estimated_openai_list_cost_usd": round(estimated, 8),
        "remaining_estimated_budget_usd": round(max(0.0, limit - estimated), 8) if limit > 0 else None,
        "stopped_reason": row["stopped_reason"],
        "updated_at": row["updated_at"],
        "inflight_notice": "Stop AI prevents new calls; an HTTP request already in flight may still finish.",
    }


def require_ai_allowed(operation: str, provider_id: str) -> None:
    with db() as conn:
        control = ai_control_state(conn)

    if not control["enabled"]:
        reason = control.get("stopped_reason") or "AI was stopped by the human executive."
        raise RuntimeError(f"AI is stopped. {reason}")

    if control["budget_blocked"] and str(provider_id).strip().lower() == "openai":
        raise RuntimeError(
            "AI estimated-cost guardrail reached. "
            f"Today's OpenAI list-price estimate is ${control['today_estimated_openai_list_cost_usd']:.4f} "
            f"against the ${control['daily_estimated_cost_limit_usd']:.2f} daily limit. "
            "Increase the guardrail or wait for the next UTC day before starting another AI call."
        )


LIBRARY_COLLECTION_TYPES = ("Class", "Program", "Series", "Research", "Policy", "Reference", "Archive", "Other")
LIBRARY_COLLECTION_STATUSES = ("Active", "Archived")


def library_catalog_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return the human-managed Library catalog. This is SQL-only and never calls AI or the network."""
    return rows(
        conn,
        """
        SELECT lc.*,COUNT(lm.id) AS material_count
        FROM library_collections lc
        LEFT JOIN library_materials lm ON lm.collection_id=lc.id
        GROUP BY lc.id
        ORDER BY CASE lc.status WHEN 'Active' THEN 0 ELSE 1 END,lc.updated_at DESC,lc.title COLLATE NOCASE
        """,
    )


def library_inbox_rows(conn: sqlite3.Connection, limit: int = 250) -> list[dict[str, Any]]:
    """Return quarantined incoming Library files. No AI/network access and no Catalog promotion."""
    return rows(
        conn,
        """
        SELECT id,original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,
               source_kind,notes,created_by,received_at,updated_at,cataloged_material_id,cataloged_at
        FROM library_inbox
        WHERE status='Incoming'
        ORDER BY received_at DESC,id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 250), 1000)),),
    )


def library_material_rows(conn: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
    """Return trusted Library material metadata without exposing large extracted text in normal state."""
    return rows(
        conn,
        """
        SELECT lm.*,lc.title AS collection_title,lc.collection_type,lc.subject,
               COALESCE(li.extraction_status,'pending') AS index_status,
               COALESCE(li.extraction_method,'') AS index_method,
               COALESCE(li.char_count,0) AS index_char_count,
               COALESCE(li.indexed_at,'') AS indexed_at,
               COALESCE(li.error,'') AS index_error
        FROM library_materials lm
        LEFT JOIN library_collections lc ON lc.id=lm.collection_id
        LEFT JOIN library_material_index li ON li.material_id=lm.id
        WHERE lm.status='Cataloged'
        ORDER BY lm.updated_at DESC,lm.id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 500), 1000)),),
    )


def library_material_search_rows(conn: sqlite3.Connection, limit: int = 1000) -> list[dict[str, Any]]:
    """Return trusted material metadata plus locally extracted text for deterministic retrieval only."""
    return rows(
        conn,
        """
        SELECT lm.*,lc.title AS collection_title,lc.collection_type,lc.subject,
               COALESCE(li.extraction_status,'pending') AS index_status,
               COALESCE(li.extraction_method,'') AS index_method,
               COALESCE(li.char_count,0) AS index_char_count,
               COALESCE(li.extracted_text,'') AS indexed_text
        FROM library_materials lm
        JOIN library_collections lc ON lc.id=lm.collection_id
        LEFT JOIN library_material_index li ON li.material_id=lm.id
        WHERE lm.status='Cataloged' AND lc.status='Active'
        ORDER BY lm.updated_at DESC,lm.id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 1000), 2000)),),
    )


def _trusted_library_material_path(row: sqlite3.Row | dict[str, Any]) -> Path | None:
    rel = Path(str(row["relative_path"] if isinstance(row, sqlite3.Row) else row.get("relative_path") or ""))
    if not str(rel) or str(rel) == ".":
        return None
    path = (DB_PATH.parent / rel).resolve()
    root = library_catalog_root().resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def index_library_material(conn: sqlite3.Connection, material_id: int, *, force: bool = False) -> dict[str, Any]:
    """Index one human-approved trusted Library file locally. Never reads Incoming Materials or the web."""
    row = conn.execute(
        "SELECT * FROM library_materials WHERE id=? AND status='Cataloged'",
        (int(material_id),),
    ).fetchone()
    if not row:
        raise ValueError("Trusted Library material not found.")
    existing = conn.execute(
        "SELECT * FROM library_material_index WHERE material_id=?", (int(material_id),)
    ).fetchone()
    sha = str(row["sha256"] or "")
    if existing and not force and str(existing["source_sha256"] or "") == sha and str(existing["extraction_status"] or "") != "pending":
        return dict(existing)
    path = _trusted_library_material_path(row)
    if path is None:
        result = {"status":"missing","method":"none","text":"","char_count":0,"error":"Trusted Library file is missing from local storage."}
    else:
        result = extract_library_text(
            path,
            original_filename=str(row["original_filename"] or path.name),
            mime_type=str(row["mime_type"] or ""),
        )
    now = utc_now()
    conn.execute(
        """
        INSERT INTO library_material_index(material_id,extraction_status,extraction_method,extracted_text,char_count,source_sha256,indexed_at,error)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(material_id) DO UPDATE SET
          extraction_status=excluded.extraction_status,extraction_method=excluded.extraction_method,
          extracted_text=excluded.extracted_text,char_count=excluded.char_count,source_sha256=excluded.source_sha256,
          indexed_at=excluded.indexed_at,error=excluded.error
        """,
        (int(material_id),str(result["status"]),str(result["method"]),str(result["text"]),int(result["char_count"]),sha,now,str(result["error"])),
    )
    return {
        "material_id": int(material_id), "extraction_status": str(result["status"]),
        "extraction_method": str(result["method"]), "char_count": int(result["char_count"]),
        "source_sha256": sha, "indexed_at": now, "error": str(result["error"]),
    }


def refresh_library_index(conn: sqlite3.Connection, *, force: bool = False) -> dict[str, Any]:
    """Backfill/rebuild trusted Library indexes. Incoming Materials are structurally excluded."""
    material_ids = [int(r[0]) for r in conn.execute(
        "SELECT id FROM library_materials WHERE status='Cataloged' AND relative_path<>'' ORDER BY id"
    ).fetchall()]
    counts: dict[str, int] = {"indexed":0,"needs_ocr":0,"unsupported":0,"missing":0,"too_large":0,"empty":0,"error":0,"unchanged":0}
    for material_id in material_ids:
        before = conn.execute("SELECT extraction_status,source_sha256 FROM library_material_index WHERE material_id=?", (material_id,)).fetchone()
        row = conn.execute("SELECT sha256 FROM library_materials WHERE id=?", (material_id,)).fetchone()
        if before and not force and str(before["source_sha256"] or "") == str(row["sha256"] or "") and str(before["extraction_status"] or "") != "pending":
            counts["unchanged"] += 1
            continue
        result = index_library_material(conn, material_id, force=force)
        status = str(result.get("extraction_status") or "error")
        counts[status] = counts.get(status, 0) + 1
    return {"materials_checked":len(material_ids), **counts, "local_only":True, "web_access":False, "additional_ai_calls":0}


_PROGRAMS_LIBRARY_STOPWORDS = {
    "the","and","for","with","from","into","about","that","this","these","those","your","our","their",
    "create","develop","build","make","prepare","design","write","program","programs","class","course","workshop",
    "lesson","plan","outline","minute","minutes","all","ages","allages","new","mavis","institute","education",
    "educational","task","project","approved","brief","using","use","need","needs","want","would","should",
}


def programs_library_query(project_title: str, task_title: str, task_brief: str) -> str:
    """Build a topic-heavy deterministic query for Programs Library First.

    Common workflow words are removed so a generic word such as "class" does not
    make every educational holding look relevant.
    """
    combined = " ".join([str(project_title or ""), str(task_title or ""), str(task_brief or "")]).lower()
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", combined):
        if len(token) < 3 or token.isdigit() or token in _PROGRAMS_LIBRARY_STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
        if len(tokens) >= 14:
            break
    if tokens:
        return " ".join(tokens)
    fallback = " ".join(str(project_title or task_title or "program").split()).strip()
    return fallback[:300] or "program"


def _programs_library_preflight_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    try:
        result = json.loads(str(item.get("result_json") or "{}"))
    except (TypeError, json.JSONDecodeError):
        result = {}
    item["result"] = result if isinstance(result, dict) else {}
    return item


def ensure_programs_library_preflight(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    task_brief_override: str | None = None,
) -> dict[str, Any]:
    """Create/read a zero-AI, zero-web Library preflight for one Programs task."""
    task_id = int(task["id"])
    existing = conn.execute(
        "SELECT * FROM programs_library_preflights WHERE task_id=?",
        (task_id,),
    ).fetchone()
    if existing:
        return _programs_library_preflight_public(existing)

    brief = str(task_brief_override or task["brief"] or task["title"] or "")
    query = programs_library_query(str(project["title"] or ""), str(task["title"] or ""), brief)
    result = search_trusted_library(
        query,
        library_catalog_rows(conn),
        library_material_search_rows(conn, limit=1000),
        collection_limit=8,
        material_limit=24,
    )
    found = bool(result.get("collections") or result.get("materials"))
    status = "Pending" if found else "No Match"
    decision = "" if found else "create_new"
    now = utc_now()
    conn.execute(
        """
        INSERT INTO programs_library_preflights(
            task_id,project_id,query,result_json,status,decision,selected_collection_id,
            human_note,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id,int(project["id"]),query,json.dumps(result,ensure_ascii=False),status,decision,None,"",now,now,
        ),
    )
    row = conn.execute("SELECT * FROM programs_library_preflights WHERE task_id=?", (task_id,)).fetchone()
    return _programs_library_preflight_public(row)


def programs_library_context_for_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM programs_library_preflights WHERE task_id=?", (int(task_id),)).fetchone()
    if not row:
        return None
    public = _programs_library_preflight_public(row)
    result = public.get("result") or {}
    context: dict[str, Any] = {
        "query": public.get("query", ""),
        "status": public.get("status", ""),
        "decision": public.get("decision", ""),
        "human_note": public.get("human_note", ""),
        "matched_collections": list(result.get("collections") or [])[:8],
        "matched_materials": list(result.get("materials") or [])[:24],
        "local_only": True,
        "trusted_library_only": True,
        "file_contents_supplied": False,
        "incoming_materials_excluded": True,
    }
    collection_id = public.get("selected_collection_id")
    if collection_id:
        collection = conn.execute(
            "SELECT * FROM library_collections WHERE id=? AND status='Active'",
            (int(collection_id),),
        ).fetchone()
        if collection:
            context["selected_collection"] = dict(collection)
            context["selected_materials"] = rows(
                conn,
                """
                SELECT lm.*,lc.title AS collection_title,lc.subject,
                       COALESCE(li.extraction_status,'pending') AS index_status,
                       COALESCE(li.char_count,0) AS index_char_count
                FROM library_materials lm
                JOIN library_collections lc ON lc.id=lm.collection_id
                LEFT JOIN library_material_index li ON li.material_id=lm.id
                WHERE lm.collection_id=? AND lm.status='Cataloged' AND lc.status='Active'
                ORDER BY lm.edition_date DESC,lm.updated_at DESC,lm.id DESC
                """,
                (int(collection_id),),
            )[:50]
            # Only human-approved trusted indexed text is supplied to Programs.
            # Bound prompt size while preserving multiple source materials.
            content_rows = conn.execute(
                """
                SELECT lm.id,lm.title,lm.material_type,lm.edition_label,li.extraction_method,li.extracted_text
                FROM library_materials lm
                JOIN library_collections lc ON lc.id=lm.collection_id
                JOIN library_material_index li ON li.material_id=lm.id
                WHERE lm.collection_id=? AND lm.status='Cataloged' AND lc.status='Active'
                  AND li.extraction_status='indexed' AND li.extracted_text<>''
                ORDER BY lm.edition_date DESC,lm.updated_at DESC,lm.id DESC
                """,
                (int(collection_id),),
            ).fetchall()
            supplied: list[dict[str, Any]] = []
            remaining = 60000
            for item in content_rows[:12]:
                if remaining <= 0:
                    break
                text = str(item["extracted_text"] or "")[:min(18000, remaining)]
                if not text.strip():
                    continue
                supplied.append({
                    "material_id": int(item["id"]),
                    "title": item["title"],
                    "material_type": item["material_type"],
                    "edition_label": item["edition_label"],
                    "extraction_method": item["extraction_method"],
                    "trusted_local_text": text,
                })
                remaining -= len(text)
            if supplied:
                context["selected_material_contents"] = supplied
                context["file_contents_supplied"] = True
                context["supplied_text_characters"] = sum(len(x["trusted_local_text"]) for x in supplied)
    return context


def materialize_programs_library_reuse(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    collection_id: int,
) -> str:
    """Reuse an approved Library collection locally without a Programs AI call."""
    collection = conn.execute(
        "SELECT * FROM library_collections WHERE id=? AND status='Active'",
        (int(collection_id),),
    ).fetchone()
    if not collection:
        raise RuntimeError("The selected trusted Library collection is no longer active.")
    materials = conn.execute(
        """
        SELECT * FROM library_materials
        WHERE collection_id=? AND status='Cataloged'
        ORDER BY edition_date DESC,updated_at DESC,id DESC
        """,
        (int(collection_id),),
    ).fetchall()

    project_id = int(project["id"])
    task_id = int(task["id"])
    expected = expected_deliverables_for_project(conn, project_id)
    expected_types = {str(item.get("type") or "") for item in expected}
    main_type = "lesson_plan" if "lesson_plan" in expected_types else "program_plan"
    deliverable_title = _expected_title(expected, main_type, str(collection["title"] or "Library Program"))

    material_lines = []
    copied = 0
    folder = _repository_project_dir(conn, project_id)
    for material in materials:
        material_lines.append(
            f"- {material['title']} ({material['material_type']}{' · ' + material['edition_label'] if material['edition_label'] else ''})"
        )
        rel = str(material["relative_path"] or "").strip()
        if not rel:
            continue
        source = (DB_PATH.parent / rel).resolve()
        root = library_catalog_root().resolve()
        if root not in source.parents or not source.is_file():
            continue
        original = str(material["original_filename"] or source.name)
        _, safe = _safe_library_filename(original)
        destination = folder / f"library-{int(material['id']):04d}-{safe}"
        try:
            shutil.copy2(source, destination)
            register_project_file(
                conn,
                project_id=project_id,
                path=destination,
                display_name=str(material["title"] or original),
                version=1,
                status="Current",
                created_by="Library reuse / Human",
            )
            copied += 1
        except OSError:
            continue

    holdings = "\n".join(material_lines) if material_lines else "- No file-level materials are cataloged under this collection yet."
    content = f"""# {deliverable_title}

**Library First decision:** Reuse existing trusted Mavis Institute material.

## Trusted Library collection

- Collection: {collection['title']}
- Type: {collection['collection_type']}
- Subject: {collection['subject'] or 'Not specified'}
- Description: {collection['description'] or 'No description recorded.'}

## Reused holdings

{holdings}

## Provenance

This project output links/reuses human-approved Library of Mavis holdings. No Programs AI call was made to create replacement curriculum. The Chief final review may still flag any project-specific gaps or decisions before public use.
"""
    upsert_deliverable(
        conn,
        project_id=project_id,
        source_task_id=task_id,
        deliverable_type=main_type,
        title=deliverable_title,
        purpose="Reuse trusted Library of Mavis program material instead of generating a duplicate class.",
        content_md=content,
        created_by="Library reuse / Human",
        provider=None,
        model=None,
        verification_items=[],
        status="Draft",
    )
    return (
        f"Programs Library First — reused trusted Library collection '{collection['title']}'. "
        f"{len(materials)} trusted material record(s) linked; {copied} file(s) copied into this project's Repository. "
        "No Programs AI call was made."
    )



def _programs_archive_material_type(deliverable_type: str) -> str:
    return {
        "lesson_plan": "Lesson Plan",
        "program_plan": "Lesson Plan",
        "facilitator_guide": "Instructor Notes",
        "materials_list": "Supply List",
        "participant_handout": "Handout",
        "worksheet": "Worksheet",
        "slideshow": "Slideshow",
        "presentation": "Slideshow",
    }.get(str(deliverable_type or "").strip().lower(), "Document")


def _programs_archive_collection(conn: sqlite3.Connection, project: sqlite3.Row, now: str) -> tuple[int, str]:
    """Choose the institutional collection for an approved Programs package."""
    preflight = conn.execute(
        """
        SELECT * FROM programs_library_preflights
        WHERE project_id=?
        ORDER BY updated_at DESC,task_id DESC
        LIMIT 1
        """,
        (int(project["id"]),),
    ).fetchone()
    if preflight and str(preflight["decision"] or "") == "revise" and preflight["selected_collection_id"]:
        selected = conn.execute(
            "SELECT id,title FROM library_collections WHERE id=? AND status='Active'",
            (int(preflight["selected_collection_id"]),),
        ).fetchone()
        if selected:
            return int(selected["id"]), str(selected["title"])

    # A deliberate Create New decision must create a new institutional collection,
    # even if another collection has a similar title. For a no-match workflow we
    # also create a new collection rather than silently attaching to unrelated work.
    title = " ".join(str(project["title"] or "Programs Project").split()).strip()[:220] or "Programs Project"
    main = conn.execute(
        """
        SELECT deliverable_type FROM deliverables
        WHERE project_id=? AND created_by='Programs' AND status='Approved'
        ORDER BY CASE deliverable_type WHEN 'lesson_plan' THEN 0 WHEN 'program_plan' THEN 1 ELSE 2 END,id
        LIMIT 1
        """,
        (int(project["id"]),),
    ).fetchone()
    collection_type = "Class" if main and str(main["deliverable_type"] or "") == "lesson_plan" else "Program"
    cur = conn.execute(
        """
        INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            title, collection_type, "",
            f"Institutional collection created from human-approved Programs project #{int(project['id'])}.",
            "Active", "Programs + Human Approval", now, now,
        ),
    )
    return int(cur.lastrowid), title


def archive_approved_programs_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    approval_id: int,
) -> dict[str, Any]:
    """Archive current human-approved Programs deliverables into the trusted Library.

    This function is local-only and deterministic. It is intentionally called only
    after the Chief final review is approved by the human. Reuse-only projects do not
    generate replacement Programs outputs and therefore do not create duplicate holdings.
    """
    existing_event = conn.execute(
        "SELECT * FROM program_archive_events WHERE source_approval_id=?",
        (int(approval_id),),
    ).fetchone()
    if existing_event:
        return {**dict(existing_event), "idempotent": True, "additional_ai_calls": 0, "web_access": False}

    project = conn.execute("SELECT * FROM projects WHERE id=?", (int(project_id),)).fetchone()
    if not project:
        raise ValueError("Programs archive project not found.")

    deliverables = conn.execute(
        """
        SELECT d.*
        FROM deliverables d
        LEFT JOIN tasks t ON t.id=d.source_task_id
        WHERE d.project_id=?
          AND d.status='Approved'
          AND d.created_by='Programs'
          AND (t.owner_agent_id='programs' OR t.owner_agent_id IS NULL)
        ORDER BY d.deliverable_type,d.title,d.version,d.id
        """,
        (int(project_id),),
    ).fetchall()

    now = utc_now()
    edition_date = now[:10]
    if not deliverables:
        return {
            "status":"Skipped","material_count":0,"skipped_count":0,
            "reason":"No approved Programs-created deliverables to archive.",
            "additional_ai_calls":0,"web_access":False,
        }

    collection_id, collection_title = _programs_archive_collection(conn, project, now)
    max_version = max(int(row["version"] or 1) for row in deliverables)
    edition_label = f"Approved {edition_date} · Project #{int(project_id)} · v{max_version}"
    collection_dir = library_catalog_root() / f"collection-{collection_id}"
    collection_dir.mkdir(parents=True, exist_ok=True)

    material_ids: list[int] = []
    skipped = 0
    errors: list[str] = []
    copied_paths: list[Path] = []
    for deliverable in deliverables:
        duplicate = conn.execute(
            """
            SELECT id FROM library_materials
            WHERE source_kind='programs_auto_archive' AND source_deliverable_id=? AND status='Cataloged'
            LIMIT 1
            """,
            (int(deliverable["id"]),),
        ).fetchone()
        if duplicate:
            skipped += 1
            continue

        try:
            # Ensure the current deliverable has a concrete Repository file first.
            sync_deliverable_repository_file(conn, int(deliverable["id"]))
            pf = conn.execute(
                """
                SELECT * FROM project_files
                WHERE source_deliverable_id=? AND status='Current'
                ORDER BY id DESC LIMIT 1
                """,
                (int(deliverable["id"]),),
            ).fetchone()
            if not pf:
                raise OSError("Repository file was not available.")
            source = _repository_safe_path(str(pf["relative_path"]))
            if not source.is_file():
                raise OSError("Repository file is missing from local storage.")

            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            safe = _repository_slug(str(deliverable["title"]), fallback="program-output")
            suffix = source.suffix.lower() or ".md"
            stored_name = f"program-{int(project_id):04d}-output-{int(deliverable['id']):04d}-v{int(deliverable['version'])}-{safe}{suffix}"
            destination = collection_dir / stored_name
            if destination.exists():
                destination = collection_dir / f"{digest[:12]}-{stored_name}"
            shutil.copy2(source, destination)
            copied_paths.append(destination)
            relative_path = destination.relative_to(DB_PATH.parent).as_posix()
            size = int(destination.stat().st_size)
            mime_type = mimetypes.guess_type(destination.name)[0] or "text/markdown"
            notes = (
                f"Automatically archived after human approval of Chief final review #{int(approval_id)}. "
                f"Source project: {project['title']} (#{int(project_id)}). "
                f"Source output: {deliverable['title']} · deliverable #{int(deliverable['id'])} · version {int(deliverable['version'])}."
            )
            cur = conn.execute(
                """
                INSERT INTO library_materials(
                    collection_id,title,material_type,edition_label,edition_date,status,source_kind,
                    source_project_id,source_deliverable_id,notes,created_by,created_at,updated_at,
                    inbox_id,original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    collection_id,str(deliverable["title"]),_programs_archive_material_type(str(deliverable["deliverable_type"])),
                    edition_label,edition_date,"Cataloged","programs_auto_archive",int(project_id),int(deliverable["id"]),
                    notes,"Programs + Human Approval",now,now,None,source.name,destination.name,relative_path,mime_type,size,digest,
                ),
            )
            material_id = int(cur.lastrowid)
            material_ids.append(material_id)
            index_library_material(conn, material_id, force=True)
        except Exception as exc:
            errors.append(f"{deliverable['title']}: {str(exc)[:240]}")
            # If this deliverable failed after copying but before successful cataloging,
            # remove only its orphan destination. Successfully cataloged files remain.
            if copied_paths:
                candidate = copied_paths[-1]
                linked = conn.execute(
                    "SELECT id FROM library_materials WHERE relative_path=? LIMIT 1",
                    (candidate.relative_to(DB_PATH.parent).as_posix(),),
                ).fetchone()
                if not linked:
                    candidate.unlink(missing_ok=True)
                    copied_paths.pop()

    status = "Archived" if material_ids and not errors else "Partial" if material_ids else "Failed"
    conn.execute(
        "UPDATE library_collections SET updated_at=? WHERE id=?",
        (now,int(collection_id)),
    )
    conn.execute(
        """
        INSERT INTO program_archive_events(
            source_project_id,source_project_title,source_approval_id,collection_id,
            edition_label,edition_date,status,material_count,skipped_count,error_text,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(project_id),str(project["title"]),int(approval_id),int(collection_id),edition_label,edition_date,
            status,len(material_ids),skipped,"\n".join(errors)[:4000],now,
        ),
    )
    log(
        conn,"library_archive","Programs",
        f"Programs Auto-Archive {status.lower()}: {len(material_ids)} approved output(s) archived to '{collection_title}' after final human approval; {skipped} already archived.",
    )
    return {
        "status":status,"collection_id":collection_id,"collection_title":collection_title,
        "edition_label":edition_label,"material_ids":material_ids,"material_count":len(material_ids),
        "skipped_count":skipped,"errors":errors,"additional_ai_calls":0,"web_access":False,
    }


def _safe_library_filename(filename: str) -> tuple[str, str]:
    raw = str(filename or '').replace('\\', '/').split('/')[-1].strip()
    if not raw or raw in {'.', '..'}:
        raise HTTPException(status_code=400, detail='A valid filename is required.')
    original = raw[:240]
    safe = re.sub(r'[^A-Za-z0-9._ -]+', '_', original).strip(' .')
    safe = re.sub(r'\s+', ' ', safe)[:180] or 'library-file'
    return original, safe


def library_foundation_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Local, deterministic Library status. No AI or network access."""
    collection_count = int(conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0])
    active_count = int(conn.execute("SELECT COUNT(*) FROM library_collections WHERE status='Active'").fetchone()[0])
    material_count = int(conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0])
    incoming_count = int(conn.execute("SELECT COUNT(*) FROM library_inbox WHERE status='Incoming'").fetchone()[0])
    indexed_count = int(conn.execute("SELECT COUNT(*) FROM library_material_index WHERE extraction_status='indexed'").fetchone()[0])
    needs_ocr_count = int(conn.execute("SELECT COUNT(*) FROM library_material_index WHERE extraction_status='needs_ocr'").fetchone()[0])
    auto_archive_count = int(conn.execute("SELECT COUNT(*) FROM program_archive_events WHERE status IN ('Archived','Partial')").fetchone()[0])
    return {
        "enabled": True,
        "phase": "programs_auto_archive",
        "collections": collection_count,
        "active_collections": active_count,
        "materials": material_count,
        "incoming_materials": incoming_count,
        "indexed_materials": indexed_count,
        "needs_ocr_materials": needs_ocr_count,
        "local_only": True,
        "additional_ai_calls": 0,
        "catalog_enabled": True,
        "catalog_search_enabled": True,
        "uploads_enabled": True,
        "cataloging_desk_enabled": True,
        "trusted_material_file_access_enabled": True,
        "librarian_agent_enabled": True,
        "librarian_retrieval_enabled": True,
        "librarian_web_access": False,
        "librarian_trusted_library_only": True,
        "librarian_incoming_materials_excluded": True,
        "programs_library_first_enabled": True,
        "programs_library_first_human_choice": True,
        "programs_library_first_web_access": False,
        "local_document_indexing_enabled": True,
        "local_document_indexing_web_access": False,
        "local_document_indexing_ai_calls": 0,
        "indexed_file_types": ["PDF text", "DOCX", "PPTX", "XLSX", "TXT/MD/CSV/JSON/XML/HTML"],
        "scanned_pdf_ocr_enabled": False,
        "program_auto_archive_enabled": True,
        "program_auto_archive_final_human_approval_only": True,
        "program_auto_archive_web_access": False,
        "program_auto_archive_ai_calls": 0,
        "program_auto_archive_events": auto_archive_count,
    }


def _valid_md(value: str) -> str:
    clean = str(value or '').strip()
    if not re.fullmatch(r"\d{2}-\d{2}", clean):
        raise ValueError("Seasonal dates must use MM-DD.")
    month, day = [int(x) for x in clean.split('-')]
    datetime(2000, month, day)
    return clean


def _md_active(md: str, start_md: str, end_md: str) -> bool:
    if start_md <= end_md:
        return start_md <= md <= end_md
    return md >= start_md or md <= end_md


def _store_weather_refresh(conn: sqlite3.Connection, result: dict[str, Any]) -> None:
    now = utc_now()
    current = result.get("current") or {}
    if current:
        conn.execute(
            """INSERT INTO weather_current(
                   id,source,source_kind,station_id,observed_at,temperature_f,feels_like_f,humidity_pct,dewpoint_f,pressure_in,
                   wind_mph,wind_gust_mph,wind_direction_deg,precip_rate_in,precip_total_in,solar_radiation,uv_index,summary,latitude,longitude,updated_at
               ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   source=excluded.source,source_kind=excluded.source_kind,station_id=excluded.station_id,observed_at=excluded.observed_at,
                   temperature_f=excluded.temperature_f,feels_like_f=excluded.feels_like_f,humidity_pct=excluded.humidity_pct,
                   dewpoint_f=excluded.dewpoint_f,pressure_in=excluded.pressure_in,wind_mph=excluded.wind_mph,
                   wind_gust_mph=excluded.wind_gust_mph,wind_direction_deg=excluded.wind_direction_deg,precip_rate_in=excluded.precip_rate_in,
                   precip_total_in=excluded.precip_total_in,solar_radiation=excluded.solar_radiation,uv_index=excluded.uv_index,
                   summary=excluded.summary,latitude=excluded.latitude,longitude=excluded.longitude,updated_at=excluded.updated_at""",
            (current.get("source", ""), current.get("source_kind", ""), current.get("station_id", ""), current.get("observed_at"),
             current.get("temperature_f"), current.get("feels_like_f"), current.get("humidity_pct"), current.get("dewpoint_f"), current.get("pressure_in"),
             current.get("wind_mph"), current.get("wind_gust_mph"), current.get("wind_direction_deg"), current.get("precip_rate_in"), current.get("precip_total_in"),
             current.get("solar_radiation"), current.get("uv_index"), current.get("summary", ""), current.get("latitude"), current.get("longitude"), now),
        )
    for day in result.get("forecast") or []:
        conn.execute(
            """INSERT INTO weather_daily(forecast_date,high_f,low_f,precip_chance,precip_total_in,rain_total_in,snow_total_in,wind_max_mph,wind_gust_max_mph,sunrise,sunset,daylight_seconds,summary,source,observed_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(forecast_date) DO UPDATE SET high_f=excluded.high_f,low_f=excluded.low_f,precip_chance=excluded.precip_chance,
                   precip_total_in=excluded.precip_total_in,rain_total_in=excluded.rain_total_in,snow_total_in=excluded.snow_total_in,
                   wind_max_mph=excluded.wind_max_mph,wind_gust_max_mph=excluded.wind_gust_max_mph,sunrise=excluded.sunrise,sunset=excluded.sunset,
                   daylight_seconds=excluded.daylight_seconds,summary=excluded.summary,source=excluded.source,observed_at=excluded.observed_at,updated_at=excluded.updated_at""",
            (day.get("forecast_date"),day.get("high_f"),day.get("low_f"),day.get("precip_chance"),day.get("precip_total_in"),day.get("rain_total_in"),
             day.get("snow_total_in"),day.get("wind_max_mph"),day.get("wind_gust_max_mph"),day.get("sunrise"),day.get("sunset"),day.get("daylight_seconds"),
             day.get("summary", ""),day.get("source", "Open-Meteo"),now,now),
        )
    errors = result.get("errors") or []
    status = "PWS + forecast" if result.get("pws_connected") else ("Forecast fallback" if (result.get("forecast") or result.get("current")) else "Failed")
    conn.execute(
        "UPDATE environment_settings SET last_refresh_at=?,last_refresh_status=?,last_refresh_error=?,forecast_source=?,updated_at=? WHERE id=1",
        (now,status,"; ".join(errors)[:1000],"Open-Meteo",now),
    )


def moon_cycle_summary(local_now: datetime) -> dict[str, Any]:
    """Approximate lunar phase locally without network access.

    Uses the mean synodic month and a well-known new-moon epoch. This is
    intentionally planning/display precision, not an astronomical ephemeris.
    """
    synodic_days = 29.53058867
    epoch = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    now_utc = local_now.astimezone(timezone.utc)
    age_days = ((now_utc - epoch).total_seconds() / 86400.0) % synodic_days
    fraction = age_days / synodic_days
    illumination = (1.0 - math.cos(2.0 * math.pi * fraction)) / 2.0
    phase_index = int((fraction * 8.0) + 0.5) % 8
    phases = [
        ("New Moon", "🌑"),
        ("Waxing Crescent", "🌒"),
        ("First Quarter", "🌓"),
        ("Waxing Gibbous", "🌔"),
        ("Full Moon", "🌕"),
        ("Waning Gibbous", "🌖"),
        ("Last Quarter", "🌗"),
        ("Waning Crescent", "🌘"),
    ]
    phase_name, icon = phases[phase_index]
    days_to_new = (synodic_days - age_days) % synodic_days
    if days_to_new < 0.01:
        days_to_new = 0.0
    days_to_full = ((synodic_days / 2.0) - age_days) % synodic_days
    return {
        "phase": phase_name,
        "icon": icon,
        "illumination_pct": round(illumination * 100.0, 1),
        "age_days": round(age_days, 1),
        "next_full_moon": (local_now + timedelta(days=days_to_full)).date().isoformat(),
        "next_new_moon": (local_now + timedelta(days=days_to_new)).date().isoformat(),
        "calculation": "local_mean_synodic_cycle",
        "network_access": False,
        "additional_ai_calls": 0,
    }


def environment_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM environment_settings WHERE id=1").fetchone()
    settings = dict(row) if row else {
        "location_label": "Flat Top, West Virginia", "timezone_name": "America/New_York",
        "seasonal_region": "Southern Appalachia", "forecast_source": "Open-Meteo", "live_weather_enabled": 1,
        "pws_station_id": "KWFLATT11", "pws_provider": "Weather Underground", "latitude": 37.59, "longitude": -81.11,
    }
    tz_name = settings.get("timezone_name") or "America/New_York"
    try:
        local_now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        tz_name = "America/New_York"
        try:
            local_now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            local_now = datetime.now(timezone.utc)
    md = local_now.strftime("%m-%d")
    windows = rows(conn, "SELECT * FROM seasonal_windows ORDER BY category,name,id")
    phenology = rows(conn, "SELECT * FROM phenology_observations ORDER BY observation_date DESC,id DESC LIMIT 50")
    watchlist = rows(conn, "SELECT * FROM phenology_watchlist ORDER BY category,subject,id")
    for item in watchlist:
        try: item["stages"] = json.loads(item.pop("stages_json"))
        except Exception: item["stages"] = []
    active = [w for w in windows if w.get("status") == "Active" and _md_active(md, w["start_md"], w["end_md"])]
    today = local_now.date().isoformat()
    weather = rows(conn, "SELECT * FROM weather_daily WHERE forecast_date>=? ORDER BY forecast_date LIMIT 10", (today,))
    current_row = conn.execute("SELECT * FROM weather_current WHERE id=1").fetchone()
    current = dict(current_row) if current_row else None
    season = next((w["name"].replace("Meteorological ", "") for w in active if w.get("category") == "Season"), "Season not set")
    pws_key = weather_underground_key_available()
    last_refresh_at = settings.get("last_refresh_at")
    last_refresh_status = settings.get("last_refresh_status") or "Never"
    last_refresh_error = settings.get("last_refresh_error") or ""
    error_lc = last_refresh_error.lower()

    if current and current.get("source_kind") == "personal_weather_station":
        pws_status = "Connected"
        pws_status_detail = "KWFLATT11 is supplying direct personal weather station observations."
    elif not pws_key:
        pws_status = "API key needed"
        pws_status_detail = "Add WEATHER_UNDERGROUND_API_KEY to .env to read KWFLATT11 directly."
    elif not last_refresh_at:
        pws_status = "Awaiting refresh"
        pws_status_detail = "The API key is configured; refresh weather to test the PWS connection."
    elif "pws:" in error_lc and ("401" in error_lc or "unauthorized" in error_lc):
        pws_status = "Authorization failed"
        pws_status_detail = "Weather Underground rejected the configured API key. Open-Meteo fallback can still supply regional conditions."
    elif "pws:" in error_lc and ("timed out" in error_lc or "timeout" in error_lc):
        pws_status = "Timed out"
        pws_status_detail = "The PWS request timed out. Regional fallback weather may still be available."
    elif "pws:" in error_lc:
        pws_status = "Unavailable"
        pws_status_detail = "The PWS refresh failed; see the last-refresh detail below. Regional fallback weather may still be available."
    else:
        pws_status = "Awaiting refresh"
        pws_status_detail = "The PWS key is configured, but no direct KWFLATT11 observation has been stored yet."

    has_fallback_current = bool(current and current.get("source_kind") != "personal_weather_station")
    if last_refresh_status in {"PWS + forecast", "Forecast fallback"} and (weather or has_fallback_current):
        forecast_status = "Connected"
    elif not last_refresh_at:
        forecast_status = "Awaiting refresh"
    elif "forecast:" in error_lc and ("timed out" in error_lc or "timeout" in error_lc):
        forecast_status = "Timed out"
    elif "forecast:" in error_lc:
        forecast_status = "Unavailable"
    elif weather:
        forecast_status = "Stored data"
    else:
        forecast_status = "Unavailable"

    return {
        "enabled": True,
        "phase": "weather_seasons_pws",
        "location_label": settings.get("location_label"),
        "timezone_name": tz_name,
        "seasonal_region": settings.get("seasonal_region"),
        "latitude": settings.get("latitude"),
        "longitude": settings.get("longitude"),
        "pws_station_id": settings.get("pws_station_id") or "KWFLATT11",
        "pws_provider": settings.get("pws_provider") or "Weather Underground",
        "pws_api_key_configured": pws_key,
        "pws_connection_status": pws_status,
        "pws_status_detail": pws_status_detail,
        "forecast_connection_status": forecast_status,
        "current_conditions": current,
        "local_date": today,
        "season": season,
        "moon": moon_cycle_summary(local_now),
        "active_seasonal_windows": active,
        "seasonal_windows": windows,
        "phenology_observations": phenology,
        "phenology_watchlist": watchlist,
        "forecast_days": weather,
        "forecast_source": settings.get("forecast_source") or "Open-Meteo",
        "fallback_provider": settings.get("fallback_provider") or "Open-Meteo",
        "live_weather_enabled": bool(settings.get("live_weather_enabled")),
        "last_refresh_at": last_refresh_at,
        "last_refresh_status": last_refresh_status,
        "last_refresh_error": last_refresh_error,
        "weather_network_access": True,
        "librarian_network_access": False,
        "additional_ai_calls": 0,
        "internal_calendar_enabled": True,
        "calendar_integration_enabled": False,
        "automatic_rescheduling_enabled": False,
    }


def system_health(conn: sqlite3.Connection) -> dict[str, Any]:
    required_tables = {
        "projects","tasks","approvals","notes","activity_log","ai_calls","ai_control","people","activity_categories","work_sessions","work_session_audit","grants","events",
        "chief_plans","research_artifacts","programs_artifacts","chief_review_artifacts",
        "workflow_runs","chief_request_submissions","schema_meta","deliverables","revision_requests","revision_plans","project_files","institutional_memory","playbooks","briefing_snapshots",
        "library_collections","library_materials","library_material_index","library_inbox","programs_library_preflights","program_archive_events",
        "environment_settings","weather_current","weather_daily","seasonal_windows","phenology_observations","phenology_watchlist",
    }
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing_tables = sorted(required_tables - tables)

    required_ai_columns = {"project_id","task_id"}
    ai_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(ai_calls)").fetchall()
    }
    missing_ai_columns = sorted(required_ai_columns - ai_columns)
    chief_plan_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(chief_plans)").fetchall()
    }
    missing_chief_plan_columns = sorted(
        {"expected_deliverables_json"} - chief_plan_columns
    )
    memory_columns = {row[1] for row in conn.execute("PRAGMA table_info(institutional_memory)").fetchall()}
    missing_memory_columns = sorted(
        {"reviewed_at","review_interval_days","review_due_at","supersedes_id","superseded_by_id"} - memory_columns
    )

    material_columns = {row[1] for row in conn.execute("PRAGMA table_info(library_materials)").fetchall()}
    missing_library_material_columns = sorted(
        {"inbox_id","original_filename","stored_filename","relative_path","mime_type","size_bytes","sha256"} - material_columns
    )
    inbox_columns = {row[1] for row in conn.execute("PRAGMA table_info(library_inbox)").fetchall()}
    missing_library_inbox_columns = sorted({"cataloged_material_id","cataloged_at"} - inbox_columns)

    schema_row = conn.execute(
        "SELECT schema_version,updated_at FROM schema_meta WHERE id=1"
    ).fetchone()

    active_runs = int(
        conn.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE state='Running'"
        ).fetchone()[0]
    )
    interrupted_projects = int(
        conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='Execution Interrupted'"
        ).fetchone()[0]
    )

    ok = not missing_tables and not missing_ai_columns and not missing_chief_plan_columns and not missing_memory_columns and not missing_library_material_columns and not missing_library_inbox_columns and bool(schema_row)
    return {
        "ok": ok,
        "schema_version": schema_row["schema_version"] if schema_row else None,
        "target_schema_version": SCHEMA_VERSION,
        "missing_tables": missing_tables,
        "missing_ai_columns": missing_ai_columns,
        "missing_chief_plan_columns": missing_chief_plan_columns,
        "missing_memory_columns": missing_memory_columns,
        "missing_library_material_columns": missing_library_material_columns,
        "missing_library_inbox_columns": missing_library_inbox_columns,
        "active_workflow_journals": active_runs,
        "interrupted_projects": interrupted_projects,
    }


def set_workflow_run(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    state: str,
    current_task_id: int | None = None,
    last_error: str | None = None,
    increment_retry: bool = False,
) -> None:
    now = utc_now()
    existing = conn.execute(
        "SELECT * FROM workflow_runs WHERE project_id=?",
        (project_id,),
    ).fetchone()

    retry_count = int(existing["retry_count"]) if existing else 0
    if increment_retry:
        retry_count += 1

    started_at = existing["started_at"] if existing and existing["started_at"] else now
    conn.execute(
        """
        INSERT INTO workflow_runs(
            project_id,state,current_task_id,started_at,updated_at,last_error,retry_count
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(project_id) DO UPDATE SET
            state=excluded.state,
            current_task_id=excluded.current_task_id,
            started_at=excluded.started_at,
            updated_at=excluded.updated_at,
            last_error=excluded.last_error,
            retry_count=excluded.retry_count
        """,
        (
            project_id,
            state,
            current_task_id,
            started_at,
            now,
            last_error,
            retry_count,
        ),
    )


def reconcile_interrupted_workflows() -> list[int]:
    """Make stale in-process work explicit after an app/server restart."""
    recovered: list[int] = []

    with db() as conn:
        candidates = conn.execute(
            """
            SELECT DISTINCT p.id,p.title,p.status
            FROM projects p
            LEFT JOIN workflow_runs wr ON wr.project_id=p.id
            WHERE p.status='Active'
               OR wr.state='Running'
            ORDER BY p.id
            """
        ).fetchall()

        for project in candidates:
            project_id = int(project["id"])
            now = utc_now()

            # A stale "Running" journal does not override a project that already
            # reached a durable human-decision state before shutdown.
            if project["status"] == "Awaiting Execution Review":
                set_workflow_run(
                    conn,
                    project_id,
                    state="Awaiting Human Review",
                    current_task_id=None,
                    last_error=None,
                )
                continue
            if project["status"] == "Completed":
                set_workflow_run(
                    conn,
                    project_id,
                    state="Completed",
                    current_task_id=None,
                    last_error=None,
                )
                continue
            if project["status"] == "Needs Revision":
                set_workflow_run(
                    conn,
                    project_id,
                    state="Needs Revision",
                    current_task_id=None,
                    last_error=None,
                )
                continue
            if project["status"] == "Awaiting Approval":
                set_workflow_run(
                    conn,
                    project_id,
                    state="Awaiting Plan Approval",
                    current_task_id=None,
                    last_error=None,
                )
                continue
            if project["status"] == "Awaiting Revision Approval":
                set_workflow_run(
                    conn,
                    project_id,
                    state="Awaiting Revision Approval",
                    current_task_id=None,
                    last_error=None,
                )
                continue

            stale_tasks = conn.execute(
                """
                SELECT id,title
                FROM tasks
                WHERE project_id=? AND status='In Progress'
                ORDER BY sequence,id
                """,
                (project_id,),
            ).fetchall()

            for task in stale_tasks:
                recovery_result = (
                    "Recovery — the Campus restarted while this task was in progress. "
                    "No completion is assumed. Use Retry / Resume Workflow to run this task again."
                )
                conn.execute(
                    """
                    UPDATE tasks
                    SET status='Blocked',
                        result=CASE
                            WHEN result IS NULL OR TRIM(result)='' THEN ?
                            ELSE result
                        END,
                        updated_at=?
                    WHERE id=?
                    """,
                    (recovery_result, now, int(task["id"])),
                )

            conn.execute(
                "UPDATE projects SET status='Execution Interrupted',updated_at=? WHERE id=?",
                (now, project_id),
            )
            set_workflow_run(
                conn,
                project_id,
                state="Interrupted",
                current_task_id=int(stale_tasks[0]["id"]) if stale_tasks else None,
                last_error="Campus restarted while the workflow was active.",
            )
            reset_agents(conn)
            log(
                conn,
                "recovery",
                "System",
                (
                    f"Detected unfinished workflow after restart: {project['title']}. "
                    "Completed tasks were preserved; unfinished work now requires an explicit Retry / Resume Workflow."
                ),
            )
            recovered.append(project_id)

    return recovered


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def expected_deliverables_for_project(
    conn: sqlite3.Connection,
    project_id: int,
) -> list[dict[str, str]]:
    row = conn.execute(
        "SELECT expected_deliverables_json FROM chief_plans WHERE project_id=?",
        (project_id,),
    ).fetchone()
    if not row:
        return []

    output: list[dict[str, str]] = []
    for item in _safe_json_list(row["expected_deliverables_json"]):
        if not isinstance(item, dict):
            continue
        deliverable_type = str(item.get("type") or "project_output").strip().lower()
        title = str(item.get("title") or deliverable_type.replace("_", " ").title()).strip()
        purpose = str(item.get("purpose") or "").strip()
        if title:
            output.append({
                "type": deliverable_type,
                "title": title,
                "purpose": purpose,
            })
    return output[:12]


def _expected_title(
    expected: list[dict[str, str]],
    deliverable_type: str,
    fallback: str,
) -> str:
    for item in expected:
        if item.get("type") == deliverable_type and item.get("title"):
            return item["title"]
    return fallback


def _deliverable_key(deliverable_type: str, source_task_id: int | None) -> str:
    return (
        f"{deliverable_type}:task:{source_task_id}"
        if source_task_id is not None
        else f"{deliverable_type}:project"
    )


def latest_revision_request(
    conn: sqlite3.Connection,
    project_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM revision_requests
        WHERE project_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()


def latest_revision_plan(
    conn: sqlite3.Connection,
    project_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM revision_plans
        WHERE project_id=?
        ORDER BY revision_number DESC,id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()


def active_revision_plan(
    conn: sqlite3.Connection,
    project_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM revision_plans
        WHERE project_id=? AND status='Executing'
        ORDER BY revision_number DESC,id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()


def revision_task_instruction(
    conn: sqlite3.Connection,
    project_id: int,
    task_id: int,
) -> str | None:
    plan = active_revision_plan(conn, project_id)
    if not plan:
        return None
    for item in _safe_json_list(plan["task_revisions_json"]):
        if not isinstance(item, dict):
            continue
        try:
            candidate = int(item.get("task_id"))
        except (TypeError, ValueError):
            continue
        if candidate == int(task_id):
            text = str(item.get("revision_brief") or "").strip()
            return text or None
    return None


def revision_context_for_project(
    conn: sqlite3.Connection,
    project_id: int,
) -> dict[str, Any] | None:
    plan = latest_revision_plan(conn, project_id)
    if not plan:
        return None
    request = conn.execute(
        "SELECT * FROM revision_requests WHERE id=?",
        (plan["request_id"],),
    ).fetchone()
    return {
        "revision_number": int(plan["revision_number"]),
        "status": plan["status"],
        "summary": plan["summary"],
        "human_request": request["request_text"] if request else "",
        "task_revisions": _safe_json_list(plan["task_revisions_json"]),
        "deliverable_revisions": _safe_json_list(plan["deliverable_revisions_json"]),
        "preserve_deliverable_keys": _safe_json_list(plan["preserve_keys_json"]),
    }


def _latest_deliverable_for_key(
    conn: sqlite3.Connection,
    project_id: int,
    deliverable_key: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM deliverables
        WHERE project_id=? AND deliverable_key=?
        ORDER BY version DESC,id DESC
        LIMIT 1
        """,
        (project_id, deliverable_key),
    ).fetchone()


def _repository_slug(value: str, *, fallback: str = "file") -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", str(value or "")).strip().lower()
    value = re.sub(r"[\s._-]+", "-", value).strip("-")
    return (value[:80] or fallback)


def _repository_project_dir(conn: sqlite3.Connection, project_id: int) -> Path:
    project = conn.execute("SELECT title FROM projects WHERE id=?", (project_id,)).fetchone()
    title = project["title"] if project else f"project-{project_id}"
    prefix = f"project-{project_id:04d}-"
    REPOSITORY.mkdir(parents=True, exist_ok=True)
    for child in REPOSITORY.iterdir():
        if child.is_dir() and child.name.startswith(prefix):
            return child
    folder = REPOSITORY / f"{prefix}{_repository_slug(title, fallback='project')}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _repository_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf": return "pdf"
    if ext in {".ppt", ".pptx", ".odp"}: return "slides"
    if ext in {".doc", ".docx", ".odt"}: return "document"
    if ext in {".xls", ".xlsx", ".ods", ".csv"}: return "spreadsheet"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}: return "image"
    if ext in {".txt", ".md", ".rtf"}: return "text"
    if ext in {".zip", ".7z", ".tar", ".gz"}: return "archive"
    return "other"


def _repository_safe_path(relative_path: str) -> Path:
    root = REPOSITORY.resolve()
    target = (REPOSITORY / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Repository path escaped the repository root.")
    return target


def register_project_file(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    path: Path,
    display_name: str | None = None,
    source_deliverable_id: int | None = None,
    version: int = 1,
    status: str = "Current",
    created_by: str = "Campus",
) -> int:
    path = path.resolve()
    root = REPOSITORY.resolve()
    if root not in path.parents:
        raise ValueError("Project files must live inside the Campus repository directory.")
    relative_path = path.relative_to(root).as_posix()
    now = utc_now()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    conn.execute(
        """
        INSERT INTO project_files(
            project_id,source_deliverable_id,display_name,filename,relative_path,
            file_kind,mime_type,version,status,created_by,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(relative_path) DO UPDATE SET
            project_id=excluded.project_id,
            source_deliverable_id=COALESCE(excluded.source_deliverable_id,project_files.source_deliverable_id),
            display_name=excluded.display_name,
            filename=excluded.filename,
            file_kind=excluded.file_kind,
            mime_type=excluded.mime_type,
            version=excluded.version,
            status=excluded.status,
            created_by=excluded.created_by,
            updated_at=excluded.updated_at
        """,
        (
            project_id, source_deliverable_id, display_name or path.stem, path.name,
            relative_path, _repository_kind(path), mime_type, max(1,int(version)),
            status, created_by[:80], now, now,
        ),
    )
    row = conn.execute("SELECT id FROM project_files WHERE relative_path=?", (relative_path,)).fetchone()
    return int(row["id"])


def sync_deliverable_repository_file(conn: sqlite3.Connection, deliverable_id: int) -> int | None:
    row = conn.execute("SELECT * FROM deliverables WHERE id=?", (deliverable_id,)).fetchone()
    if not row:
        return None
    folder = _repository_project_dir(conn, int(row["project_id"]))
    filename = (
        f"output-{int(row['id']):04d}-v{int(row['version'])}-"
        f"{_repository_slug(row['title'], fallback='output')}.md"
    )
    path = folder / filename
    path.write_text(str(row["content_md"] or ""), encoding="utf-8")
    file_status = "Previous" if row["status"] == "Superseded" else "Current"
    file_id = register_project_file(
        conn,
        project_id=int(row["project_id"]),
        path=path,
        display_name=row["title"],
        source_deliverable_id=int(row["id"]),
        version=int(row["version"]),
        status=file_status,
        created_by=row["created_by"] or "Campus",
    )
    # Any repository file tied to an older version of the same deliverable key
    # becomes Previous once a newer version exists.
    conn.execute(
        """
        UPDATE project_files
        SET status='Previous',updated_at=?
        WHERE project_id=? AND source_deliverable_id IN (
            SELECT id FROM deliverables
            WHERE project_id=? AND deliverable_key=? AND version<?
        )
        """,
        (utc_now(), int(row["project_id"]), int(row["project_id"]), row["deliverable_key"], int(row["version"])),
    )
    return file_id


def sync_repository_from_deliverables(conn: sqlite3.Connection) -> int:
    count = 0
    for row in conn.execute("SELECT id FROM deliverables ORDER BY id").fetchall():
        try:
            if sync_deliverable_repository_file(conn, int(row["id"])) is not None:
                count += 1
        except OSError:
            continue
    return count


def rescan_repository(conn: sqlite3.Connection) -> int:
    REPOSITORY.mkdir(parents=True, exist_ok=True)
    # First ensure every current/previous deliverable has a concrete Markdown file.
    sync_repository_from_deliverables(conn)
    pattern = re.compile(r"^project-(\d{4,})-")
    for folder in REPOSITORY.iterdir():
        if not folder.is_dir():
            continue
        match = pattern.match(folder.name)
        if not match:
            continue
        project_id = int(match.group(1))
        if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            rel = path.resolve().relative_to(REPOSITORY.resolve()).as_posix()
            existing = conn.execute("SELECT id FROM project_files WHERE relative_path=?", (rel,)).fetchone()
            if existing:
                continue
            register_project_file(
                conn,
                project_id=project_id,
                path=path,
                display_name=path.stem.replace("-", " ").title(),
                version=1,
                status="Current",
                created_by="Campus / Agent file",
            )
    return int(conn.execute("SELECT COUNT(*) FROM project_files").fetchone()[0])


def upsert_deliverable(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    source_task_id: int | None,
    deliverable_type: str,
    title: str,
    purpose: str,
    content_md: str,
    created_by: str,
    provider: str | None,
    model: str | None,
    verification_items: list[str] | None = None,
    status: str = "Draft",
    version: int | None = None,
) -> int:
    now = utc_now()
    key = _deliverable_key(deliverable_type, source_task_id)
    verification_items = [
        str(item).strip()
        for item in (verification_items or [])
        if str(item).strip()
    ][:20]

    latest = _latest_deliverable_for_key(conn, project_id, key)
    revision = active_revision_plan(conn, project_id)

    # During an approved revision run, only outputs explicitly queued by the
    # Chief revision plan get a new version. Preserved outputs are untouched
    # even when their source task is rerun for another output.
    if revision and latest:
        if latest["status"] != "Revision Queued":
            return int(latest["id"])
        target_version = int(latest["version"]) + 1
    elif version is not None:
        target_version = int(version)
    elif latest:
        target_version = int(latest["version"])
    else:
        target_version = 1

    conn.execute(
        """
        INSERT INTO deliverables(
            project_id,source_task_id,deliverable_key,deliverable_type,title,purpose,
            status,content_md,version,created_by,provider,model,verification_json,
            chief_review_status,chief_review_note,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,deliverable_key,version) DO UPDATE SET
            title=excluded.title,
            purpose=excluded.purpose,
            status=CASE
                WHEN deliverables.status='Approved' THEN deliverables.status
                ELSE excluded.status
            END,
            content_md=excluded.content_md,
            created_by=excluded.created_by,
            provider=excluded.provider,
            model=excluded.model,
            verification_json=excluded.verification_json,
            chief_review_status=NULL,
            chief_review_note=NULL,
            updated_at=excluded.updated_at
        """,
        (
            project_id,
            source_task_id,
            key,
            deliverable_type,
            title[:220],
            purpose[:800],
            status,
            content_md.strip(),
            target_version,
            created_by[:80],
            provider,
            model,
            json.dumps(verification_items, ensure_ascii=False),
            None,
            None,
            now,
            now,
        ),
    )

    row = conn.execute(
        """
        SELECT id FROM deliverables
        WHERE project_id=? AND deliverable_key=? AND version=?
        """,
        (project_id, key, target_version),
    ).fetchone()

    if revision and latest and target_version > int(latest["version"]):
        conn.execute(
            """
            UPDATE deliverables
            SET status='Superseded',updated_at=?
            WHERE id=?
            """,
            (now, int(latest["id"])),
        )
        sync_deliverable_repository_file(conn, int(latest["id"]))

    deliverable_id = int(row["id"])
    sync_deliverable_repository_file(conn, deliverable_id)
    return deliverable_id



def _md_bullets(items: list[Any]) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else "- None recorded."


def materialize_research_deliverables(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    artifact: dict[str, Any],
    provider: str,
    model: str,
) -> list[int]:
    project_id = int(project["id"])
    task_id = int(task["id"])
    expected = expected_deliverables_for_project(conn, project_id)
    verification = [
        str(item) for item in artifact.get("verification_needed", [])
        if str(item).strip()
    ]
    uncertainties = [
        str(item) for item in artifact.get("uncertainties", [])
        if str(item).strip()
    ]

    research_md = f"""# {_expected_title(expected, "research_brief", f"{project['title']} — Research Brief")}

## Executive Summary
{artifact.get("executive_summary", "")}

## Findings
{_md_bullets(artifact.get("findings", []))}

## Practical Recommendations
{_md_bullets(artifact.get("practical_recommendations", []))}

## Uncertainties / Limitations
{_md_bullets(uncertainties)}

## Verification Before Public Use
{_md_bullets(verification)}

## Research Handoff
{artifact.get("handoff_note", "")}

---
Internal Research output. This does not claim autonomous web verification or authorize external action.
"""

    verification_md = f"""# {_expected_title(expected, "verification_checklist", f"{project['title']} — Verification Checklist")}

Use this checklist before material from this project is presented as externally verified or published.

## Claims / Items to Verify
{_md_bullets(verification)}

## Known Uncertainties
{_md_bullets(uncertainties)}

## Source Boundary
This checklist was assembled locally from the structured Research artifact. No additional AI call was used to create it.
"""

    ids = [
        upsert_deliverable(
            conn,
            project_id=project_id,
            source_task_id=task_id,
            deliverable_type="research_brief",
            title=_expected_title(expected, "research_brief", f"{project['title']} — Research Brief"),
            purpose="Preserve the completed internal Research findings and recommendations.",
            content_md=research_md,
            created_by="Research",
            provider=provider,
            model=model,
            verification_items=verification,
        ),
        upsert_deliverable(
            conn,
            project_id=project_id,
            source_task_id=task_id,
            deliverable_type="verification_checklist",
            title=_expected_title(expected, "verification_checklist", f"{project['title']} — Verification Checklist"),
            purpose="Collect verification items and uncertainties before public use.",
            content_md=verification_md,
            created_by="Research",
            provider=provider,
            model=model,
            verification_items=verification,
            status="Verify First" if verification else "Draft",
        ),
    ]
    return ids


def materialize_programs_deliverables(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    artifact: dict[str, Any],
    provider: str,
    model: str,
) -> list[int]:
    project_id = int(project["id"])
    task_id = int(task["id"])
    expected = expected_deliverables_for_project(conn, project_id)
    expected_types = {item.get("type") for item in expected}
    main_type = "lesson_plan" if "lesson_plan" in expected_types else "program_plan"
    verification = [
        str(item) for item in artifact.get("verification_flags", [])
        if str(item).strip()
    ]

    run_lines: list[str] = []
    for item in artifact.get("run_of_show", []):
        if not isinstance(item, dict):
            continue
        run_lines.append(
            f"### {item.get('minutes', 0)} min — {item.get('segment', 'Segment')}\n"
            f"**Purpose:** {item.get('purpose', '')}\n\n"
            f"**Facilitator action:** {item.get('facilitator_action', '')}"
        )
    run_md = "\n\n".join(run_lines) or "No run of show recorded."

    main_title = _expected_title(
        expected,
        main_type,
        str(artifact.get("deliverable_title") or f"{project['title']} — Final Program Plan"),
    )
    main_md = f"""# {main_title}

## Program Summary
{artifact.get("program_summary", "")}

## Audience
{artifact.get("audience", "") or "Not specified."}

## Duration
{artifact.get("duration_minutes", 0)} minutes

## Objectives
{_md_bullets(artifact.get("objectives", []))}

## Run of Show
{run_md}

## Participant Activities
{_md_bullets(artifact.get("participant_activities", []))}

## Research Integration
{_md_bullets(artifact.get("research_integration", []))}

## Verification Before Public Use
{_md_bullets(verification)}

---
Internal Programs output assembled locally from the structured Programs artifact.
"""

    facilitator_title = _expected_title(
        expected,
        "facilitator_guide",
        f"{project['title']} — Facilitator Guide",
    )
    facilitator_md = f"""# {facilitator_title}

## Purpose
Use this guide alongside the main program plan.

## Session Flow
{run_md}

## Facilitator Notes
{_md_bullets(artifact.get("facilitator_notes", []))}

## Participant Activities
{_md_bullets(artifact.get("participant_activities", []))}

## Verification Reminders
{_md_bullets(verification)}
"""

    materials_title = _expected_title(
        expected,
        "materials_list",
        f"{project['title']} — Materials & Supplies",
    )
    materials_md = f"""# {materials_title}

## Materials
{_md_bullets(artifact.get("materials", []))}

## Preparation Notes
{_md_bullets(artifact.get("facilitator_notes", []))}

---
Generated locally from the approved Programs artifact; no purchasing action occurred.
"""

    handout_title = _expected_title(
        expected,
        "participant_handout",
        f"{project['title']} — Participant Handout",
    )
    handout_md = f"""# {handout_title}

## What This Session Is About
{artifact.get("program_summary", "")}

## What Participants Should Learn
{_md_bullets(artifact.get("objectives", []))}

## Key Activities
{_md_bullets(artifact.get("participant_activities", []))}

## Take-Home / Resource Ideas
{_md_bullets(artifact.get("handout_or_resource_ideas", []))}

## Verify Before Sharing Publicly
{_md_bullets(verification)}

---
Participant-facing draft. Review and verify flagged items before public distribution.
"""

    ids: list[int] = []
    for deliverable_type, title, purpose, content in [
        (
            main_type,
            main_title,
            "Provide the main usable educational program or lesson plan.",
            main_md,
        ),
        (
            "facilitator_guide",
            facilitator_title,
            "Provide practical facilitator actions and notes.",
            facilitator_md,
        ),
        (
            "materials_list",
            materials_title,
            "Provide a clean preparation and materials list.",
            materials_md,
        ),
        (
            "participant_handout",
            handout_title,
            "Provide a participant-facing draft resource.",
            handout_md,
        ),
    ]:
        ids.append(
            upsert_deliverable(
                conn,
                project_id=project_id,
                source_task_id=task_id,
                deliverable_type=deliverable_type,
                title=title,
                purpose=purpose,
                content_md=content,
                created_by="Programs",
                provider=provider,
                model=model,
                verification_items=verification,
                status="Verify First" if verification and deliverable_type == "participant_handout" else "Draft",
            )
        )
    return ids


def materialize_caretaker_deliverables(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    result: str,
) -> list[int]:
    project_id = int(project["id"])
    task_id = int(task["id"])
    expected = expected_deliverables_for_project(conn, project_id)
    expected_types = {item.get("type") for item in expected}

    deliverable_type = (
        "maintenance_checklist"
        if "maintenance_checklist" in expected_types
        else "project_proposal"
        if "project_proposal" in expected_types
        else "grounds_brief"
    )
    title = _expected_title(
        expected,
        deliverable_type,
        f"{project['title']} — Grounds & Stewardship Brief",
    )
    content = f"""# {title}

## Approved Internal Task
{task["brief"] or task["title"]}

## Current Internal Result
{result}

---
This v0.8.7 Caretaker output is assembled from the current simulated Caretaker task result. It is not yet a real Caretaker AI artifact.
"""
    return [
        upsert_deliverable(
            conn,
            project_id=project_id,
            source_task_id=task_id,
            deliverable_type=deliverable_type,
            title=title,
            purpose="Preserve the current grounds, maintenance, or stewardship output.",
            content_md=content,
            created_by="Caretaker",
            provider=None,
            model=None,
        )
    ]


def materialize_chief_deliverables(
    conn: sqlite3.Connection,
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    artifact: dict[str, Any],
    provider: str,
    model: str,
) -> list[int]:
    project_id = int(project["id"])
    task_id = int(task["id"])
    expected = expected_deliverables_for_project(conn, project_id)

    summary_title = _expected_title(
        expected,
        "executive_summary",
        f"{project['title']} — Chief Executive Summary",
    )

    def review_items(items: list[Any]) -> str:
        output: list[str] = []
        for item in items:
            if isinstance(item, dict):
                label = str(item.get("criterion") or item.get("deliverable") or item.get("deliverable_key") or "Item")
                status = str(item.get("status") or "")
                note = str(item.get("evidence") or item.get("note") or "")
                output.append(f"- **{status.replace('_', ' ').title()} — {label}**" + (f": {note}" if note else ""))
            elif str(item).strip():
                output.append(f"- {item}")
        return "\n".join(output) if output else "- None recorded."

    summary_md = f"""# {summary_title}

## Executive Summary
{artifact.get("executive_summary", "")}

## Chief Recommendation
**{str(artifact.get("approval_recommendation", "review")).replace("_", " ").upper()}**

## Success Criteria Review
{review_items(artifact.get("success_criteria_review", []))}

## Deliverable Review
{review_items(artifact.get("deliverable_review", []))}

## Research / Programs Alignment
{_md_bullets(artifact.get("research_programs_alignment", []))}

## Gaps or Conflicts
{_md_bullets(artifact.get("gaps_or_conflicts", []))}

## Verify Before Public Use
{_md_bullets(artifact.get("verification_before_public_use", []))}

## Recommended Revisions
{_md_bullets(artifact.get("recommended_revisions", []))}

## Executive Decisions Needed
{_md_bullets(artifact.get("executive_decisions_needed", []))}

## Final Package
{artifact.get("final_package_summary", "")}

## Handoff
{artifact.get("handoff_note", "")}

---
Internal executive review. Human approval does not authorize external action.
"""

    ids = [
        upsert_deliverable(
            conn,
            project_id=project_id,
            source_task_id=task_id,
            deliverable_type="executive_summary",
            title=summary_title,
            purpose="Summarize the completed internal package and its readiness for human decision.",
            content_md=summary_md,
            created_by="Chief of Staff",
            provider=provider,
            model=model,
            verification_items=[
                str(item) for item in artifact.get("verification_before_public_use", [])
                if str(item).strip()
            ],
            status="Approval Ready",
        )
    ]

    # If the plan explicitly requested a decision memo, the same Chief review
    # is enough to build it locally without another model call.
    if any(item.get("type") == "decision_memo" for item in expected):
        memo_title = _expected_title(
            expected,
            "decision_memo",
            f"{project['title']} — Decision Memo",
        )
        memo_md = f"""# {memo_title}

## Decision
{str(artifact.get("approval_recommendation", "review")).replace("_", " ").title()}

## Why
{artifact.get("executive_summary", "")}

## Decisions Needed
{_md_bullets(artifact.get("executive_decisions_needed", []))}

## Conditions / Verification
{_md_bullets(artifact.get("verification_before_public_use", []))}
"""
        ids.append(
            upsert_deliverable(
                conn,
                project_id=project_id,
                source_task_id=task_id,
                deliverable_type="decision_memo",
                title=memo_title,
                purpose="Provide a concise decision memo from the final Chief review.",
                content_md=memo_md,
                created_by="Chief of Staff",
                provider=provider,
                model=model,
                verification_items=artifact.get("verification_before_public_use", []),
                status="Approval Ready",
            )
        )
    return ids


def deliverable_coverage(
    conn: sqlite3.Connection,
    project_id: int,
) -> dict[str, Any]:
    expected = expected_deliverables_for_project(conn, project_id)
    rows_now = rows(
        conn,
        """
        SELECT *
        FROM deliverables
        WHERE project_id=? AND status!='Superseded'
        ORDER BY deliverable_type,title,id
        """,
        (project_id,),
    )
    produced_types = {row["deliverable_type"] for row in rows_now}
    missing = [
        item for item in expected
        if item.get("type") not in produced_types
    ]
    return {
        "expected": expected,
        "produced": rows_now,
        "missing": missing,
        "expected_count": len(expected),
        "produced_count": len(rows_now),
        "missing_count": len(missing),
    }


def apply_chief_deliverable_review(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    artifact: dict[str, Any],
) -> None:
    reviews = artifact.get("deliverable_review")
    if not isinstance(reviews, list):
        reviews = []

    by_key = {
        str(item.get("deliverable_key") or ""): item
        for item in reviews
        if isinstance(item, dict)
    }

    by_title = {
        str(item.get("deliverable") or "").strip().lower(): item
        for item in reviews
        if isinstance(item, dict) and str(item.get("deliverable") or "").strip()
    }

    deliverable_rows = conn.execute(
        """
        SELECT *
        FROM deliverables
        WHERE project_id=? AND status!='Superseded'
        """,
        (project_id,),
    ).fetchall()

    recommendation = str(artifact.get("approval_recommendation") or "review")
    now = utc_now()

    for row in deliverable_rows:
        item = by_key.get(str(row["deliverable_key"]))
        if item is None:
            item = by_title.get(str(row["title"]).strip().lower())

        review_status = str(item.get("status") if item else "").strip().lower()
        note = str(item.get("note") if item else "").strip()

        if review_status == "ready":
            status = "Approval Ready"
        elif review_status == "needs_verification":
            status = "Verify First"
        elif review_status in {"needs_revision", "not_ready"}:
            status = "Needs Revision"
        elif row["deliverable_type"] == "executive_summary":
            status = "Approval Ready"
        elif recommendation == "approve_internal":
            status = "Approval Ready"
        elif recommendation == "revise":
            status = "Needs Revision"
        elif recommendation == "hold":
            status = "Needs Revision"
        else:
            status = "Chief Reviewed"

        conn.execute(
            """
            UPDATE deliverables
            SET status=?,chief_review_status=?,chief_review_note=?,updated_at=?
            WHERE id=?
            """,
            (
                status,
                review_status or None,
                note or None,
                now,
                int(row["id"]),
            ),
        )


def approval_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return approvals enriched with project stage and Chief final-review context."""
    approval_items = rows(conn, "SELECT * FROM approvals ORDER BY id DESC")
    if not approval_items:
        return []

    project_status = {
        int(row["id"]): row["status"]
        for row in rows(conn, "SELECT id,status FROM projects")
    }

    review_rows = rows(
        conn,
        """
        SELECT project_id,content_json,provider,model,created_at
        FROM chief_review_artifacts
        ORDER BY created_at DESC
        """,
    )

    review_by_project: dict[int, dict[str, Any]] = {}
    for row in review_rows:
        project_id = int(row["project_id"])
        if project_id in review_by_project:
            continue
        artifact = _safe_json_object(row["content_json"])
        review_by_project[project_id] = {
            "artifact": artifact,
            "provider": row["provider"],
            "model": row["model"],
            "created_at": row["created_at"],
        }

    enriched: list[dict[str, Any]] = []
    for approval in approval_items:
        item = dict(approval)
        project_id = int(item["project_id"])
        review = review_by_project.get(project_id)
        title = str(item.get("title") or "")
        is_final_review = bool(review) and title.startswith("Chief final review:")

        if is_final_review:
            artifact = review["artifact"]
            recommendation = str(
                artifact.get("approval_recommendation") or ""
            ).strip().lower()
            if recommendation not in {"approve_internal", "revise", "hold"}:
                recommendation = "review"

            verification = artifact.get("verification_before_public_use")
            gaps = artifact.get("gaps_or_conflicts")
            revisions = artifact.get("recommended_revisions")
            decisions = artifact.get("executive_decisions_needed")

            item.update(
                {
                    "stage": "final_review",
                    "chief_recommendation": recommendation,
                    "chief_review_title": str(artifact.get("review_title") or ""),
                    "chief_review_summary": str(artifact.get("executive_summary") or ""),
                    "verification_count": len(verification) if isinstance(verification, list) else 0,
                    "gap_count": len(gaps) if isinstance(gaps, list) else 0,
                    "revision_count": len(revisions) if isinstance(revisions, list) else 0,
                    "executive_decision_count": len(decisions) if isinstance(decisions, list) else 0,
                    "review_provider": review["provider"],
                    "review_model": review["model"],
                }
            )
        else:
            if title.startswith("Approve revision plan:"):
                approval_stage = "revision_plan"
            elif project_status.get(project_id) == "Awaiting Approval":
                approval_stage = "plan"
            else:
                approval_stage = "other"
            item.update(
                {
                    "stage": approval_stage,
                    "chief_recommendation": None,
                    "chief_review_title": "",
                    "chief_review_summary": "",
                    "verification_count": 0,
                    "gap_count": 0,
                    "revision_count": 0,
                    "executive_decision_count": 0,
                    "review_provider": None,
                    "review_model": None,
                }
            )

        enriched.append(item)

    return enriched


def repair_approval_invariants() -> dict[str, int]:
    """Repair missing/duplicate approval gates without changing human decisions."""
    repaired = 0
    superseded = 0

    with db() as conn:
        projects = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE status IN ('Awaiting Approval','Awaiting Revision Approval','Awaiting Execution Review')
            ORDER BY id
            """
        ).fetchall()

        for project in projects:
            project_id = int(project["id"])
            final_stage = project["status"] == "Awaiting Execution Review"
            revision_stage = project["status"] == "Awaiting Revision Approval"
            title_prefix = (
                "Chief final review:"
                if final_stage
                else "Approve revision plan:"
                if revision_stage
                else "Approve Chief's plan:"
            )

            pending = conn.execute(
                """
                SELECT id
                FROM approvals
                WHERE project_id=?
                  AND status='Pending'
                  AND title LIKE ?
                ORDER BY id
                """,
                (project_id, f"{title_prefix}%"),
            ).fetchall()

            if len(pending) > 1:
                keep_id = int(pending[0]["id"])
                duplicate_ids = [int(row["id"]) for row in pending[1:]]
                placeholders = ",".join("?" for _ in duplicate_ids)
                conn.execute(
                    f"""
                    UPDATE approvals
                    SET status='Superseded',updated_at=?
                    WHERE id IN ({placeholders})
                    """,
                    (utc_now(), *duplicate_ids),
                )
                superseded += len(duplicate_ids)
                log(
                    conn,
                    "recovery",
                    "System",
                    f"Superseded {len(duplicate_ids)} duplicate pending approval gate(s) for project #{project_id}.",
                )
                pending = [pending[0]]

            if pending:
                continue

            now = utc_now()

            if revision_stage:
                revision_plan = conn.execute(
                    """
                    SELECT *
                    FROM revision_plans
                    WHERE project_id=? AND status='Awaiting Approval'
                    ORDER BY revision_number DESC,id DESC
                    LIMIT 1
                    """,
                    (project_id,),
                ).fetchone()
                if not revision_plan:
                    continue
                title = (
                    f"Approve revision plan: {project['title']} — "
                    f"Revision {revision_plan['revision_number']}"
                )
                summary = (
                    f"Recovered selective revision-plan approval gate. "
                    f"{revision_plan['summary']} "
                    "Approval authorizes only the selected internal revision work; no external action is authorized."
                )[:4000]
            elif final_stage:
                review_row = conn.execute(
                    """
                    SELECT content_json
                    FROM chief_review_artifacts
                    WHERE project_id=?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (project_id,),
                ).fetchone()
                if not review_row:
                    continue

                artifact = _safe_json_object(review_row["content_json"])
                recommendation = str(
                    artifact.get("approval_recommendation") or "review"
                ).replace("_", " ").upper()
                executive_summary_text = str(
                    artifact.get("executive_summary")
                    or "The Chief final review is complete."
                )
                summary = (
                    f"Recovered approval gate. Chief recommendation: {recommendation}. "
                    f"{executive_summary_text} "
                    "Approval accepts the internal package only and does not authorize an external action."
                )[:4000]
                title = f"Chief final review: {project['title']}"
            else:
                plan = conn.execute(
                    "SELECT summary FROM chief_plans WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                if not plan:
                    continue

                title = f"Approve Chief's plan: {project['title']}"
                summary = (
                    f"Recovered plan approval gate. {plan['summary']} "
                    "Approval authorizes only the internal campus workflow; no external action is authorized."
                )[:4000]

            conn.execute(
                """
                INSERT INTO approvals(
                    project_id,title,summary,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (project_id, title, summary, "Pending", now, now),
            )
            repaired += 1
            log(
                conn,
                "recovery",
                "System",
                f"Recreated a missing human approval gate for project #{project_id}.",
            )

    return {"repaired": repaired, "superseded": superseded}


def executive_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    approval_items = approval_rows(conn)
    pending_items = [item for item in approval_items if item["status"] == "Pending"]

    active_projects = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM projects
            WHERE status IN ('Active','Awaiting Approval','Awaiting Revision Approval','Awaiting Execution Review','Awaiting Library Decision')
            """
        ).fetchone()[0]
    )
    revision_projects = int(
        conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='Needs Revision'"
        ).fetchone()[0]
    )
    blocked_tasks = int(
        conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='Blocked'"
        ).fetchone()[0]
    )
    library_decisions = int(
        conn.execute(
            "SELECT COUNT(*) FROM programs_library_preflights WHERE status='Pending'"
        ).fetchone()[0]
    )

    ready_to_approve = sum(
        1
        for item in pending_items
        if item.get("stage") == "final_review"
        and item.get("chief_recommendation") == "approve_internal"
    )
    revision_recommended = sum(
        1
        for item in pending_items
        if item.get("stage") == "final_review"
        and item.get("chief_recommendation") == "revise"
    )
    hold_recommended = sum(
        1
        for item in pending_items
        if item.get("stage") == "final_review"
        and item.get("chief_recommendation") == "hold"
    )
    plan_approvals = sum(
        1
        for item in pending_items
        if item.get("stage") == "plan"
    )
    revision_plan_approvals = sum(
        1
        for item in pending_items
        if item.get("stage") == "revision_plan"
    )

    attention: list[dict[str, Any]] = []

    for approval in pending_items:
        stage = approval.get("stage")
        recommendation = approval.get("chief_recommendation")

        if stage == "final_review" and recommendation == "approve_internal":
            kind = "approval_ready"
            label = "Approval Ready"
            priority = "high"
            summary = (
                approval.get("chief_review_summary")
                or "Stella recommends accepting this internal package."
            )
        elif stage == "final_review" and recommendation == "revise":
            kind = "revision_recommended"
            label = "Stella Recommends Revision"
            priority = "high"
            summary = (
                approval.get("chief_review_summary")
                or "Stella recommends revisions before you accept the internal package."
            )
        elif stage == "final_review" and recommendation == "hold":
            kind = "hold_recommended"
            label = "Stella Recommends Hold"
            priority = "high"
            summary = (
                approval.get("chief_review_summary")
                or "Stella recommends holding this package until missing information is resolved."
            )
        elif stage == "revision_plan":
            kind = "revision_plan_approval"
            label = "Revision Plan Approval"
            priority = "high"
            summary = approval.get("summary") or "Stella’s selective revision plan is waiting for approval."
        elif stage == "plan":
            kind = "plan_approval"
            label = "Plan Approval"
            priority = "high"
            summary = approval.get("summary") or "Stella’s proposed plan is waiting for approval."
        else:
            kind = "approval"
            label = "Approval"
            priority = "high"
            summary = approval.get("summary") or "A human decision is required."

        attention.append(
            {
                "kind": kind,
                "label": label,
                "priority": priority,
                "approval_id": approval["id"],
                "project_id": approval["project_id"],
                "title": approval["title"],
                "summary": summary,
                "chief_recommendation": recommendation,
                "verification_count": approval.get("verification_count", 0),
                "gap_count": approval.get("gap_count", 0),
            }
        )

    for project in rows(
        conn,
        """
        SELECT id,title,status
        FROM projects
        WHERE status='Needs Revision'
        ORDER BY id DESC
        """,
    ):
        revision_request = latest_revision_request(conn, int(project["id"]))
        request_status = revision_request["status"] if revision_request else None
        if request_status == "Planning Failed":
            label = "Revision Planning Failed"
            summary = (
                "Stella could not produce a usable revision plan. "
                "Open the project to retry Stella’s revision-planning call."
            )
        elif revision_request:
            label = "Revision Requested"
            summary = (
                f"{revision_request['request_text']} "
                "Open the project to ask Stella for a selective revision plan."
            )[:1200]
        else:
            label = "Changes Requested"
            summary = "You requested changes. This project is waiting for new direction."

        attention.append(
            {
                "kind": "revision",
                "label": label,
                "priority": "medium",
                "project_id": project["id"],
                "title": project["title"],
                "summary": summary,
            }
        )

    for item in rows(
        conn,
        """
        SELECT plp.task_id,plp.project_id,plp.query,t.title,p.title AS project_title
        FROM programs_library_preflights plp
        JOIN tasks t ON t.id=plp.task_id
        JOIN projects p ON p.id=plp.project_id
        WHERE plp.status='Pending'
        ORDER BY plp.updated_at DESC,plp.task_id DESC
        """,
    ):
        attention.append(
            {
                "kind": "library_first",
                "label": "Programs Library First",
                "priority": "high",
                "project_id": item["project_id"],
                "task_id": item["task_id"],
                "title": item["title"],
                "summary": "The Librarian found trusted Mavis material. Choose Reuse, Revise, or Create New before Programs spends an AI call.",
            }
        )

    for task in rows(
        conn,
        """
        SELECT id,project_id,title
        FROM tasks
        WHERE status='Blocked'
        ORDER BY id DESC
        """,
    ):
        attention.append(
            {
                "kind": "blocked",
                "label": "Blocked Task",
                "priority": "medium",
                "project_id": task["project_id"],
                "task_id": task["id"],
                "title": task["title"],
                "summary": "This task is blocked and needs intervention.",
            }
        )

    return {
        "pending_approvals": len(pending_items),
        "active_projects": active_projects,
        "needs_revision": revision_projects,
        "blocked_tasks": blocked_tasks,
        "library_decisions": library_decisions,
        "ready_to_approve": ready_to_approve,
        "revision_recommended": revision_recommended,
        "hold_recommended": hold_recommended,
        "plan_approvals": plan_approvals,
        "revision_plan_approvals": revision_plan_approvals,
        "attention_count": len(attention),
        "attention": attention,
    }



MEMORY_REVIEW_INTERVALS = {0, 90, 180, 365}


def normalize_review_interval(value: Any) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        interval = 180
    return interval if interval in MEMORY_REVIEW_INTERVALS else 180


def memory_review_due(base_time: str | None, interval_days: int) -> str | None:
    interval = normalize_review_interval(interval_days)
    if interval == 0:
        return None
    try:
        base = datetime.fromisoformat(str(base_time or utc_now()))
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=interval)).astimezone(timezone.utc).isoformat(timespec="seconds")


def enrich_memory_record(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    due_at = item.get("review_due_at")
    due = False
    overdue_days = 0
    if item.get("status") == "Active" and due_at:
        try:
            due_dt = datetime.fromisoformat(str(due_at))
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            due = due_dt <= now
            if due:
                overdue_days = max(0, (now - due_dt).days)
        except (TypeError, ValueError):
            due = True
    item["review_due"] = due
    item["review_overdue_days"] = overdue_days
    return item


def memory_governance_summary(memory_rows: list[dict[str, Any]]) -> dict[str, int]:
    active = [m for m in memory_rows if m.get("status") == "Active"]
    due = [m for m in active if m.get("review_due")]
    return {
        "active": len(active),
        "due": len(due),
        "core_due": sum(1 for m in due if m.get("importance") == "Core"),
        "archived": sum(1 for m in memory_rows if m.get("status") == "Archived"),
        "superseded": sum(1 for m in memory_rows if m.get("superseded_by_id") is not None),
    }


MEMORY_TYPES = {"Decision", "Fact", "Policy", "Lesson", "Preference", "Context"}
MEMORY_IMPORTANCE = {"Core", "Normal"}
MEMORY_STATUSES = {"Active", "Archived"}


def normalize_memory_type(value: str) -> str:
    cleaned = " ".join(str(value or "").split()).title()
    return cleaned if cleaned in MEMORY_TYPES else "Context"


def institutional_memory_for_prompt(
    conn: sqlite3.Connection,
    project_id: int | None = None,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = "m.status='Active' AND m.project_id IS NULL"
    if project_id is not None:
        where = "m.status='Active' AND (m.project_id IS NULL OR m.project_id=?)"
        params.append(project_id)
    params.append(max(1, min(int(limit), 20)))
    rows_now = conn.execute(
        f"""
        SELECT m.*,p.title AS project_title
        FROM institutional_memory m
        LEFT JOIN projects p ON p.id=m.project_id
        WHERE {where}
        ORDER BY CASE m.importance WHEN 'Core' THEN 0 ELSE 1 END,
                 CASE WHEN m.project_id IS NOT NULL THEN 0 ELSE 1 END,
                 m.updated_at DESC,m.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "scope": row["project_title"] or "Institution-wide",
            "memory_type": row["memory_type"],
            "title": row["title"],
            "body": str(row["body"] or "")[:1400],
            "tags": row["tags"],
            "importance": row["importance"],
            "source": f"{row['source_kind']}:{row['source_id']}" if row["source_id"] is not None else row["source_kind"],
            "created_by": row["created_by"],
        }
        for row in rows_now
    ]


PLAYBOOK_STATUSES = {"Draft", "Active", "Archived"}
PLAYBOOK_OWNERS = {"chief", "research", "programs", "caretaker"}


def _playbook_steps(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else []
    steps: list[str] = []
    for item in raw[:20]:
        text = " ".join(str(item or "").split()).strip()[:700]
        if text:
            steps.append(text)
    return steps


def playbooks_for_prompt(
    conn: sqlite3.Connection,
    project_id: int | None = None,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = "pb.status='Active' AND pb.project_id IS NULL"
    if project_id is not None:
        where = "pb.status='Active' AND (pb.project_id IS NULL OR pb.project_id=?)"
        params.append(project_id)
    params.append(max(1, min(int(limit), 10)))
    found = conn.execute(
        f"""
        SELECT pb.*,p.title AS project_title,a.name AS owner_name
        FROM playbooks pb
        LEFT JOIN projects p ON p.id=pb.project_id
        LEFT JOIN agents a ON a.id=pb.owner_agent_id
        WHERE {where}
        ORDER BY CASE WHEN pb.project_id IS NOT NULL THEN 0 ELSE 1 END, pb.updated_at DESC, pb.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "scope": row["project_title"] or "Institution-wide",
            "title": row["title"],
            "purpose": row["purpose"],
            "owner": row["owner_name"] or row["owner_agent_id"] or "Institution",
            "when_to_use": row["trigger_text"],
            "steps": _safe_json_list(row["steps_json"]),
            "tags": row["tags"],
        }
        for row in found
    ]


def _daily_steward_forecast_context(environment: dict[str, Any]) -> dict[str, Any]:
    """Reduce stored weather into planning signals without pretending to know farm conditions we do not have."""
    today = str(environment.get("local_date") or "")
    days = list(environment.get("forecast_days") or [])
    today_row = next((d for d in days if str(d.get("forecast_date") or "") == today), None)
    tomorrow_row = None
    try:
        tomorrow_date = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
        tomorrow_row = next((d for d in days if str(d.get("forecast_date") or "") == tomorrow_date), None)
    except Exception:
        pass

    def num(row: dict[str, Any] | None, key: str) -> float | None:
        if not row or row.get(key) is None:
            return None
        try:
            return float(row.get(key))
        except (TypeError, ValueError):
            return None

    current = environment.get("current_conditions") or {}
    today_precip = num(today_row, "precip_chance")
    tomorrow_precip = num(tomorrow_row, "precip_chance")
    high = num(today_row, "high_f")
    low = num(today_row, "low_f")
    wind = num(today_row, "wind_max_mph")
    current_temp = num(current, "temperature_f")

    outdoor_adjustment = 0
    indoor_adjustment = 0
    notes: list[str] = []
    summary_parts: list[str] = []

    if today_row:
        if high is not None and low is not None:
            summary_parts.append(f"{round(high):.0f}°/{round(low):.0f}°")
        elif current_temp is not None:
            summary_parts.append(f"{round(current_temp):.0f}° now")
        if today_precip is not None:
            summary_parts.append(f"{round(today_precip):.0f}% precip")
        if str(today_row.get("summary") or "").strip():
            summary_parts.append(str(today_row.get("summary")).strip())
    elif current_temp is not None:
        summary_parts.append(f"{round(current_temp):.0f}° now")

    if today_precip is not None and today_precip >= 65:
        outdoor_adjustment -= 14
        indoor_adjustment += 4
        notes.append("A wet-weather day favors indoor, planning, research, program, or administrative work unless an outdoor job truly needs rain.")
    elif today_precip is not None and today_precip <= 35 and tomorrow_precip is not None and tomorrow_precip >= 60:
        outdoor_adjustment += 12
        notes.append("Today looks like a useful dry-work window before a wetter forecast tomorrow.")
    if high is not None and high >= 88:
        outdoor_adjustment -= 6
        notes.append("Heat is high enough to favor shorter outdoor work blocks and earlier/later timing.")
    if low is not None and low <= 35:
        notes.append("The forecast low is near freezing; Stewart should keep frost-sensitive plants and water systems in mind.")
    if wind is not None and wind >= 25:
        outdoor_adjustment -= 5
        notes.append("Stronger wind makes some outdoor jobs less attractive today.")

    return {
        "today": today_row,
        "tomorrow": tomorrow_row,
        "today_precip_chance": today_precip,
        "tomorrow_precip_chance": tomorrow_precip,
        "outdoor_adjustment": outdoor_adjustment,
        "indoor_adjustment": indoor_adjustment,
        "summary": " · ".join(summary_parts) if summary_parts else "No current forecast detail stored",
        "notes": notes,
    }



def calendar_event_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return durable Campus calendar records, with linked project context."""
    return rows(conn, """
        SELECT e.*,p.title AS project_title
        FROM events e
        LEFT JOIN projects p ON p.id=e.project_id
        ORDER BY e.event_date ASC,
                 CASE WHEN e.all_day=1 OR e.start_time IS NULL OR e.start_time='' THEN '00:00' ELSE e.start_time END ASC,
                 e.id ASC
    """)


def calendar_summary(conn: sqlite3.Connection, local_today: date | None = None) -> dict[str, Any]:
    """Build a local, deterministic view of Today / Tomorrow / This Week."""
    if local_today is None:
        try:
            local_today = date.fromisoformat(str(environment_summary(conn).get("local_date") or date.today().isoformat()))
        except Exception:
            local_today = date.today()
    tomorrow = local_today + timedelta(days=1)
    week_end = local_today + timedelta(days=6)
    all_events = calendar_event_rows(conn)
    scheduled = [e for e in all_events if str(e.get("status") or "Scheduled") == "Scheduled"]
    today_rows = [e for e in scheduled if e.get("event_date") == local_today.isoformat()]
    tomorrow_rows = [e for e in scheduled if e.get("event_date") == tomorrow.isoformat()]
    week_rows = [e for e in scheduled if local_today.isoformat() <= str(e.get("event_date") or "") <= week_end.isoformat()]
    upcoming = [e for e in scheduled if str(e.get("event_date") or "") >= local_today.isoformat()]
    major_today = [e for e in today_rows if str(e.get("commitment_level") or "Normal") == "Major"]
    return {
        "enabled": True,
        "source": "Campus internal calendar",
        "external_connected": False,
        "external_status": "Google Calendar not connected",
        "today_date": local_today.isoformat(),
        "tomorrow_date": tomorrow.isoformat(),
        "week_end_date": week_end.isoformat(),
        "today": today_rows,
        "tomorrow": tomorrow_rows,
        "this_week": week_rows,
        "upcoming": upcoming[:40],
        "today_count": len(today_rows),
        "tomorrow_count": len(tomorrow_rows),
        "week_count": len(week_rows),
        "major_today_count": len(major_today),
        "next_event": upcoming[0] if upcoming else None,
    }


def _calendar_event_time_label(event: dict[str, Any]) -> str:
    if int(event.get("all_day") or 0):
        return "all day"
    start = str(event.get("start_time") or "").strip()
    end = str(event.get("end_time") or "").strip()
    if start and end:
        return f"{start}–{end}"
    return start or "time not set"


def daily_steward(conn: sqlite3.Connection) -> dict[str, Any]:
    """Stella's deterministic ADHD-friendly daily focus layer.

    v0.8.7.1 uses only information the Campus already has. Internal calendar events are
    first-class context; Stella still never invents plant conditions, deadlines, work estimates,
    or external calendar data and makes zero AI calls.
    """
    env = environment_summary(conn)
    weather = _daily_steward_forecast_context(env)
    local_today = date.fromisoformat(str(env.get("local_date") or date.today().isoformat()))
    calendar = calendar_summary(conn, local_today)
    today_events = list(calendar.get("today") or [])
    major_today = int(calendar.get("major_today_count") or 0)
    # A real calendar commitment should reduce how many additional work threads Stella opens.
    if major_today >= 2 or len(today_events) >= 3:
        focus_cap = 1
    elif major_today >= 1 or len(today_events) >= 2:
        focus_cap = 2
    else:
        focus_cap = 3
    agent_names = {str(r["id"]): str(r["name"]) for r in conn.execute("SELECT id,name FROM agents").fetchall()}
    candidates: list[dict[str, Any]] = []

    def add(score: int, *, kind: str, agent_id: str, title: str, why: str, first_action: str, **links: Any) -> None:
        candidates.append({
            "score": int(score), "kind": kind, "agent_id": agent_id,
            "agent": agent_names.get(agent_id, agent_id.title()), "title": title,
            "why": why, "first_action": first_action, **links,
        })

    # Human gates outrank ordinary work because the rest of the Campus can be waiting on them.
    pending = approval_rows(conn)
    for approval in [a for a in pending if a.get("status") == "Pending"][:4]:
        add(
            110, kind="decision", agent_id="chief", title=str(approval.get("title") or "Review waiting decision"),
            why="A human decision is waiting and can hold downstream work in place.",
            first_action="Open the approval, make the smallest clear decision, and leave a short note if context matters.",
            approval_id=approval.get("id"), project_id=approval.get("project_id"),
        )

    # Interrupted and blocked work represents an existing commitment that should usually be closed before opening new work.
    for task in rows(conn, """
        SELECT t.id,t.project_id,t.title,t.status,t.owner_agent_id,t.sequence,p.title AS project_title,p.status AS project_status
        FROM tasks t JOIN projects p ON p.id=t.project_id
        WHERE t.status='Blocked'
        ORDER BY p.updated_at DESC,t.sequence,t.id LIMIT 5
    """):
        add(
            98, kind="blocked_task", agent_id=str(task.get("owner_agent_id") or "chief"), title=str(task.get("title") or "Blocked task"),
            why=f"{task.get('project_title') or 'A project'} has a blocked task. Clearing the blocker is usually higher value than starting another thread.",
            first_action="Open the blocked task and identify the single missing decision, input, or prerequisite.",
            task_id=task.get("id"), project_id=task.get("project_id"),
        )
    for project in rows(conn, "SELECT id,title,status FROM projects WHERE status='Execution Interrupted' ORDER BY updated_at DESC LIMIT 3"):
        add(
            101, kind="recovery", agent_id="chief", title=f"Resume {project['title']}",
            why="The Campus recorded an interrupted workflow; completed work is preserved but the workflow needs a deliberate resume decision.",
            first_action="Open the project and use Retry / Resume only after checking the interrupted task.", project_id=project["id"],
        )

    # Grant deadlines: Vernadette surfaces only active pipeline items due within 30 days.
    grant_horizon = (local_today + timedelta(days=30)).isoformat()
    grants = rows(conn, """
        SELECT g.id,g.title,g.funder,g.deadline,g.status,g.recommendation,g.project_id,p.title AS project_title
        FROM grants g LEFT JOIN projects p ON p.id=g.project_id
        WHERE g.deadline IS NOT NULL AND g.deadline>=? AND g.deadline<=?
          AND g.status IN ('Discovered','Reviewing','Pursue','Preparing')
        ORDER BY g.deadline,g.id LIMIT 10
    """, (local_today.isoformat(), grant_horizon))
    for grant in grants:
        try:
            days_left = (date.fromisoformat(str(grant["deadline"])) - local_today).days
        except Exception:
            continue
        score = 96 if days_left <= 3 else 92 if days_left <= 7 else 80 if days_left <= 14 else 66
        if str(grant.get("recommendation") or "") == "Pursue": score += 5
        if str(grant.get("recommendation") or "") == "Pass": score -= 20
        add(
            score, kind="grant", agent_id="grants", title=str(grant.get("title") or "Grant opportunity"),
            why=f"{grant.get('funder') or 'Funder'} · due in {days_left} day(s) · {grant.get('status')} · Vernadette recommends {grant.get('recommendation')}.",
            first_action="Open the Grant Desk and decide the next missing application step before doing general grant browsing.",
            grant_id=grant.get("id"), project_id=grant.get("project_id"),
        )

    # If the primary user is already clocked in, preserving that focus is often the least-friction option.
    primary_open = conn.execute("""
        SELECT ws.id,ws.person_id,ws.project_id,ws.started_at,ws.notes,ac.name AS activity_name,p.title AS project_title,pe.display_name
        FROM work_sessions ws
        JOIN people pe ON pe.id=ws.person_id
        LEFT JOIN activity_categories ac ON ac.id=ws.activity_category_id
        LEFT JOIN projects p ON p.id=ws.project_id
        WHERE ws.ended_at IS NULL AND pe.is_primary_user=1
        ORDER BY ws.started_at DESC LIMIT 1
    """).fetchone()
    if primary_open:
        detail = str(primary_open["project_title"] or primary_open["activity_name"] or "current work")
        add(
            76, kind="continue_session", agent_id="operations", title=f"Continue {detail}",
            why="Poe shows that you are already clocked into this work. Staying with an active thread avoids an unnecessary context switch.",
            first_action="Finish the smallest useful stopping point, then clock out before switching to another priority.",
            project_id=primary_open["project_id"], work_session_id=primary_open["id"],
        )

    # Next recorded executable task from each active project. We intentionally do not invent due dates or effort estimates.
    task_rows = rows(conn, """
        SELECT t.id,t.project_id,t.title,t.status,t.owner_agent_id,t.sequence,t.brief,p.title AS project_title,p.status AS project_status
        FROM tasks t JOIN projects p ON p.id=t.project_id
        WHERE t.status IN ('Waiting','In Progress','Library Review')
          AND p.status IN ('Active','Awaiting Library Decision')
        ORDER BY p.updated_at DESC,t.sequence,t.id
    """)
    seen_projects: set[int] = set()
    owner_base = {"programs":64,"caretaker":63,"operations":61,"research":59,"grants":62,"chief":58}
    for task in task_rows:
        project_id = int(task["project_id"])
        if project_id in seen_projects:
            continue
        seen_projects.add(project_id)
        owner = str(task.get("owner_agent_id") or "chief")
        score = owner_base.get(owner, 56)
        if owner == "caretaker": score += int(weather.get("outdoor_adjustment") or 0)
        else: score += int(weather.get("indoor_adjustment") or 0)
        if task.get("status") == "In Progress": score += 8
        if task.get("status") == "Library Review": score += 10
        lane = {
            "programs":"Percy has this as the next recorded education/program task.",
            "caretaker":"Stewart has this as the next recorded land or living-systems task.",
            "operations":"Poe has this as the next recorded operations task.",
            "research":"Rose has this as the next recorded research task.",
            "grants":"Vernadette has this as the next recorded development task.",
            "chief":"Stella has this as the next recorded coordination task.",
        }.get(owner,"This is the next recorded task in an active project.")
        weather_reason = ""
        if owner == "caretaker" and int(weather.get("outdoor_adjustment") or 0) >= 8:
            weather_reason = " The forecast makes outdoor work relatively favorable today."
        elif owner == "caretaker" and int(weather.get("outdoor_adjustment") or 0) <= -8:
            weather_reason = " The forecast makes outdoor work less favorable, so only keep this high if it cannot wait."
        add(
            score, kind="task", agent_id=owner, title=str(task.get("title") or "Next project task"),
            why=f"{lane}{weather_reason} Project: {task.get('project_title') or 'Untitled'}.",
            first_action="Open this task and do only the smallest concrete next step before deciding whether to continue.",
            task_id=task.get("id"), project_id=task.get("project_id"),
        )

    # Deterministic selection, capped at three to protect attention.
    candidates.sort(key=lambda x: (-int(x.get("score") or 0), str(x.get("title") or "")))
    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[Any, ...]] = set()
    for item in candidates:
        key = (item.get("kind"), item.get("approval_id"), item.get("task_id"), item.get("grant_id"), item.get("project_id"), item.get("work_session_id"))
        if key in selected_keys:
            continue
        selected.append(dict(item))
        selected_keys.add(key)
        if len(selected) >= focus_cap:
            break

    if not selected:
        selected.append({
            "score": 40, "kind": "light_day", "agent_id": "chief", "agent": agent_names.get("chief", "Stella"),
            "title": "Keep the day intentionally light",
            "why": "The Campus has no recorded decision, deadline, blocked task, active work session, or executable project task demanding attention right now.",
            "first_action": "Use one short focus block to finish a small real-world obligation or capture the next genuine Mavis priority instead of creating busywork.",
        })

    slots = ["Main priority", "Secondary priority", "Close one loop"]
    for idx, item in enumerate(selected):
        item["slot"] = slots[idx] if idx < len(slots) else f"Priority {idx+1}"
        item.pop("score", None)

    watch: list[dict[str, str]] = []
    for event in today_events[:3]:
        watch.append({
            "source":"Calendar",
            "title":str(event.get("title") or "Today's commitment"),
            "detail":f"{_calendar_event_time_label(event)} · {event.get('event_type') or 'Event'} · {event.get('commitment_level') or 'Normal'} commitment" + (f" · {event.get('location')}" if str(event.get('location') or '').strip() else ""),
        })
    if not today_events and calendar.get("tomorrow"):
        next_day = calendar.get("tomorrow")[0]
        watch.append({"source":"Calendar","title":"Tomorrow","detail":f"{next_day.get('title')} · {_calendar_event_time_label(next_day)}"})
    for note in list(weather.get("notes") or [])[:2]:
        watch.append({"source":"Stewart", "title":"Weather / season", "detail":note})
    if grants:
        earliest = grants[0]
        if not any(x.get("grant_id") == earliest.get("id") for x in selected):
            watch.append({"source":"Vernadette", "title":"Upcoming grant", "detail":f"{earliest['title']} is due {earliest['deadline']}."})
    open_count = int(conn.execute("SELECT COUNT(*) FROM work_sessions WHERE ended_at IS NULL").fetchone()[0])
    if open_count and not primary_open:
        watch.append({"source":"Poe", "title":"Active work session", "detail":f"{open_count} person(s) are currently clocked in."})
    due_memory = int(conn.execute("SELECT COUNT(*) FROM institutional_memory WHERE status='Active' AND review_due_at IS NOT NULL AND review_due_at<=?", (utc_now(),)).fetchone()[0])
    if due_memory:
        watch.append({"source":"Rose", "title":"Institutional memory", "detail":f"{due_memory} memory item(s) are due for review; this is a watch item unless it blocks current work."})

    counts_by_owner = {str(r["owner_agent_id"] or "chief"): int(r["n"]) for r in conn.execute("""
        SELECT owner_agent_id,COUNT(*) AS n FROM tasks
        WHERE status NOT IN ('Completed','Superseded') GROUP BY owner_agent_id
    """).fetchall()}
    active_grants = int(conn.execute("SELECT COUNT(*) FROM grants WHERE status IN ('Discovered','Reviewing','Pursue','Preparing')").fetchone()[0])
    staff_inputs = [
        {"agent":"Stella","lane":"Executive gates & calendar","status":f"{len([a for a in pending if a.get('status')=='Pending'])} decision(s) waiting · {len(today_events)} calendar event(s) today"},
        {"agent":"Percy","lane":"Programs","status":f"{counts_by_owner.get('programs',0)} open task(s)"},
        {"agent":"Rose","lane":"Research & memory","status":f"{counts_by_owner.get('research',0)} open research task(s) · {due_memory} memory review(s)"},
        {"agent":"Stewart","lane":"Weather, season & land","status":f"{env.get('season','Season')} · {weather.get('summary')}"},
        {"agent":"Vernadette","lane":"Funding","status":f"{active_grants} active grant record(s)"},
        {"agent":"Poe","lane":"Operations & people","status":f"{open_count} person(s) clocked in"},
    ]

    if focus_cap < 3:
        commitment_word = "major commitment" if major_today else "multiple commitments"
        protect = f"Your calendar already carries {commitment_word} today. Keep additional focus work to {focus_cap} item(s), protect transition time, and do not fill the remaining space just because it exists."
    elif any(item.get("kind") in {"decision","recovery","blocked_task"} for item in selected):
        protect = "Do not open a new major project until the waiting decision, recovery item, or blocker above is cleared."
    elif len(candidates) > len(selected):
        protect = "Do not expand today's list. Finish or intentionally stop one of these priorities before pulling another project into the day."
    else:
        protect = "Do not manufacture urgency. Keep the list small and close one useful loop before starting something new."

    return {
        "generated_at": utc_now(),
        "local_date": env.get("local_date"),
        "location": env.get("location_label"),
        "season": env.get("season"),
        "weather_summary": weather.get("summary"),
        "forecast_source": env.get("forecast_source"),
        "calendar": {
            "connected": True,
            "source": "Campus internal calendar",
            "external_connected": False,
            "status": f"{len(today_events)} event(s) today" if today_events else "No events today",
            "detail": "Internal Campus calendar is active. Google Calendar is not connected yet.",
            "today": today_events,
            "tomorrow": calendar.get("tomorrow") or [],
            "this_week": calendar.get("this_week") or [],
        },
        "focus": selected[:focus_cap],
        "watch": watch[:4],
        "protect_attention": protect,
        "staff_inputs": staff_inputs,
        "candidate_count": len(candidates),
        "focus_cap": focus_cap,
        "calendar_pressure": {"today_count": len(today_events), "major_today_count": major_today},
        "additional_ai_calls": 0,
        "method": "deterministic_local_coordination",
        "limitations": ["Google Calendar not connected yet", "No automatic plant/phenology records yet", "No automatic rescheduling or external actions"],
    }


def executive_briefing(conn: sqlite3.Connection) -> dict[str, Any]:
    """Build an executive briefing from local Campus state only. No AI call occurs here."""
    executive = executive_summary(conn)
    now = utc_now()
    project_rows = rows(
        conn,
        """
        SELECT p.id,p.title,p.status,p.updated_at,
               COUNT(t.id) AS task_count,
               SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) AS completed_tasks,
               SUM(CASE WHEN t.status='Blocked' THEN 1 ELSE 0 END) AS blocked_tasks
        FROM projects p
        LEFT JOIN tasks t ON t.project_id=p.id
        GROUP BY p.id
        ORDER BY CASE p.status
          WHEN 'Awaiting Approval' THEN 0 WHEN 'Awaiting Revision Approval' THEN 0
          WHEN 'Awaiting Execution Review' THEN 1 WHEN 'Needs Revision' THEN 1
          WHEN 'Execution Interrupted' THEN 1 WHEN 'Active' THEN 2 ELSE 3 END,
          p.updated_at DESC
        LIMIT 12
        """,
    )
    for project in project_rows:
        total = int(project.get("task_count") or 0)
        done = int(project.get("completed_tasks") or 0)
        project["progress_percent"] = round((done / total) * 100) if total else 0

    due_memories = [
        enrich_memory_record(dict(row))
        for row in conn.execute(
            """
            SELECT m.*,p.title AS project_title
            FROM institutional_memory m
            LEFT JOIN projects p ON p.id=m.project_id
            WHERE m.status='Active' AND m.review_due_at IS NOT NULL AND m.review_due_at<=?
            ORDER BY CASE m.importance WHEN 'Core' THEN 0 ELSE 1 END,m.review_due_at,m.id
            LIMIT 10
            """,
            (now,),
        ).fetchall()
    ]
    active_playbooks = rows(
        conn,
        """
        SELECT pb.id,pb.title,pb.purpose,pb.owner_agent_id,pb.project_id,p.title AS project_title
        FROM playbooks pb LEFT JOIN projects p ON p.id=pb.project_id
        WHERE pb.status='Active'
        ORDER BY CASE WHEN pb.project_id IS NOT NULL THEN 0 ELSE 1 END,pb.updated_at DESC
        LIMIT 8
        """,
    )
    recent_completed = rows(
        conn,
        """
        SELECT t.id,t.project_id,t.title,t.updated_at,p.title AS project_title
        FROM tasks t JOIN projects p ON p.id=t.project_id
        WHERE t.status='Completed'
        ORDER BY t.updated_at DESC,t.id DESC LIMIT 8
        """,
    )
    recent_outputs = rows(
        conn,
        """
        SELECT d.id,d.project_id,d.title,d.deliverable_type,d.version,d.updated_at,p.title AS project_title
        FROM deliverables d JOIN projects p ON p.id=d.project_id
        WHERE d.status!='Superseded'
        ORDER BY d.updated_at DESC,d.id DESC LIMIT 6
        """,
    )
    ai = ai_control_state(conn)
    environment = environment_summary(conn)
    local_today = date.fromisoformat(str(environment.get("local_date") or date.today().isoformat()))
    grant_horizon = (local_today + timedelta(days=30)).isoformat()
    urgent_grants = rows(
        conn,
        """
        SELECT g.id,g.title,g.funder,g.deadline,g.status,g.recommendation,g.project_id,p.title AS project_title
        FROM grants g LEFT JOIN projects p ON p.id=g.project_id
        WHERE g.deadline IS NOT NULL AND g.deadline>=? AND g.deadline<=?
          AND g.status IN ('Discovered','Reviewing','Pursue','Preparing')
        ORDER BY g.deadline,g.id LIMIT 8
        """,
        (local_today.isoformat(), grant_horizon),
    )
    interrupted = [p for p in project_rows if p.get("status") == "Execution Interrupted"]
    priorities: list[dict[str, Any]] = [dict(item) for item in executive.get("attention", [])]
    for project in interrupted:
        priorities.append({
            "kind": "recovery",
            "label": "Workflow Recovery",
            "priority": "high",
            "project_id": project["id"],
            "title": project["title"],
            "summary": "Execution was interrupted. Human-triggered Retry / Resume is required; completed work will be preserved.",
        })
    for grant in urgent_grants:
        days_left = (date.fromisoformat(grant["deadline"]) - local_today).days
        priorities.append({
            "kind": "grant_deadline",
            "label": "Grant Deadline",
            "priority": "high" if days_left <= 7 else "medium",
            "grant_id": grant["id"],
            "project_id": grant.get("project_id"),
            "title": grant["title"],
            "summary": f"{grant['funder']} · due in {days_left} day(s) · {grant['status']} · Vernadette recommends {grant['recommendation']}.",
        })
    for memory in due_memories[:6]:
        priorities.append({
            "kind": "memory_review",
            "label": "Core Memory Review" if memory.get("importance") == "Core" else "Memory Review",
            "priority": "medium" if memory.get("importance") == "Core" else "low",
            "memory_id": memory["id"],
            "title": memory["title"],
            "summary": f"{memory.get('importance','Normal')} {memory.get('memory_type','Context')} memory is due for human review.",
        })
    if not ai.get("enabled") or ai.get("budget_blocked"):
        priorities.insert(0, {
            "kind": "ai_control",
            "label": "AI Operations",
            "priority": "high",
            "title": "AI calls are currently constrained",
            "summary": ai.get("stopped_reason") or "The estimated-cost guardrail is blocking new OpenAI calls.",
        })

    return {
        "generated_at": now,
        "source": "deterministic_local_state",
        "additional_ai_calls": 0,
        "daily_steward": daily_steward(conn),
        "priority_count": len(priorities),
        "priorities": priorities[:18],
        "projects": project_rows,
        "memory_due": due_memories,
        "active_playbooks": active_playbooks,
        "recent_completed_tasks": recent_completed,
        "recent_outputs": recent_outputs,
        "environment": environment,
        "ai_control": {
            "enabled": ai.get("enabled"),
            "budget_blocked": ai.get("budget_blocked"),
            "today_estimated_openai_list_cost_usd": ai.get("today_estimated_openai_list_cost_usd"),
            "daily_estimated_cost_limit_usd": ai.get("daily_estimated_cost_limit_usd"),
        },
        "counts": {
            "pending_approvals": executive.get("pending_approvals", 0),
            "blocked_tasks": executive.get("blocked_tasks", 0),
            "library_decisions": executive.get("library_decisions", 0),
            "needs_revision": executive.get("needs_revision", 0),
            "memory_review_due": len(due_memories),
            "active_playbooks": len(active_playbooks),
            "tracked_projects": len(project_rows),
        },
    }


def _parse_iso_datetime(value: str, field_name: str = "time") -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date/time.") from exc
    return parsed


def _session_duration_minutes(started_at: str, ended_at: str) -> int:
    start = _parse_iso_datetime(started_at, "started_at")
    end = _parse_iso_datetime(ended_at, "ended_at")
    if (start.tzinfo is None) != (end.tzinfo is None):
        raise ValueError("started_at and ended_at must use matching timezone styles.")
    minutes = int(round((end - start).total_seconds() / 60.0))
    if minutes < 0:
        raise ValueError("ended_at cannot be before started_at.")
    return minutes


def work_session_rows(conn: sqlite3.Connection, limit: int = 250) -> list[dict[str, Any]]:
    return rows(
        conn,
        """
        SELECT ws.*,p.display_name AS person_name,p.person_type,
               ac.code AS activity_code,ac.name AS activity_name,
               pr.title AS project_title
        FROM work_sessions ws
        JOIN people p ON p.id=ws.person_id
        LEFT JOIN activity_categories ac ON ac.id=ws.activity_category_id
        LEFT JOIN projects pr ON pr.id=ws.project_id
        ORDER BY CASE WHEN ws.ended_at IS NULL THEN 0 ELSE 1 END,ws.started_at DESC,ws.id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 1000)),),
    )


def work_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    summary = conn.execute(
        """
        SELECT COUNT(*) AS session_count,
               SUM(CASE WHEN ended_at IS NULL THEN 1 ELSE 0 END) AS active_count,
               COALESCE(SUM(CASE WHEN duration_minutes IS NOT NULL THEN duration_minutes ELSE 0 END),0) AS completed_minutes
        FROM work_sessions
        """
    ).fetchone()
    by_type = rows(
        conn,
        """
        SELECT participation_type,COUNT(*) AS session_count,
               COALESCE(SUM(duration_minutes),0) AS minutes
        FROM work_sessions
        WHERE ended_at IS NOT NULL
        GROUP BY participation_type
        ORDER BY minutes DESC,participation_type
        """,
    )
    return {
        "session_count": int(summary["session_count"] or 0),
        "active_count": int(summary["active_count"] or 0),
        "completed_minutes": int(summary["completed_minutes"] or 0),
        "completed_hours": round(int(summary["completed_minutes"] or 0) / 60.0, 2),
        "by_participation_type": by_type,
    }


def _work_report_timezone(conn: sqlite3.Connection) -> tuple[str, ZoneInfo]:
    row = conn.execute("SELECT timezone_name FROM environment_settings WHERE id=1").fetchone()
    tz_name = str(row["timezone_name"] if row and row["timezone_name"] else "America/New_York")
    try:
        return tz_name, ZoneInfo(tz_name)
    except Exception:
        return "America/New_York", ZoneInfo("America/New_York")


def _report_date(value: str | None, field_name: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD.") from exc


def _session_local_datetime(value: str, tz: ZoneInfo) -> datetime:
    parsed = _parse_iso_datetime(value, "started_at")
    # Clock records created by the Campus are offset-aware UTC. If an older/manual
    # correction is timezone-naive, treat it as local Campus time rather than
    # silently shifting the volunteer's stated clock time.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def work_report_data(
    conn: sqlite3.Connection,
    *,
    person_id: int | None = None,
    activity_category_id: int | None = None,
    project_id: int | None = None,
    participation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    try:
        start = _report_date(start_date, "start_date")
        end = _report_date(end_date, "end_date")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date.")

    participation = " ".join(str(participation_type or "").split()).strip()
    params: list[Any] = []
    where = ["ws.ended_at IS NOT NULL", "ws.duration_minutes IS NOT NULL"]
    if person_id is not None:
        where.append("ws.person_id=?")
        params.append(int(person_id))
    if activity_category_id is not None:
        where.append("ws.activity_category_id=?")
        params.append(int(activity_category_id))
    if project_id is not None:
        where.append("ws.project_id=?")
        params.append(int(project_id))
    if participation:
        where.append("LOWER(ws.participation_type)=LOWER(?)")
        params.append(participation)

    raw = rows(
        conn,
        f"""
        SELECT ws.*,p.display_name AS person_name,p.person_type,
               ac.code AS activity_code,ac.name AS activity_name,
               pr.title AS project_title
        FROM work_sessions ws
        JOIN people p ON p.id=ws.person_id
        LEFT JOIN activity_categories ac ON ac.id=ws.activity_category_id
        LEFT JOIN projects pr ON pr.id=ws.project_id
        WHERE {' AND '.join(where)}
        ORDER BY ws.started_at DESC,ws.id DESC
        """,
        tuple(params),
    )

    tz_name, tz = _work_report_timezone(conn)
    sessions: list[dict[str, Any]] = []
    for item in raw:
        record = dict(item)
        manual_day = None
        if str(item.get("entry_mode") or "clock") == "manual_duration" and item.get("work_date"):
            try:
                manual_day = date.fromisoformat(str(item["work_date"]))
            except ValueError:
                manual_day = None
        if manual_day is not None:
            local_day = manual_day
            record["local_started_at"] = ""
            record["local_ended_at"] = ""
        else:
            try:
                local_start = _session_local_datetime(str(item["started_at"]), tz)
            except ValueError:
                continue
            local_day = local_start.date()
            record["local_started_at"] = local_start.isoformat(timespec="minutes")
            try:
                local_end = _session_local_datetime(str(item["ended_at"]), tz)
                record["local_ended_at"] = local_end.isoformat(timespec="minutes")
            except (ValueError, TypeError):
                record["local_ended_at"] = str(item.get("ended_at") or "")
        if start and local_day < start:
            continue
        if end and local_day > end:
            continue
        record["local_date"] = local_day.isoformat()
        record["local_month"] = local_day.strftime("%Y-%m")
        record["duration_hours"] = round(int(item.get("duration_minutes") or 0) / 60.0, 2)
        sessions.append(record)

    def grouped(key_fn, label_fn):
        bucket: dict[Any, dict[str, Any]] = {}
        for item in sessions:
            key = key_fn(item)
            if key not in bucket:
                bucket[key] = {"key": key, "label": label_fn(item), "session_count": 0, "minutes": 0}
            bucket[key]["session_count"] += 1
            bucket[key]["minutes"] += int(item.get("duration_minutes") or 0)
        result = []
        for entry in bucket.values():
            entry["hours"] = round(entry["minutes"] / 60.0, 2)
            result.append(entry)
        return sorted(result, key=lambda x: (-int(x["minutes"]), str(x["label"]).lower()))

    total_minutes = sum(int(item.get("duration_minutes") or 0) for item in sessions)
    unique_people = len({int(item["person_id"]) for item in sessions})
    by_person = grouped(lambda x: int(x["person_id"]), lambda x: x.get("person_name") or "Unknown person")
    by_activity = grouped(lambda x: x.get("activity_code") or "uncategorized", lambda x: x.get("activity_name") or "Uncategorized")
    by_participation = grouped(lambda x: x.get("participation_type") or "Unspecified", lambda x: x.get("participation_type") or "Unspecified")
    by_project = grouped(lambda x: int(x["project_id"]) if x.get("project_id") is not None else 0, lambda x: x.get("project_title") or "No project / general operations")
    monthly = grouped(lambda x: x["local_month"], lambda x: x["local_month"])
    monthly.sort(key=lambda x: str(x["key"]), reverse=True)

    return {
        "timezone_name": tz_name,
        "filters": {
            "person_id": person_id,
            "activity_category_id": activity_category_id,
            "project_id": project_id,
            "participation_type": participation or None,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
        },
        "summary": {
            "session_count": len(sessions),
            "people_count": unique_people,
            "minutes": total_minutes,
            "hours": round(total_minutes / 60.0, 2),
        },
        "by_person": by_person,
        "by_activity": by_activity,
        "by_participation": by_participation,
        "by_project": by_project,
        "monthly": monthly,
        "sessions": sessions,
    }


def _work_report_csv(report: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Session ID", "Person", "Person Type", "Participation", "Activity", "Activity Code",
        "Project / Program", "Local Date", "Entry Mode", "Started", "Ended", "Minutes", "Hours", "Notes", "Created By", "Last Updated",
    ])
    for item in report.get("sessions", []):
        writer.writerow([
            item.get("id"), item.get("person_name"), item.get("person_type"), item.get("participation_type"),
            item.get("activity_name") or "Uncategorized", item.get("activity_code") or "", item.get("project_title") or "",
            item.get("local_date"), item.get("entry_mode") or "clock", item.get("local_started_at"), item.get("local_ended_at"), item.get("duration_minutes"),
            item.get("duration_hours"), item.get("notes") or "", item.get("created_by") or "", item.get("updated_at") or "",
        ])
    return output.getvalue()



POE_ACTIVITY_ALIASES = [
    ("maintenance", ("repair", "repairs", "fix", "fixing", "maintenance", "infrastructure", "construction", "building repair", "powerwash", "painting")),
    ("animal_care", ("animal", "animals", "chicken", "chickens", "duck", "ducks", "bee", "bees", "hive", "feeding", "feed the chickens")),
    ("farm_land", ("farm", "garden", "gardening", "land", "orchard", "fruit forest", "greenhouse", "plant", "planting", "harvest", "soil", "pond", "stream", "mowing")),
    ("education", ("education", "educational", "class", "classes", "teaching", "teach", "workshop", "program delivery", "lesson", "curriculum")),
    ("research", ("research", "archive", "archives", "documentation", "fact check", "library research")),
    ("grants", ("grant", "grants", "funding", "development", "donor")),
    ("outreach", ("outreach", "community", "partnership", "visitor", "public event")),
    ("media", ("media", "stream", "streaming", "video", "website", "social media", "communications", "photography")),
    ("planning", ("planning", "governance", "board meeting", "strategy", "meeting")),
    ("volunteer_coordination", ("volunteer coordination", "onboarding", "volunteer onboarding", "volunteer scheduling")),
    ("learning", ("learning", "training", "course", "studying", "study", "skill building")),
    ("admin", ("admin", "administration", "paperwork", "records", "filing", "email", "correspondence", "scheduling", "office work")),
]

POE_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _poe_normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _poe_clean_command(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    return re.sub(r"^poe\s*[,;:\-]?\s*", "", text, flags=re.IGNORECASE).strip()


def _poe_primary_person(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM people WHERE is_primary_user=1 AND status='Active' LIMIT 1").fetchone()


def _poe_resolve_person(conn: sqlite3.Connection, command: str, *, allow_all: bool = False) -> tuple[sqlite3.Row | None, str | None]:
    norm = _poe_normalize(command)
    words = set(norm.split())
    if allow_all and ("our" in words or "everyone" in words or "all people" in norm or "all volunteers" in norm):
        return None, None

    people = conn.execute(
        "SELECT * FROM people WHERE status='Active' ORDER BY LENGTH(display_name) DESC,display_name COLLATE NOCASE"
    ).fetchall()
    padded = f" {norm} "
    exact = []
    for person in people:
        pnorm = _poe_normalize(person["display_name"])
        if pnorm and f" {pnorm} " in padded:
            exact.append(person)
    # Explicit names win over conversational filler such as “show me Lisa's hours”.
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, "I found more than one matching person. Use the full name so I don't put hours on the wrong record."

    # A first-name-only mention is useful when it uniquely identifies one active person.
    token_matches = []
    for person in people:
        first = _poe_normalize(person["display_name"]).split()
        if first and first[0] in words:
            token_matches.append(person)
    if len(token_matches) == 1:
        return token_matches[0], None
    if len(token_matches) > 1:
        return None, "That first name matches more than one person. Give me the full name."

    if words.intersection({"me", "my", "mine", "i"}):
        primary = _poe_primary_person(conn)
        if primary:
            return primary, None
        return None, "I don't know which People record means ‘me’ yet. In Poe's People Ledger, mark your record as ‘This is me’ once, then try again."

    return None, "I couldn't match a person in the People Ledger. Add them first, or use their recorded name in the command."


def _poe_resolve_activity(conn: sqlite3.Connection, command: str) -> sqlite3.Row | None:
    norm = _poe_normalize(command)
    categories = {row["code"]: row for row in conn.execute("SELECT * FROM activity_categories WHERE active=1").fetchall()}
    # Exact category names/codes win before conversational aliases.
    padded = f" {norm} "
    for row in categories.values():
        for candidate in (_poe_normalize(row["name"]), _poe_normalize(row["code"])):
            if candidate and f" {candidate} " in padded:
                return row
    for code, aliases in POE_ACTIVITY_ALIASES:
        if any(_poe_normalize(alias) in norm for alias in aliases):
            return categories.get(code)
    return None


def _poe_resolve_project(conn: sqlite3.Connection, command: str) -> sqlite3.Row | None:
    norm = _poe_normalize(command)
    if not norm:
        return None
    projects = conn.execute("SELECT * FROM projects ORDER BY CASE status WHEN 'Active' THEN 0 ELSE 1 END,id DESC").fetchall()
    padded = f" {norm} "
    direct = []
    for project in projects:
        title = _poe_normalize(project["title"])
        if title and f" {title} " in padded:
            direct.append(project)
    if direct:
        return max(direct, key=lambda x: len(_poe_normalize(x["title"])))

    best = None
    best_score = 0
    command_words = set(norm.split())
    for project in projects:
        title_words = [w for w in _poe_normalize(project["title"]).split() if len(w) > 2]
        if not title_words:
            continue
        hits = sum(1 for word in title_words if word in command_words)
        # Require a substantial match so a generic word like “class” does not attach the wrong project.
        score = hits / len(title_words)
        if hits >= 2 and score > best_score:
            best, best_score = project, score
    return best


def _poe_participation(command: str) -> str:
    norm = _poe_normalize(command)
    if "paid" in norm or "payroll" in norm:
        return "Paid"
    if "learning" in norm or "training" in norm or "learner" in norm:
        return "Learning"
    return "Volunteer"


def _poe_local_today(conn: sqlite3.Connection) -> date:
    _, tz = _work_report_timezone(conn)
    return datetime.now(timezone.utc).astimezone(tz).date()


def _poe_month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        following = date(year + 1, 1, 1)
    else:
        following = date(year, month + 1, 1)
    return first, following - timedelta(days=1)


def _poe_date_window(command: str, today: date) -> tuple[date | None, date | None, str]:
    norm = _poe_normalize(command)
    if "yesterday" in norm:
        day = today - timedelta(days=1)
        return day, day, day.strftime("%B %d, %Y").replace(" 0", " ")
    if "today" in norm:
        return today, today, "today"
    if "this week" in norm:
        start = today - timedelta(days=today.weekday())
        return start, today, "this week"
    if "last week" in norm:
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end, "last week"
    if "this month" in norm:
        start, _ = _poe_month_bounds(today.year, today.month)
        return start, today, today.strftime("%B %Y")
    if "last month" in norm:
        first_this, _ = _poe_month_bounds(today.year, today.month)
        prior_day = first_this - timedelta(days=1)
        start, end = _poe_month_bounds(prior_day.year, prior_day.month)
        return start, end, prior_day.strftime("%B %Y")

    for label, month in POE_MONTHS.items():
        if re.search(rf"\b{re.escape(label)}\b", norm):
            year_match = re.search(r"\b(20\d{2})\b", norm)
            year = int(year_match.group(1)) if year_match else today.year
            # Without an explicit year, use the most recent occurrence of that month.
            if not year_match and month > today.month:
                year -= 1
            start, end = _poe_month_bounds(year, month)
            if year == today.year and month == today.month:
                end = today
            return start, end, date(year, month, 1).strftime("%B %Y")
    return None, None, "all recorded time"


def _poe_single_work_date(command: str, today: date) -> date:
    norm = _poe_normalize(command)
    if "yesterday" in norm:
        return today - timedelta(days=1)
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", command)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1))
        except ValueError:
            pass
    for label, month in POE_MONTHS.items():
        match = re.search(rf"\b{re.escape(label)}\s+(\d{{1,2}})(?:\s*,?\s*(20\d{{2}}))?\b", norm)
        if match:
            year = int(match.group(2)) if match.group(2) else today.year
            try:
                return date(year, month, int(match.group(1)))
            except ValueError:
                break
    return today


def _poe_duration_minutes(command: str) -> int | None:
    total = 0.0
    found = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|hr|minutes?|mins?|min)\b", command, flags=re.IGNORECASE):
        found = True
        amount = float(value)
        if unit.lower().startswith(("h", "hr")):
            total += amount * 60
        else:
            total += amount
    if not found:
        return None
    minutes = int(round(total))
    return minutes if minutes > 0 else None


def _poe_duration_label(minutes: int) -> str:
    minutes = max(0, int(minutes or 0))
    hours, rem = divmod(minutes, 60)
    if hours and rem:
        return f"{hours}h {rem}m"
    if hours:
        return f"{hours}h"
    return f"{rem}m"


def _poe_manual_session(conn: sqlite3.Connection, *, person_id: int, activity_category_id: int, participation_type: str, work_day: date, duration_minutes: int, project_id: int | None, notes: str) -> int:
    _, tz = _work_report_timezone(conn)
    # Date-only remembered time is intentionally stored as manual_duration. The noon
    # timestamps are internal sort anchors; reports hide them so we never imply the
    # volunteer supplied exact start/end clock times.
    local_start = datetime.combine(work_day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
    local_end = local_start + timedelta(minutes=int(duration_minutes))
    started_at = local_start.astimezone(timezone.utc).isoformat(timespec="seconds")
    ended_at = local_end.astimezone(timezone.utc).isoformat(timespec="seconds")
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO work_sessions(person_id,project_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,entry_mode,work_date,notes,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,'Poe',?,?)
        """,
        (int(person_id), project_id, int(activity_category_id), participation_type, started_at, ended_at, int(duration_minutes), "manual_duration", work_day.isoformat(), str(notes or "")[:4000], now, now),
    )
    session_id = int(cur.lastrowid)
    _audit_work_session(conn, session_id, "manual_duration", "Poe")
    return session_id


def _poe_command_kind(command: str) -> str:
    norm = _poe_normalize(command)
    if re.search(r"\bclock\b.*\bout\b", norm) or norm.startswith("clock out"):
        return "clock_out"
    if re.search(r"\bclock\b.*\bin\b", norm) or norm.startswith("clock in"):
        return "clock_in"
    if re.search(r"\b(add|record|log)\b", norm) and _poe_duration_minutes(command):
        return "manual_duration"
    if any(phrase in norm for phrase in ("how many", "how much time", "show me", "hours", "hour total", "work report", "total time", "report")):
        return "report"
    return "unknown"


def _poe_command_report(conn: sqlite3.Connection, command: str) -> dict[str, Any]:
    today = _poe_local_today(conn)
    start, end, period_label = _poe_date_window(command, today)
    person, person_error = _poe_resolve_person(conn, command, allow_all=True)
    norm = _poe_normalize(command)
    if person_error and set(norm.split()).intersection({"me", "my", "mine", "i"}):
        return {"status": "clarification", "intent": "report", "message": person_error}
    activity = _poe_resolve_activity(conn, command)
    project = _poe_resolve_project(conn, command)
    participation = None
    if "volunteer" in norm:
        participation = "Volunteer"
    elif "paid" in norm:
        participation = "Paid"
    elif "learning" in norm or "training" in norm:
        participation = "Learning"
    filters = {
        "person_id": int(person["id"]) if person else None,
        "activity_category_id": int(activity["id"]) if activity else None,
        "project_id": int(project["id"]) if project else None,
        "participation_type": participation,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
    }
    report = work_report_data(conn, **filters)
    total = int(report["summary"]["minutes"] or 0)
    pieces = []
    if participation:
        pieces.append(participation.lower())
    if activity:
        pieces.append(str(activity["name"]).lower())
    descriptor = " ".join(pieces) + (" " if pieces else "")
    who = f" for {person['display_name']}" if person else ""
    message = f"{period_label}: {_poe_duration_label(total)} of {descriptor}time across {report['summary']['session_count']} completed session(s){who}."
    return {
        "status": "ok",
        "intent": "report",
        "message": message,
        "report_filters": filters,
        "report_summary": report["summary"],
    }

def _work_session_snapshot(conn: sqlite3.Connection, session_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM work_sessions WHERE id=?", (int(session_id),)).fetchone()
    return dict(row) if row else {}


def _audit_work_session(conn: sqlite3.Connection, session_id: int, action: str, actor: str = "Poe") -> None:
    conn.execute(
        "INSERT INTO work_session_audit(work_session_id,action,actor,snapshot_json,created_at) VALUES(?,?,?,?,?)",
        (int(session_id), str(action), str(actor), json.dumps(_work_session_snapshot(conn, session_id), ensure_ascii=False), utc_now()),
    )


def grant_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(
        conn,
        """
        SELECT g.*,p.title AS project_title
        FROM grants g
        LEFT JOIN projects p ON p.id=g.project_id
        ORDER BY
          CASE g.status
            WHEN 'Preparing' THEN 0 WHEN 'Pursue' THEN 1 WHEN 'Reviewing' THEN 2 WHEN 'Discovered' THEN 3
            WHEN 'Submitted' THEN 4 WHEN 'Awarded' THEN 5 WHEN 'Declined' THEN 6 ELSE 7 END,
          CASE WHEN g.deadline IS NULL OR g.deadline='' THEN 1 ELSE 0 END,
          g.deadline ASC,g.updated_at DESC,g.id DESC
        """,
    )


def grant_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    counts = {row["status"]: int(row["n"]) for row in conn.execute("SELECT status,COUNT(*) AS n FROM grants GROUP BY status").fetchall()}
    environment = environment_summary(conn)
    today = str(environment.get("local_date") or date.today().isoformat())
    horizon = (date.fromisoformat(today) + timedelta(days=30)).isoformat()
    upcoming = int(conn.execute(
        "SELECT COUNT(*) FROM grants WHERE deadline IS NOT NULL AND deadline>=? AND deadline<=? AND status IN ('Discovered','Reviewing','Pursue','Preparing')",
        (today,horizon),
    ).fetchone()[0])
    nearest = conn.execute(
        "SELECT id,title,funder,deadline,status,recommendation FROM grants WHERE deadline IS NOT NULL AND deadline>=? AND status IN ('Discovered','Reviewing','Pursue','Preparing') ORDER BY deadline,id LIMIT 1",
        (today,),
    ).fetchone()
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "active_pipeline": sum(counts.get(x,0) for x in ("Discovered","Reviewing","Pursue","Preparing","Submitted")),
        "upcoming_30_days": upcoming,
        "nearest_deadline": dict(nearest) if nearest else None,
    }


def _clean_grant_request(req: GrantRequest, conn: sqlite3.Connection) -> dict[str, Any]:
    funder = " ".join(str(req.funder or "").split()).strip()[:220]
    title = " ".join(str(req.title or "").split()).strip()[:260]
    if not funder or not title:
        raise HTTPException(status_code=400, detail="Funder and grant name are required.")
    status = " ".join(str(req.status or "Discovered").split()).strip()
    if status not in GRANT_STATUSES:
        raise HTTPException(status_code=400, detail="Use a valid grant pipeline status.")
    recommendation = " ".join(str(req.recommendation or "Review").split()).strip()
    if recommendation not in GRANT_RECOMMENDATIONS:
        raise HTTPException(status_code=400, detail="Recommendation must be Pursue, Review, or Pass.")
    deadline = str(req.deadline or "").strip() or None
    if deadline:
        try:
            date.fromisoformat(deadline)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Deadline must be YYYY-MM-DD.") from exc
    project_id = req.project_id
    if project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (int(project_id),)).fetchone():
        raise HTTPException(status_code=404, detail="Project not found.")
    amount_min = req.amount_min
    amount_max = req.amount_max
    if amount_min is not None and amount_min < 0:
        raise HTTPException(status_code=400, detail="Minimum amount cannot be negative.")
    if amount_max is not None and amount_max < 0:
        raise HTTPException(status_code=400, detail="Maximum amount cannot be negative.")
    if amount_min is not None and amount_max is not None and amount_max < amount_min:
        raise HTTPException(status_code=400, detail="Maximum amount cannot be less than minimum amount.")
    scores = {}
    for key in ("mission_fit","workload","restrictions","strategic_value"):
        value = int(getattr(req,key))
        if value < 1 or value > 5:
            raise HTTPException(status_code=400, detail=f"{key.replace('_',' ').title()} must be from 1 to 5.")
        scores[key] = value
    source_url = str(req.source_url or "").strip()[:1200]
    if source_url and not re.match(r"^https?://", source_url, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Source link must start with http:// or https://.")
    return {
        "funder": funder, "title": title, "deadline": deadline, "amount_min": amount_min, "amount_max": amount_max,
        "amount_notes": str(req.amount_notes or "")[:500], "source_url": source_url,
        "status": status, "project_id": project_id, "notes": str(req.notes or "")[:5000],
        **scores, "recommendation": recommendation, "assessment_notes": str(req.assessment_notes or "")[:5000],
    }


VERNADETTE_ACTIVE_STATUSES = ("Discovered", "Reviewing", "Pursue", "Preparing", "Submitted")
VERNADETTE_STOPWORDS = {
    "vernadette", "grant", "grants", "opportunity", "opportunities", "show", "list", "me", "our", "the", "a", "an",
    "mark", "move", "set", "update", "change", "status", "recommend", "recommendation", "as", "to", "please", "what",
    "which", "should", "we", "is", "are", "due", "deadline", "deadlines", "this", "next", "month", "days", "day",
}


def _vernadette_normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _vernadette_clean_command(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"^vernadette\s*[,;:\-]?\s*", "", text, flags=re.IGNORECASE).strip()


def _vernadette_local_today(conn: sqlite3.Connection) -> date:
    environment = environment_summary(conn)
    value = str(environment.get("local_date") or date.today().isoformat())
    return date.fromisoformat(value)


def _vernadette_parse_deadline(command: str, today: date) -> date | None:
    text = str(command or "")
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    norm = _vernadette_normalize(text)
    if re.search(r"\bdue\s+today\b|\bdeadline\s+today\b", norm):
        return today
    if re.search(r"\bdue\s+tomorrow\b|\bdeadline\s+tomorrow\b", norm):
        return today + timedelta(days=1)
    month_names = "|".join(sorted(POE_MONTHS.keys(), key=len, reverse=True))
    match = re.search(rf"\b(?:due|deadline(?:\s+is)?(?:\s+on)?)\s+(?:on\s+)?({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(20\d{{2}}))?\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    month = POE_MONTHS[match.group(1).lower()]
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if not match.group(3) and candidate < today - timedelta(days=7):
        candidate = date(year + 1, month, day)
    return candidate


def _vernadette_parse_amount(command: str) -> tuple[float | None, float | None, str]:
    text = str(command or "")
    range_match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:-|–|—|to)\s*\$?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if range_match:
        lo = float(range_match.group(1).replace(",", ""))
        hi = float(range_match.group(2).replace(",", ""))
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi, f"{lo:g}–{hi:g}"
    amount = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text)
    if not amount:
        return None, None, ""
    value = float(amount.group(1).replace(",", ""))
    before = text[max(0, amount.start()-18):amount.start()].lower()
    if "up to" in before or "maximum" in before or "max " in before:
        return None, value, ""
    if "at least" in before or "minimum" in before or "min " in before:
        return value, None, ""
    return value, value, ""


def _vernadette_extract_add_identity(command: str) -> tuple[str | None, str | None]:
    text = _vernadette_clean_command(command).strip().rstrip(". ")
    tail = r"(?=\s+(?:due\b|deadline\b|for\s+\$|worth\s+\$|up\s+to\s+\$|at\s+least\s+\$|source\b|link\b|https?://|for\s+(?:the\s+)?project\b)|$)"
    patterns = [
        rf"^(?:add|create|record)\s+(?:a\s+)?(?:grant|opportunity)\s+from\s+(?P<funder>.+?)\s+(?:called|named|titled)\s+(?P<title>.+?){tail}",
        rf"^(?:add|create|record)\s+(?:a\s+)?(?:grant|opportunity)\s+(?P<title>.+?)\s+from\s+(?P<funder>.+?){tail}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            funder = " ".join(match.group("funder").strip(" ,;:-").split())[:220]
            title = " ".join(match.group("title").strip(" ,;:-").split())[:260]
            return funder or None, title or None
    return None, None


def _vernadette_resolve_status(command: str) -> str | None:
    norm = _vernadette_normalize(command)
    aliases = [
        ("Preparing", ("preparing", "prepare", "drafting")),
        ("Submitted", ("submitted", "submit")),
        ("Awarded", ("awarded", "award", "won", "funded")),
        ("Declined", ("declined", "decline", "rejected")),
        ("Passed", ("passed", "pass on", "skip", "skipped")),
        ("Reviewing", ("reviewing", "review")),
        ("Discovered", ("discovered", "discovery", "new")),
        ("Pursue", ("pursue", "pursuing")),
    ]
    for status, words in aliases:
        if any(re.search(rf"\b{re.escape(_vernadette_normalize(word))}\b", norm) for word in words):
            return status
    return None


def _vernadette_resolve_recommendation(command: str) -> str | None:
    norm = _vernadette_normalize(command)
    if not re.search(r"\brecommend(?:ation|ed|ing)?\b", norm):
        return None
    if re.search(r"\bpursue\b", norm):
        return "Pursue"
    if re.search(r"\bpass\b|\bskip\b", norm):
        return "Pass"
    if re.search(r"\breview\b", norm):
        return "Review"
    return None


def _vernadette_resolve_grant(conn: sqlite3.Connection, command: str) -> tuple[sqlite3.Row | None, str | None]:
    candidates = conn.execute("SELECT * FROM grants ORDER BY updated_at DESC,id DESC").fetchall()
    if not candidates:
        return None, "There aren't any grants in the Grant Desk yet."
    norm = _vernadette_normalize(command)
    direct_title = [row for row in candidates if _vernadette_normalize(row["title"]) and _vernadette_normalize(row["title"]) in norm]
    if len(direct_title) == 1:
        return direct_title[0], None
    if len(direct_title) > 1:
        names = ", ".join(row["title"] for row in direct_title[:4])
        return None, f"I found more than one matching grant: {names}. Use a little more of the grant name."
    direct_funder = [row for row in candidates if _vernadette_normalize(row["funder"]) and _vernadette_normalize(row["funder"]) in norm]
    if len(direct_funder) == 1:
        return direct_funder[0], None
    meaningful = [w for w in norm.split() if len(w) > 2 and w not in VERNADETTE_STOPWORDS and not w.isdigit()]
    scored: list[tuple[int, sqlite3.Row]] = []
    for row in candidates:
        hay = set((_vernadette_normalize(row["title"]) + " " + _vernadette_normalize(row["funder"])).split())
        score = sum(1 for word in meaningful if word in hay)
        if score:
            scored.append((score, row))
    if scored:
        scored.sort(key=lambda x: (x[0], len(_vernadette_normalize(x[1]["title"]))), reverse=True)
        if len(scored) == 1 or scored[0][0] > scored[1][0]:
            return scored[0][1], None
        tied = [row["title"] for score, row in scored if score == scored[0][0]][:4]
        return None, f"I need a more specific grant name. I found: {', '.join(tied)}."
    return None, "I couldn't tell which Grant Desk record you mean. Use the grant name or funder."


def _vernadette_date_window(command: str, today: date) -> tuple[date | None, date | None, str]:
    norm = _vernadette_normalize(command)
    match = re.search(r"\b(?:next|within)\s+(7|30|60|90)\s+days\b", norm)
    if match:
        n = int(match.group(1))
        return today, today + timedelta(days=n), f"Next {n} days"
    if "this week" in norm:
        return today, today + timedelta(days=7), "Next 7 days"
    if "this month" in norm:
        _, end = _poe_month_bounds(today.year, today.month)
        return today, end, today.strftime("%B %Y")
    if "next month" in norm:
        _, this_end = _poe_month_bounds(today.year, today.month)
        first = this_end + timedelta(days=1)
        start, end = _poe_month_bounds(first.year, first.month)
        return start, end, first.strftime("%B %Y")
    for label, month in POE_MONTHS.items():
        if re.search(rf"\b{re.escape(label)}\b", norm):
            year_match = re.search(r"\b(20\d{2})\b", norm)
            year = int(year_match.group(1)) if year_match else today.year
            if not year_match and month < today.month:
                year += 1
            start, end = _poe_month_bounds(year, month)
            if year == today.year and month == today.month:
                start = today
            return start, end, date(year, month, 1).strftime("%B %Y")
    return None, None, "all recorded grants"


def _vernadette_grant_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": item.get("id"), "title": item.get("title"), "funder": item.get("funder"),
        "deadline": item.get("deadline"), "status": item.get("status"), "recommendation": item.get("recommendation"),
        "amount_min": item.get("amount_min"), "amount_max": item.get("amount_max"), "project_id": item.get("project_id"),
        "project_title": item.get("project_title"), "mission_fit": item.get("mission_fit"), "workload": item.get("workload"),
        "restrictions": item.get("restrictions"), "strategic_value": item.get("strategic_value"),
        "source_name": item.get("source_name"), "source_key": item.get("source_key"),
        "opportunity_number": item.get("opportunity_number"), "source_status": item.get("source_status"),
        "source_url": item.get("source_url"),
    }


def _vernadette_command_kind(command: str) -> str:
    norm = _vernadette_normalize(command)
    if re.search(r"\b(find|search|discover|look for)\b", norm) and re.search(r"\b(grant|grants|opportunity|opportunities|funding)\b", norm):
        return "discover"
    if re.search(r"\b(add|create|record)\b", norm) and re.search(r"\b(grant|opportunity)\b", norm):
        return "add"
    if re.search(r"\b(mark|move|set|update|change)\b", norm) and (_vernadette_resolve_status(command) or _vernadette_resolve_recommendation(command)):
        return "update"
    return "report"


def _vernadette_discovery_keyword(command: str) -> str:
    text = _vernadette_clean_command(command).strip().rstrip(". ")
    match = re.search(r"\b(?:find|search(?:\s+for)?|discover|look\s+for)\s+(?:me\s+)?(?:some\s+)?(?:grants?|opportunities|funding)(?:\s+(?:for|about|on|related\s+to))?\s*(.*)$", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return " ".join(match.group(1).strip(" ,;:-").split())[:180]


def _annotate_discovery_imported(conn: sqlite3.Connection, result: dict[str, Any]) -> dict[str, Any]:
    item = dict(result)
    source_key = str(item.get("source_key") or "").strip()
    existing = None
    if source_key:
        existing = conn.execute(
            "SELECT id,status,recommendation FROM grants WHERE source_name='Grants.gov' AND source_key=? LIMIT 1",
            (source_key,),
        ).fetchone()
    item["already_in_desk"] = bool(existing)
    item["grant_id"] = int(existing["id"]) if existing else None
    item["desk_status"] = existing["status"] if existing else None
    item["desk_recommendation"] = existing["recommendation"] if existing else None
    return item


def _vernadette_discovery_result(conn: sqlite3.Connection, keyword: str, rows_requested: int = 20) -> dict[str, Any]:
    try:
        found = search_grants_gov(keyword, rows=rows_requested)
    except GrantDiscoveryError as exc:
        return {
            "status": "clarification",
            "action": "discover",
            "message": str(exc),
            "provider": "Grants.gov",
            "query": keyword,
            "discovery_results": [],
            "open_grant_desk": True,
        }
    results = [_annotate_discovery_imported(conn, item) for item in found.get("results", [])]
    fresh = sum(1 for item in results if not item.get("already_in_desk"))
    return {
        "status": "ok",
        "action": "discover",
        "message": f"Grants.gov found {found.get('hit_count', len(results))} matching federal opportunity record(s). I brought back {len(results)} for review; {fresh} are not already in the Grant Desk.",
        "provider": found.get("provider", "Grants.gov"),
        "query": found.get("query", keyword),
        "hit_count": found.get("hit_count", len(results)),
        "discovery_results": results,
        "grants": [],
        "open_grant_desk": True,
    }


def _vernadette_command_discover(conn: sqlite3.Connection, command: str) -> dict[str, Any]:
    keyword = _vernadette_discovery_keyword(command)
    if not keyword:
        return {
            "status": "clarification",
            "action": "discover",
            "message": "Tell me what kind of funding to search for — for example: ‘Vernadette, find grants for rural community education.’",
            "discovery_results": [],
            "open_grant_desk": True,
        }
    return _vernadette_discovery_result(conn, keyword)


def _vernadette_command_report(conn: sqlite3.Connection, command: str) -> dict[str, Any]:
    norm = _vernadette_normalize(command)
    all_rows = grant_rows(conn)
    today = _vernadette_local_today(conn)
    if re.search(r"\bnext\s+(grant\s+)?deadline\b|\bwhat(?:'s| is)\s+next\b", str(command), flags=re.IGNORECASE):
        future = [g for g in all_rows if g.get("deadline") and g.get("status") in VERNADETTE_ACTIVE_STATUSES and g["deadline"] >= today.isoformat()]
        future.sort(key=lambda g: (g["deadline"], g["id"]))
        if not future:
            return {"status":"ok","action":"report","message":"There are no future active grant deadlines recorded right now.","grants":[],"open_grant_desk":True}
        g = future[0]
        days = (date.fromisoformat(g["deadline"]) - today).days
        return {"status":"ok","action":"report","message":f"Next deadline: {g['title']} from {g['funder']} is due {g['deadline']} — in {days} day(s). Status: {g['status']}; recommendation: {g['recommendation']}.","grants":[_vernadette_grant_public(g)],"open_grant_desk":True}
    filtered = list(all_rows)
    recommendation = None
    if re.search(r"\bshould\s+we\s+pursue\b|\brecommend(?:ed|ation)?\s+pursue\b|\bworth\s+pursuing\b", norm):
        recommendation = "Pursue"
    elif re.search(r"\brecommend(?:ed|ation)?\s+pass\b", norm):
        recommendation = "Pass"
    if recommendation:
        filtered = [g for g in filtered if g.get("recommendation") == recommendation]
    status = _vernadette_resolve_status(command)
    if status and not recommendation:
        # In report questions, "what should we pursue" is recommendation; a plain status word is a pipeline filter.
        filtered = [g for g in filtered if g.get("status") == status]
    if "active" in norm or "pipeline" in norm:
        filtered = [g for g in filtered if g.get("status") in VERNADETTE_ACTIVE_STATUSES]
    start, end, period_label = _vernadette_date_window(command, today)
    wants_due = "due" in norm or "deadline" in norm or start is not None or end is not None
    if wants_due and (start or end):
        filtered = [g for g in filtered if g.get("deadline") and (start is None or g["deadline"] >= start.isoformat()) and (end is None or g["deadline"] <= end.isoformat())]
    if wants_due:
        filtered.sort(key=lambda g: (g.get("deadline") is None, g.get("deadline") or "9999-12-31", g.get("id") or 0))
    if not all_rows:
        message = "The Grant Desk is empty right now."
    elif not filtered:
        message = "I don't have any Grant Desk records matching that request."
    else:
        descriptor = ""
        if recommendation:
            descriptor = f" recommended {recommendation}"
        elif status:
            descriptor = f" in {status}"
        if wants_due and (start or end):
            descriptor += f" due in {period_label.lower()}"
        message = f"I found {len(filtered)} grant{'' if len(filtered)==1 else 's'}{descriptor}."
        if filtered:
            first = filtered[0]
            deadline = f" due {first['deadline']}" if first.get("deadline") else ""
            message += f" First: {first['title']} · {first['funder']}{deadline} · {first['status']} · {first['recommendation']}."
    return {"status":"ok","action":"report","message":message,"grants":[_vernadette_grant_public(g) for g in filtered[:12]],"open_grant_desk":True}


def _vernadette_command_add(conn: sqlite3.Connection, command: str) -> dict[str, Any]:
    funder, title = _vernadette_extract_add_identity(command)
    if not funder or not title:
        return {"status":"clarification","action":"add","message":"Tell me the funder and grant name. A reliable format is: ‘Vernadette, add a grant from Appalachian Future Fund called Community Food Education due September 30, 2026 for $25,000.’"}
    today = _vernadette_local_today(conn)
    deadline = _vernadette_parse_deadline(command, today)
    amount_min, amount_max, amount_note = _vernadette_parse_amount(command)
    project = _poe_resolve_project(conn, command)
    source_match = re.search(r"https?://[^\s<>\"]+", str(command))
    source_url = source_match.group(0).rstrip(".,);]")[:1200] if source_match else ""
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO grants(funder,title,deadline,amount_min,amount_max,amount_notes,source_url,status,project_id,notes,mission_fit,workload,restrictions,strategic_value,recommendation,assessment_notes,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,'Discovered',?,'',3,3,3,3,'Review','Added conversationally; Vernadette has not scored this opportunity yet.','Vernadette',?,?)
        """,
        (funder,title,deadline.isoformat() if deadline else None,amount_min,amount_max,amount_note,source_url,int(project["id"]) if project else None,now,now),
    )
    grant_id = int(cur.lastrowid)
    log(conn, "grant", "Vernadette", f"Added grant opportunity conversationally: {title} · {funder}.")
    row = conn.execute("SELECT g.*,p.title AS project_title FROM grants g LEFT JOIN projects p ON p.id=g.project_id WHERE g.id=?", (grant_id,)).fetchone()
    extras = []
    if deadline:
        extras.append(f"due {deadline.isoformat()}")
    if amount_min is not None or amount_max is not None:
        if amount_min is not None and amount_max is not None and amount_min == amount_max:
            extras.append(f"${amount_min:,.0f}")
        elif amount_min is not None and amount_max is not None:
            extras.append(f"${amount_min:,.0f}–${amount_max:,.0f}")
        elif amount_max is not None:
            extras.append(f"up to ${amount_max:,.0f}")
        else:
            extras.append(f"at least ${amount_min:,.0f}")
    detail = f" · {' · '.join(extras)}" if extras else ""
    return {"status":"ok","action":"add","message":f"Added {title} from {funder} to the Grant Desk as Discovered / Review{detail}. I left the four assessment scores at neutral 3/5 until we evaluate it.","grants":[_vernadette_grant_public(row)],"open_grant_desk":True}


def _vernadette_command_update(conn: sqlite3.Connection, command: str) -> dict[str, Any]:
    grant, error = _vernadette_resolve_grant(conn, command)
    if error:
        return {"status":"clarification","action":"update","message":error}
    recommendation = _vernadette_resolve_recommendation(command)
    status = None if recommendation else _vernadette_resolve_status(command)
    if recommendation:
        conn.execute("UPDATE grants SET recommendation=?,updated_at=? WHERE id=?", (recommendation,utc_now(),int(grant["id"])))
        log(conn, "grant", "Vernadette", f"Changed grant recommendation: {grant['title']} → {recommendation}.")
        field_message = f"recommendation to {recommendation}"
    elif status:
        conn.execute("UPDATE grants SET status=?,updated_at=? WHERE id=?", (status,utc_now(),int(grant["id"])))
        log(conn, "grant", "Vernadette", f"Changed grant status: {grant['title']} → {status}.")
        field_message = f"status to {status}"
    else:
        return {"status":"clarification","action":"update","message":"Tell me which pipeline status or recommendation to use."}
    row = conn.execute("SELECT g.*,p.title AS project_title FROM grants g LEFT JOIN projects p ON p.id=g.project_id WHERE g.id=?", (int(grant["id"]),)).fetchone()
    return {"status":"ok","action":"update","message":f"Updated {grant['title']} — {field_message}.","grants":[_vernadette_grant_public(row)],"open_grant_desk":True}


def current_state() -> dict[str, Any]:
    with db() as conn:
        memory_rows = [
            enrich_memory_record(item)
            for item in rows(
                conn,
                """
                SELECT m.*,p.title AS project_title
                FROM institutional_memory m
                LEFT JOIN projects p ON p.id=m.project_id
                ORDER BY CASE m.status WHEN 'Active' THEN 0 ELSE 1 END,
                         CASE m.importance WHEN 'Core' THEN 0 ELSE 1 END,
                         m.updated_at DESC,m.id DESC
                """,
            )
        ]
        return {
            "buildings": rows(conn, "SELECT * FROM buildings ORDER BY name"),
            "agents": rows(conn, "SELECT * FROM agents ORDER BY name"),
            "people": rows(conn, "SELECT * FROM people ORDER BY CASE status WHEN 'Active' THEN 0 ELSE 1 END,display_name COLLATE NOCASE,id"),
            "activity_categories": rows(conn, "SELECT * FROM activity_categories WHERE active=1 ORDER BY sort_order,name"),
            "work_sessions": work_session_rows(conn),
            "work_session_audit": rows(conn, "SELECT * FROM work_session_audit ORDER BY id DESC LIMIT 250"),
            "work_summary": work_summary(conn),
            "grants": grant_rows(conn),
            "grant_summary": grant_summary(conn),
            "events": calendar_event_rows(conn),
            "calendar_summary": calendar_summary(conn),
            "projects": rows(conn, "SELECT * FROM projects ORDER BY id DESC"),
            "tasks": rows(conn, "SELECT * FROM tasks ORDER BY project_id DESC,sequence,id"),
            "approvals": approval_rows(conn),
            "notes": rows(conn, "SELECT * FROM notes ORDER BY id DESC LIMIT 100"),
            "institutional_memory": memory_rows,
            "memory_governance": memory_governance_summary(memory_rows),
            "playbooks": rows(
                conn,
                """
                SELECT pb.*,p.title AS project_title,a.name AS owner_name
                FROM playbooks pb
                LEFT JOIN projects p ON p.id=pb.project_id
                LEFT JOIN agents a ON a.id=pb.owner_agent_id
                ORDER BY CASE pb.status WHEN 'Active' THEN 0 WHEN 'Draft' THEN 1 ELSE 2 END,pb.updated_at DESC,pb.id DESC
                """,
            ),
            "activity": rows(conn, "SELECT * FROM activity_log ORDER BY id DESC LIMIT 100"),
            "ai_activity": [
                enrich_ai_call(row)
                for row in rows(conn, "SELECT * FROM ai_calls ORDER BY id DESC LIMIT 40")
            ],
            "ai_usage": ai_usage_summary(conn),
            "ai_control": ai_control_state(conn),
            "chief_plans": rows(conn, "SELECT * FROM chief_plans ORDER BY project_id DESC"),
            "research_artifacts": rows(conn, "SELECT * FROM research_artifacts ORDER BY task_id DESC"),
            "programs_artifacts": rows(conn, "SELECT * FROM programs_artifacts ORDER BY task_id DESC"),
            "chief_review_artifacts": rows(conn, "SELECT * FROM chief_review_artifacts ORDER BY task_id DESC"),
            "deliverables": rows(conn, "SELECT * FROM deliverables ORDER BY project_id DESC,deliverable_type,title,version,id"),
            "project_files": [
                {**dict(row), "exists": _repository_safe_path(row["relative_path"]).is_file()}
                for row in conn.execute(
                    """
                    SELECT pf.*,p.title AS project_title
                    FROM project_files pf JOIN projects p ON p.id=pf.project_id
                    ORDER BY pf.updated_at DESC,pf.id DESC
                    """
                ).fetchall()
            ],
            "revision_requests": rows(conn, "SELECT * FROM revision_requests ORDER BY id DESC"),
            "revision_plans": rows(conn, "SELECT * FROM revision_plans ORDER BY id DESC"),
            "workflow_runs": rows(conn, "SELECT * FROM workflow_runs ORDER BY project_id DESC"),
            "executive_briefing": executive_briefing(conn),
            "briefing_snapshots": rows(conn, "SELECT * FROM briefing_snapshots ORDER BY captured_at DESC,id DESC LIMIT 12"),
            "library_collections": library_catalog_rows(conn),
            "library_materials": library_material_rows(conn),
            "library_inbox": library_inbox_rows(conn),
            "programs_library_preflights": [
                _programs_library_preflight_public(row)
                for row in conn.execute(
                    "SELECT * FROM programs_library_preflights ORDER BY updated_at DESC,task_id DESC"
                ).fetchall()
            ],
            "program_archive_events": rows(
                conn,
                "SELECT * FROM program_archive_events ORDER BY created_at DESC,id DESC LIMIT 100",
            ),
            "library_foundation": library_foundation_summary(conn),
            "environment": environment_summary(conn),
            "system_health": system_health(conn),
            "executive": executive_summary(conn),
            "generated_at": utc_now(),
        }


def reset_agents(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE agents SET building_id=home_building_id,status='Available',task_id=NULL,updated_at=?", (utc_now(),))


def reset_runtime() -> None:
    with db() as conn:
        conn.execute("DELETE FROM activity_log")
        conn.execute("DELETE FROM ai_calls")
        conn.execute("DELETE FROM chief_plans")
        conn.execute("DELETE FROM research_artifacts")
        conn.execute("DELETE FROM programs_artifacts")
        conn.execute("DELETE FROM programs_library_preflights")
        conn.execute("DELETE FROM chief_review_artifacts")
        conn.execute("DELETE FROM project_files")
        conn.execute("DELETE FROM deliverables")
        conn.execute("DELETE FROM revision_plans")
        conn.execute("DELETE FROM revision_requests")
        conn.execute("DELETE FROM workflow_runs")
        conn.execute("DELETE FROM chief_request_submissions")
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM approvals")
        conn.execute("DELETE FROM tasks")
        # Durable project memory survives reset, but becomes archived before its
        # project is deleted so it cannot silently broaden into active
        # institution-wide AI context through ON DELETE SET NULL.
        conn.execute(
            "UPDATE institutional_memory SET status='Archived', updated_at=? "
            "WHERE project_id IS NOT NULL AND status='Active'",
            (utc_now(),),
        )
        # Project-scoped playbooks survive as archived history; archiving first
        # prevents ON DELETE SET NULL from broadening them into institution-wide procedure.
        conn.execute(
            "UPDATE playbooks SET status='Archived', updated_at=? "
            "WHERE project_id IS NOT NULL AND status!='Archived'",
            (utc_now(),),
        )
        conn.execute("DELETE FROM projects")
        reset_agents(conn)
        log(conn, "system", "Campus", "Campus reset. Agents are ready.")
    if REPOSITORY.exists():
        shutil.rmtree(REPOSITORY, ignore_errors=True)
    REPOSITORY.mkdir(parents=True, exist_ok=True)


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        await ws.send_json({"type": "state", "data": current_state()})

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self) -> None:
        payload = {"type": "state", "data": current_state()}
        dead: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self.disconnect(client)


hub = Hub()
workflow_task: asyncio.Task | None = None
chief_plan_lock = asyncio.Lock()
CHIEF_DUPLICATE_WINDOW_SECONDS = 120


async def pause(seconds: float = 1.8) -> None:
    await asyncio.sleep(seconds)


async def set_agent(agent_id: str, *, building: str | None = None, status: str | None = None, task_id: int | None | object = ...) -> None:
    with db() as conn:
        current = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not current:
            raise KeyError(agent_id)
        new_building = building if building is not None else current["building_id"]
        new_status = status if status is not None else current["status"]
        new_task_id = current["task_id"] if task_id is ... else task_id
        conn.execute(
            "UPDATE agents SET building_id=?,status=?,task_id=?,updated_at=? WHERE id=?",
            (new_building, new_status, new_task_id, utc_now(), agent_id),
        )
    await hub.broadcast()


async def set_task(task_id: int, status: str, result: str | None = None) -> None:
    with db() as conn:
        if result is None:
            conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, utc_now(), task_id))
        else:
            conn.execute("UPDATE tasks SET status=?,result=?,updated_at=? WHERE id=?", (status, result, utc_now(), task_id))
    await hub.broadcast()


async def add_log(event_type: str, actor: str, message: str) -> None:
    with db() as conn:
        log(conn, event_type, actor, message)
    await hub.broadcast()


OWNER_HOME = {
    "chief": "manor",
    "programs": "barn",
    "research": "library",
    "caretaker": "fruit_forest",
}

OWNER_LABEL = {
    "chief": "Stella — Chief of Staff",
    "programs": "Percy — Director of Programs & Education",
    "research": "Rose — Director of Research & Archives",
    "caretaker": "Stewart — Land Steward",
}

BUILDING_LABEL = {
    "manor": "Mavis Manor",
    "barn": "Coopenheimer Barn",
    "library": "Library of Mavis",
    "fruit_forest": "Fruit Forest",
}


def simulated_task_result(task: sqlite3.Row) -> str:
    owner = OWNER_LABEL.get(task["owner_agent_id"], task["owner_agent_id"])
    brief = " ".join(str(task["brief"] or task["title"]).split())
    return (
        f"Simulated — {owner}\n\n"
        f"v0.8.7.4.2 simulated execution completed the approved workflow step: {brief[:700]} "
        "This role is not AI-powered yet. No specialist AI call, web research, publication, email, "
        "purchase, submission, or external action occurred."
    )


async def execute_real_research_task(
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    task_brief_override: str | None = None,
) -> tuple[str, str]:
    """Run the approved Research brief with its configured provider and persist the structured artifact."""
    task_id = int(task["id"])

    with db() as conn:
        plan = conn.execute(
            "SELECT * FROM chief_plans WHERE project_id=?",
            (project["id"],),
        ).fetchone()
        prior_rows = conn.execute(
            """
            SELECT t.owner_agent_id,t.result
            FROM tasks t
            WHERE t.project_id=? AND t.sequence < ? AND t.status='Completed' AND t.result IS NOT NULL
            ORDER BY t.sequence
            """,
            (project["id"], task["sequence"]),
        ).fetchall()

    project_summary = plan["summary"] if plan else project["title"]
    prior_results = [
        {
            "owner": OWNER_LABEL.get(row["owner_agent_id"], row["owner_agent_id"]),
            "result": row["result"],
        }
        for row in prior_rows
    ]

    with db() as conn:
        institutional_memory_for_prompt_context = institutional_memory_for_prompt(conn, int(project["id"]))

    research_provider_id = role_provider_id("research")
    research_status = provider_public_status(research_provider_id)
    require_ai_allowed("research_task", research_provider_id)
    provider = get_role_provider("research")
    started = time.perf_counter()

    try:
        research_result = await asyncio.to_thread(
            run_research,
            provider,
            project_title=project["title"],
            project_summary=project_summary,
            task_title=task["title"],
            task_brief=task_brief_override or task["brief"] or task["title"],
            prior_results=prior_results,
            institutional_memory=institutional_memory_for_prompt_context,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    research_provider_id,
                    str(research_status.get("model", "")),
                    "research_task",
                    "Failed",
                    latency_ms,
                    len(str(task_brief_override or task["brief"] or task["title"])),
                    0,
                    str(exc)[:500],
                    int(project["id"]),
                    task_id,
                    utc_now(),
                ),
            )
        raise

    latency_ms = int((time.perf_counter() - started) * 1000)
    generation = research_result.generation

    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_artifacts(
                task_id,project_id,content_json,provider,model,created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                task_id,
                project["id"],
                json.dumps(research_result.artifact, ensure_ascii=False),
                generation.provider,
                generation.model,
                utc_now(),
            ),
        )
        materialize_research_deliverables(
            conn,
            project=project,
            task=task,
            artifact=research_result.artifact,
            provider=generation.provider,
            model=generation.model,
        )
        conn.execute(
            """
            INSERT INTO ai_calls(
                provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                generation.provider,
                generation.model,
                "research_task",
                "Success",
                latency_ms,
                generation.input_chars,
                generation.output_chars,
                f"Research completed task #{task_id}: {task['title']}",
                int(project["id"]),
                task_id,
                utc_now(),
            ),
        )

    return research_result.rendered_text, generation.model


async def execute_real_programs_task(
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    task_brief_override: str | None = None,
) -> tuple[str, str]:
    """Run the approved Programs brief with its configured provider and persist the structured artifact."""
    task_id = int(task["id"])

    with db() as conn:
        plan = conn.execute(
            "SELECT * FROM chief_plans WHERE project_id=?",
            (project["id"],),
        ).fetchone()

        research_rows = conn.execute(
            """
            SELECT ra.content_json, ra.provider, ra.model, t.title, t.sequence
            FROM research_artifacts ra
            JOIN tasks t ON t.id = ra.task_id
            WHERE ra.project_id=? AND t.sequence < ?
            ORDER BY t.sequence
            """,
            (project["id"], task["sequence"]),
        ).fetchall()

        prior_rows = conn.execute(
            """
            SELECT t.owner_agent_id,t.result
            FROM tasks t
            WHERE t.project_id=? AND t.sequence < ?
              AND t.status='Completed'
              AND t.result IS NOT NULL
              AND t.owner_agent_id != 'research'
            ORDER BY t.sequence
            """,
            (project["id"], task["sequence"]),
        ).fetchall()

    project_summary = plan["summary"] if plan else project["title"]

    research_artifacts: list[dict[str, Any]] = []
    for row in research_rows[:4]:
        try:
            artifact = json.loads(row["content_json"])
        except (TypeError, json.JSONDecodeError):
            continue

        if isinstance(artifact, dict):
            artifact = dict(artifact)
            artifact["_source"] = {
                "task_title": row["title"],
                "provider": row["provider"],
                "model": row["model"],
            }
            research_artifacts.append(artifact)

    prior_results = [
        {
            "owner": OWNER_LABEL.get(row["owner_agent_id"], row["owner_agent_id"]),
            "result": row["result"],
        }
        for row in prior_rows
    ]

    with db() as conn:
        institutional_memory_for_prompt_context = institutional_memory_for_prompt(conn, int(project["id"]))
        library_context_for_programs = programs_library_context_for_task(conn, task_id)

    programs_provider_id = role_provider_id("programs")
    programs_status = provider_public_status(programs_provider_id)
    require_ai_allowed("programs_task", programs_provider_id)
    provider = get_role_provider("programs")
    started = time.perf_counter()

    try:
        programs_result = await asyncio.to_thread(
            run_programs,
            provider,
            project_title=project["title"],
            project_summary=project_summary,
            task_title=task["title"],
            task_brief=task_brief_override or task["brief"] or task["title"],
            research_artifacts=research_artifacts,
            prior_results=prior_results,
            institutional_memory=institutional_memory_for_prompt_context,
            library_context=library_context_for_programs,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    programs_provider_id,
                    str(programs_status.get("model", "")),
                    "programs_task",
                    "Failed",
                    latency_ms,
                    len(str(task_brief_override or task["brief"] or task["title"])),
                    0,
                    str(exc)[:500],
                    int(project["id"]),
                    task_id,
                    utc_now(),
                ),
            )
        raise

    latency_ms = int((time.perf_counter() - started) * 1000)
    generation = programs_result.generation

    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO programs_artifacts(
                task_id,project_id,content_json,provider,model,created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                task_id,
                project["id"],
                json.dumps(programs_result.artifact, ensure_ascii=False),
                generation.provider,
                generation.model,
                utc_now(),
            ),
        )
        materialize_programs_deliverables(
            conn,
            project=project,
            task=task,
            artifact=programs_result.artifact,
            provider=generation.provider,
            model=generation.model,
        )
        conn.execute(
            """
            INSERT INTO ai_calls(
                provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                generation.provider,
                generation.model,
                "programs_task",
                "Success",
                latency_ms,
                generation.input_chars,
                generation.output_chars,
                f"Programs completed task #{task_id}: {task['title']}",
                int(project["id"]),
                task_id,
                utc_now(),
            ),
        )

    return programs_result.rendered_text, generation.model


async def execute_real_chief_review_task(
    *,
    project: sqlite3.Row,
    task: sqlite3.Row,
    task_brief_override: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Review completed internal work with the configured Chief provider and persist the executive artifact."""
    task_id = int(task["id"])

    with db() as conn:
        plan = conn.execute(
            "SELECT * FROM chief_plans WHERE project_id=?",
            (project["id"],),
        ).fetchone()

        research_rows = conn.execute(
            """
            SELECT ra.content_json,ra.provider,ra.model,t.title,t.sequence
            FROM research_artifacts ra
            JOIN tasks t ON t.id=ra.task_id
            WHERE ra.project_id=? AND t.status='Completed'
            ORDER BY t.sequence
            """,
            (project["id"],),
        ).fetchall()

        programs_rows = conn.execute(
            """
            SELECT pa.content_json,pa.provider,pa.model,t.title,t.sequence
            FROM programs_artifacts pa
            JOIN tasks t ON t.id=pa.task_id
            WHERE pa.project_id=? AND t.status='Completed'
            ORDER BY t.sequence
            """,
            (project["id"],),
        ).fetchall()

        other_rows = conn.execute(
            """
            SELECT owner_agent_id,title,result,sequence
            FROM tasks
            WHERE project_id=?
              AND id != ?
              AND status='Completed'
              AND result IS NOT NULL
              AND owner_agent_id NOT IN ('research','programs')
            ORDER BY sequence
            """,
            (project["id"], task_id),
        ).fetchall()

        deliverable_rows = conn.execute(
            """
            SELECT *
            FROM deliverables
            WHERE project_id=? AND status!='Superseded'
            ORDER BY deliverable_type,title,id
            """,
            (project["id"],),
        ).fetchall()
        expected_deliverables = expected_deliverables_for_project(
            conn,
            int(project["id"]),
        )
        revision_context = revision_context_for_project(
            conn,
            int(project["id"]),
        )

    def parse_json_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []

    def load_artifacts(source_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for row in source_rows:
            try:
                content = json.loads(row["content_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(content, dict):
                continue
            artifact = dict(content)
            artifact["_source"] = {
                "task_title": row["title"],
                "provider": row["provider"],
                "model": row["model"],
            }
            artifacts.append(artifact)
        return artifacts

    project_summary = plan["summary"] if plan else project["title"]
    success_criteria = parse_json_list(plan["success_criteria_json"] if plan else None)
    risk_notes = parse_json_list(plan["risk_notes_json"] if plan else None)
    questions_for_executive = parse_json_list(plan["questions_json"] if plan else None)

    research_artifacts = load_artifacts(list(research_rows))
    programs_artifacts = load_artifacts(list(programs_rows))
    other_completed_results = [
        {
            "owner": OWNER_LABEL.get(row["owner_agent_id"], row["owner_agent_id"]),
            "title": row["title"],
            "result": row["result"],
        }
        for row in other_rows
    ]

    if revision_context:
        other_completed_results.append({
            "owner": "Human + Chief Revision Plan",
            "title": f"Revision {revision_context['revision_number']} context",
            "result": (
                f"Human revision instruction: {revision_context.get('human_request','')}\n"
                f"Revision strategy: {revision_context.get('summary','')}"
            ),
        })

    deliverable_context: list[dict[str, Any]] = []
    produced_types: set[str] = set()
    for row in deliverable_rows:
        produced_types.add(str(row["deliverable_type"]))
        deliverable_context.append({
            "deliverable_key": row["deliverable_key"],
            "deliverable_type": row["deliverable_type"],
            "title": row["title"],
            "purpose": row["purpose"],
            "status": row["status"],
            "content_excerpt": str(row["content_md"] or "")[:2400],
            "verification_items": _safe_json_list(row["verification_json"]),
            "created_by": row["created_by"],
        })

    for item in expected_deliverables:
        if item.get("type") in produced_types:
            continue
        deliverable_context.append({
            "deliverable_key": f"expected:{item.get('type','project_output')}",
            "deliverable_type": item.get("type", "project_output"),
            "title": item.get("title", "Expected Deliverable"),
            "purpose": item.get("purpose", ""),
            "status": "Missing — expected deliverable not produced",
            "content": "",
            "verification_items": [],
            "created_by": "Expected by approved Chief plan",
        })

    with db() as conn:
        institutional_memory_for_prompt_context = institutional_memory_for_prompt(conn, int(project["id"]))
        playbook_context = playbooks_for_prompt(conn, int(project["id"]))

    chief_provider_id = role_provider_id("chief")
    chief_status = provider_public_status(chief_provider_id)
    require_ai_allowed("chief_final_review", chief_provider_id)
    provider = get_role_provider("chief")
    started = time.perf_counter()

    try:
        review_result = await asyncio.to_thread(
            run_chief_review,
            provider,
            project_title=project["title"],
            project_summary=project_summary,
            task_title=task["title"],
            task_brief=task_brief_override or task["brief"] or task["title"],
            success_criteria=success_criteria,
            risk_notes=risk_notes,
            questions_for_executive=questions_for_executive,
            research_artifacts=research_artifacts,
            programs_artifacts=programs_artifacts,
            deliverables=deliverable_context,
            other_completed_results=other_completed_results,
            institutional_memory=institutional_memory_for_prompt_context,
            playbooks=playbook_context,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    chief_provider_id,
                    str(chief_status.get("model", "")),
                    "chief_final_review",
                    "Failed",
                    latency_ms,
                    len(str(task_brief_override or task["brief"] or task["title"])),
                    0,
                    str(exc)[:500],
                    int(project["id"]),
                    task_id,
                    utc_now(),
                ),
            )
        raise

    latency_ms = int((time.perf_counter() - started) * 1000)
    generation = review_result.generation

    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO chief_review_artifacts(
                task_id,project_id,content_json,provider,model,attempt_count,created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                task_id,
                project["id"],
                json.dumps(review_result.artifact, ensure_ascii=False),
                generation.provider,
                generation.model,
                review_result.attempt_count,
                utc_now(),
            ),
        )
        materialize_chief_deliverables(
            conn,
            project=project,
            task=task,
            artifact=review_result.artifact,
            provider=generation.provider,
            model=generation.model,
        )
        apply_chief_deliverable_review(
            conn,
            project_id=int(project["id"]),
            artifact=review_result.artifact,
        )
        conn.execute(
            """
            INSERT INTO ai_calls(
                provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                generation.provider,
                generation.model,
                "chief_final_review",
                "Success",
                latency_ms,
                generation.input_chars,
                generation.output_chars,
                (
                    f"Chief completed final review for task #{task_id} in "
                    f"{review_result.attempt_count} same-provider attempt(s): {task['title']}"
                ),
                int(project["id"]),
                task_id,
                utc_now(),
            ),
        )

    return review_result.rendered_text, generation.model, review_result.artifact


async def execute_approved_plan(project_id: int, *, resume: bool = False, revision: bool = False) -> None:
    """Execute or resume an approved project while preserving completed work."""
    try:
        with db() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            tasks = conn.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY sequence,id",
                (project_id,),
            ).fetchall()

        if not project:
            raise RuntimeError("Approved project was not found.")
        if not tasks:
            raise RuntimeError("Approved project has no tasks to execute.")

        with db() as conn:
            revision_row = active_revision_plan(conn, project_id)
            revision = bool(revision or revision_row)
            set_workflow_run(
                conn,
                project_id,
                state="Revision Running" if revision else "Running",
                current_task_id=None,
                last_error=None,
                increment_retry=resume,
            )
            conn.execute(
                "UPDATE projects SET status='Active',updated_at=? WHERE id=?",
                (utc_now(), project_id),
            )

        chief_tasks = [task for task in tasks if task["owner_agent_id"] == "chief"]
        final_chief_task_id = int(chief_tasks[-1]["id"]) if chief_tasks else None

        # The approved Chief synthesis task is a final review. Keep it last even
        # if the planning model placed another specialist immediately after it.
        if final_chief_task_id is not None:
            tasks = [
                task for task in tasks
                if int(task["id"]) != final_chief_task_id
            ] + [
                task for task in tasks
                if int(task["id"]) == final_chief_task_id
            ]

        await set_agent("chief", building="manor", status="Activating approved plan", task_id=None)
        await add_log(
            "recovery" if resume else ("revision" if revision else "execution"),
            "Chief of Staff",
            (
                f"Resuming {'revision' if revision else 'approved'} workflow for {project['title']}. Completed tasks will not be repeated."
                if resume
                else (
                    f"Human approved the selective revision plan for {project['title']}. Beginning v0.8.7.4.2 revision work while preserving unselected tasks and output versions."
                    if revision
                    else f"Human approved the plan for {project['title']}. Beginning v0.8.7.4.2 execution with restart-safe workflow journaling."
                )
            ),
        )
        await pause(1.0)

        for task in tasks:
            task_id = int(task["id"])

            # Recovery never repeats a task that already reached Completed.
            if task["status"] == "Completed":
                continue

            with db() as conn:
                set_workflow_run(
                    conn,
                    project_id,
                    state="Revision Running" if revision else "Running",
                    current_task_id=task_id,
                    last_error=None,
                )

            with db() as conn:
                revision_brief = revision_task_instruction(conn, project_id, task_id)
                revision_context = revision_context_for_project(conn, project_id) if revision else None

            owner = task["owner_agent_id"]
            if revision and owner == "chief" and task_id == final_chief_task_id and not revision_brief:
                revision_brief = (
                    "Review the revised package against the human revision instruction and selective revision plan. "
                    f"Human requested: {revision_context.get('human_request','') if revision_context else ''} "
                    f"Revision strategy: {revision_context.get('summary','') if revision_context else ''}"
                ).strip()

            owner_label = OWNER_LABEL.get(owner, owner)
            home = OWNER_HOME.get(owner, "manor")
            home_label = BUILDING_LABEL.get(home, home)

            # The Chief visibly briefs specialist departments before their work begins.
            if owner != "chief":
                await set_agent(
                    "chief",
                    building=home,
                    status=f"Briefing {owner_label}",
                    task_id=None,
                )
                await add_log(
                    "delegation",
                    "Chief of Staff",
                    f"Carrying the approved brief to {owner_label} at {home_label}: {task['title']}",
                )
                await pause(1.5)
                await set_agent(
                    "chief",
                    building="manor",
                    status="Returning to Mavis Manor",
                    task_id=None,
                )

            await set_task(task_id, "In Progress")
            await set_agent(
                owner,
                building=home,
                status=f"Working: {task['title'][:64]}",
                task_id=task_id,
            )
            if owner == "research":
                await add_log(
                    "workflow",
                    owner_label,
                    f"Started approved Research task with {provider_public_status(role_provider_id('research'))['provider']}: {task['title']}",
                )
                await set_agent(
                    "research",
                    building="library",
                    status=f"Researching with {provider_public_status(role_provider_id('research'))['provider']}: {task['title'][:52]}",
                    task_id=task_id,
                )
                try:
                    result, research_model = await execute_real_research_task(
                        project=project,
                        task=task,
                        task_brief_override=revision_brief,
                    )
                except Exception as exc:
                    await set_task(task_id, "Blocked", f"Research AI failed: {str(exc)[:600]}")
                    await set_agent(
                        "research",
                        building="library",
                        status="Research blocked — needs attention",
                        task_id=None,
                    )
                    await add_log(
                        "ai_error",
                        "Research",
                        f"Research provider failed after automatic retry for task: {task['title']}. Execution stopped so the failure is visible.",
                    )
                    raise RuntimeError(f"Research task failed: {exc}") from exc

                await set_task(task_id, "Completed", result)
                await add_log(
                    "result",
                    owner_label,
                    f"Completed real AI Research task using {research_model}: {task['title']}",
                )

            elif owner == "programs":
                # Programs Library First: the local Librarian checks trusted Mavis
                # holdings before Programs is allowed to spend an AI call.
                await set_agent(
                    "programs",
                    building="library",
                    status=f"Checking Library first: {task['title'][:48]}",
                    task_id=task_id,
                )
                with db() as conn:
                    preflight = ensure_programs_library_preflight(
                        conn,
                        project=project,
                        task=task,
                        task_brief_override=revision_brief,
                    )

                preflight_result = preflight.get("result") or {}
                if preflight.get("status") == "Pending" and not preflight.get("decision"):
                    match_count = int(preflight_result.get("collection_count") or 0)
                    material_count = int(preflight_result.get("material_count") or 0)
                    message = (
                        f"Programs Library First found {match_count} trusted collection(s) and "
                        f"{material_count} trusted material(s). Human choice required before Programs generates anything."
                    )
                    with db() as conn:
                        now = utc_now()
                        conn.execute(
                            "UPDATE tasks SET status='Library Review',result=?,updated_at=? WHERE id=?",
                            (message, now, task_id),
                        )
                        conn.execute(
                            "UPDATE projects SET status='Awaiting Library Decision',updated_at=? WHERE id=?",
                            (now, project_id),
                        )
                        set_workflow_run(
                            conn,
                            project_id,
                            state="Awaiting Library Decision",
                            current_task_id=task_id,
                            last_error=None,
                        )
                        conn.execute(
                            "UPDATE agents SET building_id='library',status='Waiting for Library First decision',task_id=?,updated_at=? WHERE id='programs'",
                            (task_id, now),
                        )
                        conn.execute(
                            "UPDATE agents SET building_id='manor',status='Waiting for Library First decision',task_id=NULL,updated_at=? WHERE id='chief'",
                            (now,),
                        )
                        log(
                            conn,
                            "library_first",
                            "Librarian",
                            (
                                f"Programs Library First paused '{task['title']}'. Trusted Library matches were found; "
                                "the human must choose Reuse, Revise, or Create New before any Programs AI call."
                            ),
                        )
                    await hub.broadcast()
                    return

                decision = str(preflight.get("decision") or "create_new").strip().lower()
                if decision == "reuse":
                    collection_id = preflight.get("selected_collection_id")
                    if not collection_id:
                        raise RuntimeError("Programs Library First reuse decision is missing a selected Library collection.")
                    await set_agent(
                        "programs",
                        building="library",
                        status="Reusing approved Library holdings",
                        task_id=task_id,
                    )
                    with db() as conn:
                        result = materialize_programs_library_reuse(
                            conn,
                            project=project,
                            task=task,
                            collection_id=int(collection_id),
                        )
                    await set_task(task_id, "Completed", result)
                    await add_log(
                        "library_first",
                        owner_label,
                        f"Completed Programs task by reusing trusted Library material with zero Programs AI calls: {task['title']}",
                    )
                else:
                    if preflight.get("status") == "No Match":
                        await add_log(
                            "library_first",
                            "Librarian",
                            f"No useful trusted Library match for Programs task; new Programs work is allowed: {task['title']}",
                        )
                    elif decision == "revise":
                        await add_log(
                            "library_first",
                            "Human",
                            f"Chose Revise from trusted Library material before Programs work: {task['title']}",
                        )
                    else:
                        await add_log(
                            "library_first",
                            "Human",
                            f"Chose Create New after reviewing trusted Library matches: {task['title']}",
                        )

                    programs_provider_name = provider_public_status(role_provider_id("programs"))["provider"]
                    await add_log(
                        "workflow",
                        owner_label,
                        f"Started approved Programs task with {programs_provider_name} after Library First: {task['title']}",
                    )
                    await set_agent(
                        "programs",
                        building="barn",
                        status=f"Building program with {programs_provider_name}: {task['title'][:48]}",
                        task_id=task_id,
                    )

                    try:
                        result, programs_model = await execute_real_programs_task(
                            project=project,
                            task=task,
                            task_brief_override=revision_brief,
                        )
                    except Exception as exc:
                        await set_task(task_id, "Blocked", f"Programs AI failed: {str(exc)[:600]}")
                        await set_agent(
                            "programs",
                            building="barn",
                            status="Programs blocked — needs attention",
                            task_id=None,
                        )
                        await add_log(
                            "ai_error",
                            "Programs",
                            f"Programs provider failed after automatic retry for task: {task['title']}. Execution stopped so the failure is visible.",
                        )
                        raise RuntimeError(f"Programs task failed: {exc}") from exc

                    await set_task(task_id, "Completed", result)
                    await add_log(
                        "result",
                        owner_label,
                        f"Completed real AI Programs task using {programs_model} after Library First: {task['title']}",
                    )

            elif owner == "chief" and task_id == final_chief_task_id:
                chief_provider_name = provider_public_status(role_provider_id("chief"))["provider"]
                await add_log(
                    "review",
                    "Chief of Staff",
                    f"Started real final synthesis with {chief_provider_name}: {task['title']}",
                )
                await set_agent(
                    "chief",
                    building="manor",
                    status=f"Synthesizing final review with {chief_provider_name}",
                    task_id=task_id,
                )

                try:
                    result, chief_review_model, chief_review_artifact = await execute_real_chief_review_task(
                        project=project,
                        task=task,
                        task_brief_override=revision_brief,
                    )
                except Exception as exc:
                    await set_task(task_id, "Blocked", f"Chief final review AI failed: {str(exc)[:600]}")
                    await set_agent(
                        "chief",
                        building="manor",
                        status="Chief final review blocked — needs attention",
                        task_id=None,
                    )
                    await add_log(
                        "ai_error",
                        "Chief of Staff",
                        f"Chief final-review provider failed for task: {task['title']}. Execution stopped so the failure is visible.",
                    )
                    raise RuntimeError(f"Chief final review failed: {exc}") from exc

                await set_task(task_id, "Completed", result)
                await add_log(
                    "review",
                    "Chief of Staff",
                    (
                        f"Completed real AI final review using {chief_review_model}. "
                        f"Recommendation: {chief_review_artifact.get('approval_recommendation', 'review')}."
                    ),
                )

            else:
                await add_log(
                    "workflow",
                    owner_label,
                    f"Started approved task: {task['title']}. This role remains simulated in v0.8.7.4.2.",
                )
                await pause(2.0)
                result = simulated_task_result(task)
                if revision_brief:
                    result += (
                        "\n\nRevision instruction applied locally:\n"
                        + revision_brief
                    )
                await set_task(task_id, "Completed", result)
                if owner == "caretaker":
                    with db() as conn:
                        materialize_caretaker_deliverables(
                            conn,
                            project=project,
                            task=task,
                            result=result,
                        )
                await add_log("result", owner_label, f"Completed simulated task: {task['title']}")

            if owner != "chief":
                await set_agent(
                    owner,
                    building="manor",
                    status="Delivering result to Chief of Staff",
                    task_id=None,
                )
                await add_log(
                    "movement",
                    owner_label,
                    f"Carrying the completed result to Mavis Manor for handoff.",
                )
                await pause(1.5)
                await set_agent(
                    owner,
                    building=home,
                    status=f"Returning to {home_label}",
                    task_id=None,
                )
                await pause(1.0)
                await set_agent(owner, building=home, status="Available", task_id=None)
            else:
                await set_agent("chief", building="manor", status="Reviewing workflow progress", task_id=None)

            with db() as conn:
                set_workflow_run(
                    conn,
                    project_id,
                    state="Revision Running" if revision else "Running",
                    current_task_id=None,
                    last_error=None,
                )

        await set_agent(
            "chief",
            building="manor",
            status="Preparing execution review",
            task_id=None,
        )
        await add_log(
            "review",
            "Chief of Staff",
            "All selected work reached Completed. The Chief final review is evaluating the current v0.8.7.4.2 output package, including preserved and newly versioned deliverables.",
        )
        await pause(1.2)

        with db() as conn:
            completed = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id=? AND status='Completed'",
                (project_id,),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]

            chief_review_row = conn.execute(
                """
                SELECT *
                FROM chief_review_artifacts
                WHERE project_id=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

            review_artifact: dict[str, Any] = {}
            if chief_review_row:
                try:
                    parsed_review = json.loads(chief_review_row["content_json"])
                    if isinstance(parsed_review, dict):
                        review_artifact = parsed_review
                except (TypeError, json.JSONDecodeError):
                    review_artifact = {}

            coverage = deliverable_coverage(conn, project_id)
            recommendation = str(review_artifact.get("approval_recommendation") or "review")
            executive_summary_text = str(
                review_artifact.get("executive_summary")
                or f"v0.8.7.4.2 completed {completed} of {total} approved tasks."
            )
            verification_items = review_artifact.get("verification_before_public_use") or []
            decisions = review_artifact.get("executive_decisions_needed") or []

            summary_parts = [
                f"Chief recommendation: {recommendation.replace('_', ' ').upper()}.",
                executive_summary_text,
                (
                    f"Project outputs: {coverage['produced_count']} produced"
                    + (
                        f"; {coverage['missing_count']} expected output(s) still missing."
                        if coverage["missing_count"]
                        else "; expected output coverage is complete."
                    )
                ),
            ]
            if verification_items:
                summary_parts.append(
                    "Verification before public use: "
                    + "; ".join(str(item) for item in verification_items[:3])
                )
            if decisions:
                summary_parts.append(
                    "Executive decisions needed: "
                    + "; ".join(str(item) for item in decisions[:3])
                )
            summary_parts.append(
                "Your approval accepts the internal package only; it does not authorize publishing, email, purchasing, spending, submission, external contact, or another outside action."
            )

            now = utc_now()
            final_title = f"Chief final review: {project['title']}"
            final_summary = " ".join(summary_parts)[:4000]

            # Resume/recovery can reach this finalization block more than once.
            # Reuse one pending final-review approval instead of creating duplicates.
            pending_final = conn.execute(
                """
                SELECT id
                FROM approvals
                WHERE project_id=?
                  AND status='Pending'
                  AND title LIKE 'Chief final review:%'
                ORDER BY id
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

            if pending_final:
                keep_id = int(pending_final["id"])
                conn.execute(
                    """
                    UPDATE approvals
                    SET title=?,summary=?,updated_at=?
                    WHERE id=?
                    """,
                    (final_title, final_summary, now, keep_id),
                )
                conn.execute(
                    """
                    UPDATE approvals
                    SET status='Superseded',updated_at=?
                    WHERE project_id=?
                      AND status='Pending'
                      AND title LIKE 'Chief final review:%'
                      AND id != ?
                    """,
                    (now, project_id, keep_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        final_title,
                        final_summary,
                        "Pending",
                        now,
                        now,
                    ),
                )

            conn.execute(
                "UPDATE projects SET status='Awaiting Execution Review',updated_at=? WHERE id=?",
                (now, project_id),
            )
            conn.execute(
                "UPDATE agents SET building_id='manor',status='Waiting for execution review',task_id=NULL,updated_at=? WHERE id='chief'",
                (now,),
            )
            set_workflow_run(
                conn,
                project_id,
                state="Awaiting Human Review",
                current_task_id=None,
                last_error=None,
            )
            if revision:
                conn.execute(
                    """
                    UPDATE revision_plans
                    SET status='Awaiting Human Review',updated_at=?
                    WHERE project_id=? AND status='Executing'
                    """,
                    (now, project_id),
                )
                conn.execute(
                    """
                    UPDATE revision_requests
                    SET status='Awaiting Human Review',updated_at=?
                    WHERE id=(
                        SELECT request_id FROM revision_plans
                        WHERE project_id=?
                        ORDER BY revision_number DESC LIMIT 1
                    )
                    """,
                    (now, project_id),
                )
            log(
                conn,
                "approval",
                "Chief of Staff",
                "Chief final review is complete and is waiting for human executive review.",
            )

        await hub.broadcast()

    except asyncio.CancelledError:
        with db() as conn:
            now = utc_now()
            in_progress = conn.execute(
                """
                SELECT id
                FROM tasks
                WHERE project_id=? AND status='In Progress'
                ORDER BY sequence,id
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            current_task_id = int(in_progress["id"]) if in_progress else None

            if current_task_id is not None:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status='Blocked',
                        result=CASE
                            WHEN result IS NULL OR TRIM(result)='' THEN ?
                            ELSE result
                        END,
                        updated_at=?
                    WHERE id=?
                    """,
                    (
                        "Recovery — the Campus stopped while this task was in progress. Retry / Resume Workflow to continue.",
                        now,
                        current_task_id,
                    ),
                )

            conn.execute(
                "UPDATE projects SET status='Execution Interrupted',updated_at=? WHERE id=?",
                (now, project_id),
            )
            set_workflow_run(
                conn,
                project_id,
                state="Interrupted",
                current_task_id=current_task_id,
                last_error="Campus process stopped while the workflow was running.",
            )
            reset_agents(conn)
            log(
                conn,
                "recovery",
                "System",
                "Campus stopped while a workflow was running. Completed work was preserved and explicit retry is required.",
            )
        await hub.broadcast()
        raise
    except Exception as exc:
        with db() as conn:
            now = utc_now()
            blocked = conn.execute(
                """
                SELECT id
                FROM tasks
                WHERE project_id=? AND status='Blocked'
                ORDER BY sequence,id
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            blocked_task_id = int(blocked["id"]) if blocked else None
            conn.execute(
                "UPDATE projects SET status='Execution Interrupted',updated_at=? WHERE id=?",
                (now, project_id),
            )
            set_workflow_run(
                conn,
                project_id,
                state="Interrupted",
                current_task_id=blocked_task_id,
                last_error=str(exc)[:1000],
            )
            reset_agents(conn)
            log(conn, "error", "System", f"Approved-plan execution stopped: {exc}")
        await hub.broadcast()


async def demo_workflow(project_id: int, task_ids: dict[str, int]) -> None:
    try:
        await set_agent("chief", status="Reviewing request", task_id=None)
        await add_log("workflow", "Chief of Staff", "Received the project at Mavis Manor and is deciding how to delegate it.")
        await pause(1.8)
        await set_task(task_ids["intake"], "Completed", "Project accepted and split into research, curriculum, and review work.")

        await set_agent("chief", building="barn", status="Walking to Coopenheimer Barn")
        await add_log("movement", "Chief of Staff", "Walking from Mavis Manor to Coopenheimer Barn to brief Programs.")
        await pause(3.2)
        await set_agent("chief", status="Delegating project to Programs")
        await add_log("delegation", "Chief of Staff", "Briefed Programs and delegated the research/curriculum sequence.")
        await pause(1.4)
        await set_agent("chief", building="manor", status="Returning to Mavis Manor")
        await add_log("movement", "Chief of Staff", "Returning to Mavis Manor while the specialist work proceeds.")

        await set_agent("programs", building="library", status="Walking to Library of Mavis")
        await add_log("movement", "Programs", "Walking from Coopenheimer Barn to the Library of Mavis to request preservation research.")
        await pause(3.4)
        await set_agent("programs", status="Briefing Research")
        await set_task(task_ids["research"], "In Progress")
        await set_agent("research", status="Researching preservation methods", task_id=task_ids["research"])
        await add_log("workflow", "Programs", "Asked Research for a verified packet on physical and digital document preservation.")
        await pause(1.3)
        await set_agent("programs", building="barn", status="Returning to Coopenheimer Barn")
        await pause(3.2)
        await set_agent("programs", status="Waiting for research packet")

        await add_log("workflow", "Research", "Working inside the Library of Mavis on physical and digital preservation practices.")
        await pause(2.6)
        research_result = (
            "Prototype research packet: organize originals, use archival-safe storage, create redundant digital copies, "
            "use clear file naming, keep one copy off-site, test backups, and teach a simple family document inventory."
        )
        await set_task(task_ids["research"], "Completed", research_result)
        await set_agent("research", building="barn", status="Carrying research packet to Coopenheimer Barn", task_id=None)
        await add_log("movement", "Research", "Research is complete and is being carried from the Library of Mavis to Programs.")
        await pause(3.4)
        await set_agent("research", status="Delivering research packet")
        await add_log("result", "Research", "Delivered the first research packet to Programs at Coopenheimer Barn.")

        await set_agent("programs", status="Building 45-minute class outline", task_id=task_ids["programs"])
        await set_task(task_ids["programs"], "In Progress")
        await add_log("workflow", "Programs", "Using the research packet to draft an all-ages 45-minute class.")
        await pause(2.8)
        program_result = (
            "Prototype class: 5 min why preservation matters; 10 min identify critical documents; "
            "10 min physical storage demo; 10 min digital backup/file naming; 5 min family inventory exercise; "
            "5 min questions and take-home challenge."
        )
        await set_task(task_ids["programs"], "Completed", program_result)
        await set_agent("research", building="library", status="Returning to Library of Mavis")
        await set_agent("programs", building="manor", status="Carrying class proposal to Mavis Manor", task_id=None)
        await add_log("movement", "Programs", "Walking the completed class proposal to Mavis Manor for executive review.")
        await pause(3.5)
        await set_agent("research", status="Available")
        await set_agent("programs", status="Delivering class proposal")
        await add_log("result", "Programs", "Delivered the draft class structure to the Chief of Staff at Mavis Manor.")

        await set_agent("chief", building="manor", status="Reviewing class proposal", task_id=task_ids["review"])
        await set_task(task_ids["review"], "In Progress")
        await pause(2.3)
        await set_task(task_ids["review"], "Completed", "Draft is coherent and ready for human review; no external action taken.")
        await set_agent("programs", building="barn", status="Returning to Coopenheimer Barn")
        await pause(3.1)
        await set_agent("programs", status="Available")
        with db() as conn:
            conn.execute(
                "INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (
                    project_id,
                    "Approve the Digital Preservation class concept",
                    "Research and Programs completed a first 45-minute outline. Approval authorizes the project to move into detailed curriculum development; it does not publish or send anything.",
                    "Pending",
                    utc_now(),
                    utc_now(),
                ),
            )
            conn.execute("UPDATE projects SET status='Awaiting Approval',updated_at=? WHERE id=?", (utc_now(), project_id))
            log(conn, "approval", "Chief of Staff", "Human approval requested. The workflow is paused here by design.")
        await set_agent("chief", status="Waiting for human approval", task_id=None)
        await hub.broadcast()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await add_log("error", "System", f"Workflow stopped: {exc}")


class ProjectRequest(BaseModel):
    title: str = "Develop a 45-minute all-ages class about preserving important documents digitally and physically."
    request_id: str = ""
    force_new: bool = False


class ApprovalDecision(BaseModel):
    decision: str
    note: str = ""


class NoteRequest(BaseModel):
    body: str
    author: str = "Human"


class MemoryRequest(BaseModel):
    project_id: int | None = None
    memory_type: str = "Context"
    title: str
    body: str
    tags: str = ""
    importance: str = "Normal"
    review_interval_days: int = 180
    created_by: str = "Human"
    source_kind: str = "manual"
    source_id: int | None = None


class MemoryEditRequest(BaseModel):
    project_id: int | None = None
    memory_type: str = "Context"
    title: str
    body: str
    tags: str = ""
    importance: str = "Normal"
    review_interval_days: int = 180


class MemoryCaptureRequest(BaseModel):
    source_kind: str
    source_id: int
    memory_type: str = "Context"
    importance: str = "Normal"
    review_interval_days: int = 180


class MemoryStatusRequest(BaseModel):
    status: str


class PlaybookRequest(BaseModel):
    project_id: int | None = None
    title: str
    purpose: str
    owner_agent_id: str | None = None
    trigger_text: str = ""
    steps: list[str] = []
    tags: str = ""
    status: str = "Draft"


class PlaybookStatusRequest(BaseModel):
    status: str


class LibraryCollectionRequest(BaseModel):
    title: str
    collection_type: str = "Program"
    subject: str = ""
    description: str = ""
    status: str = "Active"


class LibraryCollectionStatusRequest(BaseModel):
    status: str


class LibraryCatalogRequest(BaseModel):
    collection_id: int
    title: str
    material_type: str = "Document"
    edition_label: str = ""
    edition_date: str | None = None
    notes: str = ""


class ProgramsLibraryDecisionRequest(BaseModel):
    decision: str
    collection_id: int | None = None
    note: str = ""


class EnvironmentSettingsRequest(BaseModel):
    location_label: str = "Flat Top, West Virginia"
    timezone_name: str = "America/New_York"
    seasonal_region: str = "Southern Appalachia"
    latitude: float | None = 37.59
    longitude: float | None = -81.11
    pws_station_id: str = "KWFLATT11"
    live_weather_enabled: bool = True


class WeatherDayRequest(BaseModel):
    forecast_date: str
    high_f: float | None = None
    low_f: float | None = None
    precip_chance: int | None = None
    summary: str = ""


class SeasonalWindowRequest(BaseModel):
    name: str
    category: str = "Seasonal Window"
    start_md: str
    end_md: str
    priority: str = "Normal"
    notes: str = ""
    status: str = "Active"


class PhenologyObservationRequest(BaseModel):
    subject: str
    stage: str
    observation_date: str
    location_area: str
    source: str = "human observation"
    status: str = "observed"
    notes: str = ""


class PhenologyReviewRequest(BaseModel):
    status: str
    notes: str = ""

class PhenologyWatchlistRequest(BaseModel):
    subject: str; category: str; location_area: str; stages: list[str] = []; priority: str = "Normal"; notes: str = ""


class PersonRequest(BaseModel):
    display_name: str
    person_type: str = "Volunteer"
    status: str = "Active"
    contact_info: str = ""
    notes: str = ""
    is_primary_user: bool = False


class PoeCommandRequest(BaseModel):
    text: str


class VernadetteCommandRequest(BaseModel):
    text: str


class StellaDailyRequest(BaseModel):
    text: str = "What should I focus on today?"


class CampusAskRequest(BaseModel):
    text: str
    agent: str = "auto"
    previous_agent: str | None = None


class GrantDiscoveryRequest(BaseModel):
    keyword: str
    rows: int = 20


class GrantDiscoveryImportRequest(BaseModel):
    source_key: str
    opportunity_number: str = ""
    title: str
    funder: str
    deadline: str | None = None
    source_status: str = ""


class WorkClockInRequest(BaseModel):
    person_id: int
    project_id: int | None = None
    activity_category_id: int | None = None
    participation_type: str = "Volunteer"
    notes: str = ""


class WorkClockOutRequest(BaseModel):
    ended_at: str | None = None
    notes: str | None = None


class WorkSessionEditRequest(BaseModel):
    person_id: int | None = None
    project_id: int | None = None
    activity_category_id: int | None = None
    participation_type: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    work_date: str | None = None
    duration_minutes: int | None = None
    notes: str | None = None


class GrantRequest(BaseModel):
    funder: str
    title: str
    deadline: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    amount_notes: str = ""
    source_url: str = ""
    status: str = "Discovered"
    project_id: int | None = None
    notes: str = ""
    mission_fit: int = 3
    workload: int = 3
    restrictions: int = 3
    strategic_value: int = 3
    recommendation: str = "Review"
    assessment_notes: str = ""


class EventRequest(BaseModel):
    title: str
    event_date: str
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool = False
    location: str = ""
    event_type: str = "Institute"
    commitment_level: str = "Normal"
    project_id: int | None = None
    notes: str = ""
    status: str = "Scheduled"


class TaskStatusRequest(BaseModel):
    status: str


class AIBudgetRequest(BaseModel):
    daily_estimated_cost_limit_usd: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recovered = reconcile_interrupted_workflows()
    approval_repairs = repair_approval_invariants()
    with db() as conn:
        repository_count = rescan_repository(conn)

    with db() as conn:
        library_index_summary = refresh_library_index(conn)

    with db() as conn:
        health = system_health(conn)
        log(
            conn,
            "system",
            "Campus",
            (
                "Mavis Digital Campus v0.8.7.4.2 is online. "
                f"Schema {health['schema_version']} · "
                f"{len(recovered)} interrupted workflow(s) detected · "
                f"{approval_repairs['repaired']} approval gate(s) repaired · {repository_count} repository file(s) · {library_index_summary['indexed']} Library file(s) newly indexed."
            ),
        )

    yield

    global workflow_task
    if workflow_task and not workflow_task.done():
        workflow_task.cancel()
        try:
            await workflow_task
        except asyncio.CancelledError:
            pass



CAMPUS_AGENT_ALIASES = {
    "auto": "auto", "stella": "stella", "chief": "stella",
    "percy": "percy", "programs": "percy",
    "rose": "rose", "research": "rose",
    "stewart": "stewart", "caretaker": "stewart",
    "vernadette": "vernadette", "grants": "vernadette",
    "poe": "poe", "operations": "poe",
}
CAMPUS_AGENT_LABELS = {
    "stella": "Stella · Chief of Staff",
    "percy": "Percy · Director of Programs & Education",
    "rose": "Rose · Director of Research & Archives",
    "stewart": "Stewart · Land Steward",
    "vernadette": "Vernadette · Grants & Development Officer",
    "poe": "Poe · Operations & Volunteer Coordinator",
}
CAMPUS_AGENT_PROVIDER_ROLES = {"stella":"chief","percy":"programs","rose":"research","stewart":"caretaker"}


def _campus_clean_question(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:2500]


def _campus_weather_sensitive_work_intent(text: str) -> bool:
    q = text.casefold()
    timing = bool(re.search(r"\b(today|tomorrow|this (morning|afternoon|evening)|good day|best time|when should|when can|before (the )?rain|after (the )?rain)\b", q))
    outdoor_work = bool(re.search(r"\b(paint|painting|stain|staining|seal|sealing|roof|roofing|power ?wash|pressure ?wash|mow|mowing|hay|harvest|plant|planting|transplant|spray|outdoor work|outside work|garden work|yard work)\b", q))
    return timing and outdoor_work


def _campus_auto_route_detail(text: str, previous_agent: str | None = None) -> tuple[str, str, str]:
    q = text.casefold().strip()
    if any(token in q for token in ("what should i focus", "what should i do", "focus on today", "priorities today", "priority today", "plan my day", "today's priorities", "todays priorities", "needs my attention today")):
        return "stella", "Daily priorities and attention management belong with Stella.", "auto"
    if re.search(r"\b(clock|clocked|hours?|work session|volunteer hours?|timesheet|timekeeping)\b", q) or q.startswith("poe"):
        return "poe", "Work hours, volunteers, and day-to-day operations belong with Poe.", "auto"
    if re.search(r"\b(grant|grants|funding|funder|foundation|award|proposal deadline)\b", q) or q.startswith("vernadette"):
        return "vernadette", "Funding opportunities and grant tracking belong with Vernadette.", "auto"
    if _campus_weather_sensitive_work_intent(text):
        return "stewart", "This is outdoor work whose timing depends on weather, so Stewart should judge the conditions.", "auto"
    if re.search(r"\b(weather|forecast|rain|snow|temperature|temp|frost|moon|season|seasonal|plant|planting|garden|soil|pond|drainage|farm|animals?)\b", q) or q.startswith("stewart"):
        return "stewart", "Weather, land, plants, animals, and seasonal conditions belong with Stewart.", "auto"
    if re.search(r"\b(class|workshop|curriculum|lesson|teach|teaching|education|educational|program|course|handout|worksheet)\b", q) or q.startswith("percy"):
        return "percy", "Classes, curriculum, and educational programs belong with Percy.", "auto"
    if re.search(r"\b(research|history|historical|archive|source|evidence|verify|fact[- ]?check|what did we|library)\b", q) or q.startswith("rose"):
        return "rose", "Research, verification, archives, and institutional knowledge belong with Rose.", "auto"
    prev = CAMPUS_AGENT_ALIASES.get(str(previous_agent or "").strip().casefold())
    followup = bool(re.search(r"^(what about|how about|and what|and how|also|why|when|where|how|can you|could you|would you|is that|does that|what if)\b|\b(that|those|it|this)\b", q))
    if prev in {"stella", "percy", "rose", "stewart"} and followup and len(q.split()) <= 22:
        return prev, f"This looks like a follow-up, so I kept it with {CAMPUS_AGENT_LABELS[prev].split(' · ')[0]}.", "followup"
    return "stella", "No specialist lane was clearly stronger, so Stella is handling the general question.", "auto"


def _campus_auto_route(text: str) -> str:
    return _campus_auto_route_detail(text)[0]


def _campus_daily_intent(text: str) -> bool:
    q=text.casefold()
    return any(token in q for token in ("what should i focus", "what should i do", "focus on today", "priorities today", "priority today", "plan my day", "today's priorities", "todays priorities", "needs my attention today"))


def _campus_explicit_project_intent(text: str) -> bool:
    q=text.casefold()
    return bool(re.search(r"\b(create|start|make|build|turn|set up|setup)\b.{0,28}\b(project|initiative)\b|\b(project|initiative)\b.{0,28}\b(create|start|make|plan)\b", q))


def _campus_weather_intent(text: str) -> bool:
    q=text.casefold()
    return bool(re.search(r"\b(weather|forecast|rain|snow|temperature|temp|frost|moon|season|seasonal)\b", q))


def _campus_weather_answer(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    env=environment_summary(conn)
    q=text.casefold()
    moon=env.get("moon") or {}
    if "moon" in q:
        msg=(f"The moon is {moon.get('phase','unknown')} at about {moon.get('illumination_pct','?')}% illumination. "
             f"The next full moon is {moon.get('next_full_moon','not stored')} and the next new moon is {moon.get('next_new_moon','not stored')}.")
        return {"message":msg,"environment":env}
    local_date=str(env.get("local_date") or date.today().isoformat())
    target=local_date
    if "tomorrow" in q:
        try: target=(date.fromisoformat(local_date)+timedelta(days=1)).isoformat()
        except Exception: pass
    forecast=next((d for d in (env.get("forecast_days") or []) if str(d.get("forecast_date") or "")==target),None)
    current=env.get("current_conditions") or {}
    parts=[]
    if target==local_date and current:
        if current.get("temperature_f") is not None: parts.append(f"{round(float(current['temperature_f']))}°F now")
        if current.get("humidity_pct") is not None: parts.append(f"{round(float(current['humidity_pct']))}% humidity")
    if forecast:
        if forecast.get("high_f") is not None and forecast.get("low_f") is not None: parts.append(f"high {round(float(forecast['high_f']))}° / low {round(float(forecast['low_f']))}°")
        if forecast.get("precip_chance") is not None: parts.append(f"{round(float(forecast['precip_chance']))}% precipitation chance")
        if str(forecast.get("summary") or "").strip(): parts.append(str(forecast.get("summary")).strip())
    when="Tomorrow" if target!=local_date else "Today"
    msg=f"{when} at {env.get('location_label') or 'the Campus'}: " + (" · ".join(parts) if parts else "no detailed forecast is currently stored") + "."
    if env.get("pws_connection_status") not in {None,"Connected"}:
        msg += f" KWFLATT11: {env.get('pws_connection_status')}; regional forecast: {env.get('forecast_connection_status')}."
    return {"message":msg,"environment":env}


def _campus_advisor_prompt(agent: str, question: str, conn: sqlite3.Connection) -> str:
    base = {
        "stella": "You are Stella, Chief of Staff for the Mavis Digital Campus. Be warm, decisive, concise, mission-focused, protective of attention, and willing to disagree. You coordinate but do not pretend to have taken actions.",
        "percy": "You are Percy, Director of Programs & Education for the Mavis Institute. Be practical, grounded, warm, concise, and teacherly without jargon. Education should be useful, grounded, and alive.",
        "rose": "You are Rose, Director of Research & Archives for the Mavis Institute. Be curious, precise, patient, evidence-conscious, and comfortable saying when something is uncertain. Never fabricate sources or claim web research you did not perform.",
        "stewart": "You are Stewart, Land Steward for the Mavis Digital Campus. Be plainspoken, observant, practical, permaculture-grounded, and willing to recommend leaving something alone. Observe first, work with the system, intervene only as much as necessary.",
    }[agent]
    values=("Default to the Mavis realm: permaculture, Appalachian place-based knowledge, repair/reuse, resilience, stewardship, community, appropriate technology, practical low-input solutions, and long-term maintainability. "
            "Do not let this worldview override factual accuracy, safety, law, grant rules, or uncertainty.")
    limits=("This is a read-only advisory conversation. Do not create a project, modify records, send messages, spend money, schedule anything, submit anything, or claim an external action occurred. "
            "If the user is describing a substantial initiative, you may recommend turning it into a project, but do not create it. Answer the question directly in plain text, usually under 350 words.")
    context=[]
    memories=institutional_memory_for_prompt(conn, limit=6)
    if memories:
        context.append("Relevant institutional memory:\n"+"\n".join(f"- {m['title']}: {m['body'][:500]}" for m in memories))
    if agent in {"stella","stewart"}:
        env=environment_summary(conn); weather=_daily_steward_forecast_context(env)
        context.append(f"Campus local date: {env.get('local_date')}; season: {env.get('season')}; stored weather: {weather.get('summary')}. Weather planning notes: {'; '.join(weather.get('notes') or []) or 'none' }.")
        if agent=="stewart":
            current=env.get("current_conditions") or {}
            forecast=list(env.get("forecast_days") or [])[:2]
            context.append(
                "Current and near-term weather detail for practical outdoor-work judgment: "
                f"current temperature={current.get('temperature_f')}F, humidity={current.get('humidity_pct')}%, wind={current.get('wind_mph')} mph, source={current.get('source') or current.get('source_kind')}; "
                + "; ".join(
                    f"{d.get('forecast_date')}: high={d.get('high_f')}F, low={d.get('low_f')}F, precip={d.get('precip_chance')}%, rain={d.get('rain_total_in')} in, wind max={d.get('wind_max_mph')} mph, summary={d.get('summary')}"
                    for d in forecast
                )
            )
    if agent=="stella":
        d=daily_steward(conn); context.append("Today focus currently generated by Daily Steward: "+"; ".join(str(x.get('title') or '') for x in (d.get('focus') or [])[:3]))
    if agent=="percy":
        cal=calendar_summary(conn); upcoming=[x for x in cal.get('upcoming',[]) if x.get('event_type') in {'Class / Program','Institute'}][:5]
        if upcoming: context.append("Upcoming program/calendar context: "+"; ".join(f"{x.get('event_date')} {x.get('title')}" for x in upcoming))
    return f"{base}\n\n{values}\n\n{limits}\n\n" + ("\n\n".join(context)+"\n\n" if context else "") + f"User question: {question}\n\nRespond as {CAMPUS_AGENT_LABELS[agent].split(' · ')[0]}."


async def _campus_ai_advice(agent: str, question: str) -> dict[str, Any]:
    provider_role=CAMPUS_AGENT_PROVIDER_ROLES[agent]
    provider_id=role_provider_id(provider_role)
    status=provider_public_status(provider_id)
    if not status.get("configured"):
        raise HTTPException(status_code=400, detail=f"{status.get('provider')} is assigned to {CAMPUS_AGENT_LABELS[agent].split(' · ')[0]} but its API key is not configured in .env.")
    try: require_ai_allowed(f"campus_advice_{agent}", provider_id)
    except RuntimeError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    with db() as conn: prompt=_campus_advisor_prompt(agent, question, conn)
    started=time.perf_counter()
    try:
        provider=get_role_provider(provider_role)
        result=await asyncio.to_thread(provider.generate_text, prompt, max_output_tokens=700)
    except Exception as exc:
        latency_ms=int((time.perf_counter()-started)*1000)
        with db() as conn:
            conn.execute("INSERT INTO ai_calls(provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(provider_id,str(status.get('model','')),f"campus_advice_{agent}","Failed",latency_ms,len(prompt),0,str(exc)[:500],utc_now()))
            log(conn,"ai_error",CAMPUS_AGENT_LABELS[agent].split(' · ')[0],f"Read-only Campus advice failed: {str(exc)[:240]}")
        await hub.broadcast()
        raise HTTPException(status_code=502,detail=str(exc)[:500]) from exc
    latency_ms=int((time.perf_counter()-started)*1000)
    message=str(result.text or '').strip()
    with db() as conn:
        conn.execute("INSERT INTO ai_calls(provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(result.provider,result.model,f"campus_advice_{agent}","Success",latency_ms,result.input_chars,result.output_chars,f"Read-only advice answered by {CAMPUS_AGENT_LABELS[agent].split(' · ')[0]}; no project or external action created.",utc_now()))
        log(conn,"ai",CAMPUS_AGENT_LABELS[agent].split(' · ')[0],"Answered a read-only Ask the Campus question.")
    await hub.broadcast()
    return {"status":"ok","mode":"ai_advice","handled_by":CAMPUS_AGENT_LABELS[agent],"agent":agent,"message":message,"model":result.model,"provider":result.provider,"project_created":False,"additional_ai_calls":1}


app = FastAPI(title="Mavis Digital Campus", version=SCHEMA_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    return current_state()



@app.post("/api/campus/ask")
async def api_campus_ask(req: CampusAskRequest) -> dict[str, Any]:
    text=_campus_clean_question(req.text)
    if not text: raise HTTPException(status_code=400,detail="Ask the Campus a question or request first.")
    selected=CAMPUS_AGENT_ALIASES.get(str(req.agent or "auto").strip().casefold())
    if selected is None: raise HTTPException(status_code=400,detail="Choose Auto, Stella, Percy, Rose, Stewart, Vernadette, or Poe.")
    if selected == "auto":
        routed, route_reason, route_source = _campus_auto_route_detail(text, req.previous_agent)
    else:
        routed, route_reason, route_source = selected, f"You chose {CAMPUS_AGENT_LABELS[selected].split(' · ')[0]} directly.", "selected"

    if _campus_explicit_project_intent(text):
        return {"status":"project_suggestion","mode":"routing","handled_by":"Stella · Chief of Staff","agent":"stella","message":"This sounds like a real project or initiative. I have not created anything yet. If you want, Stella can turn this exact request into a proposed project plan for your approval.","suggest_project":True,"original_text":text,"project_created":False,"additional_ai_calls":0,"route_reason":"Projects are coordinated through Stella before they enter the approval workflow.","route_source":"project_guard"}

    if routed=="stella" and _campus_daily_intent(text):
        with db() as conn: steward=daily_steward(conn)
        return {"status":"ok","mode":"deterministic","handled_by":CAMPUS_AGENT_LABELS['stella'],"agent":"stella","message":"I checked the Campus lanes and kept today to the smallest useful set of priorities.","daily_steward":steward,"open_panel":"briefing","open_label":"Daily Steward","project_created":False,"additional_ai_calls":0,"route_reason":route_reason,"route_source":route_source}

    if routed=="stewart" and _campus_weather_intent(text):
        with db() as conn: answer=_campus_weather_answer(conn,text)
        return {"status":"ok","mode":"deterministic","handled_by":CAMPUS_AGENT_LABELS['stewart'],"agent":"stewart","message":answer['message'],"open_panel":"environment","open_label":"Weather & Seasons","project_created":False,"additional_ai_calls":0,"route_reason":route_reason,"route_source":route_source}

    if routed=="poe":
        result=await api_poe_command(PoeCommandRequest(text=text))
        return {"status":result.get('status','ok'),"mode":"deterministic","handled_by":CAMPUS_AGENT_LABELS['poe'],"agent":"poe","message":result.get('message','Poe handled the request.'),"poe_result":result,"open_panel":"people" if result.get('report_filters') else None,"open_label":"People & Work","project_created":False,"additional_ai_calls":0,"route_reason":route_reason,"route_source":route_source}

    if routed=="vernadette":
        result=await api_vernadette_command(VernadetteCommandRequest(text=text))
        return {"status":result.get('status','ok'),"mode":"deterministic","handled_by":CAMPUS_AGENT_LABELS['vernadette'],"agent":"vernadette","message":result.get('message','Vernadette checked the Grant Desk.'),"vernadette_result":result,"open_panel":"grants","open_label":"Grant Desk","project_created":False,"additional_ai_calls":0,"route_reason":route_reason,"route_source":route_source}

    # Stella, Percy, Rose, and Stewart can answer ordinary read-only advice questions
    # through their configured AI role without turning the question into a project.
    result = await _campus_ai_advice(routed,text)
    result["route_reason"] = route_reason
    result["route_source"] = route_source
    return result


@app.post("/api/vernadette/command")
async def api_vernadette_command(req: VernadetteCommandRequest) -> dict[str, Any]:
    command = _vernadette_clean_command(req.text)
    if not command:
        raise HTTPException(status_code=400, detail="Tell Vernadette what you want her to do.")
    with db() as conn:
        kind = _vernadette_command_kind(command)
        if kind == "discover":
            keyword = _vernadette_discovery_keyword(command)
            if not keyword:
                return {"status":"clarification","action":"discover","message":"Tell me what kind of funding to search for — for example: ‘Vernadette, find grants for rural community education.’","discovery_results":[],"open_grant_desk":True}
            try:
                found = await asyncio.to_thread(search_grants_gov, keyword, 20)
            except GrantDiscoveryError as exc:
                return {"status":"clarification","action":"discover","message":str(exc),"provider":"Grants.gov","query":keyword,"discovery_results":[],"open_grant_desk":True}
            results = [_annotate_discovery_imported(conn, item) for item in found.get("results", [])]
            fresh = sum(1 for item in results if not item.get("already_in_desk"))
            return {"status":"ok","action":"discover","message":f"Grants.gov found {found.get('hit_count', len(results))} matching federal opportunity record(s). I brought back {len(results)} for review; {fresh} are not already in the Grant Desk.","provider":found.get("provider","Grants.gov"),"query":found.get("query",keyword),"hit_count":found.get("hit_count",len(results)),"discovery_results":results,"grants":[],"open_grant_desk":True}
        if kind == "add":
            return _vernadette_command_add(conn, command)
        if kind == "update":
            return _vernadette_command_update(conn, command)
        return _vernadette_command_report(conn, command)


@app.post("/api/grants/discover")
async def api_grant_discover(req: GrantDiscoveryRequest) -> dict[str, Any]:
    keyword = " ".join(str(req.keyword or "").split()).strip()[:180]
    if not keyword:
        raise HTTPException(status_code=400, detail="Add a grant search phrase first.")
    rows_requested = max(1, min(int(req.rows or 20), 40))
    try:
        found = await asyncio.to_thread(search_grants_gov, keyword, rows_requested)
    except GrantDiscoveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db() as conn:
        results = [_annotate_discovery_imported(conn, item) for item in found.get("results", [])]
    return {**found, "results": results}


@app.post("/api/grants/import-discovery")
async def api_grant_import_discovery(req: GrantDiscoveryImportRequest) -> dict[str, Any]:
    source_key = " ".join(str(req.source_key or "").split()).strip()[:80]
    title = " ".join(str(req.title or "").split()).strip()[:260]
    funder = " ".join(str(req.funder or "").split()).strip()[:220]
    opportunity_number = " ".join(str(req.opportunity_number or "").split()).strip()[:180]
    source_status = " ".join(str(req.source_status or "").split()).strip()[:80]
    if not source_key or not title or not funder:
        raise HTTPException(status_code=400, detail="The Grants.gov opportunity is missing its source ID, title, or agency.")
    deadline = str(req.deadline or "").strip() or None
    if deadline:
        try:
            date.fromisoformat(deadline)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Discovery deadline must be YYYY-MM-DD.") from exc
    source_url = f"https://www.grants.gov/search-results-detail/{source_key}"
    now = utc_now()
    with db() as conn:
        existing = conn.execute("SELECT id,status FROM grants WHERE source_name='Grants.gov' AND source_key=? LIMIT 1", (source_key,)).fetchone()
        if existing:
            return {"grant_id": int(existing["id"]), "status": "already_exists", "desk_status": existing["status"]}
        notes = f"Imported from Grants.gov discovery. Opportunity number: {opportunity_number or 'not listed'}. Source status: {source_status or 'not listed'}. Verify full eligibility, award details, match, and reporting requirements before deciding to pursue."
        cur = conn.execute(
            """
            INSERT INTO grants(funder,title,deadline,amount_min,amount_max,amount_notes,source_url,source_name,source_key,opportunity_number,source_status,status,project_id,notes,mission_fit,workload,restrictions,strategic_value,recommendation,assessment_notes,created_by,created_at,updated_at)
            VALUES(?,?,?,NULL,NULL,'Open the Grants.gov source for full award amount and match details.',?,'Grants.gov',?,?,?, 'Discovered',NULL,?,3,3,3,3,'Review','Federal discovery import; Vernadette has not completed fit scoring yet.','Vernadette · Grants.gov discovery',?,?)
            """,
            (funder,title,deadline,source_url,source_key,opportunity_number,source_status,notes,now,now),
        )
        grant_id = int(cur.lastrowid)
        log(conn, "grant", "Vernadette", f"Imported federal grant discovery: {title} · {funder} · {opportunity_number or source_key}.")
    await hub.broadcast()
    return {"grant_id": grant_id, "status": "created"}


@app.post("/api/grants")
async def api_grant_create(req: GrantRequest) -> dict[str, Any]:
    with db() as conn:
        data = _clean_grant_request(req, conn)
        now = utc_now()
        cur = conn.execute(
            """
            INSERT INTO grants(funder,title,deadline,amount_min,amount_max,amount_notes,source_url,status,project_id,notes,mission_fit,workload,restrictions,strategic_value,recommendation,assessment_notes,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'Vernadette',?,?)
            """,
            (data["funder"],data["title"],data["deadline"],data["amount_min"],data["amount_max"],data["amount_notes"],data["source_url"],data["status"],data["project_id"],data["notes"],data["mission_fit"],data["workload"],data["restrictions"],data["strategic_value"],data["recommendation"],data["assessment_notes"],now,now),
        )
        grant_id = int(cur.lastrowid)
        log(conn, "grant", "Vernadette", f"Added grant opportunity: {data['title']} · {data['funder']}.")
    await hub.broadcast()
    return {"grant_id": grant_id, "status": "created"}


@app.post("/api/grants/{grant_id}")
async def api_grant_edit(grant_id: int, req: GrantRequest) -> dict[str, Any]:
    with db() as conn:
        existing = conn.execute("SELECT id FROM grants WHERE id=?", (int(grant_id),)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Grant opportunity not found.")
        data = _clean_grant_request(req, conn)
        now = utc_now()
        conn.execute(
            """
            UPDATE grants SET funder=?,title=?,deadline=?,amount_min=?,amount_max=?,amount_notes=?,source_url=?,status=?,project_id=?,notes=?,mission_fit=?,workload=?,restrictions=?,strategic_value=?,recommendation=?,assessment_notes=?,updated_at=?
            WHERE id=?
            """,
            (data["funder"],data["title"],data["deadline"],data["amount_min"],data["amount_max"],data["amount_notes"],data["source_url"],data["status"],data["project_id"],data["notes"],data["mission_fit"],data["workload"],data["restrictions"],data["strategic_value"],data["recommendation"],data["assessment_notes"],now,int(grant_id)),
        )
        log(conn, "grant", "Vernadette", f"Updated grant opportunity: {data['title']} · {data['status']}.")
    await hub.broadcast()
    return {"grant_id": int(grant_id), "status": "updated"}



def _clean_event_request(req: EventRequest, conn: sqlite3.Connection) -> dict[str, Any]:
    title = " ".join(str(req.title or "").split()).strip()[:220]
    if not title:
        raise HTTPException(status_code=400, detail="Event title is required.")
    event_date = str(req.event_date or "").strip()
    try:
        date.fromisoformat(event_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Event date must be YYYY-MM-DD.") from exc
    all_day = bool(req.all_day)

    def clean_time(value: str | None, label: str) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{label} must be HH:MM.") from exc
        return raw

    start_time = None if all_day else clean_time(req.start_time, "Start time")
    end_time = None if all_day else clean_time(req.end_time, "End time")
    if start_time and end_time and end_time <= start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time for this same-day Calendar event.")
    event_type = str(req.event_type or "Institute").strip()
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Choose a valid event type.")
    commitment_level = str(req.commitment_level or "Normal").strip().title()
    if commitment_level not in EVENT_COMMITMENT_LEVELS:
        raise HTTPException(status_code=400, detail="Commitment level must be Light, Normal, or Major.")
    status = str(req.status or "Scheduled").strip().title()
    if status not in EVENT_STATUSES:
        raise HTTPException(status_code=400, detail="Event status must be Scheduled or Cancelled.")
    project_id = int(req.project_id) if req.project_id is not None else None
    if project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
        raise HTTPException(status_code=400, detail="Linked project was not found.")
    return {
        "title": title,
        "event_date": event_date,
        "start_time": start_time,
        "end_time": end_time,
        "all_day": 1 if all_day else 0,
        "location": " ".join(str(req.location or "").split()).strip()[:300],
        "event_type": event_type,
        "commitment_level": commitment_level,
        "project_id": project_id,
        "notes": str(req.notes or "").strip()[:4000],
        "status": status,
    }


@app.post("/api/events")
async def api_event_create(req: EventRequest) -> dict[str, Any]:
    with db() as conn:
        data = _clean_event_request(req, conn)
        now = utc_now()
        cur = conn.execute(
            """
            INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'Human',?,?)
            """,
            (data["title"],data["event_date"],data["start_time"],data["end_time"],data["all_day"],data["location"],data["event_type"],data["commitment_level"],data["project_id"],data["notes"],data["status"],now,now),
        )
        event_id = int(cur.lastrowid)
        log(conn, "calendar", "Human", f"Added calendar event: {data['title']} · {data['event_date']}.")
    await hub.broadcast()
    return {"event_id": event_id, "status": "created"}


@app.post("/api/events/{event_id}")
async def api_event_edit(event_id: int, req: EventRequest) -> dict[str, Any]:
    with db() as conn:
        if not conn.execute("SELECT id FROM events WHERE id=?", (int(event_id),)).fetchone():
            raise HTTPException(status_code=404, detail="Calendar event not found.")
        data = _clean_event_request(req, conn)
        now = utc_now()
        conn.execute(
            """
            UPDATE events SET title=?,event_date=?,start_time=?,end_time=?,all_day=?,location=?,event_type=?,commitment_level=?,project_id=?,notes=?,status=?,updated_at=?
            WHERE id=?
            """,
            (data["title"],data["event_date"],data["start_time"],data["end_time"],data["all_day"],data["location"],data["event_type"],data["commitment_level"],data["project_id"],data["notes"],data["status"],now,int(event_id)),
        )
        log(conn, "calendar", "Human", f"Updated calendar event: {data['title']} · {data['event_date']} · {data['status']}.")
    await hub.broadcast()
    return {"event_id": int(event_id), "status": "updated"}


@app.get("/api/work-report")
async def api_work_report(
    person_id: int | None = None,
    activity_category_id: int | None = None,
    project_id: int | None = None,
    participation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    with db() as conn:
        return work_report_data(
            conn,
            person_id=person_id,
            activity_category_id=activity_category_id,
            project_id=project_id,
            participation_type=participation_type,
            start_date=start_date,
            end_date=end_date,
        )


@app.get("/api/work-report.csv")
async def api_work_report_csv(
    person_id: int | None = None,
    activity_category_id: int | None = None,
    project_id: int | None = None,
    participation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Response:
    with db() as conn:
        report = work_report_data(
            conn,
            person_id=person_id,
            activity_category_id=activity_category_id,
            project_id=project_id,
            participation_type=participation_type,
            start_date=start_date,
            end_date=end_date,
        )
    csv_text = _work_report_csv(report)
    start_label = report["filters"].get("start_date") or "all"
    end_label = report["filters"].get("end_date") or "time"
    filename = f"mavis-work-hours-{start_label}-to-{end_label}.csv"
    return Response(
        content="\ufeff" + csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@app.post("/api/people")
async def api_person_create(req: PersonRequest) -> dict[str, Any]:
    name = " ".join(str(req.display_name or "").split()).strip()
    if not name:
        raise HTTPException(status_code=400, detail="A person name is required.")
    person_type = " ".join(str(req.person_type or "Volunteer").split()).strip()[:80] or "Volunteer"
    status = "Active" if str(req.status or "Active").strip().lower() != "inactive" else "Inactive"
    now = utc_now()
    with db() as conn:
        if bool(req.is_primary_user):
            conn.execute("UPDATE people SET is_primary_user=0")
        cur = conn.execute(
            """
            INSERT INTO people(display_name,person_type,status,contact_info,notes,is_primary_user,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (name, person_type, status, str(req.contact_info or "")[:1200], str(req.notes or "")[:4000], 1 if req.is_primary_user else 0, now, now),
        )
        person_id = int(cur.lastrowid)
        log(conn, "people", "Poe", f"Added {name} to the Campus people ledger as {person_type}.")
    await hub.broadcast()
    return {"person_id": person_id, "status": "created"}


@app.post("/api/people/{person_id}/primary")
async def api_person_set_primary(person_id: int) -> dict[str, Any]:
    with db() as conn:
        person = conn.execute("SELECT * FROM people WHERE id=?", (int(person_id),)).fetchone()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found.")
        conn.execute("UPDATE people SET is_primary_user=0,updated_at=? WHERE is_primary_user=1", (utc_now(),))
        conn.execute("UPDATE people SET is_primary_user=1,updated_at=? WHERE id=?", (utc_now(), int(person_id)))
        log(conn, "people", "Poe", f"Set {person['display_name']} as the primary ‘me’ record for conversational timekeeping.")
    await hub.broadcast()
    return {"person_id": int(person_id), "status": "primary"}


@app.post("/api/poe/command")
async def api_poe_command(req: PoeCommandRequest) -> dict[str, Any]:
    command = _poe_clean_command(req.text)
    if not command:
        raise HTTPException(status_code=400, detail="Tell Poe what you want to do.")
    kind = _poe_command_kind(command)

    if kind == "report":
        with db() as conn:
            return _poe_command_report(conn, command)

    if kind == "clock_in":
        with db() as conn:
            person, error = _poe_resolve_person(conn, command)
            if error or not person:
                return {"status": "clarification", "intent": kind, "message": error or "Who should I clock in?"}
            activity = _poe_resolve_activity(conn, command)
            if not activity:
                return {
                    "status": "clarification", "intent": kind,
                    "message": "What kind of work is this? Try something like farm work, education, admin, research, animal care, maintenance, grants, outreach, media, planning, learning, or volunteer coordination.",
                }
            project = _poe_resolve_project(conn, command)
            participation = _poe_participation(command)
            person_id = int(person["id"])
            person_name = str(person["display_name"])
            activity_id = int(activity["id"])
            activity_name = str(activity["name"])
            project_id = int(project["id"]) if project else None
            project_title = str(project["title"]) if project else ""
        result = await api_work_clock_in(WorkClockInRequest(
            person_id=person_id,
            project_id=project_id,
            activity_category_id=activity_id,
            participation_type=participation,
            notes="",
        ))
        project_phrase = f" on {project_title}" if project_title else ""
        return {
            **result,
            "status": "ok", "intent": kind,
            "message": f"Clocked {person_name} in for {participation.lower()} · {activity_name}{project_phrase}.",
        }

    if kind == "clock_out":
        with db() as conn:
            person, error = _poe_resolve_person(conn, command)
            if error or not person:
                return {"status": "clarification", "intent": kind, "message": error or "Who should I clock out?"}
            session = conn.execute(
                "SELECT id,started_at FROM work_sessions WHERE person_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
                (int(person["id"]),),
            ).fetchone()
            if not session:
                return {"status": "clarification", "intent": kind, "message": f"{person['display_name']} is not currently clocked in."}
            session_id = int(session["id"])
            person_name = str(person["display_name"])
        result = await api_work_clock_out(session_id, WorkClockOutRequest())
        return {
            **result,
            "status": "ok", "intent": kind,
            "message": f"Clocked {person_name} out · {_poe_duration_label(int(result['duration_minutes']))} recorded.",
        }

    if kind == "manual_duration":
        with db() as conn:
            person, error = _poe_resolve_person(conn, command)
            if error or not person:
                return {"status": "clarification", "intent": kind, "message": error or "Whose hours should I record?"}
            activity = _poe_resolve_activity(conn, command)
            if not activity:
                return {
                    "status": "clarification", "intent": kind,
                    "message": "I found the duration, but I still need the work category before I save it.",
                }
            duration = _poe_duration_minutes(command)
            if not duration:
                return {"status": "clarification", "intent": kind, "message": "How much time should I record?"}
            today = _poe_local_today(conn)
            work_day = _poe_single_work_date(command, today)
            if work_day > today:
                return {"status": "clarification", "intent": kind, "message": "I won't record completed hours in the future. Give me the day the work actually happened."}
            project = _poe_resolve_project(conn, command)
            participation = _poe_participation(command)
            session_id = _poe_manual_session(
                conn,
                person_id=int(person["id"]),
                activity_category_id=int(activity["id"]),
                participation_type=participation,
                work_day=work_day,
                duration_minutes=duration,
                project_id=int(project["id"]) if project else None,
                notes=f"Remembered via Poe: {command}"[:4000],
            )
            person_name = str(person["display_name"])
            activity_name = str(activity["name"])
            project_title = str(project["title"]) if project else ""
            log(conn, "work", "Poe", f"Recorded {_poe_duration_label(duration)} of remembered work for {person_name} on {work_day.isoformat()}.")
        await hub.broadcast()
        project_phrase = f" · {project_title}" if project_title else ""
        return {
            "status": "ok", "intent": kind, "session_id": session_id,
            "message": f"Recorded {_poe_duration_label(duration)} for {person_name} on {work_day.strftime('%b %d, %Y').replace(' 0', ' ')} · {participation} · {activity_name}{project_phrase}. Exact clock times were not invented; this is stored as a date-only remembered-duration entry.",
        }

    return {
        "status": "clarification",
        "intent": "unknown",
        "message": "I can handle work-hour commands right now. Try: ‘Clock me in for farm work,’ ‘Clock Lisa out,’ ‘Add 2 hours yesterday for Sam doing maintenance,’ or ‘Show me our education hours this month.’",
    }


@app.post("/api/work-sessions/clock-in")
async def api_work_clock_in(req: WorkClockInRequest) -> dict[str, Any]:
    participation = " ".join(str(req.participation_type or "Volunteer").split()).strip()[:80] or "Volunteer"
    now = utc_now()
    with db() as conn:
        person = conn.execute("SELECT * FROM people WHERE id=?", (int(req.person_id),)).fetchone()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found.")
        open_row = conn.execute("SELECT id FROM work_sessions WHERE person_id=? AND ended_at IS NULL", (int(req.person_id),)).fetchone()
        if open_row:
            raise HTTPException(status_code=409, detail=f"{person['display_name']} is already clocked in.")
        if req.project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (int(req.project_id),)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found.")
        if req.activity_category_id is not None and not conn.execute("SELECT id FROM activity_categories WHERE id=? AND active=1", (int(req.activity_category_id),)).fetchone():
            raise HTTPException(status_code=404, detail="Activity category not found.")
        cur = conn.execute(
            """
            INSERT INTO work_sessions(person_id,project_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,NULL,NULL,?,'Poe',?,?)
            """,
            (int(req.person_id), req.project_id, req.activity_category_id, participation, now, str(req.notes or "")[:4000], now, now),
        )
        session_id = int(cur.lastrowid)
        _audit_work_session(conn, session_id, "clock_in", "Poe")
        log(conn, "work", "Poe", f"Clocked {person['display_name']} in for {participation.lower()} work.")
    await hub.broadcast()
    return {"session_id": session_id, "status": "clocked_in", "started_at": now}


@app.post("/api/work-sessions/{session_id}/clock-out")
async def api_work_clock_out(session_id: int, req: WorkClockOutRequest) -> dict[str, Any]:
    with db() as conn:
        session = conn.execute(
            "SELECT ws.*,p.display_name AS person_name FROM work_sessions ws JOIN people p ON p.id=ws.person_id WHERE ws.id=?",
            (int(session_id),),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Work session not found.")
        if session["ended_at"]:
            raise HTTPException(status_code=409, detail="This work session is already clocked out.")
        ended_at = str(req.ended_at or utc_now())
        try:
            duration = _session_duration_minutes(str(session["started_at"]), ended_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        notes = str(session["notes"] or "") if req.notes is None else str(req.notes or "")[:4000]
        now = utc_now()
        conn.execute(
            "UPDATE work_sessions SET ended_at=?,duration_minutes=?,notes=?,updated_at=? WHERE id=?",
            (ended_at, duration, notes, now, int(session_id)),
        )
        _audit_work_session(conn, session_id, "clock_out", "Poe")
        log(conn, "work", "Poe", f"Clocked {session['person_name']} out after {duration} minute(s).")
    await hub.broadcast()
    return {"session_id": int(session_id), "status": "clocked_out", "ended_at": ended_at, "duration_minutes": duration}


@app.post("/api/work-sessions/{session_id}")
async def api_work_session_edit(session_id: int, req: WorkSessionEditRequest) -> dict[str, Any]:
    with db() as conn:
        current = conn.execute("SELECT * FROM work_sessions WHERE id=?", (int(session_id),)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Work session not found.")
        values = dict(current)
        for field in ("person_id", "project_id", "activity_category_id", "participation_type", "started_at", "ended_at", "work_date", "duration_minutes", "notes"):
            incoming = getattr(req, field)
            if incoming is not None:
                values[field] = incoming
        if not conn.execute("SELECT id FROM people WHERE id=?", (int(values["person_id"]),)).fetchone():
            raise HTTPException(status_code=404, detail="Person not found.")
        if values["project_id"] is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (int(values["project_id"]),)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found.")
        if values["activity_category_id"] is not None and not conn.execute("SELECT id FROM activity_categories WHERE id=?", (int(values["activity_category_id"]),)).fetchone():
            raise HTTPException(status_code=404, detail="Activity category not found.")

        if str(current["entry_mode"] or "clock") == "manual_duration":
            try:
                work_day = date.fromisoformat(str(values.get("work_date") or ""))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="work_date must be YYYY-MM-DD for remembered-duration entries.") from exc
            duration = int(values.get("duration_minutes") or 0)
            if duration <= 0:
                raise HTTPException(status_code=400, detail="duration_minutes must be greater than zero for remembered-duration entries.")
            _, tz = _work_report_timezone(conn)
            local_start = datetime.combine(work_day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
            local_end = local_start + timedelta(minutes=duration)
            values["started_at"] = local_start.astimezone(timezone.utc).isoformat(timespec="seconds")
            values["ended_at"] = local_end.astimezone(timezone.utc).isoformat(timespec="seconds")
            values["work_date"] = work_day.isoformat()
        else:
            duration = None
            if values["ended_at"]:
                try:
                    duration = _session_duration_minutes(str(values["started_at"]), str(values["ended_at"]))
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        now = utc_now()
        try:
            conn.execute(
                """
                UPDATE work_sessions
                SET person_id=?,project_id=?,activity_category_id=?,participation_type=?,started_at=?,ended_at=?,duration_minutes=?,work_date=?,notes=?,updated_at=?
                WHERE id=?
                """,
                (int(values["person_id"]), values["project_id"], values["activity_category_id"], str(values["participation_type"] or "Volunteer")[:80], str(values["started_at"]), values["ended_at"], duration, values.get("work_date"), str(values["notes"] or "")[:4000], now, int(session_id)),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="That person already has another open work session.") from exc
        _audit_work_session(conn, session_id, "edit", "Poe")
        log(conn, "work", "Poe", f"Corrected work session #{int(session_id)}. The audit trail was preserved.")
    await hub.broadcast()
    return {"session_id": int(session_id), "status": "updated", "duration_minutes": duration}


@app.get("/api/environment")
async def api_environment() -> dict[str, Any]:
    with db() as conn:
        return environment_summary(conn)


@app.post("/api/environment/settings")
async def api_environment_settings(req: EnvironmentSettingsRequest) -> dict[str, Any]:
    label = " ".join(req.location_label.split()).strip()[:180]
    region = " ".join(req.seasonal_region.split()).strip()[:180]
    tz_name = req.timezone_name.strip()[:80]
    if not label:
        raise HTTPException(status_code=400, detail="Location label is required.")
    try:
        ZoneInfo(tz_name)
    except Exception:
        raise HTTPException(status_code=400, detail="Use a valid IANA timezone such as America/New_York.")
    if req.latitude is not None and not (-90 <= req.latitude <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90.")
    if req.longitude is not None and not (-180 <= req.longitude <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180.")
    with db() as conn:
        station_id = re.sub(r"[^A-Za-z0-9_-]", "", req.pws_station_id.strip().upper())[:40] or "KWFLATT11"
        conn.execute("""UPDATE environment_settings SET location_label=?,timezone_name=?,seasonal_region=?,latitude=?,longitude=?,pws_station_id=?,live_weather_enabled=?,updated_at=? WHERE id=1""",
                     (label,tz_name,region,req.latitude,req.longitude,station_id,1 if req.live_weather_enabled else 0,utc_now()))
        log(conn,"environment","Human",f"Updated Weather & Seasons location context: {label}.")
        result = environment_summary(conn)
    await hub.broadcast()
    return result


@app.post("/api/environment/refresh")
async def api_environment_refresh() -> dict[str, Any]:
    with db() as conn:
        settings_row = conn.execute("SELECT * FROM environment_settings WHERE id=1").fetchone()
        settings = dict(settings_row) if settings_row else {}
    if not bool(settings.get("live_weather_enabled", 1)):
        raise HTTPException(status_code=409, detail="Live weather is disabled in Weather settings.")
    try:
        result = await asyncio.to_thread(refresh_weather_provider, settings)
    except Exception as exc:
        with db() as conn:
            now = utc_now()
            conn.execute("UPDATE environment_settings SET last_refresh_at=?,last_refresh_status='Failed',last_refresh_error=?,updated_at=? WHERE id=1", (now,str(exc)[:1000],now))
            log(conn,"environment","Weather",f"Weather refresh failed: {str(exc)[:300]}")
        await hub.broadcast()
        raise HTTPException(status_code=502, detail=f"Weather refresh failed: {exc}")
    with db() as conn:
        _store_weather_refresh(conn, result)
        source = "KWFLATT11" if result.get("pws_connected") else "Open-Meteo fallback"
        log(conn,"environment","Weather",f"Weather refreshed from {source}; forecast from Open-Meteo. No AI call was used.")
        summary = environment_summary(conn)
    await hub.broadcast()
    return summary


@app.post("/api/environment/weather/day")
async def api_environment_weather_day(req: WeatherDayRequest) -> dict[str, Any]:
    try:
        parsed = datetime.strptime(req.forecast_date.strip(), "%Y-%m-%d").date().isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="Forecast date must use YYYY-MM-DD.")
    precip = req.precip_chance
    if precip is not None and not (0 <= precip <= 100):
        raise HTTPException(status_code=400, detail="Precipitation chance must be 0–100.")
    with db() as conn:
        conn.execute("""INSERT INTO weather_daily(forecast_date,high_f,low_f,precip_chance,summary,source,observed_at,updated_at)
                        VALUES(?,?,?,?,?,'manual',?,?)
                        ON CONFLICT(forecast_date) DO UPDATE SET high_f=excluded.high_f,low_f=excluded.low_f,precip_chance=excluded.precip_chance,summary=excluded.summary,source='manual',observed_at=excluded.observed_at,updated_at=excluded.updated_at""",
                     (parsed,req.high_f,req.low_f,precip," ".join(req.summary.split()).strip()[:500],utc_now(),utc_now()))
        log(conn,"environment","Human",f"Saved manual weather context for {parsed}.")
        result=environment_summary(conn)
    await hub.broadcast()
    return result


@app.post("/api/environment/seasonal-windows")
async def api_environment_seasonal_window(req: SeasonalWindowRequest) -> dict[str, Any]:
    try:
        start_md=_valid_md(req.start_md); end_md=_valid_md(req.end_md)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    name=" ".join(req.name.split()).strip()[:180]
    if not name:
        raise HTTPException(status_code=400, detail="Seasonal window name is required.")
    status=req.status if req.status in {"Active","Archived"} else "Active"
    priority=req.priority if req.priority in {"Low","Normal","High"} else "Normal"
    with db() as conn:
        now=utc_now()
        conn.execute("""INSERT INTO seasonal_windows(name,category,start_md,end_md,priority,notes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                     (name," ".join(req.category.split()).strip()[:80] or "Seasonal Window",start_md,end_md,priority," ".join(req.notes.split()).strip()[:1000],status,now,now))
        log(conn,"environment","Human",f"Added seasonal planning window: {name}.")
        result=environment_summary(conn)
    await hub.broadcast()
    return result


@app.post("/api/environment/seasonal-windows/{window_id}/status")
async def api_environment_seasonal_status(window_id: int, req: LibraryCollectionStatusRequest) -> dict[str, Any]:
    status=req.status if req.status in {"Active","Archived"} else None
    if not status:
        raise HTTPException(status_code=400, detail="Status must be Active or Archived.")
    with db() as conn:
        row=conn.execute("SELECT name FROM seasonal_windows WHERE id=?",(window_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Seasonal window not found.")
        conn.execute("UPDATE seasonal_windows SET status=?,updated_at=? WHERE id=?",(status,utc_now(),window_id))
        log(conn,"environment","Human",f"Set seasonal window {row['name']} to {status}.")
        result=environment_summary(conn)
    await hub.broadcast()
    return result


def _phenology_text(value: str, field: str, limit: int) -> str:
    cleaned = " ".join(str(value or "").split()).strip()[:limit]
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"Phenology {field} is required.")
    return cleaned


def phenology_history(conn: sqlite3.Connection, subject: str, stage: str, location_area: str = "") -> dict[str, Any]:
    subject_display=_phenology_text(subject,"subject",180); stage_display=_phenology_text(stage,"stage",120)
    norm_subject=" ".join(subject_display.casefold().split()); norm_stage=" ".join(stage_display.casefold().split())
    params=[norm_subject,norm_stage]; where="lower(trim(subject))=? AND lower(trim(stage))=? AND status IN ('observed','confirmed')"
    if location_area.strip(): where+=" AND lower(trim(location_area))=?"; params.append(" ".join(location_area.casefold().split()))
    records=rows(conn,f"SELECT subject,stage,observation_date,location_area,source,status,notes FROM phenology_observations WHERE {where} ORDER BY observation_date",tuple(params))
    for record in records: record["year"]=int(record["observation_date"][:4])
    dates=[date.fromisoformat(r["observation_date"]) for r in records]; years=sorted({r["year"] for r in records})
    stats={"years_recorded":len(years),"earliest_date":dates[0].isoformat() if dates else None,"latest_date":dates[-1].isoformat() if dates else None,"average_date":None,"current_year_difference_days":None,"comparison_years":0}
    if dates:
        avg_doy=round(sum(d.timetuple().tm_yday for d in dates)/len(dates)); stats["average_date"]=(date(2000,1,1)+timedelta(days=avg_doy-1)).strftime("%b %d").replace(" 0"," ")
        current=[d for d in dates if d.year==date.today().year]; prior=[d for d in dates if d.year<date.today().year]
        if current and prior: stats["comparison_years"]=len({d.year for d in prior}); stats["current_year_difference_days"]=current[0].timetuple().tm_yday-round(sum(d.timetuple().tm_yday for d in prior)/len(prior))
    return {"subject":subject_display,"stage":stage_display,"location_area":location_area.strip(),"records":records,"statistics":stats}


@app.post("/api/environment/phenology")
async def api_phenology_create(req: PhenologyObservationRequest) -> dict[str, Any]:
    try:
        observation_date = date.fromisoformat(req.observation_date.strip()).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Phenology observation date must use YYYY-MM-DD.")
    source = req.source if req.source in PHENOLOGY_SOURCES else "human observation"
    status = req.status if req.status in PHENOLOGY_STATUSES else "observed"
    if source == "system suggestion":
        status = "suggested"
    elif status == "suggested":
        raise HTTPException(status_code=400, detail="Only a system suggestion may use suggested status.")
    with db() as conn:
        now = utc_now()
        cursor = conn.execute(
            """INSERT INTO phenology_observations(subject,stage,observation_date,location_area,status,source,notes,review_agent_id,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (_phenology_text(req.subject,"subject",180), _phenology_text(req.stage,"stage",120), observation_date,
             _phenology_text(req.location_area,"location",180), status, source, " ".join(req.notes.split()).strip()[:1000], "research", now, now),
        )
        log(conn,"phenology","Rose",f"Recorded {status} phenology entry: {req.subject} — {req.stage}.")
        result = dict(conn.execute("SELECT * FROM phenology_observations WHERE id=?", (cursor.lastrowid,)).fetchone())
    await hub.broadcast()
    return {"status": "created", "observation": result}


@app.get("/api/environment/phenology/history")
async def api_phenology_history(subject: str, stage: str, location_area: str = "") -> dict[str, Any]:
    with db() as conn:
        return phenology_history(conn, subject, stage, location_area)


@app.post("/api/environment/phenology/{observation_id}/review")
async def api_phenology_review(observation_id: int, req: PhenologyReviewRequest) -> dict[str, Any]:
    if req.status not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=400, detail="Phenology review status must be confirmed or rejected.")
    with db() as conn:
        row = conn.execute("SELECT * FROM phenology_observations WHERE id=?", (observation_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Phenology observation not found.")
        if row["status"] != "suggested":
            raise HTTPException(status_code=409, detail="Only suggested phenology observations can be confirmed or rejected.")
        now = utc_now()
        notes = " ".join(req.notes.split()).strip()[:1000] or row["notes"]
        conn.execute("UPDATE phenology_observations SET status=?,notes=?,review_agent_id='research',reviewed_at=?,updated_at=? WHERE id=?", (req.status,notes,now,now,observation_id))
        log(conn,"phenology","Rose",f"{req.status.title()} phenology suggestion: {row['subject']} — {row['stage']}.")
        result = dict(conn.execute("SELECT * FROM phenology_observations WHERE id=?", (observation_id,)).fetchone())
    await hub.broadcast()
    return {"status": req.status, "observation": result}

@app.post("/api/environment/phenology/watchlist")
async def api_phenology_watchlist_create(req: PhenologyWatchlistRequest) -> dict[str, Any]:
    stages=[" ".join(str(s).split())[:120] for s in req.stages if str(s).strip()]
    with db() as conn:
        now=utc_now(); cur=conn.execute("INSERT INTO phenology_watchlist(subject,category,location_area,stages_json,status,priority,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(_phenology_text(req.subject,"watchlist subject",180),_phenology_text(req.category,"watchlist category",120),_phenology_text(req.location_area,"watchlist location",180),json.dumps(stages),"Active",req.priority if req.priority in {"Low","Normal","High"} else "Normal"," ".join(req.notes.split()).strip()[:1000],now,now)); row=dict(conn.execute("SELECT * FROM phenology_watchlist WHERE id=?",(cur.lastrowid,)).fetchone())
    row["stages"]=json.loads(row.pop("stages_json")); await hub.broadcast(); return {"status":"created","watchlist":row}

@app.post("/api/environment/phenology/watchlist/{watch_id}/status")
async def api_phenology_watchlist_status(watch_id:int, req: LibraryCollectionStatusRequest)->dict[str,Any]:
    if req.status not in {"Active","Inactive"}: raise HTTPException(status_code=400,detail="Watchlist status must be Active or Inactive.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM phenology_watchlist WHERE id=?",(watch_id,)).fetchone(): raise HTTPException(status_code=404,detail="Phenology watchlist item not found.")
        conn.execute("UPDATE phenology_watchlist SET status=?,updated_at=? WHERE id=?",(req.status,utc_now(),watch_id))
    await hub.broadcast(); return {"status":req.status}

@app.post("/api/environment/phenology/watchlist/{watch_id}/suggest")
async def api_phenology_watchlist_suggest(watch_id:int)->dict[str,Any]:
    with db() as conn:
        watch=conn.execute("SELECT * FROM phenology_watchlist WHERE id=?",(watch_id,)).fetchone()
        if not watch or watch["status"]!="Active": raise HTTPException(status_code=409,detail="An active watchlist item is required.")
        stages=json.loads(watch["stages_json"]); stage=stages[0] if stages else "check-in"
        today=date.fromisoformat(str(environment_summary(conn)["local_date"])); now=utc_now(); prompt=f"Rose check-in: Are you seeing {watch['subject']} — {stage} at {watch['location_area']}?"; cur=conn.execute("INSERT INTO phenology_observations(subject,stage,observation_date,location_area,status,source,notes,review_agent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(watch["subject"],stage,today.isoformat(),watch["location_area"],"suggested","system suggestion",prompt,"research",now,now)); result=dict(conn.execute("SELECT * FROM phenology_observations WHERE id=?",(cur.lastrowid,)).fetchone())
    await hub.broadcast(); return {"status":"suggested","observation":result}


@app.post("/api/stella/daily")
async def api_stella_daily(req: StellaDailyRequest) -> dict[str, Any]:
    """Answer Stella's daily-focus question from local Campus + internal Calendar state only."""
    text = " ".join(str(req.text or "").split()).strip()[:500]
    normalized = text.lower()
    understood = any(token in normalized for token in (
        "focus", "today", "priority", "priorities", "what should i do", "plan my day", "needs my attention", "work on"
    ))
    if not understood:
        return {
            "status":"clarification",
            "action":"daily_focus",
            "message":"Daily Steward can answer today’s focus and priority questions using the Campus internal Calendar. Try: ‘Stella, what should I focus on today?’",
            "additional_ai_calls":0,
        }
    with db() as conn:
        steward = daily_steward(conn)
    return {
        "status":"ok",
        "action":"daily_focus",
        "message":"I checked the Campus lanes and kept today to the smallest useful set of priorities.",
        "daily_steward":steward,
        "additional_ai_calls":0,
    }


@app.post("/api/briefing/snapshot")
async def api_briefing_snapshot() -> dict[str, Any]:
    with db() as conn:
        brief = executive_briefing(conn)
        captured_at = utc_now()
        cur = conn.execute(
            "INSERT INTO briefing_snapshots(captured_at,brief_json,created_by) VALUES(?,?,?)",
            (captured_at,json.dumps(brief,ensure_ascii=False),"Human"),
        )
        snapshot_id = int(cur.lastrowid)
        log(conn, "briefing", "Human", "Saved an Executive Briefing snapshot from local Campus state.")
    await hub.broadcast()
    return {"status":"saved","snapshot_id":snapshot_id,"captured_at":captured_at,"additional_ai_calls":0}


def _clean_memory_fields(*, title: str, body: str, memory_type: str, importance: str, tags: str = "") -> tuple[str, str, str, str, str]:
    clean_title = " ".join(str(title or "").split()).strip()[:180]
    clean_body = str(body or "").strip()[:5000]
    clean_type = normalize_memory_type(memory_type)
    clean_importance = str(importance or "Normal").title()
    if clean_importance not in MEMORY_IMPORTANCE:
        clean_importance = "Normal"
    clean_tags = ", ".join([part.strip() for part in str(tags or "").split(",") if part.strip()])[:500]
    if not clean_title or not clean_body:
        raise HTTPException(status_code=400, detail="Memory title and body are required.")
    return clean_title, clean_body, clean_type, clean_importance, clean_tags


def _memory_capture_source(conn: sqlite3.Connection, source_kind: str, source_id: int) -> dict[str, Any]:
    kind = re.sub(r"[^a-z0-9_-]+", "_", str(source_kind or "").strip().lower())
    if kind == "note":
        row = conn.execute(
            """
            SELECT n.*,p.title AS project_title,t.title AS task_title
            FROM notes n
            JOIN projects p ON p.id=n.project_id
            LEFT JOIN tasks t ON t.id=n.task_id
            WHERE n.id=?
            """,
            (source_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Note not found")
        title = f"Note — {row['task_title'] or row['project_title']}"
        return {
            "source_kind": "note",
            "source_id": int(row["id"]),
            "project_id": int(row["project_id"]),
            "title": title[:180],
            "body": str(row["body"] or "")[:5000],
            "tags": "captured, note",
        }
    if kind == "deliverable":
        row = conn.execute(
            """
            SELECT d.*,p.title AS project_title
            FROM deliverables d JOIN projects p ON p.id=d.project_id
            WHERE d.id=?
            """,
            (source_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project output not found")
        return {
            "source_kind": "deliverable",
            "source_id": int(row["id"]),
            "project_id": int(row["project_id"]),
            "title": f"Output — {row['title']}"[:180],
            "body": str(row["content_md"] or "")[:5000],
            "tags": f"captured, output, {row['deliverable_type']}",
        }
    raise HTTPException(status_code=400, detail="Memory capture supports note or deliverable sources.")


def _clean_playbook_request(req: PlaybookRequest) -> tuple[str, str, str | None, str, list[str], str, str]:
    title = " ".join(str(req.title or "").split()).strip()[:180]
    purpose = " ".join(str(req.purpose or "").split()).strip()[:1600]
    trigger_text = " ".join(str(req.trigger_text or "").split()).strip()[:1200]
    tags = ", ".join(part.strip() for part in str(req.tags or "").split(",") if part.strip())[:500]
    owner = str(req.owner_agent_id or "").strip().lower() or None
    if owner not in PLAYBOOK_OWNERS:
        owner = None
    status = " ".join(str(req.status or "Draft").split()).title()
    if status not in PLAYBOOK_STATUSES:
        status = "Draft"
    steps = _playbook_steps(req.steps)
    if not title:
        raise HTTPException(status_code=400, detail="Playbook title is required.")
    if not purpose:
        raise HTTPException(status_code=400, detail="Playbook purpose is required.")
    if not steps:
        raise HTTPException(status_code=400, detail="Add at least one playbook step.")
    return title, purpose, owner, trigger_text, steps, tags, status


def _clean_library_collection_request(req: LibraryCollectionRequest) -> tuple[str, str, str, str, str]:
    title = " ".join(str(req.title or "").split()).strip()[:220]
    collection_type = " ".join(str(req.collection_type or "Program").split()).title()
    subject = " ".join(str(req.subject or "").split()).strip()[:220]
    description = " ".join(str(req.description or "").split()).strip()[:2400]
    status = " ".join(str(req.status or "Active").split()).title()
    if not title:
        raise HTTPException(status_code=400, detail="Library title is required.")
    if collection_type not in LIBRARY_COLLECTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Library type must be one of: {', '.join(LIBRARY_COLLECTION_TYPES)}.")
    if status not in LIBRARY_COLLECTION_STATUSES:
        raise HTTPException(status_code=400, detail="Library status must be Active or Archived.")
    return title, collection_type, subject, description, status


@app.get("/api/library/inbox")
async def api_library_inbox(limit: int = 250) -> dict[str, Any]:
    """List Drop Box items only. Incoming files are not part of trusted Catalog search."""
    with db() as conn:
        incoming = library_inbox_rows(conn, limit=limit)
    return {"status":"ok","items":incoming,"count":len(incoming),"quarantined":True,"additional_ai_calls":0}


@app.post("/api/library/inbox/upload")
async def api_library_inbox_upload(request: Request, filename: str = "") -> dict[str, Any]:
    """Store one raw uploaded file in the local Library Drop Box with SHA-256 deduplication."""
    original, safe_name = _safe_library_filename(filename or request.headers.get("x-filename", ""))
    content_type = str(request.headers.get("content-type") or "application/octet-stream").split(";", 1)[0][:200]
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_LIBRARY_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Library files are limited to 100 MB each in v0.8.7.4.2.")
        except ValueError:
            pass

    inbox = library_inbox_root()
    inbox.mkdir(parents=True, exist_ok=True)
    temp_path = inbox / f".incoming-{time.time_ns()}"
    hasher = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_LIBRARY_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Library files are limited to 100 MB each in v0.8.7.4.2.")
                hasher.update(chunk)
                handle.write(chunk)
        if size <= 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        digest = hasher.hexdigest()
        with db() as conn:
            duplicate = conn.execute(
                "SELECT id,original_filename,status FROM library_inbox WHERE sha256=?", (digest,)
            ).fetchone()
            if duplicate:
                temp_path.unlink(missing_ok=True)
                return {
                    "status":"duplicate",
                    "inbox_id":int(duplicate["id"]),
                    "original_filename":duplicate["original_filename"],
                    "inbox_status":duplicate["status"],
                    "sha256":digest,
                    "additional_ai_calls":0,
                }

        stored_name = f"{digest[:12]}-{safe_name}"
        final_path = inbox / stored_name
        if final_path.exists():
            stored_name = f"{digest[:20]}-{safe_name}"
            final_path = inbox / stored_name
        temp_path.replace(final_path)
        relative_path = f"library/inbox/{stored_name}"
        now = utc_now()
        try:
            with db() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO library_inbox(original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,source_kind,notes,created_by,received_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (original,stored_name,relative_path,content_type,size,digest,"Incoming","upload","","Human",now,now),
                )
                inbox_id = int(cur.lastrowid)
                log(conn, "library", "Human", f"Added incoming Library material: {original}")
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    await hub.broadcast()
    return {
        "status":"received",
        "inbox_id":inbox_id,
        "original_filename":original,
        "size_bytes":size,
        "sha256":digest,
        "quarantined":True,
        "cataloged":False,
        "additional_ai_calls":0,
    }


@app.get("/api/library/inbox/{inbox_id}/file")
async def api_library_inbox_file(inbox_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT original_filename,stored_filename,mime_type FROM library_inbox WHERE id=?", (inbox_id,)
        ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Incoming Library material not found")
    path = library_inbox_root() / item["stored_filename"]
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Incoming Library file is missing from local storage")
    return FileResponse(path, media_type=item["mime_type"] or None, filename=item["original_filename"])


def _clean_library_catalog_request(req: LibraryCatalogRequest) -> tuple[int, str, str, str, str | None, str]:
    collection_id = int(req.collection_id)
    title = " ".join(str(req.title or "").split()).strip()[:240]
    material_type = " ".join(str(req.material_type or "Document").split()).title()
    edition_label = " ".join(str(req.edition_label or "").split()).strip()[:160]
    edition_date = str(req.edition_date or "").strip()[:32] or None
    notes = str(req.notes or "").strip()[:2400]
    if not title:
        raise HTTPException(status_code=400, detail="Cataloged material needs a title.")
    if material_type not in LIBRARY_MATERIAL_TYPES:
        raise HTTPException(status_code=400, detail=f"Material type must be one of: {', '.join(LIBRARY_MATERIAL_TYPES)}.")
    if edition_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition_date):
        raise HTTPException(status_code=400, detail="Edition date must use YYYY-MM-DD.")
    return collection_id, title, material_type, edition_label, edition_date, notes


@app.post("/api/library/inbox/{inbox_id}/catalog")
async def api_library_inbox_catalog(inbox_id: int, req: LibraryCatalogRequest) -> dict[str, Any]:
    """Human-only promotion from quarantined Intake to trusted Library material. No AI/network calls."""
    collection_id, title, material_type, edition_label, edition_date, notes = _clean_library_catalog_request(req)
    with db() as conn:
        item = conn.execute("SELECT * FROM library_inbox WHERE id=?", (inbox_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Incoming Library material not found")
        if item["status"] != "Incoming":
            raise HTTPException(status_code=409, detail="This incoming material has already been processed.")
        collection = conn.execute("SELECT id,title,status FROM library_collections WHERE id=?", (collection_id,)).fetchone()
        if not collection:
            raise HTTPException(status_code=404, detail="Library collection not found")
        if collection["status"] != "Active":
            raise HTTPException(status_code=400, detail="Restore the Library collection before cataloging new material into it.")

    source = library_inbox_root() / item["stored_filename"]
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="Incoming Library file is missing from local storage")
    collection_dir = library_catalog_root() / f"collection-{collection_id}"
    collection_dir.mkdir(parents=True, exist_ok=True)
    destination = collection_dir / item["stored_filename"]
    if destination.exists():
        destination = collection_dir / f"{item['sha256'][:20]}-{item['stored_filename']}"
    shutil.move(str(source), str(destination))
    relative_path = destination.relative_to(DB_PATH.parent).as_posix()
    now = utc_now()
    try:
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO library_materials(
                    collection_id,title,material_type,edition_label,edition_date,status,source_kind,notes,
                    created_by,created_at,updated_at,inbox_id,original_filename,stored_filename,relative_path,
                    mime_type,size_bytes,sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    collection_id,title,material_type,edition_label,edition_date,"Cataloged","library_inbox",notes,
                    "Human",now,now,inbox_id,item["original_filename"],destination.name,relative_path,
                    item["mime_type"],int(item["size_bytes"] or 0),item["sha256"],
                ),
            )
            material_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE library_inbox SET status='Cataloged',cataloged_material_id=?,cataloged_at=?,updated_at=? WHERE id=? AND status='Incoming'",
                (material_id,now,now,inbox_id),
            )
            conn.execute("UPDATE library_collections SET updated_at=? WHERE id=?", (now,collection_id))
            log(conn, "library", "Human", f"Cataloged trusted Library material: {title} → {collection['title']}")
    except Exception:
        # Return the file to quarantine if the database promotion fails.
        source.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not source.exists():
            shutil.move(str(destination), str(source))
        raise
    with db() as conn:
        index_result = index_library_material(conn, material_id, force=True)
        log(conn, "library_index", "Librarian", f"Locally indexed trusted material #{material_id}: {index_result['extraction_status']} ({index_result['char_count']} chars).")
    await hub.broadcast()
    return {
        "status":"cataloged","inbox_id":inbox_id,"material_id":material_id,"collection_id":collection_id,
        "trusted":True,"local_only":True,"additional_ai_calls":0,"index":index_result,
    }


@app.post("/api/library/index/refresh")
async def api_library_index_refresh() -> dict[str, Any]:
    """Rebuild trusted local document indexes. Incoming Materials and the web are excluded."""
    with db() as conn:
        result = refresh_library_index(conn, force=True)
        log(conn, "library_index", "Human", f"Refreshed trusted Library text index: {result['indexed']} indexed; {result['needs_ocr']} need OCR.")
    await hub.broadcast()
    return {"status":"refreshed", **result}


@app.get("/api/library/materials/{material_id}/file")
async def api_library_material_file(material_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT original_filename,relative_path,mime_type,status FROM library_materials WHERE id=?", (material_id,)
        ).fetchone()
    if not item or item["status"] != "Cataloged":
        raise HTTPException(status_code=404, detail="Trusted Library material not found")
    rel = Path(str(item["relative_path"] or ""))
    path = (DB_PATH.parent / rel).resolve()
    root = library_catalog_root().resolve()
    if root not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Trusted Library file is missing from local storage")
    return FileResponse(path, media_type=item["mime_type"] or None, filename=item["original_filename"] or path.name)


@app.get("/api/library/librarian")
async def api_library_librarian(q: str = "") -> dict[str, Any]:
    """Search trusted Mavis Library holdings only. No AI or network access is available here."""
    clean_query = " ".join(str(q or "").split()).strip()[:300]
    if not clean_query:
        raise HTTPException(status_code=400, detail="Ask the Librarian a question or enter a search phrase.")
    with db() as conn:
        # These helpers structurally exclude quarantined library_inbox rows.
        collections = library_catalog_rows(conn)
        materials = library_material_search_rows(conn, limit=1000)
        result = search_trusted_library(clean_query, collections, materials)
        log(conn, "library", "Librarian", f"Local trusted-Library retrieval: {clean_query[:180]}")
    return result


@app.post("/api/programs/library-first/{task_id}/decide")
async def api_programs_library_first_decide(task_id: int, req: ProgramsLibraryDecisionRequest) -> dict[str, Any]:
    """Record the human Library First choice and resume the approved workflow."""
    global workflow_task
    if workflow_task and not workflow_task.done():
        raise HTTPException(status_code=409, detail="The campus workflow is still running. Wait for the Library First pause to finish.")

    decision = str(req.decision or "").strip().lower()
    if decision not in PROGRAMS_LIBRARY_DECISIONS:
        raise HTTPException(status_code=400, detail="Decision must be reuse, revise, or create_new.")
    note = " ".join(str(req.note or "").split()).strip()[:1200]

    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Programs task not found.")
        if str(task["owner_agent_id"] or "") != "programs":
            raise HTTPException(status_code=400, detail="Library First decisions apply only to Programs tasks.")
        project = conn.execute("SELECT * FROM projects WHERE id=?", (int(task["project_id"]),)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")
        preflight = conn.execute(
            "SELECT * FROM programs_library_preflights WHERE task_id=?",
            (int(task_id),),
        ).fetchone()
        if not preflight:
            raise HTTPException(status_code=409, detail="This Programs task has not reached its Library First check yet.")
        if str(preflight["status"] or "") != "Pending":
            raise HTTPException(status_code=409, detail="This Library First decision has already been recorded.")

        try:
            result = json.loads(str(preflight["result_json"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            result = {}
        matched_ids: set[int] = set()
        for item in list(result.get("collections") or []):
            if isinstance(item, dict) and item.get("id") is not None:
                try: matched_ids.add(int(item["id"]))
                except (TypeError, ValueError): pass
        for item in list(result.get("materials") or []):
            if isinstance(item, dict) and item.get("collection_id") is not None:
                try: matched_ids.add(int(item["collection_id"]))
                except (TypeError, ValueError): pass

        selected_collection_id: int | None = None
        if decision in {"reuse", "revise"}:
            if req.collection_id is None:
                raise HTTPException(status_code=400, detail="Choose a Library collection to reuse or revise.")
            selected_collection_id = int(req.collection_id)
            if selected_collection_id not in matched_ids:
                raise HTTPException(status_code=400, detail="Choose one of the trusted Library collections returned by this preflight.")
            selected = conn.execute(
                "SELECT id,title FROM library_collections WHERE id=? AND status='Active'",
                (selected_collection_id,),
            ).fetchone()
            if not selected:
                raise HTTPException(status_code=409, detail="The selected Library collection is no longer active.")

        now = utc_now()
        conn.execute(
            """
            UPDATE programs_library_preflights
            SET status='Decided',decision=?,selected_collection_id=?,human_note=?,updated_at=?
            WHERE task_id=?
            """,
            (decision, selected_collection_id, note, now, int(task_id)),
        )
        conn.execute(
            "UPDATE tasks SET status='Waiting',result=NULL,updated_at=? WHERE id=?",
            (now, int(task_id)),
        )
        conn.execute(
            "UPDATE projects SET status='Active',updated_at=? WHERE id=?",
            (now, int(project["id"])),
        )
        set_workflow_run(
            conn,
            int(project["id"]),
            state="Library Decision Queued",
            current_task_id=int(task_id),
            last_error=None,
        )
        reset_agents(conn)
        label = {"reuse":"Reuse Existing","revise":"Revise Existing","create_new":"Create New"}[decision]
        log(
            conn,
            "library_first",
            "Human",
            f"Programs Library First decision: {label} for {task['title']}.",
        )

    await hub.broadcast()
    workflow_task = asyncio.create_task(execute_approved_plan(int(project["id"]), resume=True))
    return {
        "status": "resuming",
        "project_id": int(project["id"]),
        "task_id": int(task_id),
        "decision": decision,
        "selected_collection_id": selected_collection_id,
        "library_first": True,
    }


@app.get("/api/library/catalog")
async def api_library_catalog(q: str = "", collection_type: str = "all", status: str = "Active", limit: int = 100) -> dict[str, Any]:
    """Search the local catalog only. This endpoint performs no AI or network calls."""
    query = " ".join(str(q or "").split()).strip()[:300]
    type_filter = " ".join(str(collection_type or "all").split()).title()
    status_filter = " ".join(str(status or "all").split()).title()
    if type_filter != "All" and type_filter not in LIBRARY_COLLECTION_TYPES:
        raise HTTPException(status_code=400, detail="Unknown Library type filter.")
    if status_filter != "All" and status_filter not in LIBRARY_COLLECTION_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown Library status filter.")
    limit = max(1, min(int(limit or 100), 250))
    clauses: list[str] = []
    params: list[Any] = []
    if query:
        like = f"%{query}%"
        clauses.append("(lc.title LIKE ? COLLATE NOCASE OR lc.subject LIKE ? COLLATE NOCASE OR lc.description LIKE ? COLLATE NOCASE OR lc.collection_type LIKE ? COLLATE NOCASE)")
        params.extend([like, like, like, like])
    if type_filter != "All":
        clauses.append("lc.collection_type=?")
        params.append(type_filter)
    if status_filter != "All":
        clauses.append("lc.status=?")
        params.append(status_filter)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with db() as conn:
        found = rows(
            conn,
            f"""
            SELECT lc.*,COUNT(lm.id) AS material_count
            FROM library_collections lc
            LEFT JOIN library_materials lm ON lm.collection_id=lc.id
            {where}
            GROUP BY lc.id
            ORDER BY CASE lc.status WHEN 'Active' THEN 0 ELSE 1 END,lc.updated_at DESC,lc.title COLLATE NOCASE
            LIMIT ?
            """,
            tuple(params),
        )
    return {"status":"ok","query":query,"collections":found,"count":len(found),"local_only":True,"additional_ai_calls":0}


@app.post("/api/library/collections")
async def api_library_collection_create(req: LibraryCollectionRequest) -> dict[str, Any]:
    title, collection_type, subject, description, status = _clean_library_collection_request(req)
    now = utc_now()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (title,collection_type,subject,description,status,"Human",now,now),
        )
        collection_id = int(cur.lastrowid)
        log(conn, "library", "Human", f"Cataloged Library {collection_type.lower()}: {title}")
    await hub.broadcast()
    return {"status":"saved","collection_id":collection_id,"additional_ai_calls":0}


@app.post("/api/library/collections/{collection_id}")
async def api_library_collection_edit(collection_id: int, req: LibraryCollectionRequest) -> dict[str, Any]:
    title, collection_type, subject, description, status = _clean_library_collection_request(req)
    with db() as conn:
        existing = conn.execute("SELECT id FROM library_collections WHERE id=?", (collection_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Library collection not found")
        conn.execute(
            """
            UPDATE library_collections
            SET title=?,collection_type=?,subject=?,description=?,status=?,updated_at=?
            WHERE id=?
            """,
            (title,collection_type,subject,description,status,utc_now(),collection_id),
        )
        log(conn, "library", "Human", f"Updated Library catalog record: {title}")
    await hub.broadcast()
    return {"status":"updated","collection_id":collection_id,"additional_ai_calls":0}


@app.post("/api/library/collections/{collection_id}/status")
async def api_library_collection_status(collection_id: int, req: LibraryCollectionStatusRequest) -> dict[str, Any]:
    status = " ".join(str(req.status or "").split()).title()
    if status not in LIBRARY_COLLECTION_STATUSES:
        raise HTTPException(status_code=400, detail="Library status must be Active or Archived.")
    with db() as conn:
        collection = conn.execute("SELECT id,title FROM library_collections WHERE id=?", (collection_id,)).fetchone()
        if not collection:
            raise HTTPException(status_code=404, detail="Library collection not found")
        conn.execute("UPDATE library_collections SET status=?,updated_at=? WHERE id=?", (status,utc_now(),collection_id))
        log(conn, "library", "Human", f"Set Library record {collection['title']} to {status}.")
    await hub.broadcast()
    return {"status":"updated","collection_id":collection_id,"collection_status":status,"additional_ai_calls":0}


@app.post("/api/playbooks")
async def api_playbook_create(req: PlaybookRequest) -> dict[str, Any]:
    title, purpose, owner, trigger_text, steps, tags, status = _clean_playbook_request(req)
    now = utc_now()
    with db() as conn:
        if req.project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (req.project_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found")
        cur = conn.execute(
            """
            INSERT INTO playbooks(project_id,title,purpose,owner_agent_id,trigger_text,steps_json,tags,status,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (req.project_id,title,purpose,owner,trigger_text,json.dumps(steps,ensure_ascii=False),tags,status,"Human",now,now),
        )
        playbook_id = int(cur.lastrowid)
        log(conn, "playbook", "Human", f"Created {status.lower()} playbook: {title}")
    await hub.broadcast()
    return {"status":"saved","playbook_id":playbook_id}


@app.post("/api/playbooks/{playbook_id}")
async def api_playbook_edit(playbook_id: int, req: PlaybookRequest) -> dict[str, Any]:
    title, purpose, owner, trigger_text, steps, tags, status = _clean_playbook_request(req)
    now = utc_now()
    with db() as conn:
        old = conn.execute("SELECT id FROM playbooks WHERE id=?", (playbook_id,)).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Playbook not found")
        if req.project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (req.project_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found")
        conn.execute(
            """
            UPDATE playbooks SET project_id=?,title=?,purpose=?,owner_agent_id=?,trigger_text=?,steps_json=?,tags=?,status=?,updated_at=? WHERE id=?
            """,
            (req.project_id,title,purpose,owner,trigger_text,json.dumps(steps,ensure_ascii=False),tags,status,now,playbook_id),
        )
        log(conn, "playbook", "Human", f"Updated playbook: {title}")
    await hub.broadcast()
    return {"status":"updated","playbook_id":playbook_id}


@app.post("/api/playbooks/{playbook_id}/status")
async def api_playbook_status(playbook_id: int, req: PlaybookStatusRequest) -> dict[str, Any]:
    status = " ".join(str(req.status or "").split()).title()
    if status not in PLAYBOOK_STATUSES:
        raise HTTPException(status_code=400, detail="Playbook status must be Draft, Active, or Archived.")
    with db() as conn:
        pb = conn.execute("SELECT id,title FROM playbooks WHERE id=?", (playbook_id,)).fetchone()
        if not pb:
            raise HTTPException(status_code=404, detail="Playbook not found")
        conn.execute("UPDATE playbooks SET status=?,updated_at=? WHERE id=?", (status,utc_now(),playbook_id))
        log(conn, "playbook", "Human", f"Set playbook {pb['title']} to {status}.")
    await hub.broadcast()
    return {"status":"updated","playbook_id":playbook_id,"playbook_status":status}


@app.post("/api/memory")
async def api_memory_create(req: MemoryRequest) -> dict[str, Any]:
    title, body, memory_type, importance, tags = _clean_memory_fields(
        title=req.title, body=req.body, memory_type=req.memory_type, importance=req.importance, tags=req.tags
    )
    source_kind = re.sub(r"[^a-z0-9_-]+", "_", str(req.source_kind or "manual").strip().lower())[:40] or "manual"
    created_by = " ".join(str(req.created_by or "Human").split()).strip()[:80] or "Human"
    now = utc_now()
    with db() as conn:
        if req.project_id is not None:
            project = conn.execute("SELECT id,title FROM projects WHERE id=?", (req.project_id,)).fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        review_interval = normalize_review_interval(req.review_interval_days)
        review_due_at = memory_review_due(now, review_interval)
        cur = conn.execute(
            """
            INSERT INTO institutional_memory(
                project_id,memory_type,title,body,tags,importance,source_kind,source_id,status,created_by,created_at,updated_at,reviewed_at,review_interval_days,review_due_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (req.project_id, memory_type, title, body, tags, importance, source_kind, req.source_id, "Active", created_by, now, now, now, review_interval, review_due_at),
        )
        memory_id = int(cur.lastrowid)
        scope = f"project #{req.project_id}" if req.project_id is not None else "the institution"
        log(conn, "memory", created_by, f"Added institutional memory for {scope}: {title}")
    await hub.broadcast()
    return {"status": "saved", "memory_id": memory_id}


@app.post("/api/memory/capture")
async def api_memory_capture(req: MemoryCaptureRequest) -> dict[str, Any]:
    with db() as conn:
        source = _memory_capture_source(conn, req.source_kind, req.source_id)
        existing = conn.execute(
            "SELECT id,status FROM institutional_memory WHERE source_kind=? AND source_id=? ORDER BY id DESC LIMIT 1",
            (source["source_kind"], source["source_id"]),
        ).fetchone()
        if existing:
            return {
                "status": "exists",
                "memory_id": int(existing["id"]),
                "memory_status": existing["status"],
                "already_exists": True,
            }
        title, body, memory_type, importance, tags = _clean_memory_fields(
            title=source["title"], body=source["body"], memory_type=req.memory_type, importance=req.importance, tags=source["tags"]
        )
        now = utc_now()
        review_interval = normalize_review_interval(req.review_interval_days)
        review_due_at = memory_review_due(now, review_interval)
        cur = conn.execute(
            """
            INSERT INTO institutional_memory(
                project_id,memory_type,title,body,tags,importance,source_kind,source_id,status,created_by,created_at,updated_at,reviewed_at,review_interval_days,review_due_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (source["project_id"], memory_type, title, body, tags, importance, source["source_kind"], source["source_id"], "Active", "Human", now, now, now, review_interval, review_due_at),
        )
        memory_id = int(cur.lastrowid)
        log(conn, "memory", "Human", f"Captured {source['source_kind']} #{source['source_id']} into Institutional Memory: {title}")
    await hub.broadcast()
    return {"status": "captured", "memory_id": memory_id, "already_exists": False}



@app.post("/api/memory/{memory_id}")
async def api_memory_edit(memory_id: int, req: MemoryEditRequest) -> dict[str, Any]:
    title, body, memory_type, importance, tags = _clean_memory_fields(
        title=req.title, body=req.body, memory_type=req.memory_type, importance=req.importance, tags=req.tags
    )
    with db() as conn:
        memory = conn.execute("SELECT * FROM institutional_memory WHERE id=?", (memory_id,)).fetchone()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        if req.project_id is not None:
            project = conn.execute("SELECT id FROM projects WHERE id=?", (req.project_id,)).fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        now = utc_now()
        review_interval = normalize_review_interval(req.review_interval_days)
        interval_changed = review_interval != normalize_review_interval(memory["review_interval_days"])
        reviewed_at = now if interval_changed else (memory["reviewed_at"] or now)
        review_due_at = memory_review_due(reviewed_at, review_interval) if interval_changed else memory["review_due_at"]
        conn.execute(
            """
            UPDATE institutional_memory
            SET project_id=?,memory_type=?,title=?,body=?,tags=?,importance=?,updated_at=?,
                reviewed_at=?,review_interval_days=?,review_due_at=?
            WHERE id=?
            """,
            (req.project_id, memory_type, title, body, tags, importance, now, reviewed_at, review_interval, review_due_at, memory_id),
        )
        log(conn, "memory", "Human", f"Edited institutional memory: {title}")
    await hub.broadcast()
    return {"status": "updated", "memory_id": memory_id}


@app.post("/api/memory/{memory_id}/review")
async def api_memory_review(memory_id: int) -> dict[str, Any]:
    with db() as conn:
        memory = conn.execute("SELECT * FROM institutional_memory WHERE id=?", (memory_id,)).fetchone()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        now = utc_now()
        interval = normalize_review_interval(memory["review_interval_days"])
        due = memory_review_due(now, interval)
        conn.execute(
            "UPDATE institutional_memory SET reviewed_at=?,review_due_at=?,updated_at=? WHERE id=?",
            (now, due, now, memory_id),
        )
        log(conn, "memory", "Human", f"Reviewed institutional memory: {memory['title']}")
    await hub.broadcast()
    return {"status": "reviewed", "memory_id": memory_id, "review_due_at": due}


@app.post("/api/memory/{memory_id}/supersede")
async def api_memory_supersede(memory_id: int, req: MemoryEditRequest) -> dict[str, Any]:
    title, body, memory_type, importance, tags = _clean_memory_fields(
        title=req.title, body=req.body, memory_type=req.memory_type, importance=req.importance, tags=req.tags
    )
    with db() as conn:
        old = conn.execute("SELECT * FROM institutional_memory WHERE id=?", (memory_id,)).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Memory not found")
        if old["superseded_by_id"] is not None:
            raise HTTPException(status_code=409, detail="This memory has already been superseded.")
        if req.project_id is not None and not conn.execute("SELECT id FROM projects WHERE id=?", (req.project_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found")
        now = utc_now()
        interval = normalize_review_interval(req.review_interval_days)
        due = memory_review_due(now, interval)
        cur = conn.execute(
            """
            INSERT INTO institutional_memory(
                project_id,memory_type,title,body,tags,importance,source_kind,source_id,status,created_by,
                created_at,updated_at,reviewed_at,review_interval_days,review_due_at,supersedes_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (req.project_id,memory_type,title,body,tags,importance,old["source_kind"],old["source_id"],"Active","Human",
             now,now,now,interval,due,memory_id),
        )
        new_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE institutional_memory SET status='Archived',superseded_by_id=?,updated_at=? WHERE id=?",
            (new_id, now, memory_id),
        )
        log(conn, "memory", "Human", f"Superseded institutional memory #{memory_id} with #{new_id}: {title}")
    await hub.broadcast()
    return {"status": "superseded", "memory_id": new_id, "supersedes_id": memory_id}


@app.post("/api/memory/{memory_id}/status")
async def api_memory_status(memory_id: int, req: MemoryStatusRequest) -> dict[str, Any]:
    status = req.status.title()
    if status not in MEMORY_STATUSES:
        raise HTTPException(status_code=400, detail="Memory status must be Active or Archived.")
    with db() as conn:
        memory = conn.execute("SELECT id,title,status FROM institutional_memory WHERE id=?", (memory_id,)).fetchone()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        conn.execute("UPDATE institutional_memory SET status=?,updated_at=? WHERE id=?", (status, utc_now(), memory_id))
        log(conn, "memory", "Human", f"{status} institutional memory: {memory['title']}")
    await hub.broadcast()
    return {"status": status, "memory_id": memory_id}


@app.post("/api/repository/rescan")
async def api_repository_rescan() -> dict[str, Any]:
    with db() as conn:
        file_count = rescan_repository(conn)
        log(conn, "repository", "Campus", f"Project Repository refreshed: {file_count} registered file(s).")
    await hub.broadcast()
    return {"status": "ok", "file_count": file_count}


@app.get("/api/repository/files/{file_id}/download")
async def api_repository_file_download(file_id: int) -> FileResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM project_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Repository file not found")
        path = _repository_safe_path(row["relative_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Repository file is missing from disk")
        return FileResponse(path, media_type=row["mime_type"] or None, filename=row["filename"])


@app.get("/api/repository/files/{file_id}/view")
async def api_repository_file_view(file_id: int) -> FileResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM project_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Repository file not found")
        path = _repository_safe_path(row["relative_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Repository file is missing from disk")
        headers = {"Content-Disposition": f'inline; filename="{row["filename"].replace(chr(34), "")}"'}
        return FileResponse(path, media_type=row["mime_type"] or None, headers=headers)


@app.get("/api/ai/status")
async def api_ai_status() -> dict[str, object]:
    status = public_ai_status()

    with db() as conn:
        last = conn.execute(
            "SELECT provider,operation,status,model,created_at FROM ai_calls ORDER BY id DESC LIMIT 1"
        ).fetchone()

        verified_rows = conn.execute(
            """
            SELECT provider, MAX(id) AS latest_id
            FROM ai_calls
            WHERE operation='connection_test' AND status='Success'
            GROUP BY provider
            """
        ).fetchall()

    verified = {row["provider"] for row in verified_rows}

    for provider_id, provider_status in status["providers"].items():
        provider_status["last_verified"] = provider_id in verified

    status["last_operation"] = last["operation"] if last else None
    status["last_provider"] = last["provider"] if last else None
    status["last_status"] = last["status"] if last else None
    status["last_seen"] = last["created_at"] if last else None

    with db() as conn:
        status["control"] = ai_control_state(conn)
        status["usage_today"] = ai_usage_summary(conn)["today"]

    return status


@app.post("/api/ai/stop")
async def api_ai_stop() -> dict[str, Any]:
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE ai_control
            SET enabled=0,stopped_reason=?,updated_at=?
            WHERE id=1
            """,
            ("Stopped by the human executive.", now),
        )
        log(
            conn,
            "ai_control",
            "Human",
            "Emergency Stop AI enabled. New AI calls are blocked. A request already in flight may still finish.",
        )
        control = ai_control_state(conn)

    await hub.broadcast()
    return {"status": "stopped", "control": control}


@app.post("/api/ai/resume")
async def api_ai_resume() -> dict[str, Any]:
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE ai_control
            SET enabled=1,stopped_reason=NULL,updated_at=?
            WHERE id=1
            """,
            (now,),
        )
        control = ai_control_state(conn)
        log(
            conn,
            "ai_control",
            "Human",
            (
                "AI calls re-enabled by the human executive."
                if not control["budget_blocked"]
                else "AI manually re-enabled, but the estimated-cost guardrail is still blocking new calls."
            ),
        )

    await hub.broadcast()
    return {"status": "resumed", "control": control}


@app.post("/api/ai/budget")
async def api_ai_budget(req: AIBudgetRequest) -> dict[str, Any]:
    value = float(req.daily_estimated_cost_limit_usd)
    if value < 0 or value > 1000:
        raise HTTPException(
            status_code=400,
            detail="Daily estimated-cost limit must be between $0 and $1,000. Use $0 for no cost-limit guardrail.",
        )

    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE ai_control
            SET daily_estimated_cost_limit_usd=?,updated_at=?
            WHERE id=1
            """,
            (value, now),
        )
        control = ai_control_state(conn)
        log(
            conn,
            "ai_control",
            "Human",
            f"Changed the daily OpenAI list-price estimate guardrail to ${value:.2f}.",
        )

    await hub.broadcast()
    return {"status": "updated", "control": control}


@app.post("/api/ai/test/{provider_id}")
async def api_ai_test_provider(provider_id: str) -> dict[str, Any]:
    provider_id = provider_id.strip().lower()

    try:
        status = provider_public_status(provider_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Unsupported AI provider: {provider_id}")

    if not status["supported"]:
        raise HTTPException(status_code=400, detail=f"{status['provider']} is not supported.")
    if not status["configured"]:
        key_name = "GEMINI_API_KEY" if provider_id == "gemini" else "OPENAI_API_KEY"
        raise HTTPException(
            status_code=400,
            detail=f"{status['provider']} API key not found. Add {key_name}=your_key to .env beside app.py.",
        )

    prompt = "Reply with exactly: Mavis Digital Campus AI connection successful."
    started = time.perf_counter()

    try:
        require_ai_allowed("connection_test", provider_id)
        provider = get_provider(provider_id)
        result = await asyncio.to_thread(
            provider.generate_text,
            prompt,
            max_output_tokens=64,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        expected = "Mavis Digital Campus AI connection successful."
        normalized = result.text.strip().rstrip()
        verified = normalized == expected or normalized.rstrip(".") == expected.rstrip(".")

        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    result.provider,
                    result.model,
                    "connection_test",
                    "Success" if verified else "Responded",
                    latency_ms,
                    result.input_chars,
                    result.output_chars,
                    "Connection verified." if verified else f"{status['provider']} responded but used different wording.",
                    utc_now(),
                ),
            )
            log(
                conn,
                "ai",
                status["provider"],
                f"AI connection test {'verified' if verified else 'responded'} using {result.model}. No project data was sent.",
            )

        await hub.broadcast()

        return {
            "status": "connected",
            "verified": verified,
            "provider": status["provider"],
            "provider_id": provider_id,
            "model": result.model,
            "message": result.text,
            "latency_ms": latency_ms,
            "authority": "Connection test only",
        }

    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = str(exc)[:500]

        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    provider_id,
                    str(status.get("model", "")),
                    "connection_test",
                    "Failed",
                    latency_ms,
                    len(prompt),
                    0,
                    message,
                    utc_now(),
                ),
            )
            log(
                conn,
                "ai_error",
                status["provider"],
                "AI connection test failed. No project data was sent.",
            )

        await hub.broadcast()
        raise HTTPException(status_code=502, detail=message) from exc


@app.post("/api/ai/test")
async def api_ai_test_legacy() -> dict[str, Any]:
    """Backward-compatible Gemini test endpoint."""
    return await api_ai_test_provider("gemini")


@app.post("/api/reset")
async def api_reset() -> dict[str, str]:
    global workflow_task
    if workflow_task and not workflow_task.done():
        workflow_task.cancel()
        try:
            await workflow_task
        except asyncio.CancelledError:
            pass
    reset_runtime()
    await hub.broadcast()
    return {"status": "reset"}


def normalize_chief_request(value: str) -> str:
    """Normalize only for duplicate protection; preserve the original request for the actual Chief prompt."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def chief_existing_plan_response(conn: sqlite3.Connection, project_id: int, *, reason: str) -> dict[str, Any] | None:
    project = conn.execute("SELECT id,title,status FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        return None
    task_count = int(conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id=?", (project_id,)).fetchone()[0])
    plan_row = conn.execute("SELECT questions_json,model FROM chief_plans WHERE project_id=?", (project_id,)).fetchone()
    questions: list[str] = []
    model = ""
    if plan_row:
        try:
            questions = json.loads(plan_row["questions_json"] or "[]")
        except Exception:
            questions = []
        model = str(plan_row["model"] or "")
    return {
        "status": "existing_project",
        "project_id": int(project["id"]),
        "project_title": str(project["title"]),
        "project_status": str(project["status"]),
        "task_count": task_count,
        "questions_for_executive": questions,
        "latency_ms": 0,
        "model": model,
        "duplicate_prevented": True,
        "duplicate_reason": reason,
    }


def recent_duplicate_chief_request(conn: sqlite3.Connection, normalized_request: str) -> dict[str, Any] | None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CHIEF_DUPLICATE_WINDOW_SECONDS)
    candidates = conn.execute(
        """
        SELECT project_id,updated_at
        FROM chief_request_submissions
        WHERE normalized_request=? AND status='Completed' AND project_id IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
        """,
        (normalized_request,),
    ).fetchall()
    for row in candidates:
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if updated >= cutoff:
            existing = chief_existing_plan_response(conn, int(row["project_id"]), reason="same_request_recently_completed")
            if existing:
                return existing
    return None


@app.post("/api/chief/plan")
async def api_chief_plan(req: ProjectRequest) -> dict[str, Any]:
    """Serialize Chief planning so duplicate submissions cannot race each other."""
    async with chief_plan_lock:
        return await _api_chief_plan_locked(req)


async def _api_chief_plan_locked(req: ProjectRequest) -> dict[str, Any]:
    """Ask the real Chief of Staff to create one proposed plan, then stop at human approval."""
    global workflow_task
    if workflow_task and not workflow_task.done():
        raise HTTPException(status_code=409, detail="A workflow is already running.")

    executive_request = req.title.strip()
    if not executive_request:
        raise HTTPException(status_code=400, detail="Executive request cannot be empty.")

    normalized_request = normalize_chief_request(executive_request)
    request_key = str(req.request_id or "").strip()[:160]
    if not request_key:
        request_key = hashlib.sha256(f"legacy:{time.time_ns()}:{executive_request}".encode("utf-8")).hexdigest()

    with db() as conn:
        exact = conn.execute(
            "SELECT status,project_id FROM chief_request_submissions WHERE request_key=?",
            (request_key,),
        ).fetchone()
        if exact and exact["status"] == "Completed" and exact["project_id"] is not None:
            existing = chief_existing_plan_response(conn, int(exact["project_id"]), reason="same_submission_id")
            if existing:
                return existing
        if not req.force_new:
            existing = recent_duplicate_chief_request(conn, normalized_request)
            if existing:
                return existing

    with db() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE status='Pending'").fetchone()[0]
    if pending:
        raise HTTPException(
            status_code=409,
            detail="Resolve the pending human approval before asking the Chief to plan another project.",
        )

    chief_provider_id = role_provider_id("chief")
    chief_status = provider_public_status(chief_provider_id)
    if not chief_status["configured"]:
        raise HTTPException(
            status_code=400,
            detail=f"{chief_status['provider']} is assigned to the Chief but its API key is not configured in .env.",
        )

    try:
        require_ai_allowed("chief_plan", chief_provider_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    with db() as conn:
        now = utc_now()
        conn.execute(
            """
            INSERT INTO chief_request_submissions(
                request_key,normalized_request,original_request,status,project_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(request_key) DO UPDATE SET
                normalized_request=excluded.normalized_request,
                original_request=excluded.original_request,
                status='Planning',
                project_id=NULL,
                updated_at=excluded.updated_at
            """,
            (request_key, normalized_request, executive_request, "Planning", None, now, now),
        )

    await set_agent("chief", building="manor", status=f"Planning with {chief_status['provider']}", task_id=None)
    await add_log("ai", "Chief of Staff", f"Received the executive request and is preparing a proposed work plan with {chief_status['provider']}.")

    started = time.perf_counter()
    try:
        provider = get_role_provider("chief")
        with db() as conn:
            memory_context = institutional_memory_for_prompt(conn)
            playbook_context = playbooks_for_prompt(conn)
        chief_result = await asyncio.to_thread(
            plan_project, provider, executive_request, memory_context, playbook_context
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        plan = chief_result.plan
        generation = chief_result.generation
        now = utc_now()

        with db() as conn:
            reset_agents(conn)
            cur = conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                (plan["project_title"], "Awaiting Approval", now, now),
            )
            project_id = int(cur.lastrowid)

            for sequence, task in enumerate(plan["tasks"], start=1):
                conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        task["title"],
                        task["owner"],
                        "Waiting",
                        sequence,
                        task["brief"],
                        now,
                        now,
                    ),
                )

            conn.execute(
                """
                INSERT INTO chief_plans(
                    project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                    expected_deliverables_json,provider,model,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    project_id,
                    plan["summary"],
                    json.dumps(plan["success_criteria"], ensure_ascii=False),
                    json.dumps(plan["questions_for_executive"], ensure_ascii=False),
                    json.dumps(plan["risk_notes"], ensure_ascii=False),
                    json.dumps(plan.get("expected_deliverables", []), ensure_ascii=False),
                    generation.provider,
                    generation.model,
                    now,
                ),
            )

            task_summary = "; ".join(
                f"{i}. {task['title']} → {task['owner']}"
                for i, task in enumerate(plan["tasks"], start=1)
            )
            questions = plan["questions_for_executive"]
            approval_summary = (
                f"{plan['summary']} Proposed delegation: {task_summary}. "
                + (
                    "Questions for you: " + " | ".join(questions) + ". "
                    if questions
                    else ""
                )
                + f"Expected outputs: {len(plan.get('expected_deliverables', []))}. "
                + "Approve to authorize the internal v0.8.7.4.2 workflow. Outputs will be assembled locally from agent artifacts; no external action is authorized."
            )[:3500]

            conn.execute(
                """
                INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    project_id,
                    f"Approve Chief's plan: {plan['project_title']}",
                    approval_summary,
                    "Pending",
                    now,
                    now,
                ),
            )

            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,project_id,task_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    generation.provider,
                    generation.model,
                    "chief_plan",
                    "Success",
                    latency_ms,
                    generation.input_chars,
                    generation.output_chars,
                    f"Chief created a {len(plan['tasks'])}-task project plan. No tasks were executed.",
                    project_id,
                    None,
                    now,
                ),
            )
            conn.execute(
                "UPDATE chief_request_submissions SET status='Completed',project_id=?,updated_at=? WHERE request_key=?",
                (project_id, now, request_key),
            )
            log(
                conn,
                "plan",
                "Chief of Staff",
                f"Prepared a {len(plan['tasks'])}-task plan for human approval: {plan['project_title']}",
            )
            log(
                conn,
                "approval",
                "Chief of Staff",
                "The proposed plan is waiting for executive approval. No delegated task has started.",
            )
            conn.execute(
                "UPDATE agents SET building_id='manor',status='Waiting for plan approval',task_id=NULL,updated_at=? WHERE id='chief'",
                (now,),
            )

        await hub.broadcast()
        return {
            "status": "awaiting_approval",
            "project_id": project_id,
            "project_title": plan["project_title"],
            "task_count": len(plan["tasks"]),
            "questions_for_executive": plan["questions_for_executive"],
            "latency_ms": latency_ms,
            "model": generation.model,
            "duplicate_prevented": False,
        }

    except ChiefPlanError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute(
                "UPDATE chief_request_submissions SET status='Failed',updated_at=? WHERE request_key=?",
                (utc_now(), request_key),
            )
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    chief_provider_id,
                    str(chief_status.get("model", "")),
                    "chief_plan",
                    "Failed",
                    latency_ms,
                    len(executive_request),
                    0,
                    str(exc)[:500],
                    utc_now(),
                ),
            )
            conn.execute(
                "UPDATE agents SET building_id='manor',status='Available',task_id=NULL,updated_at=? WHERE id='chief'",
                (utc_now(),),
            )
            log(conn, "ai_error", "Chief of Staff", "Could not create a valid project plan. No project was created.")
        await hub.broadcast()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = str(exc)[:500]
        with db() as conn:
            conn.execute(
                "UPDATE chief_request_submissions SET status='Failed',updated_at=? WHERE request_key=?",
                (utc_now(), request_key),
            )
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,message,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    chief_provider_id,
                    str(chief_status.get("model", "")),
                    "chief_plan",
                    "Failed",
                    latency_ms,
                    len(executive_request),
                    0,
                    message,
                    utc_now(),
                ),
            )
            conn.execute(
                "UPDATE agents SET building_id='manor',status='Available',task_id=NULL,updated_at=? WHERE id='chief'",
                (utc_now(),),
            )
            log(conn, "ai_error", "Chief of Staff", "Chief planning provider failed. No project was created.")
        await hub.broadcast()
        raise HTTPException(status_code=502, detail=message) from exc


@app.post("/api/demo/start")
async def api_demo_start(req: ProjectRequest) -> dict[str, Any]:
    global workflow_task
    if workflow_task and not workflow_task.done():
        raise HTTPException(status_code=409, detail="A workflow is already running.")
    with db() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE status='Pending'").fetchone()[0]
    if pending:
        raise HTTPException(status_code=409, detail="Resolve or reset the pending human approval before starting another project.")
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Project title cannot be empty.")

    now = utc_now()
    with db() as conn:
        reset_agents(conn)
        cur = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", (title, "Active", now, now))
        project_id = int(cur.lastrowid)
        task_specs = [
            ("intake", "Triage request and create work plan", "chief", 1),
            ("research", "Research physical and digital document preservation", "research", 2),
            ("programs", "Create a 45-minute all-ages class outline", "programs", 3),
            ("review", "Review proposal and prepare human approval", "chief", 4),
        ]
        task_ids: dict[str, int] = {}
        for key, task_title, owner, sequence in task_specs:
            cur = conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (project_id, task_title, owner, "Waiting", sequence, now, now),
            )
            task_ids[key] = int(cur.lastrowid)
        log(conn, "project", "Human", f"Created project: {title}")

    await hub.broadcast()
    workflow_task = asyncio.create_task(demo_workflow(project_id, task_ids))
    return {"status": "started", "project_id": project_id}


@app.post("/api/projects/{project_id}/notes")
async def api_project_note(project_id: int, req: NoteRequest) -> dict[str, Any]:
    body = req.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Note cannot be empty.")
    with db() as conn:
        project = conn.execute("SELECT id,title FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        cur = conn.execute(
            "INSERT INTO notes(project_id,task_id,author,body,created_at) VALUES(?,?,?,?,?)",
            (project_id, None, req.author.strip() or "Human", body, utc_now()),
        )
        log(conn, "note", req.author.strip() or "Human", f"Added a project note to: {project['title']}")
        note_id = int(cur.lastrowid)
    await hub.broadcast()
    return {"status": "saved", "note_id": note_id}


@app.post("/api/tasks/{task_id}/notes")
async def api_task_note(task_id: int, req: NoteRequest) -> dict[str, Any]:
    body = req.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Note cannot be empty.")
    with db() as conn:
        task = conn.execute("SELECT id,project_id,title FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        cur = conn.execute(
            "INSERT INTO notes(project_id,task_id,author,body,created_at) VALUES(?,?,?,?,?)",
            (task["project_id"], task_id, req.author.strip() or "Human", body, utc_now()),
        )
        log(conn, "note", req.author.strip() or "Human", f"Added a task note to: {task['title']}")
        note_id = int(cur.lastrowid)
    await hub.broadcast()
    return {"status": "saved", "note_id": note_id}


@app.post("/api/projects/{project_id}/revision/plan")
async def api_revision_plan(project_id: int) -> dict[str, Any]:
    with db() as conn:
        project = conn.execute(
            "SELECT * FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        if project["status"] != "Needs Revision":
            raise HTTPException(
                status_code=409,
                detail="This project is not currently waiting for a revision plan.",
            )

        request = latest_revision_request(conn, project_id)
        if not request:
            raise HTTPException(
                status_code=409,
                detail="No human revision instruction is recorded for this project.",
            )
        if request["status"] not in {"Requested","Planning Failed","Changes Requested"}:
            raise HTTPException(
                status_code=409,
                detail=f"The latest revision request is currently {request['status']}.",
            )

        pending = conn.execute(
            """
            SELECT id FROM approvals
            WHERE project_id=? AND status='Pending'
              AND title LIKE 'Approve revision plan:%'
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if pending:
            raise HTTPException(
                status_code=409,
                detail="A revision plan is already waiting for human approval.",
            )

        original_plan = conn.execute(
            "SELECT * FROM chief_plans WHERE project_id=?",
            (project_id,),
        ).fetchone()
        task_rows = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE project_id=?
            ORDER BY sequence,id
            """,
            (project_id,),
        ).fetchall()
        deliverable_rows = conn.execute(
            """
            SELECT *
            FROM deliverables
            WHERE project_id=? AND status!='Superseded'
            ORDER BY deliverable_type,title,id
            """,
            (project_id,),
        ).fetchall()
        review_row = conn.execute(
            """
            SELECT content_json
            FROM chief_review_artifacts
            WHERE project_id=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()

        revision_number = int(
            conn.execute(
                "SELECT COALESCE(MAX(revision_number),0)+1 FROM revision_plans WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
        )

    def parse_list(raw: str | None) -> list[str]:
        values = _safe_json_list(raw)
        return [str(value) for value in values]

    project_summary = original_plan["summary"] if original_plan else project["title"]
    success_criteria = parse_list(
        original_plan["success_criteria_json"] if original_plan else None
    )
    previous_review = _safe_json_object(
        review_row["content_json"] if review_row else None
    )

    tasks_for_chief = [
        {
            "task_id": int(row["id"]),
            "sequence": int(row["sequence"]),
            "title": row["title"],
            "owner": row["owner_agent_id"],
            "brief": row["brief"] or row["title"],
            "status": row["status"],
            "result_excerpt": str(row["result"] or "")[:1600],
        }
        for row in task_rows
    ]
    outputs_for_chief = [
        {
            "deliverable_key": row["deliverable_key"],
            "deliverable_type": row["deliverable_type"],
            "title": row["title"],
            "purpose": row["purpose"],
            "status": row["status"],
            "version": int(row["version"]),
            "chief_review_status": row["chief_review_status"],
            "chief_review_note": row["chief_review_note"],
            "verification_items": _safe_json_list(row["verification_json"]),
            "content_excerpt": str(row["content_md"] or "")[:1800],
        }
        for row in deliverable_rows
    ]

    chief_provider_id = role_provider_id("chief")
    chief_status = provider_public_status(chief_provider_id)
    try:
        require_ai_allowed("chief_revision_plan", chief_provider_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    provider = get_role_provider("chief")
    with db() as conn:
        institutional_memory_for_prompt_context = institutional_memory_for_prompt(conn, project_id)
        playbook_context = playbooks_for_prompt(conn, project_id)
    await set_agent(
        "chief",
        building="manor",
        status=f"Planning revision {revision_number} with {chief_status['provider']}",
        task_id=None,
    )
    await add_log(
        "revision",
        "Chief of Staff",
        f"Reviewing the human revision request for {project['title']} and selecting only the work that needs to reopen.",
    )

    started = time.perf_counter()
    try:
        result = await asyncio.to_thread(
            run_chief_revision_plan,
            provider,
            project_title=project["title"],
            project_summary=project_summary,
            success_criteria=success_criteria,
            human_revision_request=request["request_text"],
            tasks=tasks_for_chief,
            deliverables=outputs_for_chief,
            previous_chief_review=previous_review,
            institutional_memory=institutional_memory_for_prompt_context,
            playbooks=playbook_context,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute(
                """
                INSERT INTO ai_calls(
                    provider,model,operation,status,latency_ms,input_chars,output_chars,
                    message,project_id,task_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    chief_provider_id,
                    str(chief_status.get("model", "")),
                    "chief_revision_plan",
                    "Failed",
                    latency_ms,
                    len(str(request["request_text"])),
                    0,
                    str(exc)[:500],
                    project_id,
                    None,
                    utc_now(),
                ),
            )
            conn.execute(
                "UPDATE revision_requests SET status='Planning Failed',updated_at=? WHERE id=?",
                (utc_now(), int(request["id"])),
            )
        await set_agent(
            "chief",
            building="manor",
            status="Revision planning blocked — needs attention",
            task_id=None,
        )
        await hub.broadcast()
        raise HTTPException(
            status_code=502,
            detail=f"Chief revision planning failed: {exc}",
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    generation = result.generation
    plan = result.plan
    now = utc_now()

    # Consistency guard: if the Chief selects an output for a new version,
    # make sure its non-Chief source task is also reopened. This is resolved
    # locally and does not require another model call.
    task_owner_by_id = {
        int(row["id"]): str(row["owner_agent_id"])
        for row in task_rows
    }
    output_source_by_key = {
        str(row["deliverable_key"]): (
            int(row["source_task_id"]) if row["source_task_id"] is not None else None
        )
        for row in deliverable_rows
    }
    output_title_by_key = {
        str(row["deliverable_key"]): str(row["title"])
        for row in deliverable_rows
    }

    selected_task_ids = [
        int(item["task_id"])
        for item in plan["task_revisions"]
    ]
    selected_output_keys = [
        str(item["deliverable_key"])
        for item in plan["deliverable_revisions"]
    ]

    for key in selected_output_keys:
        source_task_id = output_source_by_key.get(key)
        if source_task_id is None:
            continue
        if task_owner_by_id.get(source_task_id) == "chief":
            continue
        if source_task_id in selected_task_ids:
            continue
        plan["task_revisions"].append({
            "task_id": source_task_id,
            "reason": f"Required to create a revised version of {output_title_by_key.get(key, key)}.",
            "revision_brief": (
                "Revise the prior task only as needed to satisfy the human revision instruction "
                f"and create a new version of {output_title_by_key.get(key, key)}. "
                "Preserve useful prior work that is not affected by the requested change."
            ),
        })
        selected_task_ids.append(source_task_id)

    with db() as conn:
        conn.execute(
            """
            INSERT INTO revision_plans(
                project_id,request_id,revision_number,summary,task_revisions_json,
                deliverable_revisions_json,preserve_keys_json,questions_json,
                provider,model,attempt_count,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                project_id,
                int(request["id"]),
                revision_number,
                plan["revision_summary"],
                json.dumps(plan["task_revisions"], ensure_ascii=False),
                json.dumps(plan["deliverable_revisions"], ensure_ascii=False),
                json.dumps(plan["preserve_deliverable_keys"], ensure_ascii=False),
                json.dumps(plan["questions_for_executive"], ensure_ascii=False),
                generation.provider,
                generation.model,
                result.attempt_count,
                "Awaiting Approval",
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE revision_requests SET status='Awaiting Approval',updated_at=? WHERE id=?",
            (now, int(request["id"])),
        )
        conn.execute(
            "UPDATE projects SET status='Awaiting Revision Approval',updated_at=? WHERE id=?",
            (now, project_id),
        )

        task_titles = {
            int(row["id"]): row["title"]
            for row in task_rows
        }
        output_titles = {
            row["deliverable_key"]: row["title"]
            for row in deliverable_rows
        }
        task_summary = "; ".join(
            task_titles.get(task_id, f"Task {task_id}")
            for task_id in selected_task_ids
        ) or "No specialist tasks selected"
        output_summary = "; ".join(
            output_titles.get(key, key)
            for key in selected_output_keys
        ) or "No existing output selected"

        approval_summary = (
            f"Revision {revision_number}: {plan['revision_summary']} "
            f"Reopen tasks: {task_summary}. "
            f"Create new versions for: {output_summary}. "
            f"Preserve {len(plan['preserve_deliverable_keys'])} other current output(s). "
            "Approval authorizes only this selective internal revision workflow; no external action is authorized."
        )[:4000]

        conn.execute(
            """
            INSERT INTO approvals(
                project_id,title,summary,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                project_id,
                f"Approve revision plan: {project['title']} — Revision {revision_number}",
                approval_summary,
                "Pending",
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO ai_calls(
                provider,model,operation,status,latency_ms,input_chars,output_chars,
                message,project_id,task_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                generation.provider,
                generation.model,
                "chief_revision_plan",
                "Success",
                latency_ms,
                generation.input_chars,
                generation.output_chars,
                (
                    f"Chief prepared selective revision {revision_number}: "
                    f"{len(selected_task_ids)} task(s), {len(selected_output_keys)} output(s)."
                ),
                project_id,
                None,
                now,
            ),
        )
        set_workflow_run(
            conn,
            project_id,
            state="Awaiting Revision Approval",
            current_task_id=None,
            last_error=None,
        )
        log(
            conn,
            "revision",
            "Chief of Staff",
            (
                f"Prepared revision {revision_number}: "
                f"{len(selected_task_ids)} task(s) proposed for reopening and "
                f"{len(selected_output_keys)} output(s) proposed for a new version."
            ),
        )
        conn.execute(
            """
            UPDATE agents
            SET building_id='manor',status='Waiting for revision-plan approval',
                task_id=NULL,updated_at=?
            WHERE id='chief'
            """,
            (now,),
        )

    await hub.broadcast()
    return {
        "status": "awaiting_revision_approval",
        "project_id": project_id,
        "revision_number": revision_number,
        "selected_task_count": len(selected_task_ids),
        "selected_output_count": len(selected_output_keys),
        "provider": generation.provider,
        "model": generation.model,
        "latency_ms": latency_ms,
    }


@app.post("/api/tasks/{task_id}/status")
async def api_task_status(task_id: int, req: TaskStatusRequest) -> dict[str, Any]:
    global workflow_task
    if workflow_task and not workflow_task.done():
        raise HTTPException(status_code=409, detail="Wait until the running campus workflow pauses before manually changing task status.")
    allowed = {"Waiting", "In Progress", "Blocked", "Completed"}
    if req.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(sorted(allowed))}")
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (req.status, utc_now(), task_id))
        log(conn, "task", "Human", f"Changed task status to {req.status}: {task['title']}")
    await hub.broadcast()
    return {"status": req.status}


@app.post("/api/projects/{project_id}/resume")
async def api_project_resume(project_id: int) -> dict[str, Any]:
    global workflow_task

    if workflow_task and not workflow_task.done():
        raise HTTPException(
            status_code=409,
            detail="Another campus workflow is already running.",
        )

    with db() as conn:
        project = conn.execute(
            "SELECT * FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project["status"] != "Execution Interrupted":
            raise HTTPException(
                status_code=409,
                detail="Only an interrupted project can be resumed with this recovery action.",
            )

        pending_final = conn.execute(
            """
            SELECT id
            FROM approvals
            WHERE project_id=?
              AND status='Pending'
              AND title LIKE 'Chief final review:%'
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if pending_final:
            raise HTTPException(
                status_code=409,
                detail="This project already has a final review waiting for your decision; it does not need to be retried.",
            )

        control = ai_control_state(conn)
        if not control["enabled"]:
            raise HTTPException(
                status_code=409,
                detail="AI is stopped. Use Resume AI before retrying an interrupted workflow.",
            )

        tasks = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE project_id=?
            ORDER BY sequence,id
            """,
            (project_id,),
        ).fetchall()

        if not tasks:
            raise HTTPException(status_code=409, detail="This project has no tasks to resume.")

        # Only unfinished work is reset. Completed tasks and their artifacts stay intact.
        now = utc_now()
        conn.execute(
            """
            UPDATE tasks
            SET status='Waiting',
                result=NULL,
                updated_at=?
            WHERE project_id=?
              AND status IN ('Blocked','In Progress')
            """,
            (now, project_id),
        )

        refreshed = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE project_id=?
            ORDER BY sequence,id
            """,
            (project_id,),
        ).fetchall()
        first_unfinished = next(
            (task for task in refreshed if task["status"] != "Completed"),
            None,
        )

        if first_unfinished and first_unfinished["owner_agent_id"] in {"chief","research","programs"}:
            role = str(first_unfinished["owner_agent_id"])
            provider_id = role_provider_id(role)
            try:
                require_ai_allowed(f"{role}_resume", provider_id)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        conn.execute(
            "UPDATE projects SET status='Active',updated_at=? WHERE id=?",
            (now, project_id),
        )
        set_workflow_run(
            conn,
            project_id,
            state="Retry Queued",
            current_task_id=int(first_unfinished["id"]) if first_unfinished else None,
            last_error=None,
        )
        reset_agents(conn)
        log(
            conn,
            "recovery",
            "Human",
            (
                f"Retry / Resume Workflow requested for {project['title']}. "
                "Completed tasks and saved artifacts will be preserved."
            ),
        )

    await hub.broadcast()
    workflow_task = asyncio.create_task(
        execute_approved_plan(project_id, resume=True)
    )
    return {
        "status": "resuming",
        "project_id": project_id,
        "completed_tasks_preserved": True,
    }


@app.post("/api/approvals/{approval_id}/decide")
async def api_approval_decide(approval_id: int, req: ApprovalDecision) -> dict[str, Any]:
    global workflow_task

    decision = req.decision.strip().lower()
    if decision not in {"approve", "changes"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'changes'")

    execution_started = False
    revision_execution_started = False
    project_completed = False
    project_id: int | None = None
    archive_result: dict[str, Any] | None = None

    with db() as conn:
        approval = conn.execute(
            "SELECT * FROM approvals WHERE id=?",
            (approval_id,),
        ).fetchone()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        if approval["status"] != "Pending":
            raise HTTPException(status_code=409, detail="Approval has already been decided")

        project = conn.execute(
            "SELECT * FROM projects WHERE id=?",
            (approval["project_id"],),
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project_id = int(project["id"])
        old_project_status = project["status"]
        title = str(approval["title"] or "")
        is_revision_plan = title.startswith("Approve revision plan:")
        is_final_review = title.startswith("Chief final review:")
        status = "Approved" if decision == "approve" else "Changes Requested"
        now = utc_now()

        if decision == "changes":
            new_project_status = "Needs Revision"
        elif is_revision_plan:
            if workflow_task and not workflow_task.done():
                raise HTTPException(
                    status_code=409,
                    detail="Another workflow is already running.",
                )
            revision_plan = conn.execute(
                """
                SELECT *
                FROM revision_plans
                WHERE project_id=? AND status='Awaiting Approval'
                ORDER BY revision_number DESC,id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if not revision_plan:
                raise HTTPException(
                    status_code=409,
                    detail="The revision plan is no longer available for execution.",
                )
            new_project_status = "Active"
            revision_execution_started = True
        elif old_project_status == "Awaiting Approval":
            if workflow_task and not workflow_task.done():
                raise HTTPException(
                    status_code=409,
                    detail="Another workflow is already running.",
                )
            new_project_status = "Active"
            execution_started = True
        elif old_project_status == "Awaiting Execution Review":
            new_project_status = "Completed"
            project_completed = True
        else:
            new_project_status = "Approved for Development"

        conn.execute(
            "UPDATE approvals SET status=?,decision_note=?,updated_at=? WHERE id=?",
            (status, req.note.strip(), now, approval_id),
        )
        conn.execute(
            "UPDATE projects SET status=?,updated_at=? WHERE id=?",
            (new_project_status, now, project_id),
        )

        if req.note.strip():
            conn.execute(
                """
                INSERT INTO notes(project_id,task_id,author,body,created_at)
                VALUES(?,?,?,?,?)
                """,
                (project_id, None, "Human", req.note.strip(), now),
            )

        if revision_execution_started:
            revision_plan = conn.execute(
                """
                SELECT *
                FROM revision_plans
                WHERE project_id=? AND status='Awaiting Approval'
                ORDER BY revision_number DESC,id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            task_revisions = _safe_json_list(revision_plan["task_revisions_json"])
            output_revisions = _safe_json_list(
                revision_plan["deliverable_revisions_json"]
            )
            preserve_keys = [
                str(value)
                for value in _safe_json_list(revision_plan["preserve_keys_json"])
            ]

            selected_task_ids = []
            for item in task_revisions:
                if not isinstance(item, dict):
                    continue
                try:
                    selected_task_ids.append(int(item.get("task_id")))
                except (TypeError, ValueError):
                    continue

            selected_keys = [
                str(item.get("deliverable_key"))
                for item in output_revisions
                if isinstance(item, dict) and str(item.get("deliverable_key") or "")
            ]

            if selected_task_ids:
                placeholders = ",".join("?" for _ in selected_task_ids)
                conn.execute(
                    f"""
                    UPDATE tasks
                    SET status='Waiting',updated_at=?
                    WHERE project_id=? AND id IN ({placeholders})
                    """,
                    (now, project_id, *selected_task_ids),
                )

            # Final Chief review always reruns after selective specialist work.
            final_chief = conn.execute(
                """
                SELECT id
                FROM tasks
                WHERE project_id=? AND owner_agent_id='chief'
                ORDER BY sequence DESC,id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if final_chief:
                conn.execute(
                    "UPDATE tasks SET status='Waiting',updated_at=? WHERE id=?",
                    (now, int(final_chief["id"])),
                )

            # Preserve every current output unless the approved revision plan
            # explicitly selected it for a new version.
            conn.execute(
                """
                UPDATE deliverables
                SET status='Preserved',updated_at=?
                WHERE project_id=? AND status!='Superseded'
                """,
                (now, project_id),
            )

            if selected_keys:
                placeholders = ",".join("?" for _ in selected_keys)
                conn.execute(
                    f"""
                    UPDATE deliverables
                    SET status='Revision Queued',updated_at=?
                    WHERE project_id=?
                      AND status!='Superseded'
                      AND deliverable_key IN ({placeholders})
                    """,
                    (now, project_id, *selected_keys),
                )

            # The executive summary is always revised because the Chief must
            # describe the new package and human decision.
            conn.execute(
                """
                UPDATE deliverables
                SET status='Revision Queued',updated_at=?
                WHERE project_id=?
                  AND status!='Superseded'
                  AND deliverable_type IN ('executive_summary','decision_memo')
                """,
                (now, project_id),
            )

            conn.execute(
                """
                UPDATE revision_plans
                SET status='Executing',updated_at=?
                WHERE id=?
                """,
                (now, int(revision_plan["id"])),
            )
            conn.execute(
                """
                UPDATE revision_requests
                SET status='Executing',updated_at=?
                WHERE id=?
                """,
                (now, int(revision_plan["request_id"])),
            )
            set_workflow_run(
                conn,
                project_id,
                state="Revision Queued",
                current_task_id=selected_task_ids[0] if selected_task_ids else None,
                last_error=None,
            )
            log(
                conn,
                "revision",
                "Human",
                (
                    f"Approved selective revision {revision_plan['revision_number']}. "
                    f"{len(selected_task_ids)} specialist task(s) will reopen; "
                    f"{len(selected_keys)} selected output(s) will receive a new version. "
                    f"{len(preserve_keys)} output key(s) are preserved."
                ),
            )
            conn.execute(
                """
                UPDATE agents
                SET building_id='manor',
                    status='Revision plan approved — starting selective work',
                    task_id=NULL,updated_at=?
                WHERE id='chief'
                """,
                (now,),
            )

        elif execution_started:
            log(
                conn,
                "approval",
                "Human",
                "Chief's plan approved. Internal campus execution is authorized and starting now. No external action is authorized.",
            )
            conn.execute(
                """
                UPDATE agents
                SET building_id='manor',status='Plan approved — starting execution',
                    task_id=NULL,updated_at=?
                WHERE id='chief'
                """,
                (now,),
            )

        elif project_completed:
            conn.execute(
                """
                UPDATE deliverables
                SET status='Approved',updated_at=?
                WHERE project_id=? AND status!='Superseded'
                """,
                (now, project_id),
            )

            latest_revision = latest_revision_plan(conn, project_id)
            if latest_revision and latest_revision["status"] == "Awaiting Human Review":
                conn.execute(
                    "UPDATE revision_plans SET status='Completed',updated_at=? WHERE id=?",
                    (now, int(latest_revision["id"])),
                )
                conn.execute(
                    "UPDATE revision_requests SET status='Completed',updated_at=? WHERE id=?",
                    (now, int(latest_revision["request_id"])),
                )

            set_workflow_run(
                conn,
                project_id,
                state="Completed",
                current_task_id=None,
                last_error=None,
            )
            archive_result = archive_approved_programs_project(
                conn, project_id=project_id, approval_id=approval_id
            )
            log(
                conn,
                "approval",
                "Human",
                "Stella final review approved. The v0.8.7.4.2 internal package and current output versions are accepted. "
                f"Programs Auto-Archive: {archive_result.get('status', 'Skipped')} "
                f"({archive_result.get('material_count', 0)} new trusted Library material(s)).",
            )
            reset_agents(conn)

        else:
            if decision == "changes" and is_revision_plan:
                revision_plan = conn.execute(
                    """
                    SELECT *
                    FROM revision_plans
                    WHERE project_id=? AND status='Awaiting Approval'
                    ORDER BY revision_number DESC,id DESC
                    LIMIT 1
                    """,
                    (project_id,),
                ).fetchone()
                if revision_plan:
                    conn.execute(
                        "UPDATE revision_plans SET status='Changes Requested',updated_at=? WHERE id=?",
                        (now, int(revision_plan["id"])),
                    )
                    request = conn.execute(
                        "SELECT * FROM revision_requests WHERE id=?",
                        (int(revision_plan["request_id"]),),
                    ).fetchone()
                    if request:
                        revised_text = str(request["request_text"])
                        if req.note.strip():
                            revised_text += (
                                "\nAdditional executive direction on the revision plan: "
                                + req.note.strip()
                            )
                        conn.execute(
                            """
                            UPDATE revision_requests
                            SET request_text=?,status='Requested',updated_at=?
                            WHERE id=?
                            """,
                            (revised_text[:6000], now, int(request["id"])),
                        )

                set_workflow_run(
                    conn,
                    project_id,
                    state="Needs Revision",
                    current_task_id=None,
                    last_error=None,
                )
                log(
                    conn,
                    "revision",
                    "Human",
                    "Requested changes to the Chief's revision plan. No revision work started.",
                )

            elif decision == "changes" and is_final_review:
                request_text = (
                    req.note.strip()
                    or "Revise the internal package to address the Chief review, unresolved gaps, and any items that should be improved before acceptance."
                )
                conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        approval_id,
                        request_text[:6000],
                        "Requested",
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE deliverables
                    SET status='Revision Review',updated_at=?
                    WHERE project_id=? AND status!='Superseded'
                    """,
                    (now, project_id),
                )

                prior_revision = latest_revision_plan(conn, project_id)
                if prior_revision and prior_revision["status"] == "Awaiting Human Review":
                    conn.execute(
                        "UPDATE revision_plans SET status='Changes Requested',updated_at=? WHERE id=?",
                        (now, int(prior_revision["id"])),
                    )
                    conn.execute(
                        "UPDATE revision_requests SET status='Changes Requested',updated_at=? WHERE id=?",
                        (now, int(prior_revision["request_id"])),
                    )

                set_workflow_run(
                    conn,
                    project_id,
                    state="Needs Revision",
                    current_task_id=None,
                    last_error=None,
                )
                log(
                    conn,
                    "revision",
                    "Human",
                    "Requested revisions to the finished package. Current output versions were preserved and are waiting for a selective Chief revision plan.",
                )

            elif decision == "changes":
                existing_run = conn.execute(
                    "SELECT project_id FROM workflow_runs WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                if existing_run:
                    set_workflow_run(
                        conn,
                        project_id,
                        state="Needs Revision",
                        current_task_id=None,
                        last_error=None,
                    )
                log(
                    conn,
                    "approval",
                    "Human",
                    "Changes requested. No external action was taken.",
                )
            else:
                log(
                    conn,
                    "approval",
                    "Human",
                    f"Decision recorded: {status}. No external action was taken.",
                )

            conn.execute(
                "UPDATE agents SET status='Available',task_id=NULL,updated_at=? WHERE id='chief'",
                (now,),
            )

    await hub.broadcast()

    if execution_started and project_id is not None:
        workflow_task = asyncio.create_task(
            execute_approved_plan(project_id)
        )
    elif revision_execution_started and project_id is not None:
        workflow_task = asyncio.create_task(
            execute_approved_plan(project_id, revision=True)
        )

    return {
        "status": status,
        "execution_started": execution_started,
        "revision_execution_started": revision_execution_started,
        "project_completed": project_completed,
        "project_id": project_id,
        "programs_auto_archive": archive_result,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
